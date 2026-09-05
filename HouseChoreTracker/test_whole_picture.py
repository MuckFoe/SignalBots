from __future__ import annotations

import os
import re
import tempfile
import unittest
from unittest.mock import patch

from commands import TEXT, handle_command
from schedule_utils import ONE_SHOT_STATS_KEY
from storage import Storage


def _text(result: object) -> str:
    if isinstance(result, list):
        return "\n".join(str(part) for part in result)
    if isinstance(result, dict):
        return str(result.get("reply", ""))
    return str(result)


def _listed_names(listing: str) -> list[str]:
    names: list[str] = []
    for line in listing.splitlines():
        match = re.match(r"^\d+\. (.+)$", line)
        if not match:
            continue
        body = match.group(1)
        names.append(body.split(" (", 1)[0])
    return names


class WholePictureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(os.path.join(self.tmp.name, "chores.db"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _setup_group(self, command: str, group_id: str, sender: str, expected: str) -> str:
        scope = f"group:{group_id}"
        with patch.dict(
            os.environ,
            {"BOT_REGISTRY": "", "BOT_INSTANCE_ID": "default", "BOT_INSTANCE_NAME": "House Chore Bot"},
        ):
            reply = _text(handle_command(self.storage, command, sender, scope, group_id))
        self.assertIn(expected, reply)
        self.assertTrue(self.storage.is_group_ready(scope))
        return scope

    def test_user_facing_copy_stays_small(self) -> None:
        for language in ("en", "de"):
            did_you_mean = TEXT[language]["did_you_mean"]
            self.assertEqual(did_you_mean.count("\n"), 0, msg=f"{language}:did_you_mean")
            self.assertIn("{command}", did_you_mean)
            self.assertLess(len(did_you_mean), 40)
            self.assertLess(len(TEXT[language]["help"]), 700)
            self.assertLess(len(TEXT[language]["chore_help"]), 550)
            self.assertLessEqual(TEXT[language]["help"].count("\n"), 22)
            self.assertLessEqual(TEXT[language]["chore_help"].count("\n"), 10)
            self.assertNotIn(TEXT[language]["help"], did_you_mean)
            self.assertNotIn("confirmation <", TEXT[language]["help"])
            self.assertNotIn("fälligkeit <", TEXT[language]["help"].lower())

    def _finish_once(
        self,
        scope: str,
        group_id: str,
        sender: str,
        command: str,
        count_stats: bool = True,
        language: str = "de",
    ) -> str:
        first = _text(handle_command(self.storage, command, sender, scope, group_id))
        # Interview may ask time, then stats, then confirmation.
        replies = [first]
        current = first.lower()
        if "uhrzeit" in current or "what time" in current or "at what time" in current:
            replies.append(_text(handle_command(self.storage, "19:45", sender, scope, group_id)))
            current = replies[-1].lower()
        if "statistik" in current or "count in stats" in current or "stats" in current:
            stats_answer = "ja" if language == "de" else "yes"
            if not count_stats:
                stats_answer = "nein" if language == "de" else "no"
            replies.append(_text(handle_command(self.storage, stats_answer, sender, scope, group_id)))
            current = replies[-1].lower()
        if "bestätigt" in current or "confirmation" in current:
            conf = "ja" if language == "de" else "yes"
            replies.append(_text(handle_command(self.storage, conf, sender, scope, group_id)))
        return replies[-1]

    def test_german_group_commands_work_together(self) -> None:
        group_id = "wg-kitchen"
        anna = "sender-anna"
        max_user = "sender-max"
        scope = self._setup_group("sprache deutsch", group_id, anna, "Setup fertig")

        self.assertIn("Anna", _text(handle_command(self.storage, "name Anna", anna, scope, group_id)))
        self.assertIn("Max", _text(handle_command(self.storage, "name Max", max_user, scope, group_id)))

        recurring = _text(handle_command(self.storage, "aufgabe Müll Mittwoch", anna, scope, group_id))
        self.assertIn("Müll", recurring)
        self.assertNotIn("Einmalaufgabe", recurring)

        todo = _text(handle_command(self.storage, "todo Milch kaufen", anna, scope, group_id))
        self.assertIn("Milch kaufen", todo)
        self.assertIn("Kein Plan", todo)

        once = self._finish_once(scope, group_id, anna, "einmal Paket Freitag 19:45")
        self.assertIn("Paket", once)
        self.assertIn("Einmalaufgabe", once)

        rows = {row["name"]: row for row in self.storage.list_chores(scope)}
        self.assertEqual(rows["Müll"]["reminder_schedule"], "weekday:2")
        self.assertEqual(int(rows["Müll"]["one_shot"] or 0), 0)
        self.assertEqual(rows["Milch kaufen"]["reminder_schedule"], "none")
        self.assertEqual(int(rows["Milch kaufen"]["one_shot"] or 0), 0)
        self.assertEqual(rows["Paket"]["reminder_schedule"], "once:weekday:4")
        self.assertEqual(int(rows["Paket"]["one_shot"] or 0), 1)

        listing = _text(handle_command(self.storage, "liste", anna, scope, group_id))
        details = _text(handle_command(self.storage, "liste erweitert", anna, scope, group_id))
        short_names = _listed_names(listing)
        detail_names = _listed_names(details)
        self.assertEqual(short_names, ["Milch kaufen", "Müll", "Paket"])
        self.assertEqual(short_names, detail_names)
        self.assertIn("offen", listing.lower())
        self.assertIn("mittwoch", listing.lower())
        self.assertIn("einmal", listing.lower())
        self.assertIn("liste erweitert", listing)
        self.assertIn("Erinnerungszeit", details)
        self.assertIn("19:45", details)
        self.assertIn("offene Aufgabe", details)
        self.assertIn("kein plan", details.lower())

        done_recurring = _text(handle_command(self.storage, "erledigt Müll", anna, scope, group_id))
        self.assertIn("Müll", done_recurring)
        self.assertIn("Anna", done_recurring)
        self.assertNotIn("entfernt", done_recurring.lower())

        after_recurring = _text(handle_command(self.storage, "liste", anna, scope, group_id))
        self.assertIn("Müll", after_recurring)
        self.assertIn("Milch kaufen", after_recurring)
        self.assertIn("Paket", after_recurring)

        done_once = _text(handle_command(self.storage, "erledigt Paket", anna, scope, group_id))
        self.assertIn("Paket", done_once)
        self.assertIn("entfernt", done_once.lower())
        self.assertIn("Einmalaufgaben", done_once)
        self.assertNotIn("rückgängig", done_once.lower())

        after_once = _text(handle_command(self.storage, "liste", anna, scope, group_id))
        after_once_details = _text(handle_command(self.storage, "liste erweitert", anna, scope, group_id))
        self.assertEqual(_listed_names(after_once), ["Milch kaufen", "Müll"])
        self.assertEqual(_listed_names(after_once), _listed_names(after_once_details))
        self.assertNotIn("Paket", after_once)
        self.assertNotIn("Paket", after_once_details)
        self.assertIn("Milch kaufen", after_once)
        self.assertIn("offen", after_once.lower())

        done_for = _text(handle_command(self.storage, "erledigt Milch kaufen von Max", anna, scope, group_id))
        self.assertIn("Max", done_for)
        self.assertIn("Milch kaufen", done_for)
        self.assertNotIn("entfernt", done_for.lower())
        self.assertNotIn("Einmalaufgaben", done_for)

        after_todo = _text(handle_command(self.storage, "liste", anna, scope, group_id))
        self.assertIn("Milch kaufen", after_todo)
        self.assertIn("Müll", after_todo)
        self.assertNotIn("Paket", after_todo)

        alias_list = _text(handle_command(self.storage, "list", anna, scope, group_id))
        self.assertEqual(_listed_names(alias_list), ["Milch kaufen", "Müll"])
        alias_done = _text(handle_command(self.storage, "done Müll", max_user, scope, group_id))
        self.assertIn("Müll", alias_done)
        self.assertIn("Max", alias_done)

        user_stats = _text(handle_command(self.storage, "meine statistik", anna, scope, group_id))
        self.assertIn("Statistik", user_stats)
        self.assertIn("Müll", user_stats)
        self.assertIn("Einmalaufgaben", user_stats)
        self.assertNotIn("Paket", user_stats)
        self.assertNotIn("Milch kaufen", user_stats)

        group_stats = _text(handle_command(self.storage, "gruppen statistik", anna, scope, group_id))
        self.assertIn("Gruppen", group_stats)
        self.assertIn("Müll", group_stats)
        self.assertIn("Milch kaufen", group_stats)
        self.assertIn("Einmalaufgaben", group_stats)
        self.assertNotIn("Paket", group_stats)
        self.assertIn("Anna", group_stats)
        self.assertIn("Max", group_stats)

        buckets = {row["name"]: row for row in self.storage.task_stats(scope)}
        self.assertIn(ONE_SHOT_STATS_KEY, buckets)
        self.assertEqual(buckets[ONE_SHOT_STATS_KEY]["completions"], 1)
        self.assertNotIn("Paket", buckets)
        self.assertEqual(buckets["Müll"]["completions"], 2)
        self.assertEqual(buckets["Milch kaufen"]["completions"], 1)

        typo = _text(handle_command(self.storage, "listee", anna, scope, group_id))
        self.assertIn("Meintest du", typo)
        self.assertIn("liste", typo.lower())
        self.assertEqual(typo.count("\n"), 0)
        self.assertLess(len(typo), 60)
        self.assertNotIn(TEXT["de"]["help"], typo)
        self.assertNotIn("Haushalts-Bot", typo)
        self.assertNotIn("erledigt <Name>", typo)

        chat = _text(handle_command(self.storage, "Wie spät kommt ihr?", anna, scope, group_id))
        self.assertEqual(chat, "")
        self.assertEqual(_text(handle_command(self.storage, "blubbxyz", anna, scope, group_id)), "")

        vacation = _text(handle_command(self.storage, "urlaub 2 tage", anna, scope, group_id))
        self.assertIn("Urlaub", vacation)
        status = _text(handle_command(self.storage, "urlaub status", anna, scope, group_id))
        self.assertIn("Urlaub", status)
        cancel = _text(handle_command(self.storage, "urlaub abbrechen", anna, scope, group_id))
        self.assertIn("abgebrochen", cancel.lower())
        still_listed = _text(handle_command(self.storage, "liste", anna, scope, group_id))
        self.assertIn("Müll", still_listed)
        self.assertIn("Milch kaufen", still_listed)

        extra_once = self._finish_once(scope, group_id, anna, "once Fenster heute")
        self.assertIn("Fenster", extra_once)
        self.assertIn("Einmalaufgabe", extra_once)
        extra_done = _text(handle_command(self.storage, "erledigt Fenster", anna, scope, group_id))
        self.assertIn("entfernt", extra_done.lower())
        later_stats = _text(handle_command(self.storage, "gruppen statistik", anna, scope, group_id))
        self.assertIn("Einmalaufgaben", later_stats)
        self.assertNotIn("Fenster", later_stats)
        self.assertNotIn("Paket", later_stats)

    def test_english_aliases_and_chat_ignore(self) -> None:
        group_id = "flat-en"
        alice = "sender-alice"
        bob = "sender-bob"
        scope = self._setup_group("language en", group_id, alice, "Setup complete")
        self.assertIn("Alice", _text(handle_command(self.storage, "name Alice", alice, scope, group_id)))
        self.assertIn("Bob", _text(handle_command(self.storage, "name Bob", bob, scope, group_id)))

        self.assertIn("bins", _text(handle_command(self.storage, "add bins Wednesday", alice, scope, group_id)))
        self.assertIn("open task", _text(handle_command(self.storage, "todo buy milk", alice, scope, group_id)).lower())
        once = self._finish_once(scope, group_id, alice, "once library Saturday", language="en")
        self.assertIn("one-time", once.lower())
        self.assertIn("library", once.lower())

        listing = _text(handle_command(self.storage, "list", alice, scope, group_id))
        details = _text(handle_command(self.storage, "list extend", alice, scope, group_id))
        self.assertEqual(_listed_names(listing), _listed_names(details))
        self.assertIn("bins", listing)
        self.assertIn("buy milk", listing)
        self.assertIn("library", listing)
        de_list = _text(handle_command(self.storage, "liste", alice, scope, group_id))
        self.assertEqual(_listed_names(listing), _listed_names(de_list))

        done_by = _text(handle_command(self.storage, "done buy milk by Bob", alice, scope, group_id))
        self.assertIn("Bob", done_by)
        german_done = _text(handle_command(self.storage, "erledigt bins", alice, scope, group_id))
        self.assertIn("bins", german_done)
        self.assertIn("Alice", german_done)

        once_done = _text(handle_command(self.storage, "done library", alice, scope, group_id))
        self.assertIn("removed", once_done.lower())
        self.assertIn("one-time chores", once_done.lower())

        after = _text(handle_command(self.storage, "list", alice, scope, group_id))
        self.assertIn("bins", after)
        self.assertIn("buy milk", after)
        self.assertNotIn("library", after)

        stats = _text(handle_command(self.storage, "group stats", alice, scope, group_id))
        self.assertIn("one-time chores", stats)
        self.assertNotIn("library", stats)
        self.assertIn("bins", stats)
        self.assertIn("buy milk", stats)
        my_stats = _text(handle_command(self.storage, "my stats", alice, scope, group_id))
        self.assertIn("one-time chores", my_stats)
        self.assertNotIn("library", my_stats)

        typo = _text(handle_command(self.storage, "listt", alice, scope, group_id))
        self.assertIn("Did you mean", typo)
        self.assertIn("list", typo)
        self.assertEqual(typo.count("\n"), 0)
        self.assertLess(len(typo), 60)
        self.assertNotIn(TEXT["en"]["help"], typo)
        self.assertNotIn("House Chore Bot", typo)

        pizza = _text(
            handle_command(
                self.storage,
                "Shall we get pizza later tonight with everyone?",
                alice,
                scope,
                group_id,
            )
        )
        self.assertEqual(pizza, "")

        vacation = _text(handle_command(self.storage, "vacation 2 days", alice, scope, group_id))
        self.assertIn("Vacation", vacation)
        cancel = _text(handle_command(self.storage, "vacation cancel", alice, scope, group_id))
        self.assertIn("cancelled", cancel.lower())


if __name__ == "__main__":
    unittest.main()
