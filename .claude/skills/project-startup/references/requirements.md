# Building requirements

Runs after the business background is settled with the user, and before any
rules are proposed. Rules govern *how* work is done; requirements say *what*
is to be built. Without them, commit traceability has nothing to point at.

Inputs: `input/_analysis.md`, and the user's answers to its Questions section.
Output: `REQUIREMENTS.md`.

---

## The clarity bar

**A requirement is written only when it is unambiguous.** Not mostly clear.
Not clear enough to start on. Every requirement is checked against all five:

1. **Done is decidable.** There is a stated condition under which this is
   finished, and it can be evaluated without asking anyone.
2. **Every term is defined.** Each domain term appearing in it is defined in
   `docs/concepts.md` or the analysis. A requirement resting on an undefined
   term is undefined.
3. **One reading.** You cannot construct a second defensible interpretation.
4. **The boundary is stated.** What this does *not* cover is written down.
   Scope is defined by its edges, and the edges are where disputes happen.
5. **No undecided dependency.** It does not rest on a question still open.

A requirement failing any of these is not written. It stays a question until
the user closes it.

**Never write a requirement containing an assumption.** An assumption inside a
requirement is invisible the moment it is written — it reads exactly like
something the user specified, and everything downstream implements it as such.

---

## Asking well

When a requirement is not clear, **say precisely what is not clear.** The
failure mode here is not asking too little; it is asking uselessly.

> ❌ "Let me know if anything is unclear."
> ❌ "Is this requirement clear enough?"
> ❌ "Please confirm the details of the export feature."

These produce "yes, fine" and the ambiguity survives into code.

The shape that works: **name the requirement, quote the ambiguous part, state
the readings you can see, ask which.**

> ✅ R4 says exports include *all games*. I can see two readings and cannot
> choose between them:
>   (a) every game in the database
>   (b) every game matching the filter currently applied
> The brief uses "all" both ways in different sections. Which is meant here?

If you cannot even articulate the competing readings, say that plainly:

> ✅ R7 refers to a *qualified rotation*. That term appears three times in the
> notes and is never defined, and I cannot infer it from the code. I am not
> able to propose readings. What is a qualified rotation?

Both of these are good outcomes. Neither is a failure to understand — they are
the mechanism working.

**Ask about one requirement at a time.** A list of twelve questions gets
answered in a batch, briefly, and the brief answers are where ambiguity
re-enters.

---

## Format

```markdown
## R<n> — <short title>
<What must be true when this is done. One or two sentences.>

**Done when:** <the decidable condition>
**Not included:** <the boundary — what this explicitly does not cover>
**Source:** <citation from input/, or "user, <date>">
**Status:** open | in progress | done | dropped
```

Ids are stable and never reused, so commits and reviews can cite them.

**Sizing.** A requirement is a unit of work that can be completed and verified
as a whole. If it cannot be finished in one go it is several requirements; if
it is too small to describe an outcome it is a task, and tasks do not belong
here.

**A requirement states an outcome, not a design.** "Users can export a match
report as PDF" is a requirement. "Add a `POST /api/report` endpoint using
jsPDF" is a design decision — it belongs in the discussion the greenfield
clause of your architecture rules requires, not here.

---

## Process

1. Draft the requirement set from the analysis and the user's answers. Present
   the **list of titles only** first, so the user can see the shape and spot
   what is missing before any of it is written out in full.
2. Take them **one at a time**. For each: run the five clarity checks, then
   either present the full requirement for a verdict, or ask the specific
   question blocking it.
3. Record accepted requirements in `REQUIREMENTS.md` as you go.
4. Anything unresolved stays in the Questions section of the analysis. Do not
   let an open question quietly become a written requirement.
5. When the set is closed, state what you believe is **out of scope** and
   confirm it. Unstated scope boundaries are where projects grow.

---

## For an existing codebase

Behavior already built is not automatically a requirement — it may be
accidental, or something the user has been meaning to remove. Do not
reverse-engineer requirements from code and present them as intent.

Where existing behavior appears to encode a business rule, report it as an
observation with its location and ask whether it is intended:

> The store deletes every action and rebuilds from the client payload on sync.
> That makes the client authoritative over the whole collection. Is that
> intended behavior, or an artifact?

The answer determines whether it becomes a requirement, a finding, or a bug.
Inferring which one it is would be inventing intent, which is the same failure
as inventing a business rule.
