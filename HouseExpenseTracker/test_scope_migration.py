import os
import sqlite3
import tempfile
import unittest

from storage import MIGRATION, Storage

PERSON_COLUMNS = {"sender", "requested_by", "added_by", "paid_by", "created_by", "member_sender", "from_sender", "to_sender"}

OLD_SCOPE, OLD_GROUP = "group:c2lnbmFsLWdyb3Vw", "c2lnbmFsLWdyb3Vw"
NEW_SCOPE, NEW_GROUP = "group:120363000000000000@g.us", "120363000000000000@g.us"
ANNA_SIGNAL, ANNA_WA = "70a4ae95-d4df-444f-86eb-a9a1dc1416d6", "40631279829046@lid"
BOB_SIGNAL, BOB_WA = "+491700000002", "491700000002@c.us"


class SpecCoverageTests(unittest.TestCase):
    def test_every_scoped_table_and_person_column_is_handled(self) -> None:
        path = os.path.join(tempfile.mkdtemp(), "e.db")
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
        self.storage = st = Storage(os.path.join(tempfile.mkdtemp(), "e.db"))
        st.register_group(OLD_GROUP)
        st.set_language(OLD_SCOPE, "de")
        st.add_admin(OLD_SCOPE, ANNA_SIGNAL)
        st.set_display_name(OLD_SCOPE, ANNA_SIGNAL, "Anna")
        st.set_display_name(OLD_SCOPE, BOB_SIGNAL, "Bob")
        st.add_expense(OLD_SCOPE, "Einkauf", 9000, "EUR", ANNA_SIGNAL, [ANNA_SIGNAL, BOB_SIGNAL], ANNA_SIGNAL)
        st.add_settlement(OLD_SCOPE, BOB_SIGNAL, ANNA_SIGNAL, 1000, "EUR", BOB_SIGNAL)
        self.before = st.compute_balances(OLD_SCOPE)

    def test_move_and_claims_keep_balances_intact(self) -> None:
        st = self.storage
        st.move_scope(OLD_SCOPE, NEW_SCOPE, OLD_GROUP, NEW_GROUP)
        self.assertEqual(st.compute_balances(OLD_SCOPE), {})
        self.assertEqual(st.compute_balances(NEW_SCOPE), self.before)

        st.set_display_name(NEW_SCOPE, BOB_WA, "Bobby")  # joined before claiming
        st.merge_member(NEW_SCOPE, ANNA_SIGNAL, ANNA_WA)
        st.merge_member(NEW_SCOPE, BOB_SIGNAL, BOB_WA)

        after = st.compute_balances(NEW_SCOPE)
        self.assertEqual(after, {ANNA_WA: self.before[ANNA_SIGNAL], BOB_WA: self.before[BOB_SIGNAL]})
        self.assertEqual(st.display_name(NEW_SCOPE, BOB_WA), "Bob")
        self.assertTrue(st.is_admin(NEW_SCOPE, ANNA_WA))
        self.assertEqual({row["sender"] for row in st.list_members(NEW_SCOPE)}, {ANNA_WA, BOB_WA})
        expense = st.list_expenses(NEW_SCOPE)[0]
        self.assertEqual(expense["paid_by"], ANNA_WA)
        self.assertEqual({row["member_sender"] for row in st.list_expense_splits(expense["id"])}, {ANNA_WA, BOB_WA})

    def test_members_are_offered_for_claiming(self) -> None:
        st = self.storage
        st.move_scope(OLD_SCOPE, NEW_SCOPE, OLD_GROUP, NEW_GROUP)
        self.assertEqual(
            st.migration_members(NEW_SCOPE),
            [{"sender": ANNA_SIGNAL, "name": "Anna"}, {"sender": BOB_SIGNAL, "name": "Bob"}],
        )


if __name__ == "__main__":
    unittest.main()
