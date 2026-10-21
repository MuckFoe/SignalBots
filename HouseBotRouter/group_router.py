from __future__ import annotations



import re

import sqlite3

from pathlib import Path

from typing import Any, Literal



import requests



Job = Literal["chores", "rentals", "expenses"]





class GroupRouter:

    def __init__(

        self,

        db_path: str,

        chore_bot_url: str,

        rental_bot_url: str,

        expense_bot_url: str,

    ) -> None:

        self.db_path = db_path

        self.bot_urls = {

            "chores": chore_bot_url.rstrip("/"),

            "rentals": rental_bot_url.rstrip("/"),

            "expenses": expense_bot_url.rstrip("/"),

        }

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_db()



    def _connect(self) -> sqlite3.Connection:

        conn = sqlite3.connect(self.db_path)

        conn.row_factory = sqlite3.Row

        return conn



    def _init_db(self) -> None:

        with self._connect() as conn:

            conn.execute(

                """

                CREATE TABLE IF NOT EXISTS group_jobs (

                    scope_id TEXT PRIMARY KEY,

                    job TEXT NOT NULL,

                    created_at TEXT NOT NULL DEFAULT (datetime('now'))

                )

                """

            )

            conn.commit()



    def get_job(self, scope_id: str) -> str | None:

        with self._connect() as conn:

            row = conn.execute(

                "SELECT job FROM group_jobs WHERE scope_id = ?",

                (scope_id,),

            ).fetchone()

        if row is None:

            return None

        return row["job"]



    def set_job(self, scope_id: str, job: Job) -> None:

        with self._connect() as conn:

            conn.execute(

                """

                INSERT INTO group_jobs (scope_id, job)

                VALUES (?, ?)

                ON CONFLICT(scope_id) DO UPDATE SET job = excluded.job

                """,

                (scope_id, job),

            )

            conn.commit()



    def _scope_has_admins(self, base_url: str, scope_id: str) -> bool:

        try:

            response = requests.post(

                f"{base_url}/internal/scope",

                json={"scope_id": scope_id},

                timeout=10,

            )

            response.raise_for_status()

            return bool(response.json().get("has_admins"))

        except requests.RequestException:

            return False



    def resolve_job(self, scope_id: str) -> str | None:

        explicit = self.get_job(scope_id)

        if explicit:

            return explicit

        for job in ("chores", "rentals", "expenses"):

            if self._scope_has_admins(self.bot_urls[job], scope_id):

                return job

        return None



    def forward(

        self,

        job: str,

        scope_id: str,

        sender: str,

        message: str,

        group_id: str | None,

        attachments: list[dict[str, Any]] | None = None,

    ) -> dict:

        base_url = self.bot_urls.get(job)

        if not base_url:

            raise ValueError(f"Unknown job: {job}")

        payload: dict[str, Any] = {

            "scope_id": scope_id,

            "sender": sender,

            "message": message,

            "group_id": group_id,

        }

        if attachments:

            payload["attachments"] = attachments

        response = requests.post(

            f"{base_url}/internal/handle",

            json=payload,

            timeout=120,

        )

        response.raise_for_status()

        return response.json()





JOB_TEXT = {
    "en": (
        "🤖 Hi! What should I do in this chat? Reply with one word:\n"
        "- chores – household tasks and cleaning schedule\n"
        "- rentals – watch holiday rentals (prices and availability)\n"
        "- expenses – split shared costs\n"
        "💡 chores english also sets the language right away."
    ),
    "de": (
        "🤖 Hallo! Wofür soll ich in diesem Chat da sein? Antworte mit einem Wort:\n"
        "- haushalt – Aufgaben und Putzplan\n"
        "- ferien – Ferienunterkünfte beobachten (Preise und Verfügbarkeit)\n"
        "- ausgaben – gemeinsame Kosten teilen\n"
        "💡 Mit haushalt deutsch stellst du gleich auch die Sprache ein."
    ),
}

_GERMAN_HINTS = {
    "hilfe", "hallo", "moin", "servus", "danke", "bitte", "deutsch", "german", "sprache",
    "haushalt", "haus", "aufgaben", "ferien", "urlaub", "mieten", "mietobjekte",
    "ausgaben", "kosten", "rechnung", "rechnungen",
}
_ENGLISH_HINTS = {
    "help", "hello", "hi", "hey", "thanks", "please", "english", "englisch", "language",
    "chores", "chore", "tasks", "household", "rentals", "rental", "houses", "expenses", "expense",
}


def guess_language(text: str) -> str | None:
    words = set(re.findall(r"[a-zäöüß]+", text.lower()))
    german = bool(words & _GERMAN_HINTS)
    english = bool(words & _ENGLISH_HINTS)
    if german and not english:
        return "de"
    if english and not german:
        return "en"
    return None


_CHORE_ALIASES = {"chores", "chore", "haushalt", "aufgaben", "tasks", "household", "haus"}

_RENTAL_ALIASES = {"rentals", "rental", "mieten", "mietobjekte", "houses", "ferien", "urlaub"}

_EXPENSE_ALIASES = {

    "expenses",

    "expense",

    "ausgaben",

    "kosten",

    "splitwise",

    "tricount",

    "rechnung",

    "rechnungen",

    "kosten teilen",

}

_LANGUAGE_SUFFIXES: tuple[tuple[str, str], ...] = (

    (" english", "en"),

    (" englisch", "en"),

    (" en", "en"),

    (" german", "de"),

    (" deutsch", "de"),

    (" de", "de"),

)





def _parse_job_token(token: str) -> Job | None:

    if token in _CHORE_ALIASES:

        return "chores"

    if token in _RENTAL_ALIASES:

        return "rentals"

    if token in _EXPENSE_ALIASES:

        return "expenses"

    return None





def parse_job_and_language(text: str) -> tuple[Job | None, str | None]:

    cleaned = text.strip().lower()

    if not cleaned:

        return None, None

    for suffix, language in _LANGUAGE_SUFFIXES:

        if cleaned.endswith(suffix):

            job = _parse_job_token(cleaned[: -len(suffix)].strip())

            if job:

                return job, language

    for prefix, language in (("en ", "en"), ("de ", "de"), ("english ", "en"), ("deutsch ", "de")):

        if cleaned.startswith(prefix):

            job = _parse_job_token(cleaned[len(prefix) :].strip())

            if job:

                return job, language

    return _parse_job_token(cleaned), None





def parse_job_command(text: str) -> Job | None:

    job, _ = parse_job_and_language(text)

    return job





def language_command_for(language: str) -> str:

    return "language en" if language == "en" else "sprache deutsch"





def job_picker_text(message_hint: str = "") -> str:
    language = guess_language(message_hint)
    if language:
        return JOB_TEXT[language]
    return JOB_TEXT["en"] + "\n\n" + JOB_TEXT["de"]


JOB_SELECTED = {
    "chores": {
        "en": "🧹 Chore bot selected.",
        "de": "🧹 Haushalts-Bot ausgewählt.",
    },
    "rentals": {
        "en": "🏠 Rental watcher selected.",
        "de": "🏠 Ferienunterkunft-Beobachtung ausgewählt.",
    },
    "expenses": {
        "en": "💸 Expense splitting selected.",
        "de": "💸 Kosten teilen ausgewählt.",
    },
}

LANGUAGE_QUESTION = {
    "en": "Which language should I use? Reply: english or deutsch",
    "de": "Welche Sprache soll ich verwenden? Antworte: deutsch oder english",
}

ERROR_TEXT = {
    "en": "⚠️ Something went wrong. Please try again.",
    "de": "⚠️ Da ist etwas schiefgelaufen. Bitte versuch es noch einmal.",
}


def job_selected_text(job: Job, language: str) -> str:
    return JOB_SELECTED[job][language if language in {"en", "de"} else "en"]


def job_set_ack(job: Job, language_hint: str | None = None) -> str:
    if language_hint in {"en", "de"}:
        return f"{JOB_SELECTED[job][language_hint]}\n{LANGUAGE_QUESTION[language_hint]}"
    return (
        f"{JOB_SELECTED[job]['en']}\n{LANGUAGE_QUESTION['en']}\n\n"
        f"{JOB_SELECTED[job]['de']}\n{LANGUAGE_QUESTION['de']}"
    )


def error_text(message_hint: str = "") -> str:
    language = guess_language(message_hint)
    if language:
        return ERROR_TEXT[language]
    return ERROR_TEXT["en"] + "\n" + ERROR_TEXT["de"]
