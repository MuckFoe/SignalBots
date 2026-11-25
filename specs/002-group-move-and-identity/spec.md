# 002 — Moving a group between Signal and WhatsApp, one identity per person

**Status:** draft · written 2026-11-24 from the code
(`HouseBotRouter/migrations.py`, `HouseBotRouter/identity.py`,
`HouseBotRouter/app.py`, each bot's `scope_migration.py` and `/internal/migrate`
and `/internal/merge_member`). Released 2026-10-21 and 2026-10-23 (CHANGELOG).

## Summary

A group can move from Signal to WhatsApp or back and take all its bot data
along. Separately, a person appears as one member of a group even though
Signal and WhatsApp name them by different ids (number, UUID, `@c.us`, `@lid`),
and the id can change from one message to the next.

## Functional requirements

- **FR1** — `umzug whatsapp` / `move whatsapp` (likewise `signal`, also
  `umziehen`, `nach`/`to`) in a group with a job starts a move. Only an admin
  of that group in the owning bot may start one. Starting a move to the
  platform the group is already on is refused.
- **FR2** — Starting a move returns a 6-digit one-time code that is valid for
  30 minutes. A new start in the same group replaces its earlier code.
- **FR3** — `umzug <code>` / `move <code>` in a new group on the target
  platform completes the move. The code is refused if it is unknown or expired,
  if it is sent on the wrong platform, or if the bot is already in use in the
  receiving group.
- **FR4** — On completion the owning bot moves every row of the old scope to
  the new one (`/internal/migrate`). The person completing the move becomes an
  admin there. The router moves the job to the new scope and marks the old
  scope as moved, and the old group is told once that it has moved. From then
  on the old group gets no replies.
- **FR5** — After a move, the bot returns the old group's members (sender and
  display name). Members who have not been matched yet are listed in the new
  group with the prompt to send `ich bin <Name>` / `i am <name>`. Each member
  of the new group sees the prompt once.
- **FR6** — `ich bin <Name>` / `i am <name>` matching an unclaimed old member
  (case-insensitive) moves that member's history, admin rights and names to the
  sender (`/internal/merge_member`). A second claim by the same person is
  refused. A sentence that matches no old name ("ich bin gleich da") is passed
  on to the bot as an ordinary message.
- **FR7** — In groups, the router turns sender ids into the phone number where
  it can. A WhatsApp `<digits>@c.us` id becomes `+<digits>`. A Signal UUID
  becomes the number once signal-cli has sent both together. A WhatsApp `@lid`
  becomes the number through WAHA's lid lookup. Learned mappings are stored in
  `known_numbers`. Ids that cannot be resolved pass through unchanged.
- **FR8** — When a member is known by a number, rows the bot stored under any
  other id of that person in the group are folded into the number once per
  scope (`merged_aliases`). Old members with the same number are marked as
  claimed automatically, so they need no `ich bin`.
- **FR9** — Bots refuse a display name that another member of the same group
  already has (chore bot: spec 005, FR2).

## Acceptance criteria

- **FR1** — `umzug whatsapp` sent by a non-admin returns "only admins can start
  a move", and no code is created.
- **FR2** — A code used 31 minutes after it was issued returns "invalid or
  expired".
- **FR3** — A Signal-move code sent in another Signal group returns "please
  send it in the new WhatsApp group".
- **FR4** — After a move, `list` in the new WhatsApp group shows the chores of
  the old Signal group, and the old Signal group got the "has moved" notice
  once.
- **FR5** — The first message of each member in the new group is followed by
  the claim prompt that names the still-unclaimed members. Later messages are
  not.
- **FR6** — `ich bin Anna` in the new group gives Anna's old completions to the
  sender: `my stats` there shows them.
- **FR7** — The same person writing once from `491701234567@c.us` and once from
  a `…@lid` id is handed to the bot as `+491701234567` both times.
- **FR8** — A member whose completions are stored under a Signal UUID has them
  under the phone number after their next message.
- **FR9** — `name Anna` when another member already uses Anna returns "already
  taken".

## Open questions

None found in the code. Not tested end to end: only `HouseBotRouter/test_identity.py`
and the bots' `test_scope_migration.py` cover pieces of it.
