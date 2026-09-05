# Wiring the harness

Runs after the ruleset is written (Phase 8). A ruleset states what must be true;
the harness is what makes some of it hold without the agent choosing to comply.

The ruleset and the harness are different kinds of thing and the gap between
them is where rulesets fail quietly. A rule accepted at `hook` tier with no hook
behind it is not a stricter rule than an advisory one — it is an advisory rule
that has been mislabeled, and the label buys confidence nobody earned.

**Everything here is proposed and approved the same way rules are: one at a
time, with a stated cost.** A harness the user did not agree to is one they will
disable the first time it gets in the way.

---

## Order

Work in this order. Each step is skippable and several will not apply.

1. **Enforcement debt** — the hooks and CI the accepted rules already imply
2. **Permissions** — what the agent may do without asking
3. **Verification command** — the single check that proves the project works
4. **Subagents** — where fresh context is worth more than continuity
5. **External tools** — CLI tools and MCP servers
6. **Plugins** — only when a listed need matches one

---

## 1. Enforcement debt

`rules/_progress.md` lists every rule accepted at `hook` or `CI` tier whose
enforcement has not been built. This is the list, and it was written by the user
accepting those tiers.

For each, present the rule, what a hook or job would actually check, and what it
would cost when it fires on a false positive. Then build it, or downgrade the
tier honestly.

**A hook must be cheap and deterministic.** It runs on every matching event. A
hook invoking a language model, hitting the network, or taking seconds is a hook
the user will remove. If a rule cannot be checked cheaply and deterministically,
it is `advisory` or it is `CI` — those are the honest options.

`.claude/hooks/check-ruleset.mjs` in this kit is a worked example: it validates
what exists rather than what is complete, so it never blocks a half-finished
run, and it exits 2 with the specific failure on stderr so the agent can fix it
without the user relaying anything.

Useful events: `PreToolUse` to block an action before it happens, `PostToolUse`
to check the result of one, `Stop` to gate the end of a turn. A `Stop` hook is
the deterministic version of "verify your work" — Claude Code overrides it after
8 consecutive blocks, so it must be satisfiable.

## 2. Permissions

Ask directly: **what may the agent do without asking, in this repository?** The
`agent-conduct` domain has usually already settled the policy — this step writes
it into `.claude/settings.json` so it holds without being read.

Three lists, and the shape matters:

- `allow` — named, read-only, or trivially reversible. Test commands, linters,
  `git status`, `git diff`.
- `ask` — reversible but consequential. Commits, pushes, installs, migrations.
- `deny` — never, regardless of instruction. Secret files, credential paths,
  production endpoints.

The `deny` list is the one worth spending time on, because it is the only one
that holds when the agent has been talked into something. Ask what must never
be read or run **even if the agent believes it should be**.

Do not propose a blanket `Bash(*)`. A permission list that allows everything is
a permission list that was not worth writing.

## 3. Verification command

The `verification` domain established what proves the project still works. Make
that runnable and record it:

- Put the exact command in the `CLAUDE.md` command table.
- If the user wants the agent blocked from ending a turn while it fails, that is
  a `Stop` hook.
- If it cannot yet run — no tests, no build — say so plainly and record a
  follow-up in `_progress.md`. **A dormant verification clause honestly labeled
  is worth more than a command that does not exist**, because the first gets
  built and the second gets discovered during an incident.

## 4. Subagents

Propose a subagent where **fresh context beats continuity**, not wherever work
could be delegated. Two cases earn it reliably:

- **Investigation that would flood the main context.** Reading many files to
  answer one question. The subagent returns the answer; the files stay in its
  context.
- **Review that must not be biased by the reasoning that produced the work.**
  The author of a change is the worst judge of it. This is why `/project-startup`
  reviews its own output in Phase 10 rather than checking its own work inline.

This kit ships `input-analyst` and `ruleset-reviewer`. Project-specific ones go
in `.claude/agents/`. Give each the narrowest `tools` list that lets it finish —
a reviewer with `Write` is not a reviewer.

Do not propose a subagent per domain. Subagents cost a context handoff each, and
one that reports back something the main session could have read directly is
pure overhead.

## 5. External tools

**CLI tools first.** They are the most context-efficient way to reach an
external service, and the agent already knows the common ones. Ask what services
this project touches — GitHub, a cloud provider, an error tracker, a database —
and record the CLI and any auth prerequisite in `CLAUDE.md` bindings. `gh` in
particular is worth naming: without it, GitHub work falls back to unauthenticated
API calls that hit rate limits mid-task.

**MCP servers where no CLI exists**, or where the data is structured enough that
parsing CLI output is the wrong shape — an issue tracker, a design tool, a
database the agent should query directly. Record the server in `.mcp.json` so
the team gets it, and note in `CLAUDE.md` what it is for.

Ask before adding either: an MCP server the user has not authorised is a
dependency and a trust decision, not a convenience.

## 6. Plugins

Only when a need already on the list matches one. If the project uses a typed
language, a code-intelligence plugin gives precise symbol navigation and
post-edit error detection — that is a real, named benefit. Otherwise say there
is nothing to recommend rather than filling the section.

---

## Writing it

Same discipline as Phase 7: show the exact file content, get confirmation, then
write. Files this phase may touch:

| File | Holds |
|---|---|
| `.claude/settings.json` | Permissions and hooks |
| `.claude/hooks/*` | Hook scripts |
| `.claude/agents/*.md` | Project-specific subagents |
| `.mcp.json` | MCP servers, checked in for the team |

Never overwrite an existing `settings.json`. Read it, show the merged result,
and confirm — the user may have local permissions that predate this run and
losing them silently is exactly the kind of thing that ends trust in a tool.

Record what was built in `_progress.md`, and move anything not built to open
follow-ups with the rule id that wanted it. **An unbuilt hook is a tier that is
currently a lie**, and the follow-up list is what makes that recoverable rather
than permanent.
