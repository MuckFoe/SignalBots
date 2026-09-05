# House Bots Stack

One Signal account, five services:

| Container | Role |
|-----------|------|
| `signal-api` | Signal link (one QR code) |
| `bot-router` | Receives webhooks, routes per group |
| `chore-bot` | Household chore tracker |
| `rental-bot` | Vacation rental price tracker |
| `expense-bot` | Shared expenses (Splitwise/Tricount style) |

## Deploy

From this directory (`ProjectHub`):

```bash
cp .env.example .env
# edit SIGNAL_BOT_NUMBER
docker compose up -d --build
```

Signal QR: `http://127.0.0.1:8080/v1/qrcodelink?device_name=signal-api`

## Data (separate, not merged)

- `housechoretracker_bot-data` → `chores.db`
- `projecthub_rental-bot-data` → `rentals.db`
- `projecthub_expense-bot-data` → `expenses.db`
- `projecthub_router-data` → `router.db` (group job assignments only)

Existing chore groups keep working: router detects them via chore-bot admins.

New groups are asked: `chores`, `rentals`, or `expenses`.

## Projects

- `HouseChoreTracker/` — chore-bot
- `HouseRentalTracker/` — rental-bot
- `HouseExpenseTracker/` — expense-bot
- `HouseBotRouter/` — router
