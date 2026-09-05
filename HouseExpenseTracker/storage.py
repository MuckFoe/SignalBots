from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import List, Optional

from balances import simplify_debts
from display_names import default_display_name, is_opaque_sender, is_valid_display_name
from money import split_equal, split_with_multipliers
from dialogue_utils import STALE_STEP, dialogue_ttl_minutes, is_dialogue_stale


class Storage:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
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
                CREATE TABLE IF NOT EXISTS chat_settings (
                    scope_id TEXT PRIMARY KEY,
                    language TEXT NOT NULL DEFAULT 'en',
                    currency TEXT NOT NULL DEFAULT 'EUR',
                    bot_id TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(scope_id, sender)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    number TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS members (
                    scope_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY(scope_id, sender)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    description TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    paid_by TEXT NOT NULL,
                    split_type TEXT NOT NULL DEFAULT 'equal',
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS expense_splits (
                    expense_id INTEGER NOT NULL,
                    member_sender TEXT NOT NULL,
                    share_cents INTEGER NOT NULL,
                    PRIMARY KEY(expense_id, member_sender),
                    FOREIGN KEY(expense_id) REFERENCES expenses(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settlements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    from_sender TEXT NOT NULL,
                    to_sender TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_expense_adds (
                    scope_id TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    step TEXT NOT NULL,
                    amount_cents INTEGER,
                    description TEXT NOT NULL DEFAULT '',
                    paid_by TEXT NOT NULL DEFAULT '',
                    split_members_json TEXT NOT NULL DEFAULT '[]',
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY(scope_id, requested_by)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_member_names (
                    scope_id TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    purpose TEXT NOT NULL DEFAULT 'join',
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY(scope_id, requested_by)
                )
                """
            )
            self._migrate_member_display_names(conn)
            self._ensure_column(conn, "expense_splits", "share_multiplier", "REAL NOT NULL DEFAULT 1.0")
            self._ensure_column(
                conn,
                "pending_expense_adds",
                "split_multipliers_json",
                "TEXT NOT NULL DEFAULT '{}'",
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS command_usage (
                    scope_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    command_key TEXT NOT NULL,
                    usage_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY(scope_id, sender, command_key)
                )
                """
            )
            for table in ("pending_expense_adds", "pending_member_names"):
                self._ensure_dialogue_columns(conn, table)
                self._ensure_column(conn, table, "step", "TEXT NOT NULL DEFAULT ''")
            conn.commit()

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {row["name"] for row in columns}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _ensure_dialogue_columns(self, conn: sqlite3.Connection, table: str) -> None:
        self._ensure_column(conn, table, "last_activity_at", "TEXT NOT NULL DEFAULT (datetime('now'))")
        self._ensure_column(conn, table, "previous_step", "TEXT NOT NULL DEFAULT ''")

    def _dialogue_ttl(self) -> int:
        return dialogue_ttl_minutes()

    def _prepare_dialogue_row(
        self,
        conn: sqlite3.Connection,
        table: str,
        scope_id: str,
        requested_by: str,
        row: sqlite3.Row | None,
        step_column: str = "step",
    ) -> sqlite3.Row | None:
        if row is None:
            return None
        expires_at = row["expires_at"] if "expires_at" in row.keys() else None
        if expires_at and conn.execute(
            "SELECT datetime(?) < datetime('now') AS expired",
            (expires_at,),
        ).fetchone()["expired"]:
            conn.execute(
                f"DELETE FROM {table} WHERE scope_id = ? AND requested_by = ?",
                (scope_id, requested_by),
            )
            conn.commit()
            return None
        last_activity = row["last_activity_at"] if "last_activity_at" in row.keys() else None
        current_step = row[step_column] if step_column in row.keys() else ""
        if current_step != STALE_STEP and is_dialogue_stale(last_activity):
            conn.execute(
                f"""
                UPDATE {table}
                SET {step_column} = ?, previous_step = ?, last_activity_at = datetime('now')
                WHERE scope_id = ? AND requested_by = ?
                """,
                (STALE_STEP, current_step or "", scope_id, requested_by),
            )
            conn.commit()
            return conn.execute(
                f"SELECT * FROM {table} WHERE scope_id = ? AND requested_by = ?",
                (scope_id, requested_by),
            ).fetchone()
        return row

    def restore_dialogue_step(self, table: str, scope_id: str, requested_by: str, step_column: str = "step") -> str:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT previous_step FROM {table} WHERE scope_id = ? AND requested_by = ?",
                (scope_id, requested_by),
            ).fetchone()
            previous = row["previous_step"] if row else ""
            conn.execute(
                f"""
                UPDATE {table}
                SET {step_column} = ?,
                    previous_step = '',
                    last_activity_at = datetime('now'),
                    expires_at = datetime('now', '+' || ? || ' minutes')
                WHERE scope_id = ? AND requested_by = ?
                """,
                (previous, self._dialogue_ttl(), scope_id, requested_by),
            )
            conn.commit()
        return previous

    def bump_command_usage(self, scope_id: str, sender: str, command_key: str) -> int:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO command_usage (scope_id, sender, command_key, usage_count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(scope_id, sender, command_key) DO UPDATE SET
                    usage_count = usage_count + 1,
                    updated_at = datetime('now')
                """,
                (scope_id, sender, command_key),
            )
            conn.commit()
            row = conn.execute(
                "SELECT usage_count FROM command_usage WHERE scope_id = ? AND sender = ? AND command_key = ?",
                (scope_id, sender, command_key),
            ).fetchone()
        return int(row["usage_count"]) if row else 1

    def user_stats(self, scope_id: str, sender: str) -> dict:
        with self._connect() as conn:
            paid_count = conn.execute(
                "SELECT COUNT(*) AS c FROM expenses WHERE scope_id = ? AND paid_by = ?",
                (scope_id, sender),
            ).fetchone()["c"]
            paid_total = conn.execute(
                "SELECT COALESCE(SUM(amount_cents), 0) AS t FROM expenses WHERE scope_id = ? AND paid_by = ?",
                (scope_id, sender),
            ).fetchone()["t"]
            shared_count = conn.execute(
                """
                SELECT COUNT(DISTINCT e.id) AS c
                FROM expenses e
                JOIN expense_splits es ON es.expense_id = e.id
                WHERE e.scope_id = ? AND es.member_sender = ?
                """,
                (scope_id, sender),
            ).fetchone()["c"]
            settlements = conn.execute(
                """
                SELECT COUNT(*) AS c FROM settlements
                WHERE scope_id = ? AND (from_sender = ? OR to_sender = ?)
                """,
                (scope_id, sender, sender),
            ).fetchone()["c"]
        balance = self.compute_balances(scope_id).get(sender, 0)
        return {
            "paid_count": paid_count,
            "paid_total": int(paid_total),
            "shared_count": shared_count,
            "settlements": settlements,
            "balance_cents": balance,
        }

    def _migrate_member_display_names(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT DISTINCT scope_id, sender FROM (
                SELECT scope_id, sender FROM members
                UNION SELECT scope_id, paid_by FROM expenses
                UNION SELECT scope_id, created_by FROM expenses
                UNION SELECT e.scope_id, es.member_sender
                FROM expense_splits es JOIN expenses e ON e.id = es.expense_id
                UNION SELECT scope_id, sender FROM chat_admins
            ) WHERE sender IS NOT NULL AND trim(sender) != ''
            """
        ).fetchall()
        names_by_scope: dict[str, set[str]] = {}
        for row in rows:
            scope_id = row["scope_id"]
            sender = row["sender"].strip()
            if not is_opaque_sender(sender):
                continue
            existing = conn.execute(
                "SELECT display_name FROM members WHERE scope_id = ? AND sender = ?",
                (scope_id, sender),
            ).fetchone()
            if existing is not None:
                names_by_scope.setdefault(scope_id, set()).add(existing["display_name"])
                continue
            used = names_by_scope.setdefault(scope_id, set())
            display_name = default_display_name(sender, used)
            conn.execute(
                "INSERT INTO members (scope_id, sender, display_name) VALUES (?, ?, ?)",
                (scope_id, sender, display_name),
            )

    def register_contact(self, number: str) -> None:
        normalized = number.strip()
        if not normalized:
            return
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO contacts (number) VALUES (?)", (normalized,))
            conn.commit()

    def register_group(self, group_id: str) -> None:
        normalized = group_id.strip()
        if not normalized:
            return
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO chat_groups (group_id) VALUES (?)", (normalized,))
            conn.commit()

    def get_language(self, scope_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT language FROM chat_settings WHERE scope_id = ?", (scope_id,)).fetchone()
        return row["language"] if row else "en"

    def set_language(self, scope_id: str, language: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_settings (scope_id, language) VALUES (?, ?)
                ON CONFLICT(scope_id) DO UPDATE SET language = excluded.language, updated_at = datetime('now')
                """,
                (scope_id, language),
            )
            conn.commit()

    def get_currency(self, scope_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT currency FROM chat_settings WHERE scope_id = ?", (scope_id,)).fetchone()
        return row["currency"] if row else "EUR"

    def set_currency(self, scope_id: str, currency: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_settings (scope_id, currency) VALUES (?, ?)
                ON CONFLICT(scope_id) DO UPDATE SET currency = excluded.currency, updated_at = datetime('now')
                """,
                (scope_id, currency.strip().upper()),
            )
            conn.commit()

    def set_bot_id(self, scope_id: str, bot_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_settings (scope_id, bot_id) VALUES (?, ?)
                ON CONFLICT(scope_id) DO UPDATE SET bot_id = excluded.bot_id, updated_at = datetime('now')
                """,
                (scope_id, bot_id),
            )
            conn.commit()

    def get_bot_id(self, scope_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT bot_id FROM chat_settings WHERE scope_id = ?", (scope_id,)).fetchone()
        return row["bot_id"] if row else ""

    def has_bot(self, scope_id: str) -> bool:
        return bool(self.get_bot_id(scope_id).strip())

    def has_admins(self, scope_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM chat_admins WHERE scope_id = ? LIMIT 1", (scope_id,)).fetchone()
        return row is not None

    def has_language(self, scope_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT language FROM chat_settings WHERE scope_id = ?", (scope_id,)).fetchone()
        return row is not None

    def is_group_ready(self, scope_id: str) -> bool:
        return self.has_language(scope_id) and self.has_admins(scope_id) and self.has_bot(scope_id)

    def is_admin(self, scope_id: str, sender: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM chat_admins WHERE scope_id = ? AND sender = ?",
                (scope_id, sender.strip()),
            ).fetchone()
        return row is not None

    def add_admin(self, scope_id: str, sender: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO chat_admins (scope_id, sender) VALUES (?, ?)",
                (scope_id, sender.strip()),
            )
            conn.commit()

    def is_member(self, scope_id: str, sender: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM members WHERE scope_id = ? AND sender = ?",
                (scope_id, sender.strip()),
            ).fetchone()
        return row is not None

    def display_name(self, scope_id: str, sender: str) -> str:
        normalized = sender.strip()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT display_name FROM members WHERE scope_id = ? AND sender = ?",
                (scope_id, normalized),
            ).fetchone()
        if row is not None:
            return row["display_name"]
        if is_opaque_sender(normalized):
            return normalized[:8]
        return normalized

    def set_display_name(self, scope_id: str, sender: str, display_name: str) -> bool:
        normalized_sender = sender.strip()
        normalized_name = display_name.strip()
        if not normalized_sender or not is_valid_display_name(normalized_name):
            return False
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO members (scope_id, sender, display_name) VALUES (?, ?, ?)
                ON CONFLICT(scope_id, sender) DO UPDATE SET display_name = excluded.display_name
                """,
                (scope_id, normalized_sender, normalized_name),
            )
            conn.commit()
        return True

    def list_members(self, scope_id: str) -> List[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT sender, display_name FROM members
                WHERE scope_id = ? ORDER BY display_name COLLATE NOCASE ASC
                """,
                (scope_id,),
            ).fetchall()

    def find_member_by_name(self, scope_id: str, name: str) -> Optional[sqlite3.Row]:
        cleaned = name.strip()
        if not cleaned:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT sender, display_name FROM members
                WHERE scope_id = ? AND lower(display_name) = lower(?)
                """,
                (scope_id, cleaned),
            ).fetchone()
            if row is not None:
                return row
            return conn.execute(
                """
                SELECT sender, display_name FROM members
                WHERE scope_id = ? AND lower(display_name) LIKE lower(?)
                ORDER BY length(display_name) ASC LIMIT 1
                """,
                (scope_id, f"%{cleaned}%"),
            ).fetchone()

    def remove_member(self, scope_id: str, sender: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM members WHERE scope_id = ? AND sender = ?",
                (scope_id, sender.strip()),
            )
            conn.commit()
        return cursor.rowcount > 0

    def start_pending_member_name(self, scope_id: str, requested_by: str, purpose: str = "join", ttl_minutes: int | None = None) -> None:
        ttl = ttl_minutes if ttl_minutes is not None else self._dialogue_ttl()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_member_names (
                    scope_id, requested_by, purpose, step, expires_at, last_activity_at, previous_step
                )
                VALUES (?, ?, ?, 'name', datetime('now', '+' || ? || ' minutes'), datetime('now'), '')
                ON CONFLICT(scope_id, requested_by) DO UPDATE SET
                    purpose = excluded.purpose,
                    step = 'name',
                    expires_at = excluded.expires_at,
                    last_activity_at = datetime('now'),
                    previous_step = ''
                """,
                (scope_id, requested_by, purpose, ttl),
            )
            conn.commit()

    def get_pending_member_name(self, scope_id: str, requested_by: str) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT purpose, step, previous_step, expires_at, last_activity_at
                FROM pending_member_names
                WHERE scope_id = ? AND requested_by = ?
                """,
                (scope_id, requested_by),
            ).fetchone()
            prepared = self._prepare_dialogue_row(conn, "pending_member_names", scope_id, requested_by, row)
            if prepared is None:
                return None
            return conn.execute(
                "SELECT purpose, step, previous_step FROM pending_member_names WHERE scope_id = ? AND requested_by = ?",
                (scope_id, requested_by),
            ).fetchone()

    def clear_pending_member_name(self, scope_id: str, requested_by: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM pending_member_names WHERE scope_id = ? AND requested_by = ?",
                (scope_id, requested_by),
            )
            conn.commit()

    def start_pending_expense(self, scope_id: str, requested_by: str, ttl_minutes: int | None = None) -> None:
        ttl = ttl_minutes if ttl_minutes is not None else self._dialogue_ttl()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_expense_adds (
                    scope_id, requested_by, step, expires_at, last_activity_at, previous_step
                )
                VALUES (?, ?, 'amount', datetime('now', '+' || ? || ' minutes'), datetime('now'), '')
                ON CONFLICT(scope_id, requested_by) DO UPDATE SET
                    step = 'amount', amount_cents = NULL, description = '', paid_by = '',
                    split_members_json = '[]', split_multipliers_json = '{}',
                    expires_at = excluded.expires_at, last_activity_at = datetime('now'), previous_step = ''
                """,
                (scope_id, requested_by, ttl),
            )
            conn.commit()

    def get_pending_expense(self, scope_id: str, requested_by: str) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT step, amount_cents, description, paid_by, split_members_json, split_multipliers_json,
                       previous_step, expires_at, last_activity_at
                FROM pending_expense_adds
                WHERE scope_id = ? AND requested_by = ?
                """,
                (scope_id, requested_by),
            ).fetchone()
            return self._prepare_dialogue_row(conn, "pending_expense_adds", scope_id, requested_by, row)

    def update_pending_expense(
        self,
        scope_id: str,
        requested_by: str,
        step: str,
        amount_cents: int | None = None,
        description: str | None = None,
        paid_by: str | None = None,
        split_members: list[str] | None = None,
        split_multipliers: dict[str, float] | None = None,
        ttl_minutes: int | None = None,
    ) -> None:
        ttl = ttl_minutes if ttl_minutes is not None else self._dialogue_ttl()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT amount_cents, description, paid_by, split_members_json, split_multipliers_json FROM pending_expense_adds WHERE scope_id = ? AND requested_by = ?",
                (scope_id, requested_by),
            ).fetchone()
            current_amount = row["amount_cents"] if row else None
            current_description = row["description"] if row else ""
            current_paid_by = row["paid_by"] if row else ""
            current_split = json.loads(row["split_members_json"]) if row else []
            current_multipliers = json.loads(row["split_multipliers_json"]) if row else {}
            conn.execute(
                """
                UPDATE pending_expense_adds
                SET step = ?, amount_cents = ?, description = ?, paid_by = ?,
                    split_members_json = ?, split_multipliers_json = ?,
                    expires_at = datetime('now', '+' || ? || ' minutes'),
                    last_activity_at = datetime('now')
                WHERE scope_id = ? AND requested_by = ?
                """,
                (
                    step,
                    amount_cents if amount_cents is not None else current_amount,
                    description if description is not None else current_description,
                    paid_by if paid_by is not None else current_paid_by,
                    json.dumps(split_members if split_members is not None else current_split),
                    json.dumps(split_multipliers if split_multipliers is not None else current_multipliers),
                    ttl_minutes,
                    scope_id,
                    requested_by,
                ),
            )
            conn.commit()

    def clear_pending_expense(self, scope_id: str, requested_by: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM pending_expense_adds WHERE scope_id = ? AND requested_by = ?",
                (scope_id, requested_by),
            )
            conn.commit()

    def add_expense(
        self,
        scope_id: str,
        description: str,
        amount_cents: int,
        currency: str,
        paid_by: str,
        split_members: list[str],
        created_by: str,
        split_type: str = "equal",
        custom_shares: dict[str, int] | None = None,
        multipliers: dict[str, float] | None = None,
    ) -> int:
        if not split_members:
            raise ValueError("split_members required")
        if custom_shares is not None:
            shares_map = custom_shares
            split_type = "custom"
        elif multipliers and any(multipliers.get(member, 1.0) < 1.0 for member in split_members):
            shares_map = split_with_multipliers(amount_cents, split_members, multipliers)
            split_type = "weighted"
        else:
            equal_parts = split_equal(amount_cents, len(split_members))
            shares_map = {member: equal_parts[index] for index, member in enumerate(split_members)}
            split_type = split_type or "equal"
        if sum(shares_map.values()) != amount_cents:
            raise ValueError("shares must sum to amount")
        active_multipliers = multipliers or {}
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO expenses (scope_id, description, amount_cents, currency, paid_by, split_type, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (scope_id, description.strip(), amount_cents, currency, paid_by, split_type, created_by),
            )
            expense_id = cursor.lastrowid
            for member in split_members:
                conn.execute(
                    """
                    INSERT INTO expense_splits (expense_id, member_sender, share_cents, share_multiplier)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        expense_id,
                        member,
                        shares_map[member],
                        active_multipliers.get(member, 1.0),
                    ),
                )
            conn.commit()
        return int(expense_id)

    def get_expense(self, scope_id: str, expense_id: int) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, description, amount_cents, currency, paid_by, split_type, created_by, created_at
                FROM expenses WHERE scope_id = ? AND id = ?
                """,
                (scope_id, expense_id),
            ).fetchone()

    def list_expense_splits(self, expense_id: int) -> List[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT member_sender, share_cents, share_multiplier FROM expense_splits WHERE expense_id = ? ORDER BY member_sender",
                (expense_id,),
            ).fetchall()

    def list_expenses(self, scope_id: str, limit: int = 20) -> List[sqlite3.Row]:
        limit = max(1, min(limit, 50))
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, description, amount_cents, currency, paid_by, created_at
                FROM expenses WHERE scope_id = ? ORDER BY id DESC LIMIT ?
                """,
                (scope_id, limit),
            ).fetchall()

    def delete_expense(self, scope_id: str, expense_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM expenses WHERE scope_id = ? AND id = ?", (scope_id, expense_id))
            conn.commit()
        return cursor.rowcount > 0

    def add_settlement(
        self,
        scope_id: str,
        from_sender: str,
        to_sender: str,
        amount_cents: int,
        currency: str,
        created_by: str,
        note: str = "",
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO settlements (scope_id, from_sender, to_sender, amount_cents, currency, note, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (scope_id, from_sender, to_sender, amount_cents, currency, note.strip(), created_by),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def list_settlements(self, scope_id: str, limit: int = 10) -> List[sqlite3.Row]:
        limit = max(1, min(limit, 30))
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, from_sender, to_sender, amount_cents, currency, note, created_at
                FROM settlements WHERE scope_id = ? ORDER BY id DESC LIMIT ?
                """,
                (scope_id, limit),
            ).fetchall()

    def compute_balances(self, scope_id: str) -> dict[str, int]:
        balances: dict[str, int] = {}
        with self._connect() as conn:
            for row in conn.execute("SELECT sender FROM members WHERE scope_id = ?", (scope_id,)):
                balances[row["sender"]] = 0
            for row in conn.execute("SELECT paid_by, amount_cents FROM expenses WHERE scope_id = ?", (scope_id,)):
                balances[row["paid_by"]] = balances.get(row["paid_by"], 0) + row["amount_cents"]
            for row in conn.execute(
                """
                SELECT es.member_sender, es.share_cents
                FROM expense_splits es JOIN expenses e ON e.id = es.expense_id
                WHERE e.scope_id = ?
                """,
                (scope_id,),
            ):
                balances[row["member_sender"]] = balances.get(row["member_sender"], 0) - row["share_cents"]
            for row in conn.execute(
                "SELECT from_sender, to_sender, amount_cents FROM settlements WHERE scope_id = ?",
                (scope_id,),
            ):
                balances[row["from_sender"]] = balances.get(row["from_sender"], 0) + row["amount_cents"]
                balances[row["to_sender"]] = balances.get(row["to_sender"], 0) - row["amount_cents"]
        return balances

    def simplified_debts(self, scope_id: str) -> list[tuple[str, str, int]]:
        return simplify_debts(self.compute_balances(scope_id))

    def total_spent(self, scope_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM expenses WHERE scope_id = ?",
                (scope_id,),
            ).fetchone()
        return int(row["total"])

    def member_paid_totals(self, scope_id: str) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT paid_by, COALESCE(SUM(amount_cents), 0) AS total
                FROM expenses
                WHERE scope_id = ?
                GROUP BY paid_by
                """,
                (scope_id,),
            ).fetchall()
        return {row["paid_by"]: int(row["total"]) for row in rows}

    def balance_between(self, scope_id: str, from_sender: str, to_sender: str) -> int:
        debts = self.simplified_debts(scope_id)
        owed = 0
        for debtor, creditor, amount in debts:
            if debtor == from_sender and creditor == to_sender:
                owed += amount
            elif debtor == to_sender and creditor == from_sender:
                owed -= amount
        return owed
