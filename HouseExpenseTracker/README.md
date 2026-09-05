# Expense Split Bot

Splitwise/Tricount-style shared expense tracking over Signal. Runs as `expense-bot` in the **ProjectHub** stack.

## Features

- Group members with display names (`join`, `name`)
- Add expenses (guided `add` or quick `spent 25.50 pizza`)
- Custom splits (`split 100 dinner | Alice:60 Bob:40`)
- Balances and simplified who-owes-whom (`balances`)
- Record settlements (`settle Bob` or `settle Bob 20`)
- Expense list/detail/delete, total spending, currency setting
- English and German

## New Signal group

Reply `expenses` when the router asks what this chat is for, then follow setup (language → your name → others `join`).

## Deploy

```bash
cd ..
docker compose up -d --build
```
