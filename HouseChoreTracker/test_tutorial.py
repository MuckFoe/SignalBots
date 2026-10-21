import os
import tempfile
import unittest

from commands import handle_command
from storage import Storage
from tutorial import TOPICS, parse_tutorial_command, tutorial_text

BAD_REPLY_MARKERS = (
    "Meintest du", "Did you mean", "So geht's", "Usage:", "nicht gefunden", "was not found",
    "gibt es nicht", "verstehe ich nicht", "could not", "konnte nicht", "Bitte antworte",
    "Please reply", "Bitte wähle", "Please choose", "In Gruppen bitte admin", "In groups, put admin",
)

ANNA, MAX = "sender-anna", "sender-max"

# Every command the tutorial pages show, in the order a reader would try them.
GERMAN_WALKTHROUGH = [
    (ANNA, "name Anna"), (MAX, "name Max"), (ANNA, "liste"), (ANNA, "liste erweitert"), (ANNA, "hilfe"),
    (ANNA, "aufgabe"), (ANNA, "Bad putzen"), (ANNA, "jede Woche"), (ANNA, "18:00"), (ANNA, "ja"),
    (ANNA, "aufgabe Müll jeden Mittwoch"), (ANNA, "aufgabe Fenster jeden Monat"),
    (ANNA, "aufgabe Blumen gießen jeden Tag"), (ANNA, "aufgabe Kühlschrank alle 2 Wochen"),
    (ANNA, "erledigt Müll"), (ANNA, "erledigt Müll für Max"), (ANNA, "rückgängig Müll"), (ANNA, "verlauf"),
    (ANNA, "erinnerungszeit Müll 19:00"), (ANNA, "erinnerung Müll 2 Stunden"), (ANNA, "bestätigung Müll aus"),
    (ANNA, "todo Staubsaugerbeutel kaufen"), (ANNA, "erledigt Staubsaugerbeutel kaufen"),
    (ANNA, "einmal"), (ANNA, "Paket abholen"), (ANNA, "morgen"), (ANNA, "egal"), (ANNA, "ja"), (ANNA, "ja"),
    (ANNA, "einmal IKEA Freitag"), (ANNA, "egal"), (ANNA, "ja"), (ANNA, "ja"),
    (ANNA, "bearbeite Müll"), (ANNA, "zeitplan"), (ANNA, "alle 2 Wochen"),
    (ANNA, "umbenennen Müll -> Restmüll"), (ANNA, "lösche Restmüll"),
    (ANNA, "urlaub aufgabe Kühlschrank leeren"), (ANNA, "urlaub in 3 tagen für 14 tage"),
    (ANNA, "urlaub status"), (ANNA, "urlaub abbrechen"), (ANNA, "urlaub 14 tage"),
    (ANNA, "urlaub erledigt Kühlschrank leeren"), (ANNA, "urlaub abbrechen"),
    (ANNA, "meine statistik"), (ANNA, "gruppen statistik"), (ANNA, "gruppen statistik aufgabe Bad putzen"),
    (ANNA, "gruppen statistik alle"), (ANNA, "meine statistik diagramm"),
    (ANNA, "admin hilfe"), (ANNA, "admin ruhezeit 23:00-07:00"), (ANNA, "admin sprache englisch"),
]

ENGLISH_WALKTHROUGH = [
    (ANNA, "name Anna"), (MAX, "name Max"), (ANNA, "list"), (ANNA, "list extend"), (ANNA, "help"),
    (ANNA, "add"), (ANNA, "clean bathroom"), (ANNA, "every week"), (ANNA, "18:00"), (ANNA, "yes"),
    (ANNA, "add bins every Wednesday"), (ANNA, "add windows every month"),
    (ANNA, "add water plants every day"), (ANNA, "add fridge every 2 weeks"),
    (ANNA, "done bins"), (ANNA, "done bins for Max"), (ANNA, "undo done bins"), (ANNA, "history"),
    (ANNA, "reminder time bins 19:00"), (ANNA, "reminder bins 2 hours"), (ANNA, "confirmation bins off"),
    (ANNA, "todo buy vacuum bags"), (ANNA, "done buy vacuum bags"),
    (ANNA, "once"), (ANNA, "pick up parcel"), (ANNA, "tomorrow"), (ANNA, "anytime"), (ANNA, "yes"), (ANNA, "yes"),
    (ANNA, "once IKEA Friday"), (ANNA, "anytime"), (ANNA, "yes"), (ANNA, "yes"),
    (ANNA, "edit bins"), (ANNA, "schedule"), (ANNA, "every 2 weeks"),
    (ANNA, "rename bins -> recycling"), (ANNA, "delete recycling"),
    (ANNA, "vacation add empty fridge"), (ANNA, "vacation in 3 days for 14 days"),
    (ANNA, "vacation status"), (ANNA, "vacation cancel"), (ANNA, "vacation 14 days"),
    (ANNA, "vacation done empty fridge"), (ANNA, "vacation cancel"),
    (ANNA, "my stats"), (ANNA, "group stats"), (ANNA, "group stats chore clean bathroom"),
    (ANNA, "group stats all"), (ANNA, "my stats chart"),
    (ANNA, "admin help"), (ANNA, "admin quiet hours 23:00-07:00"), (ANNA, "admin language de"),
]


def _flat(reply) -> str:
    if isinstance(reply, dict):
        reply = reply.get("reply", "")
    if isinstance(reply, list):
        return "\n".join(_flat(item) for item in reply)
    return reply or ""


class TutorialPageTests(unittest.TestCase):
    def test_parse(self) -> None:
        self.assertEqual(parse_tutorial_command("anleitung"), 0)
        self.assertEqual(parse_tutorial_command("tutorial 3"), 3)
        self.assertEqual(parse_tutorial_command("anleitung  12"), 12)
        self.assertIsNone(parse_tutorial_command("anleitung bitte"))
        self.assertIsNone(parse_tutorial_command("liste"))

    def test_both_languages_have_the_same_topics(self) -> None:
        self.assertEqual(len(TOPICS["de"]), len(TOPICS["en"]))

    def test_menu_lists_every_topic_and_out_of_range_falls_back_to_it(self) -> None:
        for language in ("de", "en"):
            menu = tutorial_text(language, 0)
            for title, _ in TOPICS[language]:
                self.assertIn(title, menu)
            self.assertEqual(tutorial_text(language, 99), menu)

    def test_pages_link_to_the_next_one_and_the_last_one_ends(self) -> None:
        count = len(TOPICS["de"])
        for topic in range(1, count):
            self.assertIn(f"anleitung {topic + 1}", tutorial_text("de", topic))
            self.assertIn(f"tutorial {topic + 1}", tutorial_text("en", topic))
        self.assertIn("Das war's", tutorial_text("de", count))
        self.assertIn("That's it", tutorial_text("en", count))

    def test_pages_fit_a_phone_screen(self) -> None:
        for language in ("de", "en"):
            for topic in range(1, len(TOPICS[language]) + 1):
                self.assertLessEqual(tutorial_text(language, topic).count("\n"), 24, (language, topic))


class TutorialInChatTests(unittest.TestCase):
    def _group(self, language_command: str) -> tuple[Storage, str, str]:
        storage = Storage(os.path.join(tempfile.mkdtemp(), "c.db"))
        scope, group = "group:tutorial", "tutorial"
        handle_command(storage, language_command, ANNA, scope, group)
        return storage, scope, group

    def test_command_and_typo_in_a_german_group(self) -> None:
        storage, scope, group = self._group("deutsch")
        self.assertIn("Anleitung – wähle ein Thema", _flat(handle_command(storage, "anleitung", ANNA, scope, group)))
        self.assertIn("2/9 · Aufgaben anlegen", _flat(handle_command(storage, "Anleitung 2", ANNA, scope, group)))
        self.assertIn("anleitung", _flat(handle_command(storage, "anleitng", ANNA, scope, group)))
        self.assertIn("anleitung", _flat(handle_command(storage, "hilfe", ANNA, scope, group)))

    def test_setup_points_to_the_tutorial(self) -> None:
        storage = Storage(os.path.join(tempfile.mkdtemp(), "c.db"))
        self.assertIn("anleitung", _flat(handle_command(storage, "deutsch", ANNA, "group:x", "x")))

    def _walk(self, language_command: str, steps: list[tuple[str, str]]) -> None:
        storage, scope, group = self._group(language_command)
        for sender, message in steps:
            reply = _flat(handle_command(storage, message, sender, scope, group))
            with self.subTest(message=message):
                self.assertTrue(reply.strip(), f"no reply to {message!r}")
                for marker in BAD_REPLY_MARKERS:
                    self.assertNotIn(marker, reply, f"{message!r} -> {reply!r}")

    def test_every_german_example_works(self) -> None:
        self._walk("deutsch", GERMAN_WALKTHROUGH)

    def test_every_english_example_works(self) -> None:
        self._walk("english", ENGLISH_WALKTHROUGH)


if __name__ == "__main__":
    unittest.main()
