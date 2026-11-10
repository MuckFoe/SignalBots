"""Headless-browser fetch for pages that only show prices after JavaScript runs.

Used by the LLM fallback (scrapers.ScraperRegistry._llm_fill) when a plain HTTP GET
gave the model no price/availability. Runs Chromium inside the rental-bot container:

1. open the page (images, media and fonts blocked to save RAM and bandwidth),
2. click away the cookie banner (known consent tools first, then "Alle akzeptieren"-type buttons),
3. wait for the page to settle,
4. return the rendered DOM plus the price-related JSON the page fetched in the
   background ("price capture"), flattened to `path: value` lines the LLM can read
   and the validator can check numbers against.

One page at a time (a lock), a fresh browser per page: memory is freed after every
render instead of growing over a poll run.

Config:
  RENTAL_BROWSER_ENABLED=false          master switch (also needs the LLM fallback on)
  RENTAL_BROWSER_TIMEOUT_SECONDS=45     whole render incl. waiting for the page to settle

Try it:  python browser_fetch.py <url>
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Consent tools used by most EU sites: OneTrust, Cookiebot, Usercentrics, Didomi, Borlabs, Quantcast, TrustArc.
CONSENT_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "#CybotCookiebotDialogBodyButtonAccept",
    "[data-testid='uc-accept-all-button']",
    "#didomi-notice-agree-button",
    "a._brlbs-btn-accept-all",
    ".qc-cmp2-summary-buttons button[mode='primary']",
    "#truste-consent-button",
    "button[data-cookiebanner='accept_button']",
]
# Button texts, most specific first. Never "Einstellungen"/"settings"/"ablehnen".
CONSENT_TEXTS = [
    re.compile(r"^\s*(alle\s+(cookies\s+)?(akzeptieren|zulassen|erlauben|annehmen)|accept\s+all(\s+cookies)?|allow\s+all(\s+cookies)?|tout\s+accepter|accepteer\s+alles?|accetta\s+tutt[io])\s*$", re.I),
    re.compile(r"^\s*(akzeptieren|annehmen|zustimmen|einverstanden|alles\s+klar|ok(ay)?|verstanden|accept(\s+cookies)?|agree|i\s+agree|got\s+it|accepter|accepteren|accetta)\s*$", re.I),
]

PRICE_KEY = re.compile(
    r"price|preis|amount|total|gesamt|sum|cost|rate|night|nacht|fee|cleaning|reinigung|currency|w(ae|ä)hrung|"
    r"avail|verfueg|verfüg|bookable|isbookable|status|minstay|min_?nights|mindest|ppn|discount|rabatt",
    re.I,
)
MAX_BODY_BYTES = 400_000
MAX_LINES_PER_RESPONSE = 80
MAX_RESPONSES = 8

_render_lock = threading.Lock()


@dataclass
class RenderedPage:
    url: str
    html: str
    captured: list[str] = field(default_factory=list)  # one block of `path: value` lines per JSON response
    cookie_banner_clicked: bool = False


def enabled() -> bool:
    return os.getenv("RENTAL_BROWSER_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _timeout_ms() -> int:
    try:
        return int(float(os.getenv("RENTAL_BROWSER_TIMEOUT_SECONDS", "") or 45) * 1000)
    except ValueError:
        return 45_000


# --------------------------------------------------------------------------- price capture


def flatten_relevant(data: object, prefix: str = "", out: list[str] | None = None, limit: int = MAX_LINES_PER_RESPONSE) -> list[str]:
    """`path: value` lines for leaves whose path looks price/availability related."""
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(data, dict):
        for key, value in data.items():
            flatten_relevant(value, f"{prefix}.{key}" if prefix else str(key), out, limit)
    elif isinstance(data, list):
        for index, value in enumerate(data[:30]):
            flatten_relevant(value, f"{prefix}[{index}]", out, limit)
    elif data is None or (isinstance(data, str) and len(data) > 80):
        pass  # empty or prose: not a price fact
    elif PRICE_KEY.search(prefix):
        out.append(f"{prefix}: {json.dumps(data, ensure_ascii=False)}")
    return out


def summarize_json_response(url: str, body: str) -> str | None:
    if len(body) > MAX_BODY_BYTES or not PRICE_KEY.search(body):
        return None
    try:
        data = json.loads(body)
    except ValueError:
        return None
    lines = flatten_relevant(data)
    if not lines or not any(re.search(r"\d", line.split(":", 1)[1]) for line in lines):
        return None
    path = re.sub(r"^https?://[^/]+", "", url)[:150]
    return f"[{path}]\n" + "\n".join(lines)


# --------------------------------------------------------------------------- cookie banner


def dismiss_cookie_banner(page) -> bool:
    """Click the consent button if there is one. Checks every frame (some banners live in iframes)."""
    for frame in page.frames:
        for selector in CONSENT_SELECTORS:
            try:
                locator = frame.locator(selector).first
                if locator.count() and locator.is_visible():
                    locator.click(timeout=2000)
                    return True
            except Exception:
                continue
    for pattern in CONSENT_TEXTS:
        for frame in page.frames:
            try:
                locator = frame.get_by_role("button", name=pattern).first
                if locator.count() and locator.is_visible():
                    locator.click(timeout=2000)
                    return True
            except Exception:
                continue
    return False


# --------------------------------------------------------------------------- render


def render(url: str) -> RenderedPage | None:
    """Rendered page + captured price JSON, or None (browser missing, blocked, timeout)."""
    if not _render_lock.acquire(timeout=_timeout_ms() / 1000 * 2):
        logger.warning("Browser busy, skipping %s", url)
        return None
    try:
        return _render(url)
    except Exception as exc:
        logger.warning("Browser render failed for %s: %s", url, exc)
        return None
    finally:
        _render_lock.release()


def _render(url: str) -> RenderedPage | None:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright not installed; browser fetch unavailable")
        return None

    timeout = _timeout_ms()
    json_responses = []

    def on_response(response) -> None:
        try:
            if response.request.resource_type not in ("xhr", "fetch") or response.status != 200:
                return
            if "json" in (response.headers.get("content-type") or "").lower():
                json_responses.append(response)
        except Exception:
            pass

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--disable-gpu", "--no-zygote", "--disable-extensions"],
        )
        try:
            context = browser.new_context(
                user_agent=USER_AGENT,
                locale="de-DE",
                timezone_id="Europe/Berlin",
                viewport={"width": 1366, "height": 900},
                extra_http_headers={"Accept-Language": "de-DE,de;q=0.9,en;q=0.8"},
            )
            context.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in ("image", "media", "font")
                else route.continue_(),
            )
            page = context.new_page()
            page.set_default_timeout(timeout)
            page.on("response", on_response)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            _settle(page, PlaywrightTimeout, 8000)
            clicked = dismiss_cookie_banner(page)
            if clicked:
                logger.info("Cookie banner dismissed on %s", url)
                _settle(page, PlaywrightTimeout, 8000)
            # prices often load when the booking widget scrolls into view
            page.mouse.wheel(0, 1500)
            _settle(page, PlaywrightTimeout, 5000)

            captured = []
            for response in json_responses:
                if len(captured) >= MAX_RESPONSES:
                    break
                try:
                    summary = summarize_json_response(response.url, response.text())
                except Exception:
                    continue
                if summary:
                    captured.append(summary)
            html = page.content()
            final_url = page.url
        finally:
            browser.close()
    logger.info("Rendered %s: %d chars, %d price responses", url, len(html), len(captured))
    return RenderedPage(url=final_url, html=html, captured=captured, cookie_banner_clicked=clicked)


def _settle(page, timeout_error, wait_ms: int) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=wait_ms)
    except timeout_error:
        pass  # sites with polling/analytics never go idle; continue with what's there
    page.wait_for_timeout(500)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) != 2:
        sys.exit("usage: python browser_fetch.py <url>")
    rendered = render(sys.argv[1])
    if rendered is None:
        sys.exit("render failed")
    print(f"final url: {rendered.url}\ncookie banner clicked: {rendered.cookie_banner_clicked}\nhtml: {len(rendered.html)} chars")
    for block in rendered.captured:
        print(f"\n{block}")
