from __future__ import annotations

import json
import os
import threading
import unittest
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import browser_fetch
import llm_extract
import scrapers
from scrape_types import ScrapeResult
from scrapers import ScraperRegistry
from test_llm_extract import CHECK_IN, CHECK_OUT, FakeLlm, StubAdapter, answer

EMPTY_PAGE = "<html><body><h1>Haus Seeblick</h1><div id='price'>Preis wird geladen…</div></body></html>"
RENDERED_PAGE = """<html><body><h1>Haus Seeblick</h1>
<div id='price'>1.234,50 € für 7 Nächte</div><div>Ihr Zeitraum ist verfügbar</div></body></html>"""


class FlattenTests(unittest.TestCase):
    def test_keeps_price_paths_only(self) -> None:
        data = {
            "offer": {"pricing": {"total": 1234.5, "currency": "EUR", "perNight": 176.36}, "isAvailable": True},
            "images": [{"url": "a.jpg"}],
            "description": "Schönes Haus",
        }
        lines = browser_fetch.flatten_relevant(data)
        self.assertIn("offer.pricing.total: 1234.5", lines)
        self.assertIn('offer.pricing.currency: "EUR"', lines)
        self.assertIn("offer.isAvailable: true", lines)
        self.assertFalse(any("images" in line or "description" in line for line in lines))

    def test_summary_skips_unrelated_and_huge_responses(self) -> None:
        self.assertIsNone(browser_fetch.summarize_json_response("https://x/api/user", json.dumps({"name": "Mo"})))
        self.assertIsNone(browser_fetch.summarize_json_response("https://x/api", "not json price"))
        self.assertIsNone(browser_fetch.summarize_json_response("https://x/api", '{"price": "' + "x" * 500_000 + '"}'))
        summary = browser_fetch.summarize_json_response("https://x.example/api/price?id=1", json.dumps({"price": {"total": 99}}))
        self.assertTrue(summary.startswith("[/api/price?id=1]"))
        self.assertIn("price.total: 99", summary)

    def test_captured_numbers_count_as_on_page(self) -> None:
        captured = ["[/api/price]\nprice.total: 1234.5\nprice.available: true"]
        text = llm_extract.page_text(EMPTY_PAGE, captured=captured)
        self.assertIn("price.total: 1234.5", text)
        values, _ = llm_extract.validate({"total_price": 1234.5}, text, CHECK_IN, CHECK_OUT)
        self.assertEqual(values["total_price"], 1234.5)


class TwoStepTests(unittest.TestCase):
    """Plain page first; browser only when price/availability are still missing."""

    def setUp(self) -> None:
        self.addCleanup(llm_extract.set_client, None)
        patcher = mock.patch.object(scrapers, "_request_text", return_value=EMPTY_PAGE)
        self.fetch = patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {"RENTAL_BROWSER_ENABLED": "true"})
        env.start()
        self.addCleanup(env.stop)
        self.registry = ScraperRegistry()
        self.registry._builtin = [StubAdapter(ScrapeResult(error="No vacation rental JSON-LD found."))]

    def scrape(self) -> ScrapeResult:
        return self.registry.scrape("https://x.example/1", CHECK_IN, CHECK_OUT, 4)

    def by_page(self, empty_reply: str, rendered_reply: str | None) -> FakeLlm:
        class ByPage(FakeLlm):
            def complete(self, messages):
                self.calls.append(messages)
                return rendered_reply if "1.234,50" in messages[-1]["content"] else empty_reply

        fake = ByPage(None)
        llm_extract.set_client(fake)
        return fake

    def nothing(self) -> str:
        return answer(available=None, availability_evidence=None, price_per_night=None, total_price=None,
                      cleaning_fee=None, bedrooms=None, bathrooms=None, guests_max=None)

    def test_browser_fills_what_plain_page_lacked(self) -> None:
        fake = self.by_page(self.nothing(), answer(price_per_night=None, cleaning_fee=None))
        rendered = browser_fetch.RenderedPage(url="https://x.example/1", html=RENDERED_PAGE)
        with mock.patch.object(browser_fetch, "render", return_value=rendered) as render:
            result = self.scrape()
        render.assert_called_once()
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(result.total_price, 1234.5)
        self.assertTrue(result.available)
        self.assertFalse(result.fallback_failed)

    def test_plain_page_enough_skips_browser(self) -> None:
        self.fetch.return_value = RENDERED_PAGE
        self.by_page(self.nothing(), answer(price_per_night=None, cleaning_fee=None))
        with mock.patch.object(browser_fetch, "render") as render:
            result = self.scrape()
        render.assert_not_called()
        self.assertEqual(result.total_price, 1234.5)

    def test_browser_off_skips_browser(self) -> None:
        self.by_page(self.nothing(), None)
        with mock.patch.dict(os.environ, {"RENTAL_BROWSER_ENABLED": "false"}), mock.patch.object(browser_fetch, "render") as render:
            result = self.scrape()
        render.assert_not_called()
        self.assertFalse(result.fallback_failed)  # LLM answered; the page simply has no price

    def test_browser_failure_flags_result(self) -> None:
        self.by_page(self.nothing(), None)
        with mock.patch.object(browser_fetch, "render", return_value=None):
            self.assertTrue(self.scrape().fallback_failed)

    def test_llm_down_skips_browser(self) -> None:
        llm_extract.set_client(FakeLlm(None))
        with mock.patch.object(browser_fetch, "render") as render:
            result = self.scrape()
        render.assert_not_called()
        self.assertTrue(result.fallback_failed)

    def test_blocked_plain_fetch_uses_browser(self) -> None:
        self.fetch.return_value = None
        self.by_page(self.nothing(), answer(price_per_night=None, cleaning_fee=None))
        rendered = browser_fetch.RenderedPage(url="https://x.example/1", html=RENDERED_PAGE)
        with mock.patch.object(browser_fetch, "render", return_value=rendered):
            result = self.scrape()
        self.assertEqual(result.total_price, 1234.5)
        self.assertFalse(result.fallback_failed)

    def test_captured_json_reaches_the_model(self) -> None:
        fake = self.by_page(self.nothing(), None)
        rendered = browser_fetch.RenderedPage(url="u", html=EMPTY_PAGE, captured=["[/api/p]\nprice.total: 777"])
        with mock.patch.object(browser_fetch, "render", return_value=rendered):
            self.scrape()
        self.assertIn("price.total: 777", fake.calls[-1][-1]["content"])


# --------------------------------------------------------------------------- real browser, local site

SITE = """<!doctype html><html><body>
<div id="consent" style="position:fixed;inset:0;background:#fff">
  Wir verwenden Cookies. <button>Einstellungen</button> <button id="ok">Alle akzeptieren</button>
</div>
<h1>Haus Seeblick</h1><div id="price">Preis wird geladen…</div>
<script>
document.getElementById('ok').onclick = async () => {
  document.getElementById('consent').remove();
  const r = await fetch('/api/price?arrival=2026-12-20');
  const d = await r.json();
  document.getElementById('price').textContent = d.offer.total.toFixed(2).replace('.', ',') + ' € gesamt';
};
</script></body></html>"""


class _Site(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.startswith("/api/price"):
            body, kind = json.dumps({"offer": {"total": 1499.0, "currency": "EUR", "isAvailable": True}}), "application/json"
        else:
            body, kind = SITE, "text/html; charset=utf-8"
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:
        pass


def _playwright_ready() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            playwright.chromium.launch(headless=True).close()
        return True
    except Exception:
        return False


@unittest.skipUnless(_playwright_ready(), "Playwright + Chromium not installed")
class RealBrowserTests(unittest.TestCase):
    def test_cookie_banner_and_price_capture(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Site)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        rendered = browser_fetch.render(f"http://127.0.0.1:{server.server_port}/haus/1")
        self.assertIsNotNone(rendered)
        self.assertTrue(rendered.cookie_banner_clicked)
        self.assertIn("1499,00 € gesamt", rendered.html)
        self.assertEqual(len(rendered.captured), 1)
        self.assertIn("offer.total: 1499.0", rendered.captured[0])
        self.assertIn("offer.isAvailable: true", rendered.captured[0])


if __name__ == "__main__":
    unittest.main()
