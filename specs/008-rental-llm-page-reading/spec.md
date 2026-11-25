# 008 — Rental bot: reading pages with the local LLM and a headless browser

**Status:** draft · written 2026-11-24 from the code
(`HouseRentalTracker/llm_extract.py`, `browser_fetch.py`, `scrapers.py`
`_llm_fill`, `poller.py` `keep_last_known`, `HouseRentalTracker/README.md`).
Design notes: `docs/llm-rental-extract-plan.md`. LLM step live since
2026-11-11; the browser step is built but off.

## Summary

When a scraper misses the price or the availability, the page is handed to the
local model on the Mac mini. Only values that can be found on the page are
kept. A headless browser step for JavaScript-loaded pages exists but is
switched off.

## Functional requirements

- **FR1** — The LLM step runs only when a scraper result lacks price or
  availability, and only when `RENTAL_LLM_ENABLED` is true and an LLM URL and
  model are set (`RENTAL_LLM_MODEL`, else `LLM_MODEL`).
- **FR2** — The page is reduced to text: title, meta tags, JSON-LD and visible
  text, without scripts and styles. Long pages keep the start plus the lines
  around price and availability keywords, up to `RENTAL_LLM_MAX_CHARS`
  (default 24000).
- **FR3** — The model answers in a fixed JSON schema (price per night, total,
  cleaning fee, currency, availability plus quoted evidence, minimum nights,
  rooms, rating, …). Timeout `RENTAL_LLM_TIMEOUT_SECONDS`, default 90 s.
- **FR4** — Validation: every money value must appear on the page.
  Availability counts only if the quoted evidence is on the page. Implausible
  numbers are dropped, and a generic "from" price is never stored as a total.
- **FR5** — The LLM fills only empty fields. Values found by a scraper always
  win.
- **FR6** — If a step that was needed fails (LLM down, page not fetched), the
  poll keeps the last known values for the empty fields, so an unreachable Mac
  mini never looks like a price change.
- **FR7** — Browser step, when `RENTAL_BROWSER_ENABLED` is also true and the
  plain page still lacks price or availability: render it in headless Chromium
  in the container with images, media and fonts blocked. Accept the cookie
  banner (known consent tools first, then "accept all" buttons; never settings
  or reject), scroll once and wait for the page to settle. Price-related JSON
  the page loads is flattened to `path: value` lines that count as "on the
  page" for FR4. Timeout `RENTAL_BROWSER_TIMEOUT_SECONDS`, default 45 s.
- **FR8** — One render runs at a time, with a fresh browser for each page. If
  the LLM is down, the browser step is skipped.
- **FR9** — Any error in this step is logged and never breaks a poll.

## Acceptance criteria

- **FR1** — A HomeToGo result with a price and availability makes no LLM call.
- **FR2** — A 200 kB page produces model input of at most 24000 characters
  that still contains its price lines.
- **FR3** — A recorded request carries the JSON schema.
- **FR4** — A model answer with a total of 999 that does not appear on the page
  stores no total.
- **FR5** — With a scraper price of 1200 and a model price of 1100, the stored
  price stays 1200.
- **FR6** — With the Mac mini off, the nightly poll produces no change message
  for a rental whose price came from the LLM.
- **FR7** — With the browser on, a page whose price arrives by XHR stores that
  price when it is in the captured JSON.
- **FR8** — Two polls needing the browser render one after the other, not side
  by side.
- **FR9** — An exception inside the extraction leaves the poll result as the
  scraper produced it.

## Open questions

None. **Decided 2026-11-24:** the browser step is switched on once a trial
run shows that it works on the rentals being watched now:

- it finds a price or availability for at least one current rental that has
  none without it,
- it never stores a value that is not on the page (FR4 holds), and
- the rental-bot container stays within the VM's memory during the nightly
  run, with no restart.

Still to do (a manual run, not code): try it by hand with
`USE_BROWSER=1 python llm_extract.py <url> <check-in> <check-out> <guests>`
inside the rental-bot container, against each current rental.

## Sources

Tests: `test_llm_extract.py`, `test_browser_fetch.py` (36 tests pass, 1
skipped, run 2026-11-24).
