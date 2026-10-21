"""Numbered tutorial pages: "anleitung" shows the topics, "anleitung 3" one topic.

Stateless on purpose: navigation words like "weiter" already mean "continue"
for unfinished dialogues, so every page names the next command explicitly.
"""

from __future__ import annotations

import re

_COMMAND_RE = re.compile(r"^(?:anleitung|tutorial|guide)(?:\s+(\d{1,2}))?$")

NAV = {
    "en": {
        "next": "➡️ Next: tutorial {next} · Overview: tutorial",
        "last": "🎉 That's it! Overview: tutorial · All commands: help",
    },
    "de": {
        "next": "➡️ Weiter: anleitung {next} · Übersicht: anleitung",
        "last": "🎉 Das war's! Übersicht: anleitung · Alle Befehle: hilfe",
    },
}

MENU = {
    "en": ("🎓 Tutorial – pick a topic:", "Reply e.g. with: tutorial 1"),
    "de": ("🎓 Anleitung – wähle ein Thema:", "Antworte z.B. mit: anleitung 1"),
}

TOPICS = {
    "en": [
        (
            "Getting started",
            "The bot keeps track of this group's chores and reminds you when something is due.\n\n"
            "1. Tell the bot your name:\n"
            "   name Anna\n"
            "2. Look at the chores:\n"
            "   list  (with details: list extend)\n"
            "3. All commands at a glance:\n"
            "   help\n\n"
            "💡 Commands are plain messages in the group – no special app or menu.",
        ),
        (
            "Adding chores",
            "Step by step – the bot asks for everything:\n"
            "   You: add\n"
            "   Bot: What is the chore called?\n"
            "   You: clean bathroom\n"
            "   Bot: How often is 'clean bathroom' due?\n"
            "   You: every week\n"
            "   Bot: At what time should the bot remind you…?\n"
            "   You: 18:00\n"
            "   Bot: Does 'clean bathroom' have to be marked as done?\n"
            "   You: yes\n\n"
            "Or all in one message:\n"
            "   add bins every Wednesday\n\n"
            "Schedules: every day · every 2 weeks · every Wednesday · every month",
        ),
        (
            "Marking done and undoing",
            "When you have done something:\n"
            "   done bins\n"
            "Mark it done for someone else (that person needs a name):\n"
            "   done bins for Max\n"
            "Marked by mistake?\n"
            "   undo done bins\n"
            "Who did what recently?\n"
            "   history\n\n"
            "💡 After marking a chore as done, its schedule starts again from now – "
            "with 'every Wednesday' the next Wednesday is due.",
        ),
        (
            "How reminders work",
            "• When a chore is due, the bot writes to the group at its reminder time (default 08:00).\n"
            "• If the chore has to be marked as done, the bot reminds you again while it is overdue – "
            "until someone sends done.\n"
            "• During quiet hours (default 00:00-08:00) no reminders are sent.\n\n"
            "Adjust it:\n"
            "   reminder time bins 19:00\n"
            "   reminder bins 2 hours  (gap between repeated reminders)\n"
            "   confirmation bins off  (remind only once)",
        ),
        (
            "Open and one-time chores",
            "An open task without a due date (e.g. shopping):\n"
            "   todo buy vacuum bags\n"
            "   → mark it done with: done buy vacuum bags\n\n"
            "A one-time chore with a date:\n"
            "   You: once\n"
            "   Bot: What is the chore called?\n"
            "   You: pick up parcel\n"
            "   Bot: When should the one-time chore … be done?\n"
            "   You: tomorrow\n"
            "   … then the time, whether it counts in stats, and the confirmation.\n"
            "Short version: once IKEA Friday\n\n"
            "💡 One-time chores disappear from the list once they are done.",
        ),
        (
            "Changing and deleting chores",
            "   You: edit bins\n"
            "   Bot: What do you want to change for 'bins'? (name, schedule, reminder time, …, delete)\n"
            "   You: schedule\n"
            "   Bot: How often is 'bins' due?\n"
            "   You: every 2 weeks\n\n"
            "Directly:\n"
            "   rename bins -> recycling\n"
            "   delete recycling\n\n"
            "💡 You can cancel any question with: cancel",
        ),
        (
            "Vacation",
            "Going away? Tell the bot – while a vacation is active, this group gets no chore reminders.\n"
            "   vacation 14 days  (starting now)\n"
            "   vacation in 3 days for 14 days  (plan ahead)\n\n"
            "Something to do before leaving? Add tasks for it:\n"
            "   vacation add empty fridge\n"
            "When the vacation starts, the bot lists them; check them off with:\n"
            "   vacation done empty fridge\n\n"
            "Status and cancelling: vacation status · vacation cancel",
        ),
        (
            "Statistics",
            "   my stats  – what you have done\n"
            "   group stats  – who did how much\n"
            "   group stats chore bins  – one chore only\n"
            "   group stats all  – all charts in one image\n"
            "   my stats chart  – your numbers as a chart",
        ),
        (
            "Admins and moving the group",
            "Whoever chose the language during setup is admin. Admin commands start with admin:\n"
            "   admin help\n"
            "   admin language de\n"
            "   admin quiet hours 23:00-07:00\n\n"
            "Moving to WhatsApp (or back to Signal):\n"
            "1. An admin writes here: move whatsapp  (or: move signal)\n"
            "2. Create the new group, add the bot and send the code there: move <code>\n"
            "3. Everyone writes once in the new group: i am <name>\n"
            "Chores, history and stats all move along.",
        ),
    ],
    "de": [
        (
            "Erste Schritte",
            "Der Bot verwaltet die Aufgaben dieser Gruppe und erinnert, wenn etwas fällig ist.\n\n"
            "1. Sag dem Bot, wie du heißt:\n"
            "   name Anna\n"
            "2. Schau dir die Aufgaben an:\n"
            "   liste  (mit Details: liste erweitert)\n"
            "3. Alle Befehle auf einen Blick:\n"
            "   hilfe\n\n"
            "💡 Befehle schreibst du einfach als normale Nachricht in die Gruppe.",
        ),
        (
            "Aufgaben anlegen",
            "Schritt für Schritt – der Bot fragt alles ab:\n"
            "   Du: aufgabe\n"
            "   Bot: Wie heißt die Aufgabe?\n"
            "   Du: Bad putzen\n"
            "   Bot: Wie oft ist 'Bad putzen' fällig?\n"
            "   Du: jede Woche\n"
            "   Bot: Um wie viel Uhr soll der Bot erinnern …?\n"
            "   Du: 18:00\n"
            "   Bot: Muss 'Bad putzen' als erledigt abgehakt werden?\n"
            "   Du: ja\n\n"
            "Oder alles in einer Nachricht:\n"
            "   aufgabe Müll jeden Mittwoch\n\n"
            "Zeitpläne: jeden Tag · alle 2 Wochen · jeden Mittwoch · jeden Monat",
        ),
        (
            "Abhaken und rückgängig machen",
            "Wenn du etwas erledigt hast:\n"
            "   erledigt Müll\n"
            "Für jemand anderen abhaken (die Person braucht einen Namen):\n"
            "   erledigt Müll für Max\n"
            "Versehentlich abgehakt?\n"
            "   rückgängig Müll\n"
            "Wer hat zuletzt was gemacht?\n"
            "   verlauf\n\n"
            "💡 Nach dem Abhaken zählt der Zeitplan ab jetzt neu – "
            "bei 'jeden Mittwoch' ist dann der nächste Mittwoch dran.",
        ),
        (
            "Wie Erinnerungen funktionieren",
            "• Ist eine Aufgabe fällig, schreibt der Bot zur Erinnerungszeit in die Gruppe (Standard: 08:00).\n"
            "• Muss die Aufgabe abgehakt werden, erinnert er erneut, solange sie überfällig ist – "
            "bis jemand erledigt schreibt.\n"
            "• In der Ruhezeit (Standard: 00:00-08:00) kommen keine Erinnerungen.\n\n"
            "Anpassen:\n"
            "   erinnerungszeit Müll 19:00\n"
            "   erinnerung Müll 2 Stunden  (Abstand der erneuten Erinnerung)\n"
            "   bestätigung Müll aus  (nur einmal erinnern)",
        ),
        (
            "Offene und einmalige Aufgaben",
            "Offene Aufgabe ohne Termin (z.B. Einkäufe):\n"
            "   todo Staubsaugerbeutel kaufen\n"
            "   → abhaken mit: erledigt Staubsaugerbeutel kaufen\n\n"
            "Einmalige Aufgabe mit Termin:\n"
            "   Du: einmal\n"
            "   Bot: Wie heißt die Aufgabe?\n"
            "   Du: Paket abholen\n"
            "   Bot: Wann soll die einmalige Aufgabe … erledigt werden?\n"
            "   Du: morgen\n"
            "   … danach Uhrzeit, Statistik ja/nein und Bestätigung.\n"
            "Kurz: einmal IKEA Freitag\n\n"
            "💡 Einmalige Aufgaben verschwinden nach dem Abhaken von der Liste.",
        ),
        (
            "Aufgaben ändern und löschen",
            "   Du: bearbeite Müll\n"
            "   Bot: Was möchtest du bei 'Müll' ändern? (name, zeitplan, erinnerungszeit, …, löschen)\n"
            "   Du: zeitplan\n"
            "   Bot: Wie oft ist 'Müll' fällig?\n"
            "   Du: alle 2 Wochen\n\n"
            "Direkt geht es auch:\n"
            "   umbenennen Müll -> Restmüll\n"
            "   lösche Restmüll\n\n"
            "💡 Jede Frage kannst du mit abbrechen beenden.",
        ),
        (
            "Urlaub",
            "Ihr verreist? Sag dem Bot Bescheid – solange ein Urlaub läuft, gibt es in dieser Gruppe "
            "keine Aufgaben-Erinnerungen.\n"
            "   urlaub 14 tage  (ab sofort)\n"
            "   urlaub in 3 tagen für 14 tage  (im Voraus)\n\n"
            "Vorher noch etwas erledigen? Leg Vorbereitungsaufgaben an:\n"
            "   urlaub aufgabe Kühlschrank leeren\n"
            "Zum Urlaubsbeginn listet der Bot sie auf; abhaken mit:\n"
            "   urlaub erledigt Kühlschrank leeren\n\n"
            "Status und Abbruch: urlaub status · urlaub abbrechen",
        ),
        (
            "Statistik",
            "   meine statistik  – was du erledigt hast\n"
            "   gruppen statistik  – wer wie viel gemacht hat\n"
            "   gruppen statistik aufgabe Müll  – nur eine Aufgabe\n"
            "   gruppen statistik alle  – alle Diagramme in einem Bild\n"
            "   meine statistik diagramm  – deine Zahlen als Diagramm",
        ),
        (
            "Admins und Gruppenumzug",
            "Wer beim Einrichten die Sprache gewählt hat, ist Admin. Admin-Befehle beginnen mit admin:\n"
            "   admin hilfe\n"
            "   admin sprache englisch\n"
            "   admin ruhezeit 23:00-07:00\n\n"
            "Umzug nach WhatsApp (oder zurück zu Signal):\n"
            "1. Ein Admin schreibt hier: umzug whatsapp  (bzw. umzug signal)\n"
            "2. Neue Gruppe erstellen, Bot hinzufügen und dort den Code senden: umzug <Code>\n"
            "3. Jede Person schreibt in der neuen Gruppe einmal: ich bin <Name>\n"
            "Aufgaben, Verlauf und Statistik ziehen komplett mit um.",
        ),
    ],
}


def parse_tutorial_command(command_lowered: str) -> int | None:
    """0 for the topic overview, n for topic n, None if this is not a tutorial command."""
    match = _COMMAND_RE.match(command_lowered.strip())
    if match is None:
        return None
    return int(match.group(1)) if match.group(1) else 0


def tutorial_text(language: str, topic: int) -> str:
    language = language if language in TOPICS else "en"
    topics = TOPICS[language]
    if not 1 <= topic <= len(topics):
        header, footer = MENU[language]
        lines = [f"{index}. {title}" for index, (title, _) in enumerate(topics, start=1)]
        return "\n".join([header, *lines, footer])
    title, body = topics[topic - 1]
    nav = NAV[language]
    footer = nav["next"].format(next=topic + 1) if topic < len(topics) else nav["last"]
    return f"🎓 {topic}/{len(topics)} · {title}\n\n{body}\n\n{footer}"
