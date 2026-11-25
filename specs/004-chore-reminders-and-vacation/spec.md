# 004 — Chore reminders, quiet hours and vacation

**Status:** draft · written 2026-11-24 from the code
(`HouseChoreTracker/app.py` `_run_reminder_loop`, `storage.py` `due_reminders`,
`is_quiet_time`, `auth_reminder_due`, vacation tables, `vacation_utils.py`,
`commands.py` vacation handlers).

## Summary

A background loop runs every 60 s. It sends reminders for chores that are due,
repeats them while a chore that needs confirmation stays overdue, holds them
back during quiet hours, and pauses them while a member is on vacation.

## Functional requirements

- **FR1** — A recurring or one-time chore reminds once when it falls due. Due
  is counted from its last completion, or from its creation if it has none,
  plus any vacation pause. Open tasks and chores scheduled `no reminder`
  never remind.
- **FR2** — A chore that needs confirmation reminds again at its overdue-repeat
  interval until someone sends `done`. The default interval depends on the
  schedule: 5 min for minute or hour schedules, 1 h for schedules under 7 days,
  and 8 h for weekly, weekday, longer and one-time schedules. A chore that
  needs no confirmation reminds once per due date.
- **FR3** — A reminder names the chore and, if confirmation is needed, the
  exact `done <chore>` reply.
- **FR4** — A chore can have a reminder time (`HH:MM`, group local time).
  `anytime` means 08:00.
- **FR5** — Quiet hours per group, default 00:00–08:00 in the group's
  timezone, set with `admin quiet hours HH:MM-HH:MM`. A window may span
  midnight, and equal start and end means no quiet hours. A reminder that
  falls due during quiet hours is not dropped: it is sent on the first loop
  after the window ends.
- **FR6** — Reminders for a group go to that group. Reminders and vacation
  notices for a direct-chat scope `dm:<id>` go only to `<id>`. (Built 2026-11-24.
  Before that they went to every contact the bot had stored.)
- **FR7** — Signal link reminder: off by default, switched with
  `admin auth reminder on|off`. When on, the group gets a note about the
  linked-device risk with the re-link URL about every 25 days, outside quiet
  hours.
- **FR8** — Vacation per member: `vacation` (guided), `vacation 14 days`,
  `vacation in 3 days for 14 days`, `vacation status`, `vacation cancel`.
- **FR9** — Prep tasks before leaving: `vacation add <name>`,
  `vacation list`, `vacation delete <name>`, `vacation done <name>`,
  `vacation skip prep`. When a vacation starts with prep tasks open, it is in
  *prep* until they are done or skipped.
- **FR10** — While any member of a group has a vacation in prep or active,
  every chore reminder and the Signal link reminder of that group are paused.
- **FR11** — After a vacation, schedules continue from where they were, shifted
  by the pause. A weekly Friday chore reminds on the first Friday after the
  vacation, not on the day the member returns.
- **FR12** — The group is told when a member's vacation starts (with open prep
  tasks, if any) and when it ends.

## Acceptance criteria

- **FR1** — A chore `every 1 day` created at 09:00 with no completion reminds
  once at 09:00 the next day.
- **FR2** — A daily chore that needs confirmation and is left overdue reminds
  again 1 hour later, and stops after `done <chore>`.
- **FR3** — The reminder text for a chore that needs confirmation contains
  `done <chore>`.
- **FR4** — `reminder time dishes 19:30` makes dishes remind at 19:30 local
  time.
- **FR5** — With quiet hours 23:00–07:00, a reminder due at 02:00 arrives at
  about 07:00.
- **FR6** — With two contacts stored, a reminder for a chore created in A's
  direct chat reaches A only.
- **FR7** — `admin auth reminder on` and then 25 days without a pause bring
  one link reminder.
- **FR8** — `vacation in 3 days for 14 days` gives a planned vacation, and
  `vacation status` shows its start and end.
- **FR9** — With one prep task added, the vacation starts in prep. After
  `vacation done <task>` it is active.
- **FR10** — During an active vacation of one member, no chore reminder is sent
  to that group.
- **FR11** — A weekly chore due on the Friday that falls inside the vacation
  reminds on the first Friday after it ends.
- **FR12** — The group receives "<name>'s vacation has started" and later
  "… is over".

## Open questions

None. Decided 2026-11-24: direct-chat reminders go to that chat only (FR6).
One member's vacation pauses the whole group's reminders, as it does today
(FR10), because reminders are not addressed to anyone in particular.

## Sources

Tests: `test_whole_picture.py`, `test_command_surface_extra.py`.
