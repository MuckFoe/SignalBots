# Changelog

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
