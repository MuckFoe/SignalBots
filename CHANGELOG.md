# Changelog

## 2026-10-21

### For the groups

Sent to every set-up group, in its language and for its bot. The blocks below
are the exact messages; `broadcast_changelog.py` sends them.

```chores-de
📢 Neuigkeiten vom Haushalts-Bot

🎓 Neu: die Anleitung. Schreib anleitung, und der Bot erklärt dir alle Abläufe Schritt für Schritt – vom Anlegen einer Aufgabe über Erinnerungen bis zum Urlaub.

💬 Alle Texte sind überarbeitet: verständlicher, und jeder Befehl, den der Bot vorschlägt, funktioniert jetzt auch. Wer nur einen Befehl schreibt (z.B. erledigt), bekommt eine kurze Erklärung dazu.

🕐 Uhrzeiten bei Erledigungen und in der Statistik stimmen jetzt mit eurer Ortszeit überein – vorher waren sie um 2 Stunden verschoben.

📦 Neu: Umzug nach WhatsApp. Ein Admin schreibt umzug whatsapp, und alle Aufgaben samt Verlauf ziehen in eine WhatsApp-Gruppe mit (zurück geht es genauso). Mehr dazu: anleitung 9

Alle Befehle: hilfe
```

```chores-en
📢 What's new in the chore bot

🎓 New: the tutorial. Send tutorial and the bot explains every flow step by step – from adding a chore to reminders and vacations.

💬 All messages have been rewritten: clearer, and every command the bot suggests now actually works. Sending just a command (e.g. done) now gets you a short explanation.

🕐 Times for completed chores and in the stats now match your local time – before, they were off by 2 hours.

📦 New: moving to WhatsApp. An admin sends move whatsapp and all chores and their history move to a WhatsApp group (and back the same way). More: tutorial 9

All commands: help
```

```rentals-de
📢 Neuigkeiten vom Ferienunterkunft-Bot

💬 Alle Texte sind überarbeitet: verständlicher, und wer nur einen Befehl schreibt (z.B. entfernen), bekommt eine kurze Erklärung dazu.

📦 Neu: Umzug nach WhatsApp. Ein Admin schreibt umzug whatsapp, und alle beobachteten Unterkünfte ziehen in eine WhatsApp-Gruppe mit.

🏠 Noch keine Unterkunft eingetragen? Schick mir einfach den Link: hinzufügen <Link>

Alle Befehle: hilfe
```

```rentals-en
📢 What's new in the rental watcher

💬 All messages have been rewritten: clearer, and sending just a command (e.g. remove) now gets you a short explanation.

📦 New: moving to WhatsApp. An admin sends move whatsapp and all watched rentals move to a WhatsApp group.

🏠 Not watching a rental yet? Just send me the link: add <link>

All commands: help
```

```expenses-de
📢 Neuigkeiten vom Ausgaben-Bot

🛠️ Ausgaben Schritt für Schritt erfassen (hinzufügen) funktioniert wieder – vorher brach es nach dem Betrag ab. Auch bilanz diagramm geht jetzt.

💬 Alle Texte sind überarbeitet: verständlicher, und wer nur einen Befehl schreibt (z.B. ausgegeben), bekommt eine kurze Erklärung dazu.

📦 Neu: Umzug nach WhatsApp. Ein Admin schreibt umzug whatsapp, und alle Ausgaben samt Bilanz ziehen in eine WhatsApp-Gruppe mit.

Alle Befehle: hilfe
```

```expenses-en
📢 What's new in the expense bot

🛠️ Adding an expense step by step (add) works again – before, it stopped after the amount. balances chart works now too.

💬 All messages have been rewritten: clearer, and sending just a command (e.g. spent) now gets you a short explanation.

📦 New: moving to WhatsApp. An admin sends move whatsapp and all expenses and balances move to a WhatsApp group.

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
