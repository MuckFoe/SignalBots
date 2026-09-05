# Input analysis

Generated 2026-09-05 by the `input-analyst` subagent, per
`.claude/skills/project-startup/references/ingestion.md`.

## Files read

### In `input/`

- `input/README.md` (1981 bytes) — read in full.

**Verdict: `input/README.md` is a placeholder / instruction document, not a
project source document.** It is boilerplate shipped with the project-startup
kit, telling the user what to put in the folder. It contains zero assertions
about SignalBots. Its own example ("a set is won at 25 points … that is how
volleyball works") is the same illustrative example used verbatim in
`ingestion.md`, confirming it is kit text rather than domain material.

> Source: input/README.md § top — "Put whatever you already have about this
> project here, before running `/project-startup`."

**Therefore `input/` is effectively empty of source material.** Per
`ingestion.md` § "If `input/` is empty", this analysis proceeds with a
repository survey only, and the questions below matter more, not less.

No file in `input/` was unreadable.

### Outside `input/` (repository survey)

Read completely:

- `README.md` (root)
- `HouseChoreTracker/README.md`
- `HouseChoreTracker/CLAUDE.md`
- `HouseExpenseTracker/README.md`
- `HouseRentalTracker/README.md`
- `.env.example` (root)
- `docker-compose.yml` (root)
- `HouseBotRouter/group_router.py`
- `.claude/settings.json`

Inspected structurally (file listing, line counts, greps for routes, decorators,
constants, imports; **not** read line by line):

- All other `.py` files across `HouseBotRouter/`, `HouseChoreTracker/`,
  `HouseExpenseTracker/`, `HouseGroceryTracker/`, `HouseRentalTracker/`, and the
  five root-level operational scripts (~17,257 lines of Python total).
- All `Dockerfile`s, per-project `docker-compose.yml` files,
  `requirements.txt` files, `HouseChoreTracker/proxmox_setup.sh`.

**Not read, and contents not inferred:**

- `HouseChoreTracker/.env` — read access is denied by `.claude/settings.json`
  (`"deny": ["Read(./.env)", "Read(./.env.*)"]`). I do not know what it
  contains. I note only that a file with that name exists inside a project
  directory.
- `HouseChoreTracker/.env.example`, `HouseBotRouter/.env.example`,
  `HouseExpenseTracker/.env.example`, `HouseRentalTracker/.env.example` — same
  deny rule.
- All `__pycache__/*.pyc` files (compiled binaries).

---

## Stated

### A. From input documents

**Nothing.** No project fact, rule, term definition, requirement, constraint, or
piece of history was extracted from `input/`, because `input/` contains no
project document. There is no spec, no brief, no domain note, no glossary, no
architecture note, no style guide, and no requirement list.

Everything in section B below comes from the repository, not from an input
document. It is recorded as **observation**, not as approved rule, and not as
anything the user has told me.

### B. From the repository

These are things the repository visibly contains. Where the source is a prose
document (a README), the item is a *claim of that document* and is marked as
such — READMEs can be stale, and most of these were **not** verified against the
code in this pass.

#### Topology and deployment

1. The stack is composed of six Docker services: `signal-api`, `bot-router`,
   `chore-bot`, `rental-bot`, `expense-bot`, `grocery-bot`.
   > Source: docker-compose.yml § services — service keys `signal-api`,
   > `bot-router`, `chore-bot`, `rental-bot`, `expense-bot`, `grocery-bot`.
   > (Note: the root README states five — see Conflicts §1.)

2. `signal-api` runs the image `bbernhard/signal-cli-rest-api:latest` in
   `MODE=json-rpc`, with `RECEIVE_WEBHOOK_URL=http://bot-router:5100/webhook`.
   > Source: docker-compose.yml § signal-api — "RECEIVE_WEBHOOK_URL=http://bot-router:5100/webhook"

3. Each bot service exposes `GET /health`, `POST /internal/scope`, and
   `POST /internal/handle`; the router exposes `GET /health` and
   `POST /webhook`.
   > Source: HouseChoreTracker/app.py:110,115,128; HouseExpenseTracker/app.py:57,62,75;
   > HouseGroceryTracker/app.py:59,64,77; HouseRentalTracker/app.py:129,134,147;
   > HouseBotRouter/app.py:183,188

4. Ports as configured: router 5100, chore 5000, rental 5001, expense 5002,
   grocery 5003, signal-api 8080. All host bindings are `127.0.0.1`.
   > Source: docker-compose.yml § ports — e.g. "127.0.0.1:5003:5003"

5. All Python services build from `python:3.12-slim`. `HouseChoreTracker`'s
   Dockerfile sets `ENV TZ=Europe/Berlin`; the router's and grocery's do not.
   > Source: HouseChoreTracker/Dockerfile:1,7; HouseBotRouter/Dockerfile:1;
   > HouseGroceryTracker/Dockerfile:1

6. The router stores group-to-job assignments in a SQLite table `group_jobs`
   (`scope_id` primary key, `job`, `created_at`).
   > Source: HouseBotRouter/group_router.py § _init_db — "CREATE TABLE IF NOT EXISTS group_jobs"

7. The router's job type is a Literal of exactly four values: chores, rentals,
   expenses, grocery.
   > Source: HouseBotRouter/group_router.py, top — Job = Literal["chores", "rentals", "expenses", "grocery"]

8. When no explicit job is stored for a scope, the router probes each bot's
   `/internal/scope` in the fixed order chores, rentals, expenses, grocery and
   selects the first that returns `has_admins`.
   > Source: HouseBotRouter/group_router.py § resolve_job — for job in ("chores", "rentals", "expenses", "grocery")

9. Each service has its own SQLite database file and its own Docker volume:
   `router.db`, `chores.db`, `rentals.db`, `expenses.db`, `grocery.db`.
   `signal-cli-config` and `housechoretracker_bot-data` are declared
   `external: true`; the other four volumes are not.
   > Source: docker-compose.yml § volumes — "name: housechoretracker_bot-data", "external: true"

10. Root README states the databases are deliberately not merged.
    > Source: README.md § "Data (separate, not merged)" — "Existing chore groups keep working: router detects them via chore-bot admins."

11. Root-level scripts deploy to and inspect a remote host over SSH using
    `paramiko`, with the host, username and password written literally into the
    source: HOST "<SSH_HOST>", USER "signalbot", PASSWORD <redacted>,
    REMOTE_ROOT "/home/signalbot/ProjectHub".
    > Source: deploy_stack.py:4-7; the same literals appear in audit_server_data.py:5-7,
    > fix_stack_deploy.py:3-5, and check_chore_bot.py:5

12. `deploy_stack.py` deploys an explicit per-project file whitelist plus
    ROOT_FILES of `docker-compose.yml`, `README.md`, `.env.example`. Tests,
    `CLAUDE.md`, `proxmox_setup.sh`, and the per-project helper scripts are not
    in any whitelist.
    > Source: deploy_stack.py § PROJECTS, ROOT_FILES

13. `HouseChoreTracker/README.md` claims the production target is a Proxmox
    guest running Debian 12, set up via `proxmox_setup.sh`.
    > Source: HouseChoreTracker/README.md § "Full stack on Proxmox guest" — "Create a Debian 12 (bookworm) VM (recommended), or a privileged Debian 12 LXC."
    > Not verified against any code in this pass.

#### Behaviour claimed by project READMEs (unverified)

14. `HouseChoreTracker/README.md` documents a large Signal command surface
    (`help`, `chores`/`list`, `done`, `undo done`, `add`, `edit`, `schedule`,
    `confirmation`, `reminder`, `delete`, `rename`, `history`, `groups`,
    `language`, and an `admin …` family) in English and German aliases.
    > Source: HouseChoreTracker/README.md § Commands — "`done <chore name>` - logs with timestamp"
    > These are documented claims. I did not verify them against the 3,560-line
    > `HouseChoreTracker/commands.py`.

15. The same README states specific defaults: reminder loop "checks due chores
    every 60 seconds"; quiet hours "muted by default from `00:00` to `08:00`";
    repeat defaults "hourly tasks repeat every 5 minutes, daily tasks every 1
    hour, weekly/weekday tasks every 8 hours"; Signal link reminders "off by
    default" and "roughly every 25 days" when enabled; group reset code valid
    "within 10 minutes and by the same sender".
    > Source: HouseChoreTracker/README.md § "How it works" and § Notes
    > Unverified against code. Several of these are Partial (see Questions).

16. `HouseExpenseTracker/README.md` claims Splitwise/Tricount-style features:
    `join`, `name`, `add`, `spent`, `split`, `balances`, `settle`, expense
    list/detail/delete, total spending, currency setting, English and German.
    > Source: HouseExpenseTracker/README.md § Features — "Custom splits (`split 100 dinner | Alice:60 Bob:40`)"

17. `HouseRentalTracker/README.md` is three sentences; it states the bot tracks
    vacation rentals, uses `rentals.db` only, and "Does not touch chore data."
    > Source: HouseRentalTracker/README.md — "Data: `rentals.db` only. Does not touch chore data."

18. The rental scraper recognises the hostnames `casamundo.de`,
    `casamundo.com`, `hometogo.de`, `hometogo.com`, `fewo-direkt.de`,
    `amivac.de`, `bellevue-ferienhaus.de`, `vacationrenter.com`.
    > Source: HouseRentalTracker/scrapers.py:153-163

19. The rental scrape result model tracks `available`, `price_per_night`,
    `total_price`, `currency` (default "EUR"), `title`, `location_name`,
    `lat`, `lon`, `guests_max`, `bedrooms`, `bathrooms`, `rating`,
    `review_count`, `min_nights`, `cleaning_fee`, `pets_allowed`,
    `property_type`, `error`.
    > Source: HouseRentalTracker/scrape_types.py § ScrapeResult

20. `POLL_TIMES=08:00,20:00` is set for the rental bot.
    > Source: docker-compose.yml § rental-bot; also .env.example — "POLL_TIMES=08:00,20:00"

21. The grocery bot downloads Signal attachments from
    `{signal_api_url}/v1/attachments/{attachment_id}` and has a module named
    `image_recognition.py`.
    > Source: HouseGroceryTracker/image_recognition.py § download_attachment

#### Language / i18n

22. The router presents its job picker in both English and German and accepts
    German aliases for every job (`haus`, `ferien`, `tricount`, `einkauf`, and
    others), plus language suffixes/prefixes (`en`, `de`, `english`,
    `deutsch`).
    > Source: HouseBotRouter/group_router.py § JOB_TEXT, _CHORE_ALIASES … _GROCERY_ALIASES, _LANGUAGE_SUFFIXES

23. Chore and expense READMEs both state per-group language selection between
    English and German.
    > Source: HouseChoreTracker/README.md § Notes — "Language is stored per group/chat."; HouseExpenseTracker/README.md § Features — "English and German"

#### Tests and tooling

24. Tests exist only in `HouseChoreTracker/`: `test_command_surface.py`,
    `test_command_surface_extra.py`, `test_one_shot.py`,
    `test_whole_picture.py` (848 lines total). They use `unittest` with
    `unittest.mock.patch` and a `unittest.main()` entry point.
    `HouseBotRouter`, `HouseExpenseTracker`, `HouseGroceryTracker`, and
    `HouseRentalTracker` contain no test files.
    > Source: HouseChoreTracker/test_whole_picture.py:6 — "import unittest"; file listing

25. The repository contains no `pyproject.toml`, `setup.cfg`, `pytest.ini`,
    `.gitignore`, linter/formatter config, or CI configuration anywhere.
    > Source: exhaustive `find` for `*.toml`, `*.cfg`, `*.ini`, `.gitignore`,
    > `*.yml`, `*.yaml`, `*.json` — only `.claude/settings.json`, the four
    > `docker-compose.yml` files, and `proxmox_setup.sh` matched.

26. The working directory is not a git repository.
    > Source: environment report — "Is directory a git repo: No"

27. `HouseChoreTracker/CLAUDE.md` is a generic LLM-behaviour guideline document
    (think before coding, simplicity first, surgical changes, goal-driven
    execution). It contains no SignalBots-specific content and lives only in
    that one subdirectory.
    > Source: HouseChoreTracker/CLAUDE.md § top — "Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed."

28. Substantial modules are duplicated per project rather than shared:
    `signal_client.py` (5 copies), `bot_registry.py` (4), `dialogue_utils.py`
    (4), `storage.py` (4), `commands.py` (4), `stats_charts.py` (3),
    `chart_parse.py` (3), `display_names.py` (2). There is no shared package.
    > Source: repository file listing

---

## Questions — could not be determined

Nothing in this section is answered anywhere in `input/`. Most of it is not
answered anywhere in the repository either. Each question names what is
missing; none of them should be closed by inference.

### 1. Whether there is any project documentation at all

1.1 `input/` contains only the kit's own placeholder README. Do you have any
    spec, brief, domain notes, requirement list, ticket export, meeting notes,
    or design document for SignalBots that has not been placed in `input/`? If
    yes, adding it and re-running this analysis will change almost every
    answer below.

1.2 If no such document exists, is the intent that the rules for this project
    be established entirely from the interview and the existing code?

### 2. Project identity and scope

2.1 What is this project called? The local folder is `SignalBots`, the root
    README titles it "House Bots Stack", and both the README and the deploy
    script call the deployment root `ProjectHub`
    (`README.md` § Deploy — "From this directory (`ProjectHub`)";
    `deploy_stack.py` — REMOTE_ROOT "/home/signalbot/ProjectHub"). Which name
    is authoritative, and are `ProjectHub` and `SignalBots` the same thing?

2.2 Is the scope of this project all five bots plus the router, or is one of
    them the actual subject and the rest context? The rule set that comes out of
    this differs a lot depending on the answer.

2.3 Who uses this system? No document states the intended users, the number of
    households, whether it is private to you or shared with others, or whether
    anyone outside your household ever sends it messages.

2.4 Is this a personal/hobby deployment or does it have external users,
    availability expectations, or anyone else depending on it?

2.5 Is the system live in production right now, or is the state on
    `<SSH_HOST>` stale?

### 3. The grocery bot's status

3.1 `HouseGroceryTracker` exists as a full service (806-line `storage.py`,
    793-line `commands.py`, wired into `docker-compose.yml`, routed by the
    router, listed in `deploy_stack.py`), but the root README does not mention
    it and lists only five services. Is the grocery bot current and in scope, or
    is the README simply out of date? (See Conflicts §1–3.)

3.2 `HouseGroceryTracker` and `HouseBotRouter` have no README. Is that
    deliberate, or a gap to be filled?

3.3 `HouseGroceryTracker` has no `docker-compose.yml` of its own while
    chore/rental/expense each do. Is standalone local dev intentionally
    unsupported for the grocery bot?

### 4. Undefined domain terms

Each of the following is used in code or docs without ever being defined. I have
not supplied meanings for any of them.

4.1 `scope_id` — the router's primary key, with at least one observed form
    "dm:<SIGNAL_BOT_NUMBER>" (`HouseChoreTracker/README.md` § Quick test). What is the
    full set of valid forms? What is the group form? Is it stable if a Signal
    group is renamed or a member leaves?

4.2 "job" — the router's term for what a chat is for. Is a scope ever allowed to
    have more than one job? Can a job be changed after it is set, and if so by
    whom?

4.3 "admin" — used throughout (`admin help`, `admin stats`, `admin reset group`,
    `has_admins`, `bot_registry.py`, a `chat_admins` table referenced in
    `check_chore_bot.py`). Who becomes an admin, how, and what exactly are they
    allowed to do that others are not? `HouseChoreTracker/README.md` says
    "Everyone can add/edit chores" and "Admin actions are hidden from normal
    help" — but it never states who is an admin.

4.4 "one-shot" — `ONE_SHOT_STATS_KEY` is imported by the tests
    (`test_whole_picture.py:11`) and `test_one_shot.py` is an entire test file
    about it, yet no document defines what a one-shot chore is.

4.5 "vacation" — `HouseChoreTracker/vacation_utils.py` (90 lines) exists and is
    in the deploy whitelist, but no README mentions vacation at all. What is
    this feature and is it live?

4.6 "quiet hours" — stated as `00:00`–`08:00` by default. In whose timezone?
    (`HouseChoreTracker/Dockerfile` sets `TZ=Europe/Berlin`; the router and
    grocery Dockerfiles do not.) Is the timezone per group, per container, or
    fixed?

4.7 "confirmation" vs "reminder" vs "schedule" for a chore — the README treats
    these as three separate settings. What is the intended distinction, and what
    happens in the combinations the README does not describe (e.g. confirmation
    off with a reminder set)?

4.8 "no reminder" — a chore that "can be marked done but should not auto-remind"
    (`HouseChoreTracker/README.md` § Notes). Does such a chore still have a due
    date and still appear as overdue in `list`?

### 5. Partial rules in `HouseChoreTracker/README.md`

These are stated but incomplete. I have not completed any of them.

5.1 "Standard repeat defaults are: hourly tasks repeat every 5 minutes, daily
    tasks every 1 hour, weekly/weekday tasks every 8 hours." What are the
    defaults for monthly and yearly schedules, which the same README says are
    supported ("Schedules support minutes, hours, days, weeks, months, years,
    and weekdays")?

5.2 "Reminders are muted by default from `00:00` to `08:00`." What happens to a
    reminder that comes due *during* quiet hours — dropped, or delivered at
    08:00? Not stated.

5.3 "`reset group` is protected: confirmation code is required within 10 minutes
    and by the same sender." What does the reset actually delete — chores only,
    or history, admins, language, and quiet-hours settings too? Not stated. Can
    it be undone? Not stated.

5.4 "the bot sends a periodic Signal link reminder … roughly every 25 days".
    What does "roughly" mean concretely, and what is the reminder counted from?

5.5 "If no group is configured, the bot still works in direct chat fallback
    mode." What is different in fallback mode? Not stated.

5.6 "Data is isolated per group (group A cannot see group B chores/history)."
    Is this isolation a hard requirement to preserve, or a description of the
    current implementation? Should it become a rule?

5.7 "App updates run database migrations automatically on startup." Is
    forward-only automatic migration a requirement? Is there any rollback story?
    Is a backup taken first?

### 6. Ambiguities

6.1 Root README: "One Signal account, five services". The table that follows
    lists five rows *including* `signal-api`, while `docker-compose.yml` defines
    six services. Does "five services" mean "five containers including
    signal-api" (making it simply outdated by one bot), or "five bot
    services"? Both readings are defensible and both are contradicted by the
    compose file.

6.2 Root README: "Existing chore groups keep working: router detects them via
    chore-bot admins." Is admin-probing fallback a permanent designed behaviour,
    or a one-time migration mechanism that should eventually be removed?

6.3 `HouseChoreTracker/CLAUDE.md` — is this document in force for the whole
    project, for `HouseChoreTracker/` only, or is it a leftover? It says "Merge
    with project-specific instructions as needed", which does not say whose
    instructions or where they live.

### 7. Security and secrets

7.1 `deploy_stack.py`, `audit_server_data.py`, `fix_stack_deploy.py`,
    `check_bots.py`, `check_errors.py` and `check_chore_bot.py` contain a
    hard-coded host, username and password (PASSWORD <redacted>), and several run
    commands that pipe a root password into `su`. Is this acceptable for this
    project, or should a rule forbid credentials in source? I am not assuming
    either answer.

7.2 `HouseChoreTracker/.env` exists inside the project tree. I could not read it
    (blocked by `.claude/settings.json`) and have inferred nothing about it.
    Should real env files live in the tree at all? With no `.gitignore` and no
    git repository, nothing currently prevents one being committed.

7.3 Is the Signal bot number, the LAN address `<SSH_HOST>`, or anything else
    in this repository considered sensitive? No document says.

7.4 All host port bindings are `127.0.0.1`. Is that a deliberate security
    requirement to preserve, or incidental?

### 8. Version control and change management

8.1 This directory is not a git repository and has no `.gitignore`. Is the code
    versioned somewhere else, or is it unversioned? If unversioned, is putting
    it under version control in scope?

8.2 Is deployment via `deploy_stack.py`'s SSH file-copy the intended permanent
    mechanism, or a stopgap?

8.3 `deploy_stack.py` copies an explicit file whitelist per project. What is the
    rule for keeping that list correct when a new module is added? Nothing
    enforces it today.

### 9. Testing

9.1 Only `HouseChoreTracker` has tests, and only via `unittest`. Is `unittest`
    the standard for this project, or historical? Should new tests use it?

9.2 How are the tests actually run (`python test_x.py`, `python -m unittest`,
    something else)? No document, script, or config says.

9.3 Do the tests currently pass? I did not run them. Should they be part of a
    definition of done?

9.4 Is it acceptable that four of the five services have no tests, or is that a
    gap you want closed?

9.5 What is the expected coverage for a change — must a bug fix come with a
    regression test?

### 10. Architecture and code organisation

10.1 `signal_client.py`, `bot_registry.py`, `dialogue_utils.py`, `storage.py`,
     `commands.py`, `stats_charts.py`, `chart_parse.py` and `display_names.py`
     are duplicated across service directories with no shared package. Is that
     independence deliberate (each bot deployable alone) or accumulated
     duplication you want removed? A rule either way changes every future
     change.

10.2 When duplicated logic is fixed in one bot, must the fix be propagated to
     the others? Nothing states this.

10.3 `HouseChoreTracker/commands.py` is 3,560 lines and
     `HouseChoreTracker/storage.py` is 2,227. Is there a size or structure limit
     you want, or is this fine?

10.4 `HouseChoreTracker/rental/` exists as an empty package (`__init__.py` is 0
     bytes) containing only `__pycache__` artefacts for `scrape_types` and
     `storage` — apparently a leftover from rental code once living inside the
     chore bot. Should it be deleted?

10.5 Is there a required layering (app to commands to storage) that new code
     must follow, or is the current shape simply what happened?

### 11. Data, persistence, and migrations

11.1 `signal-cli-config` and `housechoretracker_bot-data` are declared
     `external: true` while the other four volumes are not. Is that deliberate
     (protecting pre-existing data from `docker compose down -v`) or an
     inconsistency to fix?

11.2 Are there backups of any of the five SQLite databases? No document
     mentions one.

11.3 Is there a retention policy for chore history, expense records, rental
     price history, or grocery images? Nothing states one.

11.4 Do any of these databases contain personal data with deletion obligations
     (phone numbers are used as sender identity throughout)? Not stated.

### 12. External dependencies and third-party rules

12.1 `HouseRentalTracker/scrapers.py` targets `casamundo.de`/`.com`,
     `hometogo.de`/`.com`, `fewo-direkt.de`, `amivac.de`,
     `bellevue-ferienhaus.de`, `vacationrenter.com`. Are there terms-of-service
     or rate-limit constraints you want encoded as rules? Is scraping frequency
     (`POLL_TIMES=08:00,20:00`) a hard constraint or a convenience?

12.2 What does `HouseGroceryTracker/image_recognition.py` recognise images
     *with*? It downloads attachments from the Signal API; whether recognition
     is local or via a third-party service, and whether any API key or cost is
     involved, is not stated in any document.

12.3 `signal-api` is pinned to `:latest`. Is unpinned upstream acceptable?

12.4 Are `matplotlib`-based chart features (`stats_charts.py` in three services)
     a supported feature or experimental?

### 13. Language and user-facing text

13.1 Is bilingual English/German support a hard requirement for every new
     user-facing string, or a feature of some bots only? The router, chore bot
     and expense bot show both; nothing states whether grocery and rental do.

13.2 Where do user-facing strings live and what is the rule for adding one?
     `TEXT` is imported from `commands` in the chore tests, but no document
     describes the convention.

13.3 Emoji appear in user-facing bot text (the router's job picker and job
     acknowledgements). Is that an intentional style rule for bot output?

### 14. Working agreement

14.1 Are you the only person working on this? No document names contributors.

14.2 What counts as "done" for a change here — deployed to `<SSH_HOST>`,
     tests passing, something else?

14.3 Is there a change you have tried before that failed, or an approach you
     have deliberately rejected? Nothing in the repository records decisions or
     history, so the decisions log currently starts empty.

---

## Conflicts

No document-vs-document conflict exists *within* `input/`, because `input/`
contains no project documents. The following are conflicts found in the
repository survey, between repository documents and repository code.

### 1. Root README omits the grocery bot that the code deploys

- **README.md** § top: "One Signal account, five services:" — table lists
  `signal-api`, `bot-router`, `chore-bot`, `rental-bot`, `expense-bot`. No
  grocery row.
- **docker-compose.yml** § services: defines a sixth service —
  `grocery-bot:` with `BOT_PORT=5003`, `DATABASE_PATH=/data/grocery.db`,
  `BOT_INSTANCE_NAME=Grocery List Bot`, and `bot-router` `depends_on:` it.
- **HouseBotRouter/group_router.py**: the Job literal includes "grocery".
- **.env.example** (root) also lists `GROCERY_BOT_URL=http://localhost:5003`.

My reading: the root README is stale. I am not resolving it — the alternative
(that the grocery bot is abandoned and the compose entry should be removed) is
also consistent with what I can see, and only you know which.

### 2. Root README's list of job answers omits `grocery`

- **README.md** § Data: "New groups are asked: `chores`, `rentals`, or
  `expenses`."
- **HouseBotRouter/group_router.py** § JOB_TEXT: "Reply: chores · rentals ·
  expenses · grocery" — plus the alias set `grocery, groceries, shopping,
  einkauf, einkaufsliste, einkaufen, lebensmittel, supermarkt`.

### 3. Root README's volume list omits the grocery volume

- **README.md** § Data: lists `housechoretracker_bot-data`,
  `projecthub_rental-bot-data`, `projecthub_expense-bot-data`,
  `projecthub_router-data`.
- **docker-compose.yml** § volumes: also declares `grocery-bot-data` with name
  `projecthub_grocery-bot-data`.

### 4. Root README's project list omits one project

- **README.md** § Projects: lists `HouseChoreTracker/`, `HouseRentalTracker/`,
  `HouseExpenseTracker/`, `HouseBotRouter/`.
- Repository contains a fifth project directory, `HouseGroceryTracker/`, which
  `deploy_stack.py` § PROJECTS also deploys.

### 5. Directory name vs documented deployment root

- **README.md** § Deploy: "From this directory (`ProjectHub`)".
- **deploy_stack.py**: REMOTE_ROOT "/home/signalbot/ProjectHub".
- The actual working directory is
  `C:\Users\Moe\Desktop\ProjectHub\SignalBots` — i.e. `SignalBots` inside a
  parent called `ProjectHub`. Whether the deployed root corresponds to this
  directory or to its parent is not determinable from the documents. This is
  recorded as unresolved, not resolved.

### 6. Unverifiable, not conflicting

`HouseChoreTracker/README.md` makes roughly forty behavioural claims (defaults,
timings, command semantics). I did **not** verify these against
`HouseChoreTracker/commands.py` (3,560 lines) or `storage.py` (2,227 lines) in
this pass. They are neither confirmed nor contradicted here. Treat them as
unverified until checked.

---

## Not extracted

- **`input/README.md` in its entirety.** It is kit boilerplate describing how
  the `input/` folder is used. It asserts nothing about SignalBots. Extracting
  from it would have produced fabricated project facts.

- **`.claude/` contents** (`SKILL.md`, `references/*.md`, `agents/*.md`,
  `hooks/check-ruleset.mjs`, `settings.json`). These are the project-startup
  kit's own machinery, not project source documents. `settings.json` is cited
  once above only to record that it blocks `.env` reads.

- **`HouseChoreTracker/.env` and the four `.env.example` files.** Read access
  denied. Named, not inferred.

- **All `__pycache__/*.pyc` files.** Compiled binaries, not source of record.

- **Detailed behaviour of ~17,000 lines of Python.** `ingestion.md` directs that
  what is already inferable from the code should not be extracted as a rule.
  Command semantics, storage schemas, and dialogue flows live in the code and
  are authoritative there. What I extracted instead is the *shape* of the system
  and the places where documents and code disagree.

- **`HouseChoreTracker/CLAUDE.md` as a rule source.** It is real, and it is
  prescriptive, but its scope is undeclared (it sits in one subdirectory of a
  five-project repository and refers to "project-specific instructions" that do
  not exist). Adopting it project-wide would be an inference. It became question
  6.3 instead.

- **Any statement of purpose, user base, business rule, or success criterion.**
  None exists in any file I could read. This is the largest single gap and it is
  why section 2 of the Questions leads with identity and scope.
