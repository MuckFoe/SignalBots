from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from commands import TEXT, format_reminder, handle_command
from schedule_utils import next_due_at, to_local
from storage import Storage


def _text(result: object) -> str:
    if isinstance(result, list):
        return "\n".join(str(part) for part in result)
    if isinstance(result, dict):
        return str(result.get("reply", ""))
    return str(result)


class ExtraCommandSurfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(os.path.join(self.tmp.name, "chores.db"))
        self.group_id = "english-group"
        self.scope = f"group:{self.group_id}"
        self.alice = "sender-alice"
        self.bob = "sender-bob"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _setup_english_group(self) -> None:
        with patch.dict(
            os.environ,
            {"BOT_REGISTRY": "", "BOT_INSTANCE_ID": "default", "BOT_INSTANCE_NAME": "House Chore Bot"},
        ):
            reply = _text(
                handle_command(
                    self.storage,
                    "language en",
                    self.alice,
                    self.scope,
                    self.group_id,
                )
            )
        self.assertIn("Setup complete", reply)
        self.assertTrue(self.storage.is_group_ready(self.scope))

    def test_english_group_setup_and_command_flow(self) -> None:
        self._setup_english_group()
        self.assertIn("Alice", _text(handle_command(self.storage, "name Alice", self.alice, self.scope, self.group_id)))
        self.assertIn("Bob", _text(handle_command(self.storage, "name Bob", self.bob, self.scope, self.group_id)))

        added = _text(handle_command(self.storage, "add bins Thursday", self.alice, self.scope, self.group_id))
        self.assertIn("Added chore", added)
        task = _text(handle_command(self.storage, "todo buy milk", self.alice, self.scope, self.group_id))
        self.assertIn("Added open task", task)
        listing = _text(handle_command(self.storage, "list extend", self.alice, self.scope, self.group_id))
        self.assertIn("bins", listing)
        self.assertIn("buy milk", listing)
        self.assertIn("Thursday", listing)
        self.assertIn("open task", listing)

    def test_weekday_due_time_defaults_and_explicit_time(self) -> None:
        last_done = datetime(2026, 1, 8, 18, 30, tzinfo=timezone.utc)  # Thursday, 19:30 Berlin
        schedule = {"type": "weekday", "weekday": 3}

        default_due = to_local(next_due_at(last_done, schedule, tz_name="Europe/Berlin"), "Europe/Berlin")
        explicit_due = to_local(
            next_due_at(last_done, schedule, reminder_at_minutes=19 * 60 + 45, tz_name="Europe/Berlin"),
            "Europe/Berlin",
        )

        self.assertEqual((default_due.date().isoformat(), default_due.hour, default_due.minute), ("2026-01-15", 8, 0))
        self.assertEqual((explicit_due.date().isoformat(), explicit_due.hour, explicit_due.minute), ("2026-01-15", 19, 45))

    def test_done_by_person_in_english_and_german_aliases(self) -> None:
        self._setup_english_group()
        self.storage.set_display_name(self.scope, self.alice, "Alice")
        self.storage.set_display_name(self.scope, self.bob, "Bob")
        self.assertTrue(self.storage.add_chore(self.scope, "Milk", {"type": "none"}))
        self.assertTrue(self.storage.add_chore(self.scope, "Trash", {"type": "none"}))

        english = _text(handle_command(self.storage, "done Milk by Bob", self.alice, self.scope, self.group_id))
        german_alias = _text(handle_command(self.storage, "erledigt Milk von Alice", self.bob, self.scope, self.group_id))
        english_for = _text(handle_command(self.storage, "done Trash for Bob", self.alice, self.scope, self.group_id))
        german_for = _text(handle_command(self.storage, "erledigt Trash für Alice", self.bob, self.scope, self.group_id))

        self.assertIn("Bob", english)
        self.assertIn("Alice", german_alias)
        self.assertIn("Bob", english_for)
        self.assertIn("Alice", german_for)
        self.assertEqual(
            [row["sender"] for row in self.storage.recent_logs(self.scope)],
            [self.alice, self.bob, self.alice, self.bob],
        )

    def test_quiet_hours_wrap_midnight_and_end_is_exclusive(self) -> None:
        self.assertTrue(self.storage.set_quiet_hours(self.scope, 22 * 60, 7 * 60))
        self.assertTrue(self.storage.is_quiet_time(self.scope, 23 * 60))
        self.assertTrue(self.storage.is_quiet_time(self.scope, 6 * 60 + 59))
        self.assertFalse(self.storage.is_quiet_time(self.scope, 7 * 60))
        self.assertFalse(self.storage.is_quiet_time(self.scope, 12 * 60))

    def test_active_vacation_pauses_reminders(self) -> None:
        self.assertFalse(self.storage.is_reminders_paused(self.scope))
        vacation = self.storage.create_member_vacation(
            self.scope,
            self.alice,
            delay=timedelta(0),
            duration=timedelta(days=2),
        )
        self.assertEqual(vacation["status"], "active")
        self.assertTrue(self.storage.is_reminders_paused(self.scope))
        self.assertTrue(self.storage.cancel_member_vacation(self.scope, self.alice))
        self.assertFalse(self.storage.is_reminders_paused(self.scope))

    def test_duplicate_rejected_and_open_task_differs_from_scheduled(self) -> None:
        self._setup_english_group()
        first = _text(handle_command(self.storage, "add bins Thursday", self.alice, self.scope, self.group_id))
        duplicate = _text(handle_command(self.storage, "add BINS Thursday", self.alice, self.scope, self.group_id))
        open_task = _text(handle_command(self.storage, "todo vacuum bags", self.alice, self.scope, self.group_id))

        self.assertIn("Added chore", first)
        self.assertIn("already exists", duplicate)
        self.assertIn("Added open task", open_task)
        rows = {row["name"]: row for row in self.storage.list_chores(self.scope)}
        self.assertEqual(rows["bins"]["reminder_schedule"], "weekday:3")
        self.assertEqual(rows["vacuum bags"]["reminder_schedule"], "none")

    def test_cancel_mid_edit_keeps_original_chore(self) -> None:
        self._setup_english_group()
        handle_command(self.storage, "add bins Thursday", self.alice, self.scope, self.group_id)
        self.assertIn("What do you want to edit", _text(handle_command(self.storage, "edit bins", self.alice, self.scope, self.group_id)))
        self.assertIn("due schedule", _text(handle_command(self.storage, "schedule", self.alice, self.scope, self.group_id)))
        self.assertIn("Cancelled", _text(handle_command(self.storage, "cancel", self.alice, self.scope, self.group_id)))

        row = self.storage.list_chores(self.scope)[0]
        self.assertEqual(row["name"], "bins")
        self.assertEqual(row["reminder_schedule"], "weekday:3")
        self.assertIsNone(self.storage.get_pending_chore_edit(self.scope, self.alice))

    def test_bare_statistik_returns_stats_usage(self) -> None:
        self._setup_english_group()
        reply = _text(handle_command(self.storage, "statistik", self.alice, self.scope, self.group_id))
        self.assertIn("my stats", reply)
        self.assertIn("group stats", reply)

    def test_help_pointers_are_real_commands_in_both_languages(self) -> None:
        self._setup_english_group()
        self.assertIn("Add a chore", _text(handle_command(self.storage, "chore help", self.alice, self.scope, self.group_id)))
        self.assertIn("Change a chore", _text(handle_command(self.storage, "edit help", self.alice, self.scope, self.group_id)))

        german_scope = "dm:german"
        self.storage.set_language(german_scope, "de")
        self.assertIn("Aufgabe anlegen", _text(handle_command(self.storage, "aufgabe hilfe", "german", german_scope)))
        self.assertIn("Aufgabe ändern", _text(handle_command(self.storage, "bearbeite hilfe", "german", german_scope)))

    def test_quick_add_uses_confirmation_default_and_reminder_copy(self) -> None:
        self._setup_english_group()
        handle_command(self.storage, "add bins Thursday", self.alice, self.scope, self.group_id)
        row = self.storage.list_chores(self.scope)[0]

        self.assertEqual(row["requires_confirmation"], 1)
        self.assertIn("done bins", format_reminder(self.storage, self.scope, "bins", requires_confirmation=True))
        self.assertNotEqual(TEXT["en"]["reminder"], TEXT["en"]["reminder_no_confirmation"])

    def test_unknown_chat_is_ignored_and_typos_are_suggested(self) -> None:
        self._setup_english_group()
        self.assertEqual(_text(handle_command(self.storage, "Shall we cook pasta tonight?", self.alice, self.scope, self.group_id)), "")
        self.assertEqual(_text(handle_command(self.storage, "ok cool", self.alice, self.scope, self.group_id)), "")
        suggestion = _text(handle_command(self.storage, "listt", self.alice, self.scope, self.group_id))
        self.assertIn("Did you mean", suggestion)
        self.assertIn("list", suggestion)
        done_typo = _text(handle_command(self.storage, "doone bins", self.alice, self.scope, self.group_id))
        self.assertIn("done", done_typo)

    def test_bare_delete_commands_show_existing_usage_copy(self) -> None:
        self._setup_english_group()
        self.assertIn("Usage: delete", _text(handle_command(self.storage, "delete", self.alice, self.scope, self.group_id)))
        self.storage.set_language(self.scope, "de")
        self.assertIn("So geht's: lösche", _text(handle_command(self.storage, "lösche", self.alice, self.scope, self.group_id)))


if __name__ == "__main__":
    unittest.main()
