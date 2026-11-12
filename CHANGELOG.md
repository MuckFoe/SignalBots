# Changelog

## 2026-11-12 – Chore bot: cold-start notice

### For the groups

Only the chore bot changed; rental and expense groups get no message.

```chores-de
📢 Kurze Info vom Putz-Bot

⏳ Kaltstart: Damit der Rechner nicht dauernd Strom und Speicher belegt, legt sich die KI nach ein paar Minuten ohne Nachrichten schlafen. Beim nächsten frei formulierten Satz (z. B. „spülmaschine ist ausgeräumt“) muss sie erst wieder geladen werden – das dauert etwa eine halbe Minute. Bisher ging die Nachricht dabei verloren; jetzt sagt der Bot kurz Bescheid und schickt die Antwort hinterher.

⚡ Befehle, die der Bot direkt versteht (z. B. „liste“ oder „erledigt Bad“), brauchen die KI nicht und kommen wie immer sofort an.
```

```chores-en
📢 A quick note from the chore bot

⏳ Cold start: so the computer doesn't use power and memory all the time, the AI goes to sleep after a few minutes without messages. For the next free-text message (e.g. "dishwasher is emptied") it first has to load again, which takes about half a minute. Until now that message got lost; now the bot tells you and sends the answer afterwards.

⚡ Commands the bot understands directly (e.g. "list" or "done bathroom") don't need the AI and are answered right away as always.
```

### Under the hood

- Cause: Ollama unloads the model after 5 min idle (`OLLAMA_KEEP_ALIVE=5m` on
  the Mac mini). A cold request takes ~24 s (10 s load + 14 s uncached
  prompt), over `LLM_TIMEOUT_SECONDS=20`, so the first message on 2026-11-12
  timed out and went unanswered.
- `llm_assist.LlmClient` checks `/api/ps` before each call; if the model isn't
  loaded (or other messages are already waiting for it) it raises `ModelCold`.
  A failed check counts as loaded.
- `app.py` answers `ModelCold` with the `llm_warming` notice (once per cold
  start), queues the message, and a worker thread re-runs it with
  `LLM_COLD_TIMEOUT_SECONDS` (default 120) and sends the reply itself (text
  only, no chart attachments).
- Free-text group chatter also triggers the LLM, so after an idle phase a
  plain chat message can produce the notice with no answer following.

## 2026-11-11 – Rental checks at night

### For the groups

Only the rental bot changed; chore and expense groups get no message.

```rentals-de
📢 Kurze Info vom Ferienunterkunft-Bot

🌙 Der Bot prüft eure Unterkünfte jetzt einmal pro Nacht (gegen 3 Uhr) statt morgens und abends. Hat sich bei Preis oder Verfügbarkeit etwas geändert, findet ihr die Nachricht also morgens in der Gruppe.

🔄 Wollt ihr zwischendurch den aktuellen Stand, schreibt einfach „jetzt prüfen“.
```

```rentals-en
📢 A quick note from the rental watcher

🌙 The bot now checks your rentals once a night (around 3 am) instead of morning and evening. If a price or availability changed, you'll find the message in the group in the morning.

🔄 Want the latest in between? Just write "check".
```

### Under the hood

- `POLL_TIMES=02:00` in `docker-compose.yml` (was `08:00,20:00`; the
  container clock is UTC, so 03:00 German time, 04:00 in summer). Keeps the
  rental bot's LLM page reads (~35 s, thinking on) away from daytime chore
  messages; the Mac mini's MLX engine serves one request at a time.
- Chore LLM timeout 8 s → 20 s (loading the model after 30 min idle takes
  ~9 s).

## 2026-11-11 – Chore bot understands free text

### For the groups

Only the chore bot changed; the rental and expense bots get no message.

```chores-de
📢 Neuigkeiten vom Haushalts-Bot

💬 Ihr müsst die Befehle nicht mehr genau kennen. Der Bot versteht jetzt auch normale Sätze, zum Beispiel:
• „bad ist sauber“
• „erinner mich morgen abend den vermieter anzurufen“
• „neue aufgabe staubsaugen alle 2 wochen“
• „was steht noch an?“

✅ Bevor er etwas einträgt oder ändert, fragt er nach („Habe ich das richtig verstanden?“), und ihr antwortet mit ja oder nein. Die gewohnten Befehle funktionieren weiter wie bisher.

🤫 Bei normalen Unterhaltungen in der Gruppe bleibt der Bot still.

🏠 Das Verstehen übernimmt unser eigenes KI-Modell, lokal bei uns zu Hause. Eure Nachrichten gehen an keinen externen KI-Dienst.
```

```chores-en
📢 News from the chore bot

💬 You no longer need to know the exact commands. The bot now understands normal sentences too, for example:
• "bathroom is clean"
• "remind me tomorrow evening to call the landlord"
• "new chore vacuum every 2 weeks"
• "what's left to do?"

✅ Before it adds or changes anything, it asks back ("Did I get that right?") and you answer yes or no. The usual commands keep working as before.

🤫 The bot stays quiet during normal conversation in the group.

🏠 The understanding is done by our own AI model, running locally at home. Your messages are not sent to any external AI service.
```

### Under the hood

- Chore bot LLM command assist switched on (`LLM_ENABLED=true`, all chats):
  free text that no parser understands goes to `qwen3.6:35b` on the Mac mini
  with a strict `json_schema` (slots optional) and thinking off; every slot is
  validated by the bot's own parsers, actions need a yes. Eval: intent 100 %,
  slots 96–98 %, 0 % chatter answered, p50 0.6 s.
- Prompt fixes: open tasks ("ohne termin") are `add_chore` + `none`; task names
  in short base form; "früh/morgens/nachmittags" times; "in 2 days" accepted
  for one-time tasks.
- Mac mini: Ollama switched from Homebrew to the official build (Homebrew's
  lacks xgrammar, so structured output on MLX answered 501), with a daily
  self-checking updater (`macmini/`). The rental bot now gets structured
  output too.

## 2026-11-11 – Rental bot reads more pages

### For the groups

When the rental scrapers can't find the price or availability on a page,
the bot now lets a local AI model (on the Mac mini at home) read the page
text. It only keeps values that literally appear on the page. The chore
groups got a short general note on request (the chore bot itself did not
change; sent separately with `--only chores`). Expense groups were not told.

Not in this release: the headless-browser step (`RENTAL_BROWSER_ENABLED`)
is built in but stays off until it has been tested on real sites.

```rentals-de
📢 Neuigkeiten vom Ferienunterkunft-Bot

🔍 Der Bot erkennt Preise und Verfügbarkeit jetzt auch auf Seiten, die er bisher nicht lesen konnte. Findet er dort nichts auf dem üblichen Weg, liest ein KI-Modell den Seitentext. Übernommen wird nur, was wirklich auf der Seite steht.

🏠 Das Modell läuft lokal bei uns, die Seiten gehen an keinen externen KI-Dienst.

Fehlt bei einer Unterkunft trotzdem noch der Preis, gebt gern Bescheid.
```

```rentals-en
📢 News from the rental watcher

🔍 The bot now finds prices and availability on pages it couldn't read before. When the usual way finds nothing, an AI model reads the page text. Only values that actually appear on the page are used.

🏠 The model runs locally on our own hardware; pages are not sent to any external AI service.

If a rental still shows no price, let us know.
```

```chores-de
📢 Kurze Info zu den Bots

🏠 Hinter den Bots läuft jetzt ein eigenes KI-Modell, lokal bei uns zu Hause. Als Erstes nutzt es der Ferienunterkunft-Bot, um Preise auf Webseiten zu lesen. Daten gehen dabei an keinen externen KI-Dienst.

🧹 Für den Haushalts-Bot ändert sich nichts, alles funktioniert wie gewohnt.
```

```chores-en
📢 A quick note about the bots

🏠 The bots now have their own AI model, running locally at home. The rental watcher is the first to use it, to read prices on web pages. No data is sent to any external AI service.

🧹 Nothing changes for the chore bot, everything works as before.
```

## 2026-11-10 – Open tasks without a schedule

### For the groups

Only the chore bot changed; the rental and expense bots get no message.

```chores-de
📢 Kleine Neuigkeit vom Haushalts-Bot

🛠️ Behoben: Eine Aufgabe ließ sich nicht anlegen, wenn es den gleichen Namen schon in einer anderen Gruppe gab („… konnte nicht angelegt werden“).

📝 Aufgaben ohne festen Termin gehen jetzt leichter: Auf „Wie oft ist … fällig?“ reicht ein „ohne“ (oder „ohne termin“, „kein termin“), und kleine Tippfehler wie „ohen“ versteht der Bot auch. Oder alles auf einmal: aufgabe Spüle putzen ohne
```

```chores-en
📢 A small update from the chore bot

🛠️ Fixed: a chore could not be added if another group already had a chore with the same name ("… could not be added").

📝 Chores without a fixed schedule are easier now: to "How often is … due?" just answer "no schedule" (or "none"), and small typos are understood too. Or all at once: add clean sink no schedule
```

### Under the hood

- Live `chores` table still had the original global `name TEXT NOT NULL
  UNIQUE` (it got `scope_id` via `ALTER TABLE`, so `_migrate_chores_schema`
  skipped it). `Storage._scope_chore_name_uniqueness` rebuilds it with
  `UNIQUE(scope_id, name)`, keeping all columns and ids.
- `parse_schedule` accepts "ohne", "ohne termin", "kein termin", trailing
  punctuation and one-letter typos of the "ohne/kein/no schedule" phrases.
  Answering the name question with "<Name> ohne" creates the open task.
- Replies with a usage hint or "did you mean" log the message text
  (`Not understood in <scope>: …`).

## 2026-10-23 – One person, one member

### For the groups

Only the chore and expense bots changed for their groups; the rental bot
gets no message.

```chores-de
📢 Kleine Neuigkeit vom Haushalts-Bot

🛠️ Behoben: Manchmal hat der Bot jemanden, den er schon kannte, noch einmal nach dem Namen gefragt. Danach gab es die Person doppelt, und ihre Statistik war aufgeteilt.

👤 Der Bot erkennt euch jetzt, wo möglich, an eurer Telefonnummer, und jeder Name kann in einer Gruppe nur einmal vergeben werden.
```

```chores-en
📢 A small update from the chore bot

🛠️ Fixed: the bot sometimes asked someone it already knew for their name again. That person then showed up twice, with their stats split in two.

👤 The bot now recognises you by your phone number where possible, and each name can only be taken once per group.
```

```expenses-de
📢 Kleine Neuigkeit vom Ausgaben-Bot

👤 Der Bot erkennt euch jetzt, wo möglich, an eurer Telefonnummer, und jeder Name kann in einer Gruppe nur einmal vergeben werden. So landet niemand doppelt in der Gruppe, und eure Ausgaben bleiben in einer Bilanz.
```

```expenses-en
📢 A small update from the expense bot

👤 The bot now recognises you by your phone number where possible, and each name can only be taken once per group. That way nobody ends up in the group twice, and your expenses stay in one balance.
```

### Under the hood

- Router hands the bots the phone number as sender in groups
  (`HouseBotRouter/identity.py`): WhatsApp `@c.us` ids, `@lid` ids (via
  WAHA's lids lookup) and Signal UUIDs (once signal-cli has sent both) map
  to `+<number>`; rows under an older id fold in via `/internal/merge_member`
  once per group, and moved members with the same number need no `ich bin`.
- Chore and expense bots refuse a display name another member of the group
  already has.
- Data fix in one chore group: Signal had switched one member from UUID to
  phone number, leaving two "Moritz" entries; merged into one.

## 2026-10-21 – WhatsApp

### For the groups

The bots are now reachable on WhatsApp too, and a group can move between
Signal and WhatsApp with its data. Each group's message names what moves
for its bot.

```chores-de
📱 Den Haushalts-Bot gibt es jetzt auch auf WhatsApp!

Lieber WhatsApp statt Signal? So zieht diese Gruppe um:
1. Ein Admin schreibt hier: umzug whatsapp
2. Erstellt eine WhatsApp-Gruppe und fügt den Bot hinzu: +49 1520 6685988
3. Schickt dort den Code, den der Bot hier nennt: umzug <Code>
4. Jede Person schreibt in der neuen Gruppe einmal: ich bin <Name>

Alle Aufgaben, der Verlauf und die Statistik ziehen mit um. Zurück zu Signal geht es genauso mit: umzug signal
Mehr dazu: anleitung 9
```

```chores-en
📱 The chore bot is now on WhatsApp too!

Prefer WhatsApp over Signal? This is how the group moves:
1. An admin writes here: move whatsapp
2. Create a WhatsApp group and add the bot: +49 1520 6685988
3. Send the code the bot gives you here, in the new group: move <code>
4. Everyone writes once in the new group: i am <name>

All chores, their history and the stats move along. Moving back to Signal works the same way: move signal
More: tutorial 9
```

```rentals-de
📱 Den Ferienunterkunft-Bot gibt es jetzt auch auf WhatsApp!

Lieber WhatsApp statt Signal? So zieht diese Gruppe um:
1. Ein Admin schreibt hier: umzug whatsapp
2. Erstellt eine WhatsApp-Gruppe und fügt den Bot hinzu: +49 1520 6685988
3. Schickt dort den Code, den der Bot hier nennt: umzug <Code>

Alle beobachteten Unterkünfte und Einstellungen ziehen mit um. Zurück zu Signal geht es genauso mit: umzug signal
```

```rentals-en
📱 The rental watcher is now on WhatsApp too!

Prefer WhatsApp over Signal? This is how the group moves:
1. An admin writes here: move whatsapp
2. Create a WhatsApp group and add the bot: +49 1520 6685988
3. Send the code the bot gives you here, in the new group: move <code>

All watched rentals and settings move along. Moving back to Signal works the same way: move signal
```

```expenses-de
📱 Den Ausgaben-Bot gibt es jetzt auch auf WhatsApp!

Lieber WhatsApp statt Signal? So zieht diese Gruppe um:
1. Ein Admin schreibt hier: umzug whatsapp
2. Erstellt eine WhatsApp-Gruppe und fügt den Bot hinzu: +49 1520 6685988
3. Schickt dort den Code, den der Bot hier nennt: umzug <Code>
4. Jede Person schreibt in der neuen Gruppe einmal: ich bin <Name>

Alle Ausgaben und die Bilanz ziehen mit um. Zurück zu Signal geht es genauso mit: umzug signal
```

```expenses-en
📱 The expense bot is now on WhatsApp too!

Prefer WhatsApp over Signal? This is how the group moves:
1. An admin writes here: move whatsapp
2. Create a WhatsApp group and add the bot: +49 1520 6685988
3. Send the code the bot gives you here, in the new group: move <code>
4. Everyone writes once in the new group: i am <name>

All expenses and balances move along. Moving back to Signal works the same way: move signal
```

## 2026-10-21

### For the groups

Sent to every set-up group, in its language. Each group only hears about
changes to its own bot; platform-wide changes (WhatsApp, group moves) are
not announced here. The blocks below are the exact messages;
`broadcast_changelog.py` sends them.

```chores-de
📢 Neuigkeiten vom Haushalts-Bot

🎓 Neu: die Anleitung. Schreib anleitung, und der Bot erklärt dir alle Abläufe Schritt für Schritt – vom Anlegen einer Aufgabe über Erinnerungen bis zum Urlaub.

💬 Alle Texte sind überarbeitet: verständlicher, und jeder Befehl, den der Bot vorschlägt, funktioniert jetzt auch. Wer nur einen Befehl schreibt (z.B. erledigt), bekommt eine kurze Erklärung dazu.

🕐 Uhrzeiten bei Erledigungen und in der Statistik stimmen jetzt mit eurer Ortszeit überein – vorher waren sie um 2 Stunden verschoben.

📊 admin statistik zeigt wieder die Statistik der Gruppe an.

Alle Befehle: hilfe
```

```chores-en
📢 What's new in the chore bot

🎓 New: the tutorial. Send tutorial and the bot explains every flow step by step – from adding a chore to reminders and vacations.

💬 All messages have been rewritten: clearer, and every command the bot suggests now actually works. Sending just a command (e.g. done) now gets you a short explanation.

🕐 Times for completed chores and in the stats now match your local time – before, they were off by 2 hours.

📊 admin stats shows the group's statistics again.

All commands: help
```

```rentals-de
📢 Neuigkeiten vom Ferienunterkunft-Bot

💬 Alle Texte sind überarbeitet: verständlicher, und wer nur einen Befehl schreibt (z.B. entfernen), bekommt eine kurze Erklärung dazu.

Alle Befehle: hilfe
```

```rentals-en
📢 What's new in the rental watcher

💬 All messages have been rewritten: clearer, and sending just a command (e.g. remove) now gets you a short explanation.

🌐 add website works now (it was mistaken for adding a rental link).

All commands: help
```

```expenses-de
📢 Neuigkeiten vom Ausgaben-Bot

🛠️ Ausgaben Schritt für Schritt erfassen (hinzufügen) funktioniert wieder – vorher brach es nach dem Betrag ab. Auch bilanz diagramm geht jetzt.

💬 Alle Texte sind überarbeitet: verständlicher, und wer nur einen Befehl schreibt (z.B. ausgegeben), bekommt eine kurze Erklärung dazu.

Alle Befehle: hilfe
```

```expenses-en
📢 What's new in the expense bot

🛠️ Adding an expense step by step (add) works again – before, it stopped after the amount. balances chart works now too.

💬 All messages have been rewritten: clearer, and sending just a command (e.g. spent) now gets you a short explanation.

All commands: help
```

### Under the hood

- WhatsApp connection via WAHA (`whatsapp-api`), routed through the same bots.
- Group migration between Signal and WhatsApp (`umzug` / `move`, `ich bin` /
  `i am`), backed by `scope_migration.py` in each bot and
  `HouseBotRouter/migrations.py`.
- Chore bot tutorial (`HouseChoreTracker/tutorial.py`).
- All German and English texts in the router and the three bots rewritten;
  advertised commands checked against the parsers; bare command words answer
  with their usage line.
- Fixes: expense guided add crashed after the amount; expense balance charts
  crashed; chore `admin statistik` showed the stats help; chore done messages
  and stats used UTC; rental `add website` never worked in English.
- Signal link monitor (`check_signal_link.sh`, cron on the host).
- grocery-bot decommissioned; `projecthub_` naming dropped.
