from __future__ import annotations

import re

QTY_RE = re.compile(r"^(\d+)\s*[x×]\s*(.+)$", re.IGNORECASE)


def parse_add_text(text: str) -> tuple[str, str, str | None, str | None]:
    """Return (name, quantity, category_hint, shop_hint)."""
    cleaned = text.strip()
    quantity = ""
    m = QTY_RE.match(cleaned)
    if m:
        quantity = m.group(1)
        cleaned = m.group(2).strip()

    category_hint = None
    shop_hint = None

    if "@" in cleaned:
        cleaned, _, cat_part = cleaned.partition("@")
        category_hint = cat_part.strip().split("#")[0].strip() or None
    if "#" in cleaned:
        cleaned, _, shop_part = cleaned.partition("#")
        shop_hint = shop_part.strip() or None

    return cleaned.strip(), quantity, category_hint, shop_hint


def strip_command_prefix(text: str, prefixes: tuple[str, ...]) -> str | None:
    lowered = text.strip().lower()
    for prefix in prefixes:
        if lowered == prefix:
            return ""
        if lowered.startswith(prefix + " "):
            return text.strip()[len(prefix) :].strip()
    return None
