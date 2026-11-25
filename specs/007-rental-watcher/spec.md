# 007 — Holiday rental watcher

**Status:** draft · written 2026-11-24 from the code
(`HouseRentalTracker/app.py`, `commands.py`, `poller.py`, `scrapers.py`,
`storage.py`, `drive_time.py`, `docker-compose.yml`). How pages are read when
the scrapers miss something is spec 008.

## Summary

A group watches holiday rentals for fixed dates and a guest count. The bot
checks every rental once a night and tells the group when the price or
availability changes.

## Functional requirements

- **FR1** — Group setup, language, `admin` prefix and `admin language` work as
  in the chore bot (spec 005, FR3–FR5). The person who sets the language
  becomes admin.
- **FR2** — `add` starts a guided add: link, name (with a suggestion from the
  page), check-in, check-out, guests, then a confirmation that names the
  website and the adapter. `add <link>` and
  `add <link> <check-in> <check-out> [guests]` fill in steps. Dates are
  YYYY-MM-DD, check-out must be after check-in, and guests must be 1–30.
- **FR3** — Every http(s) link is accepted. The HomeToGo family (HomeToGo,
  Casamundo, fewo-direkt, …) is read through its API, and any other page as a
  generic page (schema.org JSON-LD, then the LLM reader of spec 008). A website
  added with `add website <domain>` is listed under `websites` for the group
  that added it only, and read as a generic page. A text that is not a link
  gets "That does not look like a valid link". (Built 2026-11-24. Before that,
  added websites used the HomeToGo adapter and were shared by all groups.)
- **FR4** — On add, the rental is read once and stored with what was found:
  availability, price per night, total, cleaning fee, currency, title,
  location, bedrooms, bathrooms, rating, and drive time.
- **FR5** — `overview` (also `list`, `status`) shows every rental of the group
  with stay, nights, guests, availability, prices, cleaning fee, location,
  drive time, rooms, rating, last checked and last changed.
- **FR6** — Scheduled check: at each time in `POLL_TIMES` (container clock,
  UTC; deployed `02:00`, code default `08:00,20:00`) every active rental of
  every group is read again, once per time slot.
- **FR7** — A change in availability, price per night, total, currency or
  cleaning fee is stored in the rental's history and announced to the rental's
  group: "Change for '<name>'" with availability, price per night and total.
  Nothing is sent if nothing changed.
- **FR8** — `check` / `prüfen` / `jetzt prüfen` (also `admin check`) reads
  this group's rentals now and answers with their changes, or "No changes
  found". Other groups' rentals are left for the nightly run. (Built
  2026-11-24. Before that it read every group's rentals, and their changes
  were stored without being announced.)
- **FR9** — `remove <name>`, `history <name>` (stored changes with date,
  availability, prices), `websites` (known and added), and `stats` (rentals the
  sender added, rentals in the group).
- **FR10** — Drive time from the group's origin (default Stuttgart), set with
  `drive from <city>`. The place is looked up with Nominatim and the drive with
  the public OSRM server. If a rental has no coordinates, its last known drive
  time is kept.
- **FR11** — Charts: `overview chart` (total prices), `overview chart night`
  (price per night), `history <name> chart`.
- **FR12** — Data lives in `rentals.db` only. The rental bot never reads chore
  data.
- **FR13** — In a group, a message the bot does not understand, or one with no
  text (a photo, a sticker), gets no reply. In a direct chat it gets
  "I don't know that command" plus the help. (Built 2026-11-24.)

## Acceptance criteria

- **FR1** — `deutsch` in a new rental group completes setup, and the sender is
  admin.
- **FR2** — `add <link> 2027-07-08 2027-07-01 4` returns "check-out must be
  after check-in".
- **FR3** — `add not-a-link` returns "That does not look like a valid link".
  After `add website example.com` in group A, `websites` lists example.com in
  A but not in B, and a link to it is read as a generic page in both.
- **FR4** — A HomeToGo link added for 7 nights shows a total price in
  `overview`.
- **FR5** — `overview` in a group with two rentals lists both with all fields,
  and missing values are shown as unknown.
- **FR6** — With `POLL_TIMES=02:00`, rentals are read once between 02:00 and
  02:01 UTC, and not again in the same minute after a restart.
- **FR7** — A total price going from 1200 to 1100 sends one change message to
  that group and adds one history row.
- **FR8** — `check` with no changes returns "No changes found". A `check` in
  group A reads none of group B's rentals.
- **FR9** — `remove Haus am See` removes it from `overview`.
- **FR10** — `drive from München` changes the drive time at the next check.
- **FR11** — `overview chart` in a group with prices returns an image.
- **FR12** — Deleting `chores.db` has no effect on the rental bot.
- **FR13** — "bis später" in a rental group gets no reply. "?" gets the help.

## Open questions

None. Decided 2026-11-24: a manual check covers the asking group only (FR8),
the bot is silent on unknown text in groups (FR13), and added websites are
generic, read with the LLM, and kept per group (FR3).

## Sources

Tests: `test_scope_migration.py`. The scrapers and the poller have no tests.
