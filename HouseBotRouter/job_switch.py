"""Switching a chat to another bot (spec 001 FR13).

Flow: an admin writes "admin switch bot" / "admin bot wechseln"; the router lists the other
bots; the admin names one; the router asks yes/no; on yes the chat's job changes. The old
bot keeps its data for the chat but gets no more messages, so switching back finds it again.
Only the sender who started a switch can answer it, and an unanswered switch expires.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

SWITCH_TTL_MINUTES = 10

_START_RE = re.compile(
    r"^admin\s+(?:switch\s+bot|bot\s+switch|change\s+bot|bot\s+wechseln|bot\s+wechsel|wechsel\s+bot)[.!]?$",
    re.IGNORECASE,
)
_YES = {"yes", "y", "ja", "j", "ok", "okay"}
_NO = {"no", "n", "nein", "cancel", "abbrechen", "stop"}

JOB_NAMES = {
    "en": {"chores": "the chore bot", "rentals": "the rental watcher", "expenses": "expense splitting"},
    "de": {"chores": "Haushalts-Bot", "rentals": "Ferienunterkunft-Beobachtung", "expenses": "Kosten teilen"},
}
JOB_WORDS = {
    "en": {"chores": "chores – household tasks and cleaning schedule", "rentals": "rentals – watch holiday rentals"},
    "de": {"chores": "haushalt – Aufgaben und Putzplan", "rentals": "ferien – Ferienunterkünfte beobachten"},
}

TEXT = {
    "en": {
        "pick": "🔄 Which bot should this chat use instead of {old}? Reply with one word:\n{options}\nOr: cancel",
        "nothing_else": "There is no other bot to switch to.",
        "confirm": (
            "Switch this chat from {old} to {new}?\n"
            "The data of {old} is kept, but it will no longer answer here. You can switch back later.\n"
            "Reply: yes or no"
        ),
        "not_admin": "Only admins of this group can switch the bot.",
        "cancelled": "↩️ Cancelled. This chat keeps {old}.",
        "done": "✅ This chat now uses {new}.",
    },
    "de": {
        "pick": "🔄 Welcher Bot soll hier statt {old} laufen? Antworte mit einem Wort:\n{options}\nOder: abbrechen",
        "nothing_else": "Es gibt keinen anderen Bot, zu dem gewechselt werden kann.",
        "confirm": (
            "Diesen Chat von {old} auf {new} umstellen?\n"
            "Die Daten von {old} bleiben erhalten, aber der Bot antwortet hier nicht mehr. "
            "Zurückwechseln geht jederzeit.\n"
            "Antworte: ja oder nein"
        ),
        "not_admin": "Den Bot wechseln können nur Admins dieser Gruppe.",
        "cancelled": "↩️ Abgebrochen. Dieser Chat bleibt bei {old}.",
        "done": "✅ Dieser Chat nutzt jetzt {new}.",
    },
}


def is_start(text: str) -> bool:
    return _START_RE.match(text.strip()) is not None


def start_language(text: str) -> str:
    return "de" if re.search(r"wechs", text, re.IGNORECASE) else "en"


def answer(text: str) -> bool | None:
    word = text.strip().lower().rstrip(".!")
    if word in _YES:
        return True
    if word in _NO:
        return False
    return None


def _lang(language: str | None) -> str:
    return language if language in TEXT else "en"


def text(language: str | None, key: str, **kwargs: object) -> str:
    return TEXT[_lang(language)][key].format(**kwargs)


def job_name(language: str | None, job: str) -> str:
    return JOB_NAMES[_lang(language)].get(job, job)


def pick_text(language: str | None, old_job: str, options: list[str]) -> str:
    lang = _lang(language)
    lines = "\n".join(f"- {JOB_WORDS[lang][job]}" for job in options)
    return text(lang, "pick", old=job_name(lang, old_job), options=lines)


class SwitchStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_switches (
                    scope_id TEXT PRIMARY KEY,
                    sender TEXT NOT NULL,
                    old_job TEXT NOT NULL,
                    new_job TEXT,
                    language TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def start(self, scope_id: str, sender: str, old_job: str, language: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO job_switches (scope_id, sender, old_job, new_job, language, expires_at)
                VALUES (?, ?, ?, NULL, ?, datetime('now', ?))
                """,
                (scope_id, sender, old_job, language, f"+{SWITCH_TTL_MINUTES} minutes"),
            )

    def get(self, scope_id: str, sender: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            conn.execute("DELETE FROM job_switches WHERE expires_at <= datetime('now')")
            return conn.execute(
                "SELECT * FROM job_switches WHERE scope_id = ? AND sender = ?",
                (scope_id, sender),
            ).fetchone()

    def choose(self, scope_id: str, new_job: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE job_switches SET new_job = ? WHERE scope_id = ?", (new_job, scope_id))

    def clear(self, scope_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM job_switches WHERE scope_id = ?", (scope_id,))
