from __future__ import annotations

CHART_MARKERS = (" chart", " diagramm", " graph", " plot", " bild")


def parse_chart_command(command_lowered: str) -> tuple[str, bool, str | None]:
    for marker in CHART_MARKERS:
        if marker not in command_lowered:
            continue
        base, _, remainder = command_lowered.partition(marker)
        kind = remainder.strip().split()[0] if remainder.strip() else None
        return base.strip(), True, kind
    return command_lowered, False, None
