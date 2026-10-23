from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

os.environ["SIGNAL_BOT_NUMBER"] = "+491500000000"
os.environ["DATABASE_PATH"] = os.path.join(tempfile.mkdtemp(), "router.db")

import app  # noqa: E402
from identity import IdentityStore  # noqa: E402

MORITZ = "+491700000001"
MORITZ_WA, MORITZ_LID, MORITZ_UUID = "491700000001@c.us", "40631279829046@lid", "70a4ae95-d4df-444f-86eb-a9a1dc1416d6"
WA_GROUP, OTHER_WA_GROUP = "120363000000000001@g.us", "120363000000000002@g.us"


class IdentityStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lids = {MORITZ_LID: MORITZ}
        self.store = IdentityStore(os.path.join(tempfile.mkdtemp(), "r.db"), self.lids.get)

    def test_every_form_of_an_id_becomes_the_phone_number(self) -> None:
        self.store.remember(MORITZ_UUID, MORITZ)
        for raw in (MORITZ, MORITZ_WA, MORITZ_LID, MORITZ_UUID):
            self.assertEqual(self.store.canonical(raw), MORITZ, raw)

    def test_unresolvable_ids_pass_through(self) -> None:
        self.assertEqual(self.store.canonical("1@lid"), "1@lid")
        self.assertEqual(self.store.canonical(MORITZ_UUID), MORITZ_UUID)

    def test_aliases_are_merged_once_per_scope(self) -> None:
        self.store.canonical(MORITZ_LID)
        self.assertEqual(self.store.unmerged_aliases("group:a", MORITZ), [MORITZ_WA, MORITZ_LID])
        self.store.mark_merged("group:a", MORITZ_WA, MORITZ)
        self.assertEqual(self.store.unmerged_aliases("group:a", MORITZ), [MORITZ_LID])
        self.assertEqual(self.store.unmerged_aliases("group:b", MORITZ), [MORITZ_WA, MORITZ_LID])


class RouterIdentityTests(unittest.TestCase):
    def _whatsapp(self, participant: str, body: str, group: str = WA_GROUP) -> None:
        payload = {"event": "message", "payload": {"from": group, "participant": participant, "body": body}}
        app.app.test_client().post("/webhook/whatsapp", json=payload)

    def test_whatsapp_member_reaches_the_bot_as_phone_number_and_old_ids_merge(self) -> None:
        calls = []
        with (
            patch.object(app.router, "resolve_job", return_value="chores"),
            patch.object(app.router, "forward", return_value={"reply": "ok"}) as forward,
            patch.object(app, "_call_bot", side_effect=lambda job, path, body: calls.append((path, body)) or {}),
            patch.object(app.identity, "lid_lookup", return_value=MORITZ),
        ):
            self._whatsapp(MORITZ_LID, "liste", OTHER_WA_GROUP)
            self._whatsapp(MORITZ_LID, "status", OTHER_WA_GROUP)

        self.assertEqual(forward.call_args.args[2], MORITZ)
        merged = [(body["old_sender"], body["new_sender"]) for path, body in calls if path == "/internal/merge_member"]
        self.assertEqual(merged, [(MORITZ_WA, MORITZ), (MORITZ_LID, MORITZ)])

    def test_moved_member_with_the_same_number_is_claimed_without_ich_bin(self) -> None:
        scope = f"group:{WA_GROUP}"
        app.migration_store.finish_move("000000", "group:old", scope, "chores", [{"sender": MORITZ, "name": "Moritz"}], "de")
        with (
            patch.object(app.router, "resolve_job", return_value="chores"),
            patch.object(app.router, "forward", return_value={"reply": "ok"}),
            patch.object(app, "_call_bot", return_value={}),
        ):
            self._whatsapp(MORITZ_WA, "liste")
        self.assertEqual(app.migration_store.open_claims(scope), [])
        self.assertEqual(app.migration_store.claimed_name(scope, MORITZ), "Moritz")


if __name__ == "__main__":
    unittest.main()
