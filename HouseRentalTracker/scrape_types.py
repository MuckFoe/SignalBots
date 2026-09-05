from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass
class ScrapeResult:
    available: bool | None = None
    price_per_night: float | None = None
    total_price: float | None = None
    currency: str = "EUR"
    title: str | None = None
    location_name: str | None = None
    lat: float | None = None
    lon: float | None = None
    guests_max: int | None = None
    bedrooms: int | None = None
    bathrooms: float | None = None
    rating: float | None = None
    review_count: int | None = None
    min_nights: int | None = None
    cleaning_fee: float | None = None
    pets_allowed: bool | None = None
    property_type: str | None = None
    error: str | None = None

    def tracked_values(self) -> dict[str, Any]:
        tracked = {}
        for field in fields(self):
            if field.name == "error":
                continue
            tracked[field.name] = getattr(self, field.name)
        return tracked

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


TRACKED_FIELDS = [
    "available",
    "price_per_night",
    "total_price",
    "currency",
    "title",
    "location_name",
    "lat",
    "lon",
    "guests_max",
    "bedrooms",
    "bathrooms",
    "rating",
    "review_count",
    "min_nights",
    "cleaning_fee",
    "pets_allowed",
    "property_type",
]

# Fields that trigger history entries and Signal notifications.
NOTIFY_CHANGE_FIELDS = [
    "available",
    "price_per_night",
    "total_price",
    "currency",
    "cleaning_fee",
    "min_nights",
]
