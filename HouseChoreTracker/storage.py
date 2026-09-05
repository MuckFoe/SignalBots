from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from schedule_utils import (
    DEFAULT_TIMEZONE,
    ONE_SHOT_STATS_KEY,
    is_one_shot_schedule,
    local_now,
    next_due_at,
    normalize_timezone_name,
    parse_db_datetime,
    schedule_from_storage,
    schedule_to_minutes,
    schedule_to_storage,
)
from display_names import default_display_name, is_opaque_sender, is_valid_display_name
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
            self._migrate_chores_schema(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    reminder_interval_minutes INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    last_reminded_at TEXT
                )
                """
            )
            self._ensure_column(conn, "chores", "reminder_interval_minutes", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "chores", "created_at", "TEXT NOT NULL DEFAULT (datetime('now'))")
            self._ensure_column(conn, "chores", "last_reminded_at", "TEXT")
            self._ensure_column(conn, "chores", "scope_id", "TEXT NOT NULL DEFAULT 'legacy'")
            self._ensure_column(conn, "chores", "reminder_schedule", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "chores", "requires_confirmation", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "chores", "repeat_reminder_minutes", "INTEGER NOT NULL DEFAULT 1440")
            self._ensure_column(conn, "chores", "repeat_reminder_schedule", "TEXT NOT NULL DEFAULT 'interval:1:days'")
            self._ensure_column(conn, "chores", "reminder_at_minutes", "INTEGER")
            self._ensure_column(conn, "chores", "vacation_delay_seconds", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "chores", "one_shot", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "chores", "count_in_stats", "INTEGER NOT NULL DEFAULT 1")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chore_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chore_id INTEGER NOT NULL,
                    sender TEXT NOT NULL,
                    done_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY(chore_id) REFERENCES chores(id)
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
                CREATE TABLE IF NOT EXISTS reset_requests (
                    scope_id TEXT PRIMARY KEY,
                    requested_by TEXT NOT NULL,
                    token TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_settings (
                    scope_id TEXT PRIMARY KEY,
                    language TEXT NOT NULL DEFAULT 'en',
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            self._ensure_column(conn, "chat_settings", "quiet_start_minutes", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "chat_settings", "quiet_end_minutes", "INTEGER NOT NULL DEFAULT 480")
            self._ensure_column(conn, "chat_settings", "auth_reminder_enabled", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "chat_settings", "bot_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(
                conn,
                "chat_settings",
                "timezone",
                "TEXT NOT NULL DEFAULT 'Europe/Berlin'",
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
                CREATE TABLE IF NOT EXISTS admin_setup_codes (
                    scope_id TEXT PRIMARY KEY,
                    code TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_chore_adds (
                    scope_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    reminder_interval_minutes INTEGER NOT NULL,
                    requested_by TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            self._ensure_column(conn, "pending_chore_adds", "reminder_schedule", "TEXT NOT NULL DEFAULT ''")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_chore_setups (
                    scope_id TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    step TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    reminder_schedule TEXT NOT NULL DEFAULT '',
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY(scope_id, requested_by)
                )
                """
            )
            self._ensure_column(conn, "pending_chore_setups", "reminder_at_minutes", "INTEGER")
            self._ensure_column(conn, "pending_chore_setups", "one_shot", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "pending_chore_setups", "count_in_stats", "INTEGER")
            self._ensure_column(conn, "chore_logs", "scope_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "chore_logs", "chore_name", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "chore_logs", "one_shot", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "chore_logs", "count_in_stats", "INTEGER NOT NULL DEFAULT 1")
            self._backfill_one_shot_logs(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_chore_edits (
                    scope_id TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    chore_name TEXT NOT NULL,
                    field TEXT NOT NULL DEFAULT '',
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY(scope_id, requested_by)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS action_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    chore_name TEXT,
                    details TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS member_names (
                    scope_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY(scope_id, sender)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_member_names (
                    scope_id TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    chore_name TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY(scope_id, requested_by)
                )
                """
            )
            self._migrate_member_display_names(conn)
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vacation_chores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(scope_id, name COLLATE NOCASE)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS member_vacations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    starts_at TEXT NOT NULL,
                    ends_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    ended_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vacation_prep_done (
                    vacation_id INTEGER NOT NULL,
                    vacation_chore_id INTEGER NOT NULL,
                    sender TEXT NOT NULL,
                    done_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (vacation_id, vacation_chore_id),
                    FOREIGN KEY(vacation_id) REFERENCES member_vacations(id),
                    FOREIGN KEY(vacation_chore_id) REFERENCES vacation_chores(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_vacation_setups (
                    scope_id TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    step TEXT NOT NULL,
                    delay_days INTEGER NOT NULL DEFAULT 0,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    last_activity_at TEXT NOT NULL DEFAULT (datetime('now')),
                    previous_step TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(scope_id, requested_by)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_vacation_chore_adds (
                    scope_id TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    step TEXT NOT NULL DEFAULT 'name',
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    last_activity_at TEXT NOT NULL DEFAULT (datetime('now')),
                    previous_step TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(scope_id, requested_by)
                )
                """
            )
            for table in (
                "pending_chore_setups",
                "pending_chore_edits",
                "pending_member_names",
                "pending_vacation_setups",
                "pending_vacation_chore_adds",
            ):
                self._ensure_dialogue_columns(conn, table)
                self._ensure_column(conn, table, "step", "TEXT NOT NULL DEFAULT ''")
            conn.commit()

    def _migrate_chores_schema(self, conn: sqlite3.Connection) -> None:
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'chores'"
        ).fetchone()
        if table_exists is None:
            return

        columns = conn.execute("PRAGMA table_info(chores)").fetchall()
        has_scope_id = any(col["name"] == "scope_id" for col in columns)
        if has_scope_id:
            return

        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            """
            CREATE TABLE chores_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_id TEXT NOT NULL,
                name TEXT NOT NULL,
                reminder_interval_minutes INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_reminded_at TEXT,
                UNIQUE(scope_id, name)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO chores_new (id, scope_id, name, reminder_interval_minutes, created_at, last_reminded_at)
            SELECT
                id,
                'legacy',
                name,
                COALESCE(reminder_interval_minutes, 0),
                COALESCE(created_at, datetime('now')),
                last_reminded_at
            FROM chores
            """
        )
        conn.execute("DROP TABLE chores")
        conn.execute("ALTER TABLE chores_new RENAME TO chores")
        conn.execute("PRAGMA foreign_keys = ON")

    def _migrate_member_display_names(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT DISTINCT scope_id, sender
            FROM (
                SELECT c.scope_id AS scope_id, l.sender AS sender
                FROM chore_logs l
                JOIN chores c ON c.id = l.chore_id
                UNION
                SELECT scope_id, sender FROM chat_admins
                UNION
                SELECT scope_id, sender FROM action_logs
            )
            WHERE sender IS NOT NULL AND trim(sender) != ''
            """
        ).fetchall()
        names_by_scope: dict[str, set[str]] = {}
        for row in rows:
            scope_id = row["scope_id"]
            sender = row["sender"].strip()
            if not is_opaque_sender(sender):
                continue
            existing = conn.execute(
                "SELECT display_name FROM member_names WHERE scope_id = ? AND sender = ?",
                (scope_id, sender),
            ).fetchone()
            if existing is not None:
                names_by_scope.setdefault(scope_id, set()).add(existing["display_name"])
                continue
            used = names_by_scope.setdefault(scope_id, set())
            display_name = default_display_name(sender, used)
            conn.execute(
                """
                INSERT INTO member_names (scope_id, sender, display_name)
                VALUES (?, ?, ?)
                """,
                (scope_id, sender, display_name),
            )

    def _backfill_one_shot_logs(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            UPDATE chores
            SET one_shot = 1
            WHERE reminder_schedule LIKE 'once%' AND one_shot = 0
            """
        )
        conn.execute(
            """
            UPDATE chore_logs
            SET
                scope_id = COALESCE(
                    NULLIF(scope_id, ''),
                    (SELECT c.scope_id FROM chores c WHERE c.id = chore_logs.chore_id),
                    ''
                ),
                chore_name = COALESCE(
                    NULLIF(chore_name, ''),
                    (SELECT c.name FROM chores c WHERE c.id = chore_logs.chore_id),
                    ''
                ),
                one_shot = CASE
                    WHEN one_shot = 1 THEN 1
                    ELSE COALESCE(
                        (SELECT c.one_shot FROM chores c WHERE c.id = chore_logs.chore_id),
                        0
                    )
                END,
                count_in_stats = CASE
                    WHEN count_in_stats = 0 THEN 0
                    ELSE COALESCE(
                        (SELECT c.count_in_stats FROM chores c WHERE c.id = chore_logs.chore_id),
                        1
                    )
                END
            """
        )

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

    def restore_dialogue_step(
        self,
        table: str,
        scope_id: str,
        requested_by: str,
        step_column: str = "step",
    ) -> str:
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
                """
                SELECT usage_count FROM command_usage
                WHERE scope_id = ? AND sender = ? AND command_key = ?
                """,
                (scope_id, sender, command_key),
            ).fetchone()
        return int(row["usage_count"]) if row else 1

    def user_stats(self, scope_id: str, sender: str) -> dict:
        logs = self._completion_log_rows(scope_id, sender)
        by_chore_counts: dict[str, int] = {}
        last_done = None
        for row in logs:
            bucket = self._stats_bucket(row)
            by_chore_counts[bucket] = by_chore_counts.get(bucket, 0) + 1
            if last_done is None or row["done_at"] > last_done:
                last_done = row["done_at"]
        by_chore = [
            {"name": name, "count": count}
            for name, count in sorted(by_chore_counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        top_chore = by_chore[0] if by_chore else None
        return {
            "total_completions": len(logs),
            "unique_chores": len(by_chore_counts),
            "top_chore": top_chore,
            "last_done_at": last_done,
            "by_chore": by_chore,
        }

    def task_stats(self, scope_id: str) -> list[dict]:
        logs = self._completion_log_rows(scope_id)
        completions: dict[str, dict] = {}
        contributors: dict[str, dict[str, int]] = {}
        for row in logs:
            bucket = self._stats_bucket(row)
            item = completions.setdefault(
                bucket,
                {"name": bucket, "completions": 0, "last_done_at": None, "last_done_by": None},
            )
            item["completions"] += 1
            if item["last_done_at"] is None or row["done_at"] > item["last_done_at"]:
                item["last_done_at"] = row["done_at"]
                item["last_done_by"] = row["sender"]
            by_person = contributors.setdefault(bucket, {})
            by_person[row["sender"]] = by_person.get(row["sender"], 0) + 1

        result = []
        with self._connect() as conn:
            live_rows = conn.execute(
                """
                SELECT name
                FROM chores
                WHERE scope_id = ? AND one_shot = 0
                ORDER BY name ASC
                """,
                (scope_id,),
            ).fetchall()
        seen = set()
        for row in live_rows:
            name = row["name"]
            seen.add(name)
            item = completions.get(
                name,
                {"name": name, "completions": 0, "last_done_at": None, "last_done_by": None},
            )
            people = contributors.get(name, {})
            item["by_person"] = [
                {"sender": sender, "count": count}
                for sender, count in sorted(people.items(), key=lambda pair: (-pair[1], pair[0]))
            ]
            result.append(item)
        if ONE_SHOT_STATS_KEY in completions:
            item = completions[ONE_SHOT_STATS_KEY]
            people = contributors.get(ONE_SHOT_STATS_KEY, {})
            item["by_person"] = [
                {"sender": sender, "count": count}
                for sender, count in sorted(people.items(), key=lambda pair: (-pair[1], pair[0]))
            ]
            result.append(item)
        result.sort(key=lambda item: (-int(item["completions"] or 0), item["name"]))
        return result

    def group_completion_totals(self, scope_id: str) -> list[dict]:
        totals: dict[str, int] = {}
        for row in self._completion_log_rows(scope_id):
            totals[row["sender"]] = totals.get(row["sender"], 0) + 1
        return [
            {"sender": sender, "count": count}
            for sender, count in sorted(totals.items(), key=lambda item: (-item[1], item[0]))
        ]

    def _completion_log_rows(self, scope_id: str, sender: str | None = None) -> list[sqlite3.Row]:
        query = """
            SELECT
                l.sender,
                l.done_at,
                l.chore_id,
                COALESCE(l.one_shot, 0) AS one_shot,
                COALESCE(l.count_in_stats, 1) AS count_in_stats,
                COALESCE(NULLIF(l.chore_name, ''), c.name, '') AS chore_name,
                COALESCE(NULLIF(l.scope_id, ''), c.scope_id, '') AS log_scope_id
            FROM chore_logs l
            LEFT JOIN chores c ON c.id = l.chore_id
            WHERE COALESCE(NULLIF(l.scope_id, ''), c.scope_id, '') = ?
              AND COALESCE(l.count_in_stats, 1) = 1
        """
        params: list[str] = [scope_id]
        if sender is not None:
            query += " AND l.sender = ?"
            params.append(sender)
        query += " ORDER BY l.done_at ASC, l.chore_id ASC"
        with self._connect() as conn:
            return conn.execute(query, params).fetchall()

    def _stats_bucket(self, row: sqlite3.Row) -> str:
        if int(row["one_shot"] or 0) == 1:
            return ONE_SHOT_STATS_KEY
        return row["chore_name"] or ""

    def add_chore(
        self,
        scope_id: str,
        name: str,
        schedule: dict,
        reminder_at_minutes: int | None = None,
        count_in_stats: bool = True,
    ) -> bool:
        normalized = name.strip()
        if not normalized or not schedule or not scope_id.strip():
            return False
        reminder_interval_minutes = schedule_to_minutes(schedule)
        reminder_schedule = schedule_to_storage(schedule)
        one_shot = 1 if is_one_shot_schedule(schedule) else 0
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO chores (
                        scope_id, name, reminder_interval_minutes, reminder_schedule,
                        reminder_at_minutes, one_shot, count_in_stats
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        scope_id,
                        normalized,
                        reminder_interval_minutes,
                        reminder_schedule,
                        reminder_at_minutes,
                        one_shot,
                        1 if count_in_stats else 0,
                    ),
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def log_action(
        self,
        scope_id: str,
        sender: str,
        action_type: str,
        chore_name: Optional[str] = None,
        details: Optional[str] = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO action_logs (scope_id, sender, action_type, chore_name, details)
                VALUES (?, ?, ?, ?, ?)
                """,
                (scope_id, sender, action_type, chore_name, details),
            )
            conn.commit()

    def list_chores(self, scope_id: str) -> List[sqlite3.Row]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT c.name, c.reminder_interval_minutes, c.reminder_schedule, c.requires_confirmation,
                       c.repeat_reminder_minutes, c.repeat_reminder_schedule,
                       c.created_at, c.last_reminded_at, c.reminder_at_minutes, c.one_shot, c.count_in_stats,
                       (SELECT MAX(l.done_at) FROM chore_logs l WHERE l.chore_id = c.id) AS last_done_at,
                       (SELECT l.sender FROM chore_logs l WHERE l.chore_id = c.id
                        ORDER BY l.done_at DESC, l.id DESC LIMIT 1) AS last_done_by
                FROM chores c
                WHERE scope_id = ?
                ORDER BY name ASC
                """,
                (scope_id,),
            ).fetchall()
        return rows

    def _find_chore_case_insensitive(self, scope_id: str, name: str) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, name, reminder_schedule, reminder_at_minutes, one_shot, count_in_stats
                FROM chores
                WHERE scope_id = ? AND lower(name) = lower(?)
                """,
                (scope_id, name.strip()),
            ).fetchone()
        return row

    def delete_chore(self, scope_id: str, name: str) -> bool:
        row = self._find_chore_case_insensitive(scope_id, name)
        if row is None:
            return False
        chore_id = row["id"]
        with self._connect() as conn:
            conn.execute("DELETE FROM chore_logs WHERE chore_id = ?", (chore_id,))
            conn.execute("DELETE FROM chores WHERE id = ?", (chore_id,))
            conn.commit()
        return True

    def register_contact(self, number: str) -> None:
        normalized = number.strip()
        if not normalized:
            return
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO contacts (number) VALUES (?)",
                (normalized,),
            )
            conn.commit()

    def list_contacts(self) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT number FROM contacts ORDER BY id ASC").fetchall()
        return [row["number"] for row in rows]

    def register_group(self, group_id: str) -> None:
        normalized = group_id.strip()
        if not normalized:
            return
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO chat_groups (group_id)
                VALUES (?)
                """,
                (normalized,),
            )
            conn.commit()

    def list_groups(self) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT group_id FROM chat_groups ORDER BY id ASC"
            ).fetchall()
        return [row["group_id"] for row in rows]

    def get_language(self, scope_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT language FROM chat_settings WHERE scope_id = ?",
                (scope_id,),
            ).fetchone()
        if row is None:
            return "en"
        return row["language"]

    def set_language(self, scope_id: str, language: str) -> bool:
        normalized = language.strip().lower()
        if normalized not in {"en", "de"}:
            return False
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_settings (scope_id, language, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(scope_id) DO UPDATE SET
                    language = excluded.language,
                    updated_at = excluded.updated_at
                """,
                (scope_id, normalized),
            )
            conn.commit()
        return True

    def has_language(self, scope_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM chat_settings WHERE scope_id = ? LIMIT 1",
                (scope_id,),
            ).fetchone()
        return row is not None

    def get_timezone(self, scope_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT timezone FROM chat_settings WHERE scope_id = ?",
                (scope_id,),
            ).fetchone()
        if row is None or not row["timezone"]:
            return DEFAULT_TIMEZONE
        return normalize_timezone_name(row["timezone"]) or DEFAULT_TIMEZONE

    def set_timezone(self, scope_id: str, timezone_name: str) -> bool:
        normalized = normalize_timezone_name(timezone_name)
        if normalized is None:
            return False
        language = self.get_language(scope_id)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_settings (scope_id, language, timezone, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(scope_id) DO UPDATE SET
                    timezone = excluded.timezone,
                    updated_at = excluded.updated_at
                """,
                (scope_id, language, normalized),
            )
            conn.commit()
        return True

    def now_local(self, scope_id: str) -> datetime:
        return local_now(self.get_timezone(scope_id))

    def get_quiet_hours(self, scope_id: str) -> Tuple[int, int]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT quiet_start_minutes, quiet_end_minutes
                FROM chat_settings
                WHERE scope_id = ?
                """,
                (scope_id,),
            ).fetchone()
        if row is None:
            return 0, 8 * 60
        return row["quiet_start_minutes"], row["quiet_end_minutes"]

    def set_quiet_hours(self, scope_id: str, start_minutes: int, end_minutes: int) -> bool:
        if not 0 <= start_minutes < 24 * 60 or not 0 <= end_minutes < 24 * 60:
            return False
        language = self.get_language(scope_id)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_settings (
                    scope_id, language, quiet_start_minutes, quiet_end_minutes, updated_at
                )
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(scope_id) DO UPDATE SET
                    quiet_start_minutes = excluded.quiet_start_minutes,
                    quiet_end_minutes = excluded.quiet_end_minutes,
                    updated_at = excluded.updated_at
                """,
                (scope_id, language, start_minutes, end_minutes),
            )
            conn.commit()
        return True

    def get_auth_reminder_enabled(self, scope_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT auth_reminder_enabled
                FROM chat_settings
                WHERE scope_id = ?
                """,
                (scope_id,),
            ).fetchone()
        if row is None:
            return False
        return row["auth_reminder_enabled"] == 1

    def set_auth_reminder_enabled(self, scope_id: str, enabled: bool) -> bool:
        language = self.get_language(scope_id)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_settings (scope_id, language, auth_reminder_enabled, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(scope_id) DO UPDATE SET
                    auth_reminder_enabled = excluded.auth_reminder_enabled,
                    updated_at = excluded.updated_at
                """,
                (scope_id, language, 1 if enabled else 0),
            )
            if enabled:
                conn.execute(
                    """
                    INSERT INTO bot_state (key, value, updated_at)
                    VALUES (?, datetime('now'), datetime('now'))
                    ON CONFLICT(key) DO NOTHING
                    """,
                    (f"last_auth_reminder_at:{scope_id}",),
                )
            conn.commit()
        return True

    def is_quiet_time(self, scope_id: str, current_minutes: int) -> bool:
        start_minutes, end_minutes = self.get_quiet_hours(scope_id)
        if start_minutes == end_minutes:
            return False
        if start_minutes < end_minutes:
            return start_minutes <= current_minutes < end_minutes
        return current_minutes >= start_minutes or current_minutes < end_minutes

    def has_bot(self, scope_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT bot_id FROM chat_settings WHERE scope_id = ?",
                (scope_id,),
            ).fetchone()
        return row is not None and bool(row["bot_id"])

    def get_bot_id(self, scope_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT bot_id FROM chat_settings WHERE scope_id = ?",
                (scope_id,),
            ).fetchone()
        if row is None or not row["bot_id"]:
            return ""
        return row["bot_id"]

    def set_bot_id(self, scope_id: str, bot_id: str) -> bool:
        normalized = bot_id.strip()
        if not normalized:
            return False
        language = self.get_language(scope_id)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_settings (scope_id, language, bot_id, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(scope_id) DO UPDATE SET
                    bot_id = excluded.bot_id,
                    updated_at = excluded.updated_at
                """,
                (scope_id, language, normalized),
            )
            conn.commit()
        return True

    def is_group_ready(self, scope_id: str) -> bool:
        return self.has_language(scope_id) and self.has_bot(scope_id) and self.has_admins(scope_id)

    def has_admins(self, scope_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM chat_admins WHERE scope_id = ? LIMIT 1",
                (scope_id,),
            ).fetchone()
        return row is not None

    def is_admin(self, scope_id: str, sender: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM chat_admins
                WHERE scope_id = ? AND sender = ?
                LIMIT 1
                """,
                (scope_id, sender),
            ).fetchone()
        return row is not None

    def list_admins(self, scope_id: str) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT sender
                FROM chat_admins
                WHERE scope_id = ?
                ORDER BY id ASC
                """,
                (scope_id,),
            ).fetchall()
        return [row["sender"] for row in rows]

    def add_admin(self, scope_id: str, sender: str) -> bool:
        normalized = sender.strip()
        if not normalized:
            return False
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO chat_admins (scope_id, sender)
                VALUES (?, ?)
                """,
                (scope_id, normalized),
            )
            conn.commit()
        return True

    def remove_admin(self, scope_id: str, sender: str) -> bool:
        normalized = sender.strip()
        if not normalized:
            return False
        admins = self.list_admins(scope_id)
        if len(admins) <= 1 and normalized in admins:
            return False
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM chat_admins WHERE scope_id = ? AND sender = ?",
                (scope_id, normalized),
            )
            conn.commit()
        return cursor.rowcount > 0

    def get_admin_code(self, scope_id: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT code FROM admin_setup_codes WHERE scope_id = ?",
                (scope_id,),
            ).fetchone()
        if row is None:
            return None
        return row["code"]

    def set_admin_code(self, scope_id: str, code: str) -> bool:
        normalized = code.strip()
        if len(normalized) < 4 or any(ch.isspace() for ch in normalized):
            return False
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO admin_setup_codes (scope_id, code)
                VALUES (?, ?)
                ON CONFLICT(scope_id) DO UPDATE SET
                    code = excluded.code,
                    created_at = datetime('now')
                """,
                (scope_id, normalized),
            )
            conn.commit()
        return True

    def validate_admin_code(self, scope_id: str, code: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM admin_setup_codes
                WHERE scope_id = ? AND code = ?
                """,
                (scope_id, code.strip()),
            ).fetchone()
        return row is not None

    def clear_admin_code(self, scope_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM admin_setup_codes WHERE scope_id = ?", (scope_id,))
            conn.commit()

    def upsert_pending_chore_add(
        self,
        scope_id: str,
        name: str,
        schedule: dict,
        requested_by: str,
        ttl_minutes: int = 10,
    ) -> None:
        reminder_interval_minutes = schedule_to_minutes(schedule)
        reminder_schedule = schedule_to_storage(schedule)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_chore_adds (
                    scope_id, name, reminder_interval_minutes, reminder_schedule, requested_by, expires_at
                )
                VALUES (?, ?, ?, ?, ?, datetime('now', '+' || ? || ' minutes'))
                ON CONFLICT(scope_id) DO UPDATE SET
                    name = excluded.name,
                    reminder_interval_minutes = excluded.reminder_interval_minutes,
                    reminder_schedule = excluded.reminder_schedule,
                    requested_by = excluded.requested_by,
                    expires_at = excluded.expires_at,
                    created_at = datetime('now')
                """,
                (scope_id, name.strip(), reminder_interval_minutes, reminder_schedule, requested_by, ttl_minutes),
            )
            conn.commit()

    def get_pending_chore_add(self, scope_id: str, requested_by: str) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT name, reminder_interval_minutes, reminder_schedule
                FROM pending_chore_adds
                WHERE scope_id = ?
                  AND requested_by = ?
                  AND datetime(expires_at) >= datetime('now')
                """,
                (scope_id, requested_by),
            ).fetchone()
        return row

    def clear_pending_chore_add(self, scope_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM pending_chore_adds WHERE scope_id = ?", (scope_id,))
            conn.commit()

    def start_pending_chore_setup(
        self,
        scope_id: str,
        requested_by: str,
        ttl_minutes: int | None = None,
        one_shot: bool = False,
    ) -> None:
        ttl = ttl_minutes if ttl_minutes is not None else self._dialogue_ttl()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_chore_setups (
                    scope_id, requested_by, step, expires_at, last_activity_at, previous_step, one_shot, count_in_stats
                )
                VALUES (?, ?, 'name', datetime('now', '+' || ? || ' minutes'), datetime('now'), '', ?, NULL)
                ON CONFLICT(scope_id, requested_by) DO UPDATE SET
                    step = 'name',
                    name = '',
                    reminder_schedule = '',
                    reminder_at_minutes = NULL,
                    one_shot = excluded.one_shot,
                    count_in_stats = NULL,
                    expires_at = excluded.expires_at,
                    last_activity_at = datetime('now'),
                    previous_step = '',
                    created_at = datetime('now')
                """,
                (scope_id, requested_by, ttl, 1 if one_shot else 0),
            )
            conn.commit()

    def get_pending_chore_setup(self, scope_id: str, requested_by: str) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT step, name, reminder_schedule, reminder_at_minutes, previous_step,
                       expires_at, last_activity_at, one_shot, count_in_stats
                FROM pending_chore_setups
                WHERE scope_id = ? AND requested_by = ?
                """,
                (scope_id, requested_by),
            ).fetchone()
            return self._prepare_dialogue_row(conn, "pending_chore_setups", scope_id, requested_by, row)

    def update_pending_chore_setup(
        self,
        scope_id: str,
        requested_by: str,
        step: str,
        name: str,
        reminder_schedule: str,
        reminder_at_minutes: int | None = None,
        count_in_stats: int | None = None,
        ttl_minutes: int | None = None,
    ) -> None:
        ttl = ttl_minutes if ttl_minutes is not None else self._dialogue_ttl()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE pending_chore_setups
                SET step = ?,
                    name = ?,
                    reminder_schedule = ?,
                    reminder_at_minutes = ?,
                    count_in_stats = ?,
                    expires_at = datetime('now', '+' || ? || ' minutes'),
                    last_activity_at = datetime('now')
                WHERE scope_id = ? AND requested_by = ?
                """,
                (
                    step,
                    name,
                    reminder_schedule,
                    reminder_at_minutes,
                    count_in_stats,
                    ttl,
                    scope_id,
                    requested_by,
                ),
            )
            conn.commit()

    def clear_pending_chore_setup(self, scope_id: str, requested_by: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM pending_chore_setups WHERE scope_id = ? AND requested_by = ?",
                (scope_id, requested_by),
            )
            conn.commit()

    def start_pending_chore_edit(
        self,
        scope_id: str,
        requested_by: str,
        chore_name: str,
        ttl_minutes: int | None = None,
    ) -> None:
        ttl = ttl_minutes if ttl_minutes is not None else self._dialogue_ttl()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_chore_edits (
                    scope_id, requested_by, chore_name, field, step, expires_at, last_activity_at, previous_step
                )
                VALUES (?, ?, ?, '', 'choose', datetime('now', '+' || ? || ' minutes'), datetime('now'), '')
                ON CONFLICT(scope_id, requested_by) DO UPDATE SET
                    chore_name = excluded.chore_name,
                    field = '',
                    step = 'choose',
                    expires_at = excluded.expires_at,
                    last_activity_at = datetime('now'),
                    previous_step = '',
                    created_at = datetime('now')
                """,
                (scope_id, requested_by, chore_name.strip(), ttl),
            )
            conn.commit()

    def get_pending_chore_edit(self, scope_id: str, requested_by: str) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT chore_name, field, step, previous_step, expires_at, last_activity_at
                FROM pending_chore_edits
                WHERE scope_id = ? AND requested_by = ?
                """,
                (scope_id, requested_by),
            ).fetchone()
            return self._prepare_dialogue_row(conn, "pending_chore_edits", scope_id, requested_by, row)

    def update_pending_chore_edit(
        self,
        scope_id: str,
        requested_by: str,
        field: str,
        ttl_minutes: int | None = None,
        step: str | None = None,
    ) -> None:
        ttl = ttl_minutes if ttl_minutes is not None else self._dialogue_ttl()
        next_step = step if step is not None else (field or "choose")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE pending_chore_edits
                SET field = ?,
                    step = ?,
                    expires_at = datetime('now', '+' || ? || ' minutes'),
                    last_activity_at = datetime('now')
                WHERE scope_id = ? AND requested_by = ?
                """,
                (field, next_step, ttl, scope_id, requested_by),
            )
            conn.commit()

    def clear_pending_chore_edit(self, scope_id: str, requested_by: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM pending_chore_edits WHERE scope_id = ? AND requested_by = ?",
                (scope_id, requested_by),
            )
            conn.commit()

    def rename_chore(self, scope_id: str, old_name: str, new_name: str) -> Tuple[bool, str]:
        old_row = self._find_chore_case_insensitive(scope_id, old_name)
        if old_row is None:
            return False, f"Chore '{old_name}' does not exist."
        new_name = new_name.strip()
        if not new_name:
            return False, "New chore name cannot be empty."

        try:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE chores SET name = ? WHERE id = ?",
                    (new_name, old_row["id"]),
                )
                conn.commit()
            return True, f"Renamed '{old_row['name']}' to '{new_name}'."
        except sqlite3.IntegrityError:
            return False, f"Chore '{new_name}' already exists."

    def set_chore_confirmation(self, scope_id: str, name: str, requires_confirmation: bool) -> bool:
        row = self._find_chore_case_insensitive(scope_id, name)
        if row is None:
            return False
        with self._connect() as conn:
            conn.execute(
                "UPDATE chores SET requires_confirmation = ? WHERE id = ?",
                (1 if requires_confirmation else 0, row["id"]),
            )
            conn.commit()
        return True

    def set_chore_reminder_time(self, scope_id: str, name: str, reminder_at_minutes: int | None) -> bool:
        row = self._find_chore_case_insensitive(scope_id, name)
        if row is None:
            return False
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE chores
                SET reminder_at_minutes = ?, last_reminded_at = NULL
                WHERE id = ?
                """,
                (reminder_at_minutes, row["id"]),
            )
            conn.commit()
        return True

    def set_chore_schedule(self, scope_id: str, name: str, schedule: dict) -> bool:
        row = self._find_chore_case_insensitive(scope_id, name)
        if row is None or not schedule:
            return False
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE chores
                SET reminder_interval_minutes = ?,
                    reminder_schedule = ?,
                    one_shot = ?,
                    last_reminded_at = NULL
                WHERE id = ?
                """,
                (
                    schedule_to_minutes(schedule),
                    schedule_to_storage(schedule),
                    1 if is_one_shot_schedule(schedule) else 0,
                    row["id"],
                ),
            )
            conn.commit()
        return True

    def set_chore_repeat_reminder(self, scope_id: str, name: str, schedule: dict) -> bool:
        row = self._find_chore_case_insensitive(scope_id, name)
        if row is None or not schedule:
            return False
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE chores
                SET repeat_reminder_minutes = ?, repeat_reminder_schedule = ?
                WHERE id = ?
                """,
                (schedule_to_minutes(schedule), schedule_to_storage(schedule), row["id"]),
            )
            conn.commit()
        return True

    def has_display_name(self, scope_id: str, sender: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM member_names WHERE scope_id = ? AND sender = ?",
                (scope_id, sender.strip()),
            ).fetchone()
        return row is not None

    def display_name(self, scope_id: str, sender: str) -> str:
        normalized = sender.strip()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT display_name FROM member_names WHERE scope_id = ? AND sender = ?",
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
                INSERT INTO member_names (scope_id, sender, display_name)
                VALUES (?, ?, ?)
                ON CONFLICT(scope_id, sender) DO UPDATE SET
                    display_name = excluded.display_name,
                    updated_at = datetime('now')
                """,
                (scope_id, normalized_sender, normalized_name),
            )
            conn.commit()
        return True

    def sender_by_display_name(self, scope_id: str, display_name: str) -> Optional[str]:
        normalized_name = display_name.strip()
        if not normalized_name:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT sender
                FROM member_names
                WHERE scope_id = ? AND LOWER(display_name) = LOWER(?)
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (scope_id, normalized_name),
            ).fetchone()
        if row is None:
            return None
        return row["sender"]

    def start_pending_member_name(self, scope_id: str, requested_by: str, chore_name: str, ttl_minutes: int | None = None) -> None:
        ttl = ttl_minutes if ttl_minutes is not None else self._dialogue_ttl()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_member_names (
                    scope_id, requested_by, chore_name, step, expires_at, last_activity_at, previous_step
                )
                VALUES (?, ?, ?, 'name', datetime('now', '+' || ? || ' minutes'), datetime('now'), '')
                ON CONFLICT(scope_id, requested_by) DO UPDATE SET
                    chore_name = excluded.chore_name,
                    step = 'name',
                    expires_at = excluded.expires_at,
                    last_activity_at = datetime('now'),
                    previous_step = '',
                    created_at = datetime('now')
                """,
                (scope_id, requested_by, chore_name.strip(), ttl),
            )
            conn.commit()

    def get_pending_member_name(self, scope_id: str, requested_by: str) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT chore_name, step, previous_step, expires_at, last_activity_at
                FROM pending_member_names
                WHERE scope_id = ? AND requested_by = ?
                """,
                (scope_id, requested_by),
            ).fetchone()
            prepared = self._prepare_dialogue_row(conn, "pending_member_names", scope_id, requested_by, row)
            if prepared is None:
                return None
            return conn.execute(
                """
                SELECT chore_name, step, previous_step
                FROM pending_member_names
                WHERE scope_id = ? AND requested_by = ?
                """,
                (scope_id, requested_by),
            ).fetchone()

    def clear_pending_member_name(self, scope_id: str, requested_by: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM pending_member_names WHERE scope_id = ? AND requested_by = ?",
                (scope_id, requested_by),
            )
            conn.commit()

    def mark_done(self, scope_id: str, chore_name: str, sender: str) -> Tuple[bool, str]:
        row = self._find_chore_case_insensitive(scope_id, chore_name)
        if row is None:
            return False, (
                f"Chore '{chore_name}' is not in allowed chores. "
                "Use 'chores' to see available items."
            )

        with self._connect() as conn:
            count_in_stats = int(row["count_in_stats"] if "count_in_stats" in row.keys() else 1)
            one_shot = int(row["one_shot"] or 0)
            conn.execute(
                """
                INSERT INTO chore_logs (chore_id, sender, scope_id, chore_name, one_shot, count_in_stats)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (row["id"], sender, scope_id, row["name"], one_shot, count_in_stats),
            )
            if one_shot == 1:
                conn.execute("DELETE FROM chores WHERE id = ?", (row["id"],))
            else:
                conn.execute(
                    "UPDATE chores SET last_reminded_at = NULL, vacation_delay_seconds = 0 WHERE id = ?",
                    (row["id"],),
                )
            done_at = conn.execute("SELECT datetime('now') AS done_at").fetchone()["done_at"]
            conn.commit()
        if one_shot == 1:
            if count_in_stats == 1:
                prefix = "One-shot saved: "
            else:
                prefix = "One-shot no-stats saved: "
        else:
            prefix = "Saved: "
        return True, f"{prefix}{row['name']} at {done_at} UTC by {self.display_name(scope_id, sender)}."

    def undo_last_done(self, scope_id: str, chore_name: str) -> Tuple[bool, str]:
        row = self._find_chore_case_insensitive(scope_id, chore_name)
        if row is None:
            return False, f"Chore '{chore_name}' is not in allowed chores."
        with self._connect() as conn:
            log_row = conn.execute(
                """
                SELECT id, done_at
                FROM chore_logs
                WHERE chore_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (row["id"],),
            ).fetchone()
            if log_row is None:
                return False, f"No completion to undo for '{row['name']}'."
            conn.execute("DELETE FROM chore_logs WHERE id = ?", (log_row["id"],))
            conn.commit()
        return True, f"Undid last completion for '{row['name']}' from {log_row['done_at']} UTC."

    def recent_logs(self, scope_id: str, limit: int = 20) -> List[sqlite3.Row]:
        limit = max(1, min(limit, 100))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT COALESCE(NULLIF(l.chore_name, ''), c.name) AS chore_name, l.sender, l.done_at
                FROM chore_logs l
                LEFT JOIN chores c ON c.id = l.chore_id
                WHERE COALESCE(NULLIF(l.scope_id, ''), c.scope_id, '') = ?
                ORDER BY l.id DESC
                LIMIT ?
                """,
                (scope_id, limit),
            ).fetchall()
        return rows

    def action_stats(self, scope_id: str) -> dict:
        with self._connect() as conn:
            chore_count = conn.execute(
                "SELECT COUNT(*) AS count FROM chores WHERE scope_id = ?",
                (scope_id,),
            ).fetchone()["count"]
            done_count = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM chore_logs l
                LEFT JOIN chores c ON c.id = l.chore_id
                WHERE COALESCE(NULLIF(l.scope_id, ''), c.scope_id, '') = ?
                  AND COALESCE(l.count_in_stats, 1) = 1
                """,
                (scope_id,),
            ).fetchone()["count"]
            action_rows = conn.execute(
                """
                SELECT action_type, COUNT(*) AS count
                FROM action_logs
                WHERE scope_id = ?
                GROUP BY action_type
                ORDER BY action_type
                """,
                (scope_id,),
            ).fetchall()
            recent_action_rows = conn.execute(
                """
                SELECT action_type, chore_name, sender, created_at
                FROM action_logs
                WHERE scope_id = ?
                ORDER BY id DESC
                LIMIT 5
                """,
                (scope_id,),
            ).fetchall()
        by_chore_counts: dict[str, int] = {}
        for row in self._completion_log_rows(scope_id):
            bucket = self._stats_bucket(row)
            by_chore_counts[bucket] = by_chore_counts.get(bucket, 0) + 1
        top_done = [
            {"name": name, "count": count}
            for name, count in sorted(by_chore_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        ]
        return {
            "chore_count": chore_count,
            "done_count": done_count,
            "actions": {row["action_type"]: row["count"] for row in action_rows},
            "top_done": top_done,
            "recent_actions": [dict(row) for row in recent_action_rows],
        }

    def active_vacation_pause_seconds(self, scope_id: str) -> int:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT starts_at, ends_at
                FROM member_vacations
                WHERE scope_id = ?
                  AND status IN ('prep', 'active')
                  AND datetime(ends_at) > datetime('now')
                """,
                (scope_id,),
            ).fetchall()
        total = 0
        for row in rows:
            start = parse_db_datetime(row["starts_at"])
            end = parse_db_datetime(row["ends_at"])
            if start is None or end is None or end <= start:
                continue
            total += int((end - start).total_seconds())
        return total

    def apply_vacation_schedule_shift(self, scope_id: str, starts_at: str, ends_at: str) -> None:
        start = parse_db_datetime(starts_at)
        end = parse_db_datetime(ends_at)
        if start is None or end is None or end <= start:
            return
        pause_seconds = int((end - start).total_seconds())
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE chores
                SET vacation_delay_seconds = vacation_delay_seconds + ?
                WHERE scope_id = ?
                """,
                (pause_seconds, scope_id),
            )
            conn.commit()

    def due_reminders(self) -> List[sqlite3.Row]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.scope_id, c.name, c.reminder_interval_minutes, c.reminder_schedule,
                       c.requires_confirmation, c.repeat_reminder_minutes, c.repeat_reminder_schedule,
                       c.created_at, c.last_reminded_at, c.reminder_at_minutes, c.vacation_delay_seconds,
                       (SELECT MAX(l.done_at) FROM chore_logs l WHERE l.chore_id = c.id) AS last_done_at
                FROM chores c
                WHERE (c.reminder_interval_minutes > 0 OR c.reminder_schedule != '')
                  AND c.reminder_schedule != 'none'
                """
            ).fetchall()
        due = []
        now = datetime.utcnow()
        active_pause_cache: dict[str, int] = {}
        timezone_cache: dict[str, str] = {}
        for row in rows:
            schedule = schedule_from_storage(row["reminder_schedule"], row["reminder_interval_minutes"])
            if schedule is None:
                continue
            scope_id = row["scope_id"]
            if scope_id not in active_pause_cache:
                active_pause_cache[scope_id] = self.active_vacation_pause_seconds(scope_id)
            if scope_id not in timezone_cache:
                timezone_cache[scope_id] = self.get_timezone(scope_id)
            pause_seconds = row["vacation_delay_seconds"] + active_pause_cache[scope_id]
            requires_confirmation = row["requires_confirmation"] == 1
            base_timestamp = row["last_done_at"] or row["created_at"]
            base_time = parse_db_datetime(base_timestamp)
            if pause_seconds > 0:
                base_time = base_time + timedelta(seconds=pause_seconds)
            reminder_at_minutes = row["reminder_at_minutes"]
            tz_name = timezone_cache[scope_id]
            next_due = next_due_at(base_time, schedule, reminder_at_minutes, tz_name=tz_name)
            if next_due > now:
                continue
            if row["last_reminded_at"]:
                last_reminded_at = parse_db_datetime(row["last_reminded_at"])
                if last_reminded_at >= base_time:
                    if requires_confirmation or is_one_shot_schedule(schedule):
                        throttle_schedule = schedule_from_storage(
                            row["repeat_reminder_schedule"],
                            row["repeat_reminder_minutes"],
                        )
                    else:
                        throttle_schedule = schedule
                    if throttle_schedule is None or next_due_at(
                        last_reminded_at, throttle_schedule, tz_name=tz_name
                    ) > now:
                        continue
            due.append(row)
        return due

    def mark_reminder_sent(self, chore_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE chores SET last_reminded_at = datetime('now') WHERE id = ?",
                (chore_id,),
            )
            conn.commit()

    def auth_reminder_due(self, scope_id: str, interval_days: int = 25) -> bool:
        if not self.get_auth_reminder_enabled(scope_id):
            return False
        state_key = f"last_auth_reminder_at:{scope_id}"
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM bot_state WHERE key = ?",
                (state_key,),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO bot_state (key, value, updated_at)
                    VALUES (?, datetime('now'), datetime('now'))
                    """,
                    (state_key,),
                )
                conn.commit()
                return False
            due_row = conn.execute(
                """
                SELECT datetime(?) <= datetime('now', '-' || ? || ' days') AS is_due
                """,
                (row["value"], interval_days),
            ).fetchone()
        return due_row["is_due"] == 1

    def mark_auth_reminder_sent(self, scope_id: str) -> None:
        state_key = f"last_auth_reminder_at:{scope_id}"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO bot_state (key, value, updated_at)
                VALUES (?, datetime('now'), datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (state_key,),
            )
            conn.commit()

    def reset_scope(self, scope_id: str) -> None:
        with self._connect() as conn:
            chore_ids = conn.execute(
                "SELECT id FROM chores WHERE scope_id = ?",
                (scope_id,),
            ).fetchall()
            for row in chore_ids:
                conn.execute("DELETE FROM chore_logs WHERE chore_id = ?", (row["id"],))
            conn.execute("DELETE FROM chore_logs WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM chores WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM reset_requests WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM chat_settings WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM chat_admins WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM admin_setup_codes WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM pending_chore_adds WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM pending_chore_setups WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM pending_chore_edits WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM pending_member_names WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM member_names WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM action_logs WHERE scope_id = ?", (scope_id,))
            vacation_ids = conn.execute(
                "SELECT id FROM member_vacations WHERE scope_id = ?",
                (scope_id,),
            ).fetchall()
            for row in vacation_ids:
                conn.execute("DELETE FROM vacation_prep_done WHERE vacation_id = ?", (row["id"],))
            conn.execute("DELETE FROM member_vacations WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM vacation_chores WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM pending_vacation_setups WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM pending_vacation_chore_adds WHERE scope_id = ?", (scope_id,))
            conn.commit()

    def upsert_reset_request(self, scope_id: str, requested_by: str, token: str, ttl_minutes: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reset_requests (scope_id, requested_by, token, expires_at)
                VALUES (?, ?, ?, datetime('now', '+' || ? || ' minutes'))
                ON CONFLICT(scope_id) DO UPDATE SET
                    requested_by = excluded.requested_by,
                    token = excluded.token,
                    expires_at = excluded.expires_at
                """,
                (scope_id, requested_by, token, ttl_minutes),
            )
            conn.commit()

    def validate_reset_request(self, scope_id: str, requested_by: str, token: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT scope_id
                FROM reset_requests
                WHERE scope_id = ?
                  AND requested_by = ?
                  AND token = ?
                  AND datetime(expires_at) >= datetime('now')
                """,
                (scope_id, requested_by, token),
            ).fetchone()
        return row is not None

    def clear_reset_request(self, scope_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM reset_requests WHERE scope_id = ?", (scope_id,))
            conn.commit()

    def list_vacation_chores(self, scope_id: str) -> List[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, name
                FROM vacation_chores
                WHERE scope_id = ?
                ORDER BY name COLLATE NOCASE
                """,
                (scope_id,),
            ).fetchall()

    def add_vacation_chore(self, scope_id: str, name: str) -> bool:
        normalized = name.strip()
        if not normalized:
            return False
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO vacation_chores (scope_id, name) VALUES (?, ?)",
                    (scope_id, normalized),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def delete_vacation_chore(self, scope_id: str, name: str) -> bool:
        with self._connect() as conn:
            row = self._find_vacation_chore(conn, scope_id, name)
            if row is None:
                return False
            conn.execute("DELETE FROM vacation_chores WHERE id = ?", (row["id"],))
            conn.commit()
        return True

    def _find_vacation_chore(self, conn: sqlite3.Connection, scope_id: str, name: str) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT id, name
            FROM vacation_chores
            WHERE scope_id = ? AND lower(name) = lower(?)
            """,
            (scope_id, name.strip()),
        ).fetchone()

    def get_member_vacation(self, scope_id: str, sender: str) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, sender, starts_at, ends_at, status
                FROM member_vacations
                WHERE scope_id = ?
                  AND sender = ?
                  AND status IN ('scheduled', 'prep', 'active')
                ORDER BY datetime(starts_at) DESC
                LIMIT 1
                """,
                (scope_id, sender),
            ).fetchone()

    def is_reminders_paused(self, scope_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM member_vacations
                WHERE scope_id = ?
                  AND status IN ('prep', 'active')
                  AND datetime(ends_at) > datetime('now')
                LIMIT 1
                """,
                (scope_id,),
            ).fetchone()
        return row is not None

    def create_member_vacation(
        self,
        scope_id: str,
        sender: str,
        delay: timedelta,
        duration: timedelta,
    ) -> sqlite3.Row:
        starts_at = datetime.utcnow() + delay
        ends_at = starts_at + duration
        status = "scheduled" if delay.total_seconds() > 0 else None
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE member_vacations
                SET status = 'cancelled', ended_at = datetime('now')
                WHERE scope_id = ? AND sender = ? AND status IN ('scheduled', 'prep', 'active')
                """,
                (scope_id, sender),
            )
            if status is None:
                prep_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM vacation_chores WHERE scope_id = ?",
                    (scope_id,),
                ).fetchone()["count"]
                status = "prep" if prep_count > 0 else "active"
            cursor = conn.execute(
                """
                INSERT INTO member_vacations (scope_id, sender, starts_at, ends_at, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    scope_id,
                    sender,
                    starts_at.strftime("%Y-%m-%d %H:%M:%S"),
                    ends_at.strftime("%Y-%m-%d %H:%M:%S"),
                    status,
                ),
            )
            vacation_id = cursor.lastrowid
            conn.commit()
            return conn.execute(
                "SELECT id, sender, starts_at, ends_at, status FROM member_vacations WHERE id = ?",
                (vacation_id,),
            ).fetchone()

    def cancel_member_vacation(self, scope_id: str, sender: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM member_vacations
                WHERE scope_id = ? AND sender = ? AND status IN ('scheduled', 'prep', 'active')
                LIMIT 1
                """,
                (scope_id, sender),
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                """
                UPDATE member_vacations
                SET status = 'cancelled', ended_at = datetime('now')
                WHERE id = ?
                """,
                (row["id"],),
            )
            conn.commit()
        return True

    def list_vacation_prep_pending(self, vacation_id: int) -> List[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT vc.id, vc.name
                FROM vacation_chores vc
                JOIN member_vacations mv ON mv.scope_id = vc.scope_id
                LEFT JOIN vacation_prep_done vpd
                    ON vpd.vacation_id = mv.id AND vpd.vacation_chore_id = vc.id
                WHERE mv.id = ? AND vpd.vacation_chore_id IS NULL
                ORDER BY vc.name COLLATE NOCASE
                """,
                (vacation_id,),
            ).fetchall()

    def mark_vacation_prep_done(self, scope_id: str, vacation_id: int, chore_name: str, sender: str) -> bool:
        with self._connect() as conn:
            chore = self._find_vacation_chore(conn, scope_id, chore_name)
            if chore is None:
                return False
            pending = conn.execute(
                """
                SELECT 1
                FROM member_vacations
                WHERE id = ? AND scope_id = ? AND status = 'prep'
                """,
                (vacation_id, scope_id),
            ).fetchone()
            if pending is None:
                return False
            conn.execute(
                """
                INSERT OR IGNORE INTO vacation_prep_done (vacation_id, vacation_chore_id, sender)
                VALUES (?, ?, ?)
                """,
                (vacation_id, chore["id"], sender),
            )
            remaining = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM vacation_chores vc
                JOIN member_vacations mv ON mv.scope_id = vc.scope_id
                LEFT JOIN vacation_prep_done vpd
                    ON vpd.vacation_id = mv.id AND vpd.vacation_chore_id = vc.id
                WHERE mv.id = ? AND vpd.vacation_chore_id IS NULL
                """,
                (vacation_id,),
            ).fetchone()["count"]
            if remaining == 0:
                conn.execute(
                    "UPDATE member_vacations SET status = 'active' WHERE id = ?",
                    (vacation_id,),
                )
            conn.commit()
            return True

    def skip_vacation_prep(self, scope_id: str, vacation_id: int, sender: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM member_vacations
                WHERE id = ? AND scope_id = ? AND sender = ? AND status = 'prep'
                """,
                (vacation_id, scope_id, sender),
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                "UPDATE member_vacations SET status = 'active' WHERE id = ?",
                (vacation_id,),
            )
            conn.commit()
        return True

    def process_vacation_transitions(self) -> List[dict]:
        events: List[dict] = []
        with self._connect() as conn:
            scheduled_rows = conn.execute(
                """
                SELECT id, scope_id, sender, starts_at, ends_at
                FROM member_vacations
                WHERE status = 'scheduled' AND datetime(starts_at) <= datetime('now')
                """
            ).fetchall()
            for row in scheduled_rows:
                prep_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM vacation_chores WHERE scope_id = ?",
                    (row["scope_id"],),
                ).fetchone()["count"]
                new_status = "prep" if prep_count > 0 else "active"
                conn.execute(
                    "UPDATE member_vacations SET status = ? WHERE id = ?",
                    (new_status, row["id"]),
                )
                events.append(
                    {
                        "type": "started",
                        "scope_id": row["scope_id"],
                        "sender": row["sender"],
                        "vacation_id": row["id"],
                        "status": new_status,
                        "ends_at": row["ends_at"],
                    }
                )

            ended_rows = conn.execute(
                """
                SELECT id, scope_id, sender, starts_at, ends_at
                FROM member_vacations
                WHERE status IN ('prep', 'active') AND datetime(ends_at) <= datetime('now')
                """
            ).fetchall()
            for row in ended_rows:
                start = parse_db_datetime(row["starts_at"])
                end = parse_db_datetime(row["ends_at"])
                if start is not None and end is not None and end > start:
                    pause_seconds = int((end - start).total_seconds())
                    conn.execute(
                        """
                        UPDATE chores
                        SET vacation_delay_seconds = vacation_delay_seconds + ?
                        WHERE scope_id = ?
                        """,
                        (pause_seconds, row["scope_id"]),
                    )
                conn.execute(
                    """
                    UPDATE member_vacations
                    SET status = 'completed', ended_at = datetime('now')
                    WHERE id = ?
                    """,
                    (row["id"],),
                )
                events.append(
                    {
                        "type": "ended",
                        "scope_id": row["scope_id"],
                        "sender": row["sender"],
                        "vacation_id": row["id"],
                    }
                )
            conn.commit()
        return events

    def start_pending_vacation_setup(self, scope_id: str, requested_by: str, ttl_minutes: int | None = None) -> None:
        ttl = ttl_minutes if ttl_minutes is not None else self._dialogue_ttl()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_vacation_setups (
                    scope_id, requested_by, step, delay_days, expires_at, last_activity_at, previous_step
                )
                VALUES (?, ?, 'when', 0, datetime('now', '+' || ? || ' minutes'), datetime('now'), '')
                ON CONFLICT(scope_id, requested_by) DO UPDATE SET
                    step = 'when',
                    delay_days = 0,
                    expires_at = excluded.expires_at,
                    last_activity_at = datetime('now'),
                    previous_step = '',
                    created_at = datetime('now')
                """,
                (scope_id, requested_by, ttl),
            )
            conn.commit()

    def get_pending_vacation_setup(self, scope_id: str, requested_by: str) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT step, delay_days, previous_step, expires_at, last_activity_at
                FROM pending_vacation_setups
                WHERE scope_id = ? AND requested_by = ?
                """,
                (scope_id, requested_by),
            ).fetchone()
            return self._prepare_dialogue_row(conn, "pending_vacation_setups", scope_id, requested_by, row)

    def update_pending_vacation_setup(
        self,
        scope_id: str,
        requested_by: str,
        step: str,
        delay_days: int = 0,
        ttl_minutes: int | None = None,
    ) -> None:
        ttl = ttl_minutes if ttl_minutes is not None else self._dialogue_ttl()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE pending_vacation_setups
                SET step = ?,
                    delay_days = ?,
                    expires_at = datetime('now', '+' || ? || ' minutes'),
                    last_activity_at = datetime('now')
                WHERE scope_id = ? AND requested_by = ?
                """,
                (step, delay_days, ttl, scope_id, requested_by),
            )
            conn.commit()

    def clear_pending_vacation_setup(self, scope_id: str, requested_by: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM pending_vacation_setups WHERE scope_id = ? AND requested_by = ?",
                (scope_id, requested_by),
            )
            conn.commit()

    def start_pending_vacation_chore_add(self, scope_id: str, requested_by: str, ttl_minutes: int | None = None) -> None:
        ttl = ttl_minutes if ttl_minutes is not None else self._dialogue_ttl()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_vacation_chore_adds (
                    scope_id, requested_by, step, expires_at, last_activity_at, previous_step
                )
                VALUES (?, ?, 'name', datetime('now', '+' || ? || ' minutes'), datetime('now'), '')
                ON CONFLICT(scope_id, requested_by) DO UPDATE SET
                    step = 'name',
                    expires_at = excluded.expires_at,
                    last_activity_at = datetime('now'),
                    previous_step = '',
                    created_at = datetime('now')
                """,
                (scope_id, requested_by, ttl),
            )
            conn.commit()

    def get_pending_vacation_chore_add(self, scope_id: str, requested_by: str) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT step, previous_step, expires_at, last_activity_at
                FROM pending_vacation_chore_adds
                WHERE scope_id = ? AND requested_by = ?
                """,
                (scope_id, requested_by),
            ).fetchone()
            return self._prepare_dialogue_row(conn, "pending_vacation_chore_adds", scope_id, requested_by, row)

    def clear_pending_vacation_chore_add(self, scope_id: str, requested_by: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM pending_vacation_chore_adds WHERE scope_id = ? AND requested_by = ?",
                (scope_id, requested_by),
            )
            conn.commit()
