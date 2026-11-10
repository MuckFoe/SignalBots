"""LLM fallback for rental pages the built-in scrapers can't read.

Flow: page HTML -> compact text (visible text, JSON-LD, meta tags) -> local LLM
(OpenAI-compatible, JSON-schema output) -> validated fields -> merged into the
ScrapeResult. The LLM only fills fields the deterministic scrapers left empty and
never overrides them.

Anti-hallucination: every money value must literally appear in the page text, and
"available" needs a quote from the page as evidence. Anything that fails is
dropped (= unknown), which is exactly today's behaviour.

Config (root .env, shared with chore-bot's LLM_BASE_URL / LLM_MODEL):
  RENTAL_LLM_ENABLED=false          master switch
  LLM_BASE_URL / LLM_MODEL          same Mac mini as chore-bot
  RENTAL_LLM_MODEL                  optional, overrides LLM_MODEL for this bot
  RENTAL_LLM_TIMEOUT_SECONDS=90     page prompts are long; polling is in the background
  RENTAL_LLM_MAX_CHARS=24000        page text budget sent to the model

Try it against a real page:
  python llm_extract.py <url> 2026-12-20 2026-12-27 4
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser

from scrape_types import ScrapeResult

logger = logging.getLogger(__name__)

# Fields the LLM may fill. Coordinates are deliberately excluded: a model guessing
# lat/lon would silently produce wrong drive times.
LLM_FIELDS = [
    "available",
    "price_per_night",
    "total_price",
    "currency",
    "cleaning_fee",
    "min_nights",
    "title",
    "location_name",
    "guests_max",
    "bedrooms",
    "bathrooms",
    "rating",
    "review_count",
    "pets_allowed",
    "property_type",
]
MONEY_FIELDS = ("price_per_night", "total_price", "cleaning_fee")


def _nullable(kind: str) -> dict:
    return {"type": [kind, "null"]}


RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "available": _nullable("boolean"),
        "availability_evidence": _nullable("string"),
        "price_per_night": _nullable("number"),
        "total_price": _nullable("number"),
        "prices_for_requested_dates": _nullable("boolean"),
        "currency": _nullable("string"),
        "cleaning_fee": _nullable("number"),
        "min_nights": _nullable("integer"),
        "title": _nullable("string"),
        "location_name": _nullable("string"),
        "guests_max": _nullable("integer"),
        "bedrooms": _nullable("integer"),
        "bathrooms": _nullable("number"),
        "rating": _nullable("number"),
        "review_count": _nullable("integer"),
        "pets_allowed": _nullable("boolean"),
        "property_type": _nullable("string"),
    },
    "required": [
        "available",
        "availability_evidence",
        "price_per_night",
        "total_price",
        "prices_for_requested_dates",
        "currency",
        "cleaning_fee",
        "min_nights",
        "title",
        "location_name",
        "guests_max",
        "bedrooms",
        "bathrooms",
        "rating",
        "review_count",
        "pets_allowed",
        "property_type",
    ],
}

SYSTEM_PROMPT = """You extract facts about ONE vacation rental from the text of its web page.
Answer with a single JSON object matching the schema. Use null for anything the page does not state.
The page text may include PRICE DATA the page loaded in the background: JSON leaves as `path: value`.
Prefer it for prices and availability when it clearly belongs to this listing and the requested stay
(e.g. a total, a nightly rate, isAvailable/bookable flags); ignore data about other listings.
Never guess, never compute values the page doesn't show (except: price_per_night = total / nights
when the page shows only a total for the requested stay and the number of nights).

Fields:
- available: true/false ONLY if the page clearly says whether the requested dates can be booked
  (e.g. "available", "verfügbar", "book now" with a price for exactly these dates; or "not available",
  "ausgebucht", "belegt", "dates unavailable"). Otherwise null.
- availability_evidence: the exact short phrase copied from the page that justifies "available"
  (null if available is null).
- price_per_night: nightly rent as shown on the page (number only, no currency sign).
- total_price: total price for the requested stay, if shown.
- prices_for_requested_dates: true if the prices are for the requested dates/guests, false if they are
  generic ("from 89 €/night", "ab"), null if unclear.
- currency: ISO code, e.g. EUR, CHF, USD.
- cleaning_fee: final cleaning fee (Endreinigung) if shown.
- min_nights: minimum stay in nights (Mindestaufenthalt).
- title, location_name (town/region, country), property_type (e.g. house, apartment, chalet).
- guests_max (max. Personen), bedrooms (Schlafzimmer), bathrooms (Badezimmer), rating (as shown,
  e.g. 4.8), review_count (Bewertungen), pets_allowed (Haustiere erlaubt).
Numbers: write 1.234,50 € as 1234.5. Ignore prices of other, similar or recommended listings."""


# --------------------------------------------------------------------------- HTML -> text


class _PageText(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template", "iframe", "head"}
    BLOCK = {"p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "td", "th", "dt", "dd"}
    META_KEYS = {"og:title", "og:description", "description", "og:price:amount", "og:price:currency",
                 "product:price:amount", "product:price:currency", "twitter:title", "twitter:description"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.json_ld: list[str] = []
        self.meta: list[str] = []
        self.title = ""
        self._skip_depth = 0
        self._in_json_ld = False
        self._in_title = False
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "") for key, value in attrs}
        if tag == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            if key in self.META_KEYS and values.get("content"):
                self.meta.append(f"{key}: {values['content'].strip()}")
            return
        if tag == "title":
            self._in_title = True
            return
        if tag == "script" and "ld+json" in values.get("type", "").lower():
            self._in_json_ld = True
            self._buffer = []
            return
        if tag in self.SKIP:
            self._skip_depth += 1
            return
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_json_ld:
            self._in_json_ld = False
            self.json_ld.append("".join(self._buffer).strip())
        elif tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._buffer.append(data)
        elif self._in_title:
            self.title += data
        elif not self._skip_depth:
            self.parts.append(data)


def _squash(text: str) -> str:
    lines = (re.sub(r"[ \t ]+", " ", line).strip() for line in text.splitlines())
    out: list[str] = []
    for line in lines:
        if line and (not out or out[-1] != line):
            out.append(line)
    return "\n".join(out)


KEYWORDS = re.compile(
    r"€|eur\b|chf|\$|£|preis|price|nacht|night|gesamt|total|verfügbar|available|unavailable|ausgebucht|belegt|"
    r"reinigung|cleaning|mindest|minimum|personen|guests|schlafzimmer|bedroom|bad|bath|haustier|pet",
    re.IGNORECASE,
)


def _fit(text: str, max_chars: int) -> str:
    """Keep the page start (title, key facts) plus the lines around price/availability keywords."""
    if len(text) <= max_chars:
        return text
    lines = text.split("\n")
    keep: set[int] = set()
    used = 0
    head_budget = max_chars // 4
    for index, line in enumerate(lines):
        if used + len(line) > head_budget:
            break
        keep.add(index)
        used += len(line) + 1
    for index, line in enumerate(lines):
        if not KEYWORDS.search(line):
            continue
        for near in range(max(0, index - 2), min(len(lines), index + 3)):
            if near in keep:
                continue
            if used + len(lines[near]) > max_chars:
                break
            keep.add(near)
            used += len(lines[near]) + 1
        if used >= max_chars:
            break
    out: list[str] = []
    last = -2
    for index in sorted(keep):
        if index != last + 1:
            out.append("…")
        out.append(lines[index])
        last = index
    return "\n".join(out)


def page_text(html: str, max_chars: int = 24000, captured: list[str] | None = None) -> str:
    """Compact, model-friendly view of a page: title, meta, JSON-LD, captured price JSON, visible text."""
    parser = _PageText()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # malformed HTML: use what was parsed so far
        logger.debug("HTML parse stopped early", exc_info=True)
    sections = []
    if parser.title.strip():
        sections.append(f"PAGE TITLE: {_squash(parser.title)}")
    if parser.meta:
        sections.append("META:\n" + "\n".join(parser.meta))
    json_ld = [block for block in parser.json_ld if block][:3]
    if json_ld:
        sections.append("STRUCTURED DATA (JSON-LD):\n" + "\n".join(block[:4000] for block in json_ld))
    if captured:
        joined = "\n\n".join(captured)[: max_chars // 3]
        sections.append("PRICE DATA THE PAGE LOADED IN THE BACKGROUND (path: value):\n" + joined)
    header = "\n\n".join(sections)
    body = _squash("".join(parser.parts))
    budget = max(2000, max_chars - len(header) - 20)
    return f"{header}\n\nPAGE TEXT:\n{_fit(body, budget)}".strip()


# --------------------------------------------------------------------------- LLM client


class LlmClient:
    """POSTs to an OpenAI-compatible /chat/completions endpoint. Returns the message text or None."""

    def __init__(self, base_url: str, model: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def complete(self, messages: list[dict]) -> str | None:
        import requests

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "rental", "schema": RESPONSE_SCHEMA, "strict": True},
            },
        }
        try:
            response = requests.post(f"{self.base_url}/chat/completions", json=payload, timeout=self.timeout)
            if response.status_code == 400:
                logger.warning("LLM rejected json_schema, retrying in json_object mode: %s", response.text[:200])
                payload["response_format"] = {"type": "json_object"}
                response = requests.post(f"{self.base_url}/chat/completions", json=payload, timeout=self.timeout)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as exc:  # fail open
            logger.warning("Rental LLM call failed: %s", exc)
            return None


_client_override: object | None = None


def set_client(client: object | None) -> None:
    """Tests inject a fake with .complete(messages) -> str | None. None restores env config."""
    global _client_override
    _client_override = client


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


def get_client() -> object | None:
    if _client_override is not None:
        return _client_override
    if os.getenv("RENTAL_LLM_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    base_url = os.getenv("LLM_BASE_URL", "").strip()
    model = (os.getenv("RENTAL_LLM_MODEL", "") or os.getenv("LLM_MODEL", "")).strip()
    if not base_url or not model:
        return None
    return LlmClient(base_url, model, _env_float("RENTAL_LLM_TIMEOUT_SECONDS", 90.0))


def enabled() -> bool:
    return get_client() is not None


# --------------------------------------------------------------------------- extraction


def build_messages(text: str, url: str, check_in: date, check_out: date, guests: int) -> list[dict]:
    nights = max(1, (check_out - check_in).days)
    user = (
        f"URL: {url}\n"
        f"Requested stay: check-in {check_in.isoformat()}, check-out {check_out.isoformat()} "
        f"({nights} nights), {guests} guests.\n\n"
        f"{text}"
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def _parse_json(raw: str) -> dict | None:
    cleaned = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _digits_only(text: str) -> str:
    return re.sub(r"[^\d]", "", text)


def number_on_page(value: float, text: str) -> bool:
    """True if `value` is written on the page in some usual format (1234, 1.234, 1,234.00, 1 234,50 …)."""
    if value <= 0:
        return False
    numbers = re.findall(r"\d[\d.,'  ]*\d|\d", text)
    for token in numbers:
        token = token.replace(" ", " ").replace("'", "").replace(" ", "")
        for decimal in (",", "."):
            thousands = "." if decimal == "," else ","
            candidate = token.replace(thousands, "")
            if candidate.count(decimal) > 1:
                continue
            try:
                parsed = float(candidate.replace(decimal, "."))
            except ValueError:
                continue
            if abs(parsed - value) < 0.005:
                return True
    return False


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


@dataclass
class Extraction:
    values: dict
    dropped: list[str]
    latency_ms: int


def validate(data: dict, text: str, check_in: date, check_out: date) -> tuple[dict, list[str]]:
    """Keep only plausible, page-backed values. Returns (values, names of dropped fields)."""
    values: dict = {}
    dropped: list[str] = []
    nights = max(1, (check_out - check_in).days)

    def drop(name: str) -> None:
        if data.get(name) is not None:
            dropped.append(name)

    for name in MONEY_FIELDS:
        value = data.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 < value < 1_000_000:
            drop(name)
            continue
        on_page = number_on_page(float(value), text)
        if not on_page and name == "price_per_night" and isinstance(data.get("total_price"), (int, float)):
            # derived nightly price: allowed when the total is on the page and the division matches
            on_page = number_on_page(float(data["total_price"]), text) and abs(float(data["total_price"]) / nights - value) < 1
        if not on_page:
            drop(name)
            continue
        values[name] = round(float(value), 2)

    if data.get("prices_for_requested_dates") is False and "total_price" in values:
        # a generic "from" price is not the total of this stay
        values.pop("total_price")
        dropped.append("total_price")

    evidence = data.get("availability_evidence")
    if isinstance(data.get("available"), bool):
        if isinstance(evidence, str) and evidence.strip() and _norm(evidence) in _norm(text):
            values["available"] = data["available"]
        else:
            dropped.append("available")

    currency = data.get("currency")
    if isinstance(currency, str) and re.fullmatch(r"[A-Za-z]{3}", currency.strip()):
        values["currency"] = currency.strip().upper()

    for name, low, high in (("min_nights", 1, 365), ("guests_max", 1, 100), ("bedrooms", 0, 50),
                            ("review_count", 0, 1_000_000)):
        value = data.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and low <= value <= high:
            values[name] = int(value)
        else:
            drop(name)
    for name, low, high in (("bathrooms", 0, 50), ("rating", 0, 10)):
        value = data.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and low <= value <= high:
            values[name] = float(value)
        else:
            drop(name)
    if isinstance(data.get("pets_allowed"), bool):
        values["pets_allowed"] = data["pets_allowed"]
    for name in ("title", "location_name", "property_type"):
        value = data.get(name)
        if isinstance(value, str) and value.strip():
            values[name] = value.strip()[:200]
    return values, dropped


def extract(
    html: str,
    url: str,
    check_in: date,
    check_out: date,
    guests: int,
    client: object | None = None,
    captured: list[str] | None = None,
) -> Extraction | None:
    """Run the LLM over a page. None when the LLM is off, down, or answered garbage."""
    client = client or get_client()
    if client is None or not html:
        return None
    text = page_text(html, int(_env_float("RENTAL_LLM_MAX_CHARS", 24000)), captured)
    started = time.monotonic()
    raw = client.complete(build_messages(text, url, check_in, check_out, guests))
    latency_ms = int((time.monotonic() - started) * 1000)
    if raw is None:
        return None
    data = _parse_json(raw)
    if data is None:
        logger.warning("Rental LLM returned non-JSON for %s: %.200s", url, raw)
        return None
    values, dropped = validate(data, text, check_in, check_out)
    logger.info("Rental LLM %s: %d fields in %d ms, dropped %s", url, len(values), latency_ms, dropped or "-")
    return Extraction(values=values, dropped=dropped, latency_ms=latency_ms)


def needs_llm(result: ScrapeResult) -> bool:
    """The deterministic scraper missed price or availability."""
    return result.available is None or (result.price_per_night is None and result.total_price is None)


def merge(result: ScrapeResult, extraction: Extraction) -> ScrapeResult:
    """Fill only empty fields; deterministic values always win."""
    filled = []
    for name, value in extraction.values.items():
        if name == "currency":
            continue
        if getattr(result, name) is None:
            setattr(result, name, value)
            filled.append(name)
    money_filled = any(name in filled for name in MONEY_FIELDS)
    if money_filled and "currency" in extraction.values:
        result.currency = extraction.values["currency"]
    if result.error and (result.available is not None or result.price_per_night is not None or result.total_price is not None):
        result.error = None
    return result


if __name__ == "__main__":
    import sys

    from scrapers import _request_text
    from utils import parse_date

    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) != 5:
        sys.exit("usage: python llm_extract.py <url> <check-in YYYY-MM-DD> <check-out YYYY-MM-DD> <guests>")
    page_url, arrive, leave, people = sys.argv[1], parse_date(sys.argv[2]), parse_date(sys.argv[3]), int(sys.argv[4])
    if arrive is None or leave is None:
        sys.exit("dates must be YYYY-MM-DD")
    captured_json = None
    if os.getenv("USE_BROWSER"):
        import browser_fetch

        rendered = browser_fetch.render(page_url)
        if rendered is None:
            sys.exit("browser render failed")
        page, captured_json = rendered.html, rendered.captured
    else:
        page = _request_text(page_url)
    if not page:
        sys.exit("could not fetch the page (blocked or JS-only? try USE_BROWSER=1)")
    if os.getenv("SHOW_TEXT"):
        print(page_text(page, captured=captured_json))
    found = extract(page, page_url, arrive, leave, people, captured=captured_json)
    print(json.dumps(found.__dict__ if found else None, indent=2, ensure_ascii=False))
