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
- [ ] Rotate the SSH password. It sat in plaintext in eight tracked files, so
      treat it as exposed even though nothing was pushed.
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
- **question** `ProjectHub` vs `SignalBots`. The folder is `SignalBots`; the
  README says "from this directory (`ProjectHub`)"; the remote root and the
  Docker volume prefixes still say `projecthub`. Whether the old name stays
  permanently is undecided.

---

## 4. Code and architecture

- [ ] **Base-bot parent project.** Agreed in principle, explicitly gated: only
      after the repo exists, starting from the current working base. Not now.
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

The root README and the code disagree. Which side is wrong has not been
decided — the grocery bot is either current and undocumented, or abandoned and
still wired in.

- [ ] README says "five services"; `docker-compose.yml` defines six.
      `grocery-bot` is missing from the service table.
- [ ] README's Projects section lists four directories; `HouseGroceryTracker/`
      exists, is built by compose, is deployed by `deploy_stack.py`, and is a
      routing target in `group_router.py`.
- [ ] README lists four volumes; compose declares five.
- [ ] README says new groups are asked `chores`, `rentals`, or `expenses`; the
      actual prompt (`group_router.py:245-252`) offers four including grocery.
- [ ] `HouseBotRouter/.env.example` is missing `GROCERY_BOT_URL`, which the
      router's own code requires (`app.py:31,38`).
- [ ] `HouseGroceryTracker` and `HouseBotRouter` have no README at all.
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

## 9. The paused ruleset run

`/project-startup` was started and stopped after the interview, before any rules
were written. What was settled:

| Question | Answer |
|---|---|
| Stage | Running, but a day of downtime is tolerable |
| Users | Just you |
| Version control | Wanted, never set up |
| Credentials | Live, needed fixing — **done** |
| Duplication | Independence is deliberate; base-bot deferred until after the repo exists |
| Testing | Gap to close over time; `unittest` stays |
| Definition of done | Deployed and healthy |
| Deploy mechanism | Undecided |

Not produced: `CLAUDE.md`, `rules/`, `REQUIREMENTS.md`, `docs/concepts.md`.
`input/` still holds only the kit's placeholder README, so any future run has
the same evidence base: the code.

Re-run `/project-startup` to continue. It will re-survey rather than resume —
there is no `rules/_progress.md`, because no rule ever reached a verdict.
