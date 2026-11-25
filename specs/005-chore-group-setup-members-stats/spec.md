# 005 — Chore bot: group setup, members, admin, stats, help

**Status:** draft · written 2026-11-24 from the code
(`HouseChoreTracker/commands.py`, `storage.py`, `display_names.py`,
`stats_charts.py`, `chart_parse.py`, `tutorial.py`, `bot_registry.py`).

## Summary

Everything around the chores themselves: setting up a new group, member names,
what "admin" means, the group settings, statistics and charts, resetting a
group, and help and the tutorial.

## Functional requirements

- **FR1** — Display names. `name <name>` sets the sender's name in this group:
  2–24 characters, letters, digits, spaces or hyphens. A member's first `done`
  without a name asks for one, then records the completion.
- **FR2** — A display name is unique within a group (case-insensitive). A taken
  name is refused, with the hint `i am <name>` in case it is the sender's own
  name from before a move.
- **FR3** — Group setup. The first message in a new group asks for the
  language (`english` / `deutsch`). Whoever answers becomes the group's first
  admin. If more than one bot instance is registered (`BOT_REGISTRY`), the group
  then picks one with `bot <number>`. With one instance it is picked
  automatically. A direct chat needs no setup.
- **FR4** — Admin commands are written `admin <command>` in groups:
  `admin help`, `admin language de|en`, `admin timezone <zone>`,
  `admin stats`, `admin quiet hours HH:MM-HH:MM`,
  `admin auth reminder on|off`, `admin reset group`. The same command without
  the prefix gets the hint to put `admin` in front. Any member may use them:
  the prefix guards against accidental changes and is not a permission
  (decided 2026-11-24). Being an admin matters only for starting a group move
  (spec 002, FR1) and for FR12.
- **FR5** — Language per scope (`en`, `de`). Every reply is in the scope's
  language, and help asked for in the other language (`hilfe` in an English
  group) is answered in that language.
- **FR6** — Timezone per scope, default Europe/Berlin. Short names are accepted
  (`berlin`, `utc`, `london`, `paris`, …). Reminder times, quiet hours and
  displayed times use it.
- **FR7** — Stats: `my stats` (completions, distinct chores, favourite, last
  done, per-chore counts), `my stats chore <name>`, `group stats` (per person
  and per chore), `group stats chore <name>`, and `admin stats` (chore count,
  completions, action counts, top chores, recent actions). One-time chores that
  count in stats are grouped under "one-time chores".
- **FR8** — Charts: `my stats chart`, `group stats people`,
  `group stats chores`, `group stats matrix`, and `group stats all` (all in one
  image). A chart is sent as an image with the text. With too little data, the
  bot says so.
- **FR9** — `admin reset group` returns a 6-digit code. Only the same sender,
  within 10 minutes, can confirm with `admin reset group confirm <code>`, which
  deletes the group's chores, history, reminders, admins and settings.
  `admin reset group cancel` drops the request.
- **FR10** — `help`, `chore help`, `edit help`, `vacation help`, `admin help`.
  `tutorial` lists 9 topics (getting started, adding, done/undo, reminders,
  open and one-time, editing, vacation, statistics, admins and moving), and
  `tutorial <n>` shows one.
- **FR11** — Every command, setting change and completion is written to
  `action_logs` with sender and time.
- **FR12** — *(built 2026-11-24)* `admin add <name>` /
  `admin hinzufügen <Name>` makes the member with that display name an admin,
  and `admin remove <name>` / `admin entfernen <Name>` takes it away. Only an
  admin can do either, and the last admin of a group cannot be removed.
  `admin list` shows the group's admins by display name. The rental bot has
  no display names, so it does not get these commands: its admins remain the
  first one plus whoever completes a move.
- **FR13** — *(built 2026-11-24)* The `groups` / `gruppen` command is
  removed. Nobody can list other groups from a chat.

## Acceptance criteria

- **FR1** — `name A` returns "Please use 2–24 characters". `name Anna`
  returns "Your name is now: Anna".
- **FR2** — A second member sending `name anna` gets "already taken".
- **FR3** — In a fresh group with one bot instance, `deutsch` returns "Sprache
  … Deutsch" and the setup-complete message, and that sender is admin
  (`/internal/scope` reports `is_admin: true` for them).
- **FR4** — `language de` in a group returns the admin-prefix hint, and the
  language does not change. `admin language de` from a member who is not an
  admin changes it.
- **FR5** — `hilfe` in an English group returns the German help.
- **FR6** — `admin timezone london` sets Europe/London, and quiet hours are then
  evaluated in London time.
- **FR7** — After Anna completes bins twice, `group stats chore bins` shows
  "Anna: 2x".
- **FR8** — `group stats all` in a group with completions returns text plus one
  PNG.
- **FR9** — A confirm code sent by a different member returns "Reset not
  confirmed", and the chores stay.
- **FR10** — `tutorial 9` returns the "Admins and moving the group" topic.
- **FR11** — `done bins` adds an `action_logs` row of type `done`.
- **FR12** — An admin sends `admin add Anna`, and Anna can then start a move.
  A non-admin sending `admin add Ben` is refused. `admin remove <self>` as the
  only admin is refused.
- **FR13** — `groups` gets no group list in any chat.

## Open questions

None. Decided 2026-11-24: admin commands stay open to every member (FR4),
admins can be added and removed (FR12), and `groups` is gone (FR13). Tutorial
topic 9 and `admin help` name the new admin commands.

## Sources

Tests: `test_member_names.py`, `test_tutorial.py`, `test_command_surface*.py`.
