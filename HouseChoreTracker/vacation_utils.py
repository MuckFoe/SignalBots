from __future__ import annotations

import re
from datetime import timedelta

from schedule_utils import UNIT_ALIASES


def _normalize_unit(raw: str) -> str | None:
    return UNIT_ALIASES.get(raw.strip().lower())


def parse_duration(text: str) -> timedelta | None:
    cleaned = text.strip().lower()
    if not cleaned:
        return None
    cleaned = cleaned.replace("für ", "for ").replace("fuer ", "for ")
    if cleaned.startswith("for "):
        cleaned = cleaned[4:].strip()
    parts = cleaned.split()
    if len(parts) == 1:
        match = re.fullmatch(r"(\d+)([a-zäöü]+)", parts[0])
        if match:
            value, unit = int(match.group(1)), match.group(2)
        else:
            return None
    elif len(parts) == 2 and parts[0].isdigit():
        value, unit = int(parts[0]), parts[1]
    else:
        return None
    normalized = _normalize_unit(unit)
    if normalized is None:
        return None
    if normalized == "minutes":
        return timedelta(minutes=value)
    if normalized == "hours":
        return timedelta(hours=value)
    if normalized == "days":
        return timedelta(days=value)
    if normalized == "weeks":
        return timedelta(weeks=value)
    if normalized == "months":
        return timedelta(days=value * 30)
    if normalized == "years":
        return timedelta(days=value * 365)
    return None


def parse_vacation_plan(text: str) -> dict | None:
    cleaned = text.strip().lower()
    if not cleaned:
        return None
    cleaned = (
        cleaned.replace("für ", "for ")
        .replace("fuer ", "for ")
        .replace("tagen", "days")
        .replace("tage", "days")
        .replace("tag", "day")
        .replace("wochen", "weeks")
        .replace("woche", "week")
        .replace("jetzt", "now")
    )
    if cleaned.startswith("now "):
        duration = parse_duration(cleaned[4:].strip())
        if duration is None:
            return None
        return {"delay": timedelta(0), "duration": duration}
    if cleaned.startswith("in "):
        match = re.match(r"in\s+(.+?)\s+for\s+(.+)$", cleaned)
        if match is None:
            duration = parse_duration(cleaned[3:].strip())
            if duration is None:
                return None
            return {"delay": timedelta(0), "duration": duration}
        delay = parse_duration(match.group(1).strip())
        duration = parse_duration(match.group(2).strip())
        if delay is None or duration is None:
            return None
        return {"delay": delay, "duration": duration}
    duration = parse_duration(cleaned)
    if duration is None:
        return None
    return {"delay": timedelta(0), "duration": duration}


def format_duration(delta: timedelta, language: str) -> str:
    total_days = max(1, int(round(delta.total_seconds() / 86400)))
    if language == "de":
        return f"{total_days} Tag{'e' if total_days != 1 else ''}"
    return f"{total_days} day{'s' if total_days != 1 else ''}"
