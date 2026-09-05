from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, List, Optional

from scrape_types import NOTIFY_CHANGE_FIELDS, TRACKED_FIELDS, ScrapeResult
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

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {row["name"] for row in columns}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_settings (
                    scope_id TEXT PRIMARY KEY,
                    language TEXT NOT NULL DEFAULT 'en',
                    drive_origin_name TEXT NOT NULL DEFAULT 'Stuttgart',
                    drive_origin_lat REAL NOT NULL DEFAULT 48.7758,
                    drive_origin_lon REAL NOT NULL DEFAULT 9.1829,
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
                CREATE TABLE IF NOT EXISTS custom_hosts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    host_pattern TEXT NOT NULL,
                    adapter_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(scope_id, host_pattern)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    url TEXT NOT NULL,
                    adapter_id TEXT NOT NULL,
                    check_in TEXT NOT NULL,
                    check_out TEXT NOT NULL,
                    guests INTEGER NOT NULL DEFAULT 2,
                    available INTEGER,
                    price_per_night REAL,
                    total_price REAL,
                    currency TEXT NOT NULL DEFAULT 'EUR',
                    title TEXT,
                    location_name TEXT,
                    lat REAL,
                    lon REAL,
                    drive_minutes INTEGER,
                    drive_km REAL,
                    guests_max INTEGER,
                    bedrooms INTEGER,
                    bathrooms REAL,
                    rating REAL,
                    review_count INTEGER,
                    min_nights INTEGER,
                    cleaning_fee REAL,
                    pets_allowed INTEGER,
                    property_type TEXT,
                    scrape_error TEXT,
                    last_checked_at TEXT,
                    last_changed_at TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(scope_id, label)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS listing_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    listing_id INTEGER NOT NULL,
                    changed_at TEXT NOT NULL DEFAULT (datetime('now')),
                    snapshot_json TEXT NOT NULL,
                    FOREIGN KEY(listing_id) REFERENCES listings(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_listing_adds (
                    scope_id TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    step TEXT NOT NULL,
                    url TEXT NOT NULL DEFAULT '',
                    label TEXT NOT NULL DEFAULT '',
                    check_in TEXT NOT NULL DEFAULT '',
                    check_out TEXT NOT NULL DEFAULT '',
                    guests INTEGER NOT NULL DEFAULT 2,
                    adapter_id TEXT NOT NULL DEFAULT '',
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY(scope_id, requested_by)
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
            self._ensure_column(conn, "listings", "added_by", "TEXT NOT NULL DEFAULT ''")
            self._ensure_dialogue_columns(conn, "pending_listing_adds")
            conn.commit()

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
            added = conn.execute(
                "SELECT COUNT(*) AS c FROM listings WHERE scope_id = ? AND added_by = ?",
                (scope_id, sender),
            ).fetchone()["c"]
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM listings WHERE scope_id = ?",
                (scope_id,),
            ).fetchone()["c"]
        return {"added_count": added, "group_total": total}

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

    def list_groups(self) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT group_id FROM chat_groups ORDER BY id ASC").fetchall()
        return [row["group_id"] for row in rows]

    def list_contacts(self) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT number FROM contacts ORDER BY id ASC").fetchall()
        return [row["number"] for row in rows]

    def get_language(self, scope_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT language FROM chat_settings WHERE scope_id = ?", (scope_id,)).fetchone()
        return row["language"] if row else "en"

    def set_language(self, scope_id: str, language: str) -> bool:
        if language not in {"en", "de"}:
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
                (scope_id, language),
            )
            conn.commit()
        return True

    def has_language(self, scope_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM chat_settings WHERE scope_id = ? LIMIT 1", (scope_id,)).fetchone()
        return row is not None

    def has_bot(self, scope_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT bot_id FROM chat_settings WHERE scope_id = ?", (scope_id,)).fetchone()
        return row is not None and bool(row["bot_id"])

    def get_bot_id(self, scope_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT bot_id FROM chat_settings WHERE scope_id = ?", (scope_id,)).fetchone()
        return row["bot_id"] if row and row["bot_id"] else ""

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

    def has_admins(self, scope_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM chat_admins WHERE scope_id = ? LIMIT 1", (scope_id,)).fetchone()
        return row is not None

    def is_group_ready(self, scope_id: str) -> bool:
        return self.has_language(scope_id) and self.has_bot(scope_id) and self.has_admins(scope_id)

    def add_admin(self, scope_id: str, sender: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO chat_admins (scope_id, sender) VALUES (?, ?)",
                (scope_id, sender.strip()),
            )
            conn.commit()

    def get_drive_origin(self, scope_id: str) -> tuple[str, float, float]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT drive_origin_name, drive_origin_lat, drive_origin_lon
                FROM chat_settings WHERE scope_id = ?
                """,
                (scope_id,),
            ).fetchone()
        if row is None:
            return "Stuttgart", 48.7758, 9.1829
        return row["drive_origin_name"], row["drive_origin_lat"], row["drive_origin_lon"]

    def set_drive_origin(self, scope_id: str, name: str, lat: float, lon: float) -> None:
        language = self.get_language(scope_id)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_settings (
                    scope_id, language, drive_origin_name, drive_origin_lat, drive_origin_lon, updated_at
                )
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(scope_id) DO UPDATE SET
                    drive_origin_name = excluded.drive_origin_name,
                    drive_origin_lat = excluded.drive_origin_lat,
                    drive_origin_lon = excluded.drive_origin_lon,
                    updated_at = excluded.updated_at
                """,
                (scope_id, language, name.strip(), lat, lon),
            )
            conn.commit()

    def add_custom_host(self, scope_id: str, host_pattern: str, adapter_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO custom_hosts (scope_id, host_pattern, adapter_id)
                VALUES (?, ?, ?)
                ON CONFLICT(scope_id, host_pattern) DO UPDATE SET adapter_id = excluded.adapter_id
                """,
                (scope_id, host_pattern.lower().removeprefix("www."), adapter_id),
            )
            conn.commit()

    def list_custom_hosts(self, scope_id: str) -> List[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT host_pattern, adapter_id FROM custom_hosts WHERE scope_id = ? ORDER BY host_pattern",
                (scope_id,),
            ).fetchall()

    def list_all_custom_hosts(self) -> List[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT scope_id, host_pattern, adapter_id FROM custom_hosts ORDER BY host_pattern"
            ).fetchall()

    def start_pending_listing_add(self, scope_id: str, requested_by: str, ttl_minutes: int | None = None) -> None:
        ttl = ttl_minutes if ttl_minutes is not None else self._dialogue_ttl()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_listing_adds (
                    scope_id, requested_by, step, expires_at, last_activity_at, previous_step
                )
                VALUES (?, ?, 'url', datetime('now', '+' || ? || ' minutes'), datetime('now'), '')
                ON CONFLICT(scope_id, requested_by) DO UPDATE SET
                    step = 'url', url = '', label = '', check_in = '', check_out = '',
                    guests = 2, adapter_id = '', expires_at = excluded.expires_at,
                    last_activity_at = datetime('now'), previous_step = '',
                    created_at = datetime('now')
                """,
                (scope_id, requested_by, ttl),
            )
            conn.commit()

    def get_pending_listing_add(self, scope_id: str, requested_by: str) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT step, url, label, check_in, check_out, guests, adapter_id,
                       previous_step, expires_at, last_activity_at
                FROM pending_listing_adds
                WHERE scope_id = ? AND requested_by = ?
                """,
                (scope_id, requested_by),
            ).fetchone()
            return self._prepare_dialogue_row(conn, "pending_listing_adds", scope_id, requested_by, row)

    def update_pending_listing_add(
        self,
        scope_id: str,
        requested_by: str,
        step: str,
        url: str = "",
        label: str = "",
        check_in: str = "",
        check_out: str = "",
        guests: int = 2,
        adapter_id: str = "",
        ttl_minutes: int | None = None,
    ) -> None:
        ttl = ttl_minutes if ttl_minutes is not None else self._dialogue_ttl()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE pending_listing_adds
                SET step = ?, url = ?, label = ?, check_in = ?, check_out = ?,
                    guests = ?, adapter_id = ?,
                    expires_at = datetime('now', '+' || ? || ' minutes'),
                    last_activity_at = datetime('now')
                WHERE scope_id = ? AND requested_by = ?
                """,
                (step, url, label, check_in, check_out, guests, adapter_id, ttl, scope_id, requested_by),
            )
            conn.commit()

    def clear_pending_listing_add(self, scope_id: str, requested_by: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM pending_listing_adds WHERE scope_id = ? AND requested_by = ?",
                (scope_id, requested_by),
            )
            conn.commit()

    def add_listing(
        self,
        scope_id: str,
        label: str,
        url: str,
        adapter_id: str,
        check_in: date,
        check_out: date,
        guests: int,
        result: ScrapeResult,
        drive_minutes: int | None,
        drive_km: float | None,
        added_by: str = "",
    ) -> bool:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO listings (
                        scope_id, label, url, adapter_id, check_in, check_out, guests,
                        available, price_per_night, total_price, currency, title, location_name,
                        lat, lon, drive_minutes, drive_km, guests_max, bedrooms, bathrooms,
                        rating, review_count, min_nights, cleaning_fee, pets_allowed, property_type,
                        scrape_error, last_checked_at, last_changed_at, added_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._listing_values(
                        scope_id,
                        label,
                        url,
                        adapter_id,
                        check_in,
                        check_out,
                        guests,
                        result,
                        drive_minutes,
                        drive_km,
                        now,
                        now,
                    )
                    + (added_by.strip(),),
                )
                listing_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
                conn.execute(
                    "INSERT INTO listing_changes (listing_id, changed_at, snapshot_json) VALUES (?, ?, ?)",
                    (listing_id, now, json.dumps(self._snapshot_dict(result, drive_minutes, drive_km))),
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def delete_listing(self, scope_id: str, label: str) -> bool:
        row = self._find_listing(scope_id, label)
        if row is None:
            return False
        with self._connect() as conn:
            conn.execute("DELETE FROM listing_changes WHERE listing_id = ?", (row["id"],))
            conn.execute("DELETE FROM listings WHERE id = ?", (row["id"],))
            conn.commit()
        return True

    def list_listings(self, scope_id: str) -> List[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT * FROM listings
                WHERE scope_id = ?
                ORDER BY label ASC
                """,
                (scope_id,),
            ).fetchall()

    def list_all_active_listings(self) -> List[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM listings ORDER BY scope_id, label").fetchall()

    def listing_history(self, scope_id: str, label: str, limit: int = 10) -> List[sqlite3.Row]:
        row = self._find_listing(scope_id, label)
        if row is None:
            return []
        limit = max(1, min(limit, 50))
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT changed_at, snapshot_json
                FROM listing_changes
                WHERE listing_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (row["id"], limit),
            ).fetchall()

    def apply_poll_result(
        self,
        listing_id: int,
        result: ScrapeResult,
        drive_minutes: int | None,
        drive_km: float | None,
    ) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
            if row is None:
                return False
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            current = self._row_snapshot(row)
            new_snapshot = self._snapshot_dict(result, drive_minutes, drive_km)
            changed = self._notify_snapshot(current) != self._notify_snapshot(new_snapshot)
            update_values = (
                self._bool_to_int(result.available),
                result.price_per_night,
                result.total_price,
                result.currency,
                result.title,
                result.location_name,
                result.lat,
                result.lon,
                drive_minutes,
                drive_km,
                result.guests_max,
                result.bedrooms,
                result.bathrooms,
                result.rating,
                result.review_count,
                result.min_nights,
                result.cleaning_fee,
                self._bool_to_int(result.pets_allowed),
                result.property_type,
                result.error,
                now,
                now if changed else row["last_changed_at"],
                listing_id,
            )
            conn.execute(
                """
                UPDATE listings SET
                    available = ?, price_per_night = ?, total_price = ?, currency = ?,
                    title = ?, location_name = ?, lat = ?, lon = ?,
                    drive_minutes = ?, drive_km = ?, guests_max = ?, bedrooms = ?, bathrooms = ?,
                    rating = ?, review_count = ?, min_nights = ?, cleaning_fee = ?,
                    pets_allowed = ?, property_type = ?, scrape_error = ?,
                    last_checked_at = ?, last_changed_at = ?
                WHERE id = ?
                """,
                update_values,
            )
            if changed:
                conn.execute(
                    "INSERT INTO listing_changes (listing_id, changed_at, snapshot_json) VALUES (?, ?, ?)",
                    (listing_id, now, json.dumps(new_snapshot)),
                )
            conn.commit()
        return changed

    def get_poll_state(self) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM bot_state").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def set_poll_state(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO bot_state (key, value, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, value),
            )
            conn.commit()

    def _find_listing(self, scope_id: str, label: str) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM listings WHERE scope_id = ? AND lower(label) = lower(?)",
                (scope_id, label.strip()),
            ).fetchone()

    def _bool_to_int(self, value: bool | None) -> int | None:
        if value is None:
            return None
        return 1 if value else 0

    def _normalize_notify_value(self, key: str, value: Any) -> Any:
        if value is None:
            return None
        if key == "available":
            return bool(value)
        if key in {"price_per_night", "total_price", "cleaning_fee"}:
            return round(float(value), 2)
        if key == "min_nights":
            return int(value)
        return value

    def _notify_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            key: self._normalize_notify_value(key, snapshot.get(key))
            for key in NOTIFY_CHANGE_FIELDS
        }

    def _snapshot_dict(
        self,
        result: ScrapeResult,
        drive_minutes: int | None,
        drive_km: float | None,
    ) -> dict[str, Any]:
        snapshot = {field: getattr(result, field) for field in TRACKED_FIELDS}
        snapshot["drive_minutes"] = drive_minutes
        snapshot["drive_km"] = drive_km
        snapshot["scrape_error"] = result.error
        return snapshot

    def _row_snapshot(self, row: sqlite3.Row) -> dict[str, Any]:
        snapshot = {}
        for field in TRACKED_FIELDS:
            snapshot[field] = row[field] if field in row.keys() else None
        snapshot["drive_minutes"] = row["drive_minutes"]
        snapshot["drive_km"] = row["drive_km"]
        snapshot["scrape_error"] = row["scrape_error"]
        if snapshot.get("pets_allowed") is not None:
            snapshot["pets_allowed"] = bool(snapshot["pets_allowed"])
        if snapshot.get("available") is not None:
            snapshot["available"] = bool(snapshot["available"])
        return snapshot

    def _listing_values(
        self,
        scope_id: str,
        label: str,
        url: str,
        adapter_id: str,
        check_in: date,
        check_out: date,
        guests: int,
        result: ScrapeResult,
        drive_minutes: int | None,
        drive_km: float | None,
        checked_at: str,
        changed_at: str,
    ) -> tuple:
        return (
            scope_id,
            label.strip(),
            url.strip(),
            adapter_id,
            check_in.isoformat(),
            check_out.isoformat(),
            guests,
            self._bool_to_int(result.available),
            result.price_per_night,
            result.total_price,
            result.currency,
            result.title,
            result.location_name,
            result.lat,
            result.lon,
            drive_minutes,
            drive_km,
            result.guests_max,
            result.bedrooms,
            result.bathrooms,
            result.rating,
            result.review_count,
            result.min_nights,
            result.cleaning_fee,
            self._bool_to_int(result.pets_allowed),
            result.property_type,
            result.error,
            checked_at,
            changed_at,
        )
