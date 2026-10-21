"""Move a chat's data to another chat id, and merge a member's old id into a new one.

Used when a group moves between Signal and WhatsApp: the group id and every
member id change, while the data should stay. Byte-identical in every bot; each
bot's storage describes its own tables with a MigrationSpec.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class MigrationSpec:
    # Tables with a scope_id column whose rows move to the new scope.
    scope_tables: tuple[str, ...]
    # Per-scope dialogue state that is dropped instead of moved.
    transient_tables: tuple[str, ...]
    # (table, column, predicate) for every column holding a member id. The
    # predicate selects the rows belonging to one scope, with one "?" for it.
    person_columns: tuple[tuple[str, str, str], ...]
    # SELECT sender, display_name ... WHERE scope_id = ? — members that can be
    # claimed by name after a move. None if the bot keeps no member names.
    member_query: str | None = None
    # bot_state keys of the form "<prefix>:<scope_id>".
    scoped_state_keys: tuple[str, ...] = ()


def move_scope(
    conn: sqlite3.Connection,
    spec: MigrationSpec,
    old_scope: str,
    new_scope: str,
    old_group_id: str | None,
    new_group_id: str | None,
) -> None:
    for table in spec.transient_tables:
        conn.execute(f"DELETE FROM {table} WHERE scope_id = ?", (old_scope,))
    # OR REPLACE: if the target already holds a stray row, the moved data wins.
    for table in spec.scope_tables:
        conn.execute(f"UPDATE OR REPLACE {table} SET scope_id = ? WHERE scope_id = ?", (new_scope, old_scope))
    if old_group_id and new_group_id:
        conn.execute(
            "UPDATE OR REPLACE chat_groups SET group_id = ? WHERE group_id = ?",
            (new_group_id, old_group_id),
        )
    for prefix in spec.scoped_state_keys:
        conn.execute(
            "UPDATE OR REPLACE bot_state SET key = ? WHERE key = ?",
            (f"{prefix}:{new_scope}", f"{prefix}:{old_scope}"),
        )


def list_members(conn: sqlite3.Connection, spec: MigrationSpec, scope_id: str) -> list[dict]:
    if spec.member_query is None:
        return []
    rows = conn.execute(spec.member_query, (scope_id,)).fetchall()
    return [{"sender": row[0], "name": row[1]} for row in rows if row[0] and row[1]]


def merge_member(
    conn: sqlite3.Connection,
    spec: MigrationSpec,
    scope_id: str,
    old_sender: str,
    new_sender: str,
) -> None:
    # OR REPLACE: rows the new id created before claiming give way to the old
    # identity's rows (name, admin flag, membership), so history wins.
    for table, column, predicate in spec.person_columns:
        conn.execute(
            f"UPDATE OR REPLACE {table} SET {column} = ? WHERE {column} = ? AND {predicate}",
            (new_sender, old_sender, scope_id),
        )
