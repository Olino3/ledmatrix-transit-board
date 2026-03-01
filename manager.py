from src.plugin_system.base_plugin import BasePlugin
from typing import Any, Dict


class TransitBoardPlugin(BasePlugin):
    """Generic GTFS-RT transit arrivals plugin.

    Displays upcoming arrivals for a configured station on any
    GTFS Realtime-compatible transit agency (NYC MTA, DC Metro,
    BART, Chicago L, and others).
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
        self.arrivals: list = []  # will hold parsed arrival data once implemented

    def update(self) -> None:
        """Fetch real-time arrival data from the GTFS-RT feed.

        Not yet implemented. Will parse TripUpdates protobuf feed
        and populate self.arrivals with (route_id, minutes) tuples.
        """
        self.logger.debug("transit-board: update() called (stub — not yet implemented)")

    def display(self, force_clear: bool = False) -> None:
        """Render arrival times to the LED matrix.

        Not yet implemented. Will draw route ID and minutes-to-arrival
        for each entry in self.arrivals.
        """
        self.logger.debug(
            "transit-board: display() called (stub) — %dx%d",
            self.display_manager.width,
            self.display_manager.height,
        )
        # Placeholder: clear so the plugin doesn't leave stale content
        self.display_manager.clear()

    def validate_config(self) -> bool:
        if not super().validate_config():
            return False
        # TODO: validate gtfs_rt_url format and station_id presence
        # when the implementation phase begins
        return True

    def on_config_change(self, new_config: Dict[str, Any]) -> None:
        super().on_config_change(new_config)
        # TODO: reinitialize API client if gtfs_rt_url or api_key changed
