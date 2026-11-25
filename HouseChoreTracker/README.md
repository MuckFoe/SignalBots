# House Chore Tracker

The chore bot of the SignalBots stack (`chore-bot`, see `../README.md`). A
household group keeps its chores here: the bot reminds when something is due,
records who did what, and shows stats. It runs in Signal and WhatsApp groups
and in direct chats, in German or English.

**What it does is specified in `../specs/`.** That is the reference; this file
only gives the overview and how to run it.

| Spec | Covers |
|---|---|
| [003 chore-tracking](../specs/003-chore-tracking/spec.md) | recurring, open and one-time chores; done/undo, edit, list, history |
| [004 reminders and vacation](../specs/004-chore-reminders-and-vacation/spec.md) | due and overdue reminders, quiet hours, Signal link reminder, vacation |
| [005 setup, members, stats](../specs/005-chore-group-setup-members-stats/spec.md) | group setup, names, admin commands, language, timezone, stats, reset, help, tutorial |
| [006 LLM assist](../specs/006-chore-llm-assist/spec.md) | free text understood by the local model, confirm before acting |
| [002 group move](../specs/002-group-move-and-identity/spec.md) | moving a group between Signal and WhatsApp |

## In the chat

New group: the first message asks for the language (`english` / `deutsch`).
Whoever answers is the group's first admin. After that, `help` / `hilfe` lists
the everyday commands, and `tutorial` / `anleitung` explains every flow step by
step. The most used commands:

- `list` · `list extend`
- `done <chore> [for <person>]` · `undo done <chore>`
- `add` (step by step) · `add <name> <schedule>` · `todo <name>` · `once`
- `edit <chore>`
- `my stats` · `group stats`
- `vacation` · `vacation help`
- `admin help`: language, timezone, quiet hours, Signal link reminder,
  `admin add <name>` / `admin remove <name>` / `admin list`, reset

## Running it

In production it runs from the root `docker-compose.yml`. The router forwards
chore chats to `POST /internal/handle`, and reminders run in a loop inside the
container every 60 s. Deploying is described in
[spec 009](../specs/009-operations/spec.md).

This folder's `docker-compose.yml` is for local chore-bot-only development.
Don't run it while the root stack is up, because both use the same container
name and port.

Environment (`../.env`):

| Var | Purpose |
|---|---|
| `SIGNAL_BOT_NUMBER` | the shared Signal number (required) |
| `SIGNAL_API_URL`, `WHATSAPP_API_URL`, `WHATSAPP_API_KEY` | where replies are sent |
| `DATABASE_PATH` | SQLite file (`/data/chores.db` in the container) |
| `LLM_ENABLED`, `LLM_BASE_URL`, `LLM_MODEL` | free-text assist (spec 006) |
| `LLM_TIMEOUT_SECONDS` (20), `LLM_COLD_TIMEOUT_SECONDS` (120) | model timeouts, normal and during a cold start |
| `LLM_SCOPES`, `LLM_GROUP_MIN_CONFIDENCE` (0.6) | limit the assist to some chats; minimum confidence in groups |
| `PENDING_STALE_HOURS` (1), `PENDING_MAX_HOURS` (24) | when an unanswered dialogue counts as stale, and when it expires |
| `BOT_INSTANCE_ID`, `BOT_INSTANCE_NAME`, `BOT_REGISTRY` | several chore-bot instances on one number (rare) |

The database schema migrates on startup and keeps existing data. Never run
`docker compose down -v`: it deletes the chore database and the Signal link.

## Tests

From this folder, with Python 3.10 or newer (the container uses 3.12):

```bash
python -m unittest discover -p 'test_*.py'
```

Intent eval for the LLM assist: `evals/run_intent_eval.py` against
`evals/intent_cases.jsonl`.

## Quick local check

```bash
curl -X POST http://localhost:5000/internal/handle \
  -H "Content-Type: application/json" \
  -d '{"scope_id": "dm:+1111111111", "sender": "+1111111111", "message": "help"}'
```
