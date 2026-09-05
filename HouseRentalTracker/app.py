from __future__ import annotations

import os
import queue
import threading
import time
from datetime import datetime
from typing import Dict, Optional

from dotenv import load_dotenv
from flask import Flask, request

from bot_registry import runtime_bot_id
from commands import format_change_message, handle_command, text_for
from poller import Poller, load_custom_hosts
from scrapers import ScraperRegistry
from signal_client import SignalClient
from storage import Storage


load_dotenv()

app = Flask(__name__)

SIGNAL_BOT_NUMBER = os.getenv("SIGNAL_BOT_NUMBER", "").strip()
SIGNAL_API_URL = os.getenv("SIGNAL_API_URL", "http://localhost:8080").strip()
DATABASE_PATH = os.getenv("DATABASE_PATH", "rentals.db").strip()
POLL_TIMES = os.getenv("POLL_TIMES", "08:00,20:00").strip()

if not SIGNAL_BOT_NUMBER:
    raise RuntimeError("SIGNAL_BOT_NUMBER is required in environment variables.")

storage = Storage(DATABASE_PATH)
registry = ScraperRegistry()
load_custom_hosts(storage, registry)
poller = Poller(storage, registry)
signal = SignalClient(SIGNAL_API_URL, SIGNAL_BOT_NUMBER)
outbound_messages: queue.Queue[Dict[str, str]] = queue.Queue()


def _parse_poll_times(raw: str) -> list[tuple[int, int]]:
    times: list[tuple[int, int]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        hour_text, minute_text = part.split(":", 1)
        try:
            hour = int(hour_text)
            minute = int(minute_text)
        except ValueError:
            continue
        if 0 <= hour < 24 and 0 <= minute < 60:
            times.append((hour, minute))
    return times or [(8, 0), (20, 0)]


POLL_SCHEDULE = _parse_poll_times(POLL_TIMES)


def _queue_signal_reply(group_id: Optional[str], recipient: str, message: str) -> None:
    target_type = "group" if group_id else "dm"
    outbound_messages.put(
        {
            "target_type": target_type,
            "target": group_id or recipient,
            "message": message,
        }
    )


def _notify_scope(scope_id: str, message: str) -> None:
    if scope_id.startswith("group:"):
        group_id = scope_id.replace("group:", "", 1)
        _queue_signal_reply(group_id, "", message)
        return
    if scope_id.startswith("dm:"):
        number = scope_id.replace("dm:", "", 1)
        _queue_signal_reply(None, number, message)


def _run_signal_send_loop() -> None:
    while True:
        item = outbound_messages.get()
        try:
            if item["target_type"] == "group":
                signal.send_group_message(item["target"], item["message"])
            else:
                signal.send_message(item["target"], item["message"])
        except Exception as exc:
            app.logger.exception("Failed sending Signal reply: %s", exc)
        finally:
            outbound_messages.task_done()


def _poll_slot_key(now: datetime) -> str:
    return now.strftime("%Y-%m-%d %H:%M")


def _should_poll_now(now: datetime) -> bool:
    current = (now.hour, now.minute)
    if current not in POLL_SCHEDULE:
        return False
    last_key = storage.get_poll_state().get("last_scheduled_poll_key", "")
    return last_key != _poll_slot_key(now)


def _run_poll(pass_scheduled: bool = False) -> None:
    now = datetime.now()
    if pass_scheduled and not _should_poll_now(now):
        return
    if pass_scheduled:
        storage.set_poll_state("last_scheduled_poll_key", _poll_slot_key(now))

    for row, changed, result in poller.poll_all():
        if changed:
            _notify_scope(row["scope_id"], format_change_message(storage, row["scope_id"], row["label"], result))


def _run_poll_loop() -> None:
    while True:
        try:
            _run_poll(pass_scheduled=True)
        except Exception as exc:
            app.logger.exception("Rental poll loop error: %s", exc)
        time.sleep(60)


@app.get("/health")
def health() -> tuple[dict, int]:
    return {"status": "ok", "service": "rental-bot"}, 200


@app.post("/internal/scope")
def internal_scope() -> tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    scope_id = body.get("scope_id", "").strip()
    if not scope_id:
        return {"error": "scope_id required"}, 400
    return {
        "scope_id": scope_id,
        "has_admins": storage.has_admins(scope_id),
        "is_ready": storage.is_group_ready(scope_id),
    }, 200


@app.post("/internal/handle")
def internal_handle() -> tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    scope_id = body.get("scope_id", "").strip()
    sender = body.get("sender", "").strip()
    message = body.get("message", "")
    group_id = body.get("group_id")
    if not scope_id or not sender:
        return {"error": "scope_id and sender required"}, 400

    storage.register_contact(sender)
    if group_id:
        storage.register_group(group_id)

    if group_id and storage.has_bot(scope_id):
        if storage.get_bot_id(scope_id) != runtime_bot_id():
            return {"status": "ignored_wrong_bot", "reply": ""}, 200

    try:
        reply = handle_command(
            storage,
            registry,
            poller,
            message,
            sender=sender,
            scope_id=scope_id,
            group_id=group_id,
        )
    except Exception as exc:
        app.logger.exception("Failed handling rental command: %s", exc)
        reply = text_for(storage, scope_id, "unexpected_error")

    if isinstance(reply, dict):
        return {"status": "processed", **reply}, 200
    return {"status": "processed", "reply": reply}, 200


if __name__ == "__main__":
    host = os.getenv("BOT_HOST", "0.0.0.0")
    port = int(os.getenv("BOT_PORT", "5001"))
    send_thread = threading.Thread(target=_run_signal_send_loop, daemon=True)
    poll_thread = threading.Thread(target=_run_poll_loop, daemon=True)
    send_thread.start()
    poll_thread.start()
    app.run(host=host, port=port)
