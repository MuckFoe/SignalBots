from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from commands import TEXT, handle_command
from schedule_utils import (
    ONE_SHOT_STATS_KEY,
    next_due_at,
    parse_schedule,
    reminder_time_applies,
    schedule_from_storage,
    schedule_to_storage,
    to_local,
)
from storage import Storage


def _text(result: object) -> str:
    if isinstance(result, list):
        return "\n".join(str(part) for part in result)
    if isinstance(result, dict):
        return str(result.get("reply", ""))
    return str(result)


class OneShotChoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(os.path.join(self.tmp.name, "chores.db"))
        self.group_id = "once-group"
        self.scope = f"group:{self.group_id}"
        self.alice = "sender-alice"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _setup_german_group(self) -> None:
        with patch.dict(
            os.environ,
            {"BOT_REGISTRY": "", "BOT_INSTANCE_ID": "default", "BOT_INSTANCE_NAME": "House Chore Bot"},
        ):
            reply = _text(handle_command(self.storage, "sprache deutsch", self.alice, self.scope, self.group_id))
        self.assertIn("Setup fertig", reply)
        self.assertIn("Anna", _text(handle_command(self.storage, "name Anna", self.alice, self.scope, self.group_id)))

    def _setup_english_group(self) -> None:
        with patch.dict(
            os.environ,
            {"BOT_REGISTRY": "", "BOT_INSTANCE_ID": "default", "BOT_INSTANCE_NAME": "House Chore Bot"},
        ):
            reply = _text(handle_command(self.storage, "language en", self.alice, self.scope, self.group_id))
        self.assertIn("Setup complete", reply)
        self.assertIn("Alice", _text(handle_command(self.storage, "name Alice", self.alice, self.scope, self.group_id)))

    def test_parse_once_schedules(self) -> None:
        self.assertEqual(parse_schedule("einmal"), {"type": "once", "when": "today"})
        self.assertEqual(parse_schedule("once tomorrow"), {"type": "once", "when": "tomorrow"})
        self.assertEqual(parse_schedule("einmal Freitag"), {"type": "once", "weekday": 4})
        self.assertEqual(parse_schedule("once 2 hours"), {"type": "once", "value": 2, "unit": "hours"})
        stored = schedule_to_storage({"type": "once", "weekday": 4})
        self.assertEqual(stored, "once:weekday:4")
        self.assertEqual(schedule_from_storage(stored), {"type": "once", "weekday": 4})
        self.assertTrue(reminder_time_applies({"type": "once", "when": "today"}))
        self.assertFalse(reminder_time_applies({"type": "once", "value": 2, "unit": "hours"}))

    def test_once_due_keeps_today_if_time_already_passed(self) -> None:
        base = datetime(2026, 8, 14, 18, 0, tzinfo=timezone.utc)
        due = to_local(
            next_due_at(base, {"type": "once", "when": "today"}, 8 * 60, tz_name="Europe/Berlin"),
            "Europe/Berlin",
        )
        self.assertEqual(due.date().isoformat(), "2026-08-14")
        self.assertEqual((due.hour, due.minute), (8, 0))

    def test_interview_asks_time_and_stats_then_deletes(self) -> None:
        self._setup_german_group()
        started = _text(handle_command(self.storage, "einmal IKEA Freitag", self.alice, self.scope, self.group_id))
        self.assertIn("Uhrzeit", started)
        stats_q = _text(handle_command(self.storage, "19:45", self.alice, self.scope, self.group_id))
        self.assertIn("Statistik", stats_q)
        confirm = _text(handle_command(self.storage, "ja", self.alice, self.scope, self.group_id))
        self.assertIn("bestätigt", confirm.lower())
        added = _text(handle_command(self.storage, "ja", self.alice, self.scope, self.group_id))
        self.assertIn("Einmalaufgabe", added)
        self.assertIn("ja", added.lower())
        self.assertIn("lösche", added.lower())

        row = self.storage._find_chore_case_insensitive(self.scope, "IKEA")
        self.assertIsNotNone(row)
        self.assertEqual(row["one_shot"], 1)
        self.assertEqual(row["count_in_stats"], 1)
        self.assertEqual(row["reminder_at_minutes"], 19 * 60 + 45)

        details = _text(handle_command(self.storage, "liste erweitert", self.alice, self.scope, self.group_id))
        self.assertIn("19:45", details)
        self.assertIn("IKEA", details)
        self.assertTrue("lösche" in details.lower() or "losche" in details.lower())

        deleted = _text(handle_command(self.storage, "lösche IKEA", self.alice, self.scope, self.group_id))
        self.assertIn("gelöscht", deleted.lower())
        listing = _text(handle_command(self.storage, "liste", self.alice, self.scope, self.group_id))
        self.assertNotIn("IKEA", listing)

    def test_stats_opt_out_and_opt_in_bucket(self) -> None:
        self._setup_german_group()

        # no-stats once
        _text(handle_command(self.storage, "einmal Paket Freitag", self.alice, self.scope, self.group_id))
        _text(handle_command(self.storage, "08:00", self.alice, self.scope, self.group_id))
        _text(handle_command(self.storage, "nein", self.alice, self.scope, self.group_id))
        added = _text(handle_command(self.storage, "ja", self.alice, self.scope, self.group_id))
        self.assertIn("nein", added.lower())
        done = _text(handle_command(self.storage, "erledigt Paket", self.alice, self.scope, self.group_id))
        self.assertIn("entfernt", done.lower())
        self.assertIn("nicht", done.lower())

        # stats once
        _text(handle_command(self.storage, "einmal Fenster morgen", self.alice, self.scope, self.group_id))
        _text(handle_command(self.storage, "09:00", self.alice, self.scope, self.group_id))
        _text(handle_command(self.storage, "ja", self.alice, self.scope, self.group_id))
        _text(handle_command(self.storage, "ja", self.alice, self.scope, self.group_id))
        done2 = _text(handle_command(self.storage, "erledigt Fenster", self.alice, self.scope, self.group_id))
        self.assertIn("Einmalaufgaben", done2)

        stats = _text(handle_command(self.storage, "gruppen statistik", self.alice, self.scope, self.group_id))
        self.assertIn("Einmalaufgaben", stats)
        self.assertNotIn("Paket", stats)
        self.assertNotIn("Fenster", stats)
        buckets = {row["name"]: row for row in self.storage.task_stats(self.scope)}
        self.assertEqual(buckets[ONE_SHOT_STATS_KEY]["completions"], 1)

    def test_guided_einmal_full_interview(self) -> None:
        self._setup_german_group()
        started = _text(handle_command(self.storage, "einmal", self.alice, self.scope, self.group_id))
        self.assertIn("Wie heißt", started)
        when = _text(handle_command(self.storage, "Paket abholen", self.alice, self.scope, self.group_id))
        self.assertIn("einmalig", when.lower())
        time_prompt = _text(handle_command(self.storage, "Freitag", self.alice, self.scope, self.group_id))
        self.assertIn("Uhrzeit", time_prompt)
        stats_prompt = _text(handle_command(self.storage, "19:45", self.alice, self.scope, self.group_id))
        self.assertIn("Statistik", stats_prompt)
        confirm = _text(handle_command(self.storage, "ja", self.alice, self.scope, self.group_id))
        self.assertIn("bestätigt", confirm)
        added = _text(handle_command(self.storage, "ja", self.alice, self.scope, self.group_id))
        self.assertIn("Einmalaufgabe", added)
        row = self.storage._find_chore_case_insensitive(self.scope, "Paket abholen")
        self.assertIsNotNone(row)
        self.assertEqual(row["one_shot"], 1)
        self.assertEqual(row["reminder_schedule"], "once:weekday:4")

    def test_english_once_interview_and_edit_delete(self) -> None:
        self._setup_english_group()
        ask_time = _text(handle_command(self.storage, "once library Saturday", self.alice, self.scope, self.group_id))
        self.assertIn("time", ask_time.lower())
        ask_stats = _text(handle_command(self.storage, "11:00", self.alice, self.scope, self.group_id))
        self.assertIn("stats", ask_stats.lower())
        ask_confirm = _text(handle_command(self.storage, "yes", self.alice, self.scope, self.group_id))
        self.assertIn("confirmation", ask_confirm.lower())
        added = _text(handle_command(self.storage, "yes", self.alice, self.scope, self.group_id))
        self.assertIn("one-time", added.lower())

        edit = _text(handle_command(self.storage, "edit library", self.alice, self.scope, self.group_id))
        self.assertIn("delete", edit.lower())
        confirm_del = _text(handle_command(self.storage, "delete", self.alice, self.scope, self.group_id))
        self.assertIn("Delete", confirm_del)
        deleted = _text(handle_command(self.storage, "yes", self.alice, self.scope, self.group_id))
        self.assertIn("Deleted", deleted)
        self.assertNotIn("library", _text(handle_command(self.storage, "list", self.alice, self.scope, self.group_id)))

    def test_help_mentions_once_interview(self) -> None:
        self.assertIn("once", TEXT["en"]["help"])
        self.assertIn("einmal", TEXT["de"]["help"])
        self.assertIn("guided", TEXT["en"]["chore_help"].lower())
        self.assertIn("geführt", TEXT["de"]["chore_help"].lower())
        self.assertIn("stats", TEXT["en"]["chore_help"].lower())
        self.assertIn("Statistik", TEXT["de"]["chore_help"])


if __name__ == "__main__":
    unittest.main()
