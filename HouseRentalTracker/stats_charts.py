from __future__ import annotations

import base64
import io
import json

from matplotlib.figure import Figure


def _png_attachment(fig: Figure, filename: str) -> str:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=130, bbox_inches="tight", facecolor="white")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;filename={filename};base64,{encoded}"


def _barh_chart(
    labels: list[str],
    values: list[float],
    title: str,
    xlabel: str,
    filename: str,
    color: str = "#4C78A8",
) -> str | None:
    if not labels or not values:
        return None
    height = max(3.2, min(10.0, len(labels) * 0.55 + 1.4))
    fig = Figure(figsize=(6.4, height), dpi=130)
    ax = fig.add_subplot(111)
    bars = ax.barh(labels, values, color=color)
    ax.set_title(title, fontsize=13, pad=10)
    ax.set_xlabel(xlabel, fontsize=11)
    ax.invert_yaxis()
    ax.bar_label(bars, padding=3, fontsize=10, fmt="%.0f")
    ax.tick_params(axis="both", labelsize=10)
    fig.tight_layout()
    return _png_attachment(fig, filename)


def listing_price_chart(
    kind: str | None,
    listings: list[dict],
    language: str,
) -> str | None:
    normalized = (kind or "total").lower()
    use_night = normalized in {"night", "nacht", "nights", "naechte", "nächte"}
    rows = []
    for row in listings:
        label = row["label"]
        if use_night:
            value = row.get("price_per_night")
            if value is None:
                continue
        else:
            value = row.get("total_price")
            if value is None:
                value = row.get("price_per_night")
            if value is None:
                continue
        rows.append((label, int(value), row.get("currency") or "EUR"))
    rows = rows[:12]
    if not rows:
        return None
    currency = rows[0][2]
    if use_night:
        title = "Preis pro Nacht" if language == "de" else "Price per night"
        filename = "rental-night-prices.png"
    else:
        title = "Gesamtpreis" if language == "de" else "Total price"
        filename = "rental-total-prices.png"
    return _barh_chart(
        [label for label, _, _ in rows],
        [value / 100.0 for _, value, _ in rows],
        title,
        currency,
        filename,
        "#59A14F",
    )


def listing_history_chart(label: str, history_rows: list, language: str) -> str | None:
    if not history_rows:
        return None
    points: list[tuple[str, float]] = []
    currency = "EUR"
    for row in reversed(history_rows):
        snapshot = json.loads(row["snapshot_json"])
        total = snapshot.get("total_price") or snapshot.get("price_per_night")
        if total is None:
            continue
        currency = snapshot.get("currency") or currency
        stamp = str(row["changed_at"])[:10]
        points.append((stamp, int(total) / 100.0))
    if len(points) < 2:
        return None
    fig = Figure(figsize=(6.4, 3.8), dpi=130)
    ax = fig.add_subplot(111)
    ax.plot([point[0] for point in points], [point[1] for point in points], marker="o", color="#E15759")
    title = f"Preisverlauf: {label}" if language == "de" else f"Price history: {label}"
    ax.set_title(title, fontsize=13, pad=10)
    ax.set_ylabel(currency, fontsize=11)
    ax.tick_params(axis="x", labelrotation=35, labelsize=9)
    ax.tick_params(axis="y", labelsize=10)
    fig.tight_layout()
    return _png_attachment(fig, "rental-history.png")


def overview_chart_kinds(language: str) -> set[str]:
    if language == "de":
        return {"total", "gesamt", "night", "nacht", "nächte", "naechte"}
    return {"total", "prices", "night", "nights"}
