from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional

from categories import DEFAULT_CATEGORIES, guess_category
from dialogue_utils import STALE_STEP, dialogue_ttl_minutes, is_dialogue_stale


_UNSET = object()


class Storage:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS chat_settings (
                    scope_id TEXT PRIMARY KEY,
                    language TEXT NOT NULL DEFAULT 'en',
                    bot_id TEXT NOT NULL DEFAULT '',
                    active_list_id INTEGER,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS chat_admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(scope_id, sender)
                );
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    number TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS chat_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS shopping_lists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(scope_id, name)
                );
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(scope_id, name)
                );
                CREATE TABLE IF NOT EXISTS shops (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(scope_id, name)
                );
                CREATE TABLE IF NOT EXISTS list_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    list_id INTEGER NOT NULL,
                    scope_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    quantity TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    category_id INTEGER,
                    shop_id INTEGER,
                    checked INTEGER NOT NULL DEFAULT 0,
                    image_path TEXT,
                    added_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    checked_at TEXT,
                    FOREIGN KEY(list_id) REFERENCES shopping_lists(id) ON DELETE CASCADE,
                    FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE SET NULL,
                    FOREIGN KEY(shop_id) REFERENCES shops(id) ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS item_catalog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    category_id INTEGER,
                    shop_id INTEGER,
                    use_count INTEGER NOT NULL DEFAULT 1,
                    last_used_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(scope_id, name)
                );
                CREATE TABLE IF NOT EXISTS pending_photos (
                    scope_id TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    attachment_id TEXT NOT NULL DEFAULT '',
                    image_path TEXT NOT NULL DEFAULT '',
                    suggested_name TEXT NOT NULL DEFAULT '',
                    expires_at TEXT NOT NULL,
                    last_activity_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY(scope_id, requested_by)
                );
                CREATE TABLE IF NOT EXISTS pending_adds (
                    scope_id TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    list_id INTEGER NOT NULL,
                    step TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    quantity TEXT NOT NULL DEFAULT '',
                    category_id INTEGER,
                    shop_id INTEGER,
                    image_path TEXT NOT NULL DEFAULT '',
                    expires_at TEXT NOT NULL,
                    last_activity_at TEXT NOT NULL DEFAULT (datetime('now')),
                    previous_step TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(scope_id, requested_by)
                );
                CREATE TABLE IF NOT EXISTS pending_checks (
                    scope_id TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    list_id INTEGER NOT NULL,
                    step TEXT NOT NULL DEFAULT 'pick',
                    expires_at TEXT NOT NULL,
                    last_activity_at TEXT NOT NULL DEFAULT (datetime('now')),
                    previous_step TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(scope_id, requested_by)
                );
                """
            )
            self._ensure_column(conn, "chat_settings", "active_list_id", "INTEGER")
            conn.commit()

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

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

    # --- scope setup ---
    def has_language(self, scope_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT language FROM chat_settings WHERE scope_id = ?", (scope_id,)).fetchone()
        return row is not None

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
                ON CONFLICT(scope_id) DO UPDATE SET language = excluded.language, updated_at = datetime('now')
                """,
                (scope_id, language),
            )
            conn.commit()
        return True

    def has_admins(self, scope_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM chat_admins WHERE scope_id = ? LIMIT 1", (scope_id,)).fetchone()
        return row is not None

    def add_admin(self, scope_id: str, sender: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO chat_admins (scope_id, sender) VALUES (?, ?)", (scope_id, sender))
            conn.commit()

    def is_admin(self, scope_id: str, sender: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM chat_admins WHERE scope_id = ? AND sender = ?",
                (scope_id, sender),
            ).fetchone()
        return row is not None

    def has_bot(self, scope_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT bot_id FROM chat_settings WHERE scope_id = ?", (scope_id,)).fetchone()
        return bool(row and row["bot_id"])

    def get_bot_id(self, scope_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT bot_id FROM chat_settings WHERE scope_id = ?", (scope_id,)).fetchone()
        return row["bot_id"] if row else ""

    def set_bot_id(self, scope_id: str, bot_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_settings (scope_id, language, bot_id, updated_at)
                VALUES (?, 'en', ?, datetime('now'))
                ON CONFLICT(scope_id) DO UPDATE SET bot_id = excluded.bot_id
                """,
                (scope_id, bot_id),
            )
            conn.commit()

    def is_group_ready(self, scope_id: str) -> bool:
        return self.has_language(scope_id) and self.has_admins(scope_id) and (
            not self.has_bot(scope_id) or bool(self.get_bot_id(scope_id))
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

    def seed_defaults(self, scope_id: str, language: str) -> None:
        with self._connect() as conn:
            for name, order in DEFAULT_CATEGORIES.get(language, DEFAULT_CATEGORIES["en"]):
                conn.execute(
                    "INSERT OR IGNORE INTO categories (scope_id, name, sort_order) VALUES (?, ?, ?)",
                    (scope_id, name, order),
                )
            list_id = conn.execute(
                "INSERT OR IGNORE INTO shopping_lists (scope_id, name) VALUES (?, ?)",
                (scope_id, "Einkauf" if language == "de" else "Shopping"),
            ).lastrowid
            if not list_id:
                row = conn.execute(
                    "SELECT id FROM shopping_lists WHERE scope_id = ? ORDER BY id ASC LIMIT 1",
                    (scope_id,),
                ).fetchone()
                list_id = row["id"] if row else None
            if list_id:
                conn.execute(
                    "UPDATE chat_settings SET active_list_id = ? WHERE scope_id = ?",
                    (list_id, scope_id),
                )
            conn.commit()

    # --- lists ---
    def get_active_list_id(self, scope_id: str) -> int | None:
        with self._connect() as conn:
            row = conn.execute("SELECT active_list_id FROM chat_settings WHERE scope_id = ?", (scope_id,)).fetchone()
            if row and row["active_list_id"]:
                return int(row["active_list_id"])
            fallback = conn.execute(
                "SELECT id FROM shopping_lists WHERE scope_id = ? ORDER BY id ASC LIMIT 1",
                (scope_id,),
            ).fetchone()
        return int(fallback["id"]) if fallback else None

    def set_active_list(self, scope_id: str, list_name: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM shopping_lists WHERE scope_id = ? AND lower(name) = lower(?)",
                (scope_id, list_name.strip()),
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                """
                INSERT INTO chat_settings (scope_id, language, active_list_id, updated_at)
                VALUES (?, 'en', ?, datetime('now'))
                ON CONFLICT(scope_id) DO UPDATE SET active_list_id = excluded.active_list_id
                """,
                (scope_id, row["id"]),
            )
            conn.commit()
        return True

    def create_list(self, scope_id: str, name: str) -> bool:
        normalized = name.strip()
        if not normalized:
            return False
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO shopping_lists (scope_id, name) VALUES (?, ?)",
                    (scope_id, normalized),
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def list_shopping_lists(self, scope_id: str) -> List[sqlite3.Row]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT l.id, l.name,
                       (SELECT COUNT(*) FROM list_items i WHERE i.list_id = l.id AND i.checked = 0) AS open_count
                FROM shopping_lists l
                WHERE l.scope_id = ?
                ORDER BY l.id ASC
                """,
                (scope_id,),
            ).fetchall()
        return rows

    def get_list_name(self, list_id: int) -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT name FROM shopping_lists WHERE id = ?", (list_id,)).fetchone()
        return row["name"] if row else ""

    # --- categories & shops ---
    def list_categories(self, scope_id: str) -> List[sqlite3.Row]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, sort_order FROM categories WHERE scope_id = ? ORDER BY sort_order, name",
                (scope_id,),
            ).fetchall()
        return rows

    def add_category(self, scope_id: str, name: str) -> bool:
        normalized = name.strip()
        if not normalized:
            return False
        with self._connect() as conn:
            max_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) AS m FROM categories WHERE scope_id = ?",
                (scope_id,),
            ).fetchone()["m"]
            try:
                conn.execute(
                    "INSERT INTO categories (scope_id, name, sort_order) VALUES (?, ?, ?)",
                    (scope_id, normalized, max_order + 1),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def delete_category(self, scope_id: str, name: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM categories WHERE scope_id = ? AND lower(name) = lower(?)",
                (scope_id, name.strip()),
            ).fetchone()
            if row is None:
                return False
            conn.execute("UPDATE list_items SET category_id = NULL WHERE category_id = ?", (row["id"],))
            conn.execute("DELETE FROM categories WHERE id = ?", (row["id"],))
            conn.commit()
        return True

    def find_category(self, scope_id: str, name: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT id, name FROM categories WHERE scope_id = ? AND lower(name) = lower(?)",
                (scope_id, name.strip()),
            ).fetchone()

    def list_shops(self, scope_id: str) -> List[sqlite3.Row]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, sort_order FROM shops WHERE scope_id = ? ORDER BY sort_order, name",
                (scope_id,),
            ).fetchall()
        return rows

    def add_shop(self, scope_id: str, name: str) -> bool:
        normalized = name.strip()
        if not normalized:
            return False
        with self._connect() as conn:
            max_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) AS m FROM shops WHERE scope_id = ?",
                (scope_id,),
            ).fetchone()["m"]
            try:
                conn.execute(
                    "INSERT INTO shops (scope_id, name, sort_order) VALUES (?, ?, ?)",
                    (scope_id, normalized, max_order + 1),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def delete_shop(self, scope_id: str, name: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM shops WHERE scope_id = ? AND lower(name) = lower(?)",
                (scope_id, name.strip()),
            ).fetchone()
            if row is None:
                return False
            conn.execute("UPDATE list_items SET shop_id = NULL WHERE shop_id = ?", (row["id"],))
            conn.execute("DELETE FROM shops WHERE id = ?", (row["id"],))
            conn.commit()
        return True

    def find_shop(self, scope_id: str, name: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT id, name FROM shops WHERE scope_id = ? AND lower(name) = lower(?)",
                (scope_id, name.strip()),
            ).fetchone()

    # --- items ---
    def add_item(
        self,
        scope_id: str,
        list_id: int,
        name: str,
        *,
        quantity: str = "",
        note: str = "",
        category_id: int | None = None,
        shop_id: int | None = None,
        added_by: str = "",
        image_path: str | None = None,
        language: str = "en",
    ) -> tuple[bool, str]:
        normalized = name.strip()
        if not normalized:
            return False, ""
        if category_id is None:
            cat_names = [row["name"] for row in self.list_categories(scope_id)]
            guessed = guess_category(normalized, cat_names, language)
            if guessed:
                row = self.find_category(scope_id, guessed)
                category_id = row["id"] if row else None
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT id FROM list_items
                WHERE list_id = ? AND checked = 0 AND lower(name) = lower(?)
                """,
                (list_id, normalized),
            ).fetchone()
            if existing:
                return False, normalized
            conn.execute(
                """
                INSERT INTO list_items (
                    list_id, scope_id, name, quantity, note, category_id, shop_id,
                    added_by, image_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (list_id, scope_id, normalized, quantity, note, category_id, shop_id, added_by, image_path),
            )
            conn.execute(
                """
                INSERT INTO item_catalog (scope_id, name, category_id, shop_id, use_count, last_used_at)
                VALUES (?, ?, ?, ?, 1, datetime('now'))
                ON CONFLICT(scope_id, name) DO UPDATE SET
                    use_count = use_count + 1,
                    category_id = COALESCE(excluded.category_id, category_id),
                    shop_id = COALESCE(excluded.shop_id, shop_id),
                    last_used_at = datetime('now')
                """,
                (scope_id, normalized, category_id, shop_id),
            )
            conn.commit()
        return True, normalized

    def find_open_item(self, scope_id: str, list_id: int, name: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT i.* FROM list_items i
                WHERE i.scope_id = ? AND i.list_id = ? AND i.checked = 0
                  AND lower(i.name) = lower(?)
                """,
                (scope_id, list_id, name.strip()),
            ).fetchone()

    def check_item(self, scope_id: str, list_id: int, name: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id FROM list_items
                WHERE scope_id = ? AND list_id = ? AND checked = 0 AND lower(name) = lower(?)
                """,
                (scope_id, list_id, name.strip()),
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                "UPDATE list_items SET checked = 1, checked_at = datetime('now') WHERE id = ?",
                (row["id"],),
            )
            conn.commit()
        return True

    def uncheck_item(self, scope_id: str, list_id: int, name: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id FROM list_items
                WHERE scope_id = ? AND list_id = ? AND checked = 1 AND lower(name) = lower(?)
                ORDER BY checked_at DESC LIMIT 1
                """,
                (scope_id, list_id, name.strip()),
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                "UPDATE list_items SET checked = 0, checked_at = NULL WHERE id = ?",
                (row["id"],),
            )
            conn.commit()
        return True

    def remove_item(self, scope_id: str, list_id: int, name: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id FROM list_items
                WHERE scope_id = ? AND list_id = ? AND lower(name) = lower(?)
                ORDER BY checked ASC, id DESC LIMIT 1
                """,
                (scope_id, list_id, name.strip()),
            ).fetchone()
            if row is None:
                return False
            conn.execute("DELETE FROM list_items WHERE id = ?", (row["id"],))
            conn.commit()
        return True

    def clear_checked(self, scope_id: str, list_id: int) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM list_items WHERE scope_id = ? AND list_id = ? AND checked = 1",
                (scope_id, list_id),
            )
            conn.commit()
        return cur.rowcount

    def list_items(
        self,
        scope_id: str,
        list_id: int,
        *,
        shop_id: int | None = None,
        include_checked: bool = False,
    ) -> List[sqlite3.Row]:
        query = """
            SELECT i.id, i.name, i.quantity, i.note, i.checked, i.image_path,
                   c.name AS category_name, c.sort_order AS category_order,
                   s.name AS shop_name
            FROM list_items i
            LEFT JOIN categories c ON c.id = i.category_id
            LEFT JOIN shops s ON s.id = i.shop_id
            WHERE i.scope_id = ? AND i.list_id = ?
        """
        params: list = [scope_id, list_id]
        if not include_checked:
            query += " AND i.checked = 0"
        if shop_id is not None:
            query += " AND i.shop_id = ?"
            params.append(shop_id)
        query += " ORDER BY i.checked ASC, COALESCE(c.sort_order, 99), c.name, i.name"
        with self._connect() as conn:
            return conn.execute(query, params).fetchall()

    def frequent_items(self, scope_id: str, limit: int = 12) -> List[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT ic.name, ic.use_count, c.name AS category_name, s.name AS shop_name
                FROM item_catalog ic
                LEFT JOIN categories c ON c.id = ic.category_id
                LEFT JOIN shops s ON s.id = ic.shop_id
                WHERE ic.scope_id = ?
                ORDER BY ic.use_count DESC, ic.last_used_at DESC
                LIMIT ?
                """,
                (scope_id, limit),
            ).fetchall()

    def search_items(self, scope_id: str, list_id: int, query: str) -> List[sqlite3.Row]:
        pattern = f"%{query.strip().lower()}%"
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT i.name, i.checked, c.name AS category_name, s.name AS shop_name
                FROM list_items i
                LEFT JOIN categories c ON c.id = i.category_id
                LEFT JOIN shops s ON s.id = i.shop_id
                WHERE i.scope_id = ? AND i.list_id = ? AND lower(i.name) LIKE ?
                ORDER BY i.checked ASC, i.name
                LIMIT 20
                """,
                (scope_id, list_id, pattern),
            ).fetchall()

    # --- pending add dialogue ---
    def start_pending_add(
        self,
        scope_id: str,
        requested_by: str,
        list_id: int,
        *,
        step: str = "name",
        name: str = "",
        image_path: str = "",
    ) -> None:
        ttl = self._dialogue_ttl()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_adds (
                    scope_id, requested_by, list_id, step, name, image_path,
                    expires_at, last_activity_at, previous_step
                )
                VALUES (?, ?, ?, ?, ?, ?, datetime('now', '+' || ? || ' minutes'), datetime('now'), '')
                ON CONFLICT(scope_id, requested_by) DO UPDATE SET
                    list_id = excluded.list_id,
                    step = excluded.step,
                    name = excluded.name,
                    quantity = '',
                    category_id = NULL,
                    shop_id = NULL,
                    image_path = excluded.image_path,
                    expires_at = excluded.expires_at,
                    last_activity_at = datetime('now'),
                    previous_step = ''
                """,
                (scope_id, requested_by, list_id, step, name, image_path, ttl),
            )
            conn.commit()

    def get_pending_add(self, scope_id: str, requested_by: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM pending_adds WHERE scope_id = ? AND requested_by = ?",
                (scope_id, requested_by),
            ).fetchone()
            return self._prepare_dialogue_row(conn, "pending_adds", scope_id, requested_by, row)

    def update_pending_add(
        self,
        scope_id: str,
        requested_by: str,
        step: str,
        *,
        name: str | None = None,
        quantity: str | None = None,
        category_id=_UNSET,
        shop_id=_UNSET,
    ) -> None:
        ttl = self._dialogue_ttl()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name, quantity, category_id, shop_id FROM pending_adds WHERE scope_id = ? AND requested_by = ?",
                (scope_id, requested_by),
            ).fetchone()
            if row is None:
                return
            cat_id = row["category_id"] if category_id is _UNSET else category_id
            sh_id = row["shop_id"] if shop_id is _UNSET else shop_id
            conn.execute(
                """
                UPDATE pending_adds
                SET step = ?, name = ?, quantity = ?, category_id = ?, shop_id = ?,
                    expires_at = datetime('now', '+' || ? || ' minutes'),
                    last_activity_at = datetime('now')
                WHERE scope_id = ? AND requested_by = ?
                """,
                (
                    step,
                    name if name is not None else row["name"],
                    quantity if quantity is not None else row["quantity"],
                    cat_id,
                    sh_id,
                    ttl,
                    scope_id,
                    requested_by,
                ),
            )
            conn.commit()

    def clear_pending_add(self, scope_id: str, requested_by: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM pending_adds WHERE scope_id = ? AND requested_by = ?",
                (scope_id, requested_by),
            )
            conn.commit()

    # --- pending check dialogue ---
    def start_pending_check(self, scope_id: str, requested_by: str, list_id: int) -> None:
        ttl = self._dialogue_ttl()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_checks (scope_id, requested_by, list_id, expires_at, last_activity_at)
                VALUES (?, ?, ?, datetime('now', '+' || ? || ' minutes'), datetime('now'))
                ON CONFLICT(scope_id, requested_by) DO UPDATE SET
                    list_id = excluded.list_id,
                    expires_at = excluded.expires_at,
                    last_activity_at = datetime('now')
                """,
                (scope_id, requested_by, list_id, ttl),
            )
            conn.commit()

    def get_pending_check(self, scope_id: str, requested_by: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM pending_checks WHERE scope_id = ? AND requested_by = ?",
                (scope_id, requested_by),
            ).fetchone()
            return self._prepare_dialogue_row(conn, "pending_checks", scope_id, requested_by, row)

    def clear_pending_check(self, scope_id: str, requested_by: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM pending_checks WHERE scope_id = ? AND requested_by = ?",
                (scope_id, requested_by),
            )
            conn.commit()

    def admin_reset(self, scope_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM list_items WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM item_catalog WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM pending_photos WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM pending_adds WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM pending_checks WHERE scope_id = ?", (scope_id,))
            conn.commit()
