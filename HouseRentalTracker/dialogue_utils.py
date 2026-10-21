from __future__ import annotations

import os
from datetime import datetime, timedelta

STALE_STEP = "__stale__"
STALE_DIALOGUE_HOURS = float(os.getenv("PENDING_STALE_HOURS", "1"))
DIALOGUE_MAX_HOURS = float(os.getenv("PENDING_MAX_HOURS", "24"))
USAGE_TIP_LIMIT = 2


def dialogue_ttl_minutes() -> int:
    return max(15, int(DIALOGUE_MAX_HOURS * 60))


def _parse_db_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    if "T" in cleaned:
        try:
            return datetime.fromisoformat(cleaned.replace("Z", ""))
        except ValueError:
            return None
    return None


def is_dialogue_stale(last_activity_at: str | None) -> bool:
    parsed = _parse_db_datetime(last_activity_at)
    if parsed is None:
        return False
    return datetime.utcnow() - parsed > timedelta(hours=STALE_DIALOGUE_HOURS)


def parse_stale_response(text: str) -> str | None:
    cleaned = text.strip().lower()
    if cleaned in {"yes", "y", "ja", "j", "continue", "fortfahren", "weiter", "resume"}:
        return "continue"
    if cleaned in {"no", "n", "nein", "cancel", "abbrechen", "discard", "verwerfen", "stop", "drop"}:
        return "discard"
    return None


FLOW_LABELS = {
    "en": {
        "name": "setting your name",
        "edit": "editing a chore",
        "add chore": "adding a chore",
        "vacation task": "adding a task before leaving",
        "vacation": "planning a vacation",
        "rental add": "adding a rental",
        "join": "joining",
        "expense": "adding an expense",
    },
    "de": {
        "name": "Name festlegen",
        "edit": "Aufgabe bearbeiten",
        "add chore": "Aufgabe anlegen",
        "vacation task": "Vorbereitungsaufgabe anlegen",
        "vacation": "Urlaub planen",
        "rental add": "Unterkunft hinzufügen",
        "join": "Beitreten",
        "expense": "Ausgabe erfassen",
    },
}


def stale_prompt_text(language: str, flow_name: str) -> str:
    hours = int(STALE_DIALOGUE_HOURS)
    if language == "de":
        label = FLOW_LABELS["de"].get(flow_name, flow_name)
        age = "1 Stunde" if hours == 1 else f"{hours} Stunden"
        return (
            f"⏳ Du hast eine angefangene Eingabe ({label}), die älter als {age} ist.\n"
            "Weitermachen? Antworte: ja oder abbrechen"
        )
    label = FLOW_LABELS["en"].get(flow_name, flow_name)
    age = "1 hour" if hours == 1 else f"{hours} hours"
    return (
        f"⏳ You started {label} more than {age} ago and did not finish.\n"
        "Continue? Reply: yes or cancel"
    )


def with_emoji(kind: str, text: str) -> str:
    """Prefix user-facing text with a fitting emoji."""
    prefixes = {
        "success": "✅",
        "done": "✅",
        "added": "➕",
        "cancelled": "↩️",
        "welcome": "👋",
        "stats": "📊",
        "list": "📋",
        "money": "💸",
        "balance": "⚖️",
        "settle": "🤝",
        "join": "👋",
        "delete": "🗑️",
        "undo": "↩️",
        "reminder": "🔔",
        "rental": "🏠",
        "poll": "🔍",
        "warn": "⚠️",
        "question": "❓",
        "stale": "⏳",
        "name": "👤",
        "setup": "🎉",
        "invite": "📨",
        "history": "🕐",
        "tip": "💡",
    }
    prefix = prefixes.get(kind)
    if not prefix or not text:
        return text
    return f"{prefix} {text}"


def append_usage_tip(reply: str, tip: str | None, usage_count: int) -> str:
    if usage_count > USAGE_TIP_LIMIT or not tip or not reply:
        return reply
    return f"{reply}\n\n💡 {tip}"


def mobile_blocks(*parts: str) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip())
