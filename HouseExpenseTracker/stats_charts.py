from __future__ import annotations

import base64
import io

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
    colors: list[str] | str | None = None,
) -> str | None:
    if not labels or not values:
        return None
    height = max(3.2, min(10.0, len(labels) * 0.55 + 1.4))
    fig = Figure(figsize=(6.4, height), dpi=130)
    ax = fig.add_subplot(111)
    bar_colors = colors if isinstance(colors, list) else ([colors] * len(labels) if colors else "#4C78A8")
    bars = ax.barh(labels, values, color=bar_colors)
    ax.set_title(title, fontsize=13, pad=10)
    ax.set_xlabel(xlabel, fontsize=11)
    ax.invert_yaxis()
    ax.bar_label(bars, padding=3, fontsize=10, fmt="%.2f")
    ax.tick_params(axis="both", labelsize=10)
    fig.tight_layout()
    return _png_attachment(fig, filename)


def _truncate(label: str, max_len: int = 22) -> str:
    cleaned = label.strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1] + "…"


def balance_chart(members: list[tuple[str, int]], currency: str, language: str) -> str | None:
    if not members:
        return None
    labels = [name for name, _ in members]
    values = [cents / 100.0 for _, cents in members]
    colors = ["#59A14F" if value >= 0 else "#E15759" for value in values]
    title = "Salden" if language == "de" else "Balances"
    xlabel = currency
    return _barh_chart(labels, values, title, xlabel, "balances.png", colors)


def paid_chart(members: list[tuple[str, int]], currency: str, language: str) -> str | None:
    if not members:
        return None
    labels = [name for name, _ in members]
    values = [cents / 100.0 for _, cents in members]
    title = "Wer wie viel bezahlt hat" if language == "de" else "Who paid how much"
    xlabel = currency
    return _barh_chart(labels, values, title, xlabel, "paid.png", "#4C78A8")


def top_expenses_chart(rows: list[tuple[str, int]], currency: str, language: str) -> str | None:
    if not rows:
        return None
    labels = [_truncate(description) for description, _ in rows]
    values = [cents / 100.0 for _, cents in rows]
    title = "Größte Ausgaben" if language == "de" else "Largest expenses"
    xlabel = currency
    return _barh_chart(labels, values, title, xlabel, "top-expenses.png", "#F28E2B")


def personal_paid_chart(rows: list[tuple[str, int]], currency: str, language: str) -> str | None:
    if not rows:
        return None
    labels = [_truncate(description) for description, _ in rows]
    values = [cents / 100.0 for _, cents in rows]
    title = "Deine Zahlungen" if language == "de" else "Your payments"
    xlabel = currency
    return _barh_chart(labels, values, title, xlabel, "my-payments.png", "#4C78A8")


def balance_chart_kind(kind: str | None, language: str) -> str:
    normalized = (kind or "balances").lower()
    if normalized in {"balances", "bilanz", "salden", "balance"}:
        return "balances"
    if normalized in {"paid", "bezahlt", "zahlungen", "payments"}:
        return "paid"
    if normalized in {"top", "groesste", "größte", "ausgaben", "expenses", "largest"}:
        return "top"
    return normalized


def balance_chart_kinds(language: str) -> set[str]:
    if language == "de":
        return {"balances", "bilanz", "salden", "paid", "bezahlt", "zahlungen", "top", "groesste", "größte", "ausgaben"}
    return {"balances", "balance", "paid", "payments", "top", "expenses", "largest"}
