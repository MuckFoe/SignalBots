from __future__ import annotations

import logging
from datetime import date, datetime

from drive_time import driving_time_minutes
from scrape_types import ScrapeResult
from scrapers import ScraperRegistry
from storage import Storage
from utils import hostname, parse_date

logger = logging.getLogger(__name__)


class Poller:
    def __init__(self, storage: Storage, registry: ScraperRegistry) -> None:
        self.storage = storage
        self.registry = registry

    def poll_listing_row(self, row) -> tuple[bool, ScrapeResult]:
        check_in = parse_date(row["check_in"])
        check_out = parse_date(row["check_out"])
        if check_in is None or check_out is None:
            result = ScrapeResult(error="Invalid stored dates.")
            self.storage.apply_poll_result(row["id"], result, row["drive_minutes"], row["drive_km"])
            return False, result

        result = self.registry.scrape(
            row["url"],
            check_in,
            check_out,
            row["guests"],
            adapter_id=row["adapter_id"],
        )
        drive_minutes, drive_km = self._drive_for_scope(row["scope_id"], result, row)
        changed = self.storage.apply_poll_result(row["id"], result, drive_minutes, drive_km)
        return changed, result

    def poll_all(self) -> list[tuple[object, bool, ScrapeResult]]:
        outcomes = []
        for row in self.storage.list_all_active_listings():
            try:
                changed, result = self.poll_listing_row(row)
                outcomes.append((row, changed, result))
            except Exception:
                logger.exception("Failed polling listing %s", row["label"])
        self.storage.set_poll_state("last_poll_at", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
        return outcomes

    def initial_scrape(
        self,
        scope_id: str,
        url: str,
        adapter_id: str,
        check_in: date,
        check_out: date,
        guests: int,
    ) -> tuple[ScrapeResult, int | None, float | None]:
        result = self.registry.scrape(url, check_in, check_out, guests, adapter_id=adapter_id)
        drive_minutes, drive_km = self._drive_for_scope(scope_id, result, None)
        return result, drive_minutes, drive_km

    def _drive_for_scope(self, scope_id: str, result: ScrapeResult, row) -> tuple[int | None, float | None]:
        if result.lat is None or result.lon is None:
            if row is not None and row["drive_minutes"] is not None:
                return row["drive_minutes"], row["drive_km"]
            return None, None
        origin_name, origin_lat, origin_lon = self.storage.get_drive_origin(scope_id)
        del origin_name
        return driving_time_minutes(origin_lat, origin_lon, result.lat, result.lon)


def load_custom_hosts(storage: Storage, registry: ScraperRegistry) -> None:
    for row in storage.list_all_custom_hosts():
        registry.register_host(row["host_pattern"], row["adapter_id"])
