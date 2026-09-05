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





def mobile_blocks(*parts: str) -> str:

    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def parse_stale_response(text: str) -> str | None:
    cleaned = text.strip().lower()
    if cleaned in {"yes", "y", "ja", "j", "continue", "fortfahren", "weiter", "resume"}:
        return "continue"
    if cleaned in {"no", "n", "nein", "cancel", "abbrechen", "discard", "verwerfen", "stop", "drop"}:
        return "discard"
    return None


def stale_prompt_text(language: str, flow_name: str) -> str:
    hours = int(STALE_DIALOGUE_HOURS)
    if language == "de":
        return (
            f"⏳ Unfertige {flow_name}-Eingabe (älter als {hours} Std.).\n"
            "Fortfahren? Antworte: ja oder abbrechen"
        )
    return (
        f"⏳ Unfinished {flow_name} entry (older than {hours}h).\n"
        "Continue? Reply: yes or cancel"
    )

