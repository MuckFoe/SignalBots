"""Free text -> intent + slots via a local LLM (OpenAI-compatible API, e.g. Ollama).

The LLM only translates. It never touches the database: commands.py validates
every slot with the bot's own parsers and decides what happens.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)

KINDS = ("action", "unclear", "chatter")
INTENTS = (
    "add_chore",
    "add_once",
    "mark_done",
    "undo_done",
    "edit_chore",
    "delete_chore",
    "rename_chore",
    "set_name",
    "vacation",
    "show",
)
EDIT_FIELDS = ("name", "schedule", "remind_time", "confirmation", "repeat")
SHOW_TARGETS = ("list", "list_extended", "history", "my_stats", "group_stats", "help", "vacation_status")
SLOT_NAMES = (
    "name",
    "schedule",
    "remind_time",
    "done_confirmation",
    "count_stats",
    "chore",
    "field",
    "value",
    "new_name",
    "display_name",
    "when",
    "duration",
    "what",
)
_BOOL_SLOTS = {"done_confirmation", "count_stats"}

# Enforced by the server (constrained decoding). Slots are optional: the model leaves out the ones
# it has no value for, which keeps answers short; parse_output fills them with None.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": list(KINDS)},
        "intent": {"type": ["string", "null"], "enum": [*INTENTS, None]},
        "slots": {
            "type": "object",
            "properties": {
                name: {"type": ["boolean", "null"]} if name in _BOOL_SLOTS else {"type": ["string", "null"]}
                for name in SLOT_NAMES
            },
            "additionalProperties": False,
        },
        "suggestions": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
    "required": ["kind", "intent", "slots", "suggestions", "confidence"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You translate chat messages for a household chore bot into JSON. You never chat yourself.
Users write German or English. The bot sits in group chats, so most messages are people talking
to each other - that is "chatter".

Reply with exactly one JSON object and nothing else (no markdown, no explanation):
{"kind": "action"|"unclear"|"chatter", "intent": <intent or null>, "slots": {...}, "suggestions": [...], "confidence": 0..1}

kind:
- "action": the message asks the bot to do or show something listed below.
- "unclear": the message is clearly meant for the bot, but you cannot tell what it wants.
- "chatter": anything else (people talking, jokes, thanks, emojis, questions to other people). When in doubt between
  chatter and anything else, choose chatter. A bare statement like "I cleaned the bathroom" counts as action
  mark_done only if a chore with that meaning exists.

slots: only the slots the message gives a value for; leave out everything else. Never invent values.

Intents and their slots:
- add_chore: a new recurring chore, or an open task without any date ("ohne termin", "irgendwann", "no schedule"
  -> schedule "none"). name, schedule, remind_time, done_confirmation
- add_once: a new one-time task due on a specific day. name, schedule (when it is due), remind_time, count_stats,
  done_confirmation
- mark_done: a chore was done. chore
- undo_done: take back the last "done" of a chore. chore
- edit_chore: change a setting of an existing chore. chore, field, value
- delete_chore: remove a chore. chore
- rename_chore: chore, new_name
- set_name: the sender tells the bot their own name. display_name
- vacation: the sender goes on vacation / is away. when, duration
- show: read-only. what

Slot formats (use exactly these, the bot parses them literally):
- name / new_name: a short task title from the user's own words, capitalised. Keep their words and spelling;
  only drop articles and turn "zu"/"to" phrases into the base form ("den vermieter anzurufen" -> "Vermieter anrufen",
  "to water the plants" -> "Water the plants", "Fensterputzen" stays "Fensterputzen").
- display_name: the name exactly as the sender wrote it.
- chore: must be copied exactly from the list of existing chores below. If no existing chore fits, use null.
- schedule (recurring): "every day", "every 2 days", "every week", "every 2 weeks", "every month",
  "every 3 months", "every monday" ... "every sunday", or "none" for a task without any schedule.
  A weekday schedule always means weekly; "every second Monday" becomes "every 2 weeks".
- schedule (add_once): "today", "tomorrow", "monday" ... "sunday" (the next one), or a count without
  "in": "2 days" (for "in 2 days"/"übermorgen"), "1 week".
- remind_time: 24h "HH:MM" like "08:00" or "19:30"; "anytime" if the user says the time does not matter.
  "morning"/"morgens"/"früh" = "08:00", "noon"/"mittags" = "12:00", "afternoon"/"nachmittags" = "15:00",
  "evening"/"abends" = "19:00". A time word inside a schedule ("jeden Montag früh") still sets remind_time.
- done_confirmation: true if someone else must confirm the chore was done, false if not, null if not said.
- count_stats: true/false whether a one-time task counts in the statistics, null if not said.
- field (edit_chore): one of "name", "schedule", "remind_time", "confirmation", "repeat"
  ("repeat" = how often to remind again when overdue). value: the new value in the format of that field
  ("yes"/"no" for confirmation, a recurring schedule for repeat).
- when (vacation): "now" or a duration until it starts like "3 days", "2 weeks".
- duration (vacation): like "5 days", "2 weeks".
- what (show): "list", "list_extended", "history", "my_stats", "group_stats", "help", "vacation_status".

suggestions: up to 3 bot commands that would help the user, written in the user's language, e.g.
"liste", "erledigt <Aufgabe>", "aufgabe <Name> <Zeitplan>", "hilfe" / "list", "done <chore>", "add <name> <schedule>",
"help". Empty for chatter.

confidence: how sure you are that kind and intent are right (0 to 1).

Examples (existing chores: Bad putzen, Müll rausbringen):
"bad ist sauber" -> {"kind":"action","intent":"mark_done","slots":{"chore":"Bad putzen"},"suggestions":[],"confidence":0.9}
"I took the trash out" -> {"kind":"action","intent":"mark_done","slots":{"chore":"Müll rausbringen"},"suggestions":[],"confidence":0.85}
"Erinner uns jeden Montag um 8 ans Fensterputzen, jemand muss es bestätigen" ->
  {"kind":"action","intent":"add_chore","slots":{"name":"Fensterputzen","schedule":"every monday","remind_time":"08:00","done_confirmation":true},"suggestions":[],"confidence":0.9}
"neue aufgabe staubsaugen alle 2 wochen" -> {"kind":"action","intent":"add_chore","slots":{"name":"Staubsaugen","schedule":"every 2 weeks"},"suggestions":[],"confidence":0.9}
"aufgabe fahrrad reparieren, kein termin" -> {"kind":"action","intent":"add_chore","slots":{"name":"Fahrrad reparieren","schedule":"none"},"suggestions":[],"confidence":0.9}
"remind me tomorrow evening to call the landlord" ->
  {"kind":"action","intent":"add_once","slots":{"name":"Call the landlord","schedule":"tomorrow","remind_time":"19:00"},"suggestions":[],"confidence":0.85}
"was steht noch an?" -> {"kind":"action","intent":"show","slots":{"what":"list"},"suggestions":[],"confidence":0.85}
"ich bin ab nächster woche 2 wochen im urlaub" -> {"kind":"action","intent":"vacation","slots":{"when":"1 week","duration":"2 weeks"},"suggestions":[],"confidence":0.8}
"Müll bitte nur noch dienstags" -> {"kind":"action","intent":"edit_chore","slots":{"chore":"Müll rausbringen","field":"schedule","value":"every tuesday"},"suggestions":[],"confidence":0.8}
"wer kommt heute zum essen?" -> {"kind":"chatter","intent":null,"slots":{},"suggestions":[],"confidence":0.95}
"haha 😂" -> {"kind":"chatter","intent":null,"slots":{},"suggestions":[],"confidence":0.95}
"bot, kannst du das mit dem ding machen" -> {"kind":"unclear","intent":null,"slots":{},"suggestions":["hilfe","liste"],"confidence":0.7}
"""


@dataclass
class Interpretation:
    kind: str
    intent: str | None
    slots: dict
    suggestions: list[str] = field(default_factory=list)
    confidence: float = 0.0
    raw: str = ""
    latency_ms: int = 0


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


class ModelCold(Exception):
    """The model is not loaded. Loading plus the first prompt take ~25 s, longer than the router waits."""


_local = threading.local()

# Set while messages wait for the model to load, so later messages queue behind them
# instead of racing the load with the short timeout.
warming = threading.Event()


@contextmanager
def cold_start_allowed():
    """Inside this block LLM calls wait for a cold model (LLM_COLD_TIMEOUT_SECONDS) instead of raising ModelCold."""
    _local.allow_cold = True
    try:
        yield
    finally:
        _local.allow_cold = False


class LlmClient:
    """POSTs to an OpenAI-compatible /chat/completions endpoint. Returns the message text or None.

    The server enforces RESPONSE_SCHEMA (strict json_schema). With Ollama on Apple Silicon this
    needs a build that ships xgrammar (the official one; Homebrew's answers 501 and the assist
    stays silent). Thinking is turned off: it adds ~20 s per message, and without it the intent
    eval already scores 96-100 %.
    """

    def __init__(self, base_url: str, model: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def is_loaded(self) -> bool:
        """Asks Ollama (/api/ps) whether the model is in memory. Any problem counts as loaded (normal path)."""
        import requests

        root = self.base_url.removesuffix("/v1")
        try:
            response = requests.get(f"{root}/api/ps", timeout=3)
            response.raise_for_status()
            models = response.json().get("models") or []
        except Exception as exc:
            logger.warning("LLM load check failed: %s", exc)
            return True
        return any(self.model in (item.get("name"), item.get("model")) for item in models)

    def complete(self, messages: list[dict]) -> str | None:
        timeout = self.timeout
        if getattr(_local, "allow_cold", False):
            timeout = max(timeout, _env_float("LLM_COLD_TIMEOUT_SECONDS", 120.0))
        elif warming.is_set() or not self.is_loaded():
            raise ModelCold()
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "reasoning_effort": "none",
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "interpretation", "schema": RESPONSE_SCHEMA, "strict": True},
            },
        }
        import requests  # imported here so the bot (and its tests) load without it when the LLM is off

        try:
            response = requests.post(f"{self.base_url}/chat/completions", json=payload, timeout=timeout)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as exc:  # fail open: any problem means "no LLM answer"
            logger.warning("LLM call failed: %s", exc)
            return None


_client_override: object | None = None


def set_client(client: object | None) -> None:
    """Tests inject a fake with .complete(messages) -> str | None. None restores env config."""
    global _client_override
    _client_override = client


def _allowed_scopes() -> set[str]:
    raw = os.getenv("LLM_SCOPES", "")
    return {part.strip() for part in raw.split(",") if part.strip()}


def client_for(scope_id: str) -> object | None:
    """The client to use for this chat, or None when the LLM is off for it."""
    scopes = _allowed_scopes()
    if scopes and scope_id not in scopes:
        return None
    if _client_override is not None:
        return _client_override
    if not _env_bool("LLM_ENABLED"):
        return None
    base_url = os.getenv("LLM_BASE_URL", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()
    if not base_url or not model:
        return None
    return LlmClient(base_url, model, _env_float("LLM_TIMEOUT_SECONDS", 20.0))


def group_min_confidence() -> float:
    return _env_float("LLM_GROUP_MIN_CONFIDENCE", 0.6)


def build_messages(
    text: str,
    language: str,
    chore_names: list[str],
    is_group: bool,
    dialogue: dict | None = None,
) -> list[dict]:
    chores = ", ".join(chore_names) if chore_names else "(none yet)"
    context = [
        f"Chat language setting: {'German' if language == 'de' else 'English'}.",
        f"Chat type: {'group chat' if is_group else 'direct message with the bot'}.",
        f"Existing chores: {chores}",
    ]
    if dialogue:
        context.append(
            "The sender is in the middle of a dialogue with the bot and this message answers its question. "
            "It is never chatter. Use intent "
            f"\"{dialogue['intent']}\". Already known: {json.dumps(dialogue['known'], ensure_ascii=False)}. "
            f"The bot just asked for: {dialogue['asking']}. Fill every slot the answer mentions; "
            "return kind \"unclear\" if the answer does not fit."
        )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(context) + f"\n\nMessage:\n{text}"},
    ]


def parse_output(raw: str | None) -> Interpretation | None:
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned[cleaned.find("{") :] if "{" in cleaned else cleaned
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict) or data.get("kind") not in KINDS:
        return None
    intent = data.get("intent")
    if intent not in INTENTS:
        intent = None
    if data["kind"] == "action" and intent is None:
        return None
    raw_slots = data.get("slots") if isinstance(data.get("slots"), dict) else {}
    slots: dict = {}
    for name in SLOT_NAMES:
        value = raw_slots.get(name)
        if name in _BOOL_SLOTS:
            slots[name] = value if isinstance(value, bool) else None
        elif isinstance(value, (str, int, float)) and not isinstance(value, bool) and str(value).strip():
            text_value = str(value).strip()
            slots[name] = None if text_value.lower() in {"null", "none"} and name not in {"schedule", "remind_time"} else text_value
        else:
            slots[name] = None
    suggestions = [str(item).strip() for item in data.get("suggestions") or [] if str(item).strip()]
    try:
        confidence = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    return Interpretation(
        kind=data["kind"],
        intent=intent,
        slots=slots,
        suggestions=suggestions[:3],
        confidence=max(0.0, min(1.0, confidence)),
        raw=raw,
    )


def interpret(
    client: object,
    text: str,
    language: str,
    chore_names: list[str],
    is_group: bool,
    dialogue: dict | None = None,
) -> tuple[Interpretation | None, str, int]:
    """Returns (interpretation or None, raw output, latency in ms)."""
    started = time.monotonic()
    try:
        raw = client.complete(build_messages(text, language, chore_names, is_group, dialogue))
    except ModelCold:
        raise
    except Exception as exc:
        logger.warning("LLM client raised: %s", exc)
        raw = None
    latency_ms = int((time.monotonic() - started) * 1000)
    result = parse_output(raw)
    if result is not None:
        result.latency_ms = latency_ms
    return result, raw or "", latency_ms
