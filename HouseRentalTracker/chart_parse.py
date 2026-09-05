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


def parse_history_chart(command_lowered: str) -> tuple[str | None, bool]:
    for prefix in ("history ", "verlauf "):
        if not command_lowered.startswith(prefix):
            continue
        rest = command_lowered[len(prefix) :]
        for marker in CHART_MARKERS:
            if marker not in rest:
                continue
            label, _, _ = rest.partition(marker)
            label = label.strip()
            if label:
                return label, True
    return None, False
