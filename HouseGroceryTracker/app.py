from __future__ import annotations

import os
import queue
import threading
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from flask import Flask, request

from bot_registry import runtime_bot_id
from commands import handle_command, text_for
from signal_client import SignalClient
from storage import Storage


load_dotenv()

app = Flask(__name__)

SIGNAL_BOT_NUMBER = os.getenv("SIGNAL_BOT_NUMBER", "").strip()
SIGNAL_API_URL = os.getenv("SIGNAL_API_URL", "http://localhost:8080").strip()
DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/grocery.db").strip()

if not SIGNAL_BOT_NUMBER:
    raise RuntimeError("SIGNAL_BOT_NUMBER is required in environment variables.")

storage = Storage(DATABASE_PATH)
signal = SignalClient(SIGNAL_API_URL, SIGNAL_BOT_NUMBER)
outbound_messages: queue.Queue[Dict[str, str]] = queue.Queue()


def _queue_signal_reply(group_id: Optional[str], recipient: str, message: str, attachments: list[str] | None = None) -> None:
    outbound_messages.put(
        {
            "target_type": "group" if group_id else "dm",
            "target": group_id or recipient,
            "message": message,
            "attachments": attachments or [],
        }
    )


def _run_signal_send_loop() -> None:
    while True:
        item = outbound_messages.get()
        try:
            attachments = item.get("attachments") or None
            if item["target_type"] == "group":
                signal.send_group_message(item["target"], item["message"], attachments)
            else:
                signal.send_message(item["target"], item["message"], attachments)
        except Exception as exc:
            app.logger.exception("Failed sending Signal reply: %s", exc)
        finally:
            outbound_messages.task_done()


@app.get("/health")
def health() -> tuple[dict, int]:
    return {"status": "ok", "service": "grocery-bot"}, 200


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
    attachments = body.get("attachments") or []
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
            attachments=attachments,
        )
    except Exception as exc:
        app.logger.exception("Failed handling grocery command: %s", exc)
        reply = text_for(storage, scope_id, "unexpected_error")

    if isinstance(reply, dict):
        return {"status": "processed", **reply}, 200
    return {"status": "processed", "reply": reply}, 200


if __name__ == "__main__":
    host = os.getenv("BOT_HOST", "0.0.0.0")
    port = int(os.getenv("BOT_PORT", "5003"))
    send_thread = threading.Thread(target=_run_signal_send_loop, daemon=True)
    send_thread.start()
    app.run(host=host, port=port)
