"""
Abstract base class for transit agency adapters.
"""

from abc import ABC, abstractmethod
from typing import Dict, List

from transit.models import StopsSource


class TransitAgency(ABC):
    """
    Adapter interface for a transit agency.

    Concrete subclasses encapsulate agency-specific knowledge:
    - Which GTFS-RT feed URLs to query for a given stop/route combination
    - How to authenticate with the feed
    - Where to obtain static stop data (stops.txt / CSV / API)
    - Official line colors for rendering
    """

    agency_id: str
    name: str

    @abstractmethod
    def get_feed_urls(self, stop_id: str, routes: List[str]) -> List[str]:
        """
        Return the GTFS-RT feed URL(s) to query for this stop/routes combination.

        For agencies with a single unified feed this is always one URL.
        For MTA, multiple feed groups may be needed (ace, bdfm, nqrw, …).
        """

    @abstractmethod
    def get_api_headers(self) -> Dict[str, str]:
        """Return HTTP headers to include in feed requests (auth, etc.)."""

    @abstractmethod
    def get_stops_source(self) -> StopsSource:
        """Return information about where to fetch static stop data."""

    def get_line_color(self, route_id: str) -> str:
        """Return official hex color for a route badge. Gray by default."""
        return "#808183"
