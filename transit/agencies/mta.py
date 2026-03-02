"""
NYC MTA subway agency adapter.

Feed mapping and line colors ported from:
  /root/star-wars-dashboard/backend/utils/subway.py
"""

from typing import Dict, List

from transit.agencies.base import TransitAgency
from transit.models import StopsSource

# Maps route_id → MTA feed group name
# MTA now uses line-group names instead of numeric feed IDs
MTA_FEED_MAPPING: Dict[str, str] = {
    "A": "ace", "C": "ace", "E": "ace", "H": "ace", "FS": "ace",
    "B": "bdfm", "D": "bdfm", "F": "bdfm", "M": "bdfm",
    "G": "g",
    "J": "jz", "Z": "jz",
    "L": "l",
    "N": "nqrw", "Q": "nqrw", "R": "nqrw", "W": "nqrw",
    "1": "123456", "2": "123456", "3": "123456",
    "4": "123456", "5": "123456", "6": "123456",
    "7": "7",
    "SI": "si",
}

# Official MTA subway line colors (hex)
MTA_LINE_COLORS: Dict[str, str] = {
    "A": "#0039A6", "C": "#0039A6", "E": "#0039A6",
    "B": "#FF6319", "D": "#FF6319", "F": "#FF6319", "M": "#FF6319",
    "G": "#6CBE45",
    "J": "#996633", "Z": "#996633",
    "L": "#A7A9AC",
    "N": "#FCCC0A", "Q": "#FCCC0A", "R": "#FCCC0A", "W": "#FCCC0A",
    "1": "#EE352E", "2": "#EE352E", "3": "#EE352E",
    "4": "#00933C", "5": "#00933C", "6": "#00933C",
    "7": "#B933AD",
    "S": "#808183",
}

# Fallback feed groups used when no routes are known
_ALL_MAJOR_FEEDS = ["123456", "nqrw", "bdfm", "ace", "g", "jz", "l", "7", "si"]

# Column mapping for MTA Stations.csv
# "GTFS Stop ID" (e.g. "R16") is the user-facing stop identifier.
# "Station ID" is the numeric internal ID; stored for reference.
MTA_CSV_COLUMN_MAP = {
    "stop_id": "GTFS Stop ID",
    "station_id": "Station ID",
    "name": "Stop Name",
    "routes": "Daytime Routes",
    "north_label": "North Direction Label",
    "south_label": "South Direction Label",
    "lat": "GTFS Latitude",
    "lng": "GTFS Longitude",
}

_BASE_FEED_URL = (
    "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-{group}"
)


class MtaAgency(TransitAgency):
    agency_id = "mta"
    name = "NYC MTA"

    def __init__(self, config: dict) -> None:
        self._config = config

    def get_feed_urls(self, stop_id: str, routes: List[str]) -> List[str]:
        """Return deduplicated GTFS-RT feed URLs for the given routes."""
        feed_groups: set = set()
        for route in routes:
            group = MTA_FEED_MAPPING.get(route)
            if group:
                feed_groups.add(group)

        if not feed_groups:
            feed_groups = set(_ALL_MAJOR_FEEDS)

        return [_BASE_FEED_URL.format(group=g) for g in sorted(feed_groups)]

    def get_api_headers(self) -> Dict[str, str]:
        return {}  # MTA no longer requires an API key

    def get_stops_source(self) -> StopsSource:
        return StopsSource(
            primary_url="",  # data.ny.gov requires a Socrata app token; skip to fallback
            fallback_url="http://web.mta.info/developers/data/nyct/subway/Stations.csv",
            column_map=MTA_CSV_COLUMN_MAP,
        )

    def get_line_color(self, route_id: str) -> str:
        return MTA_LINE_COLORS.get(route_id, "#808183")
