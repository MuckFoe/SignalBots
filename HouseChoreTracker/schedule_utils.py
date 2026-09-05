from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_TIMEZONE = "Europe/Berlin"

TIMEZONE_ALIASES = {
    "berlin": "Europe/Berlin",
    "europe/berlin": "Europe/Berlin",
    "europa/berlin": "Europe/Berlin",
    "utc": "UTC",
    "gmt": "UTC",
    "london": "Europe/London",
    "europe/london": "Europe/London",
    "paris": "Europe/Paris",
    "europe/paris": "Europe/Paris",
    "vienna": "Europe/Vienna",
    "europe/vienna": "Europe/Vienna",
    "zurich": "Europe/Zurich",
    "europe/zurich": "Europe/Zurich",
    "amsterdam": "Europe/Amsterdam",
    "europe/amsterdam": "Europe/Amsterdam",
    "new york": "America/New_York",
    "newyork": "America/New_York",
    "america/new_york": "America/New_York",
}


WEEKDAYS = {
    "monday": 0,
    "mon": 0,
    "montag": 0,
    "dienstag": 1,
    "tuesday": 1,
    "tue": 1,
    "wednesday": 2,
    "wed": 2,
    "mittwoch": 2,
    "thursday": 3,
    "thu": 3,
    "donnerstag": 3,
    "friday": 4,
    "fri": 4,
    "freitag": 4,
    "saturday": 5,
    "sat": 5,
    "samstag": 5,
    "sonnabend": 5,
    "sunday": 6,
    "sun": 6,
    "sonntag": 6,
}

WEEKDAY_NAMES = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "de": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
}

UNIT_ALIASES = {
    "m": "minutes",
    "min": "minutes",
    "mins": "minutes",
    "minute": "minutes",
    "minutes": "minutes",
    "minute(n)": "minutes",
    "minuten": "minutes",
    "h": "hours",
    "hr": "hours",
    "hrs": "hours",
    "hour": "hours",
    "hours": "hours",
    "stunde": "hours",
    "stunden": "hours",
    "d": "days",
    "day": "days",
    "days": "days",
    "tag": "days",
    "tage": "days",
    "w": "weeks",
    "week": "weeks",
    "weeks": "weeks",
    "weekly": "weeks",
    "woche": "weeks",
    "wochen": "weeks",
    "woechentlich": "weeks",
    "wöchentlich": "weeks",
    "mo": "months",
    "mon": "months",
    "month": "months",
    "months": "months",
    "monat": "months",
    "monate": "months",
    "y": "years",
    "yr": "years",
    "year": "years",
    "years": "years",
    "jahr": "years",
    "jahre": "years",
}

MINUTE_FACTORS = {
    "minutes": 1,
    "hours": 60,
    "days": 24 * 60,
    "weeks": 7 * 24 * 60,
}

ONCE_ALIASES = {
    "once",
    "one-time",
    "onetime",
    "one time",
    "einmal",
    "einmalig",
}

ONCE_PREFIXES = (
    "once ",
    "one-time ",
    "onetime ",
    "one time ",
    "einmal ",
    "einmalig ",
)

ONE_SHOT_STATS_KEY = "__one_shot__"


def one_shot_stats_label(language: str) -> str:
    return "one-time chores" if language == "en" else "Einmalaufgaben"


def is_one_shot_schedule(schedule: dict | None) -> bool:
    return bool(schedule) and schedule.get("type") == "once"


def _split_once_prefix(cleaned: str) -> tuple[bool, str]:
    if cleaned in ONCE_ALIASES:
        return True, ""
    for prefix in ONCE_PREFIXES:
        if cleaned.startswith(prefix):
            return True, cleaned[len(prefix) :].strip()
    return False, cleaned


def parse_schedule(raw: str) -> dict | None:
    cleaned = raw.strip().lower()
    if not cleaned:
        return None
    every_prefix = False
    if cleaned.startswith("every "):
        cleaned = cleaned[6:].strip()
        every_prefix = True
    if cleaned.startswith("alle "):
        cleaned = cleaned[5:].strip()
    for prefix in ("jeden ", "jede ", "jedes "):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            every_prefix = True
            break
    if cleaned in {
        "none",
        "no",
        "no reminder",
        "no schedule",
        "without reminder",
        "without schedule",
        "open",
        "open task",
        "task",
        "todo",
        "anytime",
        "disabled",
        "keine",
        "keine erinnerung",
        "kein plan",
        "kein zeitplan",
        "ohne erinnerung",
        "ohne plan",
        "ohne zeitplan",
        "offen",
        "offene aufgabe",
        "aufgabe offen",
        "jederzeit",
        "aus",
    }:
        return {"type": "none"}

    once, rest = _split_once_prefix(cleaned)
    if once:
        return _parse_once_schedule(rest)

    if cleaned in WEEKDAYS:
        return {"type": "weekday", "weekday": WEEKDAYS[cleaned]}

    parts = cleaned.split()
    if len(parts) == 1:
        if parts[0] in {"weekly", "woechentlich", "wöchentlich"}:
            value, unit = 1, parts[0]
        elif every_prefix and parts[0] in UNIT_ALIASES:
            value, unit = 1, parts[0]
        else:
            value, unit = _split_compact_interval(parts[0])
    elif len(parts) == 2 and parts[0].isdigit():
        value, unit = int(parts[0]), parts[1]
    else:
        return None

    normalized_unit = UNIT_ALIASES.get(unit)
    if value <= 0 or normalized_unit is None:
        return None
    return {"type": "interval", "value": value, "unit": normalized_unit}


def _parse_once_schedule(rest: str) -> dict | None:
    if not rest or rest in {"today", "heute"}:
        return {"type": "once", "when": "today"}
    if rest in {"tomorrow", "morgen"}:
        return {"type": "once", "when": "tomorrow"}
    if rest in WEEKDAYS:
        return {"type": "once", "weekday": WEEKDAYS[rest]}
    interval = parse_schedule(rest)
    if interval is None:
        return None
    if interval["type"] == "interval":
        return {"type": "once", "value": interval["value"], "unit": interval["unit"]}
    if interval["type"] == "weekday":
        return {"type": "once", "weekday": interval["weekday"]}
    if interval["type"] == "once":
        return interval
    return None


def schedule_to_storage(schedule: dict) -> str:
    if schedule["type"] == "none":
        return "none"
    if schedule["type"] == "once":
        if "weekday" in schedule:
            return f"once:weekday:{schedule['weekday']}"
        if schedule.get("unit"):
            return f"once:interval:{schedule['value']}:{schedule['unit']}"
        return f"once:{schedule.get('when') or 'today'}"
    if schedule["type"] == "weekday":
        return f"weekday:{schedule['weekday']}"
    return f"interval:{schedule['value']}:{schedule['unit']}"


def schedule_from_storage(raw: str, fallback_minutes: int = 0) -> dict | None:
    if raw:
        if raw == "none":
            return {"type": "none"}
        parts = raw.split(":")
        if parts and parts[0] == "once":
            if len(parts) == 1 or (len(parts) == 2 and parts[1] in {"today", "tomorrow"}):
                when = parts[1] if len(parts) == 2 else "today"
                return {"type": "once", "when": when}
            if len(parts) == 3 and parts[1] == "weekday":
                return {"type": "once", "weekday": int(parts[2])}
            if len(parts) == 4 and parts[1] == "interval":
                return {"type": "once", "value": int(parts[2]), "unit": parts[3]}
        if len(parts) == 2 and parts[0] == "weekday":
            return {"type": "weekday", "weekday": int(parts[1])}
        if len(parts) == 3 and parts[0] == "interval":
            return {"type": "interval", "value": int(parts[1]), "unit": parts[2]}
    if fallback_minutes > 0:
        return {"type": "interval", "value": fallback_minutes, "unit": "minutes"}
    return None


def schedule_to_minutes(schedule: dict) -> int:
    if schedule["type"] != "interval":
        return 0
    factor = MINUTE_FACTORS.get(schedule["unit"])
    if factor is None:
        return 0
    return schedule["value"] * factor


def _once_when_label(schedule: dict, language: str) -> str:
    if "weekday" in schedule:
        names = WEEKDAY_NAMES.get(language, WEEKDAY_NAMES["en"])
        return names[schedule["weekday"]]
    if schedule.get("unit"):
        interval = {"type": "interval", "value": schedule["value"], "unit": schedule["unit"]}
        delay = humanize_schedule(interval, language)
        return f"after {delay}" if language == "en" else f"nach {delay}"
    if schedule.get("when") == "tomorrow":
        return "tomorrow" if language == "en" else "morgen"
    return "today" if language == "en" else "heute"


def humanize_schedule(schedule: dict | None, language: str) -> str:
    if schedule is None:
        return "disabled" if language == "en" else "deaktiviert"
    if schedule["type"] == "none":
        return "no reminder" if language == "en" else "keine Erinnerung"
    if schedule["type"] == "once":
        when = _once_when_label(schedule, language)
        return f"once {when}" if language == "en" else f"einmal {when}"
    if schedule["type"] == "weekday":
        names = WEEKDAY_NAMES.get(language, WEEKDAY_NAMES["en"])
        return names[schedule["weekday"]]

    value = schedule["value"]
    unit = schedule["unit"]
    if language == "de":
        labels = {
            "minutes": ("Minute", "Minuten"),
            "hours": ("Stunde", "Stunden"),
            "days": ("Tag", "Tage"),
            "weeks": ("Woche", "Wochen"),
            "months": ("Monat", "Monate"),
            "years": ("Jahr", "Jahre"),
        }
    else:
        labels = {
            "minutes": ("minute", "minutes"),
            "hours": ("hour", "hours"),
            "days": ("day", "days"),
            "weeks": ("week", "weeks"),
            "months": ("month", "months"),
            "years": ("year", "years"),
        }
    singular, plural = labels[unit]
    return f"{value} {singular if value == 1 else plural}"


def format_schedule_frequency(schedule: dict | None, language: str) -> str:
    if schedule is None:
        return "disabled" if language == "en" else "deaktiviert"
    if schedule["type"] == "none":
        return "no schedule" if language == "en" else "kein Plan"
    if schedule["type"] == "once":
        return humanize_schedule(schedule, language)
    if schedule["type"] == "weekday":
        weekday = WEEKDAY_NAMES.get(language, WEEKDAY_NAMES["en"])[schedule["weekday"]]
        return f"every {weekday}" if language == "en" else f"jeden {weekday}"

    value = schedule["value"]
    unit = schedule["unit"]
    if language == "de":
        if value == 1:
            singular = {
                "minutes": "jede Minute",
                "hours": "jede Stunde",
                "days": "jeden Tag",
                "weeks": "jede Woche",
                "months": "jeden Monat",
                "years": "jedes Jahr",
            }
            return singular[unit]
        return f"alle {humanize_schedule(schedule, language)}"
    if value == 1:
        singular = {
            "minutes": "every minute",
            "hours": "every hour",
            "days": "every day",
            "weeks": "every week",
            "months": "every month",
            "years": "every year",
        }
        return singular[unit]
    return f"every {humanize_schedule(schedule, language)}"


def format_schedule_delay(schedule: dict | None, language: str) -> str:
    if schedule is None:
        return "disabled" if language == "en" else "deaktiviert"
    if schedule["type"] == "none":
        return "disabled" if language == "en" else "deaktiviert"
    if schedule["type"] in {"weekday", "once"}:
        return format_schedule_frequency(schedule, language)
    if language == "de":
        value = schedule["value"]
        unit = schedule["unit"]
        labels = {
            "minutes": ("Minute", "Minuten"),
            "hours": ("Stunde", "Stunden"),
            "days": ("Tag", "Tagen"),
            "weeks": ("Woche", "Wochen"),
            "months": ("Monat", "Monaten"),
            "years": ("Jahr", "Jahren"),
        }
        singular, plural = labels[unit]
        return f"nach {value} {singular if value == 1 else plural}"
    return f"after {humanize_schedule(schedule, language)}"


def format_time_of_day(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


DEFAULT_REMINDER_AT_MINUTES = 8 * 60


def reminder_time_applies(schedule: dict) -> bool:
    if schedule["type"] == "weekday":
        return True
    if schedule["type"] == "once":
        return not schedule.get("unit")
    if schedule["type"] == "interval":
        return schedule["unit"] in {"days", "weeks", "months", "years"}
    return False


def effective_reminder_at_minutes(
    schedule: dict | None,
    reminder_at_minutes: int | None,
    default_minutes: int | None = None,
) -> int | None:
    if reminder_at_minutes is not None:
        return reminder_at_minutes
    if schedule is None or not reminder_time_applies(schedule):
        return None
    if default_minutes is None:
        return DEFAULT_REMINDER_AT_MINUTES
    return default_minutes


def parse_reminder_time_answer(raw: str) -> int | None | str:
    cleaned = raw.strip().lower()
    if cleaned in {
        "anytime",
        "any time",
        "any",
        "none",
        "no",
        "jederzeit",
        "egal",
        "ohne",
        "keine",
        "keine zeit",
    }:
        return None
    token = raw.strip().replace(".", ":")
    if ":" in token:
        hour_text, minute_text = token.split(":", 1)
    elif token.isdigit() and len(token) in {1, 2}:
        hour_text, minute_text = token, "0"
    elif token.isdigit() and len(token) == 4:
        hour_text, minute_text = token[:2], token[2:]
    else:
        return "invalid"
    if not hour_text.isdigit() or not minute_text.isdigit():
        return "invalid"
    hours = int(hour_text)
    minutes = int(minute_text)
    if hours == 24 and minutes == 0:
        return 0
    if not 0 <= hours < 24 or not 0 <= minutes < 60:
        return "invalid"
    return hours * 60 + minutes


def format_reminder_time_label(reminder_at_minutes: int | None, language: str) -> str:
    if reminder_at_minutes is None:
        return "any time" if language == "en" else "jederzeit"
    time_text = format_time_of_day(reminder_at_minutes)
    if language == "de":
        return f"um {time_text}"
    return f"at {time_text}"


def normalize_timezone_name(raw: str) -> str | None:
    cleaned = raw.strip().replace("\\", "/")
    if not cleaned:
        return None
    alias = TIMEZONE_ALIASES.get(cleaned.lower())
    candidate = alias or cleaned
    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        return None
    return candidate


def get_zoneinfo(tz_name: str | None = None) -> ZoneInfo:
    name = normalize_timezone_name(tz_name or DEFAULT_TIMEZONE) or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_TIMEZONE)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_utc_naive(value: datetime) -> datetime:
    return as_utc(value).replace(tzinfo=None)


def to_local(value: datetime, tz_name: str | None = None) -> datetime:
    return as_utc(value).astimezone(get_zoneinfo(tz_name))


def format_local_timestamp(value: str | datetime, tz_name: str | None = None) -> str:
    if isinstance(value, str):
        value = parse_db_datetime(value)
    local = to_local(value, tz_name)
    return f"{local:%Y-%m-%d %H:%M}"


def local_now(tz_name: str | None = None) -> datetime:
    return datetime.now(tz=get_zoneinfo(tz_name))


def _with_reminder_time(value: datetime, reminder_at_minutes: int) -> datetime:
    hour = reminder_at_minutes // 60
    minute = reminder_at_minutes % 60
    return value.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _next_once_due(
    base_local: datetime,
    schedule: dict,
    reminder_at_minutes: int | None,
    zone: ZoneInfo,
) -> datetime:
    base_naive = base_local.replace(tzinfo=None)
    if schedule.get("unit"):
        due_naive = _next_due_at_plain(
            base_naive,
            {"type": "interval", "value": schedule["value"], "unit": schedule["unit"]},
        )
        return to_utc_naive(due_naive.replace(tzinfo=zone))

    minutes = effective_reminder_at_minutes(schedule, reminder_at_minutes) or DEFAULT_REMINDER_AT_MINUTES
    target = _with_reminder_time(base_naive, minutes)
    if schedule.get("when") == "tomorrow":
        target = target + timedelta(days=1)
    elif "weekday" in schedule:
        days_ahead = (schedule["weekday"] - base_naive.weekday()) % 7
        target = target + timedelta(days=days_ahead)
    return to_utc_naive(target.replace(tzinfo=zone))


def _next_due_at_plain(base_time: datetime, schedule: dict) -> datetime:
    if schedule["type"] == "none":
        raise ValueError("Chores without reminders do not become due.")
    if schedule["type"] == "once":
        raise ValueError("One-time due dates are computed in local time.")
    if schedule["type"] == "weekday":
        days_ahead = (schedule["weekday"] - base_time.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return base_time + timedelta(days=days_ahead)

    value = schedule["value"]
    unit = schedule["unit"]
    if unit == "minutes":
        return base_time + timedelta(minutes=value)
    if unit == "hours":
        return base_time + timedelta(hours=value)
    if unit == "days":
        return base_time + timedelta(days=value)
    if unit == "weeks":
        return base_time + timedelta(weeks=value)
    if unit == "months":
        return _add_months(base_time, value)
    if unit == "years":
        return _add_months(base_time, value * 12)
    raise ValueError(f"Unsupported schedule unit: {unit}")


def next_due_at(
    base_time: datetime,
    schedule: dict,
    reminder_at_minutes: int | None = None,
    tz_name: str | None = None,
) -> datetime:
    """Return next due time as naive UTC (matches SQLite datetime('now'))."""
    zone = get_zoneinfo(tz_name)
    base_local = as_utc(base_time).astimezone(zone)
    base_local_naive = base_local.replace(tzinfo=None)
    reminder_at_minutes = effective_reminder_at_minutes(schedule, reminder_at_minutes)
    if schedule["type"] == "once":
        return _next_once_due(base_local, schedule, reminder_at_minutes, zone)

    if reminder_at_minutes is None or not reminder_time_applies(schedule):
        due_local = _next_due_at_plain(base_local_naive, schedule).replace(tzinfo=zone)
        return to_utc_naive(due_local)

    candidate = base_local_naive
    for _ in range(1000):
        raw = _next_due_at_plain(candidate, schedule)
        due_local = _with_reminder_time(raw, reminder_at_minutes).replace(tzinfo=zone)
        if due_local > base_local:
            return to_utc_naive(due_local)
        candidate = raw
    raise ValueError("Could not compute next due date with reminder time.")


def parse_db_datetime(raw: str) -> datetime:
    return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")


def _split_compact_interval(token: str) -> tuple[int, str]:
    index = 0
    while index < len(token) and token[index].isdigit():
        index += 1
    if index == 0:
        return 0, token
    return int(token[:index]), token[index:]


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)
