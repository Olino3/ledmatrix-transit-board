"""
TransitBoardPlugin — LED matrix display for real-time transit arrivals.

Supports any GTFS-RT compatible agency via the agency adapter pattern.
Ships with a built-in NYC MTA preset; add more in transit/agencies/.

Display: one route+direction at a time, cycling every per_direction_secs.
Live priority: pre-empts other plugins when a train is < live_threshold_mins away.
"""

import time
from typing import Any, Dict, List, Optional

from PIL import Image

from src.plugin_system.base_plugin import BasePlugin
from src.logging_config import get_logger

from transit.agency_registry import REGISTRY, get_agency
from transit.gtfs_rt_client import GtfsRtClient, GtfsRtError
from transit.models import Arrival, DirectionGroup
from transit.renderer import TransitRenderer
from transit.stops_db import StopsDatabase


class TransitBoardPlugin(BasePlugin):
    """
    Displays real-time transit arrivals for a configured station.

    Config keys (in addition to standard BasePlugin keys):
      agency_id           str   "mta" or "custom"               required
      station_id          str   GTFS stop ID (e.g. "R16")        required
      route_ids           list  filter to specific routes []      optional
      per_direction_secs  int   seconds per direction card [4]   optional
      live_priority       bool  enable live priority [false]      optional
      live_threshold_mins int   imminent-train threshold [2]      optional
      window_minutes      int   arrival look-ahead minutes [30]   optional
      gtfs_rt_url         str   custom agency URL only            optional
    """

    def __init__(
        self,
        plugin_id: str,
        config: Dict[str, Any],
        display_manager: Any,
        cache_manager: Any,
        plugin_manager: Any,
    ) -> None:
        super().__init__(plugin_id, config, display_manager, cache_manager, plugin_manager)

        self._groups: List[DirectionGroup] = []
        self._current_idx: int = 0
        self._last_display_time: float = time.monotonic()  # prevents immediate advance on first display

        agency_id = config.get("agency_id", "mta")
        try:
            self._agency = get_agency(agency_id, config)
        except ValueError:
            # Invalid agency_id — validate_config() will report the error
            self._agency = get_agency("custom", config)
        self._gtfs_client = GtfsRtClient()
        self._renderer = TransitRenderer(display_manager)

        db_path = self._db_path()
        self._stops_db = StopsDatabase(db_path)
        self._ensure_stops_db()

    # ------------------------------------------------------------------
    # BasePlugin abstract methods
    # ------------------------------------------------------------------

    def update(self) -> None:
        """Fetch real-time arrivals and group by route+direction."""
        try:
            groups = self._fetch_direction_groups()
            self._groups = groups
        except Exception as exc:
            self.logger.warning("transit-board update failed (keeping stale data): %s", exc)

    def display(self, force_clear: bool = False) -> None:
        """Render current direction group; advance index after dwell time."""
        if force_clear:
            self.display_manager.clear()

        image = Image.new(
            "RGB",
            (self.display_manager.width, self.display_manager.height),
            (0, 0, 0),
        )

        if not self._groups:
            self._renderer.draw_no_data(image)
        else:
            self._maybe_advance_index()
            group = self._groups[self._current_idx % len(self._groups)]
            threshold = self.config.get("live_threshold_mins", 2)
            self._renderer.draw_direction_group(group, image, imminent_threshold=threshold)

        self.display_manager.image.paste(image)
        self.display_manager.update_display()

    # ------------------------------------------------------------------
    # Live priority
    # ------------------------------------------------------------------

    def has_live_priority(self) -> bool:
        return self.config.get("live_priority", False)

    def has_live_content(self) -> bool:
        if not self.config.get("live_priority", False):
            return False
        threshold = self.config.get("live_threshold_mins", 2)
        return any(
            g.arrivals and g.arrivals[0] < threshold
            for g in self._groups
        )

    # ------------------------------------------------------------------
    # Config validation and hot-reload
    # ------------------------------------------------------------------

    def validate_config(self) -> bool:
        if not super().validate_config():
            return False

        station_id = self.config.get("station_id", "").strip()
        if not station_id:
            self.logger.error("transit-board: 'station_id' is required")
            return False

        agency_id = self.config.get("agency_id", "mta")
        if agency_id not in REGISTRY:
            self.logger.error(
                "transit-board: unknown agency_id '%s'. Available: %s",
                agency_id,
                sorted(REGISTRY),
            )
            return False

        if agency_id == "custom" and not self.config.get("gtfs_rt_url", "").strip():
            self.logger.error(
                "transit-board: 'gtfs_rt_url' is required when agency_id='custom'"
            )
            return False

        return True

    def on_config_change(self, new_config: Dict[str, Any]) -> None:
        super().on_config_change(new_config)
        # Re-instantiate agency in case agency_id or credentials changed
        agency_id = new_config.get("agency_id", "mta")
        try:
            self._agency = get_agency(agency_id, new_config)
        except ValueError:
            self.logger.warning(
                "transit-board: invalid agency_id on config change: %s", agency_id
            )
        # Rebuild stops DB (db path is keyed by agency_id; may have changed)
        self._stops_db = StopsDatabase(self._db_path())
        self._ensure_stops_db()
        # Clear state so next update() fetches fresh data
        self._groups = []
        self._current_idx = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_direction_groups(self) -> List[DirectionGroup]:
        """Fetch GTFS-RT arrivals and return grouped DirectionGroups."""
        station_id = self.config.get("station_id", "")
        route_filter = self.config.get("route_ids", [])
        window = self.config.get("window_minutes", 30)

        station_info = self._stops_db.lookup(station_id)
        routes = route_filter or (station_info.routes if station_info else [])

        feed_urls = self._agency.get_feed_urls(station_id, routes)
        headers = self._agency.get_api_headers()

        arrivals = self._gtfs_client.fetch_arrivals(
            feed_urls=feed_urls,
            headers=headers,
            stop_id=station_id,
            window_minutes=window,
        )

        return self._group_arrivals(arrivals, station_info)

    def _group_arrivals(
        self,
        arrivals: List[Arrival],
        station_info: Optional[Any],
    ) -> List[DirectionGroup]:
        """
        Group Arrival objects by route+direction and build DirectionGroups.

        Direction label resolution (ported from subway.py format_arrivals):
          - suffix "N" → station_info.north_label
          - suffix "S" → station_info.south_label
          - else        → direction_id fallback (1=north, 0=south)
        """
        north = station_info.north_label if station_info else "Uptown"
        south = station_info.south_label if station_info else "Downtown"

        buckets: Dict[str, Dict] = {}
        for arrival in arrivals:
            suffix = arrival.direction_label  # raw suffix from GtfsRtClient
            if suffix == "N":
                label = north
            elif suffix == "S":
                label = south
            else:
                label = north if arrival.direction_id == 1 else south

            key = f"{arrival.route_id}_{label}"
            if key not in buckets:
                buckets[key] = {
                    "route_id": arrival.route_id,
                    "label": label,
                    "times": [],
                }
            buckets[key]["times"].append(arrival.minutes)

        groups: List[DirectionGroup] = []
        for data in buckets.values():
            times = sorted(data["times"])[: self.config.get("max_arrivals", 3)]
            groups.append(
                DirectionGroup(
                    route_id=data["route_id"],
                    direction_label=data["label"],
                    arrivals=times,
                    color=self._agency.get_line_color(data["route_id"]),
                )
            )

        groups.sort(key=lambda g: g.arrivals[0] if g.arrivals else 999)
        return groups

    def _maybe_advance_index(self) -> None:
        dwell = self.config.get("per_direction_secs", 4)
        now = time.monotonic()
        if now - self._last_display_time >= dwell:
            if self._groups:
                self._current_idx = (self._current_idx + 1) % len(self._groups)
            self._last_display_time = now

    def _db_path(self) -> str:
        cache_dir = self.cache_manager.get_cache_dir()
        agency_id = self.config.get("agency_id", "mta")
        return f"{cache_dir}/transit_stops_{agency_id}.db"

    def _ensure_stops_db(self) -> None:
        if self._stops_db.needs_bootstrap():
            try:
                self._stops_db.bootstrap(self._agency)
            except Exception as exc:
                self.logger.warning("Could not bootstrap stops DB: %s", exc)
