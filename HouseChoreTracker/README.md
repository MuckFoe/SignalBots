# House Chore Tracker Signal Bot

A small Signal bot that:

- Tracks only pre-defined chores.
- Saves each `done` action with a timestamp.
- Sends automatic reminders for chores.
- Lets you list all chores.
- Lets you add, delete, and rename chores.
- Is manageable directly from Signal group chats (multiple groups supported).

## Commands (send in Signal chat)

- `help` / `hilfe`
- `chore help` / `aufgabe hilfe` - explain chore setup in more detail
- `edit help` / `bearbeite hilfe` - explain editing in more detail
- `language` - show current chat/group language
- `language de` / `language en` - set language for this chat/group
- `sprache deutsch` / `sprache englisch` - German aliases for language switching
- `admin help` - show admin commands
- `admin stats` - show group statistics
- `admin quiet hours 00:00-08:00` - configure when reminders are muted
- `admin auth reminder on/off` / `admin signal erinnerung an/aus` - enable or disable Signal link reminders
- `groups` (list registered groups)
- `chores` or `list` - show all chores, last done time, and due/overdue status
- `done <chore name>` - logs with timestamp
- `undo done <chore name>` / `rückgängig <Aufgabe>` - revoke the last completion
- `add` - start guided chore setup
- `add <chore name> <schedule>` - start adding a chore
- `edit <chore name>` / `bearbeite <Aufgabe>` - start guided chore editing
- `yes` / `no` / `cancel` or `ja` / `nein` / `abbrechen` - answer or exit dialogs
- `schedule <chore name> <schedule>` - change when a chore is due without losing history
- `fälligkeit <Aufgabe> <Plan>` - German alias for schedule changes
- `confirmation <chore name> on|off` - require or skip `done` confirmation
- `reminder <chore name> <schedule>` - repeat overdue reminders for confirmation-required chores
- `delete <chore name>`
- `rename <old name> -> <new name>`
- `history [limit]` - show recent done logs
- `admin reset group` - start protected reset flow
- `admin reset group confirm <reset-code>` - confirm reset with one-time code

Examples:

- `add`
- `vacuum`
- `12 hours`
- `yes`
- `add dishes 1 day`
- `aufgabe`
- `Geschirr`
- `Montag`
- `ja`
- `add windows 2 months`
- `add taxes 1 year`
- `add bins monday`
- `add cat litter 1 week`
- `add shopping list no reminder`
- `edit bathroom`
- `bearbeite Bad putzen`
- `undo done bathroom`
- `rückgängig Bad`
- `schedule bins every Wednesday`
- `fälligkeit Geschirr jeden Tag`
- `confirmation bins off`
- `reminder dishes 1 hour`
- `admin quiet hours 00:00-08:00`
- `admin auth reminder on`
- `admin stats`

## How it works

- Runs as the `chore-bot` container in the **ProjectHub** stack (see `../README.md`).
- Signal webhooks go to `bot-router`, which forwards chore groups here via `POST /internal/handle`.
- Health endpoint: `GET /health`
- Storage: SQLite (`chores.db` by default)
- Reminder engine: background loop checks due chores every 60 seconds

## Group-native usage

1. Add the bot account to each household Signal group you want.
2. Send any first message in the group. The bot first asks for the group language.
3. Set the language with `language en` or `sprache deutsch`.
4. Everyone can add/edit chores and use `chores`/`list`, `done <chore>`, and `history`.
5. Admin actions are hidden from normal help. Ask for them with `admin help`.

Notes:

- On first message in a group, that group is auto-registered.
- Data is isolated per group (group A cannot see group B chores/history).
- Language is stored per group/chat. Use `language de` or `sprache deutsch` in a group to switch only that group to German.
- Schedules support minutes, hours, days, weeks, months, years, and weekdays.
- `add` starts a guided setup dialog asking for name, schedule, and whether `done` confirmation is needed.
- Any active dialog can be exited with `cancel` / `abbrechen`.
- `add chore clean toilet` starts the same dialog with `clean toilet` as the chore name.
- `edit clean toilet` starts a guided edit dialog and asks whether to change name, due schedule, confirmation, overdue reminder, or delete the chore.
- One-line adding still works: `add dishes 1 hour`, then reply `yes` or `ja`.
- Natural schedule text like `every hour`, `jede Stunde`, or `jeden Mittwoch` works. The shortest input is still `1 hour`, `1 Stunde`, or `Mittwoch`.
- Use `no reminder` / `keine Erinnerung` for chores that can be marked done but should not auto-remind.
- Chores require `done` by default. If confirmation is on in guided setup, the bot asks how often overdue reminders should repeat.
- Standard repeat defaults are: hourly tasks repeat every 5 minutes, daily tasks every 1 hour, weekly/weekday tasks every 8 hours.
- Reminders are muted by default from `00:00` to `08:00`. Change this with `admin quiet hours 23:00-07:00`.
- Any group user can edit chore names, due schedules, confirmation settings, and overdue reminder settings without losing completion history.
- `schedule dishes every day` / `fälligkeit Geschirr jeden Tag` changes when a chore is due and keeps its `done` history.
- Use `reminder dishes 1 hour` to remind hourly until someone sends `done dishes`.
- Use `confirmation bins off` for a recurring reminder that does not need `done`.
- `list` shows each chore's reminder schedule, confirmation setting, last done time, and next due or overdue status.
- Reminder messages show exact reply options, including how to mark done, undo a completion, edit the chore, or disable the reminder with `schedule <task> no reminder`.
- `admin stats` shows chore counts, done counts, action counts, top completed chores, and recent actions.
- Signal link reminders are off by default. Enable them per group with `admin auth reminder on` / `admin signal erinnerung an`.
- If no group is configured, the bot still works in direct chat fallback mode.
- `reset group` is protected: confirmation code is required within 10 minutes and by the same sender.

## Setup

1. Create and activate a Python virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and update values:

- `SIGNAL_BOT_NUMBER`: your Signal number used by signal-cli
- `SIGNAL_API_URL`: URL of signal-cli-rest-api (often `http://localhost:8080`)
- `BOT_HOST`: typically `0.0.0.0`
- `BOT_PORT`: bot HTTP port, e.g. `5000`
- `DATABASE_PATH`: path to SQLite DB

4. Run:

```bash
python app.py
```

## Docker setup (recommended)

Production deploy uses the parent **ProjectHub** compose (one Signal QR, router + chore + rental):

```bash
cd ..
cp .env.example .env
docker compose up -d --build
```

This folder's `docker-compose.yml` is for chore-bot-only local dev.

### Full stack on Proxmox guest

- Create a Debian 12 (bookworm) VM (recommended), or a privileged Debian 12 LXC.
- Ensure the guest has outbound internet access and DNS working.
- Update base system once before running Docker install:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

Run inside the guest:

```bash
sudo bash proxmox_setup.sh
```

Verify Docker/Compose:

```bash
docker --version
docker compose version
```

### 2) Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

- `SIGNAL_BOT_NUMBER=+<your_signal_number>`

You can keep `SIGNAL_API_URL` as default in `.env`; Docker Compose overrides the bot to use `http://signal-api:8080` internally.

### 3) Start containers

```bash
cd /path/to/ProjectHub
docker compose up -d --build
docker compose ps
```

Check logs:

```bash
docker compose logs -f bot-router
docker compose logs -f chore-bot
docker compose logs -f signal-api
```

### 4) Register Signal number in signal-cli-rest-api

The API container stores state in Docker volume `signal-cli-config`.  
If this number is not already registered in the container, do registration once:

```bash
# Request SMS code
curl -X POST "http://127.0.0.1:8080/v1/register/+1234567890"

# Verify code you received
curl -X POST "http://127.0.0.1:8080/v1/register/+1234567890/verify/<CODE>"
```

### 5) Webhook routing

Incoming messages are sent to `http://bot-router:5100/webhook` (configured in parent `docker-compose.yml`). The router forwards chore groups to this service.

### 6) Operational commands on Proxmox guest

```bash
docker compose up -d
docker compose down
docker compose pull
docker compose up -d --build
docker compose logs -f
```

### 7) Data persistence

- Chore database is in Docker volume `bot-data`.
- Signal account/session state is in Docker volume `signal-cli-config`.
- App updates run database migrations automatically on startup. Existing chores, group settings, quiet hours, completion history, and action stats are preserved.

Destroying containers does not remove these volumes unless you run `docker compose down -v`.

Safe update path:

```bash
docker compose build --pull=false chore-bot
docker compose up -d --no-build chore-bot
```

Avoid `docker compose down -v` unless you intentionally want to delete the bot database and Signal registration.

### 8) Signal linked-device session

Signal linked devices can be unlinked after long inactivity. The bot should stay active as long as the `signal-api` container keeps running and receives/sends messages through the webhook setup.

Signal link reminders are disabled by default. Enable them per group with:

```text
admin auth reminder on
admin signal erinnerung an
```

When enabled, the bot sends a periodic Signal link reminder about this risk roughly every 25 days to that group.

If the linked device is already unlinked, the bot cannot send a QR code into the Signal group because sending Signal messages is exactly what is broken. Re-link manually with:

```text
http://127.0.0.1:8080/v1/qrcodelink?device_name=signal-api
```

Then scan the QR code from Signal on the primary phone.

## Quick test locally

Simulate a routed command (internal API):

```bash
curl -X POST http://localhost:5000/internal/handle \
  -H "Content-Type: application/json" \
  -d '{
    "scope_id": "dm:+1111111111",
    "sender": "+1111111111",
    "message": "help"
  }'
```
