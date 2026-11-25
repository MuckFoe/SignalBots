# Specs

Every spec in this project, one row each. A spec is one file:
`specs/<NNN-slug>/spec.md`. Its `plan.md`, `tasks.md` and `notes.md` are added
beside it as the feature moves through the pipeline described in `CLAUDE.md`.

## Viewer

`specs/index.html` shows everything here in one place: this index, each spec's
artifacts, requirements paired with their acceptance criteria, task progress.
It holds no copy; it reads the markdown each time it loads. From the root of
the repository:

```
python specs/serve.py
```

then open <http://127.0.0.1:8777/>. A different port goes after the file name.

**Progress.** The *Progress* view (`#progress`) lists every spec with every
task, above three charts: tasks done and open per spec, how many specs have
each artifact, and tasks per wave. One row of filters — text, status, artifact,
open or done, only `[P]` — narrows the charts and the list together; clicking a
bar in the artifact chart sets that filter. All of it is counted from the
markdown on each load. A task's number, wave, `[P]` flag and requirement ids
are read from `tasks.md`: the checklist line, a table with *Wave* and *Tasks*
columns, and the `**Spec:**` line under the heading that starts with the task's
number. `/sdd-tasks` writes that format.

**Editing.** Every file the viewer shows has an **Edit** button: this index,
and each spec's `spec.md`, `plan.md`, `tasks.md` and `notes.md`. It opens the
raw markdown; **Save** (or Ctrl+S) writes the whole file back. Task checkboxes
can be ticked directly, in a `tasks.md` and in the Progress view. What to know
before relying on it:

- A save writes straight to the working tree. Nothing is committed; `git diff`
  shows what changed, and git is the undo.
- If the file changed on disk after the page read it — an agent or an editor
  got there first — the save is refused and nothing is written. Reload, then
  apply the change again.
- It edits files that exist. It does not create, rename or delete one; the
  `/sdd-*` skills create the artifacts.
- It does not know the pipeline. Changing a spec does not mark its plan or
  tasks stale, and changing a status here is the human moving it.
- Task checkboxes are list items — `- [ ] **1** — …` — not headings.

`specs/serve.py` is what saves: Python standard library, bound to `127.0.0.1`,
and it accepts writes only to those markdown files and only from this page.
Under any plain static server (`python -m http.server`, run inside `specs/`)
the page still works, read-only, and says so in its header.

The page loads its markdown renderer from cdnjs, so it needs network access.

## Index

| # | Spec | What it requires | Status | Open questions |
|---|---|---|---|---|
| 001 | [bot-router](001-bot-router/spec.md) | One entry point for Signal and WhatsApp: dedupe, assign each chat a job, forward to its bot, send replies back | draft | 0 |
| 002 | [group-move-and-identity](002-group-move-and-identity/spec.md) | Move a group between Signal and WhatsApp with its data; one member per person across ids | draft | 0 |
| 003 | [chore-tracking](003-chore-tracking/spec.md) | Recurring, open and one-time chores; done/undo, edit, list, history, per group | draft | 0 |
| 004 | [chore-reminders-and-vacation](004-chore-reminders-and-vacation/spec.md) | Due and overdue reminders, quiet hours, Signal link reminder, vacation pause and prep tasks | draft | 0 |
| 005 | [chore-group-setup-members-stats](005-chore-group-setup-members-stats/spec.md) | Group setup, display names, admin commands, language and timezone, stats and charts, reset, help and tutorial | draft | 0 |
| 006 | [chore-llm-assist](006-chore-llm-assist/spec.md) | Free text to a validated command through the local LLM, confirm before acting, silent on chatter, cold start | draft | 0 |
| 007 | [rental-watcher](007-rental-watcher/spec.md) | Watch rentals for dates and guests, nightly check, announce price and availability changes, drive time | draft | 0 |
| 008 | [rental-llm-page-reading](008-rental-llm-page-reading/spec.md) | LLM fills missing price or availability only with values found on the page; optional headless browser | draft | 0 |
| 009 | [operations](009-operations/spec.md) | Compose stack, deploy, release changelog broadcast, Signal link monitor, Mac mini LLM host | draft | 0 |

**Status** is one of `draft` (written, not approved), `approved` (every
`[NEEDS CLARIFICATION]` resolved and the spec signed off), `planned`, `in
progress`, `validated`. Only the human moves a spec out of `draft`.

Adding a spec means adding its row here; `/sdd-specify` does that. The row links
to the spec file — `[slug](NNN-slug/spec.md)` — which is how the viewer finds
it. Numbers are never reused.

Specs 001–009 were written on 2026-11-24 from the code as it ran then. Its
15 open questions were answered the same day, and the changes they called for
were built the same day too. Each such requirement says *built 2026-11-24*.
The only thing left is a manual one: the browser trial in spec 008.

## Deprecated, no spec

- **HouseExpenseTracker** (expense-bot) — deprecated 2026-11-24: hidden from
  new chats (spec 001, FR12, built 2026-11-24). Groups that already use it keep
  working, so it stays built and deployed.
- **HouseGroceryTracker** (grocery-bot) — decommissioned 2026-09-06: not built,
  routed or deployed. The source stays in the repository.
