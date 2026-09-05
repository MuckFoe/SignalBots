# Architecture — observed

What the code does, surveyed 2026-09-06. **This describes behaviour, not
intent.** Nothing here is a requirement or a design decision; it is a map of
what is actually wired up, so a later session does not have to re-derive it.

Where the README disagrees with the code, the disagreement is listed in
`TASKS.md` §6 rather than resolved here.

---

## Topology

Six containers on one host (`docker-compose.yml`). Every service binds to
`127.0.0.1` only.

| Service | Port | Image / build | Data volume |
|---|---|---|---|
| `signal-api` | 8080 | `bbernhard/signal-cli-rest-api:latest` | `signal-cli-config` (external) |
| `bot-router` | 5100 | `HouseBotRouter/` | `router-data` |
| `chore-bot` | 5000 | `HouseChoreTracker/` | `bot-data` (external) |
| `rental-bot` | 5001 | `HouseRentalTracker/` | `rental-bot-data` |
| `expense-bot` | 5002 | `HouseExpenseTracker/` | `expense-bot-data` |
| `grocery-bot` | 5003 | `HouseGroceryTracker/` | `grocery-bot-data` |

Two volumes are `external: true` (`docker-compose.yml:134-135, 139-140`) and
must already exist or the stack fails to start:
`housechoretracker_signal-cli-config` and `housechoretracker_bot-data`.

`signal-api` is configured with
`RECEIVE_WEBHOOK_URL=http://bot-router:5100/webhook` (`docker-compose.yml:8`),
so the router is the only service Signal talks to.

---

## How a message reaches a bot

1. Signal delivers to `signal-api`, which POSTs to the router's `/webhook`
   (`HouseBotRouter/app.py:188` — the only `/webhook` in the stack).
2. The router resolves which *job* the chat belongs to (`resolve_job`,
   `group_router.py:165-179`):
   - an explicit assignment in its own `group_jobs` SQLite table, else
   - probe each bot in the order `chores, rentals, expenses, grocery` by POSTing
     to `{base}/internal/scope`, taking the first that returns `has_admins`
     truthy (`group_router.py:141-161`).
3. It forwards to `{base}/internal/handle` with a 120s timeout
   (`group_router.py:183-235`), body:
   `{scope_id, sender, message, group_id, attachments}`.

Base URLs are mapped from four job names at `group_router.py:43-53`.

### The contract every bot implements

| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness |
| `POST /internal/scope` | returns whether this bot claims the scope (`has_admins`) |
| `POST /internal/handle` | handles a message |

Confirmed at `HouseChoreTracker/app.py:110,115,128`,
`HouseExpenseTracker/app.py:57,62,75`, `HouseGroceryTracker/app.py:59,64,77`,
`HouseRentalTracker/app.py:129,134,147`.

**This three-endpoint contract is the only coupling between services.** A grep
for cross-project imports and `sys.path` manipulation returns zero matches — the
five projects share no code at import time.

---

## Projects

Each is a flat directory of top-level modules importing each other by bare name
(`from commands import handle_command`), so each is only importable with its own
directory as cwd. That applies to the tests too.

| Project | Notable | Tests |
|---|---|---|
| `HouseBotRouter/` | owns `/webhook`, job routing, `group_jobs` table | none |
| `HouseChoreTracker/` | `commands.py` 3,560 lines; `storage.py` 2,227 | 4 files, 848 lines |
| `HouseRentalTracker/` | scrapers, drive-time lookup, poll loop | none |
| `HouseExpenseTracker/` | balances, money, splits | none |
| `HouseGroceryTracker/` | no README, no own compose file | none |

Runtime: every bot is `CMD ["python", "app.py"]` running the **Flask
development server** (`app.run(...)`). Each spawns a Signal send-queue daemon
thread at startup; chore adds a reminder loop (`app.py:166-167`), rental a poll
loop (`app.py:187-188`). Only HouseChoreTracker's Dockerfile sets
`TZ=Europe/Berlin`.

### Duplicated files

No shared package exists. By content hash:

- **Byte-identical** across chore / expense / rental: `signal_client.py` (36
  lines), `dialogue_utils.py` (102 lines). Router and grocery have their own
  variants. Nothing enforces that the identical three stay in sync.
- **Divergent forks** — same name, different content, in several projects:
  `commands.py`, `storage.py`, `bot_registry.py`, `stats_charts.py`,
  `chart_parse.py`, `display_names.py`.

---

## Deployment

`deploy_stack.py` (SSH via paramiko; credentials from `ssh_config.py`):

1. Connect to the host from `.env`.
2. SFTP-upload a **hand-maintained file allowlist** — `PROJECTS` (lines 10-81)
   plus `ROOT_FILES` = `docker-compose.yml`, `README.md`, `.env.example` — to
   `REMOTE_ROOT` (`/home/signalbot/ProjectHub`).
3. Ensure remote `.env` exists: copy from the legacy path
   `/home/signalbot/HouseChoreTracker/.env`, else from `.env.example`, then
   append six keys if missing (lines 121-139).
4. Back up **`chores.db` only** into the volume via a throwaway alpine
   container.
5. `docker compose down` the legacy stack, then `docker rm -f` all six
   containers.
6. `docker compose build && docker compose up -d`.
7. Print `docker ps` and curl `/health` on all five bots.

`python deploy_stack.py verify` re-runs step 7 plus log tails — read-only, no
teardown.

**The upload allowlist has drifted.** No subproject `.env.example` is uploaded,
and HouseChoreTracker's README, CLAUDE.md, four test files, `proxmox_setup.sh`
and its four SSH scripts are not deployed. A new module added to a bot will
silently not ship.

### Other scripts

All read connection settings from `ssh_config.py`.

| Script | Does |
|---|---|
| `audit_server_data.py` | read-only pre-deploy audit of volumes and DB counts |
| `fix_stack_deploy.py` | narrower repair; `docker rm -f`s only **four** containers, omitting expense and grocery |
| `check_bots.py` | health + log probe, posts smoke-test payloads to `/internal/handle` |
| `check_errors.py` | greps container logs for errors |
| `check_chore_bot.py` | chore-specific log and DB probe |
| `HouseChoreTracker/deploy_remote.py` | 7-line shim that `runpy`-executes the root `deploy_stack.py` |
| `HouseChoreTracker/proxmox_setup.sh` | bootstraps Docker on a Debian 12 host |

---

## Dependencies

Five `requirements.txt`, one per project. All floor-pinned (`>=`), no upper
bounds, no lockfile.

- **All five:** `Flask>=3.0.0`, `requests>=2.31.0`, `python-dotenv>=1.0.1`
- **+ `matplotlib>=3.8.0`:** chore, expense, rental
- **+ `tzdata>=2024.1`:** chore
- **+ `beautifulsoup4>=4.12.0`:** rental

`paramiko` is imported by nine files and declared in **no** manifest. There is
no root `requirements.txt` covering the management scripts.

No build system anywhere: no `pyproject.toml`, `setup.py`, `Makefile`, or
lockfile. Python is pinned only by `FROM python:3.12-slim` in the Dockerfiles.

### External network calls

- `nominatim.openstreetmap.org/search` and `router.project-osrm.org` — rental
  drive-time lookup
- Rental scrapers: `casamundo`, `hometogo`, `fewo-direkt`, `amivac`,
  `bellevue-ferienhaus`, `vacationrenter`, registered as host patterns at
  runtime (`HouseRentalTracker/scrapers.py:352-401`)

---

## Configuration

Env vars read by code but declared in **no** `.env.example` and no compose file:
`BOT_REGISTRY` (`HouseChoreTracker/bot_registry.py:7`), `PENDING_MAX_HOURS`,
`PENDING_STALE_HOURS`.

`GROCERY_IMAGE_DIR` is in compose (line 122) but in no template.
`HouseBotRouter/.env.example` is missing `GROCERY_BOT_URL`, which the router's
code requires (`app.py:31,38`).

Local scripts read `SSH_HOST`, `SSH_USER`, `SSH_PASSWORD`, `SSH_ROOT_PASSWORD`,
`REMOTE_ROOT`, `TEST_SENDER` from `.env` via `ssh_config.py`. That file is
gitignored; `.env.example` carries placeholders.

### Compose files collide

Root `docker-compose.yml` plus per-project files in HouseChoreTracker,
HouseExpenseTracker and HouseRentalTracker. Each sub-compose defines a single
service with the **same `container_name`** and bind port as the root stack, so
running one while the root stack is up collides. Nothing states which is
authoritative; `deploy_stack.py` uses only the root file.

---

## Unexplained

Observed, purpose not determinable from the code:

- `HouseChoreTracker/rental/__init__.py` — 0 bytes, package imported by nothing,
  contains only `__pycache__` artefacts for `scrape_types` and `storage`.
- `HouseGroceryTracker/image_recognition.py` — no OCR, ML or vision code. Its
  three functions download a Signal attachment and write it to disk.
- `check_chore_bot.py` references `/home/signalbot/ProjectHub/HouseChoreTracker/chores.db`,
  a path no other script writes to.
- The `ProjectHub` / `SignalBots` naming split. The folder is `SignalBots`; the
  remote root and Docker volume prefixes say `projecthub`.

## Not established

- Whether the tests pass — never run.
- Whether this code matches what is deployed. No version string, build stamp or
  image tag exists anywhere, and the upload allowlist has drifted.
- Which rental sites are scraped in practice — targets are registered at
  runtime, and no fixture or test pins them.
