"""
Tests for TransitBoardPlugin (manager.py) — plugin lifecycle and display cycling.

All tests are written BEFORE implementation (TDD RED phase).
"""

import pytest
import time
from unittest.mock import Mock, MagicMock, patch


PLUGIN_CONFIG = {
    "enabled": True,
    "display_duration": 15,
    "agency_id": "mta",
    "station_id": "R16",
    "route_ids": [],
    "max_arrivals": 3,
    "per_direction_secs": 4,
    "live_priority": True,
    "live_threshold_mins": 2,
    "window_minutes": 30,
}


def _make_direction_group(route_id="N", direction_label="Uptown", arrivals=None, color="#FCCC0A"):
    from transit.models import DirectionGroup
    return DirectionGroup(
        route_id=route_id,
        direction_label=direction_label,
        arrivals=arrivals if arrivals is not None else [5, 12],
        color=color,
    )


@pytest.fixture
def mock_deps(mock_display_manager, mock_cache_manager, mock_plugin_manager, tmp_path):
    """
    Fixture providing fully-mocked dependencies for TransitBoardPlugin.
    The GtfsRtClient and StopsDatabase are patched so no real I/O happens.
    """
    from transit.models import Arrival, DirectionGroup

    sample_arrivals = [
        Arrival(route_id="N", direction_id=1, direction_label="Uptown & Queens", minutes=5),
        Arrival(route_id="N", direction_id=0, direction_label="Downtown & Brooklyn", minutes=8),
    ]

    with (
        patch("transit.gtfs_rt_client.requests.get") as mock_http,
        patch("manager.StopsDatabase") as MockDB,
    ):
        # HTTP mock returns a valid feed (content doesn't matter since parse is also patched)
        mock_http.return_value = Mock(status_code=200, content=b"")

        # StopsDatabase mock: bootstrap is a no-op, lookup returns station info
        mock_db_instance = MagicMock()
        mock_db_instance.needs_bootstrap.return_value = False
        mock_db_instance.lookup.return_value = MagicMock(
            stop_id="R16",
            name="Times Sq-42 St",
            routes=["N", "Q", "R", "W"],
            north_label="Uptown & Queens",
            south_label="Downtown & Brooklyn",
        )
        MockDB.return_value = mock_db_instance

        yield {
            "display_manager": mock_display_manager,
            "cache_manager": mock_cache_manager,
            "plugin_manager": mock_plugin_manager,
            "sample_arrivals": sample_arrivals,
            "mock_db": mock_db_instance,
        }


def _make_plugin(config=None, deps=None):
    """Instantiate TransitBoardPlugin with given config and mock deps."""
    from manager import TransitBoardPlugin

    cfg = {**PLUGIN_CONFIG, **(config or {})}
    return TransitBoardPlugin(
        plugin_id="transit-board",
        config=cfg,
        display_manager=deps["display_manager"],
        cache_manager=deps["cache_manager"],
        plugin_manager=deps["plugin_manager"],
    )


class TestUpdatePopulatesGroups:
    def test_update_populates_direction_groups(self, mock_deps):
        """After update(), _groups is populated from fetched arrivals."""
        from transit.models import DirectionGroup

        plugin = _make_plugin(deps=mock_deps)
        groups = [
            _make_direction_group("N", "Uptown & Queens", [5, 12]),
            _make_direction_group("N", "Downtown & Brooklyn", [8, 16]),
        ]

        with patch.object(plugin, "_fetch_direction_groups", return_value=groups):
            plugin.update()

        assert len(plugin._groups) == 2
        assert all(isinstance(g, DirectionGroup) for g in plugin._groups)

    def test_stale_groups_retained_when_update_raises(self, mock_deps):
        """On network/parse error, existing _groups is preserved."""
        plugin = _make_plugin(deps=mock_deps)
        existing_group = _make_direction_group("N", "Uptown & Queens", [3])
        plugin._groups = [existing_group]

        with patch.object(plugin, "_fetch_direction_groups", side_effect=RuntimeError("feed down")):
            plugin.update()

        assert plugin._groups == [existing_group], "Stale data must be kept on error"


class TestDisplayCycling:
    def test_first_display_shows_index_zero(self, mock_deps):
        """First call to display() renders groups[0]."""
        plugin = _make_plugin(deps=mock_deps)
        plugin._groups = [
            _make_direction_group("N", "Uptown"),
            _make_direction_group("N", "Downtown"),
        ]
        plugin._current_idx = 0

        with patch.object(plugin._renderer, "draw_direction_group") as mock_draw:
            plugin.display()
            mock_draw.assert_called_once()
            called_group = mock_draw.call_args[0][0]
            assert called_group.direction_label == "Uptown"

    def test_display_advances_index_after_dwell_time(self, mock_deps):
        """Index advances to 1 after per_direction_secs have elapsed."""
        plugin = _make_plugin(deps=mock_deps)
        plugin._groups = [
            _make_direction_group("N", "Uptown"),
            _make_direction_group("N", "Downtown"),
        ]
        plugin._current_idx = 0
        # Simulate that enough time has passed
        plugin._last_display_time = time.monotonic() - 10  # 10s ago > 4s dwell

        with patch.object(plugin._renderer, "draw_direction_group"):
            plugin.display()

        assert plugin._current_idx == 1

    def test_display_index_wraps_after_last_group(self, mock_deps):
        """Index wraps back to 0 after the last direction group."""
        plugin = _make_plugin(deps=mock_deps)
        plugin._groups = [_make_direction_group("N", "Uptown")]
        plugin._current_idx = 0
        plugin._last_display_time = time.monotonic() - 10

        with patch.object(plugin._renderer, "draw_direction_group"):
            plugin.display()

        assert plugin._current_idx == 0, "Single-group list should always show index 0"

    def test_display_shows_no_data_when_groups_empty(self, mock_deps):
        """When _groups is empty, display() renders the no-data screen."""
        plugin = _make_plugin(deps=mock_deps)
        plugin._groups = []

        with patch.object(plugin._renderer, "draw_no_data") as mock_no_data:
            plugin.display()
            mock_no_data.assert_called_once()


class TestLivePriority:
    def test_live_content_true_when_arrival_under_threshold(self, mock_deps):
        """has_live_content() is True when any arrival is < live_threshold_mins."""
        plugin = _make_plugin(config={"live_priority": True, "live_threshold_mins": 2}, deps=mock_deps)
        plugin._groups = [_make_direction_group(arrivals=[1, 8])]  # 1 min < 2 min threshold

        assert plugin.has_live_content() is True

    def test_live_content_false_when_no_imminent_trains(self, mock_deps):
        """has_live_content() is False when all arrivals are >= live_threshold_mins."""
        plugin = _make_plugin(config={"live_priority": True, "live_threshold_mins": 2}, deps=mock_deps)
        plugin._groups = [_make_direction_group(arrivals=[5, 12])]  # all >= 2 min

        assert plugin.has_live_content() is False

    def test_live_content_false_when_live_priority_disabled(self, mock_deps):
        """has_live_content() is always False when live_priority=False in config."""
        plugin = _make_plugin(config={"live_priority": False, "live_threshold_mins": 2}, deps=mock_deps)
        plugin._groups = [_make_direction_group(arrivals=[0])]  # arriving NOW

        assert plugin.has_live_content() is False


class TestValidateConfig:
    def test_validate_config_fails_without_station_id(self, mock_deps):
        """validate_config() returns False when station_id is missing."""
        plugin = _make_plugin(config={"station_id": ""}, deps=mock_deps)

        assert plugin.validate_config() is False

    def test_validate_config_fails_with_invalid_agency_id(self, mock_deps):
        """validate_config() returns False for an unrecognised agency_id."""
        plugin = _make_plugin(config={"agency_id": "notanagency"}, deps=mock_deps)

        assert plugin.validate_config() is False

    def test_validate_config_fails_for_custom_agency_without_gtfs_rt_url(self, mock_deps):
        """validate_config() returns False when agency_id='custom' and gtfs_rt_url is empty."""
        plugin = _make_plugin(
            config={"agency_id": "custom", "gtfs_rt_url": ""},
            deps=mock_deps,
        )

        assert plugin.validate_config() is False


class TestConfigChange:
    def test_on_config_change_resets_groups_and_index(self, mock_deps):
        """on_config_change() clears _groups and resets _current_idx to 0."""
        plugin = _make_plugin(deps=mock_deps)
        plugin._groups = [_make_direction_group()]
        plugin._current_idx = 1

        plugin.on_config_change({**PLUGIN_CONFIG, "station_id": "D17"})

        assert plugin._groups == [], "_groups must be cleared on config change"
        assert plugin._current_idx == 0, "_current_idx must reset on config change"
