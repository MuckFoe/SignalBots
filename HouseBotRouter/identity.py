"""One id per person in a group: the phone number.

Signal and WhatsApp name the same person differently: a number or a UUID on
Signal, "<digits>@c.us" or a private "<n>@lid" on WhatsApp, and the form can
change from one message to the next. The bots key names, admin rights, history
and balances by sender, so the router hands them the phone number whenever it
knows it. The display name is only an alias on top of that. Ids that cannot be
resolved to a number pass through unchanged.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable


def number_from_chat_id(chat_id: str) -> str | None:
    # "491701234567@c.us" -> "+491701234567"
    local, _, server = chat_id.partition("@")
    if server == "c.us" and local.isdigit():
        return f"+{local}"
    return None


class IdentityStore:
    def __init__(self, db_path: str, lid_lookup: Callable[[str], str | None]) -> None:
        self.db_path = db_path
        self.lid_lookup = lid_lookup
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS known_numbers (
                    raw_id TEXT PRIMARY KEY,
                    number TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS merged_aliases (
                    scope_id TEXT NOT NULL,
                    alias TEXT NOT NULL,
                    number TEXT NOT NULL,
                    PRIMARY KEY (scope_id, alias, number)
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def remember(self, raw_id: str, number: str) -> None:
        if not raw_id or not number.startswith("+") or raw_id == number:
            return
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO known_numbers (raw_id, number) VALUES (?, ?)", (raw_id, number))

    def canonical(self, raw_id: str) -> str:
        if raw_id.startswith("+"):
            return raw_id
        number = number_from_chat_id(raw_id)
        if number:
            return number
        with self._connect() as conn:
            row = conn.execute("SELECT number FROM known_numbers WHERE raw_id = ?", (raw_id,)).fetchone()
        if row:
            return row["number"]
        if raw_id.endswith("@lid"):
            number = self.lid_lookup(raw_id)
            if number:
                self.remember(raw_id, number)
                return number
        return raw_id

    def aliases(self, number: str) -> list[str]:
        """Every other id the person with this number is known under."""
        if not number.startswith("+"):
            return []
        with self._connect() as conn:
            known = [row["raw_id"] for row in conn.execute("SELECT raw_id FROM known_numbers WHERE number = ?", (number,))]
        return list(dict.fromkeys([f"{number[1:]}@c.us", *known]))

    def unmerged_aliases(self, scope_id: str, number: str) -> list[str]:
        with self._connect() as conn:
            merged = {
                row["alias"]
                for row in conn.execute(
                    "SELECT alias FROM merged_aliases WHERE scope_id = ? AND number = ?",
                    (scope_id, number),
                )
            }
        return [alias for alias in self.aliases(number) if alias not in merged]

    def mark_merged(self, scope_id: str, alias: str, number: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO merged_aliases (scope_id, alias, number) VALUES (?, ?, ?)",
                (scope_id, alias, number),
            )
