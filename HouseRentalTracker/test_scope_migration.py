import os
import sqlite3
import tempfile
import unittest
from datetime import date

from scrape_types import ScrapeResult
from storage import MIGRATION, Storage

PERSON_COLUMNS = {"sender", "requested_by", "added_by", "paid_by", "created_by", "member_sender", "from_sender", "to_sender"}

OLD_SCOPE, OLD_GROUP = "group:c2lnbmFsLWdyb3Vw", "c2lnbmFsLWdyb3Vw"
NEW_SCOPE, NEW_GROUP = "group:120363000000000000@g.us", "120363000000000000@g.us"
ANNA_SIGNAL, ANNA_WA = "70a4ae95-d4df-444f-86eb-a9a1dc1416d6", "40631279829046@lid"


class SpecCoverageTests(unittest.TestCase):
    def test_every_scoped_table_and_person_column_is_handled(self) -> None:
        path = os.path.join(tempfile.mkdtemp(), "r.db")
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
    def test_listings_settings_and_admins_move(self) -> None:
        st = Storage(os.path.join(tempfile.mkdtemp(), "r.db"))
        st.register_group(OLD_GROUP)
        st.set_language(OLD_SCOPE, "de")
        st.add_admin(OLD_SCOPE, ANNA_SIGNAL)
        st.add_custom_host(OLD_SCOPE, "example-rentals.de", "json_ld")
        st.add_listing(
            OLD_SCOPE, "Haus am See", "https://example-rentals.de/1", "json_ld",
            date(2027, 7, 1), date(2027, 7, 8), 2, ScrapeResult(), None, None, added_by=ANNA_SIGNAL,
        )

        st.move_scope(OLD_SCOPE, NEW_SCOPE, OLD_GROUP, NEW_GROUP)
        self.assertEqual([row["label"] for row in st.list_listings(NEW_SCOPE)], ["Haus am See"])
        self.assertEqual(st.list_listings(OLD_SCOPE), [])
        self.assertEqual(st.get_language(NEW_SCOPE), "de")
        self.assertEqual([row["host_pattern"] for row in st.list_custom_hosts(NEW_SCOPE)], ["example-rentals.de"])
        self.assertEqual(st.list_groups(), [NEW_GROUP])
        self.assertEqual(st.migration_members(NEW_SCOPE), [])

        st.merge_member(NEW_SCOPE, ANNA_SIGNAL, ANNA_WA)
        self.assertTrue(st.is_admin(NEW_SCOPE, ANNA_WA))
        self.assertEqual(st.list_listings(NEW_SCOPE)[0]["added_by"], ANNA_WA)


if __name__ == "__main__":
    unittest.main()
