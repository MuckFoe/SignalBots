# input/

Put whatever you already have about this project here, before running
`/project-startup`. Anything readable works — there is no required format and
nothing needs cleaning up first.

Useful things to drop in:

- A spec, brief, or proposal — even a rough one
- Domain notes: what the terms mean, what the rules of the subject area are
- An old README, or documentation from a system this replaces
- Architecture notes, ADRs, diagrams
- A style guide or coding standard
- Meeting notes, requirement lists, ticket exports
- Screenshots or exports from a legacy system being rebuilt

Messy is fine. Contradictory is fine — contradictions get reported back to you
rather than silently resolved. Incomplete is fine, and expected.

## How these get used

Every file is read completely, and every statement extracted from them carries
a citation back to where it came from. Statements are classified: what the
document actually asserts, what it asserts only partially, what is ambiguous,
what is aspirational, and what the code contradicts.

The output is `input/_analysis.md` — what your documents say, and a list of
everything that could not be determined from them.

## What will not happen

**Nothing gets inferred.** If a document says a set is won at 25 points, that
is what gets recorded — not "25 points with a two-point margin", even though
that is how volleyball works. If a document lists three user roles, that does
not establish there are only three. If a term is used but never defined, it is
recorded as undefined rather than given a plausible meaning.

Gaps become questions for you. They do not become answers.

This is deliberate and it is the point. A business rule invented by an agent
looks exactly like one you specified once it is written into a rules file, and
everything downstream will implement it confidently. A missing rule gets
asked about; a wrong one does not.

Expect the questions list to be long. That is the kit working, not failing.
