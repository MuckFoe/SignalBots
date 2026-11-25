"""Spec 005 FR12 (admin add/remove/list) and FR13 (no "groups" command)."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from commands import handle_command
from storage import Storage

GROUP = "group-admins"
SCOPE = f"group:{GROUP}"
ANNA, BEN, CARL = "+491700000001", "+491700000002", "+491700000003"


def _text(result: object) -> str:
    if isinstance(result, list):
        return "\n".join(str(part) for part in result)
    if isinstance(result, dict):
        return str(result.get("reply", ""))
    return str(result)


class AdminMemberTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.storage = Storage(os.path.join(self.tmp.name, "chores.db"))
        env = patch.dict(os.environ, {"BOT_REGISTRY": "", "BOT_INSTANCE_ID": "default"})
        env.start()
        self.addCleanup(env.stop)
        self.say(ANNA, "english")  # Anna sets the language and becomes the first admin
        for sender, name in ((ANNA, "Anna"), (BEN, "Ben"), (CARL, "Carl")):
            self.storage.set_display_name(SCOPE, sender, name)

    def say(self, sender: str, message: str) -> str:
        return _text(handle_command(self.storage, message, sender, SCOPE, GROUP))

    def test_admin_adds_member_who_then_counts_as_admin(self) -> None:
        self.assertIn("Ben is now an admin", self.say(ANNA, "admin add Ben"))
        self.assertTrue(self.storage.is_admin(SCOPE, BEN))
        self.assertIn("already an admin", self.say(ANNA, "admin add ben"))

    def test_non_admin_cannot_grant_or_take_admin(self) -> None:
        self.assertIn("Only admins", self.say(BEN, "admin add Ben"))
        self.assertIn("Only admins", self.say(BEN, "admin remove Anna"))
        self.assertFalse(self.storage.is_admin(SCOPE, BEN))
        self.assertTrue(self.storage.is_admin(SCOPE, ANNA))

    def test_last_admin_cannot_be_removed(self) -> None:
        self.assertIn("last admin", self.say(ANNA, "admin remove Anna"))
        self.assertTrue(self.storage.is_admin(SCOPE, ANNA))
        self.say(ANNA, "admin add Ben")
        self.assertIn("no longer an admin", self.say(BEN, "admin remove Anna"))
        self.assertFalse(self.storage.is_admin(SCOPE, ANNA))

    def test_remove_of_a_non_admin_and_unknown_names(self) -> None:
        self.assertIn("Carl is not an admin", self.say(ANNA, "admin remove Carl"))
        self.assertIn("don't know a group member called 'Dora'", self.say(ANNA, "admin add Dora"))
        self.assertIn("Usage: admin add", self.say(ANNA, "admin add"))

    def test_list_shows_admins_by_name(self) -> None:
        self.say(ANNA, "admin add Carl")
        listing = self.say(BEN, "admin list")
        self.assertIn("- Anna", listing)
        self.assertIn("- Carl", listing)
        self.assertNotIn("Ben", listing)

    def test_german_forms(self) -> None:
        self.say(ANNA, "admin sprache deutsch")
        self.assertIn("ist jetzt Admin", self.say(ANNA, "admin hinzufügen Ben"))
        self.assertIn("ist kein Admin mehr", self.say(ANNA, "admin entfernen Ben"))
        self.assertIn("Admins dieser Gruppe", self.say(ANNA, "admin liste"))

    def test_admin_add_does_not_add_a_chore(self) -> None:
        self.say(ANNA, "admin add Ben")
        self.assertEqual(self.storage.list_chores(SCOPE), [])

    def test_groups_command_is_gone(self) -> None:
        self.storage.register_group("some-other-group")
        for message in ("groups", "gruppen", "admin groups"):
            self.assertNotIn("some-other-group", self.say(BEN, message))


if __name__ == "__main__":
    unittest.main()
