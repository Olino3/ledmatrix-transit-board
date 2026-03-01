"""
Generic GTFS-RT feed fetcher and parser.

Ported and generalised from:
  /root/star-wars-dashboard/backend/utils/subway.py :: parse_mta_feed()
"""

import time
from typing import Dict, List

import requests
from google.transit import gtfs_realtime_pb2

from transit.models import Arrival


class GtfsRtError(Exception):
    """Raised when a GTFS-RT feed cannot be fetched or is malformed."""


class GtfsRtClient:
    """Fetches GTFS-RT feeds and parses them into Arrival objects."""

    def fetch_arrivals(
        self,
        feed_urls: List[str],
        headers: Dict[str, str],
        stop_id: str,
        window_minutes: int = 30,
    ) -> List[Arrival]:
        """
        Fetch and merge arrivals from all feed_urls for stop_id.

        Args:
            feed_urls: One or more GTFS-RT TripUpdates feed URLs.
            headers: HTTP headers to include (auth, etc.).
            stop_id: The GTFS stop ID prefix to filter for (e.g. "R16").
            window_minutes: Maximum minutes ahead to include arrivals.

        Returns:
            Arrivals sorted by minutes ascending.

        Raises:
            GtfsRtError: If any feed URL returns a non-200 response.
        """
        arrivals: List[Arrival] = []

        for url in feed_urls:
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code != 200:
                    raise GtfsRtError(
                        f"Feed returned HTTP {response.status_code}: {url}"
                    )
                arrivals.extend(
                    self._parse_feed_bytes(
                        response.content, stop_id, window_minutes
                    )
                )
            except GtfsRtError:
                raise
            except requests.RequestException as exc:
                raise GtfsRtError(f"Network error fetching {url}: {exc}") from exc

        arrivals.sort(key=lambda a: a.minutes)
        return arrivals

    def _parse_feed_bytes(
        self,
        feed_bytes: bytes,
        stop_id: str,
        window_minutes: int = 30,
    ) -> List[Arrival]:
        """
        Parse raw protobuf bytes into Arrival objects for stop_id.

        Ported from parse_mta_feed() in subway.py:
        - Matches stop_id by prefix (MTA appends N/S direction suffix)
        - Calculates minutes = (arrival_time - now) / 60
        - Filters: 0 <= minutes <= window_minutes
        """
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(feed_bytes)

        arrivals: List[Arrival] = []
        now = int(time.time())

        for entity in feed.entity:
            if not entity.HasField("trip_update"):
                continue

            trip = entity.trip_update
            route_id = trip.trip.route_id if trip.trip.HasField("route_id") else ""
            direction_id = (
                trip.trip.direction_id if trip.trip.HasField("direction_id") else 0
            )

            for stu in trip.stop_time_update:
                if not stu.stop_id.startswith(stop_id):
                    continue

                # Prefer arrival time; fall back to departure
                if stu.HasField("arrival"):
                    ts = stu.arrival.time
                elif stu.HasField("departure"):
                    ts = stu.departure.time
                else:
                    continue

                minutes = int((ts - now) / 60)

                if 0 <= minutes <= window_minutes:
                    # Derive direction_label from stop_id suffix (N/S)
                    suffix = stu.stop_id[len(stop_id):]
                    direction_label = suffix  # raw suffix; manager resolves labels

                    arrivals.append(
                        Arrival(
                            route_id=route_id,
                            direction_id=direction_id,
                            direction_label=direction_label,
                            minutes=minutes,
                        )
                    )

        arrivals.sort(key=lambda a: a.minutes)
        return arrivals
