# Rental Tracker

Vacation rental tracking bot. Runs as the `rental-bot` container in the **ProjectHub** stack.

Deploy with the parent compose (one Signal QR, router forwards rental groups here):

```bash
cd ..
docker compose up -d --build
```

Standalone dev (no router): `docker compose up` in this folder — use `POST /internal/handle` to test.

Data: `rentals.db` only. Does not touch chore data.
