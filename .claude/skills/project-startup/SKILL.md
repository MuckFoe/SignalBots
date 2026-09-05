---
name: project-startup
description: Interactively build a project's agent ruleset and harness — a lean CLAUDE.md router, portable domain rule files, permissions, hooks and subagents — by proposing every rule one at a time and getting explicit approval before anything is written. Can ingest existing knowledge files (style guides, ADRs, READMEs, notes) and convert them into candidate rules.
disable-model-invocation: true
---

# Project Startup

Build the ruleset that governs agent work in this repository, then wire the
harness that makes part of it hold deterministically. Nothing is written to
disk until the user has approved it, rule by rule.

## Two hard constraints

### 1. Every rule is approved individually

**No rule reaches a file without an explicit verdict from the user on that
specific rule.** Not a batch. Not an implied yes. Not "sounds good, continue"
covering five proposals. One rule, one verdict.

This is not a formality — it is the entire point of the skill. A ruleset the
user did not author is a ruleset they will not trust, enforce, or maintain. If
the user says "just do the rest," stop and say that defeats the purpose, then
offer to speed up by narrowing domains instead.

### 2. Nothing about the project is inferred

**Never state as fact anything the inputs do not state.** Not the domain rules,
not the business logic, not the workflows, not what a term means, not what the
edge cases are. No threshold of obviousness suspends this.

An inferred fact and a stated fact are indistinguishable once written into a
rule file. From then on the inference is trusted, implemented, and defended —
and nothing marks it as invented. A wrong business rule is worse than a missing
one, because a missing one gets asked about.

Where something is not stated: ask, or record it as unknown. **"I could not
determine this" is always an acceptable answer and frequently the correct one.**
Full protocol in `references/ingestion.md`.

## Ground rules to state before starting

Open the session by telling the user, in your own words:

- Rules are proposed one at a time, each with evidence and a stated cost.
- Five verdicts: **accept** / **edit** (they rewrite it) / **reject** / **defer** /
  **record** (it is a real problem, but not a portable rule — see Phase 6).
- Rejections are recorded with reasons so future runs don't re-propose them.
- Nothing is written until a domain is fully resolved.
- They can stop at any point and keep what's been approved.

## Process

Phases 1 and 2 run in subagents. Everything after that is a conversation with
the user and runs here.

### Phase 1 — Input analysis

**Delegate to the `input-analyst` subagent.** It reads every file in `input/`
completely, writes `input/_analysis.md`, and returns the Questions section in
full plus a summary of the rest.

The delegation is not an optimisation. Reading the raw documents into this
context spends on Phase 1 the budget Phases 3–6 need for the interview, and an
interview conducted in a nearly-full context is where rubber-stamping starts.

Read `input/_analysis.md` yourself when you need detail beyond what came back.
Then walk the user through it, **questions first**. Those questions are the
decisions only they can make; every one closed by inference instead is a defect
that cannot be found later.

If `input/` is empty or absent, say so and continue. An empty input folder
raises the importance of the questions, it does not lower it.

### Phase 2 — Repository survey

**Delegate to the `Explore` subagent.** Skip entirely if there is no code yet.
Ask it for:

- Language, framework, build system, test runner, package manifests
- Directory structure and where the real boundaries are
- Existing config: linters, formatters, CI, docker, editorconfig
- Any existing `.claude/` setup, `CLAUDE.md`, or `.mcp.json`

Ask for a **findings summary, not rules**, and require that it report what it
could *not* determine — those gaps are where rules are most needed.

Keep facts observed in the code separate from claims made in the input
documents, and say plainly where the two disagree.

### Phase 3 — Business background and concepts

Walk the user through the analysis, **Questions section first**, and resolve
what can be resolved. Anything still open at the end of this phase stays open —
it does not get closed by inference (constraint 2).

Then confirm the project profile: what it is, who runs it, what stage it is at
(prototype / in production / handed off), where it runs, and what breaking it
would cost. The answers change which rules matter. A weekend prototype and a
system holding customer data deserve different rulesets, and proposing the same
list for both is the most common way this goes wrong.

**Write `docs/concepts.md` as you go** — the glossary of domain terms, each with
the definition the user gave and a citation. Phase 4's clarity bar depends on
it: a requirement resting on an undefined term is itself undefined. A term used
in the documents but never defined is recorded as undefined, not given a
plausible meaning.

This phase ends when the user agrees you have understood the subject matter.
Do not proceed on the basis that you have read the documents — reading them is
not the same as having understood what they leave out.

### Phase 4 — Requirements

Build `REQUIREMENTS.md` with the user, following `references/requirements.md`.

The bar is that **a requirement is written only when it is unambiguous**, and
where it is not, you say *precisely* what is unclear — naming the requirement,
quoting the ambiguous part, and stating the competing readings you can see.
"Let me know if anything is unclear" is not asking; it reliably produces
agreement and leaves the ambiguity in place.

One requirement at a time. A requirement containing an assumption is
indistinguishable from one the user specified the moment it is written down.

### Phase 5 — Domain selection

Present the candidate domains from `references/rule-catalog.md` with a one-line
statement of what each would govern and why you think it applies *here*, citing
what you found in Phase 1. The user picks which domains to work through and in
what order.

Do not propose a domain you found no evidence for unless the user's stated
stage makes it obviously relevant. Fewer, sharper domains beat complete coverage.

Create `rules/_progress.md` now, before the first proposal, using the template
in `references/templates.md`. It is what makes the run survivable across a
context reset — and a run that cannot survive one will not finish. Creating it
once the first domain closes is too late, because the reset does not wait.

### Phase 6 — Rule elicitation, one at a time

For each selected domain, propose rules individually in this format:

```
RULE  <domain>/<n>
─────────────────────────────────────────────
Statement   <the rule, imperative, one or two lines>
Why         <what goes wrong without it>
Evidence    <file:line, knowledge-file citation, or "no evidence — convention">
Tier        <advisory | rule-file | hook | CI> — see Enforcement tiers below
If wrong    <cost of this rule being a mistake — be honest>
```

Then collect the verdict with **`AskUserQuestion`**, offering all five
dispositions: accept / edit / reject / defer / record. Stop and wait. Do not
queue the next rule in the same message.

Use the tool rather than free text. Twenty-five verdicts typed by hand is where
attention runs out, and a verdict given because answering carefully had become
tiring is a rubber stamp with extra steps. When the user picks **edit**, take
their rewrite as free text — that one needs prose.

**Quality bar.** Before proposing, check the rule is:

1. **Actionable** — names a behavior, not a sentiment. "Write clean code" fails.
2. **Falsifiable** — you could point at a diff and say whether it was violated.
3. **Non-inferable** — an agent reading the code wouldn't already do this. If it
   would, the rule is noise and dilutes the rules that matter.
4. **Tiered** — you can name where it's enforced.
5. **Portable** — it would fire in a different project with a different stack.
   A rule that only bites given this codebase's particular design is a finding,
   not a rule. Ask: *would I want this in the next project?* If no, propose it
   as a **record**, not a rule.

**The `record` disposition.** Elicitation surfaces real problems that are not
policy — a specific broken behavior, a stale artifact, a design decision worth
revisiting. These are worth capturing and worth *not* putting in the ruleset,
because a portable ruleset diluted with situational entries stops being
portable. Write them to `rules/_progress.md` under project findings, and say
plainly that you are recording rather than proposing.

If a candidate fails any of these, don't propose it. Say what you dropped and
why when you finish the domain — the user may disagree and want it back.

**Enforcement tiers.** Every rule declares one. This is the difference between a
rule and a wish:

| Tier | Meaning |
|---|---|
| `advisory` | Stated in a rule file. Followed most of the time. Fine for preferences. |
| `rule-file` | Stated and cited by the router so it's loaded when relevant. |
| `hook` | A script enforces it deterministically. Cannot be skipped. |
| `CI` | Enforced outside the agent entirely. The only tier that always holds. |

Every rule accepted at `hook` or `CI` tier goes straight into the open
follow-ups in `_progress.md`. Phase 8 builds them. A `hook`-tier rule with no
hook behind it is mislabeled, and mislabeling is worse than being advisory
honestly.

### Phase 7 — Write the ruleset

Only after a domain's rules are all resolved:

1. Show the exact file content you intend to write.
2. Get one final confirmation.
3. Write it, using the templates in `references/templates.md`.

`CLAUDE.md` is a **router**, not a container. It holds only what applies to every
session — identity, commands, and a table pointing at domain rule files with the
trigger for reading each. Domain knowledge lives in `rules/<domain>.md` and loads
on demand.

Do not use `@path` import syntax for domain rules. Imports load eagerly at
session start, which reintroduces exactly the context bloat the split avoids.
Reference the path in prose so it is read only when its trigger fires.

Keep `CLAUDE.md` under 200 lines. If it grows past that, something belongs in a
rule file.

### Phase 8 — Wire the harness

Follow `references/harness.md`. The ruleset states what must be true; the
harness makes part of it hold without the agent choosing to comply.

Work through: enforcement debt from the `hook` and `CI` tiers, permissions in
`.claude/settings.json`, the verification command, subagents, CLI tools and MCP
servers, and plugins. Each piece is proposed and approved individually, exactly
as rules are.

Skip what does not apply and say you are skipping it. A harness section filled
in for completeness is one the user will disable the first time it fires.

### Phase 9 — Record decisions

Write `rules/_decisions.md`: every rejected and deferred rule with the user's
reason, plus rules deliberately not proposed and domains skipped entirely. A
future run reads this first and does not re-propose settled questions.

### Phase 10 — Review and hand off

**Delegate to the `ruleset-reviewer` subagent.** It reads the written ruleset in
fresh context, without the interview, and reports gaps. Its first check is the
one that matters: anything asserting a fact about the project that does not
trace back to something the user stated.

A reviewer asked to find problems will find some. Treat findings about
correctness, portability, and invented content as real; treat the rest as
optional and say so. Chasing every finding produces an over-built ruleset, which
fails the same way an over-specified `CLAUDE.md` does.

Then close the run:

- Confirm the ruleset check passes: `node .claude/hooks/check-ruleset.mjs`
- Summarise what exists now, and what is still open in `_progress.md`
- **Tell the user to `/clear` before implementing anything.** This session holds
  the entire interview; implementation wants a clean context and the written
  spec. The files are the handoff — that is what they were for.

## Resuming a paused run

Long runs get paused. Before anything else, look for `rules/_progress.md` — if
it exists, it is the authoritative resume point and it names the exact rule
awaiting a verdict. Read it, then `_decisions.md`, then the existing rule
files. Do not re-survey the repository from scratch and do not re-propose
anything already settled.

Keep `_progress.md` current as each domain closes.

## Re-running on an existing ruleset

If `CLAUDE.md` or `rules/` already exist, read them and `_decisions.md` first.
Then work only on gaps and on rules the user flags as stale. Never silently
rewrite an existing approved rule — propose the change as its own rule with the
old text shown alongside.

## References

- `references/ingestion.md` — reading `input/` without inferring anything (Phase 1)
- `references/requirements.md` — the clarity bar and how to ask about what is unclear (Phase 4)
- `references/rule-catalog.md` — candidate domains and the questions that surface real rules (Phase 5)
- `references/templates.md` — exact file shapes for CLAUDE.md, rule files, and the logs (Phases 3, 5, 7)
- `references/harness.md` — permissions, hooks, subagents, MCP (Phase 8)
