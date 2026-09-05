from __future__ import annotations

import os
import tempfile
import unittest

from commands import TEXT, handle_command
from storage import Storage


def _text(result: object) -> str:
    if isinstance(result, list):
        return "\n".join(str(part) for part in result)
    if isinstance(result, dict):
        return str(result.get("reply", ""))
    return str(result)


class CommandSurfaceTests(unittest.TestCase):
    def test_en_de_text_keys_match(self) -> None:
        self.assertEqual(set(TEXT["en"]), set(TEXT["de"]))

    def test_help_is_not_redundant(self) -> None:
        en_help = TEXT["en"]["help"]
        de_help = TEXT["de"]["help"]
        self.assertIn("chore help", en_help)
        self.assertIn("edit help", en_help)
        self.assertNotIn("confirmation <", en_help)
        self.assertNotIn("reminder time <", en_help)
        self.assertNotIn("schedule <", en_help)
        self.assertIn("aufgabe hilfe", de_help)
        self.assertIn("erledigt", de_help)
        self.assertIn("liste", de_help)
        self.assertNotIn("fälligkeit <", de_help)
        self.assertNotIn("erinnerungszeit <", de_help)
        self.assertNotIn("- add ", de_help)
        self.assertNotIn("done <", de_help)
        self.assertNotIn("overdue reminder", TEXT["en"]["chore_help"])
        self.assertNotIn("Wiederholung bei Überfälligkeit", TEXT["de"]["chore_help"])

    def test_dialogs_offer_cancel(self) -> None:
        for language in ("en", "de"):
            cancel = "cancel" if language == "en" else "abbrechen"
            for key in (
            "setup_chore_name",
                "setup_chore_schedule",
                "setup_chore_remind_time",
                "setup_chore_confirmation",
                "setup_once_schedule",
                "setup_once_remind_time",
                "setup_once_count_stats",
                "edit_options",
                "ask_display_name",
                "vacation_setup_when",
                "vacation_setup_duration",
            ):
                self.assertIn(cancel, TEXT[language][key].lower(), msg=f"{language}:{key}")

    def test_big_picture_german_group_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(os.path.join(tmp, "chores.db"))
            group_id = "g1"
            scope = f"group:{group_id}"
            anna = "sender-anna"
            max_user = "sender-max"

            setup = _text(handle_command(storage, "sprache deutsch", anna, scope, group_id))
            self.assertIn("Setup fertig", setup)
            self.assertIn("liste", setup)
            self.assertIn("aufgabe", setup.lower())

            help_text = _text(handle_command(storage, "hilfe", anna, scope, group_id))
            self.assertIn("liste", help_text)
            self.assertIn("erledigt", help_text)
            self.assertNotIn("confirmation <", help_text)

            name_reply = _text(handle_command(storage, "name Anna", anna, scope, group_id))
            self.assertIn("Anna", name_reply)
            max_name = _text(handle_command(storage, "name Max", max_user, scope, group_id))
            self.assertIn("Max", max_name)

            started = _text(handle_command(storage, "aufgabe", anna, scope, group_id))
            self.assertIn("Wie heißt die Aufgabe", started)
            asked_schedule = _text(handle_command(storage, "Biokiste rausstellen", anna, scope, group_id))
            self.assertIn("Biokiste rausstellen", asked_schedule)
            asked_time = _text(handle_command(storage, "Mittwoch", anna, scope, group_id))
            self.assertIn("Uhrzeit", asked_time)
            asked_confirm = _text(handle_command(storage, "19:45", anna, scope, group_id))
            self.assertIn("bestätigt", asked_confirm)
            added = _text(handle_command(storage, "ja", anna, scope, group_id))
            self.assertIn("Biokiste rausstellen", added)

            cancelled_start = _text(handle_command(storage, "aufgabe", anna, scope, group_id))
            self.assertIn("Wie heißt", cancelled_start)
            cancelled = _text(handle_command(storage, "abbrechen", anna, scope, group_id))
            self.assertIn("Abgebrochen", cancelled)

            open_task = _text(handle_command(storage, "todo Milch kaufen", anna, scope, group_id))
            self.assertIn("Milch kaufen", open_task)
            self.assertIn("Kein Plan", open_task)

            quick = _text(handle_command(storage, "aufgabe Bad 1 Stunde", anna, scope, group_id))
            self.assertIn("Bad", quick)

            listing = _text(handle_command(storage, "liste", anna, scope, group_id))
            self.assertIn("Biokiste rausstellen", listing)
            self.assertIn("Milch kaufen", listing)
            self.assertIn("Bad", listing)
            self.assertIn("liste erweitert", listing)

            details = _text(handle_command(storage, "liste erweitert", anna, scope, group_id))
            self.assertIn("Erinnerungszeit", details)
            self.assertIn("19:45", details)

            done_self = _text(handle_command(storage, "erledigt Milch kaufen", anna, scope, group_id))
            self.assertIn("Erledigt", done_self)
            undo = _text(handle_command(storage, "rückgängig Milch kaufen", anna, scope, group_id))
            self.assertIn("rückgängig", undo.lower())
            done_for = _text(handle_command(storage, "erledigt Milch kaufen von Max", anna, scope, group_id))
            self.assertIn("Max", done_for)

            # also credit via für / for
            self.assertTrue(storage.add_chore(scope, "Glas", {"type": "none"}))
            done_fuer = _text(handle_command(storage, "erledigt Glas für Max", anna, scope, group_id))
            self.assertIn("Max", done_fuer)

            edit = _text(handle_command(storage, "bearbeite Bad", anna, scope, group_id))
            self.assertIn("Fälligkeit", edit)
            self.assertIn("abbrechen", edit)
            time_prompt = _text(handle_command(storage, "Erinnerungszeit", anna, scope, group_id))
            self.assertIn("Uhrzeit", time_prompt)
            time_set = _text(handle_command(storage, "08:00", anna, scope, group_id))
            self.assertIn("08:00", time_set)

            stats = _text(handle_command(storage, "meine statistik", anna, scope, group_id))
            self.assertTrue("Statistik" in stats or "Erledigungen" in stats or "noch keine" in stats.lower())
            group_stats = _text(handle_command(storage, "gruppen statistik", anna, scope, group_id))
            self.assertIn("Gruppen", group_stats)

            vac = _text(handle_command(storage, "urlaub 2 tage", anna, scope, group_id))
            self.assertIn("Urlaub", vac)
            status = _text(handle_command(storage, "urlaub status", anna, scope, group_id))
            self.assertIn("Urlaub", status)
            prep = _text(handle_command(storage, "urlaub aufgabe Kühlschrank leeren", anna, scope, group_id))
            self.assertIn("Kühlschrank leeren", prep)
            cancel_vac = _text(handle_command(storage, "urlaub abbrechen", anna, scope, group_id))
            self.assertIn("abgebrochen", cancel_vac.lower())

            tz = _text(handle_command(storage, "admin zeitzone berlin", anna, scope, group_id))
            self.assertIn("Europe/Berlin", tz)
            quiet = _text(handle_command(storage, "admin ruhezeit 00:00-08:00", anna, scope, group_id))
            self.assertIn("00:00", quiet)
            self.assertIn("08:00", quiet)

            unknown = _text(handle_command(storage, "blubbxyz", anna, scope, group_id))
            self.assertEqual(unknown, "")
            chat = _text(handle_command(storage, "Wie spät kommt ihr heute?", anna, scope, group_id))
            self.assertEqual(chat, "")
            typo = _text(handle_command(storage, "listee", anna, scope, group_id))
            self.assertIn("liste", typo.lower())
            self.assertIn("Meintest du", typo)

            missing = _text(handle_command(storage, "erledigt gibt es nicht", anna, scope, group_id))
            self.assertIn("nicht gefunden", missing.lower())


if __name__ == "__main__":
    unittest.main()
