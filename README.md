# SignalBots

A gathering of independent Signal bots sharing one Signal account. Each bot
is its own container with its own database; they don't depend on each other
topic-wise, and share no code at runtime — the only coupling is the
three-endpoint contract (`/health`, `/internal/scope`, `/internal/handle`)
that `bot-router` uses to talk to whichever bot a chat is assigned to.

| Container | Role |
|-----------|------|
| `signal-api` | Signal link (one QR code) |
| `whatsapp-api` | WhatsApp link (one QR code, [WAHA](https://waha.devlike.pro)) |
| `bot-router` | Receives webhooks, routes per group |
| `chore-bot` | Household chore tracker |
| `rental-bot` | Vacation rental price tracker |
| `expense-bot` | Shared expenses (Splitwise/Tricount style) |

## Deploy

From this directory:

```bash
cp .env.example .env
# edit SIGNAL_BOT_NUMBER, set WHATSAPP_API_KEY to any long random string
docker compose up -d --build
```

Signal QR: `http://127.0.0.1:8080/v1/qrcodelink?device_name=signal-api`

WhatsApp QR: `http://127.0.0.1:3000/dashboard` (user `admin`, password =
`WHATSAPP_API_KEY`), open the `default` session and scan. `deploy_stack.py`
generates `WHATSAPP_API_KEY` in the remote `.env` if it is missing.

WhatsApp chats work like Signal chats: same commands, same job picker. They
are told apart by id — WhatsApp ids contain `@` (`…@g.us`, `…@c.us`), Signal
ids never do. The link is unofficial (WAHA drives a linked WhatsApp Web
device), so use a number you can afford to lose.

## Data (separate, not merged)

- `housechoretracker_bot-data` → `chores.db`
- `rental-bot-data` → `rentals.db`
- `expense-bot-data` → `expenses.db`
- `router-data` → `router.db` (group job assignments only)
- `whatsapp-sessions` → WhatsApp link state (losing it means re-scanning the QR)

Existing chore groups keep working: router detects them via chore-bot admins.

New groups are asked: `chores`, `rentals`, or `expenses`.

## Projects

- `HouseChoreTracker/` — chore-bot
- `HouseRentalTracker/` — rental-bot
- `HouseExpenseTracker/` — expense-bot
- `HouseBotRouter/` — router
