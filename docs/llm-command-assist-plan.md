# Plan: LLM command assist for chore-bot (POC)

Branch: `feature/llm-command-assist` · Drafted 2026-11-07 · Status: **built 2026-11-10** (steps 2–6 + eval tooling), waiting for the Mac mini — see "Bring-up runbook" at the end

## Goal

A local LLM on the new 32 GB Mac mini (same LAN as the bot server) helps users
who don't know the exact syntax:

1. **Map free text to the right command** — "bathroom is clean now" →
   `done Bathroom`.
2. **Shortcut the dialogues** — if a message already contains some or all of
   the details a multi-step interview would ask for, fill them in and **only
   ask for what's still missing**. "Remind us every Monday at 8 to clean the
   bathroom, and someone has to confirm it" creates the chore after one
   yes/no instead of five questions.
3. **Otherwise** reply with a standard "here's what you can do" message with
   suggestions — but stay silent for normal group chatter.

Scope: **chore-bot only** (`HouseChoreTracker/`). Router, expense and rental
bots stay untouched.

### Decisions (2026-11-07)

| Question | Decision |
|---|---|
| Ask before data-changing actions? | **Yes** — yes/no check from day one |
| Which group messages go to the LLM? | **Every** message the normal parsers don't understand |
| Network | Mac mini on the **same LAN** as the bot server |
| Log raw messages for tuning? | **Yes**, during the POC |
| Optional slots (reminder time, done-confirmation) missing? | **Ask** — follow the full interview, no quick-add defaults |
| Log retention / notice | Keep as long as needed for testing; no announcement in the groups |
| MCP server? | **No** — see "Why not MCP" below |

---

## How it works today (relevant parts)

- Every message ends up in `handle_command()` (`commands.py:2901`), which runs
  deterministic parsers top to bottom.
- Open dialogues are checked first (`commands.py:3240-3250`):
  `pending_member_names`, `pending_chore_setups`, `pending_chore_edits`,
  vacation setup. Each dialogue stores its progress as a `step` in its own
  table.
- If nothing matched, the tail (`commands.py:3658-3661`) does a fuzzy
  `_guess_command` ("Did you mean: …?") or returns `""` (= silence).
- **Chore creation interview** (`_handle_pending_chore_setup`,
  `commands.py:2262`), stored in `pending_chore_setups`
  (`step, name, reminder_schedule, reminder_at_minutes, one_shot, count_in_stats`):

  ```
  name → schedule → remind_time (only if the schedule needs one)
       → count_stats (one-time tasks only) → confirmation → create
  ```

  The last step asks whether completing the chore must be confirmed by
  someone — a **chore setting**, not to be confused with the LLM's own yes/no
  check below. In this doc: *done-confirmation* = chore setting,
  *yes/no check* = "Did I understand you correctly?".
- Quick add `add bins every Wednesday` already skips the interview and uses
  defaults (no reminder time, done-confirmation on).

---

## Core idea: intents with slots, validated by the existing parsers

The LLM doesn't just return a command string. It returns an **intent** plus
the **slots** (details) it found in the message. Every slot is then validated
by the parser the bot already uses for that interview step. Slots that fail
validation are treated as missing. The LLM never writes to the database
itself.

```json
{
  "kind": "action | unclear | chatter",
  "intent": "add_chore",
  "slots": {
    "name": "Bad putzen",
    "schedule": "every Monday",
    "remind_time": "08:00",
    "done_confirmation": true
  },
  "suggestions": ["add <name> <schedule>", "list"]
}
```

### Intent catalogue (POC)

| Intent | Slots (validated by) | Missing slots continue in |
|---|---|---|
| `add_chore` | `name`, `schedule` (`parse_schedule`), `remind_time` (`parse_reminder_time_answer`), `done_confirmation` (bool) | `pending_chore_setups` interview |
| `add_once` | `name`, `when` (`parse_schedule` + `_as_once_schedule`), `remind_time`, `count_stats` (bool), `done_confirmation` | `pending_chore_setups` with `one_shot=1` |
| `mark_done` | `chore` (must match an existing chore) | — ask "which chore?" via suggestions |
| `undo_done` | `chore` | same |
| `edit_chore` | `chore`, `field` (`_edit_field_from_text`), `value` | `pending_chore_edits` |
| `delete_chore` | `chore` | `pending_chore_edits` delete step (see safety) |
| `rename_chore` | `chore`, `new_name` | — |
| `set_name` | `display_name` | `pending_member_names` |
| `vacation` | `when` (`_parse_vacation_when`), `duration` (`parse_duration`) | `pending_vacation_setups` |
| `show` | `what`: list / list extend / history / my stats / group stats / help topic | — (read-only) |

Admin, reset, language and timezone commands are **not** in the catalogue.

The prompt lists each intent with its slots and the **accepted formats** the
validators understand (e.g. schedule phrases like `every Monday`,
`jeden 2. Tag`, `once tomorrow`), so the LLM normalises "jeden zweiten Montag
morgens um 8" into `schedule: "every 2 weeks"`, `remind_time: "08:00"`
(the schedule parser has no "every 2nd Monday" — a weekday schedule is always weekly). It also gets the scope's **current chore names**, so
"the bathroom is clean" maps to the exact chore `Bad putzen`.

### What happens after validation

```
LLM result
  │
  ├─ chatter ─────────────▶ group: ""  ·  DM: suggestions reply
  ├─ unclear / invalid ───▶ suggestions reply
  ├─ show (read-only) ────▶ execute now, prefix "💡 understood as: list"
  │
  └─ data-changing intent
       │
       ├─ all required slots valid
       │     ▶ summary + yes/no check
       │       "Neue Aufgabe: Bad putzen · jeden Montag · Erinnerung 08:00 ·
       │        Erledigung muss bestätigt werden. Passt das? (ja/nein)"
       │       ja   → execute (same functions the normal commands use)
       │       nein → "Okay, verworfen." + hint to the manual command
       │
       └─ some slots missing
             ▶ show what was understood, then jump straight into the
               existing interview at the first missing step
               "Verstanden: Bad putzen, jeden Montag.
                Um welche Uhrzeit soll ich erinnern? …"
             (the interview answers are explicit → no extra yes/no at the end)
```

**Prefilling the existing interview** is the key trick: we write the found
slots into `pending_chore_setups` / `pending_chore_edits` /
`pending_vacation_setups` and set `step` to the first missing one. From there
the existing, tested dialogue code takes over unchanged — including cancel,
stale-dialogue handling and the final create. Step order rules stay the
existing ones (e.g. `remind_time` is skipped when
`reminder_time_applies(schedule)` is false, `count_stats` only for one-time
tasks).

### LLM inside an open dialogue

Shortcutting also helps *during* an interview. When a dialogue step's parser
can't understand an answer (today: a `usage_*` error reply), the answer is
sent to the LLM with the current intent and the slots still missing. It can:

- normalise the answer ("nächsten Montag früh" → schedule + `remind_time`),
- fill **several** remaining slots at once and skip ahead,
- or report `unclear` → the current step's normal error/usage reply.

`cancel`/`abbrechen` and anything the step parser already understands never
go to the LLM.

### Safety

| Tier | Intents | Behaviour |
|---|---|---|
| Read-only | `show` | Execute immediately with "understood as" hint |
| Data-changing | `add_chore`, `add_once`, `mark_done`, `undo_done`, `edit_chore`, `rename_chore`, `set_name`, `vacation` | Yes/no check if complete, otherwise prefilled interview |
| Destructive | `delete_chore` | Starts the edit dialogue at its delete step (`pending_chore_edits`, field `delete`), which already asks its own yes/no (`commands.py:2250`). Never maps to the direct `delete <chore>` command |
| Not reachable | admin, reset group, language, timezone | Not in the catalogue; at most shown as a suggestion |

Plus:

- Execution always goes through the same functions as the manual commands
  (`_finalize_chore_creation`, `storage.mark_done…`, etc.), so admin checks,
  "already exists", "not found" etc. behave identically.
- The yes/no check is **per sender**: in a group only the person who wrote the
  message can confirm it.
- Any message that is not a clear yes/no clears the pending check and is
  processed normally, so a forgotten check never blocks the chat. TTL 5 min.
- LLM down / timeout (8 s) / malformed output → exactly today's behaviour.

### Standard suggestions reply

For `unclear`, invalid results, and chatter in DMs:

> 🤔 Das habe ich nicht ganz verstanden. Meintest du vielleicht:
> - `liste` – alle Aufgaben anzeigen
> - `erledigt <Aufgabe>` – Aufgabe abhaken
> - `hilfe` – alle Befehle

Suggestions = the LLM's candidates if valid, else `_guess_command` plus the
fixed `hilfe`/`liste`.

### Group chatter

Every unmatched group message goes to the LLM (decision 2). The prompt is
explicit that conversation between people is `chatter`, and in groups the bot
only replies for `action`/`unclear` when the message is plausibly addressed to
it. The eval (below) measures false replies to chatter specifically — a bot
answering "lol" is worse than a missed command. If that rate isn't near zero,
the fallback is to require `confidence ≥ x` for group replies.

---

## Changes

### 1. New module `HouseChoreTracker/llm_assist.py`

No new dependency (`requests` is already in `requirements.txt`).

- `LlmClient` — POST to an OpenAI-compatible `/v1/chat/completions`
  (Ollama / LM Studio / llama.cpp / MLX all speak it) with a JSON-schema
  constraint so output is always parseable. Timeout → `None`.
- `INTENTS` — the catalogue above: per intent the slot names, a short
  description, accepted formats, and few-shot examples in en + de.
- `build_messages(text, language, chore_names, is_group, dialogue=None)` —
  system prompt + catalogue + chore names; `dialogue` = current intent and
  missing slots when called from inside an interview.
- `interpret(...) -> Interpretation | None` — `kind`, `intent`, raw `slots`,
  `suggestions`, `confidence`.
- `validate_slots(intent, slots, storage, scope_id) -> (valid, missing)` —
  runs each slot through the existing parser; resolves chore names against
  `storage.list_chores`.

### 2. `commands.py` (surgical)

- `handle_command(..., _allow_llm: bool = True)` — internal flag; execution of
  an LLM result never calls the LLM again.
- New pending check for the yes/no right after the existing pending handlers
  (`commands.py:~3250`).
- Replace the tail `commands.py:3658-3661` with `_llm_fallback(...)`; when
  disabled/failing it returns exactly what the current code returns.
- In the dialogue handlers, where a step currently returns a `usage_*` error,
  try `_llm_fill_dialogue(...)` first (only if enabled).
- Small executor per intent: either "prefill pending table + return that
  step's prompt" or "store pending yes/no + return summary". Reuses
  `_chore_setup_prompt`, `_finalize_chore_creation`,
  `_start_vacation_from_plan`, etc.
- New `TEXT` keys in **both** `en` and `de` (`test_en_de_text_keys_match`
  enforces parity): `llm_understood_as`, `llm_understood_partial`,
  `llm_confirm_summary`, `llm_discarded`, `llm_suggestions_header`.

### 3. `storage.py`

- `pending_llm_actions (scope_id, requested_by, intent, slots_json, expires_at)`
  with start / get / clear, same pattern as `pending_member_names`.
- `llm_log (created_at, scope_id, sender, text, raw_output, outcome, latency_ms)`
  — decision 4. Plus a tiny export script to pull misses into eval cases.
- `pending_chore_setups` needs no schema change — all slots already have
  columns. The only addition is a helper to create a setup row directly at a
  given step with prefilled values.

### 4. Configuration

`.env.example` + chore-bot in `docker-compose.yml`:

| Var | Default | Purpose |
|---|---|---|
| `LLM_ENABLED` | `false` | master switch |
| `LLM_BASE_URL` | `http://<macmini-lan-ip>:11434/v1` | use the IP, mDNS from Docker is unreliable |
| `LLM_MODEL` | — | model tag |
| `LLM_TIMEOUT_SECONDS` | `8` | then fail open |
| `LLM_SCOPES` | *(empty = all)* | allowlist of scope ids; POC = our test group |

### 5. Tests

**Unit tests, fake LLM** (`test_llm_assist.py`, no Mac mini needed):

- exact commands and valid dialogue answers never call the LLM
- `add_chore` with all slots → summary + yes/no; "ja" creates the chore with
  exactly those values; "nein" creates nothing
- `add_chore` with only name + schedule → pending setup at `remind_time`;
  answering the remaining steps creates the chore
- schedule without time-of-day → `remind_time` step is skipped (existing rule)
- invalid slot (e.g. unparseable schedule) → treated as missing, interview
  asks for it
- mid-interview free-text answer fills two slots and skips a step
- `add_once` → `one_shot=1` and `count_stats` asked only if missing
- `mark_done` with unknown chore → suggestions, nothing changed
- `delete_chore` never deletes without the existing confirmation
- yes/no check: only the original sender can confirm; other message clears it;
  expires after TTL
- non-admin can't do admin things through the LLM
- chatter in group → `""`; in DM → suggestions
- timeout / exception / malformed JSON → identical to today
- existing suites stay green with `LLM_ENABLED=false`

**Eval set, real model** (`evals/intent_cases.jsonl` + `evals/run_intent_eval.py`):
~100 cases (en + de): message, chore names, open dialogue (optional),
expected intent + slots or `chatter`. Reports intent accuracy, **slot**
accuracy, chatter false-positive rate, p50/p95 latency. Used to pick the
model and tune the prompt. POC targets: ≥ 90 % intent, ≥ 85 % fully-correct
slots, ≈ 0 % chatter answered.

---

## Mac mini setup (32 GB)

- **Ollama** (OpenAI-compatible API, JSON-schema output, runs as a service).
- 7–14B instruct model, 4-bit quantised, with good German. Slot extraction is
  harder than plain classification, so lean to the larger end; compare 2–3
  candidates with the eval set. Target < 2–3 s per call.
- `OLLAMA_KEEP_ALIVE=-1` (keep the model loaded), `OLLAMA_HOST=0.0.0.0`.
- Fixed LAN IP (DHCP reservation); macOS firewall: port 11434 only from the
  bot server's IP. Ollama has no auth, so it must not be reachable from
  outside the LAN.
- Sanity check from the bot server: `curl http://<ip>:11434/v1/models`.

---

## Rollout steps

1. **Mac mini**: Ollama + candidate models, reachable from the bot server.
2. **Skeleton** (no Mac mini needed): `llm_assist.py`, config, fake-client
   tests, `_llm_fallback` with `show` + suggestions + chatter.
   → verify: with `LLM_ENABLED=false` all existing tests pass unchanged.
3. **Yes/no check** + `pending_llm_actions` + `mark_done` / `undo_done`.
4. **Dialogue shortcut for `add_chore` / `add_once`** (prefill
   `pending_chore_setups`) — the main feature.
5. **Remaining intents**: `edit_chore`, `rename_chore`, `set_name`,
   `vacation`, `delete_chore` hand-over.
6. **LLM inside open dialogues** (fill several steps from one answer).
7. **Eval** on the Mac mini, choose model, tune prompt to targets.
8. **Live POC**: `LLM_ENABLED=true`, `LLM_SCOPES=<test group>`, read `llm_log`
   for a week, turn misses into eval cases.
9. Decide on wider rollout / reuse for expense and rental bots.

---

## Why not MCP

MCP is a protocol for giving an LLM-driven *agent* a set of tools it may call
on its own, usually in a loop (model decides → calls tool → reads result →
decides again). That's the opposite of what we want here:

- **We want a narrow translator, not an agent.** One message in, one
  structured JSON out, and *our* code decides what happens. With MCP the model
  would decide which tools to call and when — exactly the "chatbot in the
  group" behaviour we're avoiding.
- **Safety is easier without it.** Today's design: the LLM can only fill a
  fixed JSON schema, and every value goes through the existing parsers. With
  tool calling, guarding against wrong or repeated calls needs extra rules.
- **Small local models are better at constrained JSON than tool calling.**
  JSON-schema-constrained output (Ollama `format`) guarantees valid output;
  tool calling with 7–14B models is noticeably less reliable.
- **Less to run.** No extra server process, no tool-calling loop, one HTTP call
  per message, easy to fail open.

MCP would make sense later only if we want a general assistant — e.g. using
Claude Desktop or an agent to manage the bots, or open-ended questions
("who skipped the most chores last month and why?"). For that, an MCP server
on top of the bots' `/internal/*` endpoints would be the right shape. That's
out of scope for this POC.

## Open questions

None at the moment.

---

## What was built (2026-11-10)

| Piece | Where |
|---|---|
| LLM client, prompt, JSON schema, output parsing | `HouseChoreTracker/llm_assist.py` |
| Intent executor, yes/no check, prefilled interviews, dialogue fill | `commands.py`, section "LLM command assist" (`_llm_fallback`, `_llm_handle_intent`, `_llm_advance_chore_setup`, `_llm_fill_chore_setup`, `_execute_llm_plan`) |
| `pending_llm_actions`, `llm_log` | `storage.py` (both follow a group move via `scope_migration`) |
| Fake-LLM tests (38) | `HouseChoreTracker/test_llm_assist.py` |
| Eval set (74 cases, en + de, incl. 16 chatter + 6 in-dialogue) | `HouseChoreTracker/evals/intent_cases.jsonl` |
| Eval runner (compares models, slot accuracy via the bot's parsers) | `HouseChoreTracker/evals/run_intent_eval.py` |
| Log export / scope ids / eval-case skeletons | `HouseChoreTracker/evals/export_llm_log.py` (deployed) |
| Config | `.env.example` (`LLM_*`), chore-bot reads them via `env_file: .env` |

Differences from the plan, decided while building:

- `add_once` uses the `schedule` slot (not `when`); `when` is only for vacation.
- Data-changing intents with a complete set of slots are executed **through the
  normal command text** (`erledigt Bad putzen`, `umbenennen A -> B`, …) after the
  yes/no, and the reply ends with "Tipp: nächstes Mal einfach: …" so people learn
  the command. `add_*`, `edit_chore` and `vacation` use the same functions the
  dialogues use.
- Mid-dialogue LLM help is wired for the **chore-creation interview** (schedule,
  remind time, count-stats, done-confirmation steps). The name step never goes
  to the LLM (any text is a valid name). The edit and vacation dialogues are
  only *prefilled* by the LLM, not helped mid-way.
- If `done_confirmation` is known but an earlier step is missing, the interview
  still asks it at the end (`pending_chore_setups` has no column for it).
- Group gating: `LLM_GROUP_MIN_CONFIDENCE` (default 0.6). Below it, and for
  every `chatter`, a group gets exactly today's reply. `unclear` above it gets
  the suggestions reply.
- If the backend rejects the strict JSON schema (HTTP 400), the client retries
  once in plain `json_object` mode.

## Bring-up runbook

1. **Mac mini** (macOS, native Ollama — not a Proxmox node):
   ```bash
   brew install ollama            # or the app from ollama.com
   launchctl setenv OLLAMA_HOST 0.0.0.0
   launchctl setenv OLLAMA_KEEP_ALIVE -1
   # restart Ollama, then:
   ollama pull qwen2.5:14b        # candidates: qwen2.5:7b, qwen2.5:14b, gemma3:12b, mistral-small
   ```
   Avoid "thinking" models (or turn thinking off): they are slow and the
   reasoning text can break the 8 s budget.
   DHCP reservation for a fixed IP; firewall: 11434 only from the bot VM.
2. **From the bot VM**: `curl http://<macmini-ip>:11434/v1/models`
3. **Eval** (from the laptop or the Mac mini, needs `requests`):
   ```bash
   cd HouseChoreTracker
   python evals/run_intent_eval.py --base-url http://<macmini-ip>:11434/v1 \
       --model qwen2.5:7b --model qwen2.5:14b --model gemma3:12b
   ```
   Pick the model that hits ≥ 90 % intent / ≥ 85 % slots / ≈ 0 % chatter
   answered at p95 < 3 s. `--only <text>` reruns single cases; `--verbose` shows every answer.
4. **Deploy** with `LLM_ENABLED=false` first, then find the test group's scope id:
   `docker exec chore-bot python evals/export_llm_log.py --scopes`
5. **Turn on** in the VM's `.env`:
   ```
   LLM_ENABLED=true
   LLM_BASE_URL=http://<macmini-ip>:11434/v1
   LLM_MODEL=<chosen model>
   LLM_SCOPES=group:<test group id>
   ```
   then `docker compose up -d chore-bot`.
6. **Try in the test group**: "bad ist sauber", "neue aufgabe fenster jeden
   montag", "was steht an?", "wer kommt heute zum essen?" (must stay silent),
   and inside `aufgabe` → name → "jeden Montag früh".
7. **Read the log**: `docker exec chore-bot python evals/export_llm_log.py`
   (`--outcome failed|chatter|unclear|low_confidence`, `--jsonl` for eval-case skeletons).
   Kill switch: `LLM_ENABLED=false` + restart — behaviour is then exactly as before.
