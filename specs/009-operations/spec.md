# 009 — Operations: stack, deploy, release broadcast, monitoring, LLM host

**Status:** draft · written 2026-11-24 from the code (`docker-compose.yml`,
`deploy_stack.py`, `ssh_config.py`, `broadcast_changelog.py`,
`check_signal_link.sh`, `check_bots.py`, `audit_server_data.py`, `macmini/`)
and the root README.

## Summary

How the bots run, ship and get announced. One VM runs the Docker stack, and a
Mac mini on the same LAN runs the model that specs 006 and 008 use.

## Functional requirements

- **FR1** — The stack is one compose file (`docker-compose.yml`): signal-api,
  whatsapp-api (WAHA), bot-router, chore-bot, rental-bot, expense-bot (see
  *Deprecated* in spec 001). Every port binds to `127.0.0.1` only.
  Signal-api sends to `bot-router:5100/webhook` and WAHA to
  `/webhook/whatsapp`.
- **FR2** — Each bot keeps its own SQLite database on its own volume:
  `housechoretracker_bot-data` (chores.db), `rental-bot-data`, `router-data`,
  `whatsapp-sessions`, plus `housechoretracker_signal-cli-config` for the Signal
  link. The two `housechoretracker_*` volumes are external and must exist
  before the stack starts.
- **FR3** — Each bot migrates its own schema on startup without losing data.
- **FR4** — `python deploy_stack.py` uploads each bot directory over SSH to
  `/home/signalbot/bots` on the VM, except tests, caches, `.env` files and
  databases. It makes sure the remote `.env` has the required keys (it
  generates `WHATSAPP_API_KEY` if missing) and backs up every bot database
  (chores.db, rentals.db, router.db, and expenses.db while expense-bot runs)
  with a timestamp. Then it removes the old containers and builds and starts
  the stack. If a backup fails, nothing is stopped. `python deploy_stack.py files`
  lists locally what would be uploaded. (Built 2026-11-24. Before that it
  uploaded a hand-kept file list and backed up only chores.db.)
  It ends with a health check of every bot. `python deploy_stack.py verify`
  runs only the checks. Credentials come from the local `.env` through
  `ssh_config.py`.
- **FR5** — Release: every release a group can notice gets a
  `## <date> – <title>` entry at the top of `CHANGELOG.md`, with a
  `<bot>-de` / `<bot>-en` block for each bot that changed. After deploying,
  `python broadcast_changelog.py` (dry run) and then `--send` send only the
  newest entry, each set-up group getting its own bot's block in its language.
  `--only <bot>` limits the send to one bot's groups.
- **FR6** — Signal link monitor: `check_signal_link.sh` runs on the VM by cron
  every 15 minutes and logs a line only when the link state changes
  (OK ↔ BROKEN).
- **FR7** — LLM host: official Ollama build (not Homebrew, which lacks
  structured output on MLX) with `qwen3.6:35b` on the Mac mini. A daily launchd
  job installs the newest signed release and rolls back unless the new version
  answers a structured-output request. The model unloads after 5 min idle
  (`OLLAMA_KEEP_ALIVE=5m`, spec 006 FR9). Context must be at least 16384
  tokens for page reading.
- **FR8** — Rental page reads run at night (`POLL_TIMES=02:00` UTC) so that
  they do not hold up chore messages, because the Mac mini serves one request
  at a time.

## Acceptance criteria

- **FR1** — `docker ps` on the VM shows the containers from FR1, and none
  listens on a non-loopback address.
- **FR2** — `docker compose down` followed by `up -d` keeps every chore,
  rental and job assignment.
- **FR3** — A bot started on a database from the previous release starts and
  keeps its rows.
- **FR4** — `python deploy_stack.py verify` reports `/health` ok for every bot.
  A new module added to a bot ships without touching `deploy_stack.py`. After a
  deploy, the VM has a fresh timestamped backup of each database.
- **FR5** — The dry run lists every group with the block it would get, and a
  group whose bot has no block in the newest entry gets nothing.
- **FR6** — Unlinking the device produces one BROKEN line within 15 minutes and
  no further lines while it stays broken.
- **FR7** — After the updater runs, `/api/ps` answers and a structured-output
  request returns valid JSON.
- **FR8** — No rental LLM request is logged on the Mac mini between 06:00 and
  24:00 local time, except for a manual `check`.

## Open questions

None. Decided 2026-11-24: every database is backed up before a deploy, and
whole directories are uploaded instead of a file list (FR4). Whether SSH copy
stays the permanent deploy mechanism remains open in `TASKS.md` section 3. It
is not a requirement here.

## Not covered here

Security debt (host-key checking off, root password through `su`, `:latest`
images) is tracked in `TASKS.md` section 2, and is not a requirement.
