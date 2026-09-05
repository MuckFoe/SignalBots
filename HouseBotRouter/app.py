from __future__ import annotations

import os
import queue
import threading
import time
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from group_router import (
    GroupRouter,
    job_picker_text,
    job_set_ack,
    language_command_for,
    parse_job_and_language,
)
from signal_client import SignalClient


load_dotenv()

app = Flask(__name__)

SIGNAL_BOT_NUMBER = os.getenv("SIGNAL_BOT_NUMBER", "").strip()
SIGNAL_API_URL = os.getenv("SIGNAL_API_URL", "http://localhost:8080").strip()
CHORE_BOT_URL = os.getenv("CHORE_BOT_URL", "http://chore-bot:5000").strip()
RENTAL_BOT_URL = os.getenv("RENTAL_BOT_URL", "http://rental-bot:5001").strip()
EXPENSE_BOT_URL = os.getenv("EXPENSE_BOT_URL", "http://expense-bot:5002").strip()
GROCERY_BOT_URL = os.getenv("GROCERY_BOT_URL", "http://grocery-bot:5003").strip()
DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/router.db").strip()
INCOMING_MAX_AGE_SECONDS = int(os.getenv("INCOMING_MAX_AGE_SECONDS", "300").strip())

if not SIGNAL_BOT_NUMBER:
    raise RuntimeError("SIGNAL_BOT_NUMBER is required in environment variables.")

router = GroupRouter(DATABASE_PATH, CHORE_BOT_URL, RENTAL_BOT_URL, EXPENSE_BOT_URL, GROCERY_BOT_URL)
signal = SignalClient(SIGNAL_API_URL, SIGNAL_BOT_NUMBER)
outbound_messages: queue.Queue[Dict[str, str]] = queue.Queue()
seen_messages: dict[str, float] = {}
seen_messages_lock = threading.Lock()


def _queue_signal_reply(
    group_id: Optional[str],
    recipient: str,
    message: str,
    attachments: list[str] | None = None,
) -> None:
    outbound_messages.put(
        {
            "target_type": "group" if group_id else "dm",
            "target": group_id or recipient,
            "message": message,
            "attachments": attachments or [],
        }
    )


def _queue_signal_replies(
    group_id: Optional[str],
    recipient: str,
    messages: str | list[str] | dict,
    attachments: list[str] | None = None,
) -> None:
    if isinstance(messages, dict):
        reply = messages.get("reply", "")
        merged_attachments = messages.get("attachments") or attachments or []
        if isinstance(reply, list):
            for index, message in enumerate(reply):
                if not message:
                    continue
                message_attachments = merged_attachments if index == len(reply) - 1 else None
                _queue_signal_reply(group_id, recipient, message, message_attachments)
            return
        if reply:
            _queue_signal_reply(group_id, recipient, reply, merged_attachments)
        return
    if isinstance(messages, str):
        if messages:
            _queue_signal_reply(group_id, recipient, messages, attachments)
        return
    for index, message in enumerate(messages):
        if message:
            message_attachments = attachments if index == len(messages) - 1 else None
            _queue_signal_reply(group_id, recipient, message, message_attachments)


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


def _extract_message_payload(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    envelope = body.get("envelope", {})
    if not envelope:
        params = body.get("params", {}) or {}
        envelope = params.get("envelope", {})
        if not envelope:
            result = params.get("result", {}) or {}
            envelope = result.get("envelope", {})

    source = envelope.get("sourceNumber") or envelope.get("source")
    data_message = envelope.get("dataMessage", {}) or {}
    message = data_message.get("message") or ""
    attachments = data_message.get("attachments") or []
    if not source:
        return None
    if not message and not attachments:
        return None
    group_info = data_message.get("groupInfo", {}) or {}
    group_id = group_info.get("groupId")
    timestamp = envelope.get("timestamp") or data_message.get("timestamp") or ""
    return {
        "source": source,
        "message": message,
        "group_id": group_id,
        "timestamp": str(timestamp),
        "attachments": attachments,
    }


def _is_duplicate_message(payload: Dict[str, Any]) -> bool:
    timestamp = payload.get("timestamp")
    if not timestamp:
        return False
    now = time.time()
    attachment_ids = ",".join(
        sorted(
            str(a.get("id") or a.get("attachmentId") or "")
            for a in (payload.get("attachments") or [])
        )
    )
    key = "|".join(
        [
            payload.get("source", ""),
            payload.get("group_id") or "",
            timestamp,
            payload.get("message", ""),
            attachment_ids,
        ]
    )
    with seen_messages_lock:
        for existing_key, expires_at in list(seen_messages.items()):
            if expires_at <= now:
                del seen_messages[existing_key]
        if key in seen_messages:
            return True
        seen_messages[key] = now + 10 * 60
    return False


def _message_timestamp_seconds(payload: Dict[str, str]) -> Optional[float]:
    raw_timestamp = payload.get("timestamp", "").strip()
    if not raw_timestamp or not raw_timestamp.isdigit():
        return None
    timestamp = float(raw_timestamp)
    while timestamp > 10_000_000_000:
        timestamp /= 1000
    return timestamp


def _is_stale_message(payload: Dict[str, str]) -> bool:
    if INCOMING_MAX_AGE_SECONDS <= 0:
        return False
    message_timestamp = _message_timestamp_seconds(payload)
    if message_timestamp is None:
        return False
    return time.time() - message_timestamp > INCOMING_MAX_AGE_SECONDS


@app.get("/health")
def health() -> tuple[dict, int]:
    return {"status": "ok", "service": "router"}, 200


@app.post("/webhook")
def webhook() -> tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    payload = _extract_message_payload(body)
    if payload is None:
        return {"status": "ignored"}, 200

    sender = payload["source"]
    incoming_text = payload.get("message", "")
    incoming_attachments = payload.get("attachments") or []
    incoming_group_id = payload.get("group_id")
    if sender == SIGNAL_BOT_NUMBER:
        return {"status": "ignored_self"}, 200
    if _is_stale_message(payload):
        return {"status": "ignored_stale"}, 200
    if _is_duplicate_message(payload):
        return {"status": "ignored_duplicate"}, 200

    scope_id = f"group:{incoming_group_id}" if incoming_group_id else f"dm:{sender}"

    try:
        job = router.resolve_job(scope_id)
        if job is None:
            picked, picked_language = parse_job_and_language(incoming_text)
            if picked:
                router.set_job(scope_id, picked)
                if picked_language:
                    result = router.forward(
                        picked,
                        scope_id,
                        sender,
                        language_command_for(picked_language),
                        incoming_group_id,
                    )
                    reply = result.get("reply", "") or job_set_ack(picked, picked_language)
                else:
                    reply = job_set_ack(picked)
                _queue_signal_replies(incoming_group_id, sender, reply)
                return jsonify({"status": "processed"}), 200
            _queue_signal_replies(incoming_group_id, sender, job_picker_text(incoming_text))
            return jsonify({"status": "processed"}), 200

        result = router.forward(
            job, scope_id, sender, incoming_text, incoming_group_id, incoming_attachments
        )
        if result.get("status") == "ignored_wrong_bot":
            return {"status": "ignored_wrong_bot"}, 200
        reply = result.get("reply", "")
        attachments = result.get("attachments") or []
        if attachments:
            _queue_signal_replies(
                incoming_group_id,
                sender,
                {"reply": reply, "attachments": attachments},
            )
        else:
            _queue_signal_replies(incoming_group_id, sender, reply)
        app.logger.info("Routed %s message for %s", job, scope_id)
    except Exception as exc:
        app.logger.exception("Router failed: %s", exc)
        _queue_signal_replies(
            incoming_group_id,
            sender,
            "Something went wrong while handling your command.",
        )

    return jsonify({"status": "processed"}), 200


if __name__ == "__main__":
    host = os.getenv("BOT_HOST", "0.0.0.0")
    port = int(os.getenv("BOT_PORT", "5100"))
    send_thread = threading.Thread(target=_run_signal_send_loop, daemon=True)
    send_thread.start()
    app.run(host=host, port=port)
