from __future__ import annotations

import re

AMOUNT_RE = re.compile(
    r"^\s*(?:€|eur\s*)?(?P<amount>\d+(?:[.,]\d{1,2})?)\s*(?:€|eur)?\s*$",
    re.IGNORECASE,
)


def parse_amount(text: str) -> int | None:
    cleaned = text.strip().replace(",", ".")
    cleaned = re.sub(r"^€\s*", "", cleaned)
    cleaned = re.sub(r"\s*€$", "", cleaned)
    cleaned = re.sub(r"^eur\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    match = AMOUNT_RE.match(cleaned) if cleaned else None
    if not match:
        try:
            value = float(cleaned)
        except ValueError:
            return None
    else:
        value = float(match.group("amount"))
    if value <= 0 or value > 1_000_000:
        return None
    return int(round(value * 100))


def format_money(cents: int, currency: str = "EUR", language: str = "en") -> str:
    amount = cents / 100
    if currency.upper() == "EUR":
        formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{formatted} €"
    return f"{currency} {amount:.2f}"


def split_equal(total_cents: int, count: int) -> list[int]:
    if count <= 0:
        return []
    base = total_cents // count
    remainder = total_cents % count
    shares = [base] * count
    for index in range(remainder):
        shares[index] += 1
    return shares


def split_with_multipliers(
    total_cents: int,
    members: list[str],
    multipliers: dict[str, float],
) -> dict[str, int]:
    """Equal base share per member; reduced multipliers redistribute shortfall to the others."""
    if not members:
        return {}
    equal_parts = split_equal(total_cents, len(members))
    shares = {member: equal_parts[index] for index, member in enumerate(members)}

    for index, member in enumerate(members):
        multiplier = multipliers.get(member, 1.0)
        if multiplier >= 1.0:
            continue
        multiplier = max(0.0, min(multiplier, 1.0))
        base_share = equal_parts[index]
        reduced_share = int(round(base_share * multiplier))
        shortfall = base_share - reduced_share
        shares[member] = reduced_share
        if shortfall <= 0:
            continue
        others = [other for other in members if other != member]
        if not others:
            continue
        extras = split_equal(shortfall, len(others))
        for other_index, other in enumerate(others):
            shares[other] += extras[other_index]

    drift = total_cents - sum(shares.values())
    if drift != 0:
        adjust_member = next(
            (member for member in members if multipliers.get(member, 1.0) >= 1.0),
            members[0],
        )
        shares[adjust_member] += drift
    return shares
