# Plan: LLM page extraction for the rental bot

Branch: `feature/llm-rental-extract` (from `main`) · Drafted and built 2026-11-10 ·
Status: **built, off by default**. Not yet tested against real sites or a real
model. See "Rollout steps" for what's left.

Related: [LLM command assist for chore-bot](llm-command-assist-plan.md). Both use
the same local LLM on the Mac mini.

## Goal

The rental bot (`HouseRentalTracker/`) watches holiday-home listings and tells
the group when **price or availability** changes. Today it only understands
two kinds of site:

- the HomeToGo family (Casamundo, fewo-direkt, …) through their internal API,
- pages that include schema.org JSON-LD.

Every other site ends up with "No vacation rental JSON-LD found." and no price.
The goal is to let the local LLM read the page and pull out the important
facts, mainly **price and availability**, for any site, without making the
tracked values less reliable.

### Decisions (2026-11-10)

| Question | Decision |
|---|---|
| Input to the LLM: screenshot or HTML? | **Rendered page text**, not a screenshot. Exact digits, cheaper, faster, and numbers can be checked against the text. Local vision models misread digits, and there would be nothing to check against |
| Pages that need JavaScript or a click first | **Headless browser (Playwright/Chromium)** as a second step, with automatic cookie-banner click and capture of the price JSON the page loads |
| Where does the browser run? | **In the rental-bot container on the bots VM**, not on the Mac mini. The Mac mini only serves the LLM |
| LLM choosing clicks itself (agent)? | **No.** Unreliable with 7–14B models, slow, and results vary from run to run (false "price changed" messages). Per-site click steps later, if needed |
| Can the LLM override scraper values? | **No.** It only fills empty fields |
| LLM or browser down? | The poller **keeps the last known values**, so there's no false change notification |

---

## How it works

```
ScraperRegistry.scrape(url, dates, guests)
  │
  ├─ adapter (HomeToGo API / JSON-LD)            ── unchanged
  │
  └─ price AND availability known? ── yes ──▶ done (no LLM call)
        │ no, and RENTAL_LLM_ENABLED
        ▼
     Step 1: plain HTTP GET → page_text → LLM → validate → merge
        │   LLM down ─────────────────────────────▶ flag fallback_failed, stop
        ▼
     still missing, and RENTAL_BROWSER_ENABLED?
        ▼
     Step 2: headless Chromium (browser_fetch.render)
        - block images/media/fonts
        - click away the cookie banner
        - scroll once, wait until the page stops loading
        - capture price-related JSON responses
        → rendered DOM + captured JSON → LLM → validate → merge
        │   render or LLM failed ────────────────▶ flag fallback_failed
        ▼
     Poller: fallback_failed → fill empty fields from the stored row
             (no "changed to unknown" notification)
```

### Page → text (`llm_extract.page_text`)

- Kept: `<title>`, relevant meta tags (`og:*`, `product:price:*`, description),
  up to 3 JSON-LD blocks, visible text, and the captured price JSON as
  `path: value` lines.
- Dropped: scripts, styles, SVG, iframes, `<head>` noise.
- Long pages: the first quarter of the budget goes to the start of the page,
  the rest to lines (±2) around price/availability keywords
  (`€`, Preis, Nacht, gesamt, verfügbar, Endreinigung, …).
  Budget `RENTAL_LLM_MAX_CHARS` (default 24000 chars ≈ 7k tokens).

### LLM output

An OpenAI-compatible `/chat/completions` call with a strict JSON schema (falls
back to `json_object` mode if the backend rejects the schema), temperature 0.
The fields match `ScrapeResult`: `available` + `availability_evidence`,
`price_per_night`, `total_price`, `prices_for_requested_dates`, `currency`,
`cleaning_fee`, `min_nights`, `title`, `location_name`, `guests_max`,
`bedrooms`, `bathrooms`, `rating`, `review_count`, `pets_allowed`,
`property_type`. Coordinates are **excluded**: a guessed lat/lon would quietly
give wrong drive times.

The prompt includes the requested stay (dates, nights, guests) and tells the
model to ignore prices of "similar listings".

### Validation (`llm_extract.validate`)

| Rule | Why |
|---|---|
| Every money value must appear on the page (`1.234,50`, `1,234.50`, `1 234`, `CHF 1'200.-`, …) | Blocks made-up prices |
| Exception: nightly price = total ÷ nights, if the total is on the page | Many sites show only the total |
| `available` needs `availability_evidence` that is really on the page | Blocks a guessed "available" |
| `prices_for_requested_dates = false` → no total | A "from 79 €" price isn't this stay's total |
| Range checks (bedrooms ≤ 50, rating ≤ 10, min nights ≤ 365, …), currency must be a 3-letter code | Blocks garbage |

Anything that fails is dropped, which means "unknown", the same as today.

### Browser step (`browser_fetch.py`)

- **Cookie banner**: first the IDs of the common consent tools (OneTrust,
  Cookiebot, Usercentrics, Didomi, Borlabs, Quantcast, TrustArc), then buttons
  named "Alle akzeptieren" / "Accept all" / …, then plain "Akzeptieren" / "OK".
  It never clicks settings or reject. It checks every frame.
- **Price capture**: XHR/fetch responses with status 200 and JSON content,
  ≤ 400 KB, that contain price keywords. They're flattened to leaves whose path
  looks price-related (`offer.pricing.total: 1234.5`), max 80 lines per
  response and 8 responses. These count as "on the page" for the number check.
- **Memory**: one render at a time (lock), a fresh browser per page that is
  closed afterwards, images/media/fonts blocked, `--disable-dev-shm-usage`.
- Docker: `playwright install --with-deps --only-shell chromium` (headless
  shell only). `--build-arg INSTALL_BROWSER=0` leaves it out.

---

## Changes (all in `HouseRentalTracker/`)

| File | Change |
|---|---|
| `llm_extract.py` | **new**: page → text, LLM client, schema, prompt, validation, merge, CLI |
| `browser_fetch.py` | **new**: Playwright render, cookie banner, price capture, CLI |
| `scrapers.py` | `ScraperRegistry.scrape` → `_llm_fill` (step 1 plain, step 2 browser) |
| `scrape_types.py` | `ScrapeResult.fallback_failed` (not stored, not tracked) |
| `poller.py` | `keep_last_known()` when `fallback_failed` |
| `requirements.txt` | `playwright>=1.49` |
| `Dockerfile` | headless Chromium, `INSTALL_BROWSER` build arg |
| `README.md` | how it works, config, CLI |
| `test_llm_extract.py`, `test_browser_fetch.py` | **new**: 30 tests |

Also on this branch: the Stop-hook path fix (`$CLAUDE_PROJECT_DIR`) from
`0970129`, because `main` doesn't have it yet.

## Configuration

Root `.env` (rental-bot reads it via `env_file`). `LLM_BASE_URL` and
`LLM_MODEL` are shared with chore-bot.

| Var | Default | Purpose |
|---|---|---|
| `RENTAL_LLM_ENABLED` | `false` | master switch for the LLM fallback |
| `LLM_BASE_URL` | — | Mac mini, e.g. `http://<lan-ip>:11434/v1` |
| `LLM_MODEL` / `RENTAL_LLM_MODEL` | — | the rental one overrides the shared one |
| `RENTAL_LLM_TIMEOUT_SECONDS` | `90` | long prompts; polling runs in the background |
| `RENTAL_LLM_MAX_CHARS` | `24000` | page text sent to the model |
| `RENTAL_BROWSER_ENABLED` | `false` | browser step (needs the LLM fallback on) |
| `RENTAL_BROWSER_TIMEOUT_SECONDS` | `45` | per page |

Mac mini: **`OLLAMA_CONTEXT_LENGTH=16384`** or more. With the default context
Ollama cuts the page off without any error.

## Tests

`cd HouseRentalTracker && python -m unittest test_llm_extract test_browser_fetch test_scope_migration`
(Python 3.12 with requirements installed). **32 tests pass** (2026-11-10).

- page-to-text (scripts dropped, JSON-LD and meta kept, long pages keep price lines)
- validation (price not on page, evidence missing, "from" prices, number formats, derived nightly price)
- merge never overrides scraper values
- registry: LLM off = unchanged, complete result = no LLM call, LLM down = flagged
- two-step flow: browser only when needed, skipped when the LLM is down, used when the plain fetch is blocked, captured JSON reaches the prompt
- poller: LLM down after a successful run → values kept, no notification
- **real Chromium** against a local test site: cookie wall with "Einstellungen" + "Alle akzeptieren", price loaded by `fetch` only after consent → correct button clicked, rendered price and captured JSON present (skipped when Playwright isn't installed)

---

## Rollout steps

1. ~~Step 1: LLM on the plain page, validation, merge, keep-last-known~~ ✅ 2026-11-10
2. ~~Step 2: browser render, cookie banner, price capture~~ ✅ 2026-11-10
3. **Docker build on the VM** and check that the headless shell starts in the
   container (`docker exec rental-bot python browser_fetch.py <url>`).
4. **RAM check** on the VM (owner: Mo): `docker stats rental-bot` during a
   render. If it's too much: `mem_limit` in compose, or
   `INSTALL_BROWSER=0` and LLM-on-plain-page only.
5. **Collect real listing URLs** for the sites we actually use. For each,
   check plain vs rendered output (`SHOW_TEXT=1`, `USE_BROWSER=1`).
6. **Mac mini up** (shared with chore-bot), `OLLAMA_CONTEXT_LENGTH` set; run
   `llm_extract.py` on those URLs, compare with what the site shows by hand.
   Turn these into a small eval set (URL, saved HTML, expected price/availability).
7. **Live**: `RENTAL_LLM_ENABLED=true`, later `RENTAL_BROWSER_ENABLED=true`.
   Watch logs (`Rental LLM … dropped …`) and change notifications for a
   week.
8. CHANGELOG entry and group broadcast per the release routine.

## Open questions / later

- **Per-site click steps** for sites that need more than the cookie banner
  (date picker, a "calculate price" button). They would be stored per host like
  custom hosts: a short list of `click <selector>` / `wait <ms>` steps. The
  LLM could suggest a site's steps once, for a human to confirm.
- **Dates in the URL** per site (URL templates), so prices for the stay show
  up without clicking.
- **Value flapping**: if the model gives different answers for the same page,
  require two polls in a row to agree before notifying. Decide after step 7.
- **Bot protection**: Airbnb and Booking often block headless Chromium too.
  Out of scope unless one of them becomes important.
- Screenshots for debugging or a "show me the listing" command (not as LLM input).
