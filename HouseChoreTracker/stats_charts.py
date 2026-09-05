from __future__ import annotations

import base64
import io

from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec


def _png_attachment(fig: Figure, filename: str) -> str:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=130, bbox_inches="tight", facecolor="white")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;filename={filename};base64,{encoded}"


def _truncate_label(text: str, limit: int = 14) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(1, limit - 1)] + "…"


def _draw_barh(ax, labels: list[str], values: list[float], title: str, xlabel: str, color: str) -> None:
    bars = ax.barh(labels, values, color=color)
    ax.set_title(title, fontsize=12, pad=8)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.invert_yaxis()
    ax.bar_label(bars, padding=3, fontsize=9, fmt="%.0f" if all(v == int(v) for v in values) else "%.2f")
    ax.tick_params(axis="both", labelsize=9)


def _people_series(user_totals: list[dict], display_name) -> tuple[list[str], list[float]] | None:
    people = user_totals[:12]
    if not people:
        return None
    return [display_name(row["sender"]) for row in people], [float(row["count"]) for row in people]


def _chore_series(chore_rows: list[dict]) -> tuple[list[str], list[float]] | None:
    chores = [row for row in chore_rows if int(row.get("completions") or 0) > 0][:12]
    if not chores:
        return None
    return [row["name"] for row in chores], [float(row["completions"]) for row in chores]


def _matrix_data(chore_rows: list[dict], display_name) -> tuple[list[str], list[str], list[list[float]]] | None:
    chores = [row for row in chore_rows if int(row.get("completions") or 0) > 0][:10]
    if not chores:
        return None
    people: list[str] = []
    seen: set[str] = set()
    for row in chores:
        for person in row.get("by_person") or []:
            sender = person["sender"]
            if sender not in seen:
                seen.add(sender)
                people.append(sender)
    people = people[:8]
    if not people:
        return None
    matrix: list[list[float]] = []
    for sender in people:
        row_values: list[float] = []
        for chore in chores:
            count = next(
                (person["count"] for person in (chore.get("by_person") or []) if person["sender"] == sender),
                0,
            )
            row_values.append(float(count))
        matrix.append(row_values)
    if not any(value > 0 for row in matrix for value in row):
        return None
    return (
        [_truncate_label(display_name(sender), 16) for sender in people],
        [_truncate_label(row["name"]) for row in chores],
        matrix,
    )


def _draw_matrix(ax, people_labels: list[str], chore_labels: list[str], matrix: list[list[float]], language: str):
    image = ax.imshow(matrix, aspect="auto", cmap="YlGnBu", vmin=0)
    ax.set_xticks(range(len(chore_labels)))
    ax.set_yticks(range(len(people_labels)))
    ax.set_xticklabels(chore_labels, rotation=35, ha="right", fontsize=8)
    ax.set_yticklabels(people_labels, fontsize=9)
    title = "Person × Aufgabe" if language == "de" else "Person × chore"
    ax.set_title(title, fontsize=12, pad=8)
    peak = max(max(row) for row in matrix)
    for row_idx, row_values in enumerate(matrix):
        for col_idx, value in enumerate(row_values):
            if value <= 0:
                continue
            ax.text(
                col_idx,
                row_idx,
                f"{int(value)}",
                ha="center",
                va="center",
                color="white" if peak and value >= peak * 0.55 else "#1f2933",
                fontsize=8,
                fontweight="bold",
            )
    return image


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
    color = colors[0] if isinstance(colors, list) and colors else (colors or "#4C78A8")
    _draw_barh(ax, labels, values, title, xlabel, str(color))
    fig.tight_layout()
    return _png_attachment(fig, filename)


def _matrix_chart(chore_rows: list[dict], display_name, language: str) -> str | None:
    data = _matrix_data(chore_rows, display_name)
    if data is None:
        return None
    people_labels, chore_labels, matrix = data
    width = max(5.5, min(11.0, len(chore_labels) * 0.85 + 2.2))
    height = max(3.6, min(9.0, len(people_labels) * 0.7 + 2.0))
    fig = Figure(figsize=(width, height), dpi=130)
    ax = fig.add_subplot(111)
    image = _draw_matrix(ax, people_labels, chore_labels, matrix, language)
    colorbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    colorbar.set_label("Erledigungen" if language == "de" else "Completions", fontsize=10)
    fig.tight_layout()
    return _png_attachment(fig, "group-matrix.png")


def group_stats_all_charts(
    user_totals: list[dict],
    chore_rows: list[dict],
    display_name,
    language: str,
) -> str | None:
    people = _people_series(user_totals, display_name)
    chores = _chore_series(chore_rows)
    matrix = _matrix_data(chore_rows, display_name)
    panels = [item for item in (people, chores, matrix) if item is not None]
    if not panels:
        return None

    xlabel = "Erledigungen" if language == "de" else "Completions"
    people_title = "Wer wie viel" if language == "de" else "Who did how much"
    chores_title = "Pro Aufgabe" if language == "de" else "Per chore"
    main_title = "Gruppen-Statistik Übersicht" if language == "de" else "Group stats overview"

    fig = Figure(figsize=(11.0, 9.2), dpi=130, layout="constrained")
    if people and chores and matrix:
        grid = GridSpec(2, 2, figure=fig, height_ratios=[1.0, 1.15])
        ax_people = fig.add_subplot(grid[0, 0])
        ax_chores = fig.add_subplot(grid[0, 1])
        ax_matrix = fig.add_subplot(grid[1, :])
        _draw_barh(ax_people, people[0], people[1], people_title, xlabel, "#59A14F")
        _draw_barh(ax_chores, chores[0], chores[1], chores_title, xlabel, "#E15759")
        image = _draw_matrix(ax_matrix, matrix[0], matrix[1], matrix[2], language)
        colorbar = fig.colorbar(image, ax=ax_matrix, fraction=0.046, pad=0.02)
        colorbar.set_label(xlabel, fontsize=9)
    elif len(panels) == 2:
        grid = GridSpec(2, 1, figure=fig)
        axes = [fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[1, 0])]
        axis_idx = 0
        if people:
            _draw_barh(axes[axis_idx], people[0], people[1], people_title, xlabel, "#59A14F")
            axis_idx += 1
        if chores:
            _draw_barh(axes[axis_idx], chores[0], chores[1], chores_title, xlabel, "#E15759")
            axis_idx += 1
        if matrix and axis_idx < 2:
            image = _draw_matrix(axes[axis_idx], matrix[0], matrix[1], matrix[2], language)
            fig.colorbar(image, ax=axes[axis_idx], fraction=0.046, pad=0.02)
    else:
        ax = fig.add_subplot(111)
        if people:
            _draw_barh(ax, people[0], people[1], people_title, xlabel, "#59A14F")
        elif chores:
            _draw_barh(ax, chores[0], chores[1], chores_title, xlabel, "#E15759")
        else:
            image = _draw_matrix(ax, matrix[0], matrix[1], matrix[2], language)
            fig.colorbar(image, ax=ax, fraction=0.046, pad=0.02)

    fig.suptitle(main_title, fontsize=14)
    return _png_attachment(fig, "group-all-charts.png")


def user_stats_chart(by_chore: list[dict], language: str) -> str | None:
    rows = by_chore[:12]
    if not rows:
        return None
    title = "Deine Aufgaben" if language == "de" else "Your chores"
    xlabel = "Erledigungen" if language == "de" else "Completions"
    return _barh_chart(
        [row["name"] for row in rows],
        [float(row["count"]) for row in rows],
        title,
        xlabel,
        "my-stats.png",
        "#4C78A8",
    )


ALL_CHART_KINDS = {
    "all",
    "alle",
    "alles",
    "dashboard",
    "komplett",
    "gesamt",
    "allcharts",
    "diagramme",
}


def group_stats_chart(
    kind: str | None,
    user_totals: list[dict],
    chore_rows: list[dict],
    display_name,
    language: str,
) -> str | None:
    normalized = (kind or "people").lower()
    if normalized in ALL_CHART_KINDS:
        return group_stats_all_charts(user_totals, chore_rows, display_name, language)

    if normalized in {"people", "leute", "wer", "users", "mitglieder"}:
        series = _people_series(user_totals, display_name)
        if series is None:
            return None
        title = "Wer wie viel erledigt hat" if language == "de" else "Who did how much"
        xlabel = "Erledigungen" if language == "de" else "Completions"
        return _barh_chart(series[0], series[1], title, xlabel, "group-people.png", "#59A14F")

    if normalized in {"chores", "aufgaben", "tasks", "aufgabe"}:
        series = _chore_series(chore_rows)
        if series is None:
            return None
        title = "Erledigungen pro Aufgabe" if language == "de" else "Completions per chore"
        xlabel = "Erledigungen" if language == "de" else "Completions"
        return _barh_chart(series[0], series[1], title, xlabel, "group-chores.png", "#E15759")

    if normalized in {
        "matrix",
        "cluster",
        "heatmap",
        "grid",
        "werwas",
        "personen",
        "overview",
        "uebersicht",
        "übersicht",
    }:
        return _matrix_chart(chore_rows, display_name, language)
    return None


def group_chart_kinds(language: str) -> set[str]:
    return {
        "people",
        "leute",
        "wer",
        "users",
        "mitglieder",
        "chores",
        "aufgaben",
        "tasks",
        "aufgabe",
        "matrix",
        "cluster",
        "heatmap",
        "grid",
        "werwas",
        "personen",
        "overview",
        "uebersicht",
        "übersicht",
        *ALL_CHART_KINDS,
    }
