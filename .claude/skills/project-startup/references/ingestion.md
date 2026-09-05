# Ingesting knowledge files

Input documents live in `input/`. They may be anything the user has: a spec, a
style guide, architecture notes, meeting minutes, a standards document, an old
README, a domain description, screenshots of a legacy system.

Run by the `input-analyst` subagent (Phase 1), which executes this protocol in
its own context and writes `input/_analysis.md`. The main session reads the
analysis, not the raw documents — that is what keeps context free for the
interview the analysis exists to drive.

Your job is to build the project's frame from what these documents **actually
say** — and to be visibly, verifiably silent about everything they do not.

---

## The prime constraint: infer nothing

**Never state as fact anything the documents do not state.** Never fill a gap
with knowledge from outside them. This applies absolutely to business and
domain information, and there is no threshold of obviousness that suspends it.

An inferred fact and a stated fact look identical once written into a rule
file. From that point on the inference is trusted, propagates into code, and is
implemented confidently — and nothing distinguishes it from the parts that were
real. A wrong business rule is worse than an absent one, because an absent one
gets asked about.

### What counts as inference

All of these are forbidden, regardless of confidence:

- **Completing a partial statement from general knowledge.** A document says a
  set is won at 25 points. Do not add "with a two-point margin" — that is real
  volleyball, and it may not be what this system implements.
- **Generalising from an example.** One example showing three roles does not
  establish that there are only three, or that those are the only valid values.
- **Assuming an industry standard applies.** A domain having a common practice
  says nothing about whether this project follows it.
- **Inferring a relationship from proximity.** Two entities described on the
  same page are not thereby related.
- **Filling in an obvious-seeming default.** "Presumably it defaults to X" is
  an inference. So is a silent assumption you never wrote down.
- **Resolving an ambiguity by picking the likelier reading.** Two readings
  means the document is ambiguous. That is a finding, not a choice.
- **Translating a term into what you think it means.** If a document uses a
  domain term without defining it, the term is undefined. Record it as
  undefined. Do not supply a definition.

### What is permitted

- Quoting or faithfully paraphrasing what a document states, with a citation.
- Reporting that two documents conflict.
- Reporting that a document and the code conflict.
- Asking the user a question.
- Marking something unknown.

**"I could not determine this" is always an acceptable output.** It is very
often the correct one, and it is never a failure.

---

## Process

### 1. Read each file completely before extracting anything

Never extract from a skim. Rules in a document frequently qualify each other,
and a rule lifted without its qualifier becomes a different rule. If a file
cannot be read — unsupported format, unreadable scan — say so. Do not infer its
contents from its filename.

### 2. Classify every statement

| Class | What it is | Where it goes |
|---|---|---|
| **Stated** | The document says it, explicitly | Candidate rule or recorded fact, with citation |
| **Partial** | Stated but incomplete — a rule with an unstated edge | A question, *not* a completed rule |
| **Ambiguous** | Two defensible readings | A question naming both readings |
| **Rationale** | Why something is the way it is | Attach to a rule's why |
| **History** | What was tried, what failed | Candidate for the decisions log |
| **Aspiration** | What someone hoped would be true | Ask whether it is actually in force |
| **Stale** | Contradicted by the current code | Report the contradiction; do not propose |

Partial and Ambiguous are the classes that matter most, because they are the
ones inference is tempted to close. They become questions.

### 3. Cite everything

Every extracted item carries its origin:

```
Source: <filename> § <section or page> — "<short quote>"
```

An item without a citation is an inference by definition — it came from
somewhere, and if that somewhere is not a document, it is you. Citation is what
makes the constraint checkable rather than a promise.

### 4. Verify against the repository

For each candidate, check whether the code actually does this:

- **Code agrees** → propose as codifying existing practice.
- **Code disagrees** → report the contradiction plainly. Often the honest
  conclusion is that the document is stale. Say so if you think so.
- **Nothing to check against** → say that too. An unverifiable claim is not a
  verified one.

### 5. Write the analysis before proposing anything

Produce `input/_analysis.md`:

```markdown
# Input analysis

Files read: <list, with anything unreadable named>

## Stated
<Facts and candidate rules the documents actually assert, each with citation.>

## Questions — could not be determined
<Everything Partial, Ambiguous, or absent. Phrased as questions, grouped by
topic. This section existing and being long is a good outcome, not a bad one.>

## Conflicts
<Document vs document, and document vs code. Both sides quoted.>

## Not extracted
<What was dropped and why: stale, aspirational, or already inferable from the
code.>
```

Walk the user through it — **the Questions section first**. Those are the
decisions only they can make, and every one answered by inference instead is a
defect you cannot see later.

### 6. Only then propose rules

Extracted rules go through the same one-at-a-time verdict as any other. A rule
from a document the user wrote themselves is still a proposal: they wrote it in
a different context, possibly for a different project, possibly years ago.

If a document yields more than roughly fifteen candidates, offer to narrow by
domain first. A thirty-rule interview in one sitting produces rubber-stamping,
which is the failure this whole skill exists to prevent.

---

## Conflicts

When an ingested rule contradicts an already-approved one, stop and surface
both. Do not resolve it. Present the approved rule and its origin, the ingested
rule and its citation, what each would mean concretely, and your
recommendation — stated as a recommendation.

The user decides. Record the resolution in the decisions log including the
losing side; the next person to read that document will have the same question.

---

## If `input/` is empty

Say so and proceed with repository survey only. Do not treat an empty input
folder as license to supply the missing context from general knowledge — it
means the project frame rests on the code and on the user's answers, and the
questions you would have asked are now more important, not less.
