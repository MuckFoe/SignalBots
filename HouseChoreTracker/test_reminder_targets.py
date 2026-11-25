"""Spec 004 FR6: reminders reach the chat their chore belongs to, and nobody else."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

_TMP = tempfile.TemporaryDirectory()
os.environ.setdefault("SIGNAL_BOT_NUMBER", "+10000000000")
os.environ.setdefault("DATABASE_PATH", os.path.join(_TMP.name, "chores.db"))
import app as chore_app  # noqa: E402  (needs the env above)


class _Stop(Exception):
    pass


def _due(scope_id: str) -> dict:
    return {"id": 1, "scope_id": scope_id, "name": "Bins", "requires_confirmation": 1}


class ReminderTargetTests(unittest.TestCase):
    def run_loop_once(self, due_rows: list[dict], vacation_events: list[dict] | None = None) -> list[tuple]:
        sent: list[tuple] = []
        storage = chore_app.storage
        patches = [
            mock.patch.object(chore_app, "_queue_signal_reply", lambda *args: sent.append(args)),
            mock.patch.object(storage, "process_vacation_transitions", return_value=vacation_events or []),
            mock.patch.object(storage, "due_reminders", return_value=due_rows),
            mock.patch.object(storage, "is_reminders_paused", return_value=False),
            mock.patch.object(storage, "is_quiet_time", return_value=False),
            mock.patch.object(storage, "mark_reminder_sent"),
            mock.patch.object(storage, "list_groups", return_value=[]),
            mock.patch.object(storage, "list_contacts", return_value=["+111", "+222", "+333"]),
            mock.patch.object(chore_app, "format_vacation_event", return_value="vacation"),
            mock.patch.object(chore_app.time, "sleep", side_effect=_Stop),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        with self.assertRaises(_Stop):
            chore_app._run_reminder_loop()
        return sent

    def test_direct_chat_reminder_goes_only_to_that_chat(self) -> None:
        sent = self.run_loop_once([_due("dm:+222")])
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][:2], (None, "+222"))

    def test_group_reminder_goes_to_the_group(self) -> None:
        sent = self.run_loop_once([_due("group:abc")])
        self.assertEqual([args[:2] for args in sent], [("abc", "")])

    def test_direct_chat_vacation_notice_goes_only_to_that_chat(self) -> None:
        sent = self.run_loop_once([], [{"scope_id": "dm:+333"}])
        self.assertEqual([args[:2] for args in sent], [(None, "+333")])


if __name__ == "__main__":
    unittest.main()
