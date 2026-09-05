from __future__ import annotations

import requests

DEFAULT_ORIGIN_NAME = "Stuttgart"
DEFAULT_ORIGIN_LAT = 48.7758
DEFAULT_ORIGIN_LON = 9.1829
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"


def driving_time_minutes(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
) -> tuple[int | None, float | None]:
    url = f"{OSRM_URL}/{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
    try:
        response = requests.get(url, params={"overview": "false"}, timeout=20)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != "Ok" or not payload.get("routes"):
            return None, None
        route = payload["routes"][0]
        duration_seconds = route.get("duration")
        distance_meters = route.get("distance")
        if duration_seconds is None:
            return None, None
        minutes = int(round(duration_seconds / 60))
        kilometers = round(distance_meters / 1000, 1) if distance_meters is not None else None
        return minutes, kilometers
    except (requests.RequestException, ValueError, TypeError):
        return None, None


def format_drive_time(minutes: int | None, kilometers: float | None, language: str) -> str:
    if minutes is None:
        return "n/a" if language == "en" else "k.A."
    if language == "de":
        parts = [f"{minutes} Min."]
        if kilometers is not None:
            parts.append(f"{kilometers} km")
        return " / ".join(parts)
    parts = [f"{minutes} min"]
    if kilometers is not None:
        parts.append(f"{kilometers} km")
    return " / ".join(parts)
