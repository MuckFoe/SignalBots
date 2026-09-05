from __future__ import annotations

import json
import re

from bot_registry import load_bot_registry, runtime_bot_id
from display_names import is_valid_display_name
from chart_parse import parse_chart_command
from dialogue_utils import STALE_STEP, append_usage_tip, mobile_blocks, parse_stale_response, stale_prompt_text
from money import format_money, parse_amount, split_with_multipliers
from stats_charts import (
    balance_chart,
    balance_chart_kind,
    balance_chart_kinds,
    paid_chart,
    personal_paid_chart,
    top_expenses_chart,
)
from storage import Storage


SUPPORTED_LANGUAGES = {"en", "de"}

USAGE_TIPS = {
    "en": {
        "spent": "Check balances with: balances",
        "balances": "Log expenses with: spent <amount> <description>",
        "join": "After joining, log expenses with: spent 20 coffee",
        "add": "Quick log: spent 80 groceries | Bob 50%",
        "settle": "See who owes what with: balances",
        "members": "Others can join with: join",
    },
    "de": {
        "spent": "Salden prüfen mit: bilanz",
        "balances": "Ausgaben erfassen mit: ausgegeben <Betrag> <Beschreibung>",
        "join": "Nach dem Beitritt: ausgegeben 20 kaffee",
        "add": "Schnell: ausgegeben 80 einkauf | Bob 50%",
        "settle": "Schulden anzeigen mit: bilanz",
        "members": "Andere können mit beitreten dazu kommen",
    },
}

TEXT = {
    "en": {
        "help": (
            "💸 Expense Split Bot (Splitwise/Tricount style):\n\n"
            "- ❓ help\n"
            "- 👥 members (alias: who)\n"
            "- 👋 join\n"
            "- 👤 name <your name>\n"
            "- ➕ add (guided)\n"
            "- 💸 spent <amount> <description>\n"
            "- 💸 spent <amount> <description> | <name> 50%\n"
            "- 💸 paid <amount> <description> (same as spent)\n"
            "- ⚖️ split <amount> <description> (equal split)\n"
            "- ⚖️ split <amount> <desc> | <name>:<amount> ...\n"
            "- ⚖️ split <amount> <desc> | <name>:50% ...\n"
            "- 📋 expenses [limit]\n"
            "- 📋 expense <id>\n"
            "- 🗑️ delete <id>\n"
            "- ⚖️ balances\n"
            "- 🤝 settle <name> [amount] [note]\n"
            "- 🤝 settlements [limit]\n"
            "- 💰 total\n"
            "- 💱 currency <code>\n"
            "- 📊 stats\n"
            "- 📈 balances chart / stats chart\n"
            "🔧 Admin: admin help"
        ),
        "setup_choose_language": (
            "👋 Welcome / Willkommen. Choose language:\n"
            "- language en\n"
            "- sprache deutsch"
        ),
        "setup_choose_bot": "Which bot should manage this group?\n{options}\nReply with: bot <id>",
        "setup_bot_set": "✅ This group now uses: {name} (bot {bot_id}).",
        "setup_choose_name": "👤 What name should I use for you in this group?\nReply with your name, or cancel.",
        "setup_complete": "🎉 Setup complete. Others can join with: join\nExample: spent 80 shopping | Bob 50%",
        "setup_bot_invalid": "Unknown bot. Reply with: bot <id>",
        "members_header": "👥 Members:",
        "members_line": "{idx}. {name} — {balance}",
        "members_empty": "No members yet. Reply: join",
        "join_prompt": "👋 What name should I use for you?\nReply with your name, or cancel.",
        "joined": "👋 You joined as {name}.",
        "already_member": "You are already registered as {name}.",
        "name_saved": "👤 Your name is now: {name}",
        "name_invalid": "Use 2-24 letters, numbers, spaces, or hyphens.",
        "usage_name": "Usage: name <your name>",
        "need_member": "Join first with: join",
        "need_two_members": "Need at least 2 members before splitting expenses.",
        "member_not_found": "⚠️ Member '{name}' not found.",
        "add_amount": "How much was spent? (e.g. 45.50)",
        "add_description": "What was it for?",
        "add_payer": "Who paid?\n{options}\nReply with a number, name, or 'me'.",
        "add_split": "Split equally among all members ({count})?\nReply: yes, no, or cancel.",
        "add_pick_members": "Who shares this expense? Reply with names separated by commas, or 'all'.",
        "add_reduced_shares": (
            "Does anyone pay less than a full share?\n"
            "Example: 4 people shopping, Bob doesn't drink → reply: Bob 50%\n"
            "The bot calculates the rest for everyone else.\n"
            "Reply: none if everyone pays equally."
        ),
        "add_confirm": (
            "Add expense?\n"
            "- {amount} for {description}\n"
            "- paid by {payer}\n"
            "- split:\n{splits}\n"
            "Reply: yes, no, or cancel."
        ),
        "expense_added": "💸 Added expense #{id}: {amount} {description}",
        "expenses_header": "📋 Recent expenses:",
        "expenses_line": "#{id} {amount} {description} — paid by {payer} ({date})",
        "expenses_empty": "No expenses yet. Try: spent 20 coffee",
        "expense_detail": (
            "Expense #{id}: {amount} {description}\n"
            "Paid by: {payer}\n"
            "Split:\n{splits}\n"
            "Date: {date}"
        ),
        "expense_not_found": "⚠️ Expense #{id} not found.",
        "deleted": "🗑️ Deleted expense #{id}.",
        "balances_header": "⚖️ Balances:",
        "balances_line": "- {name}: {balance}",
        "balances_settled": "✅ Everyone is settled up.",
        "debts_header": "💸 Who should pay whom:",
        "debts_line": "- {from_name} → {to_name}: {amount}",
        "settle_done": "🤝 Recorded: {from_name} paid {to_name} {amount}{note}",
        "settle_nothing": "You owe {name} nothing.",
        "settle_usage": "Usage: settle <name> [amount] [note]",
        "settlements_header": "🤝 Recent settlements:",
        "settlements_line": "#{id} {from_name} → {to_name}: {amount}{note} ({date})",
        "settlements_empty": "No settlements recorded yet.",
        "total_spent": "💰 Total group spending: {amount}",
        "currency_set": "Currency set to {currency}.",
        "currency_usage": "Usage: currency EUR",
        "invalid_amount": "Invalid amount. Example: 25.50",
        "invalid_split": "Custom split must match the total. Example: split 100 dinner Alice:60 Bob:40",
        "invalid_reduced_shares": (
            "Use a name and percent of a normal share, e.g. Bob 50%\n"
            "Or: none"
        ),
        "cancelled": "↩️ Cancelled.",
        "confirm_expected": "Reply: yes, no, or cancel.",
        "language_set_en": "Language set to English.",
        "language_set_de": "Language set to German.",
        "language_usage": "Usage: language en or language de",
        "admin_help": "🔧 Admin commands:\n- 🗑️ admin remove member <name>",
        "admin_only": "Use admin commands with: admin <action>",
        "member_removed": "Removed member: {name}",
        "unexpected_error": "⚠️ Something went wrong while handling your command.",
        "unknown": "Unknown command.\n\n{help}",
        "usage_delete": "Usage: delete <expense id>",
        "usage_expense": "Usage: expense <id>",
        "user_stats_header": "📊 Your expense stats:",
        "user_stats_line": "- paid {paid_count} expenses ({paid_total})\n- shared in {shared_count}\n- settlements: {settlements}\n- balance: {balance}",
        "user_stats_empty": "No activity yet. Try: join then spent 20 coffee",
        "chart_empty": "📈 Not enough data for a chart yet.",
        "chart_unknown": "📈 Unknown chart type.",
        "chart_suggest_balances": "💡 Also available:\n• balances chart paid\n• balances chart top",
        "chart_suggest_paid": "💡 Also available:\n• balances chart\n• balances chart top",
        "chart_suggest_top": "💡 Also available:\n• balances chart\n• balances chart paid",
        "chart_suggest_stats": "💡 Group charts:\n• balances chart\n• balances chart paid\n• balances chart top",
    },
    "de": {
        "help": (
            "💸 Ausgaben-Bot (wie Splitwise/Tricount):\n\n"
            "- ❓ hilfe\n"
            "- 👥 mitglieder (auch: who)\n"
            "- 👋 beitreten\n"
            "- 👤 name <dein Name>\n"
            "- ➕ hinzufügen / add (Schritt für Schritt)\n"
            "- 💸 ausgegeben <Betrag> <Beschreibung>\n"
            "- 💸 ausgegeben <Betrag> <Beschreibung> | <Name> 50%\n"
            "- 💸 paid <Betrag> <Beschreibung> (wie ausgegeben)\n"
            "- ⚖️ teilen <Betrag> <Beschreibung> (gleichmäßig)\n"
            "- ⚖️ teilen <Betrag> <Beschreibung> | <Name>:<Betrag> ...\n"
            "- ⚖️ teilen <Betrag> <Beschreibung> | <Name>:50% ...\n"
            "- 📋 ausgaben [Limit]\n"
            "- 📋 ausgabe <id>\n"
            "- 🗑️ löschen <id>\n"
            "- ⚖️ bilanz\n"
            "- 🤝 begleichen <Name> [Betrag] [Notiz]\n"
            "- 🤝 zahlungen [Limit]\n"
            "- 💰 gesamt\n"
            "- 💱 währung <Code>\n"
            "- 📊 statistik\n"
            "- 📈 bilanz diagramm / statistik diagramm\n"
            "🔧 Admin: admin hilfe"
        ),
        "setup_choose_language": (
            "👋 Welcome / Willkommen. Sprache wählen:\n"
            "- language en\n"
            "- sprache deutsch"
        ),
        "setup_choose_bot": "Welcher Bot soll diese Gruppe verwalten?\n{options}\nAntworte mit: bot <id>",
        "setup_bot_set": "✅ Diese Gruppe nutzt jetzt: {name} (bot {bot_id}).",
        "setup_choose_name": "👤 Welchen Namen soll ich für dich verwenden?\nAntworte mit deinem Namen oder abbrechen.",
        "setup_complete": "🎉 Setup fertig. Andere: beitreten\nBeispiel: ausgegeben 80 einkauf | Bob 50%",
        "setup_bot_invalid": "Unbekannter Bot. Antworte mit: bot <id>",
        "members_header": "👥 Mitglieder:",
        "members_line": "{idx}. {name} — {balance}",
        "members_empty": "Noch keine Mitglieder. Antworte: beitreten",
        "join_prompt": "👋 Welchen Namen soll ich für dich verwenden?\nAntworte mit deinem Namen oder abbrechen.",
        "joined": "👋 Du bist als {name} dabei.",
        "already_member": "Du bist bereits als {name} registriert.",
        "name_saved": "👤 Dein Name ist jetzt: {name}",
        "name_invalid": "Bitte 2-24 Zeichen (Buchstaben, Zahlen, Leerzeichen oder Bindestriche).",
        "usage_name": "So geht's: name <dein Name>",
        "need_member": "Zuerst beitreten mit: beitreten",
        "need_two_members": "Mindestens 2 Mitglieder nötig, bevor Ausgaben geteilt werden.",
        "member_not_found": "⚠️ Mitglied '{name}' nicht gefunden.",
        "add_amount": "Wie viel wurde ausgegeben? (z.B. 45,50)",
        "add_description": "Wofür war es?",
        "add_payer": "Wer hat bezahlt?\n{options}\nAntworte mit Nummer, Name oder 'ich'.",
        "add_split": "Gleichmäßig auf alle ({count}) aufteilen?\nAntworte: ja, nein oder abbrechen.",
        "add_pick_members": "Wer ist beteiligt? Namen mit Komma trennen oder 'alle'.",
        "add_reduced_shares": (
            "Zahlt jemand weniger als einen vollen Anteil?\n"
            "Beispiel: 4 Personen einkaufen, Bob trinkt nicht → Bob 50%\n"
            "Der Bot rechnet den Rest für alle anderen aus.\n"
            "Antworte: keine wenn alle gleich zahlen."
        ),
        "add_confirm": (
            "Ausgabe hinzufügen?\n"
            "- {amount} für {description}\n"
            "- bezahlt von {payer}\n"
            "- Aufteilung:\n{splits}\n"
            "Antworte: ja, nein oder abbrechen."
        ),
        "expense_added": "💸 Ausgabe #{id}: {amount} {description}",
        "expenses_header": "📋 Letzte Ausgaben:",
        "expenses_line": "#{id} {amount} {description} — {payer} ({date})",
        "expenses_empty": "Noch keine Ausgaben. z.B.: ausgegeben 20 kaffee",
        "expense_detail": (
            "Ausgabe #{id}: {amount} {description}\n"
            "Bezahlt von: {payer}\n"
            "Aufteilung:\n{splits}\n"
            "Datum: {date}"
        ),
        "expense_not_found": "⚠️ Ausgabe #{id} nicht gefunden.",
        "deleted": "🗑️ Ausgabe #{id} gelöscht.",
        "balances_header": "⚖️ Salden:",
        "balances_line": "- {name}: {balance}",
        "balances_settled": "✅ Alle sind ausgeglichen.",
        "debts_header": "💸 Wer zahlt wem:",
        "debts_line": "- {from_name} → {to_name}: {amount}",
        "settle_done": "🤝 Erfasst: {from_name} zahlte {to_name} {amount}{note}",
        "settle_nothing": "Du schuldest {name} nichts.",
        "settle_usage": "So geht's: begleichen <Name> [Betrag] [Notiz]",
        "settlements_header": "🤝 Letzte Zahlungen:",
        "settlements_line": "#{id} {from_name} → {to_name}: {amount}{note} ({date})",
        "settlements_empty": "Noch keine Zahlungen erfasst.",
        "total_spent": "💰 Gesamtausgaben der Gruppe: {amount}",
        "currency_set": "Währung gesetzt auf {currency}.",
        "currency_usage": "So geht's: währung EUR",
        "invalid_amount": "Ungültiger Betrag. Beispiel: 25,50",
        "invalid_split": "Aufteilung muss den Gesamtbetrag ergeben. z.B. teilen 100 essen Alice:60 Bob:40",
        "invalid_reduced_shares": (
            "Name und Prozent eines normalen Anteils, z.B. Bob 50%\n"
            "Oder: keine"
        ),
        "cancelled": "↩️ Abgebrochen.",
        "confirm_expected": "Antworte: ja, nein oder abbrechen.",
        "language_set_en": "Sprache auf Englisch gesetzt.",
        "language_set_de": "Sprache auf Deutsch gesetzt.",
        "language_usage": "So geht's: language en oder language de",
        "admin_help": "🔧 Admin-Befehle:\n- 🗑️ admin mitglied entfernen <Name>",
        "admin_only": "Admin-Befehle nutzt du mit: admin <Aktion>",
        "member_removed": "Mitglied entfernt: {name}",
        "unexpected_error": "⚠️ Beim Verarbeiten des Befehls ist etwas schiefgelaufen.",
        "unknown": "Unbekannter Befehl.\n\n{help}",
        "usage_delete": "So geht's: löschen <Ausgaben-ID>",
        "usage_expense": "So geht's: ausgabe <id>",
        "user_stats_header": "📊 Deine Ausgaben-Statistik:",
        "user_stats_line": "- {paid_count} mal bezahlt ({paid_total})\n- an {shared_count} Ausgaben beteiligt\n- Zahlungen: {settlements}\n- Saldo: {balance}",
        "user_stats_empty": "Noch keine Aktivität. Probiere: beitreten, dann ausgegeben 20 kaffee",
        "chart_empty": "📈 Noch nicht genug Daten für ein Diagramm.",
        "chart_unknown": "📈 Unbekannter Diagramm-Typ.",
        "chart_suggest_balances": "💡 Auch verfügbar:\n• bilanz diagramm bezahlt\n• bilanz diagramm top",
        "chart_suggest_paid": "💡 Auch verfügbar:\n• bilanz diagramm\n• bilanz diagramm top",
        "chart_suggest_top": "💡 Auch verfügbar:\n• bilanz diagramm\n• bilanz diagramm bezahlt",
        "chart_suggest_stats": "💡 Gruppen-Diagramme:\n• bilanz diagramm\n• bilanz diagramm bezahlt\n• bilanz diagramm top",
    },
}


def _parse_share_multiplier(text: str) -> float | None:
    cleaned = text.strip().lower().replace(",", ".")
    if cleaned in {"half", "halb", "hälfte", "haelfte"}:
        return 0.5
    if cleaned.endswith("%"):
        try:
            value = float(cleaned[:-1])
        except ValueError:
            return None
        if value <= 0 or value > 100:
            return None
        return value / 100
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if value <= 0:
        return None
    if value > 1:
        if value > 100:
            return None
        return value / 100
    return value


def _parse_reduced_shares(
    storage: Storage,
    scope_id: str,
    text: str,
    members: list[str],
) -> dict[str, float] | None:
    cleaned = text.strip().lower()
    if cleaned in {"", "none", "no", "nein", "keine", "nee", "-", "niemand"}:
        return {}
    member_senders = set(members)
    multipliers: dict[str, float] = {}
    for part in re.split(r"[,;]", text):
        part = part.strip()
        if not part:
            continue
        match = re.match(r"^(.+?)\s+(.+)$", part, flags=re.IGNORECASE)
        if not match:
            return None
        name, multiplier_text = match.group(1).strip(), match.group(2).strip()
        row = storage.find_member_by_name(scope_id, name)
        if row is None or row["sender"] not in member_senders:
            return None
        multiplier = _parse_share_multiplier(multiplier_text)
        if multiplier is None or multiplier > 1.0:
            return None
        multipliers[row["sender"]] = multiplier
    return multipliers


def _format_split_lines(
    storage: Storage,
    scope_id: str,
    members: list[str],
    amount_cents: int,
    language: str,
    multipliers: dict[str, float] | None = None,
) -> str:
    currency = storage.get_currency(scope_id)
    shares = split_with_multipliers(amount_cents, members, multipliers or {})
    lines = []
    for member in members:
        multiplier = (multipliers or {}).get(member, 1.0)
        label = storage.display_name(scope_id, member)
        amount = format_money(shares[member], currency, language)
        if multiplier < 1.0:
            percent = int(round(multiplier * 100))
            if language == "de":
                lines.append(f"- {label}: {amount} ({percent}% Anteil)")
            else:
                lines.append(f"- {label}: {amount} ({percent}% share)")
        else:
            lines.append(f"- {label}: {amount}")
    return "\n".join(lines)


def _expense_confirm_text(
    storage: Storage,
    scope_id: str,
    language: str,
    amount_cents: int,
    description: str,
    payer_sender: str,
    members: list[str],
    multipliers: dict[str, float] | None = None,
) -> str:
    currency = storage.get_currency(scope_id)
    return _text(
        language,
        "add_confirm",
        amount=format_money(amount_cents, currency, language),
        description=description,
        payer=storage.display_name(scope_id, payer_sender),
        splits=_format_split_lines(storage, scope_id, members, amount_cents, language, multipliers),
    )


def _parse_quick_expense_text(text: str) -> tuple[int | None, str, str | None]:
    """Parse '100 groceries' or '100 groceries | Bob 50%'."""
    reduced_text: str | None = None
    main = text.strip()
    if "|" in main:
        main, reduced_text = main.split("|", 1)
        main = main.strip()
        reduced_text = reduced_text.strip() or None
    parts = main.split(None, 1)
    if len(parts) < 2:
        return None, "", reduced_text
    amount_cents = parse_amount(parts[0])
    return amount_cents, parts[1].strip(), reduced_text


def _quick_expense_with_optional_reductions(
    storage: Storage,
    scope_id: str,
    sender: str,
    amount_cents: int,
    description: str,
    language: str,
    reduced_text: str | None = None,
    paid_by: str | None = None,
) -> str:
    members = [row["sender"] for row in storage.list_members(scope_id)]
    multipliers: dict[str, float] | None = None
    if reduced_text:
        parsed = _parse_reduced_shares(storage, scope_id, reduced_text, members)
        if parsed is None:
            return _text(language, "invalid_reduced_shares")
        multipliers = parsed
    return _quick_add_expense(
        storage,
        scope_id,
        sender,
        amount_cents,
        description,
        language,
        paid_by=paid_by,
        split_members=members,
        multipliers=multipliers,
    )


def _text(language: str, key: str, **kwargs) -> str:
    template = TEXT.get(language, TEXT["en"]).get(key, TEXT["en"].get(key, key))
    return template.format(**kwargs)


def _with_usage_tip(
    storage: Storage,
    scope_id: str,
    sender: str,
    language: str,
    command_key: str,
    reply: str,
) -> str:
    count = storage.bump_command_usage(scope_id, sender, command_key)
    tip = USAGE_TIPS.get(language, USAGE_TIPS["en"]).get(command_key)
    return append_usage_tip(reply, tip, count)


def _format_user_stats(storage: Storage, scope_id: str, sender: str, language: str) -> str:
    stats = storage.user_stats(scope_id, sender)
    if stats["paid_count"] == 0 and stats["shared_count"] == 0:
        return text_for(storage, scope_id, "user_stats_empty")
    currency = storage.get_currency(scope_id)
    return text_for(storage, scope_id, "user_stats_header") + "\n\n" + text_for(
        storage,
        scope_id,
        "user_stats_line",
        paid_count=stats["paid_count"],
        paid_total=format_money(stats["paid_total"], currency, language),
        shared_count=stats["shared_count"],
        settlements=stats["settlements"],
        balance=format_money(stats["balance_cents"], currency, language),
    )


def _chart_reply(reply: str, attachments: list[str]) -> dict:
    return {"reply": reply, "attachments": attachments}


def _expense_balance_chart(
    storage: Storage,
    scope_id: str,
    language: str,
    kind: str | None,
) -> str | dict:
    currency = storage.get_currency(scope_id)
    members = storage.list_members(scope_id)
    if not members:
        return text_for(storage, scope_id, "members_empty")

    normalized = balance_chart_kind(kind)
    if kind and normalized not in {"balances", "paid", "top"}:
        return text_for(storage, scope_id, "chart_unknown")

    caption = text_for(storage, scope_id, "balances_header")
    if normalized == "paid":
        paid_totals = storage.member_paid_totals(scope_id)
        rows = [
            (storage.display_name(scope_id, member["sender"]), paid_totals.get(member["sender"], 0))
            for member in members
            if paid_totals.get(member["sender"], 0) > 0
        ]
        rows.sort(key=lambda item: item[1], reverse=True)
        chart = paid_chart(rows[:12], currency, language)
        hint = text_for(storage, scope_id, "chart_suggest_paid")
    elif normalized == "top":
        expenses = storage.list_expenses(scope_id, limit=12)
        rows = [(row["description"], int(row["amount_cents"])) for row in expenses]
        chart = top_expenses_chart(rows, currency, language)
        hint = text_for(storage, scope_id, "chart_suggest_top")
    else:
        balances = storage.compute_balances(scope_id)
        rows = [
            (storage.display_name(scope_id, member["sender"]), balances.get(member["sender"], 0))
            for member in members
        ]
        chart = balance_chart(rows, currency, language)
        hint = text_for(storage, scope_id, "chart_suggest_balances")

    if not chart:
        return mobile_blocks(caption, text_for(storage, scope_id, "chart_empty"))
    return _chart_reply(mobile_blocks(caption, hint), [chart])


def _expense_stats_chart(
    storage: Storage,
    scope_id: str,
    sender: str,
    language: str,
) -> str | dict:
    reply = _format_user_stats(storage, scope_id, sender, language)
    if reply == text_for(storage, scope_id, "user_stats_empty"):
        return reply
    currency = storage.get_currency(scope_id)
    expenses = [
        row
        for row in storage.list_expenses(scope_id, limit=50)
        if row["paid_by"] == sender
    ]
    expenses.sort(key=lambda row: int(row["amount_cents"]), reverse=True)
    rows = [(row["description"], int(row["amount_cents"])) for row in expenses[:12]]
    chart = personal_paid_chart(rows, currency, language)
    hint = text_for(storage, scope_id, "chart_suggest_stats")
    if not chart:
        return mobile_blocks(reply, text_for(storage, scope_id, "chart_empty"))
    return _chart_reply(mobile_blocks(reply, hint), [chart])


def _expense_step_prompt(storage: Storage, scope_id: str, sender: str, language: str) -> str:
    pending = storage.get_pending_expense(scope_id, sender)
    if pending is None:
        return text_for(storage, scope_id, "cancelled")
    step = pending["step"]
    if step == "amount":
        return text_for(storage, scope_id, "add_amount")
    if step == "description":
        return text_for(storage, scope_id, "add_description")
    if step == "payer":
        return text_for(storage, scope_id, "add_payer", options=_member_options(storage, scope_id, language))
    if step == "split":
        return text_for(storage, scope_id, "add_split", count=len(storage.list_members(scope_id)))
    if step == "pick_members":
        return text_for(storage, scope_id, "add_pick_members")
    if step == "reduced_shares":
        return text_for(storage, scope_id, "add_reduced_shares")
    if step == "confirm":
        members = json.loads(pending["split_members_json"])
        multipliers = json.loads(pending["split_multipliers_json"]) if pending["split_multipliers_json"] else {}
        payer = pending["paid_by"] or sender
        return _expense_confirm_text(
            storage,
            scope_id,
            language,
            int(pending["amount_cents"]),
            pending["description"],
            payer,
            members,
            multipliers or None,
        )
    return text_for(storage, scope_id, "add_amount")


def text_for(storage: Storage, scope_id: str, key: str, **kwargs) -> str:
    return _text(storage.get_language(scope_id), key, **kwargs)


def _help_language(storage: Storage, scope_id: str, text: str, fallback: str) -> str:
    lowered = text.strip().lower()
    if any(token in lowered for token in ("deutsch", "german", " sprache de", " language de")):
        return "de"
    if any(token in lowered for token in ("english", "englisch", " sprache en", " language en")):
        return "en"
    return fallback


def _is_cancel(text: str) -> bool:
    return text.strip().lower() in {"cancel", "abbrechen", "stop"}


def _confirmation_answer(text: str) -> bool | None:
    cleaned = text.strip().lower()
    if cleaned in {"yes", "y", "ja", "j"}:
        return True
    if cleaned in {"no", "n", "nein"}:
        return False
    return None


def _language_from_command(text: str) -> str | None:
    lowered = text.strip().lower()
    if lowered in {"language", "sprache", "lang"}:
        return ""
    if lowered in {"language en", "lang en", "sprache englisch", "sprache en", "english"}:
        return "en"
    if lowered in {"language de", "lang de", "sprache deutsch", "sprache de", "german", "deutsch"}:
        return "de"
    if lowered.startswith("language ") or lowered.startswith("sprache "):
        return "invalid"
    return None


def _admin_action(text: str) -> tuple[bool, str]:
    lowered = text.strip().lower()
    if lowered.startswith("admin "):
        return True, text[6:].strip()
    if lowered == "admin":
        return True, ""
    return False, ""


def _format_bot_options(language: str) -> str:
    bots = load_bot_registry()
    return "\n".join(f"{idx}. {name} (bot {bot_id})" for idx, (bot_id, name) in enumerate(bots.items(), start=1))


def _parse_bot_command(text: str) -> str | None:
    lowered = text.strip().lower()
    if lowered in {"bot", "bot help", "bot hilfe"}:
        return ""
    if not lowered.startswith("bot "):
        return None
    bot_id = text.strip()[4:].strip()
    if not bot_id:
        return ""
    bots = load_bot_registry()
    if bot_id in bots:
        return bot_id
    if bot_id.isdigit():
        keys = list(bots.keys())
        index = int(bot_id) - 1
        if 0 <= index < len(keys):
            return keys[index]
    return "invalid"


def _complete_bot_setup(storage: Storage, scope_id: str, sender: str, language: str, bot_id: str) -> list[str]:
    bots = load_bot_registry()
    storage.set_bot_id(scope_id, bot_id)
    storage.add_admin(scope_id, sender)
    storage.start_pending_member_name(scope_id, sender, purpose="setup")
    return [
        _text(language, "setup_bot_set", name=bots[bot_id], bot_id=bot_id),
        _text(language, "setup_choose_name"),
    ]


def _format_balance(storage: Storage, scope_id: str, cents: int, language: str) -> str:
    currency = storage.get_currency(scope_id)
    formatted = format_money(abs(cents), currency, language)
    if cents > 0:
        return f"+{formatted}" if language == "en" else f"+{formatted} (bekommt)"
    if cents < 0:
        return f"-{formatted}" if language == "en" else f"-{formatted} (schuldet)"
    return formatted


def _member_options(storage: Storage, scope_id: str, language: str) -> str:
    members = storage.list_members(scope_id)
    lines = []
    for idx, row in enumerate(members, start=1):
        lines.append(f"{idx}. {row['display_name']}")
    me = "me" if language == "en" else "ich"
    lines.append(f"- {me}")
    return "\n".join(lines)


def _resolve_payer(storage: Storage, scope_id: str, sender: str, text: str, language: str) -> str | None:
    cleaned = text.strip().lower()
    if cleaned in {"me", "ich", "i"}:
        return sender
    if cleaned.isdigit():
        members = storage.list_members(scope_id)
        index = int(cleaned) - 1
        if 0 <= index < len(members):
            return members[index]["sender"]
        return None
    row = storage.find_member_by_name(scope_id, text.strip())
    return row["sender"] if row else None


def _parse_member_list(storage: Storage, scope_id: str, text: str, language: str) -> list[str] | None:
    cleaned = text.strip().lower()
    if cleaned in {"all", "alle", "everyone", "jeder"}:
        return [row["sender"] for row in storage.list_members(scope_id)]
    names = [part.strip() for part in text.split(",") if part.strip()]
    if not names:
        return None
    senders: list[str] = []
    for name in names:
        row = storage.find_member_by_name(scope_id, name)
        if row is None:
            return None
        if row["sender"] not in senders:
            senders.append(row["sender"])
    return senders


def _format_members(storage: Storage, scope_id: str, language: str) -> str:
    members = storage.list_members(scope_id)
    if not members:
        return _text(language, "members_empty")
    balances = storage.compute_balances(scope_id)
    lines = [_text(language, "members_header")]
    for idx, row in enumerate(members, start=1):
        lines.append(
            _text(
                language,
                "members_line",
                idx=idx,
                name=row["display_name"],
                balance=_format_balance(storage, scope_id, balances.get(row["sender"], 0), language),
            )
        )
    return mobile_blocks(*lines)


def _format_balances(storage: Storage, scope_id: str, language: str) -> str:
    members = storage.list_members(scope_id)
    if not members:
        return _text(language, "members_empty")
    balances = storage.compute_balances(scope_id)
    lines = [_text(language, "balances_header")]
    for row in members:
        lines.append(
            _text(
                language,
                "balances_line",
                name=row["display_name"],
                balance=_format_balance(storage, scope_id, balances.get(row["sender"], 0), language),
            )
        )
    debts = storage.simplified_debts(scope_id)
    if debts:
        lines.append("")
        lines.append(_text(language, "debts_header"))
        for debtor, creditor, amount in debts:
            note = ""
            lines.append(
                _text(
                    language,
                    "debts_line",
                    from_name=storage.display_name(scope_id, debtor),
                    to_name=storage.display_name(scope_id, creditor),
                    amount=format_money(amount, storage.get_currency(scope_id), language),
                )
            )
    elif all(value == 0 for value in balances.values()):
        lines.append(_text(language, "balances_settled"))
    return mobile_blocks(*lines)


def _format_expenses(storage: Storage, scope_id: str, language: str, limit: int = 15) -> str:
    rows = storage.list_expenses(scope_id, limit=limit)
    if not rows:
        return _text(language, "expenses_empty")
    currency = storage.get_currency(scope_id)
    lines = [_text(language, "expenses_header")]
    for row in rows:
        lines.append(
            _text(
                language,
                "expenses_line",
                id=row["id"],
                amount=format_money(row["amount_cents"], row["currency"] or currency, language),
                description=row["description"],
                payer=storage.display_name(scope_id, row["paid_by"]),
                date=row["created_at"],
            )
        )
    return mobile_blocks(*lines)


def _format_expense_detail(storage: Storage, scope_id: str, expense_id: int, language: str) -> str:
    row = storage.get_expense(scope_id, expense_id)
    if row is None:
        return _text(language, "expense_not_found", id=expense_id)
    splits = storage.list_expense_splits(expense_id)
    split_lines = []
    for split in splits:
        label = storage.display_name(scope_id, split["member_sender"])
        amount = format_money(split["share_cents"], row["currency"], language)
        multiplier = split["share_multiplier"] if "share_multiplier" in split.keys() else 1.0
        if multiplier and multiplier < 1.0:
            percent = int(round(multiplier * 100))
            if language == "de":
                split_lines.append(f"- {label}: {amount} ({percent}% Anteil)")
            else:
                split_lines.append(f"- {label}: {amount} ({percent}% share)")
        else:
            split_lines.append(f"- {label}: {amount}")
    return _text(
        language,
        "expense_detail",
        id=row["id"],
        amount=format_money(row["amount_cents"], row["currency"], language),
        description=row["description"],
        payer=storage.display_name(scope_id, row["paid_by"]),
        splits="\n".join(split_lines),
        date=row["created_at"],
    )


def _commit_pending_expense(storage: Storage, scope_id: str, sender: str, language: str) -> str:
    pending = storage.get_pending_expense(scope_id, sender)
    if pending is None:
        return _text(language, "unexpected_error")
    members = json.loads(pending["split_members_json"])
    if len(members) < 1:
        return _text(language, "need_two_members")
    multipliers = json.loads(pending["split_multipliers_json"]) if pending["split_multipliers_json"] else {}
    currency = storage.get_currency(scope_id)
    expense_id = storage.add_expense(
        scope_id,
        pending["description"],
        int(pending["amount_cents"]),
        currency,
        pending["paid_by"],
        members,
        sender,
        multipliers=multipliers,
    )
    storage.clear_pending_expense(scope_id, sender)
    header = _text(
        language,
        "expense_added",
        id=expense_id,
        amount=format_money(int(pending["amount_cents"]), currency, language),
        description=pending["description"],
    )
    if multipliers:
        header += "\n\n" + _format_split_lines(
            storage,
            scope_id,
            members,
            int(pending["amount_cents"]),
            language,
            multipliers,
        )
    return header


def _handle_pending_member_name(storage: Storage, text: str, sender: str, scope_id: str, language: str) -> str | None:
    pending = storage.get_pending_member_name(scope_id, sender)
    if pending is None:
        return None
    if pending["step"] == STALE_STEP:
        action = parse_stale_response(text)
        if action == "discard":
            storage.clear_pending_member_name(scope_id, sender)
            return _text(language, "cancelled")
        if action == "continue":
            storage.restore_dialogue_step("pending_member_names", scope_id, sender)
            return _text(language, "join_prompt")
        return stale_prompt_text(language, "join")
    if _is_cancel(text):
        storage.clear_pending_member_name(scope_id, sender)
        return _text(language, "cancelled")
    display_name = text.strip()
    if not is_valid_display_name(display_name):
        return _text(language, "name_invalid")
    storage.set_display_name(scope_id, sender, display_name)
    storage.clear_pending_member_name(scope_id, sender)
    if pending["purpose"] == "setup":
        return _text(language, "setup_complete")
    return _text(language, "joined", name=display_name)


def _handle_pending_expense(storage: Storage, text: str, sender: str, scope_id: str, language: str) -> str | None:
    pending = storage.get_pending_expense(scope_id, sender)
    if pending is None:
        return None
    if pending["step"] == STALE_STEP:
        action = parse_stale_response(text)
        if action == "discard":
            storage.clear_pending_expense(scope_id, sender)
            return _text(language, "cancelled")
        if action == "continue":
            storage.restore_dialogue_step("pending_expense_adds", scope_id, sender)
            return _expense_step_prompt(storage, scope_id, sender, language)
        return stale_prompt_text(language, "expense")
    if _is_cancel(text):
        storage.clear_pending_expense(scope_id, sender)
        return _text(language, "cancelled")

    step = pending["step"]
    if step == "amount":
        amount_cents = parse_amount(text)
        if amount_cents is None:
            return _text(language, "invalid_amount")
        storage.update_pending_expense(scope_id, sender, "description", amount_cents=amount_cents)
        return _text(language, "add_description")

    if step == "description":
        description = text.strip()
        if not description:
            return _text(language, "add_description")
        storage.update_pending_expense(scope_id, sender, "payer", description=description)
        return _text(language, "add_payer", options=_member_options(storage, scope_id, language))

    if step == "payer":
        payer = _resolve_payer(storage, scope_id, sender, text, language)
        if payer is None:
            return _text(language, "member_not_found", name=text.strip())
        members = storage.list_members(scope_id)
        storage.update_pending_expense(scope_id, sender, "split", paid_by=payer)
        return _text(language, "add_split", count=len(members))

    if step == "split":
        answer = _confirmation_answer(text)
        if answer is None:
            return _text(language, "confirm_expected")
        if not answer:
            storage.update_pending_expense(scope_id, sender, "pick_members")
            return _text(language, "add_pick_members")
        pending = storage.get_pending_expense(scope_id, sender)
        all_members = [row["sender"] for row in storage.list_members(scope_id)]
        payer = pending["paid_by"] or sender
        storage.update_pending_expense(
            scope_id,
            sender,
            "confirm",
            split_members=all_members,
            split_multipliers={},
        )
        return _expense_confirm_text(
            storage,
            scope_id,
            language,
            int(pending["amount_cents"]),
            pending["description"],
            payer,
            all_members,
            None,
        )

    if step == "pick_members":
        members = _parse_member_list(storage, scope_id, text, language)
        if not members:
            return _text(language, "add_pick_members")
        storage.update_pending_expense(scope_id, sender, "reduced_shares", split_members=members)
        return _text(language, "add_reduced_shares")

    if step == "reduced_shares":
        pending = storage.get_pending_expense(scope_id, sender)
        members = json.loads(pending["split_members_json"])
        multipliers = _parse_reduced_shares(storage, scope_id, text, members)
        if multipliers is None:
            return _text(language, "invalid_reduced_shares")
        storage.update_pending_expense(
            scope_id,
            sender,
            "confirm",
            split_multipliers=multipliers,
        )
        payer = pending["paid_by"] or sender
        return _expense_confirm_text(
            storage,
            scope_id,
            language,
            int(pending["amount_cents"]),
            pending["description"],
            payer,
            members,
            multipliers,
        )

    if step == "confirm":
        answer = _confirmation_answer(text)
        if answer is None:
            return _text(language, "confirm_expected")
        if not answer:
            storage.clear_pending_expense(scope_id, sender)
            return _text(language, "cancelled")
        return _commit_pending_expense(storage, scope_id, sender, language)
    return None


def _ensure_member_or_prompt(storage: Storage, scope_id: str, sender: str, language: str) -> str | None:
    if storage.is_member(scope_id, sender):
        return None
    storage.start_pending_member_name(scope_id, sender, purpose="join")
    return _text(language, "join_prompt")


def _quick_add_expense(
    storage: Storage,
    scope_id: str,
    sender: str,
    amount_cents: int,
    description: str,
    language: str,
    paid_by: str | None = None,
    split_members: list[str] | None = None,
    custom_shares: dict[str, int] | None = None,
    multipliers: dict[str, float] | None = None,
) -> str:
    members = split_members or [row["sender"] for row in storage.list_members(scope_id)]
    if len(members) < 2:
        return _text(language, "need_two_members")
    payer = paid_by or sender
    currency = storage.get_currency(scope_id)
    expense_id = storage.add_expense(
        scope_id,
        description,
        amount_cents,
        currency,
        payer,
        members,
        sender,
        split_type="custom" if custom_shares else ("weighted" if multipliers else "equal"),
        custom_shares=custom_shares,
        multipliers=multipliers,
    )
    header = _text(
        language,
        "expense_added",
        id=expense_id,
        amount=format_money(amount_cents, currency, language),
        description=description,
    )
    if multipliers:
        header += "\n\n" + _format_split_lines(
            storage, scope_id, members, amount_cents, language, multipliers
        )
    return header


def _parse_custom_split(
    text: str,
) -> tuple[str, dict[str, int] | None, dict[str, float] | None] | None:
    if "|" not in text:
        return None
    left, right = text.split("|", 1)
    left = left.strip()
    right = right.strip()
    if not left or not right:
        return None
    parts = left.split(None, 1)
    if len(parts) < 2:
        return None
    amount_cents = parse_amount(parts[0])
    description = parts[1].strip()
    if amount_cents is None or not description:
        return None

    fixed_shares: dict[str, int] = {}
    percent_shares: dict[str, float] = {}
    for chunk in right.split():
        if ":" not in chunk:
            return None
        name, value_text = chunk.split(":", 1)
        name = name.strip()
        value_text = value_text.strip()
        share_cents = parse_amount(value_text)
        multiplier = _parse_share_multiplier(value_text)
        if share_cents is not None:
            fixed_shares[name] = share_cents
        elif multiplier is not None:
            percent_shares[name] = multiplier
        else:
            return None

    if fixed_shares and percent_shares:
        return None
    if fixed_shares:
        if sum(fixed_shares.values()) != amount_cents:
            return None
        return description, fixed_shares, None
    if percent_shares:
        return description, None, percent_shares
    return None


def handle_command(
    storage: Storage,
    message_text: str,
    sender: str,
    scope_id: str,
    group_id: str | None = None,
) -> str | list[str]:
    language = storage.get_language(scope_id)
    command_text = message_text.strip()
    command_lowered = command_text.lower()
    admin_seen, admin_text = _admin_action(command_text)
    is_group = group_id is not None

    if not storage.has_language(scope_id):
        language_request = _language_from_command(command_text)
        if language_request is None:
            return text_for(storage, scope_id, "setup_choose_language")
        if language_request == "invalid" or not language_request:
            return text_for(storage, scope_id, "language_usage")
        storage.set_language(scope_id, language_request)
        storage.add_admin(scope_id, sender)
        if len(load_bot_registry()) > 1:
            return text_for(
                storage,
                scope_id,
                "setup_choose_bot",
                options=_format_bot_options(language_request),
            )
        bot_id = next(iter(load_bot_registry()))
        storage.set_bot_id(scope_id, bot_id)
        storage.start_pending_member_name(scope_id, sender, purpose="setup")
        return text_for(storage, scope_id, "setup_choose_name")

    language = storage.get_language(scope_id)

    if not storage.has_bot(scope_id):
        bot_choice = _parse_bot_command(command_text)
        if bot_choice is None:
            return text_for(
                storage,
                scope_id,
                "setup_choose_bot",
                options=_format_bot_options(language),
            )
        if bot_choice == "invalid" or not bot_choice:
            return text_for(storage, scope_id, "setup_bot_invalid")
        return _complete_bot_setup(storage, scope_id, sender, language, bot_choice)

    if command_lowered in {"help", "hilfe", "?"}:
        return text_for(storage, scope_id, "help")

    if storage.get_pending_member_name(scope_id, sender) is not None and storage.has_bot(scope_id):
        reply = _handle_pending_member_name(storage, command_text, sender, scope_id, language)
        if reply is not None:
            return reply

    if not storage.is_group_ready(scope_id):
        if storage.get_pending_member_name(scope_id, sender) is not None:
            return _handle_pending_member_name(storage, command_text, sender, scope_id, language) or text_for(
                storage, scope_id, "setup_choose_name"
            )
        storage.start_pending_member_name(scope_id, sender, purpose="setup")
        return text_for(storage, scope_id, "setup_choose_name")

    if command_lowered in {"help", "hilfe", "?"}:
        return text_for(storage, scope_id, "help")

    if command_lowered in {"stats", "statistik", "my stats", "meine statistik"}:
        return _format_user_stats(storage, scope_id, sender, language)

    chart_base, wants_chart, chart_kind = parse_chart_command(command_lowered)
    if wants_chart:
        if chart_base in {"balances", "bilanz", "balance", "schulden"}:
            member_prompt = _ensure_member_or_prompt(storage, scope_id, sender, language)
            if member_prompt is not None:
                return member_prompt
            return _expense_balance_chart(storage, scope_id, language, chart_kind)
        if chart_base in {"stats", "statistik", "my stats", "meine statistik"}:
            return _expense_stats_chart(storage, scope_id, sender, language)

    language_request = _language_from_command(command_text)
    if language_request is not None:
        if language_request == "invalid" or not language_request:
            return text_for(storage, scope_id, "language_usage")
        storage.set_language(scope_id, language_request)
        key = "language_set_de" if language_request == "de" else "language_set_en"
        return text_for(storage, scope_id, key)

    if admin_seen and command_lowered in {"admin", "admin help", "admin hilfe"}:
        return text_for(storage, scope_id, "admin_help")

    if _is_cancel(command_text):
        storage.clear_pending_expense(scope_id, sender)
        storage.clear_pending_member_name(scope_id, sender)
        return text_for(storage, scope_id, "cancelled")

    pending_name = _handle_pending_member_name(storage, command_text, sender, scope_id, language)
    if pending_name is not None:
        return pending_name

    pending_expense = _handle_pending_expense(storage, command_text, sender, scope_id, language)
    if pending_expense is not None:
        return pending_expense

    if command_lowered in {"join", "beitreten"}:
        if storage.is_member(scope_id, sender):
            return text_for(storage, scope_id, "already_member", name=storage.display_name(scope_id, sender))
        storage.start_pending_member_name(scope_id, sender, purpose="join")
        return _with_usage_tip(storage, scope_id, sender, language, "join", text_for(storage, scope_id, "join_prompt"))

    member_prompt = _ensure_member_or_prompt(storage, scope_id, sender, language)
    if member_prompt is not None and command_lowered not in {"members", "mitglieder"}:
        return member_prompt

    name_value = command_text
    for prefix in ("name ", "my name ", "mein name "):
        if command_lowered.startswith(prefix):
            name_value = command_text[len(prefix):].strip()
            break
    else:
        name_value = ""
    if name_value or command_lowered in {"name", "my name", "mein name"}:
        if not name_value:
            return text_for(storage, scope_id, "usage_name")
        if not is_valid_display_name(name_value):
            return text_for(storage, scope_id, "name_invalid")
        storage.set_display_name(scope_id, sender, name_value)
        return text_for(storage, scope_id, "name_saved", name=name_value.strip())

    if command_lowered in {"members", "mitglieder", "who"}:
        return _with_usage_tip(storage, scope_id, sender, language, "members", _format_members(storage, scope_id, language))

    if command_lowered in {"balances", "bilanz", "balance", "schulden"}:
        return _with_usage_tip(storage, scope_id, sender, language, "balances", _format_balances(storage, scope_id, language))

    if command_lowered in {"total", "gesamt"}:
        currency = storage.get_currency(scope_id)
        return text_for(
            storage,
            scope_id,
            "total_spent",
            amount=format_money(storage.total_spent(scope_id), currency, language),
        )

    if command_lowered.startswith("currency ") or command_lowered.startswith("währung ") or command_lowered.startswith("waehrung "):
        parts = command_text.split(None, 1)
        if len(parts) < 2 or len(parts[1].strip()) != 3:
            return text_for(storage, scope_id, "currency_usage")
        storage.set_currency(scope_id, parts[1].strip())
        return text_for(storage, scope_id, "currency_set", currency=parts[1].strip().upper())

    if command_lowered in {"add", "hinzufügen", "hinzufuegen"}:
        if len(storage.list_members(scope_id)) < 2:
            return text_for(storage, scope_id, "need_two_members")
        storage.start_pending_expense(scope_id, sender)
        return _with_usage_tip(storage, scope_id, sender, language, "add", text_for(storage, scope_id, "add_amount"))

    for prefix in ("spent ", "ausgegeben ", "paid "):
        if command_lowered.startswith(prefix):
            rest = command_text[len(prefix):].strip()
            amount_cents, description, reduced_text = _parse_quick_expense_text(rest)
            if amount_cents is None or not description:
                return text_for(storage, scope_id, "invalid_amount")
            return _with_usage_tip(
                storage,
                scope_id,
                sender,
                language,
                "spent",
                _quick_expense_with_optional_reductions(
                    storage,
                    scope_id,
                    sender,
                    amount_cents,
                    description,
                    language,
                    reduced_text=reduced_text,
                ),
            )

    if command_lowered.startswith("split ") or command_lowered.startswith("teilen "):
        prefix = "split " if command_lowered.startswith("split ") else "teilen "
        rest = command_text[len(prefix):].strip()
        parsed = _parse_custom_split(rest if "|" in rest else rest.replace(" | ", "|"))
        if parsed is None:
            if "|" not in rest:
                parts = rest.split(None, 1)
                if len(parts) < 2:
                    return text_for(storage, scope_id, "invalid_split")
                amount_cents = parse_amount(parts[0])
                if amount_cents is None:
                    return text_for(storage, scope_id, "invalid_amount")
                return _quick_add_expense(storage, scope_id, sender, amount_cents, parts[1].strip(), language)
            return text_for(storage, scope_id, "invalid_split")
        description, fixed_shares, percent_multipliers = parsed
        if fixed_shares is not None:
            members = []
            custom: dict[str, int] = {}
            for name, share_cents in fixed_shares.items():
                row = storage.find_member_by_name(scope_id, name)
                if row is None:
                    return text_for(storage, scope_id, "member_not_found", name=name)
                members.append(row["sender"])
                custom[row["sender"]] = share_cents
            amount_cents = sum(custom.values())
            return _quick_add_expense(
                storage,
                scope_id,
                sender,
                amount_cents,
                description,
                language,
                custom_shares=custom,
                split_members=members,
            )

        all_members = [row["sender"] for row in storage.list_members(scope_id)]
        sender_multipliers: dict[str, float] = {}
        for name, multiplier in (percent_multipliers or {}).items():
            row = storage.find_member_by_name(scope_id, name)
            if row is None:
                return text_for(storage, scope_id, "member_not_found", name=name)
            sender_multipliers[row["sender"]] = multiplier
        amount_cents = parse_amount(rest.split("|", 1)[0].split(None, 1)[0])
        if amount_cents is None:
            return text_for(storage, scope_id, "invalid_amount")
        return _quick_add_expense(
            storage,
            scope_id,
            sender,
            amount_cents,
            description,
            language,
            split_members=all_members,
            multipliers=sender_multipliers,
        )

    if command_lowered.startswith("expenses") or command_lowered.startswith("ausgaben"):
        parts = command_text.split()
        limit = 15
        if len(parts) > 1 and parts[1].isdigit():
            limit = int(parts[1])
        return _format_expenses(storage, scope_id, language, limit=limit)

    if command_lowered.startswith("expense ") or command_lowered.startswith("ausgabe "):
        parts = command_text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            return text_for(storage, scope_id, "usage_expense")
        return _format_expense_detail(storage, scope_id, int(parts[1]), language)

    if command_lowered.startswith("delete ") or command_lowered.startswith("löschen ") or command_lowered.startswith("loeschen "):
        parts = command_text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            return text_for(storage, scope_id, "usage_delete")
        expense_id = int(parts[1])
        if storage.delete_expense(scope_id, expense_id):
            return text_for(storage, scope_id, "deleted", id=expense_id)
        return text_for(storage, scope_id, "expense_not_found", id=expense_id)

    if command_lowered.startswith("settle ") or command_lowered.startswith("begleichen "):
        prefix = "settle " if command_lowered.startswith("settle ") else "begleichen "
        rest = command_text[len(prefix):].strip()
        parts = rest.split(None, 2)
        if not parts:
            return text_for(storage, scope_id, "settle_usage")
        row = storage.find_member_by_name(scope_id, parts[0])
        if row is None:
            return text_for(storage, scope_id, "member_not_found", name=parts[0])
        to_sender = row["sender"]
        if to_sender == sender:
            return text_for(storage, scope_id, "settle_nothing", name=row["display_name"])
        owed = storage.balance_between(scope_id, sender, to_sender)
        if owed <= 0:
            return text_for(storage, scope_id, "settle_nothing", name=row["display_name"])
        amount_cents = owed
        note = ""
        if len(parts) > 1 and parse_amount(parts[1]) is not None:
            amount_cents = parse_amount(parts[1]) or owed
            if len(parts) > 2:
                note = f" ({parts[2]})"
        elif len(parts) > 1:
            note = f" ({' '.join(parts[1:])})"
        amount_cents = min(amount_cents, owed)
        currency = storage.get_currency(scope_id)
        settlement_id = storage.add_settlement(scope_id, sender, to_sender, amount_cents, currency, sender, note=note.strip(" ()"))
        return _with_usage_tip(
            storage,
            scope_id,
            sender,
            language,
            "settle",
            text_for(
                storage,
                scope_id,
                "settle_done",
                from_name=storage.display_name(scope_id, sender),
                to_name=row["display_name"],
                amount=format_money(amount_cents, currency, language),
                note=note,
            ),
        )

    if command_lowered.startswith("settlements") or command_lowered.startswith("zahlungen"):
        rows = storage.list_settlements(scope_id)
        if not rows:
            return text_for(storage, scope_id, "settlements_empty")
        currency = storage.get_currency(scope_id)
        lines = [text_for(storage, scope_id, "settlements_header")]
        for row in rows:
            note = f" — {row['note']}" if row["note"] else ""
            lines.append(
                text_for(
                    storage,
                    scope_id,
                    "settlements_line",
                    id=row["id"],
                    from_name=storage.display_name(scope_id, row["from_sender"]),
                    to_name=storage.display_name(scope_id, row["to_sender"]),
                    amount=format_money(row["amount_cents"], row["currency"] or currency, language),
                    note=note,
                    date=row["created_at"],
                )
            )
        return "\n".join(lines)

    if admin_seen:
        admin_lower = admin_text.lower()
        if admin_lower.startswith("remove member ") or admin_lower.startswith("mitglied entfernen "):
            for prefix in ("remove member ", "mitglied entfernen "):
                if admin_lower.startswith(prefix):
                    name = admin_text[len(prefix):].strip()
                    break
            row = storage.find_member_by_name(scope_id, name)
            if row is None:
                return text_for(storage, scope_id, "member_not_found", name=name)
            storage.remove_member(scope_id, row["sender"])
            return text_for(storage, scope_id, "member_removed", name=row["display_name"])
        return text_for(storage, scope_id, "admin_only")

    return text_for(storage, scope_id, "unknown", help=text_for(storage, scope_id, "help"))
