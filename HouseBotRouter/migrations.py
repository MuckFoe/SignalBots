"""Moving a group between Signal and WhatsApp.

Flow: an admin writes "umzug whatsapp" in the old group and gets a one-time
code; someone writes "umzug <code>" in the new group; the bot owning the group
moves its data there and the old group goes quiet. Members whose phone number
the router recognises on both sides keep their identity automatically; the
others claim their old identity with "ich bin <Name>" so history, admin rights
and balances follow them to their new chat id.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
from pathlib import Path

CODE_TTL_MINUTES = 30

PLATFORM_NAMES = {"whatsapp": "WhatsApp", "signal": "Signal"}

_START_RE = re.compile(r"^(?:umzug|umziehen|move)(?:\s+(?:nach|to))?\s+(whatsapp|signal)[.!]?$", re.IGNORECASE)
_CODE_RE = re.compile(r"^(?:umzug|move)\s+(\d{6})$", re.IGNORECASE)
_CLAIM_RE = re.compile(r"^(?:ich bin|i am|i'm|im)\s+(.+?)[.!]?$", re.IGNORECASE)


def platform_of(group_id: str | None) -> str:
    # WhatsApp chat ids always contain "@"; Signal ids never do.
    return "whatsapp" if group_id and "@" in group_id else "signal"


def parse_start(text: str) -> str | None:
    match = _START_RE.match(text.strip())
    return match.group(1).lower() if match else None


def parse_code(text: str) -> str | None:
    match = _CODE_RE.match(text.strip())
    return match.group(1) if match else None


def parse_claim(text: str) -> str | None:
    match = _CLAIM_RE.match(text.strip())
    return match.group(1).strip() if match else None


def code_language(text: str) -> str:
    return "de" if text.strip().lower().startswith("umz") else "en"


TEXT = {
    "en": {
        "start_ok": (
            "📦 Move to {platform} prepared.\n"
            "1. Create the new {platform} group and add the bot to it.\n"
            "2. Within 30 minutes, send there: move {code}\n"
            "All data of this group then moves there, and I will no longer reply here."
        ),
        "already_there": "This group is already on {platform}.",
        "not_admin": "Only admins of this group can start a move.",
        "invalid_code": (
            "This move code is invalid or has expired. "
            "Start the move again in the old group with: move whatsapp or move signal"
        ),
        "wrong_platform": "This code is for a move to {platform}. Please send it in the new {platform} group.",
        "target_in_use": "The bot is already in use in this group. Please send the code in a new group.",
        "failed": "⚠️ The move did not work. Please try again.",
        "done": "✅ Move complete – all data from the old group is here now.",
        "claim_prompt": (
            "👋 If you were in the old group, send this once: i am <name>\n"
            "Not claimed yet: {names}"
        ),
        "old_notice": "📦 This group has moved to {platform}. I will no longer reply here.",
        "claim_ok": "✅ Welcome back, {name}! Your history from the old group is yours again.",
        "claim_already": "You are already linked as {name}.",
    },
    "de": {
        "start_ok": (
            "📦 Umzug nach {platform} vorbereitet.\n"
            "1. Erstelle die neue {platform}-Gruppe und füge den Bot hinzu.\n"
            "2. Schreib dort innerhalb von 30 Minuten: umzug {code}\n"
            "Danach sind alle Daten dieser Gruppe dort, und hier antworte ich nicht mehr."
        ),
        "already_there": "Diese Gruppe ist schon auf {platform}.",
        "not_admin": "Einen Umzug können nur Admins dieser Gruppe starten.",
        "invalid_code": (
            "Dieser Umzugscode ist ungültig oder abgelaufen. "
            "Starte den Umzug in der alten Gruppe neu mit: umzug whatsapp oder umzug signal"
        ),
        "wrong_platform": "Dieser Code ist für einen Umzug nach {platform}. Bitte schick ihn in der neuen {platform}-Gruppe.",
        "target_in_use": "In dieser Gruppe ist der Bot schon im Einsatz. Bitte schick den Code in einer neuen Gruppe.",
        "failed": "⚠️ Der Umzug hat nicht geklappt. Bitte versuch es noch einmal.",
        "done": "✅ Umzug abgeschlossen – alle Daten aus der alten Gruppe sind jetzt hier.",
        "claim_prompt": (
            "👋 Wer schon in der alten Gruppe dabei war, schreibt hier einmal: ich bin <Name>\n"
            "Noch offen: {names}"
        ),
        "old_notice": "📦 Diese Gruppe ist nach {platform} umgezogen. Hier antworte ich ab jetzt nicht mehr.",
        "claim_ok": "✅ Willkommen zurück, {name}! Dein Verlauf aus der alten Gruppe gehört jetzt wieder dir.",
        "claim_already": "Du bist schon als {name} zugeordnet.",
    },
}


def text(language: str | None, key: str, **kwargs: object) -> str:
    table = TEXT.get(language or "en", TEXT["en"])
    return table[key].format(**kwargs)


def claim_prompt(language: str | None, names: list[str]) -> str:
    return text(language, "claim_prompt", names=", ".join(names))


class MigrationStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS migration_codes (
                    code TEXT PRIMARY KEY,
                    from_scope TEXT NOT NULL,
                    from_group_id TEXT NOT NULL,
                    job TEXT NOT NULL,
                    target_platform TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    language TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS moved_scopes (
                    scope_id TEXT PRIMARY KEY,
                    moved_to TEXT NOT NULL,
                    moved_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS migration_claims (
                    scope_id TEXT NOT NULL,
                    old_sender TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    language TEXT NOT NULL,
                    claimed_by TEXT,
                    PRIMARY KEY (scope_id, old_sender)
                );
                CREATE TABLE IF NOT EXISTS migration_hints (
                    scope_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    PRIMARY KEY (scope_id, sender)
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_code(
        self,
        from_scope: str,
        from_group_id: str,
        job: str,
        target_platform: str,
        requested_by: str,
        language: str,
    ) -> str:
        with self._connect() as conn:
            conn.execute("DELETE FROM migration_codes WHERE expires_at <= datetime('now') OR from_scope = ?", (from_scope,))
            while True:
                code = f"{secrets.randbelow(1_000_000):06d}"
                if conn.execute("SELECT 1 FROM migration_codes WHERE code = ?", (code,)).fetchone() is None:
                    break
            conn.execute(
                """
                INSERT INTO migration_codes
                    (code, from_scope, from_group_id, job, target_platform, requested_by, language, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', ?))
                """,
                (code, from_scope, from_group_id, job, target_platform, requested_by, language, f"+{CODE_TTL_MINUTES} minutes"),
            )
        return code

    def get_code(self, code: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM migration_codes WHERE code = ? AND expires_at > datetime('now')",
                (code,),
            ).fetchone()

    def finish_move(
        self,
        code: str,
        old_scope: str,
        new_scope: str,
        job: str,
        members: list[dict],
        language: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM migration_codes WHERE code = ?", (code,))
            conn.execute("DELETE FROM group_jobs WHERE scope_id = ?", (old_scope,))
            conn.execute(
                """
                INSERT INTO group_jobs (scope_id, job) VALUES (?, ?)
                ON CONFLICT(scope_id) DO UPDATE SET job = excluded.job
                """,
                (new_scope, job),
            )
            conn.execute("DELETE FROM moved_scopes WHERE scope_id = ?", (new_scope,))
            conn.execute(
                "INSERT OR REPLACE INTO moved_scopes (scope_id, moved_to) VALUES (?, ?)",
                (old_scope, new_scope),
            )
            for scope in (old_scope, new_scope):
                conn.execute("DELETE FROM migration_claims WHERE scope_id = ?", (scope,))
                conn.execute("DELETE FROM migration_hints WHERE scope_id = ?", (scope,))
            conn.executemany(
                "INSERT INTO migration_claims (scope_id, old_sender, display_name, language) VALUES (?, ?, ?, ?)",
                [(new_scope, member["sender"], member["name"], language) for member in members],
            )

    def is_moved(self, scope_id: str) -> bool:
        with self._connect() as conn:
            return conn.execute("SELECT 1 FROM moved_scopes WHERE scope_id = ?", (scope_id,)).fetchone() is not None

    def open_claims(self, scope_id: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM migration_claims WHERE scope_id = ? AND claimed_by IS NULL ORDER BY display_name",
                (scope_id,),
            ).fetchall()

    def claimed_name(self, scope_id: str, sender: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT display_name FROM migration_claims WHERE scope_id = ? AND claimed_by = ?",
                (scope_id, sender),
            ).fetchone()
        return row["display_name"] if row else None

    def mark_claimed(self, scope_id: str, old_sender: str, new_sender: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE migration_claims SET claimed_by = ? WHERE scope_id = ? AND old_sender = ?",
                (new_sender, scope_id, old_sender),
            )

    def claim_own(self, scope_id: str, old_senders: list[str], new_sender: str) -> None:
        # A member whose old id is the same person (same number) needs no "ich bin".
        with self._connect() as conn:
            conn.executemany(
                "UPDATE migration_claims SET claimed_by = ? WHERE scope_id = ? AND old_sender = ? AND claimed_by IS NULL",
                [(new_sender, scope_id, old_sender) for old_sender in old_senders],
            )

    def hint_once(self, scope_id: str, sender: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO migration_hints (scope_id, sender) VALUES (?, ?)",
                (scope_id, sender),
            )
            return cursor.rowcount == 1
