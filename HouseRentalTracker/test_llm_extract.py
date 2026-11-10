from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date
from unittest import mock

import llm_extract
import scrapers
from poller import Poller
from scrape_types import ScrapeResult
from scrapers import ScraperRegistry
from storage import Storage

CHECK_IN, CHECK_OUT = date(2026, 12, 20), date(2026, 12, 27)

PAGE = """<html><head><title>Haus Seeblick – Ferienhaus am Tegernsee</title>
<meta property="og:description" content="Gemütliches Ferienhaus für 6 Personen">
<script>window.tracking = {"price": 999};</script>
<style>.x{color:red}</style></head>
<body><h1>Haus Seeblick</h1>
<p>Bad Wiessee, Bayern, Deutschland</p>
<ul><li>6 Personen</li><li>3 Schlafzimmer</li><li>2 Badezimmer</li></ul>
<div class="price">1.234,50&nbsp;€ für 7 Nächte</div>
<div>176,36 € / Nacht · Endreinigung 90 €</div>
<div>Ihr Zeitraum ist verfügbar</div>
<div class="similar">Ähnliche Unterkunft ab 79 € / Nacht</div>
</body></html>"""


def answer(**overrides) -> str:
    data = {name: None for name in llm_extract.RESPONSE_SCHEMA["required"]}
    data.update(
        available=True,
        availability_evidence="Ihr Zeitraum ist verfügbar",
        price_per_night=176.36,
        total_price=1234.5,
        prices_for_requested_dates=True,
        currency="EUR",
        cleaning_fee=90,
        title="Haus Seeblick",
        location_name="Bad Wiessee, Bayern, Deutschland",
        guests_max=6,
        bedrooms=3,
        bathrooms=2,
    )
    data.update(overrides)
    return json.dumps(data)


class FakeLlm:
    def __init__(self, reply: str | None) -> None:
        self.reply = reply
        self.calls: list[list[dict]] = []

    def complete(self, messages: list[dict]) -> str | None:
        self.calls.append(messages)
        return self.reply


class PageTextTests(unittest.TestCase):
    def test_keeps_visible_text_and_meta_drops_scripts(self) -> None:
        text = llm_extract.page_text(PAGE)
        self.assertIn("PAGE TITLE: Haus Seeblick", text)
        self.assertIn("og:description: Gemütliches Ferienhaus", text)
        self.assertIn("1.234,50 € für 7 Nächte", text)
        self.assertNotIn("window.tracking", text)
        self.assertNotIn("color:red", text)

    def test_keeps_json_ld(self) -> None:
        html = '<script type="application/ld+json">{"@type": "VacationRental", "name": "X"}</script><p>hi</p>'
        self.assertIn('"VacationRental"', llm_extract.page_text(html))

    def test_long_pages_keep_price_lines(self) -> None:
        filler = "".join(f"<p>Beschreibung Zeile {i} mit viel Text über die Umgebung.</p>" for i in range(3000))
        html = f"<body>{filler}<p>Gesamtpreis 2.100 €</p>{filler}</body>"
        text = llm_extract.page_text(html, max_chars=6000)
        self.assertLessEqual(len(text), 7000)
        self.assertIn("Gesamtpreis 2.100 €", text)


class ValidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = llm_extract.page_text(PAGE)

    def validate(self, **overrides):
        return llm_extract.validate(json.loads(answer(**overrides)), self.text, CHECK_IN, CHECK_OUT)

    def test_page_backed_values_are_kept(self) -> None:
        values, dropped = self.validate()
        self.assertEqual(values["total_price"], 1234.5)
        self.assertEqual(values["price_per_night"], 176.36)
        self.assertEqual(values["cleaning_fee"], 90)
        self.assertTrue(values["available"])
        self.assertEqual(dropped, [])

    def test_price_not_on_page_is_dropped(self) -> None:
        values, dropped = self.validate(price_per_night=150)
        self.assertNotIn("price_per_night", values)
        self.assertIn("price_per_night", dropped)

    def test_nightly_price_derived_from_total_is_allowed(self) -> None:
        values, _ = self.validate(price_per_night=176.36)
        self.assertEqual(values["price_per_night"], 176.36)
        page = "<p>Gesamt 1.400 € für 7 Nächte</p><p>verfügbar</p>"
        values, _ = llm_extract.validate(
            {"price_per_night": 200, "total_price": 1400}, llm_extract.page_text(page), CHECK_IN, CHECK_OUT
        )
        self.assertEqual(values["price_per_night"], 200)

    def test_availability_needs_quote_from_page(self) -> None:
        values, dropped = self.validate(availability_evidence="Jetzt buchen!")
        self.assertNotIn("available", values)
        self.assertIn("available", dropped)
        values, _ = self.validate(availability_evidence=None)
        self.assertNotIn("available", values)

    def test_generic_from_price_drops_total(self) -> None:
        values, _ = self.validate(prices_for_requested_dates=False)
        self.assertNotIn("total_price", values)
        self.assertIn("price_per_night", values)

    def test_implausible_numbers_dropped(self) -> None:
        values, _ = self.validate(bedrooms=400, rating=47, price_per_night=-5, currency="Euro")
        for name in ("bedrooms", "rating", "price_per_night", "currency"):
            self.assertNotIn(name, values)

    def test_number_formats(self) -> None:
        for text, value in (("1.234,50 €", 1234.5), ("€1,234.50", 1234.5), ("1 234 €", 1234), ("CHF 1'200.-", 1200), ("89€", 89)):
            self.assertTrue(llm_extract.number_on_page(value, text), text)
        self.assertFalse(llm_extract.number_on_page(1234, "12 Nächte, 34 €"))


class ExtractTests(unittest.TestCase):
    def test_garbage_and_down_return_none(self) -> None:
        self.assertIsNone(llm_extract.extract(PAGE, "u", CHECK_IN, CHECK_OUT, 4, client=FakeLlm(None)))
        self.assertIsNone(llm_extract.extract(PAGE, "u", CHECK_IN, CHECK_OUT, 4, client=FakeLlm("sorry, no")))

    def test_fenced_json_is_accepted(self) -> None:
        result = llm_extract.extract(PAGE, "u", CHECK_IN, CHECK_OUT, 4, client=FakeLlm(f"```json\n{answer()}\n```"))
        self.assertEqual(result.values["total_price"], 1234.5)

    def test_prompt_contains_stay(self) -> None:
        fake = FakeLlm(answer())
        llm_extract.extract(PAGE, "https://x.example/1", CHECK_IN, CHECK_OUT, 4, client=fake)
        user = fake.calls[0][-1]["content"]
        self.assertIn("2026-12-20", user)
        self.assertIn("(7 nights), 4 guests", user)

    def test_merge_never_overrides_scraper(self) -> None:
        extraction = llm_extract.extract(PAGE, "u", CHECK_IN, CHECK_OUT, 4, client=FakeLlm(answer()))
        result = ScrapeResult(title="From API", price_per_night=170.0, error="No vacation rental JSON-LD found.")
        llm_extract.merge(result, extraction)
        self.assertEqual(result.title, "From API")
        self.assertEqual(result.price_per_night, 170.0)
        self.assertEqual(result.total_price, 1234.5)
        self.assertTrue(result.available)
        self.assertIsNone(result.error)


class StubAdapter:
    adapter_id = "stub"
    display_name = "stub"

    def __init__(self, result: ScrapeResult) -> None:
        self.result = result

    def matches(self, url: str) -> bool:
        return True

    def scrape(self, url, check_in, check_out, guests) -> ScrapeResult:
        return ScrapeResult(**{k: v for k, v in self.result.__dict__.items()})


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fetch = mock.patch.object(scrapers, "_request_text", return_value=PAGE)
        self.fetch.start()
        self.addCleanup(self.fetch.stop)
        self.addCleanup(llm_extract.set_client, None)

    def registry(self, result: ScrapeResult) -> ScraperRegistry:
        registry = ScraperRegistry()
        registry._builtin = [StubAdapter(result)]
        return registry

    def test_llm_off_changes_nothing(self) -> None:
        with mock.patch.dict(os.environ, {"RENTAL_LLM_ENABLED": "false"}):
            result = self.registry(ScrapeResult(error="No vacation rental JSON-LD found.")).scrape("https://x", CHECK_IN, CHECK_OUT, 4)
        self.assertIsNone(result.price_per_night)
        self.assertEqual(result.error, "No vacation rental JSON-LD found.")

    def test_complete_scraper_result_skips_llm(self) -> None:
        fake = FakeLlm(answer())
        llm_extract.set_client(fake)
        self.registry(ScrapeResult(available=True, price_per_night=100.0)).scrape("https://x", CHECK_IN, CHECK_OUT, 4)
        self.assertEqual(fake.calls, [])

    def test_missing_price_is_filled(self) -> None:
        llm_extract.set_client(FakeLlm(answer()))
        result = self.registry(ScrapeResult(error="No vacation rental JSON-LD found.")).scrape("https://x", CHECK_IN, CHECK_OUT, 4)
        self.assertEqual(result.total_price, 1234.5)
        self.assertTrue(result.available)
        self.assertIsNone(result.error)
        self.assertFalse(result.fallback_failed)

    def test_llm_down_flags_result(self) -> None:
        llm_extract.set_client(FakeLlm(None))
        result = self.registry(ScrapeResult()).scrape("https://x", CHECK_IN, CHECK_OUT, 4)
        self.assertTrue(result.fallback_failed)


class PollerTests(unittest.TestCase):
    def test_llm_down_keeps_last_known_values_and_does_not_notify(self) -> None:
        storage = Storage(os.path.join(tempfile.mkdtemp(), "r.db"))
        scope = "group:test"
        storage.add_listing(scope, "Seeblick", "https://x.example/1", "stub", CHECK_IN, CHECK_OUT, 4,
                            ScrapeResult(), None, None, added_by="mo")
        row = storage.list_all_active_listings()[0]
        registry = ScraperRegistry()
        registry._builtin = [StubAdapter(ScrapeResult(error="No vacation rental JSON-LD found."))]
        poller = Poller(storage, registry)
        self.addCleanup(llm_extract.set_client, None)

        with mock.patch.object(scrapers, "_request_text", return_value=PAGE):
            llm_extract.set_client(FakeLlm(answer()))
            changed, _ = poller.poll_listing_row(row)
            self.assertTrue(changed)
            row = storage.list_all_active_listings()[0]
            self.assertEqual(row["total_price"], 1234.5)

            llm_extract.set_client(FakeLlm(None))
            changed, _ = poller.poll_listing_row(row)
            self.assertFalse(changed)
            row = storage.list_all_active_listings()[0]
            self.assertEqual(row["total_price"], 1234.5)
            self.assertEqual(row["available"], 1)


if __name__ == "__main__":
    unittest.main()
