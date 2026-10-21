from __future__ import annotations

import os
import queue
import threading
from typing import Dict, Optional

from dotenv import load_dotenv
from flask import Flask, request

from bot_registry import runtime_bot_id
from commands import handle_command
from signal_client import SignalClient
from storage import Storage
from whatsapp_client import WhatsAppClient, is_whatsapp_target


load_dotenv()

app = Flask(__name__)

SIGNAL_BOT_NUMBER = os.getenv("SIGNAL_BOT_NUMBER", "").strip()
SIGNAL_API_URL = os.getenv("SIGNAL_API_URL", "http://localhost:8080").strip()
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "http://whatsapp-api:3000").strip()
WHATSAPP_API_KEY = os.getenv("WHATSAPP_API_KEY", "").strip()
DATABASE_PATH = os.getenv("DATABASE_PATH", "expenses.db").strip()

if not SIGNAL_BOT_NUMBER:
    raise RuntimeError("SIGNAL_BOT_NUMBER is required in environment variables.")

storage = Storage(DATABASE_PATH)
signal = SignalClient(SIGNAL_API_URL, SIGNAL_BOT_NUMBER)
whatsapp = WhatsAppClient(WHATSAPP_API_URL, WHATSAPP_API_KEY)
outbound_messages: queue.Queue[Dict[str, str]] = queue.Queue()


def _queue_signal_reply(group_id: Optional[str], recipient: str, message: str) -> None:
    outbound_messages.put(
        {
            "target_type": "group" if group_id else "dm",
            "target": group_id or recipient,
            "message": message,
        }
    )


def _run_signal_send_loop() -> None:
    while True:
        item = outbound_messages.get()
        try:
            if is_whatsapp_target(item["target"]):
                whatsapp.send_message(item["target"], item["message"])
            elif item["target_type"] == "group":
                signal.send_group_message(item["target"], item["message"])
            else:
                signal.send_message(item["target"], item["message"])
        except Exception as exc:
            app.logger.exception("Failed sending Signal reply: %s", exc)
        finally:
            outbound_messages.task_done()


@app.get("/health")
def health() -> tuple[dict, int]:
    return {"status": "ok", "service": "expense-bot"}, 200


@app.post("/internal/scope")
def internal_scope() -> tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    scope_id = body.get("scope_id", "").strip()
    sender = body.get("sender", "").strip()
    if not scope_id:
        return {"error": "scope_id required"}, 400
    return {
        "scope_id": scope_id,
        "has_admins": storage.has_admins(scope_id),
        "is_ready": storage.is_group_ready(scope_id),
        "is_admin": bool(sender) and storage.is_admin(scope_id, sender),
        "language": storage.get_language(scope_id) if storage.has_language(scope_id) else None,
    }, 200


@app.post("/internal/migrate")
def internal_migrate() -> tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    old_scope = body.get("from_scope", "").strip()
    new_scope = body.get("to_scope", "").strip()
    sender = body.get("sender", "").strip()
    new_group_id = body.get("to_group_id")
    if not old_scope or not new_scope or not sender:
        return {"error": "from_scope, to_scope and sender required"}, 400
    if storage.has_admins(new_scope):
        return {"error": "target scope already in use"}, 409
    storage.move_scope(old_scope, new_scope, body.get("from_group_id"), new_group_id)
    if new_group_id:
        storage.register_group(new_group_id)
    storage.add_admin(new_scope, sender)
    return {
        "status": "moved",
        "language": storage.get_language(new_scope),
        "members": storage.migration_members(new_scope),
    }, 200


@app.post("/internal/merge_member")
def internal_merge_member() -> tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    scope_id = body.get("scope_id", "").strip()
    old_sender = body.get("old_sender", "").strip()
    new_sender = body.get("new_sender", "").strip()
    if not scope_id or not old_sender or not new_sender:
        return {"error": "scope_id, old_sender and new_sender required"}, 400
    storage.merge_member(scope_id, old_sender, new_sender)
    return {"status": "merged"}, 200


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
        app.logger.exception("Failed handling expense command: %s", exc)
        reply = "Something went wrong while handling your command."

    if isinstance(reply, dict):
        return {"status": "processed", **reply}, 200
    return {"status": "processed", "reply": reply}, 200


if __name__ == "__main__":
    host = os.getenv("BOT_HOST", "0.0.0.0")
    port = int(os.getenv("BOT_PORT", "5002"))
    send_thread = threading.Thread(target=_run_signal_send_loop, daemon=True)
    send_thread.start()
    app.run(host=host, port=port)
