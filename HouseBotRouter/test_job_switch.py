"""Spec 001 FR12 (expenses hidden from new chats) and FR13 (admin switch bot)."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("SIGNAL_BOT_NUMBER", "+491500000000")
os.environ.setdefault("DATABASE_PATH", os.path.join(tempfile.mkdtemp(), "router.db"))

import app  # noqa: E402
from group_router import job_picker_text, parse_job_and_language  # noqa: E402

ADMIN, OTHER = "+491700000001", "+491700000002"


class PickerTests(unittest.TestCase):
    def test_expenses_cannot_be_picked_any_more(self) -> None:
        for word in ("expenses", "ausgaben", "kosten", "expenses english"):
            self.assertEqual(parse_job_and_language(word), (None, None), word)
        self.assertEqual(parse_job_and_language("haushalt deutsch"), ("chores", "de"))
        self.assertEqual(parse_job_and_language("rentals"), ("rentals", None))

    def test_picker_no_longer_offers_expenses(self) -> None:
        picker = job_picker_text("?")
        self.assertNotIn("expenses", picker)
        self.assertNotIn("ausgaben", picker)
        self.assertIn("chores", picker)
        self.assertIn("ferien", picker)

    def test_existing_expense_chat_is_still_routed(self) -> None:
        group = "expense-group"
        app.router.set_job(f"group:{group}", "expenses")
        with patch.object(app.router, "forward", return_value={"reply": "balance"}) as forward, patch.object(
            app, "_queue_signal_replies"
        ), patch.object(app, "_call_bot", return_value={}):
            with app.app.app_context():
                app._process_incoming({"source": ADMIN, "message": "balance", "group_id": group, "timestamp": ""})
        self.assertEqual(forward.call_args.args[0], "expenses")


class SwitchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.group = f"switch-{self._testMethodName}"
        self.scope = f"group:{self.group}"
        app.router.set_job(self.scope, "chores")
        self.sent: list = []
        self.forwarded: list[tuple[str, str]] = []
        self.rentals_set_up = False

        def call_bot(job, path, body):
            if path == "/internal/scope":
                set_up = self.rentals_set_up if job == "rentals" else True
                is_admin = set_up and body.get("sender") == ADMIN
                return {"has_admins": set_up, "is_admin": is_admin, "language": "en" if set_up else None}
            return {}

        def forward(job, scope_id, sender, message, group_id, attachments=None):
            self.forwarded.append((job, message))
            return {"reply": f"{job} got {message}"}

        for patcher in (
            patch.object(app, "_call_bot", side_effect=call_bot),
            patch.object(app.router, "forward", side_effect=forward),
            patch.object(app, "_queue_signal_replies", side_effect=lambda group, to, reply: self.sent.append(reply)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def say(self, sender: str, message: str) -> str:
        self.sent.clear()
        with app.app.app_context():
            app._process_incoming({"source": sender, "message": message, "group_id": self.group, "timestamp": ""})
        reply = self.sent[-1] if self.sent else ""
        return "\n".join(reply) if isinstance(reply, list) else str(reply)

    def test_admin_switches_after_picking_and_confirming(self) -> None:
        pick = self.say(ADMIN, "admin switch bot")
        self.assertIn("rentals", pick)
        self.assertNotIn("chores –", pick)
        self.assertIn("Switch this chat from the chore bot to the rental watcher", self.say(ADMIN, "rentals"))
        done = self.say(ADMIN, "yes")
        self.assertIn("now uses the rental watcher", done)
        self.assertEqual(app.router.get_job(self.scope), "rentals")
        # A bot new to the chat is set up in the chat's language right away.
        self.assertEqual(self.forwarded, [("rentals", "language en")])
        self.say(ADMIN, "overview")
        self.assertEqual(self.forwarded[-1], ("rentals", "overview"))

    def test_switching_back_keeps_the_old_bots_setup(self) -> None:
        app.router.set_job(self.scope, "rentals")
        self.rentals_set_up = True
        # rentals -> chores: chore-bot already has admins and data for this chat, so no setup is sent
        self.say(ADMIN, "admin switch bot")
        self.say(ADMIN, "chores")
        self.say(ADMIN, "yes")
        self.assertEqual(app.router.get_job(self.scope), "chores")
        self.assertEqual(self.forwarded, [])

    def test_non_admin_is_refused(self) -> None:
        self.assertIn("Only admins", self.say(OTHER, "admin switch bot"))
        self.assertEqual(app.router.get_job(self.scope), "chores")

    def test_no_or_cancel_keeps_the_job(self) -> None:
        self.say(ADMIN, "admin switch bot")
        self.assertIn("keeps the chore bot", self.say(ADMIN, "cancel"))
        self.say(ADMIN, "admin switch bot")
        self.say(ADMIN, "rentals")
        self.assertIn("keeps the chore bot", self.say(ADMIN, "no"))
        self.assertEqual(app.router.get_job(self.scope), "chores")

    def test_other_text_drops_the_switch_and_goes_to_the_bot(self) -> None:
        self.say(ADMIN, "admin switch bot")
        self.say(ADMIN, "list")
        self.assertEqual(self.forwarded[-1], ("chores", "list"))
        self.say(ADMIN, "yes")
        self.assertEqual(app.router.get_job(self.scope), "chores")

    def test_only_the_starter_can_answer(self) -> None:
        self.say(ADMIN, "admin switch bot")
        self.say(OTHER, "rentals")
        self.assertEqual(self.forwarded[-1], ("chores", "rentals"))
        self.assertIn("Switch this chat", self.say(ADMIN, "rentals"))

    def test_german_start_is_recognised(self) -> None:
        # The group's language comes from its bot (English here), not from the command word.
        self.assertIn("Which bot should this chat use", self.say(ADMIN, "admin bot wechseln"))


if __name__ == "__main__":
    unittest.main()
