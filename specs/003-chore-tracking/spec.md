# 003 — Chore tracking

**Status:** draft · written 2026-11-24 from the code
(`HouseChoreTracker/commands.py`, `storage.py`, `schedule_utils.py`,
`dialogue_utils.py`). Every command has a German and an English form. Only the
English one is named here.

## Summary

A household group keeps a list of its chores: recurring ones, open tasks with
no schedule, and one-time tasks. Members mark them done, and the bot keeps the
history. Reminders are spec 004, and members, stats and admin are spec 005.

## Terms

- **Recurring chore** — due again after an interval (`every 2 weeks`, `1 day`,
  `12 hours`, months, years) or on a weekday (`every Wednesday`).
- **Open task** (`todo`) — no schedule. It can be marked done at any time and
  never reminds.
- **One-time chore** (`once`) — due on one day (`today`, `tomorrow`, a
  weekday, `in 2 days`). It disappears from the list when done or deleted, and
  counting it in stats is optional.
- **Confirmation** — whether a chore has to be marked done. Only chores that
  need confirmation keep reminding while overdue.

## Functional requirements

- **FR1** — Chores, their history and their settings belong to one scope. A
  group never sees another group's data, and two groups may each have a chore
  of the same name. Names are unique within a scope.
- **FR2** — `add` starts a guided setup: name, then schedule, then reminder
  time if the schedule needs one, then confirmation, then the overdue-reminder
  interval if confirmation is on. `add <name>` starts it with the name filled
  in.
- **FR3** — `add <name> <schedule>` asks "Add '<name>' (<schedule>)?" and
  creates the chore on `yes`. Schedules can be written naturally (`every hour`,
  `jeden Mittwoch`) or as short forms (`1 hour`, `Mittwoch`).
- **FR4** — `todo <name>`, or answering the schedule question with
  `no schedule` / `ohne` / `ohne termin` / `kein termin` (small typos
  accepted), creates an open task.
- **FR5** — `once` starts a guided one-time setup: name, when, time, counts in
  stats?, confirmation. `once <name> [today|tomorrow|<weekday>]` fills in what
  it can and asks for the rest.
- **FR6** — `done <chore>` records a completion with timestamp and sender.
  `done <chore> for <person>` records it for another member by display name.
  A sender with no display name is asked for one first (spec 005, FR1). A
  one-time chore is removed from the list when done.
- **FR7** — `undo done <chore>` removes the last completion of that chore.
- **FR8** — `edit <chore>` offers name, schedule, reminder time, confirmation,
  overdue reminder, or delete. Each choice asks one follow-up question, and
  deleting asks for confirmation.
- **FR9** — One-line editing commands change one setting and keep the history:
  `schedule <chore> <schedule>`, `confirmation <chore> on|off`,
  `reminder <chore> <interval>` (overdue repeat),
  `reminder time <chore> <HH:MM>`, `rename <old> -> <new>`, `delete <chore>`.
- **FR10** — `list` shows each chore with its next due or overdue state.
  `list extend` also shows the reminder schedule, reminder time, confirmation,
  overdue reminder and last completion.
- **FR11** — `history [limit]` shows the most recent completions: chore, who,
  when.
- **FR12** — Times shown to members are in the group's timezone (default
  Europe/Berlin, spec 005, FR6).
- **FR13** — Every guided dialogue can be left with `cancel` / `abbrechen`. A
  dialogue untouched for `PENDING_STALE_HOURS` (default 1 h) counts as stale,
  and one older than `PENDING_MAX_HOURS` (default 24 h) expires.
- **FR14** — A command word sent on its own (`done`, `undo`, `rename`,
  `schedule`, `reminder`, `confirmation`, …) gets its usage line. A near-miss
  of a known command gets "Did you mean: <command>?". Other text goes to the
  LLM assist if it is on (spec 006), else gets no reply.
- **FR15** — A short usage tip is added under some replies (list, done, add,
  undo, history, name, stats), at most twice per member and tip.

## Acceptance criteria

- **FR1** — Group A and group B can each add "Bad putzen". `list` in A never
  shows B's chores.
- **FR2** — `add`, `Staubsaugen`, `every 2 weeks`, `08:00`, `yes`, `default`
  creates a chore due every 2 weeks at 08:00 that needs confirmation, with the
  default overdue repeat.
- **FR3** — `add bins every Wednesday` then `yes` creates "bins" due weekly on
  Wednesday.
- **FR4** — `add Spüle putzen ohen` creates an open task "Spüle putzen".
- **FR5** — `once IKEA`, `tomorrow`, `anytime`, `no`, `no` creates a one-time
  chore that is not counted in stats and is gone from `list` after `done IKEA`.
- **FR6** — `done bins for Anna` adds a completion credited to Anna. With no
  member called Anna, it answers "I don't know a group member called 'Anna'".
- **FR7** — After `done bins` then `undo done bins`, the last completion of
  bins is the one before.
- **FR8** — `edit bins`, `delete`, `no` keeps the chore.
- **FR9** — `schedule dishes every day` changes the schedule, and `history`
  still lists the earlier dishes completions.
- **FR10** — A chore whose due time has passed shows as overdue in `list`.
- **FR11** — `history 3` shows three lines, newest first.
- **FR12** — With timezone Europe/Berlin, a completion at 10:00 UTC in summer
  shows as 12:00.
- **FR13** — `add`, then `cancel`, returns "Cancelled", and no chore is
  created.
- **FR14** — `done` on its own returns "Usage: done <chore> [for <person>]".
  `lsit` returns "Did you mean: list?".
- **FR15** — The third `list` by the same member carries no tip.

## Open questions

None. **Decided 2026-11-24:** the specs are the reference for what the chore
bot does. `HouseChoreTracker/README.md` was rewritten from specs 002–006 on
2026-11-24 and points to them for detail.

## Sources

Tests: `test_command_surface.py`, `test_command_surface_extra.py`,
`test_one_shot.py`, `test_no_schedule_phrases.py`, `test_whole_picture.py`.
