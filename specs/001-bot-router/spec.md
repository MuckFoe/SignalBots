# 001 — Bot router

**Status:** draft · written 2026-11-24 from the code as it runs today
(`HouseBotRouter/app.py`, `HouseBotRouter/group_router.py`, `docker-compose.yml`).

## Summary

One Signal account and one WhatsApp account are shared by several independent
bots. The router is the only service the messengers talk to: it receives every
incoming message, decides which bot a chat belongs to (its *job*), forwards the
message there and sends the bot's reply back on the right platform.

## Terms

- **Scope** — one chat. `group:<group id>` for a group, `dm:<sender>` for a
  direct chat. WhatsApp ids contain `@` (`…@g.us`, `…@c.us`, `…@lid`); Signal
  ids never do.
- **Job** — what a chat is for: `chores` or `rentals` (and `expenses`, see
  *Deprecated*). One job per scope.
- **Bot contract** — the endpoints every bot serves: `GET /health`,
  `POST /internal/scope`, `POST /internal/handle`, plus `POST /internal/migrate`
  and `POST /internal/merge_member` (spec 002).

## Functional requirements

- **FR1** — The router accepts Signal messages on `POST /webhook` (from
  signal-cli-rest-api) and WhatsApp messages on `POST /webhook/whatsapp` (from
  WAHA). WhatsApp events other than `message`, the bot's own messages, and
  status/broadcast/channel ids are ignored.
- **FR2** — Messages from the bot's own number, messages older than
  `INCOMING_MAX_AGE_SECONDS` (default 300 s), and duplicates of a message seen
  in the last 10 minutes (same sender, group, timestamp, text and attachments)
  are dropped without a reply.
- **FR3** — A scope's job is the one stored in the router's `group_jobs` table.
  If none is stored, the router asks each bot in the order chores, rentals,
  expenses whether it already has admins for that scope (`/internal/scope`) and
  takes the first that says yes. Chats set up before the router existed keep
  working that way.
- **FR4** — A chat with no job gets the job picker. The picker is shown in one
  language if the message hints at German or English, otherwise in both.
- **FR5** — A reply naming a job (`chores`/`haushalt`/`aufgaben`/…,
  `rentals`/`ferien`/`urlaub`/…) stores it. A language word with it
  (`haushalt deutsch`, `en chores`) also sets the bot's language in the same
  step, by forwarding `language en` or `sprache deutsch` to that bot.
- **FR6** — Every other message in a chat with a job is forwarded to that bot's
  `/internal/handle` as `{scope_id, sender, message, group_id, attachments}`,
  with a 120 s timeout. The bot's `reply` (a text or a list of texts) and its
  `attachments` are sent back to the same chat; attachments go with the last
  text.
- **FR7** — In groups, the sender handed to a bot is the person's phone number
  whenever the router knows it (spec 002, FR7). In direct chats the raw chat id
  is kept.
- **FR8** — Replies are sent from one background queue. A target containing
  `@` goes to WhatsApp, anything else to Signal.
- **FR9** — If routing or the bot call fails, the chat gets a short "something
  went wrong, try again" message (in the hinted language, or both).
- **FR10** — A bot can answer `status: ignored_wrong_bot` (another instance of
  that bot owns the group); the router then sends nothing.
- **FR11** — A scope that has moved to another platform (spec 002) is ignored.
- **FR12** — *(built 2026-11-24)* The job picker offers only
  `chores` and `rentals`. Expense words (`expenses`, `ausgaben`, …) no longer
  pick a job in a new chat. Chats that already have the `expenses` job, stored
  or found by probing, keep being routed to expense-bot.
- **FR13** — *(built 2026-11-24)* An admin of the chat's
  current bot can switch the chat to another job with `admin switch bot` /
  `admin bot wechseln`. The router shows the picker without the current job and
  asks for confirmation (yes/no) before storing the new job. The old bot's data
  for that chat stays where it is but gets no more messages. A non-admin is
  refused.

## Acceptance criteria

- **FR1** — A WAHA event with `fromMe: true`, or with a `from` ending in
  `@newsletter` or `status@broadcast`, returns `ignored` and produces no
  message.
- **FR2** — The same Signal envelope posted twice within 10 minutes gives one
  reply. An envelope with a timestamp 10 minutes old returns `ignored_stale`.
- **FR3** — A chore group with an admin in `chores.db` and no `group_jobs` row
  is routed to chore-bot.
- **FR4** — "hallo" in a new group gets only the German picker. "?" gets
  English and German.
- **FR5** — "haushalt deutsch" in a new group stores `chores`, and the next
  reply comes from chore-bot in German without asking for the language again.
- **FR6** — "list" in a chore group returns chore-bot's list in that group.
  A stats chart reply arrives as text plus image.
- **FR7** — A WhatsApp group message from `491701234567@c.us` reaches the bot
  with sender `+491701234567`.
- **FR8** — A reply to a `…@g.us` group is sent through WAHA, never through
  signal-api.
- **FR9** — With chore-bot stopped, "list" in a chore group gets the error
  message, not silence.
- **FR10** — A bot answering `ignored_wrong_bot` produces no message in the
  chat.
- **FR11** — After a completed move, a message in the old group gets no reply.
- **FR12** — "ausgaben" in a new chat gets the picker again, not expense-bot.
  An existing expense group still gets expense-bot's replies.
- **FR13** — An admin of a chore group sends `admin switch bot`, `rentals`,
  `yes`, and the next message is answered by rental-bot. Sending `list` again
  after switching back to chores shows the old chores. A non-admin gets
  "only admins".

## Deprecated

`expenses` (HouseExpenseTracker) is deprecated as of 2026-11-24, and grocery
(HouseGroceryTracker) has been deprecated since it was decommissioned on
2026-09-06. Neither has a spec. Grocery is no longer built, routed or
deployed. Expenses still is: the router still offers `expenses`/`ausgaben` in
the job picker, `resolve_job` still probes expense-bot, and `docker-compose.yml`
and `deploy_stack.py` still build and start it.

**Decided 2026-11-24:** deprecated means hidden from new chats (FR12).
Existing expense groups keep working, and the container stays in compose and
deploy for them.

## Open questions

None. A chat's job can be changed by an admin (FR13, decided 2026-11-24).

## Not covered

- What each bot does with a message: specs 003–008.
- Moving a group between platforms and member identity: spec 002.
- Deployment: spec 009.
