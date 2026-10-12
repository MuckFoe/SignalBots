# Tasks to be done

Everything deferred while making the repo safe to push. Nothing here is
urgent enough to block a first commit.

Items marked **question** are things nobody has decided yet — they are not
work items until they are answered. Where the answer is unknown it is written
as unknown rather than guessed.

---

## 1. Do this first

- [ ] `git init`, then commit. **Only after** confirming `git status` does not
      list `.env`, `HouseChoreTracker/.env`, or any `*.db` file.
- [x] ~~Rotate the SSH password.~~ Declined — user's call. It sat in plaintext
      in eight tracked files before the repo existed, so it stays treated as
      exposed, but no rotation will happen.
- [ ] Verify a deploy still works end to end: `python deploy_stack.py`, then
      `python deploy_stack.py verify`. The scripts now read credentials from
      `.env` — if that file is missing or a key is blank they exit with a
      message naming the key.

---

## 2. Security — deferred

- [ ] **SSH host-key verification is disabled.** Every remote script calls
      `paramiko.AutoAddPolicy()`, which accepts any host key without checking.
      Replace with `RejectPolicy` plus a known-hosts file. Low practical risk on
      a private-range host you control; real if the host ever moves.
- [ ] **Root password is piped into `su` over the wire** in 34 places, now via
      `SU` in `ssh_config.py`. Passwordless `sudo` for the deploy user, or an
      SSH key with a root-capable account, removes the pattern entirely.
- [ ] **Switch from password auth to an SSH key.** Removes `SSH_PASSWORD` and
      `SSH_ROOT_PASSWORD` from `.env` altogether.
- [ ] **`signal-api` is pinned to `:latest`** (`docker-compose.yml:3`). An
      upstream push changes what runs on the next rebuild with no warning. Pin a
      digest or a version tag.

---

## 3. Repository and deployment

- [ ] **`deploy_stack.py` uploads a hand-maintained file whitelist**
      (`PROJECTS`, lines 10–81). It has already drifted: no subproject
      `.env.example` is uploaded, and HouseChoreTracker's README, CLAUDE.md,
      four test files, `proxmox_setup.sh` and its four SSH scripts are not
      deployed. A new module added to a bot will silently not ship.
      Sync the directory instead of listing files.
- [ ] **No backup before destructive deploy steps.** `deploy_stack.py` backs up
      `chores.db` only (line ~151). The other four databases — router, rental,
      expense, grocery — are not backed up before `docker compose down` and
      `docker rm -f`.
- **question** Is SSH file-copy the permanent deploy mechanism, or a stopgap?
  Marked undecided. Until it is decided, do not build tooling that assumes
  either answer.
- [ ] **Four compose files define colliding container names and ports.** Root
      `docker-compose.yml` plus per-project files in HouseChoreTracker,
      HouseExpenseTracker and HouseRentalTracker. Running a sub-compose while
      the root stack is up collides. Which is authoritative is not written down
      anywhere.
- [ ] **Two volumes are `external: true`** — `housechoretracker_signal-cli-config`
      and `housechoretracker_bot-data` (`docker-compose.yml:134-135, 139-140`).
      Deploy fails if they do not already exist. The README does not mention it.
- [x] ~~`ProjectHub` vs `SignalBots`.~~ Resolved 2026-09-06: `ProjectHub` was
  never a name for this project — it's an accidental echo of the local parent
  folder (`Desktop\ProjectHub\SignalBots`), unrelated to SignalBots. Dropped
  the `projecthub_` prefix from `router-data`, `rental-bot-data`,
  `expense-bot-data`; renamed the remote deploy root to
  `/home/signalbot/bots` (the upload runs as the unprivileged `signalbot`
  user, which can only write inside its own home dir — confirmed live, so a
  bare `/home/signalbots` wasn't possible). `housechoretracker_*` volumes were left
  untouched deliberately — that's chore-bot's own naming, not part of this,
  and `housechoretracker_signal-cli-config` isn't worth the re-linking risk
  for a cosmetic rename. Old path/volumes kept as a rollback point — see §3
  new item below.
- [ ] **Remove the old `/home/signalbot/ProjectHub` directory and the three
      old `projecthub_*` volumes** (`projecthub_router-data`,
      `projecthub_rental-bot-data`, `projecthub_expense-bot-data`,
      `projecthub_grocery-bot-data`) once the renamed deployment has run
      stably for a few days. Kept for now as a rollback point.
- [x] **Migration executed and verified 2026-09-06.** Explicit timestamped
      backups taken of `grocery.db`, `rentals.db`, `expenses.db`, `router.db`
      before touching anything. Volumes copied (not moved) to
      `router-data`/`rental-bot-data`/`expense-bot-data`; deploy root moved to
      `/home/signalbot/bots` (not a bare `/home/signalbots` — `/home` is
      root-owned and the SFTP upload runs as the unprivileged `signalbot`
      user). Redeployed and confirmed: 5 healthy containers, no grocery-bot in
      deployed code (`grep -ri grocery` on the live `group_router.py` came back
      empty), chore data intact (16/85/1/1 vs. 16/84/1/1 baseline — the +1 log
      is normal activity, not loss), `router.db`'s `group_jobs` table readable
      from the new volume. Old path and volumes left in place as rollback.

---

## 4. Code and architecture

- [x] **`grocery-bot` decommissioned 2026-09-06.** It was live (up 2 weeks,
      healthy, serving real `/internal/scope`/`/internal/handle` traffic) but
      undocumented — user's call was to decommission rather than document.
      Removed from `docker-compose.yml`, `deploy_stack.py`, and
      `group_router.py`'s job set/aliases/prompts. `HouseGroceryTracker/`
      source directory is untouched in the repo (unbuilt, undeployed) —
      deleting the code itself was treated as a separate, bigger call.
- [ ] **`projecthub_grocery-bot-data` volume left dormant on the host,
      snapshotted first.** Safe to `docker volume rm` once nobody wants the
      old grocery-list data back.
- **question, reopened 2026-09-06** **Base-bot parent project.** Previously
  settled as "independence is deliberate, base-bot deferred until after the
  repo exists" — the repo now exists, and the user reopened the question:
  since all bots share functionality, does a shared base make sense? Not yet
  decided. One distinction worth keeping in mind when it's picked back up:
  `signal_client.py`/`dialogue_utils.py` are byte-identical infra glue (Signal
  API calls, send-queue daemon, the three-endpoint contract) with no domain
  logic in them, whereas `commands.py`/`storage.py`/etc. are *divergent forks*
  — different content per bot, because the domain differs. A base package
  covering the former wouldn't force the latter into a shared shape, but it
  would reintroduce a coupling point across otherwise independently
  deployable containers (a base fix means rebuilding every bot, not just the
  one you touched) — that's the tradeoff to weigh against "independent
  gathering of bots" as the stated project shape.
- [ ] **Byte-identical files with no mechanism keeping them in sync.**
      `signal_client.py` is identical across HouseChoreTracker,
      HouseExpenseTracker and HouseRentalTracker; `dialogue_utils.py` likewise.
      Nothing records whether divergence would be a bug. Decide before the
      base-bot work starts — it is the same question.
- [ ] **Divergent forks of shared modules.** `commands.py`, `storage.py`,
      `bot_registry.py`, `stats_charts.py`, `chart_parse.py`, `display_names.py`
      exist in several bots with different contents. Independence is deliberate
      (separate containers), so this is expected — but it is also the surface
      the base-bot work has to reconcile.
- [ ] **`paramiko` is imported by nine files and declared in no
      `requirements.txt`.** Nothing pins it. A root `requirements.txt` for the
      management scripts would fix it.
- [ ] **`HouseChoreTracker/rental/__init__.py` is a 0-byte package** that
      nothing imports, containing only `__pycache__` artefacts for
      `scrape_types` and `storage`. Looks like a leftover from rental code that
      once lived in the chore bot. Probably deletable — confirm first.
- [ ] **`HouseGroceryTracker/image_recognition.py` contains no recognition
      logic.** Its three functions download a Signal attachment and write it to
      disk. Either the name is wrong or a feature is missing; the code cannot
      say which.
- [ ] **Bots run the Flask development server** (`CMD ["python", "app.py"]`,
      `app.run(...)`). Fine for a single-user LAN deployment; noting it so the
      choice is deliberate rather than forgotten.
- **question** `HouseChoreTracker/commands.py` is 3,560 lines and `storage.py`
  is 2,227 — each larger than the entire router or grocery bot. Whether that
  needs splitting has not been decided.

---

## 5. Testing

- [ ] **Four of five bots have no tests.** HouseChoreTracker has 848 lines of
      `unittest`; the router's `parse_job_and_language` and the rental scrapers
      have none. Agreed direction: close the gap over time, `unittest` stays the
      standard, no retroactive coverage push.
- [ ] **Nobody knows whether the existing tests pass.** They were never run
      during this survey. Run them once to establish a baseline.
- [ ] **Tests only run with their own directory as cwd** — they import bare
      module names. Worth writing down once it is settled how they are invoked.
- [ ] **No CI, no linter, no formatter, no build system** anywhere in the tree.
      No `pyproject.toml`, no `.editorconfig`, no `.github/`.
- [ ] **Dependencies are floor-pinned (`>=`) with no upper bound and no
      lockfile** across all five `requirements.txt` files.

---

## 6. Documentation conflicts

- [x] ~~README says "five services"; `docker-compose.yml` defines six.~~
      Resolved 2026-09-06 by decommissioning `grocery-bot` rather than by
      documenting it — see the new item at the top of §4. Compose now defines
      five services, matching the README.
- [x] ~~README's Projects section lists four directories; `HouseGroceryTracker/`
      exists...~~ Same resolution: `HouseGroceryTracker/` is no longer built,
      routed, or deployed. Source directory left in the repo, untouched.
- [x] ~~README lists four volumes; compose declares five.~~ Same resolution:
      `grocery-bot-data` removed from compose.
- [x] ~~README says new groups are asked `chores`, `rentals`, or `expenses`;
      the actual prompt offers four including grocery.~~ Same resolution:
      `group_router.py`'s job set is back down to three, matching the README.
- [x] ~~`HouseBotRouter/.env.example` is missing `GROCERY_BOT_URL`.~~ Moot —
      `GROCERY_BOT_URL` is no longer read by any code.
- [ ] `HouseBotRouter` has no README at all. (No longer true for
      `HouseGroceryTracker` in the sense that mattered — it's not deployed, so
      its missing README is no longer a documentation gap.)
- [ ] `HouseChoreTracker/CLAUDE.md` is generic LLM-behaviour advice with zero
      project content, predates all the code, and sits where nothing loads it.
      Delete or replace.
- [ ] **`HouseChoreTracker/README.md` makes ~40 behavioural claims** — timings,
      defaults, command semantics — that were never verified against the
      3,560-line `commands.py`. Neither confirmed nor contradicted.

---

## 7. Undefined terms

Used in code and docs, defined nowhere. Left undefined deliberately — writing a
plausible meaning here would make a guess indistinguishable from a decision.

- **`scope_id`** — the router's primary key. One observed form is `dm:<number>`.
  Full set of valid forms unknown; group form unknown; whether it survives a
  group rename or a member leaving is unknown.
- **`job`** — what a chat is for. Whether a scope can hold more than one, and
  whether a job can be changed after it is set, are unknown.
- **`admin`** — used throughout (`admin help`, `has_admins`, a `chat_admins`
  table). Who becomes one and how is stated nowhere.
- **`one-shot`** — has a whole test file (`test_one_shot.py`) and a
  `ONE_SHOT_STATS_KEY` constant. Never defined in prose.
- **`vacation`** — `vacation_utils.py` is 90 lines and is in the deploy
  whitelist. No README mentions it.
- **quiet hours** — stated as 00:00–08:00. In whose timezone is unclear: only
  HouseChoreTracker's Dockerfile sets `TZ=Europe/Berlin`. What happens to a
  reminder falling inside the window — dropped or deferred — is not stated.
- **`BOT_REGISTRY`, `PENDING_MAX_HOURS`, `PENDING_STALE_HOURS`** — read by code,
  declared in no `.env.example` and no compose file, documented nowhere.

---

## 8. Open questions

- Do the rental scrapers have terms-of-service or rate-limit constraints worth
  respecting? Targets are `casamundo`, `hometogo`, `fewo-direkt`, `amivac`,
  `bellevue-ferienhaus`, `vacationrenter`. `POLL_TIMES` defaults to twice daily.
- Is bilingual EN/DE required for every new user-facing string, or only in the
  bots that already have it?
- Are there backups of any of the five SQLite databases? None were found.
- Is `127.0.0.1`-only port binding a deliberate requirement or incidental? All
  six services bind to loopback today.
- Does the code in this directory match what is actually running on the host?
  With no git and a drifting upload whitelist, there is no way to tell — no
  version string, build stamp, or image tag exists anywhere.

---

## 9. The ruleset run

`/project-startup` was started and stopped after an interview (2026-09-05),
before any rules were written, then resumed 2026-09-06. What was settled in
the first pass:

| Question | Answer |
|---|---|
| Stage | Running, but a day of downtime is tolerable |
| Users | Just you |
| Version control | Wanted, never set up — **done** (`git init`, this repo) |
| Credentials | Live, needed fixing — **done** |
| Duplication / base-bot | Reopened 2026-09-06, see §4 — not yet decided |
| Testing | Gap to close over time; `unittest` stays |
| Definition of done | Deployed and healthy |
| Deploy mechanism | Undecided |

Settled in the second pass (2026-09-06):

| Question | Answer |
|---|---|
| SSH password rotation | Declined — user's call, staying exposed |
| Project scope/identity | Independent gathering of bots, not one coupled stack; "SignalBots" is authoritative, not "House Bots Stack" |
| Grocery bot | Was live and undocumented, not abandoned — decommissioned |
| `ProjectHub`/`projecthub_` naming | Was an accidental echo of the local parent folder, not a project name — dropped, see §3 |

Not yet produced: `CLAUDE.md`, `rules/`, `REQUIREMENTS.md`, `docs/concepts.md`.
`input/` still holds only the kit's placeholder README, so `docs/concepts.md`
and `REQUIREMENTS.md` still have to be built from the interview, not from a
source document.

The session paused mid-Phase-3 to execute the grocery decommission and rename
above (live-infra changes, not ruleset work). Resume by continuing the Phase 3
interview — no `rules/_progress.md` exists yet because no domain has reached
rule elicitation.
