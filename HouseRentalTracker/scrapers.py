from __future__ import annotations

import json
import re
from datetime import date
from typing import Protocol
from urllib.parse import urlparse

import requests

from scrape_types import ScrapeResult
from utils import hostname, nights_between


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class ScraperAdapter(Protocol):
    adapter_id: str
    display_name: str

    def matches(self, url: str) -> bool:
        ...

    def scrape(
        self,
        url: str,
        check_in: date,
        check_out: date,
        guests: int,
    ) -> ScrapeResult:
        ...


def _request_json(url: str, params: dict | None = None) -> dict | None:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    }
    try:
        response = requests.get(url, headers=headers, params=params, timeout=25)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        return None


def _request_text(url: str) -> str | None:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    }
    try:
        response = requests.get(url, headers=headers, timeout=25)
        response.raise_for_status()
        return response.text
    except requests.RequestException:
        return None


def extract_offer_id(url: str) -> str | None:
    parsed = urlparse(url)
    match = re.search(r"/rental/([a-f0-9]+)", parsed.path, re.IGNORECASE)
    if match:
        return match.group(1)
    query = parsed.query
    object_match = re.search(r"object=(\d+)", query, re.IGNORECASE)
    if object_match:
        return object_match.group(1)
    return None


def _extract_coordinates(html: str) -> tuple[float | None, float | None]:
    lat_match = re.search(r'"lat"\s*:\s*(-?\d+\.\d+)', html)
    lng_match = re.search(r'"lng"\s*:\s*(-?\d+\.\d+)', html)
    if lat_match and lng_match:
        return float(lat_match.group(1)), float(lng_match.group(1))
    lat_match = re.search(r'"latitude"\s*:\s*(-?\d+\.\d+)', html)
    lon_match = re.search(r'"longitude"\s*:\s*(-?\d+\.\d+)', html)
    if lat_match and lon_match:
        return float(lat_match.group(1)), float(lon_match.group(1))
    return None, None


def _parse_price_details(content: dict) -> tuple[float | None, float | None, float | None, str]:
    currency = "EUR"
    price_per_night = None
    total_price = None
    cleaning_fee = None

    booking = content.get("bookingDetails") or content.get("priceDetails") or {}
    if isinstance(booking, dict):
        currency = booking.get("currency") or content.get("currency") or currency
        price_per_night = _first_number(
            booking,
            "pricePerNight",
            "nightlyPrice",
            "pricePerNightEur",
            "ppn",
        )
        total_price = _first_number(
            booking,
            "totalPrice",
            "total",
            "priceTotal",
            "amount",
        )
        cleaning_fee = _first_number(booking, "cleaningFee", "cleaning")

    price_breakdown = content.get("priceBreakdown") or content.get("prices")
    if isinstance(price_breakdown, list):
        for item in price_breakdown:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label", "")).lower()
            value = _first_number(item, "amount", "price", "value")
            if value is None:
                continue
            if "clean" in label or "reinig" in label:
                cleaning_fee = value
            if "total" in label or "gesamt" in label:
                total_price = value

    return price_per_night, total_price, cleaning_fee, currency


def _first_number(data: dict, *keys: str) -> float | None:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = re.sub(r"[^\d,.-]", "", value).replace(",", ".")
            try:
                return float(cleaned)
            except ValueError:
                continue
    return None


class HomeToGoAdapter:
    adapter_id = "hometogo"
    display_name = "HomeToGo family (Casamundo, etc.)"

    HOSTS = {
        "casamundo.de",
        "casamundo.com",
        "casamundo.at",
        "casamundo.ch",
        "hometogo.de",
        "hometogo.com",
        "fewo-direkt.de",
        "amivac.de",
        "bellevue-ferienhaus.de",
        "feries.fr",
        "vacationrenter.com",
    }

    def matches(self, url: str) -> bool:
        host = hostname(url)
        return host in self.HOSTS or any(host.endswith(f".{known}") for known in self.HOSTS)

    def scrape(
        self,
        url: str,
        check_in: date,
        check_out: date,
        guests: int,
    ) -> ScrapeResult:
        offer_id = extract_offer_id(url)
        if not offer_id:
            return ScrapeResult(error="Could not detect rental id in URL.")

        parsed = urlparse(url if url.startswith("http") else f"https://{url}")
        base = f"{parsed.scheme}://{parsed.netloc}"
        duration = max(1, nights_between(check_in, check_out))
        params = {
            "arrival": check_in.isoformat(),
            "duration": str(duration),
            "persons": str(guests),
            "_format": "json",
        }

        page_html = _request_text(f"{base}/rental/{offer_id}?{params['arrival']}&duration={duration}")
        lat, lon = _extract_coordinates(page_html or "")

        app_data = _request_json(f"{base}/rental-app-data/{offer_id}", params) or {}
        title = app_data.get("pageTitle")
        if title and " - " in title:
            title = title.rsplit(" - ", 1)[0].strip()

        analytics = (app_data.get("analyticsSnowPlow") or {}).get("search") or {}
        offer = (app_data.get("analyticsSnowPlow") or {}).get("offer") or {}
        bedrooms = analytics.get("bedrooms") or offer.get("bedrooms")
        bathrooms = analytics.get("bathrooms") or offer.get("bathrooms")
        location_name = ((app_data.get("location") or {}).get("name") or "").strip() or None
        if not title:
            title = offer.get("title")

        availability = _request_json(
            f"{base}/booking/checkout/availabilityCheck/{offer_id}",
            params,
        ) or {}
        availability_content = availability.get("content") or {}
        available = availability_content.get("isAvailable")
        tracking = availability_content.get("pandaTracking") or {}
        price_per_night = tracking.get("ppnEur")
        if price_per_night is not None:
            price_per_night = float(price_per_night)

        price_details = _request_json(
            f"{base}/booking/checkout/priceDetails/{offer_id}",
            params,
        ) or {}
        total_price = None
        cleaning_fee = None
        currency = "EUR"
        if not price_details.get("hasErrors"):
            ppn, total, cleaning, currency = _parse_price_details(price_details.get("content") or {})
            price_per_night = price_per_night or ppn
            total_price = total
            cleaning_fee = cleaning
        elif available and price_details.get("errorMessage") == "price_not_available":
            pass

        error = None
        if availability.get("hasErrors"):
            error = availability.get("errorMessage") or "availability_error"

        return ScrapeResult(
            available=available,
            price_per_night=price_per_night,
            total_price=total_price,
            currency=currency,
            title=title,
            location_name=location_name,
            lat=lat,
            lon=lon,
            guests_max=guests,
            bedrooms=int(bedrooms) if bedrooms is not None else None,
            bathrooms=float(bathrooms) if bathrooms is not None else None,
            cleaning_fee=cleaning_fee,
            error=error,
        )


class JsonLdAdapter:
    adapter_id = "json_ld"
    display_name = "Generic JSON-LD vacation rental"

    def matches(self, url: str) -> bool:
        return url.startswith("http")

    def scrape(
        self,
        url: str,
        check_in: date,
        check_out: date,
        guests: int,
    ) -> ScrapeResult:
        html = _request_text(url)
        if not html:
            return ScrapeResult(error="Could not fetch page.")

        blocks = re.findall(
            r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        for block in blocks:
            try:
                data = json.loads(block.strip())
            except json.JSONDecodeError:
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                item_type = str(item.get("@type", ""))
                if "VacationRental" not in item_type and "LodgingBusiness" not in item_type and "Product" not in item_type:
                    continue
                return self._from_json_ld(item, guests)

        lat, lon = _extract_coordinates(html)
        return ScrapeResult(lat=lat, lon=lon, guests_max=guests, error="No vacation rental JSON-LD found.")

    def _from_json_ld(self, item: dict, guests: int) -> ScrapeResult:
        title = item.get("name") or item.get("title")
        address = item.get("address") or {}
        location_name = None
        if isinstance(address, dict):
            parts = [
                address.get("addressLocality"),
                address.get("addressRegion"),
                address.get("addressCountry"),
            ]
            location_name = ", ".join(part for part in parts if part)

        geo = item.get("geo") or {}
        lat = geo.get("latitude")
        lon = geo.get("longitude")

        rating_value = None
        review_count = None
        aggregate = item.get("aggregateRating") or {}
        if isinstance(aggregate, dict):
            rating_value = aggregate.get("ratingValue")
            review_count = aggregate.get("reviewCount") or aggregate.get("ratingCount")

        contains = item.get("containsPlace") or {}
        bedrooms = contains.get("numberOfBedrooms") if isinstance(contains, dict) else None
        bathrooms = contains.get("numberOfBathroomsTotal") if isinstance(contains, dict) else None

        offers = item.get("offers")
        offer_list = offers if isinstance(offers, list) else [offers] if offers else []
        price = None
        currency = "EUR"
        available = None
        for offer in offer_list:
            if not isinstance(offer, dict):
                continue
            availability = str(offer.get("availability", ""))
            if "InStock" in availability or "LimitedAvailability" in availability:
                available = True
            elif "SoldOut" in availability:
                available = False
            price = offer.get("price") or price
            currency = offer.get("priceCurrency") or currency

        return ScrapeResult(
            available=available,
            price_per_night=float(price) if price is not None else None,
            currency=currency,
            title=title,
            location_name=location_name,
            lat=float(lat) if lat is not None else None,
            lon=float(lon) if lon is not None else None,
            guests_max=guests,
            bedrooms=int(bedrooms) if bedrooms is not None else None,
            bathrooms=float(bathrooms) if bathrooms is not None else None,
            rating=float(rating_value) if rating_value is not None else None,
            review_count=int(review_count) if review_count is not None else None,
        )


class CustomHostAdapter:
    def __init__(self, host_pattern: str, adapter_id: str, display_name: str, delegate: ScraperAdapter) -> None:
        self.host_pattern = host_pattern.lower()
        self.adapter_id = adapter_id
        self.display_name = display_name
        self.delegate = delegate

    def matches(self, url: str) -> bool:
        host = hostname(url)
        return host == self.host_pattern or host.endswith(f".{self.host_pattern}")

    def scrape(self, url: str, check_in: date, check_out: date, guests: int) -> ScrapeResult:
        return self.delegate.scrape(url, check_in, check_out, guests)


class ScraperRegistry:
    def __init__(self) -> None:
        self._builtin = [HomeToGoAdapter(), JsonLdAdapter()]
        self._custom: list[CustomHostAdapter] = []

    def register_host(self, host_pattern: str, adapter_id: str | None = None) -> str:
        normalized = host_pattern.lower().removeprefix("www.")
        adapter_key = adapter_id or f"host:{normalized}"
        self._custom = [item for item in self._custom if item.host_pattern != normalized]
        self._custom.append(
            CustomHostAdapter(
                host_pattern=normalized,
                adapter_id=adapter_key,
                display_name=f"Custom host {normalized}",
                delegate=HomeToGoAdapter(),
            )
        )
        return adapter_key

    def list_adapters(self) -> list[tuple[str, str]]:
        seen = set()
        adapters: list[tuple[str, str]] = []
        for adapter in self._custom + self._builtin:
            if adapter.adapter_id in seen:
                continue
            seen.add(adapter.adapter_id)
            adapters.append((adapter.adapter_id, adapter.display_name))
        return adapters

    def detect(self, url: str) -> ScraperAdapter | None:
        for adapter in self._custom + self._builtin:
            if adapter.matches(url):
                return adapter
        return None

    def scrape(
        self,
        url: str,
        check_in: date,
        check_out: date,
        guests: int,
        adapter_id: str | None = None,
    ) -> ScrapeResult:
        adapter = None
        if adapter_id:
            for candidate in self._custom + self._builtin:
                if candidate.adapter_id == adapter_id:
                    adapter = candidate
                    break
        if adapter is None:
            adapter = self.detect(url)
        if adapter is None:
            return ScrapeResult(error="No scraper available for this URL.")
        return adapter.scrape(url, check_in, check_out, guests)
