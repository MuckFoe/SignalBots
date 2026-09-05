from __future__ import annotations

import json
import re
from datetime import date, datetime

import requests

from bot_registry import load_bot_registry, runtime_bot_id
from drive_time import format_drive_time
from poller import Poller
from scrape_types import ScrapeResult
from scrapers import ScraperRegistry
from storage import Storage
from chart_parse import parse_chart_command, parse_history_chart
from dialogue_utils import STALE_STEP, append_usage_tip, mobile_blocks, parse_stale_response, stale_prompt_text
from stats_charts import listing_history_chart, listing_price_chart, overview_chart_kinds
from utils import (
    format_availability,
    format_date,
    format_money,
    hostname,
    normalize_url,
    nights_between,
    parse_date,
)

SUPPORTED_LANGUAGES = {"en", "de"}

USAGE_TIPS = {
    "en": {
        "overview": "Add a listing with: add <url>",
        "add": "Quick add: add <url> 2025-07-01 2025-07-08 4",
        "poll": "Set drive time with: drive from <city>",
        "history": "See all listings with: overview",
    },
    "de": {
        "overview": "Objekt hinzufügen mit: hinzufügen <url>",
        "add": "Schnell: hinzufügen <url> 2025-07-01 2025-07-08 4",
        "poll": "Fahrzeit setzen mit: fahrt von <Stadt>",
        "history": "Alle Objekte mit: übersicht",
    },
}

TEXT = {
    "en": {
        "help": (
            "🏠 Rental Tracker commands:\n\n"
            "- ❓ help\n"
            "- 🏠 overview (aliases: list, status, liste)\n"
            "- ➕ add\n"
            "- ➕ add <url>\n"
            "- ➕ add <url> YYYY-MM-DD YYYY-MM-DD [guests]\n"
            "- 🗑️ remove <label>\n"
            "- 🕐 history <label>\n"
            "- 🌐 websites\n"
            "- 🌐 add website <hostname>\n"
            "- 🚗 drive from <city>\n"
            "- 🔍 poll (aliases: check, prüfen)\n"
            "- 📊 stats\n"
            "- 📈 overview chart / stats chart\n"
            "🔧 Admin options: admin help"
        ),
        "setup_choose_language": (
            "👋 Welcome / Willkommen. Choose this group's language:\n"
            "- language en\n"
            "- sprache deutsch"
        ),
        "setup_choose_bot": "Which bot should manage this group?\n{options}\nReply with: bot <id>",
        "setup_bot_set": "✅ This group now uses: {name} (bot {bot_id}).",
        "setup_complete": "🎉 Setup complete. Quick start: overview · add <url>",
        "current_language": "Current language: English. Change with: admin language de",
        "setup_bot_invalid": "Unknown bot. Reply with: bot <id>",
        "overview_header": "🏠 Rental overview:",
        "overview_empty": "🏠 No rentals tracked yet. Start with: add",
        "overview_line": (
            "{idx}. {label}\n"
            "   - site: {host}\n"
            "   - stay: {check_in} to {check_out} ({nights} nights, {guests} guests)\n"
            "   - availability: {availability}\n"
            "   - night price: {night_price}\n"
            "   - total price: {total_price}\n"
            "   - cleaning fee: {cleaning_fee}\n"
            "   - location: {location}\n"
            "   - drive from {origin}: {drive}\n"
            "   - bedrooms/baths: {bedrooms}/{bathrooms}\n"
            "   - rating: {rating}\n"
            "   - last check: {checked}\n"
            "   - last change: {changed}"
        ),
        "add_url": "Send the rental page URL, or cancel.",
        "add_label": "What should this listing be called?\nSuggested: {suggested}\nReply with a label, or cancel.",
        "add_check_in": "Check-in date for price checks (YYYY-MM-DD), or cancel.",
        "add_check_out": "Check-out date (YYYY-MM-DD), or cancel.",
        "add_guests": "How many guests? Reply with a number, or cancel.",
        "add_confirm": (
            "Add '{label}'?\n"
            "- {url}\n"
            "- {check_in} to {check_out}, {guests} guests\n"
            "- site: {host} ({adapter})\n"
            "Reply: yes, no, or cancel."
        ),
        "added": "✅ Added rental: {label}.",
        "already_exists": "A rental with label '{label}' already exists.",
        "removed": "🗑️ Removed rental: {label}.",
        "not_found": "⚠️ Rental '{label}' not found.",
        "cancelled": "↩️ Cancelled.",
        "confirm_expected": "Please reply with yes, no, or cancel.",
        "invalid_url": "That does not look like a valid URL.",
        "unsupported_site": "I do not recognize this website yet. Register it with: add website <hostname>",
        "invalid_date": "Use date format YYYY-MM-DD.",
        "invalid_guests": "Guests must be a number between 1 and 30.",
        "invalid_checkout": "Check-out must be after check-in.",
        "website_added": "Registered website host: {host}",
        "website_usage": "Usage: add website <hostname>, e.g. add website casamundo.de",
        "websites_header": "Supported / registered sites:",
        "websites_line": "- {adapter}: {name}",
        "drive_set": "🚗 Drive time origin set to {name}.",
        "drive_usage": "Usage: drive from <city>, e.g. drive from Stuttgart",
        "drive_geocode_failed": "Could not find that place.",
        "poll_started": "🔍 Polling all rentals now...",
        "poll_done": "✅ Poll finished. {changed} change(s) detected.",
        "poll_no_changes": "✅ No changes detected.",
        "poll_change": (
            "📢 Change for '{label}':\n"
            "- availability: {availability}\n"
            "- night price: {night_price}\n"
            "- total price: {total_price}"
        ),
        "history_header": "🕐 History for '{label}':",
        "history_line": "{idx}. {changed_at}: avail {availability}, night {night_price}, total {total_price}",
        "history_empty": "No history for '{label}'.",
        "language_set_en": "Language set to English.",
        "language_set_de": "Language set to German.",
        "language_usage": "Usage: language en or language de",
        "admin_help": "🔧 Admin commands:\n- 🌐 admin language de\n- 🔍 admin poll",
        "admin_only": "Use admin commands with: admin <action>",
        "unexpected_error": "⚠️ Something went wrong while handling your command.",
        "unknown": "Unknown command.\n\n{help}",
        "usage_remove": "Usage: remove <label>",
        "usage_history": "Usage: history <label>",
        "user_stats_header": "📊 Your rental stats:",
        "user_stats_line": "- listings you added: {added}\n- total in this group: {total}",
        "user_stats_empty": "You have not added any listings yet. Try: add <url>",
        "chart_empty": "📈 Not enough data for a chart yet.",
        "chart_unknown": "📈 Unknown chart type.",
        "chart_suggest_overview": "💡 Also available:\n• overview chart night\n• history <label> chart",
        "chart_suggest_night": "💡 Also available:\n• overview chart\n• history <label> chart",
        "chart_suggest_history": "💡 Also available:\n• overview chart\n• overview chart night",
    },
    "de": {
        "help": (
            "🏠 Befehle des Miet-Trackers:\n\n"
            "- ❓ hilfe\n"
            "- 🏠 übersicht (auch: liste, status)\n"
            "- ➕ hinzufügen / track\n"
            "- ➕ hinzufügen <url>\n"
            "- ➕ hinzufügen <url> YYYY-MM-DD YYYY-MM-DD [Gäste]\n"
            "- 🗑️ entfernen <Name>\n"
            "- 🕐 verlauf <Name>\n"
            "- 🌐 webseiten\n"
            "- 🌐 webseite hinzufügen <hostname>\n"
            "- 🚗 fahrt von <Stadt>\n"
            "- 🔍 prüfen (auch: check, poll)\n"
            "- 📊 statistik\n"
            "- 📈 übersicht diagramm / statistik diagramm\n"
            "🔧 Admin-Optionen: admin hilfe"
        ),
        "setup_choose_language": (
            "👋 Welcome / Willkommen. Wähle die Sprache dieser Gruppe:\n"
            "- language en\n"
            "- sprache deutsch"
        ),
        "setup_choose_bot": "Welcher Bot soll diese Gruppe verwalten?\n{options}\nAntworte mit: bot <id>",
        "setup_bot_set": "✅ Diese Gruppe nutzt jetzt: {name} (bot {bot_id}).",
        "setup_complete": "🎉 Setup fertig. Schnellstart: übersicht · hinzufügen <url>",
        "current_language": "Aktuelle Sprache: Deutsch. Ändern mit: admin sprache englisch",
        "setup_bot_invalid": "Unbekannter Bot. Antworte mit: bot <id>",
        "overview_header": "🏠 Miet-Übersicht:",
        "overview_empty": "🏠 Noch keine Mietobjekte. Starte mit: hinzufügen",
        "overview_line": (
            "{idx}. {label}\n"
            "   - Seite: {host}\n"
            "   - Zeitraum: {check_in} bis {check_out} ({nights} Nächte, {guests} Gäste)\n"
            "   - Verfügbarkeit: {availability}\n"
            "   - Preis pro Nacht: {night_price}\n"
            "   - Gesamtpreis: {total_price}\n"
            "   - Reinigungsgebühr: {cleaning_fee}\n"
            "   - Ort: {location}\n"
            "   - Fahrt ab {origin}: {drive}\n"
            "   - Schlafzimmer/Bäder: {bedrooms}/{bathrooms}\n"
            "   - Bewertung: {rating}\n"
            "   - Zuletzt geprüft: {checked}\n"
            "   - Zuletzt geändert: {changed}"
        ),
        "add_url": "Schick die URL der Mietseite oder abbrechen.",
        "add_label": "Wie soll das Objekt heißen?\nVorschlag: {suggested}\nAntworte mit einem Namen oder abbrechen.",
        "add_check_in": "Check-in für Preisabfragen (YYYY-MM-DD) oder abbrechen.",
        "add_check_out": "Check-out (YYYY-MM-DD) oder abbrechen.",
        "add_guests": "Wie viele Gäste? Antworte mit einer Zahl oder abbrechen.",
        "add_confirm": (
            "'{label}' hinzufügen?\n"
            "- {url}\n"
            "- {check_in} bis {check_out}, {guests} Gäste\n"
            "- Seite: {host} ({adapter})\n"
            "Antworte: ja, nein oder abbrechen."
        ),
        "added": "✅ Mietobjekt hinzugefügt: {label}.",
        "already_exists": "Ein Objekt mit dem Namen '{label}' existiert bereits.",
        "removed": "🗑️ Mietobjekt entfernt: {label}.",
        "not_found": "⚠️ Mietobjekt '{label}' nicht gefunden.",
        "cancelled": "↩️ Abgebrochen.",
        "confirm_expected": "Bitte antworte mit ja, nein oder abbrechen.",
        "invalid_url": "Das sieht nicht nach einer gültigen URL aus.",
        "unsupported_site": "Diese Webseite kenne ich noch nicht. Registriere sie mit: webseite hinzufügen <hostname>",
        "invalid_date": "Nutze das Datumsformat YYYY-MM-DD.",
        "invalid_guests": "Gäste müssen eine Zahl zwischen 1 und 30 sein.",
        "invalid_checkout": "Check-out muss nach Check-in liegen.",
        "website_added": "Webseite registriert: {host}",
        "website_usage": "So geht's: webseite hinzufügen <hostname>, z.B. webseite hinzufügen casamundo.de",
        "websites_header": "Unterstützte / registrierte Seiten:",
        "websites_line": "- {adapter}: {name}",
        "drive_set": "🚗 Fahrtzeit-Berechnung ab {name} gesetzt.",
        "drive_usage": "So geht's: fahrt von <Stadt>, z.B. fahrt von Stuttgart",
        "drive_geocode_failed": "Ort nicht gefunden.",
        "poll_started": "🔍 Prüfe alle Mietobjekte...",
        "poll_done": "✅ Prüfung fertig. {changed} Änderung(en).",
        "poll_no_changes": "✅ Keine Änderungen festgestellt.",
        "poll_change": (
            "📢 Änderung bei '{label}':\n"
            "- Verfügbarkeit: {availability}\n"
            "- Preis pro Nacht: {night_price}\n"
            "- Gesamtpreis: {total_price}"
        ),
        "history_header": "🕐 Verlauf für '{label}':",
        "history_line": "{idx}. {changed_at}: Verfügbarkeit {availability}, Nacht {night_price}, gesamt {total_price}",
        "history_empty": "Kein Verlauf für '{label}'.",
        "language_set_en": "Sprache auf Englisch gesetzt.",
        "language_set_de": "Sprache auf Deutsch gesetzt.",
        "language_usage": "So geht's: language en oder language de",
        "admin_help": "🔧 Admin-Befehle:\n- 🌐 admin sprache deutsch\n- 🔍 admin prüfen",
        "admin_only": "Admin-Befehle nutzt du mit: admin <Aktion>",
        "unexpected_error": "⚠️ Beim Verarbeiten des Befehls ist etwas schiefgelaufen.",
        "unknown": "Unbekannter Befehl.\n\n{help}",
        "usage_remove": "So geht's: entfernen <Name>",
        "usage_history": "So geht's: verlauf <Name>",
        "user_stats_header": "📊 Deine Miet-Statistik:",
        "user_stats_line": "- von dir hinzugefügt: {added}\n- gesamt in der Gruppe: {total}",
        "user_stats_empty": "Du hast noch keine Objekte hinzugefügt. Probiere: hinzufügen <url>",
        "chart_empty": "📈 Noch nicht genug Daten für ein Diagramm.",
        "chart_unknown": "📈 Unbekannter Diagramm-Typ.",
        "chart_suggest_overview": "💡 Auch verfügbar:\n• übersicht diagramm nacht\n• verlauf <Name> diagramm",
        "chart_suggest_night": "💡 Auch verfügbar:\n• übersicht diagramm\n• verlauf <Name> diagramm",
        "chart_suggest_history": "💡 Auch verfügbar:\n• übersicht diagramm\n• übersicht diagramm nacht",
    },
}


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
    if stats["added_count"] == 0:
        return _text(language, "user_stats_empty")
    return _text(language, "user_stats_header") + "\n\n" + _text(
        language,
        "user_stats_line",
        added=stats["added_count"],
        total=stats["group_total"],
    )


def _chart_reply(reply: str, attachments: list[str]) -> dict:
    return {"reply": reply, "attachments": attachments}


def _listing_dicts(rows) -> list[dict]:
    return [dict(row) for row in rows]


def _rental_overview_chart(storage: Storage, scope_id: str, language: str, kind: str | None) -> str | dict:
    rows = _listing_dicts(storage.list_listings(scope_id))
    if not rows:
        return _text(language, "overview_empty")

    normalized = (kind or "total").lower()
    if kind and normalized not in overview_chart_kinds(language):
        return _text(language, "chart_unknown")

    caption = _text(language, "overview_header")
    chart = listing_price_chart(kind, rows, language)
    if normalized in {"night", "nacht", "nights", "naechte", "nächte"}:
        hint = _text(language, "chart_suggest_night")
    else:
        hint = _text(language, "chart_suggest_overview")

    if not chart:
        return mobile_blocks(caption, _text(language, "chart_empty"))
    return _chart_reply(mobile_blocks(caption, hint), [chart])


def _rental_history_chart(storage: Storage, scope_id: str, language: str, label: str) -> str | dict:
    rows = storage.listing_history(scope_id, label, limit=20)
    if not rows:
        return _text(language, "history_empty", label=label)
    caption = _text(language, "history_header", label=label)
    chart = listing_history_chart(label, rows, language)
    hint = _text(language, "chart_suggest_history")
    if not chart:
        return mobile_blocks(caption, _text(language, "chart_empty"))
    return _chart_reply(mobile_blocks(caption, hint), [chart])


def _listing_step_prompt(
    storage: Storage,
    registry: ScraperRegistry,
    scope_id: str,
    sender: str,
    language: str,
) -> str:
    pending = storage.get_pending_listing_add(scope_id, sender)
    if pending is None:
        return _text(language, "cancelled")
    step = pending["step"]
    if step == "url":
        return _text(language, "add_url")
    if step == "label":
        return _text(language, "add_label", suggested=pending["label"] or hostname(pending["url"]))
    if step == "check_in":
        return _text(language, "add_check_in")
    if step == "check_out":
        return _text(language, "add_check_out")
    if step == "guests":
        return _text(language, "add_guests")
    if step == "confirm":
        return _listing_confirm_text(
            registry,
            language,
            pending["url"],
            pending["label"],
            pending["check_in"],
            pending["check_out"],
            pending["guests"],
            pending["adapter_id"],
        )
    return _text(language, "add_url")


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
    if cleaned in {"no", "n", "nein", "cancel", "abbrechen", "stop"}:
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
    lines = []
    for idx, (bot_id, name) in enumerate(bots.items(), start=1):
        lines.append(f"{idx}. {name} (bot {bot_id})")
    return "\n".join(lines)


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
    return [
        _text(language, "setup_bot_set", name=bots[bot_id], bot_id=bot_id),
        _text(language, "setup_complete"),
    ]


def geocode_place(name: str) -> tuple[float, float] | None:
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": name, "format": "json", "limit": 1},
            headers={"User-Agent": "HouseRentalTracker/1.0"},
            timeout=20,
        )
        response.raise_for_status()
        results = response.json()
        if not results:
            return None
        return float(results[0]["lat"]), float(results[0]["lon"])
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def _looks_like_url(text: str) -> bool:
    cleaned = text.strip().lower()
    return cleaned.startswith("http://") or cleaned.startswith("https://") or "." in cleaned and " " not in cleaned


def _format_rating(rating: float | None, review_count: int | None, language: str) -> str:
    if rating is None:
        return "n/a" if language == "en" else "k.A."
    if review_count is None:
        return f"{rating:.1f}"
    return f"{rating:.1f} ({review_count})"


def _format_optional_int(value: int | None, language: str) -> str:
    if value is None:
        return "n/a" if language == "en" else "k.A."
    return str(value)


def _format_overview(storage: Storage, scope_id: str, language: str) -> str:
    rows = storage.list_listings(scope_id)
    if not rows:
        return _text(language, "overview_empty")
    origin_name, _, _ = storage.get_drive_origin(scope_id)
    blocks = [_text(language, "overview_header")]
    for idx, row in enumerate(rows, start=1):
        check_in = parse_date(row["check_in"])
        check_out = parse_date(row["check_out"])
        nights = nights_between(check_in, check_out) if check_in and check_out else 0
        blocks.append(
            _text(
                language,
                "overview_line",
                idx=idx,
                label=row["label"],
                host=hostname(row["url"]),
                check_in=row["check_in"],
                check_out=row["check_out"],
                nights=nights,
                guests=row["guests"],
                availability=format_availability(
                    None if row["available"] is None else bool(row["available"]),
                    language,
                ),
                night_price=format_money(row["price_per_night"], row["currency"], language),
                total_price=format_money(row["total_price"], row["currency"], language),
                cleaning_fee=format_money(row["cleaning_fee"], row["currency"], language),
                location=row["location_name"] or row["title"] or ("n/a" if language == "en" else "k.A."),
                origin=origin_name,
                drive=format_drive_time(row["drive_minutes"], row["drive_km"], language),
                bedrooms=_format_optional_int(row["bedrooms"], language),
                bathrooms=str(row["bathrooms"]) if row["bathrooms"] is not None else ("n/a" if language == "en" else "k.A."),
                rating=_format_rating(row["rating"], row["review_count"], language),
                checked=row["last_checked_at"] or ("never" if language == "en" else "nie"),
                changed=row["last_changed_at"] or ("never" if language == "en" else "nie"),
            )
        )
    return mobile_blocks(*blocks)


def format_change_message(storage: Storage, scope_id: str, label: str, result: ScrapeResult) -> str:
    language = storage.get_language(scope_id)
    return _text(
        language,
        "poll_change",
        label=label,
        availability=format_availability(result.available, language),
        night_price=format_money(result.price_per_night, result.currency, language),
        total_price=format_money(result.total_price, result.currency, language),
    )


def _listing_confirm_text(
    registry: ScraperRegistry,
    language: str,
    url: str,
    label: str,
    check_in: str,
    check_out: str,
    guests: int,
    adapter_id: str,
) -> str:
    adapter_name = adapter_id
    for candidate_id, display_name in registry.list_adapters():
        if candidate_id == adapter_id:
            adapter_name = display_name
            break
    return _text(
        language,
        "add_confirm",
        label=label,
        url=url,
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        host=hostname(url),
        adapter=adapter_name,
    )


def _extract_add_payload(command_text: str, command_lowered: str) -> str | None:
    exact_commands = {"add", "hinzufügen", "hinzufuegen", "neu", "track"}
    if command_lowered in exact_commands:
        return ""
    for prefix in ("add ", "hinzufügen ", "hinzufuegen ", "neu ", "track "):
        if command_lowered.startswith(prefix):
            return command_text[len(prefix) :].strip()
    return None


def _try_start_quick_add(
    storage: Storage,
    registry: ScraperRegistry,
    sender: str,
    scope_id: str,
    language: str,
    payload: str,
) -> str:
    parts = payload.split()
    if not parts or not _looks_like_url(parts[0]):
        return _text(language, "invalid_url")
    url = normalize_url(parts[0])
    adapter = registry.detect(url)
    if adapter is None:
        return _text(language, "unsupported_site")
    suggested = hostname(url)[:80]
    storage.start_pending_listing_add(scope_id, sender)
    if len(parts) == 1:
        storage.update_pending_listing_add(
            scope_id,
            sender,
            "label",
            url=url,
            adapter_id=adapter.adapter_id,
            label=suggested,
        )
        return _text(language, "add_label", suggested=suggested)
    if len(parts) < 3:
        storage.clear_pending_listing_add(scope_id, sender)
        return _text(language, "invalid_date")
    check_in = parse_date(parts[1])
    check_out = parse_date(parts[2])
    guests = 2
    if len(parts) >= 4:
        if not parts[3].isdigit():
            storage.clear_pending_listing_add(scope_id, sender)
            return _text(language, "invalid_guests")
        guests = int(parts[3])
    if check_in is None or check_out is None:
        storage.clear_pending_listing_add(scope_id, sender)
        return _text(language, "invalid_date")
    if check_out <= check_in:
        storage.clear_pending_listing_add(scope_id, sender)
        return _text(language, "invalid_checkout")
    if not 1 <= guests <= 30:
        storage.clear_pending_listing_add(scope_id, sender)
        return _text(language, "invalid_guests")
    check_in_text = format_date(check_in)
    check_out_text = format_date(check_out)
    storage.update_pending_listing_add(
        scope_id,
        sender,
        "confirm",
        url=url,
        label=suggested,
        check_in=check_in_text,
        check_out=check_out_text,
        guests=guests,
        adapter_id=adapter.adapter_id,
    )
    return _listing_confirm_text(
        registry,
        language,
        url,
        suggested,
        check_in_text,
        check_out_text,
        guests,
        adapter.adapter_id,
    )


def _handle_pending_add(
    storage: Storage,
    registry: ScraperRegistry,
    poller: Poller,
    text: str,
    sender: str,
    scope_id: str,
    language: str,
) -> str | None:
    pending = storage.get_pending_listing_add(scope_id, sender)
    if pending is None:
        return None
    if pending["step"] == STALE_STEP:
        action = parse_stale_response(text)
        if action == "discard":
            storage.clear_pending_listing_add(scope_id, sender)
            return _text(language, "cancelled")
        if action == "continue":
            storage.restore_dialogue_step("pending_listing_adds", scope_id, sender)
            return _listing_step_prompt(storage, registry, scope_id, sender, language)
        return stale_prompt_text(language, "rental add")
    if _is_cancel(text):
        storage.clear_pending_listing_add(scope_id, sender)
        return _text(language, "cancelled")

    step = pending["step"]
    if step == "url":
        if not _looks_like_url(text):
            return _text(language, "invalid_url")
        url = normalize_url(text)
        adapter = registry.detect(url)
        if adapter is None:
            return _text(language, "unsupported_site")
        suggested = hostname(url)[:80]
        storage.update_pending_listing_add(
            scope_id,
            sender,
            "label",
            url=url,
            adapter_id=adapter.adapter_id,
            label=suggested,
        )
        return _text(language, "add_label", suggested=suggested)

    if step == "label":
        label = text.strip()
        if not label:
            return _text(language, "add_label", suggested=pending["label"] or hostname(pending["url"]))
        storage.update_pending_listing_add(
            scope_id,
            sender,
            "check_in",
            url=pending["url"],
            label=label,
            adapter_id=pending["adapter_id"],
        )
        return _text(language, "add_check_in")

    if step == "check_in":
        check_in = parse_date(text)
        if check_in is None:
            return _text(language, "invalid_date")
        storage.update_pending_listing_add(
            scope_id,
            sender,
            "check_out",
            url=pending["url"],
            label=pending["label"],
            check_in=format_date(check_in),
            adapter_id=pending["adapter_id"],
        )
        return _text(language, "add_check_out")

    if step == "check_out":
        check_out = parse_date(text)
        check_in = parse_date(pending["check_in"])
        if check_out is None or check_in is None:
            return _text(language, "invalid_date")
        if check_out <= check_in:
            return _text(language, "invalid_checkout")
        storage.update_pending_listing_add(
            scope_id,
            sender,
            "guests",
            url=pending["url"],
            label=pending["label"],
            check_in=pending["check_in"],
            check_out=format_date(check_out),
            adapter_id=pending["adapter_id"],
        )
        return _text(language, "add_guests")

    if step == "guests":
        if not text.strip().isdigit():
            return _text(language, "invalid_guests")
        guests = int(text.strip())
        if not 1 <= guests <= 30:
            return _text(language, "invalid_guests")
        storage.update_pending_listing_add(
            scope_id,
            sender,
            "confirm",
            url=pending["url"],
            label=pending["label"],
            check_in=pending["check_in"],
            check_out=pending["check_out"],
            guests=guests,
            adapter_id=pending["adapter_id"],
        )
        adapter_name = pending["adapter_id"]
        for adapter_id, display_name in registry.list_adapters():
            if adapter_id == pending["adapter_id"]:
                adapter_name = display_name
                break
        return _text(
            language,
            "add_confirm",
            label=pending["label"],
            url=pending["url"],
            check_in=pending["check_in"],
            check_out=pending["check_out"],
            guests=guests,
            host=hostname(pending["url"]),
            adapter=adapter_name,
        )

    if step == "confirm":
        answer = _confirmation_answer(text)
        if answer is None:
            return _text(language, "confirm_expected")
        storage.clear_pending_listing_add(scope_id, sender)
        if not answer:
            return _text(language, "cancelled")
        check_in = parse_date(pending["check_in"])
        check_out = parse_date(pending["check_out"])
        if check_in is None or check_out is None:
            return _text(language, "invalid_date")
        result, drive_minutes, drive_km = poller.initial_scrape(
            scope_id,
            pending["url"],
            pending["adapter_id"],
            check_in,
            check_out,
            pending["guests"],
        )
        if not storage.add_listing(
            scope_id,
            pending["label"],
            pending["url"],
            pending["adapter_id"],
            check_in,
            check_out,
            pending["guests"],
            result,
            drive_minutes,
            drive_km,
            added_by=sender,
        ):
            return _text(language, "already_exists", label=pending["label"])
        return _text(language, "added", label=pending["label"])

    storage.clear_pending_listing_add(scope_id, sender)
    return _text(language, "cancelled")


def handle_command(
    storage: Storage,
    registry: ScraperRegistry,
    poller: Poller,
    message_text: str,
    sender: str,
    scope_id: str,
    group_id: str | None = None,
) -> str | list[str]:
    text = message_text.strip()
    language = storage.get_language(scope_id)
    is_group = group_id is not None
    setup_complete = storage.is_group_ready(scope_id) if is_group else True

    if is_group and storage.has_admins(scope_id) and not storage.has_bot(scope_id):
        storage.set_bot_id(scope_id, runtime_bot_id())

    if not text:
        return _text(language, "help")

    if is_group and not setup_complete:
        language_request = _language_from_command(text)
        if not storage.has_language(scope_id):
            if language_request in SUPPORTED_LANGUAGES:
                storage.set_language(scope_id, language_request)
                storage.add_admin(scope_id, sender)
                bots = load_bot_registry()
                if len(bots) == 1:
                    bot_id = next(iter(bots))
                    storage.set_bot_id(scope_id, bot_id)
                    return [
                        _text(language_request, f"language_set_{language_request}"),
                        _text(language_request, "setup_bot_set", name=bots[bot_id], bot_id=bot_id),
                        _text(language_request, "setup_complete"),
                    ]
                return [
                    _text(language_request, f"language_set_{language_request}"),
                    _text(language_request, "setup_choose_bot", options=_format_bot_options(language_request)),
                ]
            return _text(_help_language(storage, scope_id, text, language), "setup_choose_language")

        if not storage.has_bot(scope_id):
            bot_choice = _parse_bot_command(text)
            if bot_choice == "":
                return _text(language, "setup_choose_bot", options=_format_bot_options(language))
            if bot_choice == "invalid":
                return _text(language, "setup_bot_invalid")
            if bot_choice:
                return _complete_bot_setup(storage, scope_id, sender, language, bot_choice)
            return _text(language, "setup_choose_bot", options=_format_bot_options(language))

        storage.add_admin(scope_id, sender)
        return _text(language, "setup_complete")

    admin_seen, admin_text = _admin_action(text) if is_group else (False, "")
    if admin_seen and not admin_text:
        return _text(language, "admin_help")
    command_text = admin_text if admin_text else text
    command_lowered = command_text.lower()

    language_request = _language_from_command(command_text)
    if language_request == "":
        return _text(language, "current_language")
    if language_request in SUPPORTED_LANGUAGES:
        if is_group and not admin_text:
            return _text(language, "admin_only")
        storage.set_language(scope_id, language_request)
        return _text(language_request, f"language_set_{language_request}")
    if language_request == "invalid":
        return _text(language, "language_usage")

    if admin_seen and command_lowered in {"help", "hilfe", "admin", "admin help", "adminhilfe"}:
        return _text(_help_language(storage, scope_id, text, language), "admin_help")

    if command_lowered in {"help", "hilfe", "?"}:
        return _text(_help_language(storage, scope_id, text, language), "help")

    if _is_cancel(command_text):
        storage.clear_pending_listing_add(scope_id, sender)
        return _text(language, "cancelled")

    pending_reply = _handle_pending_add(storage, registry, poller, command_text, sender, scope_id, language)
    if pending_reply is not None:
        return pending_reply

    if command_lowered in {"overview", "übersicht", "liste", "list", "status"}:
        return _with_usage_tip(
            storage,
            scope_id,
            sender,
            language,
            "overview",
            _format_overview(storage, scope_id, language),
        )

    if command_lowered in {"stats", "statistik", "my stats", "meine statistik"}:
        return _format_user_stats(storage, scope_id, sender, language)

    history_label, wants_history_chart = parse_history_chart(command_lowered)
    if wants_history_chart and history_label:
        return _rental_history_chart(storage, scope_id, language, history_label)

    chart_base, wants_chart, chart_kind = parse_chart_command(command_lowered)
    if wants_chart:
        if chart_base in {"overview", "übersicht", "liste", "list", "status"}:
            return _rental_overview_chart(storage, scope_id, language, chart_kind)
        if chart_base in {"stats", "statistik", "my stats", "meine statistik"}:
            return _rental_overview_chart(storage, scope_id, language, chart_kind)

    add_payload = _extract_add_payload(command_text, command_lowered)
    if add_payload is not None:
        if not add_payload:
            storage.start_pending_listing_add(scope_id, sender)
            return _with_usage_tip(storage, scope_id, sender, language, "add", _text(language, "add_url"))
        return _try_start_quick_add(storage, registry, sender, scope_id, language, add_payload)

    if command_lowered.startswith("remove ") or command_lowered.startswith("entfernen "):
        label = command_text.split(" ", 1)[1].strip()
        if not label:
            return _text(language, "usage_remove")
        if storage.delete_listing(scope_id, label):
            return _text(language, "removed", label=label)
        return _text(language, "not_found", label=label)

    if command_lowered.startswith("history ") or command_lowered.startswith("verlauf "):
        label = command_text.split(" ", 1)[1].strip()
        if not label:
            return _text(language, "usage_history")
        rows = storage.listing_history(scope_id, label)
        if not rows:
            return _text(language, "history_empty", label=label)
        lines = [_text(language, "history_header", label=label)]
        for idx, row in enumerate(rows, start=1):
            snapshot = json.loads(row["snapshot_json"])
            lines.append(
                _text(
                    language,
                    "history_line",
                    idx=idx,
                    changed_at=row["changed_at"],
                    availability=format_availability(snapshot.get("available"), language),
                    night_price=format_money(snapshot.get("price_per_night"), snapshot.get("currency", "EUR"), language),
                    total_price=format_money(snapshot.get("total_price"), snapshot.get("currency", "EUR"), language),
                )
            )
        return "\n".join(lines)

    if command_lowered in {"websites", "webseiten", "sites"}:
        lines = [_text(language, "websites_header")]
        for adapter_id, display_name in registry.list_adapters():
            lines.append(_text(language, "websites_line", adapter=adapter_id, name=display_name))
        for host_row in storage.list_custom_hosts(scope_id):
            lines.append(_text(language, "websites_line", adapter=host_row["adapter_id"], name=host_row["host_pattern"]))
        return "\n".join(lines)

    website_payload = command_text
    for prefix in ("add website ", "website add ", "webseite hinzufügen ", "webseite hinzufuegen "):
        if command_lowered.startswith(prefix):
            website_payload = command_text[len(prefix) :].strip()
            break
    else:
        website_payload = ""

    if website_payload:
        host = website_payload.lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").split("/")[0]
        if not host or " " in host:
            return _text(language, "website_usage")
        adapter_id = registry.register_host(host)
        storage.add_custom_host(scope_id, host, adapter_id)
        return _text(language, "website_added", host=host)

    drive_payload = ""
    for prefix in ("drive from ", "fahrt von ", "origin "):
        if command_lowered.startswith(prefix):
            drive_payload = command_text[len(prefix) :].strip()
            break
    if drive_payload:
        coords = geocode_place(drive_payload)
        if coords is None:
            return _text(language, "drive_geocode_failed")
        storage.set_drive_origin(scope_id, drive_payload, coords[0], coords[1])
        return _text(language, "drive_set", name=drive_payload)

    if command_lowered in {"poll", "check", "prüfen", "jetzt prüfen"} or (admin_seen and command_lowered in {"poll", "prüfen"}):
        outcomes = poller.poll_all()
        change_messages = []
        for row, did_change, result in outcomes:
            if did_change and row["scope_id"] == scope_id:
                change_messages.append(format_change_message(storage, scope_id, row["label"], result))
        if change_messages:
            return change_messages
        return _with_usage_tip(storage, scope_id, sender, language, "poll", _text(language, "poll_no_changes"))

    return _text(language, "unknown", help=_text(language, "help"))
