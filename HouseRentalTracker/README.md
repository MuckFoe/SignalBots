# Rental Tracker

Vacation rental tracking bot. Runs as the `rental-bot` container in the **ProjectHub** stack.

Deploy with the parent compose (one Signal QR, router forwards rental groups here):

```bash
cd ..
docker compose up -d --build
```

Standalone dev (no router): `docker compose up` in this folder — use `POST /internal/handle` to test.

Data: `rentals.db` only. Does not touch chore data.

## LLM fallback for unknown sites (off by default)

The built-in scrapers know the HomeToGo family (API) and pages with
schema.org JSON-LD. For any other site, or when a scraper misses **price or
availability**, the bot can hand the page to the local LLM on the Mac mini
(`llm_extract.py`):

1. Page HTML → compact text: title, meta tags, JSON-LD, visible text (scripts
   and styles dropped). Long pages keep the start plus the lines around
   price/availability keywords (`RENTAL_LLM_MAX_CHARS`, default 24000).
2. The LLM returns a fixed JSON schema (price per night, total, cleaning fee,
   availability + quoted evidence, min nights, rooms, rating, …).
3. **Validation**: every money value must appear on the page. `available`
   counts only if the quoted evidence is really on the page. Implausible
   numbers are dropped. A generic "from" price is never stored as a total.
4. The LLM only fills **empty** fields. Scraper values always win.
5. If the LLM is down, the poll keeps the last known values, so a sleeping Mac
   mini doesn't send "price changed" messages.

Config (root `.env`; `LLM_BASE_URL` / `LLM_MODEL` are shared with chore-bot):

| Var | Default | Purpose |
|---|---|---|
| `RENTAL_LLM_ENABLED` | `false` | master switch |
| `RENTAL_LLM_MODEL` | `LLM_MODEL` | optional, a different model for page extraction |
| `RENTAL_LLM_TIMEOUT_SECONDS` | `90` | long prompts; polling runs in the background |
| `RENTAL_LLM_MAX_CHARS` | `24000` | page text sent to the model (~7k tokens) |

Ollama: set `OLLAMA_CONTEXT_LENGTH=16384` (or more) on the Mac mini. The
default context is too small for a page and Ollama truncates it silently.

Try a real page (from this folder, with the env vars set):

```bash
python llm_extract.py "https://example.com/haus-123" 2026-12-20 2026-12-27 4
SHOW_TEXT=1 python llm_extract.py ...   # also print what the model sees
```

### Browser step (off by default)

If the plain page still gives no price or availability (JavaScript-loaded
prices, cookie wall, blocked plain requests), `browser_fetch.py` renders the
page in headless Chromium **inside the rental-bot container**:

1. Images, media and fonts are blocked to save RAM and bandwidth.
2. The cookie banner is clicked away: known consent tools first (OneTrust,
   Cookiebot, Usercentrics, Didomi, Borlabs, …), then buttons such as
   "Alle akzeptieren" / "Accept all". It never clicks settings or reject.
3. The page scrolls once and waits until it stops loading.
4. **Price capture**: JSON the page loads in the background is kept if it
   looks price-related, flattened to `path: value` lines
   (`offer.pricing.total: 1234.5`). Those lines go to the LLM together with
   the rendered page and count as "on the page" for the number check.

There's one render at a time and a fresh browser for every page, so memory is
freed after each page. If the LLM is down, the browser step is skipped.

| Var | Default | Purpose |
|---|---|---|
| `RENTAL_BROWSER_ENABLED` | `false` | browser step (needs `RENTAL_LLM_ENABLED` too) |
| `RENTAL_BROWSER_TIMEOUT_SECONDS` | `45` | per page |

The Dockerfile installs Chromium's headless shell. Build with
`--build-arg INSTALL_BROWSER=0` to leave it out; the browser step then fails
and the poller keeps the last known values.

```bash
python browser_fetch.py "https://example.com/haus-123"          # what the browser sees + captured JSON
USE_BROWSER=1 python llm_extract.py "https://…" 2026-12-20 2026-12-27 4
```

Limits: date-specific prices only appear if the site puts them in the page
for the dates in the URL. Sites with strong bot protection (Airbnb, Booking)
often block headless Chromium too. Clicks other than the cookie banner (date
pickers, a "calculate price" button) aren't supported yet. They would be
per-site steps.
