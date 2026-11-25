"""Spec 007, decided 2026-11-24: FR3 (per-group websites, generic reader), FR8 (manual check), FR13 (quiet)."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from unittest import mock

from commands import handle_command
from poller import Poller, load_custom_hosts
from scrape_types import ScrapeResult
from scrapers import JsonLdAdapter, ScraperRegistry
from storage import Storage

GROUP_A, GROUP_B = "group-a", "group-b"
SCOPE_A, SCOPE_B = f"group:{GROUP_A}", f"group:{GROUP_B}"
ANNA = "+491700000001"


def _text(result: object) -> str:
    if isinstance(result, list):
        return "\n".join(str(part) for part in result)
    if isinstance(result, dict):
        return str(result.get("reply", ""))
    return str(result or "")


class GroupDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.storage = Storage(os.path.join(self.tmp.name, "rentals.db"))
        self.registry = ScraperRegistry()
        self.poller = Poller(self.storage, self.registry)
        env = mock.patch.dict(os.environ, {"BOT_REGISTRY": "", "BOT_INSTANCE_ID": "default"})
        env.start()
        self.addCleanup(env.stop)
        for group in (GROUP_A, GROUP_B):
            self.say(group, "english")

    def say(self, group: str | None, message: str, scope: str | None = None) -> str:
        scope_id = scope or f"group:{group}"
        return _text(handle_command(self.storage, self.registry, self.poller, message, ANNA, scope_id, group))

    def add_listing(self, scope_id: str, label: str) -> None:
        self.storage.add_listing(
            scope_id, label, f"https://example.com/{label}", "json_ld",
            date(2027, 7, 1), date(2027, 7, 8), 4, ScrapeResult(available=True, total_price=1200.0), None, None,
        )

    # FR13
    def test_unknown_text_in_a_group_gets_no_reply(self) -> None:
        self.assertEqual(self.say(GROUP_A, "bis später"), "")
        self.assertEqual(self.say(GROUP_A, ""), "")
        self.assertIn("overview", self.say(GROUP_A, "?"))

    def test_unknown_text_in_a_direct_chat_still_gets_help(self) -> None:
        self.assertIn("I don't know that command", self.say(None, "bis später", scope=f"dm:{ANNA}"))

    # FR3
    def test_added_website_is_known_only_to_its_group(self) -> None:
        self.assertIn("Website added: ferien-am-see.de", self.say(GROUP_A, "add website ferien-am-see.de"))
        url = "https://www.ferien-am-see.de/haus/1"
        adapter_a = self.registry.detect(url, SCOPE_A)
        self.assertEqual(adapter_a.adapter_id, "host:ferien-am-see.de")
        self.assertIsInstance(adapter_a.delegate, JsonLdAdapter)
        self.assertEqual(self.registry.detect(url, SCOPE_B).adapter_id, "json_ld")
        self.assertIn("ferien-am-see.de", self.say(GROUP_A, "websites"))
        self.assertNotIn("ferien-am-see.de", self.say(GROUP_B, "websites"))

    def test_added_websites_reload_per_group_after_restart(self) -> None:
        self.say(GROUP_A, "add website ferien-am-see.de")
        fresh = ScraperRegistry()
        load_custom_hosts(self.storage, fresh)
        url = "https://ferien-am-see.de/haus/1"
        self.assertEqual(fresh.detect(url, SCOPE_A).adapter_id, "host:ferien-am-see.de")
        self.assertEqual(fresh.detect(url, SCOPE_B).adapter_id, "json_ld")

    # FR8
    def test_manual_check_reads_only_the_asking_groups_rentals(self) -> None:
        self.add_listing(SCOPE_A, "Haus A")
        self.add_listing(SCOPE_B, "Haus B")
        read: list[str] = []

        def fake_scrape(url, check_in, check_out, guests, adapter_id=None, scope_id=""):
            read.append(url)
            return ScrapeResult(available=True, total_price=1100.0)

        with mock.patch.object(self.registry, "scrape", side_effect=fake_scrape):
            reply = self.say(GROUP_A, "check")
        self.assertEqual(read, ["https://example.com/Haus A"])
        self.assertIn("Haus A", reply)
        self.assertNotIn("Haus B", reply)
        # Group B's rental was not read, so its change is still there for the nightly run to announce.
        row_b = self.storage.list_listings(SCOPE_B)[0]
        self.assertEqual(row_b["total_price"], 1200.0)


if __name__ == "__main__":
    unittest.main()
