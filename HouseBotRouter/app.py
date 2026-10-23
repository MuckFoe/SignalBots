from __future__ import annotations

import os
import queue
import threading
import time
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request

from group_router import (
    GroupRouter,
    error_text,
    guess_language,
    job_picker_text,
    job_selected_text,
    job_set_ack,
    language_command_for,
    parse_job_and_language,
)
from identity import IdentityStore
import migrations
from migrations import MigrationStore
from signal_client import SignalClient
from whatsapp_client import WhatsAppClient, is_whatsapp_target


load_dotenv()

app = Flask(__name__)

SIGNAL_BOT_NUMBER = os.getenv("SIGNAL_BOT_NUMBER", "").strip()
SIGNAL_API_URL = os.getenv("SIGNAL_API_URL", "http://localhost:8080").strip()
CHORE_BOT_URL = os.getenv("CHORE_BOT_URL", "http://chore-bot:5000").strip()
RENTAL_BOT_URL = os.getenv("RENTAL_BOT_URL", "http://rental-bot:5001").strip()
EXPENSE_BOT_URL = os.getenv("EXPENSE_BOT_URL", "http://expense-bot:5002").strip()
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "http://whatsapp-api:3000").strip()
WHATSAPP_API_KEY = os.getenv("WHATSAPP_API_KEY", "").strip()
DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/router.db").strip()
INCOMING_MAX_AGE_SECONDS = int(os.getenv("INCOMING_MAX_AGE_SECONDS", "300").strip())

if not SIGNAL_BOT_NUMBER:
    raise RuntimeError("SIGNAL_BOT_NUMBER is required in environment variables.")

router = GroupRouter(DATABASE_PATH, CHORE_BOT_URL, RENTAL_BOT_URL, EXPENSE_BOT_URL)
migration_store = MigrationStore(DATABASE_PATH)
signal = SignalClient(SIGNAL_API_URL, SIGNAL_BOT_NUMBER)
whatsapp = WhatsAppClient(WHATSAPP_API_URL, WHATSAPP_API_KEY)
identity = IdentityStore(DATABASE_PATH, whatsapp.phone_for_lid)
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
            if is_whatsapp_target(item["target"]):
                whatsapp.send_message(item["target"], item["message"], attachments)
            elif item["target_type"] == "group":
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
        "source_uuid": envelope.get("sourceUuid") or "",
        "message": message,
        "group_id": group_id,
        "timestamp": str(timestamp),
        "attachments": attachments,
    }


def _extract_whatsapp_payload(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if body.get("event") != "message":
        return None
    data = body.get("payload", {}) or {}
    if data.get("fromMe"):
        return None
    chat_id = data.get("from") or ""
    message = data.get("body") or ""
    if not message:
        return None
    if chat_id.endswith("@g.us"):
        source = data.get("participant")
        group_id = chat_id
    elif chat_id.endswith(("@c.us", "@lid")):
        source = chat_id
        group_id = None
    else:
        # status@broadcast, channels (@newsletter) and the like are not chats.
        return None
    if not source:
        return None
    return {
        "source": source,
        "message": message,
        "group_id": group_id,
        "timestamp": str(data.get("timestamp") or ""),
        "attachments": [],
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


def _call_bot(job: str, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    response = requests.post(f"{router.bot_urls[job]}{path}", json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def _handle_migration(scope_id: str, sender: str, text: str, group_id: str) -> Optional[str]:
    code = migrations.parse_code(text)
    if code is not None:
        return _complete_migration(scope_id, sender, group_id, code, text)
    target = migrations.parse_start(text)
    if target is not None:
        return _start_migration(scope_id, sender, group_id, target, text)
    claimed_name = migrations.parse_claim(text)
    if claimed_name is not None:
        return _claim_identity(scope_id, sender, claimed_name)
    return None


def _start_migration(scope_id: str, sender: str, group_id: str, target: str, text: str) -> Optional[str]:
    job = router.resolve_job(scope_id)
    if job is None:
        return None
    info = _call_bot(job, "/internal/scope", {"scope_id": scope_id, "sender": sender})
    language = info.get("language") or migrations.code_language(text)
    platform = migrations.PLATFORM_NAMES[target]
    if migrations.platform_of(group_id) == target:
        return migrations.text(language, "already_there", platform=platform)
    if not info.get("is_admin"):
        return migrations.text(language, "not_admin")
    code = migration_store.create_code(scope_id, group_id, job, target, sender, language)
    return migrations.text(language, "start_ok", platform=platform, code=code)


def _complete_migration(scope_id: str, sender: str, group_id: str, code: str, text: str) -> str:
    row = migration_store.get_code(code)
    if row is None:
        return migrations.text(migrations.code_language(text), "invalid_code")
    language = row["language"]
    platform = migrations.PLATFORM_NAMES[row["target_platform"]]
    if migrations.platform_of(group_id) != row["target_platform"]:
        return migrations.text(language, "wrong_platform", platform=platform)
    if router.resolve_job(scope_id) is not None:
        return migrations.text(language, "target_in_use")
    job = row["job"]
    try:
        result = _call_bot(
            job,
            "/internal/migrate",
            {
                "from_scope": row["from_scope"],
                "to_scope": scope_id,
                "from_group_id": row["from_group_id"],
                "to_group_id": group_id,
                "sender": sender,
            },
        )
    except requests.RequestException:
        app.logger.exception("Moving %s to %s failed", row["from_scope"], scope_id)
        return migrations.text(language, "failed")
    members = result.get("members") or []
    language = result.get("language") or language
    migration_store.finish_move(code, row["from_scope"], scope_id, job, members, language)
    # The mover already sees the claim prompt below; don't repeat it as a hint.
    migration_store.hint_once(scope_id, sender)
    _queue_signal_reply(row["from_group_id"], "", migrations.text(language, "old_notice", platform=platform))
    reply = migrations.text(language, "done")
    if members:
        reply += "\n\n" + migrations.claim_prompt(language, [member["name"] for member in members])
    return reply


def _claim_identity(scope_id: str, sender: str, name: str) -> Optional[str]:
    claims = migration_store.open_claims(scope_id)
    match = next((claim for claim in claims if claim["display_name"].casefold() == name.casefold()), None)
    if match is None:
        # Not a known old name: an ordinary message like "ich bin gleich da".
        return None
    language = match["language"]
    already = migration_store.claimed_name(scope_id, sender)
    if already:
        return migrations.text(language, "claim_already", name=already)
    job = router.resolve_job(scope_id)
    if job is None:
        return None
    _call_bot(
        job,
        "/internal/merge_member",
        {"scope_id": scope_id, "old_sender": match["old_sender"], "new_sender": sender},
    )
    migration_store.mark_claimed(scope_id, match["old_sender"], sender)
    return migrations.text(language, "claim_ok", name=match["display_name"])


def _merge_aliases(job: str, scope_id: str, member: str) -> None:
    # Rows stored under another id of the same number (an older "@c.us", "@lid"
    # or Signal UUID) fold into the number once per scope.
    for alias in identity.unmerged_aliases(scope_id, member):
        try:
            _call_bot(job, "/internal/merge_member", {"scope_id": scope_id, "old_sender": alias, "new_sender": member})
        except requests.RequestException:
            app.logger.exception("Merging %s into %s in %s failed", alias, member, scope_id)
            continue
        identity.mark_merged(scope_id, alias, member)
    migration_store.claim_own(scope_id, [member, *identity.aliases(member)], member)


def _claim_hint(scope_id: str, sender: str) -> Optional[str]:
    claims = migration_store.open_claims(scope_id)
    if not claims or migration_store.claimed_name(scope_id, sender):
        return None
    if not migration_store.hint_once(scope_id, sender):
        return None
    return migrations.claim_prompt(claims[0]["language"], [claim["display_name"] for claim in claims])


@app.get("/health")
def health() -> tuple[dict, int]:
    return {"status": "ok", "service": "router"}, 200


@app.post("/webhook")
def webhook() -> tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    return _process_incoming(_extract_message_payload(body))


@app.post("/webhook/whatsapp")
def webhook_whatsapp() -> tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    return _process_incoming(_extract_whatsapp_payload(body))


def _process_incoming(payload: Optional[Dict[str, Any]]) -> tuple[dict, int]:
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
        if payload.get("source_uuid"):
            identity.remember(payload["source_uuid"], sender)
        # In groups the bots know a person by phone number, so the same person
        # stays one member across Signal and WhatsApp. DMs keep the chat id,
        # which is also where the bots send DM reminders.
        member = identity.canonical(sender) if incoming_group_id else sender
        job = router.resolve_job(scope_id)
        if incoming_group_id:
            if job is not None:
                _merge_aliases(job, scope_id, member)
            migration_reply = _handle_migration(scope_id, member, incoming_text, incoming_group_id)
            if migration_reply is not None:
                _queue_signal_replies(incoming_group_id, sender, migration_reply)
                return jsonify({"status": "processed"}), 200
        if migration_store.is_moved(scope_id):
            return {"status": "ignored_moved"}, 200

        if job is None:
            picked, picked_language = parse_job_and_language(incoming_text)
            if picked:
                router.set_job(scope_id, picked)
                if picked_language:
                    result = router.forward(
                        picked,
                        scope_id,
                        member,
                        language_command_for(picked_language),
                        incoming_group_id,
                    )
                    reply = result.get("reply", "") or job_selected_text(picked, picked_language)
                else:
                    reply = job_set_ack(picked, guess_language(incoming_text))
                _queue_signal_replies(incoming_group_id, sender, reply)
                return jsonify({"status": "processed"}), 200
            _queue_signal_replies(incoming_group_id, sender, job_picker_text(incoming_text))
            return jsonify({"status": "processed"}), 200

        result = router.forward(
            job, scope_id, member, incoming_text, incoming_group_id, incoming_attachments
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
        hint = _claim_hint(scope_id, member)
        if hint:
            _queue_signal_replies(incoming_group_id, sender, hint)
        app.logger.info("Routed %s message for %s", job, scope_id)
    except Exception as exc:
        app.logger.exception("Router failed: %s", exc)
        _queue_signal_replies(
            incoming_group_id,
            sender,
            error_text(incoming_text),
        )

    return jsonify({"status": "processed"}), 200


if __name__ == "__main__":
    host = os.getenv("BOT_HOST", "0.0.0.0")
    port = int(os.getenv("BOT_PORT", "5100"))
    send_thread = threading.Thread(target=_run_signal_send_loop, daemon=True)
    send_thread.start()
    app.run(host=host, port=port)
