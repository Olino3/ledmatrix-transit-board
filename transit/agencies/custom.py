"""
Custom agency adapter — passthrough for user-supplied GTFS-RT feed URL.
"""

from typing import Dict, List

from transit.agencies.base import TransitAgency
from transit.models import StopsSource


class CustomAgency(TransitAgency):
    agency_id = "custom"
    name = "Custom GTFS-RT Agency"

    def __init__(self, config: dict) -> None:
        self._url = config.get("gtfs_rt_url", "")
        self._api_key = config.get("api_key", "")
        self._api_key_header = config.get("api_key_header", "x-api-key")

    def get_feed_urls(self, stop_id: str, routes: List[str]) -> List[str]:
        return [self._url]

    def get_api_headers(self) -> Dict[str, str]:
        if self._api_key and self._api_key_header:
            return {self._api_key_header: self._api_key}
        return {}

    def get_stops_source(self) -> StopsSource:
        return StopsSource(primary_url="", fallback_url="", column_map={})
