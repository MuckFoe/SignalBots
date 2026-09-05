from __future__ import annotations



import sqlite3

from pathlib import Path

from typing import Any, Literal



import requests



Job = Literal["chores", "rentals", "expenses", "grocery"]





class GroupRouter:

    def __init__(

        self,

        db_path: str,

        chore_bot_url: str,

        rental_bot_url: str,

        expense_bot_url: str,

        grocery_bot_url: str,

    ) -> None:

        self.db_path = db_path

        self.bot_urls = {

            "chores": chore_bot_url.rstrip("/"),

            "rentals": rental_bot_url.rstrip("/"),

            "expenses": expense_bot_url.rstrip("/"),

            "grocery": grocery_bot_url.rstrip("/"),

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

        for job in ("chores", "rentals", "expenses", "grocery"):

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

        "🤖 What should this chat do?\n"

        "Reply: chores · rentals · expenses · grocery\n"

        "(aliases: haus · ferien · tricount · einkauf)\n"

        "💡 Tip: grocery en or einkauf deutsch sets language too."

    ),

    "de": (

        "🤖 Was soll dieser Chat machen?\n"

        "Antworte: chores · rentals · expenses · grocery\n"

        "(Kürzel: haus · ferien · tricount · einkauf)\n"

        "💡 Tipp: grocery en oder einkauf deutsch wählt auch die Sprache."

    ),

}



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

_GROCERY_ALIASES = {

    "grocery",

    "groceries",

    "shopping",

    "einkauf",

    "einkaufsliste",

    "einkaufen",

    "lebensmittel",

    "supermarkt",

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

    if token in _GROCERY_ALIASES:

        return "grocery"

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

    lowered = message_hint.strip().lower()

    if any(token in lowered for token in ("deutsch", "german", "sprache de")):

        return JOB_TEXT["de"]

    if any(token in lowered for token in ("english", "englisch", "language en")):

        return JOB_TEXT["en"]

    return JOB_TEXT["en"] + "\n\n" + JOB_TEXT["de"]





JOB_SET_ACK = {

    "chores": {

        "en": "🧹 Chore bot. Choose language: language en or sprache deutsch",

        "de": "🧹 Haushalts-Bot. Sprache wählen: language en oder sprache deutsch",

    },

    "rentals": {

        "en": "🏠 Rental tracker. Choose language: language en or sprache deutsch",

        "de": "🏠 Mieten-Tracker. Sprache wählen: language en oder sprache deutsch",

    },

    "expenses": {

        "en": "💸 Expense split bot. Choose language: language en or sprache deutsch",

        "de": "💸 Ausgaben-Bot. Sprache wählen: language en oder sprache deutsch",

    },

    "grocery": {

        "en": "🛒 Grocery list bot. Choose language: language en or sprache deutsch",

        "de": "🛒 Einkaufslisten-Bot. Sprache wählen: language en oder sprache deutsch",

    },

}





def job_set_ack(job: Job, language_hint: str | None = None) -> str:

    if language_hint in {"en", "de"}:

        return JOB_SET_ACK[job][language_hint]

    return JOB_SET_ACK[job]["en"] + "\n" + JOB_SET_ACK[job]["de"]

