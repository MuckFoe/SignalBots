from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any

import requests

IMAGE_DIR = Path(__import__("os").getenv("GROCERY_IMAGE_DIR", "/data/images"))


def download_attachment(signal_api_url: str, attachment_id: str) -> tuple[bytes, str] | None:
    url = f"{signal_api_url.rstrip('/')}/v1/attachments/{attachment_id}"
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        if "json" in content_type:
            payload = response.json()
            raw = payload.get("data") or payload.get("base64") or ""
            if isinstance(raw, str):
                return base64.b64decode(raw), payload.get("contentType", "image/jpeg")
            return None
        return response.content, content_type.split(";")[0]
    except requests.RequestException:
        return None


def save_item_image(scope_id: str, item_id: int, data: bytes, content_type: str) -> str:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    ext = "jpg"
    if "png" in content_type:
        ext = "png"
    elif "webp" in content_type:
        ext = "webp"
    safe_scope = re.sub(r"[^\w\-]", "_", scope_id)[:40]
    path = IMAGE_DIR / f"{safe_scope}_{item_id}.{ext}"
    path.write_bytes(data)
    return str(path)


def fetch_incoming_image(
    signal_api_url: str,
    attachment: dict[str, Any],
) -> tuple[bytes, str] | None:
    attachment_id = attachment.get("id") or attachment.get("attachmentId") or ""
    if not attachment_id:
        return None
    downloaded = download_attachment(signal_api_url, attachment_id)
    if not downloaded:
        return None
    data, content_type = downloaded
    if not content_type.startswith("image/"):
        return None
    return data, content_type
