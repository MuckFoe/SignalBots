from __future__ import annotations

import os
import queue
import threading
import time
from typing import Dict, Optional

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from bot_registry import runtime_bot_id
from commands import format_reminder, format_vacation_event, handle_command, text_for
from signal_client import SignalClient
from storage import Storage


load_dotenv()

app = Flask(__name__)

SIGNAL_BOT_NUMBER = os.getenv("SIGNAL_BOT_NUMBER", "").strip()
SIGNAL_API_URL = os.getenv("SIGNAL_API_URL", "http://localhost:8080").strip()
DATABASE_PATH = os.getenv("DATABASE_PATH", "chores.db").strip()

if not SIGNAL_BOT_NUMBER:
    raise RuntimeError("SIGNAL_BOT_NUMBER is required in environment variables.")

storage = Storage(DATABASE_PATH)
signal = SignalClient(SIGNAL_API_URL, SIGNAL_BOT_NUMBER)
outbound_messages: queue.Queue[Dict[str, str]] = queue.Queue()


def _queue_signal_reply(group_id: Optional[str], recipient: str, message: str) -> None:
    target_type = "group" if group_id else "dm"
    outbound_messages.put(
        {
            "target_type": target_type,
            "target": group_id or recipient,
            "message": message,
        }
    )


def _run_signal_send_loop() -> None:
    while True:
        item = outbound_messages.get()
        try:
            if item["target_type"] == "group":
                signal.send_group_message(item["target"], item["message"])
            else:
                signal.send_message(item["target"], item["message"])
            app.logger.info("Sent Signal reply to %s.", item["target_type"])
        except Exception as exc:
            app.logger.exception("Failed sending Signal reply: %s", exc)
        finally:
            outbound_messages.task_done()


def _run_reminder_loop() -> None:
    while True:
        try:
            for event in storage.process_vacation_transitions():
                scope_id = event["scope_id"]
                message = format_vacation_event(storage, event)
                if scope_id.startswith("group:"):
                    group_id = scope_id.replace("group:", "", 1)
                    _queue_signal_reply(group_id, "", message)
                else:
                    for number in storage.list_contacts():
                        _queue_signal_reply(None, number, message)
            due_rows = storage.due_reminders()
            contacts = storage.list_contacts()
            for row in due_rows:
                scope_id = row["scope_id"]
                if storage.is_reminders_paused(scope_id):
                    continue
                local_now = storage.now_local(scope_id)
                current_minutes = local_now.hour * 60 + local_now.minute
                if storage.is_quiet_time(scope_id, current_minutes):
                    continue
                reminder_text = format_reminder(
                    storage,
                    scope_id,
                    row["name"],
                    requires_confirmation=row["requires_confirmation"] == 1,
                )
                if scope_id.startswith("group:"):
                    group_id = scope_id.replace("group:", "", 1)
                    _queue_signal_reply(group_id, "", reminder_text)
                else:
                    for number in contacts:
                        _queue_signal_reply(None, number, reminder_text)
                storage.mark_reminder_sent(row["id"])
            for group_id in storage.list_groups():
                scope_id = f"group:{group_id}"
                if storage.is_reminders_paused(scope_id):
                    continue
                if storage.auth_reminder_due(scope_id):
                    local_now = storage.now_local(scope_id)
                    current_minutes = local_now.hour * 60 + local_now.minute
                    if not storage.is_quiet_time(scope_id, current_minutes):
                        _queue_signal_reply(group_id, "", text_for(storage, scope_id, "auth_reminder"))
                        storage.mark_auth_reminder_sent(scope_id)
        except Exception as exc:
            app.logger.exception("Reminder loop error: %s", exc)
        time.sleep(60)


@app.get("/health")
def health() -> tuple[dict, int]:
    return {"status": "ok", "service": "chore-bot"}, 200


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
            message,
            sender=sender,
            scope_id=scope_id,
            group_id=group_id,
        )
    except Exception as exc:
        app.logger.exception("Failed handling chore command: %s", exc)
        reply = text_for(storage, scope_id, "unexpected_error")

    if isinstance(reply, dict):
        return {"status": "processed", **reply}, 200
    return {"status": "processed", "reply": reply}, 200


if __name__ == "__main__":
    host = os.getenv("BOT_HOST", "0.0.0.0")
    port = int(os.getenv("BOT_PORT", "5000"))
    send_thread = threading.Thread(target=_run_signal_send_loop, daemon=True)
    reminder_thread = threading.Thread(target=_run_reminder_loop, daemon=True)
    send_thread.start()
    reminder_thread.start()
    app.run(host=host, port=port)
