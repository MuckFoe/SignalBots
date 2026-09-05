from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlparse


def normalize_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    parsed = urlparse(cleaned)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")


def hostname(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def parse_date(text: str) -> date | None:
    cleaned = text.strip()
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", cleaned)
    if not match:
        return None
    year, month, day = map(int, match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def nights_between(check_in: date, check_out: date) -> int:
    return max(0, (check_out - check_in).days)


def format_date(value: date) -> str:
    return value.isoformat()


def format_money(amount: float | None, currency: str = "EUR", language: str = "en") -> str:
    if amount is None:
        return "n/a" if language == "en" else "k.A."
    symbol = "€" if currency.upper() == "EUR" else currency
    formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if language == "de":
        return f"{formatted} {symbol}".strip()
    return f"{symbol}{formatted}" if symbol == "€" else f"{formatted} {symbol}"


def format_availability(available: bool | None, language: str) -> str:
    if available is True:
        return "free" if language == "en" else "frei"
    if available is False:
        return "booked" if language == "en" else "belegt"
    return "unknown" if language == "en" else "unbekannt"
