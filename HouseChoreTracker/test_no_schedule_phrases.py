from __future__ import annotations

import os
import tempfile
import unittest

from commands import handle_command, is_not_understood_reply
from schedule_utils import parse_schedule
from storage import Storage

NONE = {"type": "none"}
SENDER = "sender-mo"
SCOPE = "group:test-group"


class NoSchedulePhraseTests(unittest.TestCase):
    def test_variants_typos_and_punctuation_mean_no_schedule(self) -> None:
        for text in (
            "ohne zeitplan", "Ohne Zeitplan.", "ohne", "ohne termin", "kein termin", "keinen Termin!",
            "ohen", "ohen zeitplan", "ohne zeitpaln", "kein temin", "no schedule.", "no shedule",
        ):
            with self.subTest(text=text):
                self.assertEqual(parse_schedule(text), NONE)

    def test_real_schedules_and_near_misses_are_not_no_schedule(self) -> None:
        self.assertEqual(parse_schedule("jeden Tag."), {"type": "interval", "value": 1, "unit": "days"})
        self.assertEqual(parse_schedule("montag")["type"], "weekday")
        for text in ("ofen", "one", "oben", "bohne", "blumen"):
            with self.subTest(text=text):
                self.assertIsNone(parse_schedule(text))


class NoScheduleChoreCreationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(os.path.join(self.tmp.name, "chores.db"))
        handle_command(self.storage, "deutsch", SENDER, SCOPE, "test-group")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _send(self, text: str) -> str:
        reply = handle_command(self.storage, text, SENDER, SCOPE, "test-group")
        if isinstance(reply, list):
            return "\n".join(reply)
        if isinstance(reply, dict):
            return str(reply.get("reply", ""))
        return str(reply)

    def test_quick_add_with_variants_creates_open_task_with_clean_name(self) -> None:
        for name, suffix in (
            ("Fenster putzen", "ohne"), ("Keller", "ohne termin"), ("Paket", "ohen zeitplan"),
            ("Brief", "kein termin."), ("Herd und Ofen", "ohne zeitplan"),
        ):
            with self.subTest(suffix=suffix):
                reply = self._send(f"aufgabe {name} {suffix}")
                self.assertIn(f"Offene Aufgabe angelegt: {name}.", reply)

    def test_guided_setup_accepts_typo(self) -> None:
        self._send("aufgabe")
        self._send("Staubwischen")
        self.assertIn("Offene Aufgabe angelegt: Staubwischen.", self._send("ohen"))

    def test_not_understood_detection(self) -> None:
        self._send("aufgabe")
        self._send("Staubwischen")
        self.assertTrue(is_not_understood_reply(self._send("irgendwann mal")))
        self.assertTrue(is_not_understood_reply(self._send("listee")))
        self.assertFalse(is_not_understood_reply(self._send("liste")))
        self.assertFalse(is_not_understood_reply(""))


if __name__ == "__main__":
    unittest.main()
