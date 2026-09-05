# File templates

Exact shapes for the files this skill writes (Phases 3, 5 and 7). Adapt wording
to the project; keep the structure and the two rules below, which are what make
the output reusable.

---

## The two layers

**Rules are portable. Bindings are not.**

`rules/*.md` carry policy only — no paths, no commands, no file or symbol
names, no framework specifics. `CLAUDE.md` carries everything that binds a rule
to this particular project.

The test before writing any rule: *would this fire in a different project with
a different stack?* If it only bites given this codebase's particular design,
it is a finding, not a rule — record it in `_progress.md` and move on.

This split is what lets a ruleset be lifted into the next repository whole. A
single rule containing `go build ./...` makes the whole file project-specific.

| Layer | Holds | Portable |
|---|---|---|
| `rules/*.md` | The policy. What must be true. | yes |
| `CLAUDE.md` | The bindings. Which commands, which paths, which classifications. | no |

## Always-on versus triggered

Classify every rule by **when it applies**, not by topic. The test: *would
loading this rule late cause harm?*

- **Always-on** — the rule governs behavior that happens before the agent would
  think to go read a rule file. A destructive-operation rule loaded after the
  command ran is worthless. These are cited one line each in `CLAUDE.md`.
- **Triggered** — loading it at the moment the area is touched is timely. These
  live only in their domain file and are reached through the routing table.

Cite, never copy. An always-on entry in `CLAUDE.md` is the rule id, a one-line
statement, and a path. Copying full rule text into `CLAUDE.md` creates a second
copy that will drift, and a ruleset that contradicts itself is worse than
either version alone.

Keep the always-on set small enough to scan — under about ten. If it grows past
that, the classification has gone soft.

---

## `CLAUDE.md` — the router

Loaded on **every** session, so it pays rent on every turn. Identity, commands,
citations, routing, bindings. Nothing else. Under 200 lines.

```markdown
# <Project name>

<One paragraph: what this is, who runs it, current stage. Enough that an agent
with no other context knows what it is working on and what breaking it costs.>

## Stack
- **<Component>** `<dir>/` — <language, framework, notable libraries>
- **Data** — <store, how it runs locally, ports and proxies>

## Commands
| Task | Command |
|---|---|
| Fast check (every change set) | `<...>` |
| Feature check (before done) | `<...>` |
| Run <component> | `<...>` |

<Any command with a non-obvious prerequisite gets one line here, not a
paragraph. Flag anything the commands cannot yet do — a dormant test clause is
worth stating.>

## Always
Apply on every turn. Full text in the linked file.

- **<ID>** — <one-line statement> → `rules/<domain>.md`
...

## Rules
Read before working in the area. Not loaded automatically.

| When you are... | Read |
|---|---|
| <trigger phrased as an activity> | `rules/<domain>.md` — <ids> |
...

## Bindings
<Everything a rule needs to be applicable here. One heading per rule that has a
binding, naming the rule id so the connection is explicit.>

**<Binding name>** (<RULE ID>). <The project-specific content.>

## Open
See `rules/_progress.md` for follow-ups and findings, `rules/_decisions.md`
for settled questions.

## Context
When compacting, preserve: the requirement id in progress, the files modified
this session, and the exact verification command with its last result.
```

**Do not use `@path` import syntax for domain rules.** Imports load eagerly at
session start, which reintroduces exactly the context cost the split avoids.
Reference paths in prose and in the routing table so files are read when their
trigger fires.

---

## `rules/<domain>.md`

Compact form: **statement, one-line why, enforcement tier.** Nothing else.

```markdown
---
domain: <name>
reviewed: <YYYY-MM-DD>
---

# <Domain> rules

<Optional single line: what this file governs, and which neighbouring rules
already cover adjacent ground so the reader is not left looking for them.>

## <ID> — <short imperative title>
<The rule. Imperative, falsifiable, portable. Two to six lines. Where the rule
has levels or clauses, use a short list — not prose.>
**Why:** <one line>
→ *<enforcement tier, and where the binding lives if it has one>*
```

**Keep the one-line why.** It is the highest-value-per-token content in the
file, for two reasons: it lets the model extend a rule to mechanisms the
statement did not enumerate, and — more importantly — it tells the model when
the rule does *not* apply. A statement alone is a blocklist; a statement with a
reason is a principle.

**Do not keep the long rationale.** The paragraph-length argument and the
"if wrong" analysis are decision support for the user at accept time. Once the
rule is accepted they are cost with no reader. They stay in the elicitation
transcript.

Numbered ids formed from the domain (`VER3` in verification, `SEC1` in security)
exist so rules can be cited in review and in
commit messages — "violates VER3" is a complete review comment. Do not renumber
on edit; retire an id rather than reusing it.

---

## `REQUIREMENTS.md`

Written in Phase 4, before any rule is proposed. Full protocol in
`references/requirements.md` — nothing goes in here that is not unambiguous.

```markdown
# Requirements

Every change is driven by a requirement, and its commit names it. A
requirement may be a single sentence — the bar is that it exists, was written
first, and has exactly one reading.

Ids are stable and never reused after retirement.

## R<n> — <short title>
<What must be true when this is done. One or two sentences. An outcome, not a
design.>

**Done when:** <the decidable condition>
**Not included:** <the boundary — what this explicitly does not cover>
**Source:** <citation from input/, or "user, <date>">
**Status:** open | in progress | done | dropped
```

**Out of scope** for the project as a whole gets its own section at the end and
is confirmed explicitly. Unstated scope boundaries are where projects grow.

---

## `docs/concepts.md`

Written during Phase 3 and added to whenever a term is settled. Phase 4's
clarity bar depends on it: a requirement whose terms are undefined is itself
undefined, however carefully the requirement is worded.

```markdown
# Concepts

Domain vocabulary as the user defined it. A term here means what this project
means by it, which is not always what the wider field means by it.

Terms marked **undefined** are undefined on purpose. Do not supply a plausible
meaning — that is the inference this kit exists to prevent.

## <Term>
<The definition, in the user's words where possible.>

**Source:** <citation from input/, or "user, <date>">
**Related:** <other terms, where the relationship was stated rather than assumed>

## <Term> — undefined
Appears in <where>, never defined. <What is known about its use, if anything.>

**Blocking:** <requirement ids or rules that cannot be written until this settles>
```

One heading per term, and keep the file flat. A glossary that grows
sub-sections stops being scannable, and a glossary nobody scans is one where
terms quietly acquire a second meaning.

**Record the undefined terms too.** An empty glossary and a glossary saying
"these four terms were never defined" look equally short, and only one of them
tells the next session where the ground is soft.

---

## `rules/_decisions.md`

```markdown
# Ruleset decisions

Settled questions. Read before proposing new rules — do not re-litigate these.

## Rejected
| Proposed rule | Reason | Date |
|---|---|---|

<Also note rules deliberately *not proposed* in a domain and why, so a later
run does not rediscover them. And which domains were skipped entirely.>

## Deferred
| Proposed rule | Revisit when | Date |
|---|---|---|

## Edited during elicitation
The user rewrote these. Originals kept so the intent behind each edit stays
visible.

| ID | As proposed | As accepted |
|---|---|---|

## Structural decisions
<Numbered. Decisions about how the ruleset itself is built — the portability
split, the written form, the classification axis. These outlive any individual
rule and are the most expensive things to reverse.>
```

---

## `rules/_progress.md`

Written from the first domain, updated as each closes. It is what makes a long
run survivable across a context reset — and a run that cannot survive one will
not finish.

```markdown
# Ruleset progress

<Status line: started, current state, whether elicitation is open or closed.>

## Resume here
<Only while paused. The exact rule awaiting a verdict, quoted in full so the
next session does not need the transcript. Then what comes after it.>

## Domains
| # | Domain | Status | Rules |

## The ruleset
| ID | Rule | Always-on |

## Project findings — not rules
<Real problems surfaced during elicitation that failed the portability test.
Backlog, not policy. This section is what keeps the ruleset clean — without
somewhere to put them, situational rules leak in.>

## Open follow-ups
<Checkboxes. Especially: rules accepted at hook or CI tier whose enforcement
has not been built yet, and rules that are dormant because they depend on
something that does not exist.>
```

---

## Writing style for rules

- Imperative mood. "Wrap errors with context", not "errors should be wrapped."
- One rule per rule. If it contains "and", check whether it is two. The test:
  could the user accept one half and reject the other, and both still make
  sense? If yes, they are two rules.
- Name the thing. "Validate at the trust boundary" beats "validate early."
- State the exception if there is one. An unstated exception gets discovered as
  a violation later and erodes the whole file's authority.
- No hedging. A rule that says "generally prefer" is advisory — label it that
  way in the enforcement line instead of softening the statement.
- Never write a rule the agent would follow anyway. A rule that restates a
  default is noise, and noise is what buries the rules that matter. A rule that
  *overrides* a common default is exactly what earns its slot.
