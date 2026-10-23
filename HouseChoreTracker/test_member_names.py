from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from commands import handle_command
from storage import Storage

GROUP_A, GROUP_B = "120363000000000001@g.us", "120363000000000002@g.us"
SCOPE_A, SCOPE_B = f"group:{GROUP_A}", f"group:{GROUP_B}"
MORITZ, MORITZ_WA = "+491700000001", "491700000001@c.us"
OTHER = "+491700000009"


def _text(result: object) -> str:
    if isinstance(result, list):
        return "\n".join(str(part) for part in result)
    if isinstance(result, dict):
        return str(result.get("reply", ""))
    return str(result)


class MemberNameTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(os.path.join(self.tmp.name, "chores.db"))
        env = {"BOT_REGISTRY": "", "BOT_INSTANCE_ID": "default", "BOT_INSTANCE_NAME": "House Chore Bot"}
        with patch.dict(os.environ, env):
            for group in (GROUP_A, GROUP_B):
                self._send("sprache deutsch", MORITZ, group)
        self._send("name Moritz", MORITZ, GROUP_A)
        self.storage.add_chore(SCOPE_A, "Müll", {"type": "interval", "value": 1, "unit": "weeks"})

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _send(self, message: str, sender: str, group: str) -> str:
        return _text(handle_command(self.storage, message, sender, f"group:{group}", group))

    def _members(self, scope: str) -> list[tuple[str, str]]:
        with self.storage._connect() as conn:
            rows = conn.execute("SELECT sender, display_name FROM member_names WHERE scope_id = ?", (scope,))
            return sorted((row["sender"], row["display_name"]) for row in rows)

    def test_a_name_taken_by_someone_else_in_the_group_is_refused(self) -> None:
        reply = self._send("name moritz", OTHER, GROUP_A)
        self.assertIn("schon vergeben", reply)
        self.assertIn("ich bin moritz", reply)
        self.assertEqual(self._members(SCOPE_A), [(MORITZ, "Moritz")])

    def test_renaming_yourself_to_your_own_name_is_fine(self) -> None:
        self.assertIn("Dein Name ist jetzt: Moritz", self._send("name Moritz", MORITZ, GROUP_A))

    def test_the_same_name_in_another_group_is_fine(self) -> None:
        self.assertIn("Dein Name ist jetzt: Moritz", self._send("name Moritz", OTHER, GROUP_B))

    def test_name_prompt_on_done_refuses_a_taken_name_and_keeps_asking(self) -> None:
        self.assertIn("Unter welchem Namen", self._send("erledigt Müll", OTHER, GROUP_A))
        self.assertIn("schon vergeben", self._send("Moritz", OTHER, GROUP_A))
        self.assertIn("Müll", self._send("Moritz Z", OTHER, GROUP_A))
        self.assertEqual(self._members(SCOPE_A), [(MORITZ, "Moritz"), (OTHER, "Moritz Z")])

    def test_merging_a_second_id_of_the_same_number_leaves_one_member(self) -> None:
        # The state the bug left behind: the WhatsApp id named itself Moritz too.
        self.storage.set_display_name(SCOPE_A, MORITZ_WA, "Moritz")
        self.storage.mark_done(SCOPE_A, "Müll", MORITZ_WA)
        self.storage.merge_member(SCOPE_A, MORITZ_WA, MORITZ)
        self.assertEqual(self._members(SCOPE_A), [(MORITZ, "Moritz")])
        self.assertEqual(self.storage.user_stats(SCOPE_A, MORITZ)["total_completions"], 1)


if __name__ == "__main__":
    unittest.main()
