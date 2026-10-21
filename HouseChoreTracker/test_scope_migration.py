import os
import sqlite3
import tempfile
import unittest

from storage import MIGRATION, Storage

PERSON_COLUMNS = {"sender", "requested_by", "added_by", "paid_by", "created_by", "member_sender", "from_sender", "to_sender"}

OLD_SCOPE, OLD_GROUP = "group:c2lnbmFsLWdyb3Vw", "c2lnbmFsLWdyb3Vw"
NEW_SCOPE, NEW_GROUP = "group:120363000000000000@g.us", "120363000000000000@g.us"
ANNA_SIGNAL, ANNA_WA = "70a4ae95-d4df-444f-86eb-a9a1dc1416d6", "40631279829046@lid"
BOB_SIGNAL = "+491700000002"


class SpecCoverageTests(unittest.TestCase):
    def test_every_scoped_table_and_person_column_is_handled(self) -> None:
        path = os.path.join(tempfile.mkdtemp(), "c.db")
        Storage(path)
        conn = sqlite3.connect(path)
        handled_tables = set(MIGRATION.scope_tables) | set(MIGRATION.transient_tables)
        handled_people = {(table, column) for table, column, _ in MIGRATION.person_columns}
        for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"):
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if "scope_id" in columns:
                self.assertIn(table, handled_tables, f"{table}.scope_id is not moved")
            if table in MIGRATION.transient_tables:
                continue
            for column in columns & PERSON_COLUMNS:
                self.assertIn((table, column), handled_people, f"{table}.{column} is not merged")


class MoveAndMergeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = Storage(os.path.join(tempfile.mkdtemp(), "c.db"))
        st = self.storage
        st.register_group(OLD_GROUP)
        st.set_language(OLD_SCOPE, "de")
        st.add_admin(OLD_SCOPE, ANNA_SIGNAL)
        st.set_display_name(OLD_SCOPE, ANNA_SIGNAL, "Anna")
        st.set_display_name(OLD_SCOPE, BOB_SIGNAL, "Bob")
        st.add_chore(OLD_SCOPE, "Müll", {"type": "interval", "value": 1, "unit": "weeks"})
        st.mark_done(OLD_SCOPE, "Müll", ANNA_SIGNAL)
        st.mark_done(OLD_SCOPE, "Müll", ANNA_SIGNAL)
        st.mark_auth_reminder_sent(OLD_SCOPE)
        st.start_pending_chore_setup(OLD_SCOPE, BOB_SIGNAL)

    def test_move_puts_everything_under_the_new_group(self) -> None:
        st = self.storage
        st.move_scope(OLD_SCOPE, NEW_SCOPE, OLD_GROUP, NEW_GROUP)

        self.assertEqual([row["name"] for row in st.list_chores(NEW_SCOPE)], ["Müll"])
        self.assertEqual(st.list_chores(OLD_SCOPE), [])
        self.assertEqual(st.get_language(NEW_SCOPE), "de")
        self.assertTrue(st.is_admin(NEW_SCOPE, ANNA_SIGNAL))
        self.assertFalse(st.has_admins(OLD_SCOPE))
        self.assertEqual(st.display_name(NEW_SCOPE, ANNA_SIGNAL), "Anna")
        self.assertEqual(st.user_stats(NEW_SCOPE, ANNA_SIGNAL)["total_completions"], 2)
        self.assertEqual(st.list_groups(), [NEW_GROUP])
        self.assertIsNone(st.get_pending_chore_setup(NEW_SCOPE, BOB_SIGNAL))
        with sqlite3.connect(st.db_path) as conn:
            keys = {row[0] for row in conn.execute("SELECT key FROM bot_state")}
        self.assertIn(f"last_auth_reminder_at:{NEW_SCOPE}", keys)
        self.assertNotIn(f"last_auth_reminder_at:{OLD_SCOPE}", keys)
        members = {m["name"]: m["sender"] for m in st.migration_members(NEW_SCOPE)}
        self.assertEqual(members, {"Anna": ANNA_SIGNAL, "Bob": BOB_SIGNAL})

    def test_claim_moves_history_admin_and_name_to_new_id(self) -> None:
        st = self.storage
        st.move_scope(OLD_SCOPE, NEW_SCOPE, OLD_GROUP, NEW_GROUP)
        # Before claiming, Anna's new id already left a trace (named herself).
        st.set_display_name(NEW_SCOPE, ANNA_WA, "Anna WA")
        st.merge_member(NEW_SCOPE, ANNA_SIGNAL, ANNA_WA)

        self.assertTrue(st.is_admin(NEW_SCOPE, ANNA_WA))
        self.assertFalse(st.is_admin(NEW_SCOPE, ANNA_SIGNAL))
        self.assertEqual(st.display_name(NEW_SCOPE, ANNA_WA), "Anna")
        self.assertEqual(st.user_stats(NEW_SCOPE, ANNA_WA)["total_completions"], 2)
        self.assertEqual(st.user_stats(NEW_SCOPE, ANNA_SIGNAL)["total_completions"], 0)

    def test_moving_back_restores_the_original_group(self) -> None:
        st = self.storage
        st.move_scope(OLD_SCOPE, NEW_SCOPE, OLD_GROUP, NEW_GROUP)
        st.move_scope(NEW_SCOPE, OLD_SCOPE, NEW_GROUP, OLD_GROUP)
        self.assertEqual([row["name"] for row in st.list_chores(OLD_SCOPE)], ["Müll"])
        self.assertEqual(st.list_groups(), [OLD_GROUP])


if __name__ == "__main__":
    unittest.main()
