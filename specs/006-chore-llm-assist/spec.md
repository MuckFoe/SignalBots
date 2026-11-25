# 006 — Chore bot: free-text understanding (LLM command assist)

**Status:** draft · written 2026-11-24 from the code
(`HouseChoreTracker/llm_assist.py`, `commands.py` `_llm_*`, `app.py` cold-start
queue). Design notes: `docs/llm-command-assist-plan.md`. Live since 2026-11-11,
cold-start handling since 2026-11-12 (CHANGELOG).

## Summary

A message that no parser understands goes to a local model on the Mac mini
(Ollama, `qwen3.6:35b`, spec 009). The model only translates the message into
an intent and slots. The bot checks every slot with its own parsers, and it
asks before changing anything. Group chatter gets no reply.

## Functional requirements

- **FR1** — The assist runs only after every command parser and pending
  dialogue has declined the message. Known commands never reach the model.
- **FR2** — It is on only when `LLM_ENABLED` is true and `LLM_BASE_URL` and
  `LLM_MODEL` are set. If `LLM_SCOPES` is non-empty, only those scopes use it.
- **FR3** — The request goes to an OpenAI-compatible `/chat/completions` with
  temperature 0, thinking off, and a strict JSON schema: `kind`
  (action / unclear / chatter), `intent`, optional `slots`, `suggestions` and
  `confidence`. The context sent is the chat language, the chat type and the
  names of existing chores.
- **FR4** — Intents: add_chore, add_once, mark_done, undo_done, edit_chore,
  delete_chore, rename_chore, set_name, vacation, show (list, list extended,
  history, my stats, group stats, help, vacation status).
- **FR5** — Every slot is parsed by the bot's own parsers (schedule, time, chore
  name against the existing list). An unknown chore leads to "which chore do
  you mean?" with examples. Missing details continue the normal guided setup
  (spec 003, FR2/FR5) instead of guessing.
- **FR6** — Actions that change data are summarised ("Did I get that right?")
  and run only after `yes` from the same sender as their next message. Any other
  next message drops the plan. `show` runs at once, headed "Understood as:
  <command>". A tip names the exact command for next time.
- **FR7** — Chatter in a group gets no reply. In a group, an answer with
  confidence below `LLM_GROUP_MIN_CONFIDENCE` (default 0.6) is treated as not
  understood. In a direct chat, chatter or `unclear` gets "did you mean" with up
  to 3 suggestions.
- **FR8** — Fail open: a timeout (`LLM_TIMEOUT_SECONDS`, code default 20 s), a
  bad answer or an unreachable server makes the bot behave as if the assist
  were off.
- **FR9** — Cold start. Before each call the bot asks Ollama (`/api/ps`)
  whether the model is loaded; a failed check counts as loaded. If it is not
  loaded, or messages are already waiting for it, the message is queued. A
  worker then runs it with `LLM_COLD_TIMEOUT_SECONDS` (default 120 s) and sends
  the reply itself, as text only. No notice is sent to a
  group, so chatter there still gets no reply at all. A direct chat, where
  waiting with no answer is confusing, gets one "AI is starting up" notice
  per cold start. (Built 2026-11-24. Before that every chat got the notice at
  once.)
- **FR10** — Every model call is logged to `llm_log` (scope, sender, text,
  context, raw output, outcome, latency) for the offline intent eval
  (`evals/`).

## Acceptance criteria

- **FR1** — `list` gives the normal list, and `llm_log` gets no row.
- **FR2** — With `LLM_SCOPES=group:abc`, free text in another group gets the
  non-LLM behaviour.
- **FR3** — A recorded request carries `response_format.type = json_schema`,
  `strict: true` and `temperature: 0`.
- **FR4** — "bad ist sauber" in a group with a chore "Bad" leads to a confirm
  question to mark "Bad" done.
- **FR5** — "neue aufgabe staubsaugen alle 2 wochen" asks for confirmation of
  "New chore: Staubsaugen · every 2 weeks".
- **FR6** — Answering the confirm question with "nein" returns "discarded", and
  nothing changes.
- **FR7** — "haha nice" in a group gets no reply at all.
- **FR8** — With the Mac mini off, "bad ist sauber" gets the same reply as with
  the assist off.
- **FR9** — After the model has unloaded, "haha nice" in a group gets nothing,
  and "bad ist sauber" in a group gets only the confirm question, about half a
  minute later. In a direct chat the first free-text message gets the notice
  and then the answer, and a second message during the load gets no second
  notice.
- **FR10** — Each assisted message adds one `llm_log` row with its outcome.

## Open questions

None. Decided 2026-11-24: the notice waits until the model has classified the
message (FR9), so chatter no longer gets an orphan notice. In groups that means
no notice at all. A real command sent during a cold start arrives about half a
minute late, without warning.

`.env.example` still says `LLM_TIMEOUT_SECONDS=8`, while the code default and
the deployed value are 20 s since 2026-11-11. The template needs updating;
this is a known fix, not an open question.

## Sources

Tests: `test_llm_assist.py`, `test_llm_cold_start.py`. Eval:
`evals/intent_cases.jsonl`, `evals/run_intent_eval.py` (intent 100 %, slots
96–98 %, 0 % chatter answered, p50 0.6 s on 2026-11-11).
