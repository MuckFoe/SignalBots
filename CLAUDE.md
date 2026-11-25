# SignalBots: rules for every session

## Every deployed change is announced to every chat

A deploy that changes anything a user of a bot can notice is not finished
until every chat that uses that bot has been told, in its own language:

1. Add a `## <date> – <title>` entry at the top of `CHANGELOG.md` with a
   ```` ```<bot>-de``` ```` and a ```` ```<bot>-en``` ```` block for **each bot
   that changed** (`chores`, `rentals`, `expenses`). Write for the people in the
   chat: what they will notice and what to type, not how it was built. Put the
   technical notes under "Under the hood".
2. Commit and push.
3. Deploy (`python deploy_stack.py`, then `python deploy_stack.py verify`).
4. `python broadcast_changelog.py` (dry run): check the targets and texts.
5. `python broadcast_changelog.py --send`.

The broadcast reaches every chat that uses a bot: set-up groups and direct
chats, on Signal and WhatsApp. It sends the bot that chat uses now (per the
router), never to moved chats or Signal groups the bot has left. A bot that did
not change gets no block, so its chats get no message. A change only the
operator can see (deploy scripts, tests, specs) needs a changelog entry but no
block.

## Specs

`specs/` describes what every part does (see `specs/README.md`). A change in
behaviour updates the matching spec in the same commit.

## Running the scripts

The deploy and broadcast scripts need `paramiko` (not in any
requirements.txt) and read credentials from `.env` through `ssh_config.py`.
The live stack runs from `/home/signalbot/bots`. Tests run per bot folder with
Python 3.10 or newer: `python -m unittest discover -p 'test_*.py'`.
