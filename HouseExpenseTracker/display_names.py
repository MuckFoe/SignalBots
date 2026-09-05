from __future__ import annotations

import hashlib
import re

DEFAULT_NAMES = [
    "Alex", "Sam", "Jordan", "Casey", "Riley", "Morgan", "Quinn", "Avery",
    "Jamie", "Taylor", "Robin", "Charlie", "Sky", "Nova", "Parker", "Drew",
    "Kai", "Remy", "Sage", "Rowan", "Ellis", "Reese", "Blair", "Ash",
]

PHONE_RE = re.compile(r"^\+\d")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
HEX_RE = re.compile(r"^[0-9a-f]+$", re.IGNORECASE)
DISPLAY_NAME_RE = re.compile(r"^[\w][\w \-'.]{1,23}$", re.UNICODE)


def is_opaque_sender(sender: str) -> bool:
    cleaned = sender.strip()
    if not cleaned:
        return True
    if PHONE_RE.match(cleaned):
        return False
    if UUID_RE.match(cleaned):
        return True
    if HEX_RE.match(cleaned) and len(cleaned) >= 16:
        return True
    return True


def is_valid_display_name(name: str) -> bool:
    cleaned = name.strip()
    if len(cleaned) < 2 or len(cleaned) > 24:
        return False
    return DISPLAY_NAME_RE.fullmatch(cleaned) is not None


def default_display_name(sender: str, used: set[str]) -> str:
    idx = int(hashlib.sha256(sender.encode("utf-8")).hexdigest()[:8], 16) % len(DEFAULT_NAMES)
    base = DEFAULT_NAMES[idx]
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base} {suffix}"
        suffix += 1
    used.add(candidate)
    return candidate
