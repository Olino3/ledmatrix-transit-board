"""
Shared fixtures for transit-board plugin tests.
"""

import os
import sys
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock, Mock
from PIL import Image

# Ensure plugin repo root is importable
PLUGIN_ROOT = Path(__file__).parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

# Ensure LEDMatrix core is importable (for BasePlugin)
LEDMATRIX_ROOT = Path("/root/LEDMatrix")
if str(LEDMATRIX_ROOT) not in sys.path:
    sys.path.insert(0, str(LEDMATRIX_ROOT))

# Switch to emulator mode so LEDMatrix imports don't need hardware
os.environ.setdefault("EMULATOR", "true")


# ---------------------------------------------------------------------------
# Display manager mocks
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_display_manager():
    """Mock DisplayManager (128×32)."""
    dm = MagicMock()
    dm.width = 128
    dm.height = 32
    dm.image = Image.new("RGB", (128, 32), (0, 0, 0))
    dm.clear = Mock()
    dm.update_display = Mock()
    return dm


@pytest.fixture
def mock_display_manager_16():
    """Mock DisplayManager with 16px height for small-display tests."""
    dm = MagicMock()
    dm.width = 64
    dm.height = 16
    dm.image = Image.new("RGB", (64, 16), (0, 0, 0))
    dm.clear = Mock()
    dm.update_display = Mock()
    return dm


@pytest.fixture
def mock_cache_manager(tmp_path):
    """Mock CacheManager whose cache_dir points to a temp directory."""
    cm = MagicMock()
    cm.get_cache_dir = Mock(return_value=str(tmp_path))
    cm.get = Mock(return_value=None)
    cm.set = Mock()
    return cm


@pytest.fixture
def mock_plugin_manager():
    pm = MagicMock()
    pm.plugin_manifests = {}
    return pm


# ---------------------------------------------------------------------------
# GTFS-RT protobuf fixtures
# ---------------------------------------------------------------------------

def _build_feed(stop_id, entries):
    """
    Build a minimal GTFS-RT FeedMessage.

    entries: list of dicts with keys:
        route_id, direction_id, stop_suffix ("N"|"S"), delta_seconds
    delta_seconds > 0 = future; < 0 = past
    """
    from google.transit import gtfs_realtime_pb2

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = int(time.time())
    now = int(time.time())

    for i, entry in enumerate(entries):
        entity = feed.entity.add()
        entity.id = f"trip_{i}"
        tu = entity.trip_update
        tu.trip.route_id = entry["route_id"]
        tu.trip.direction_id = entry["direction_id"]

        stu = tu.stop_time_update.add()
        stu.stop_id = f"{stop_id}{entry['stop_suffix']}"
        stu.arrival.time = now + entry["delta_seconds"]

    return feed


@pytest.fixture
def sample_feed_bytes():
    """Binary GTFS-RT feed with 3 future arrivals and 1 past arrival at stop R16."""
    feed = _build_feed("R16", [
        {"route_id": "N", "direction_id": 1, "stop_suffix": "N", "delta_seconds": 5 * 60},   # 5 min future
        {"route_id": "N", "direction_id": 0, "stop_suffix": "S", "delta_seconds": 8 * 60},   # 8 min future
        {"route_id": "Q", "direction_id": 1, "stop_suffix": "N", "delta_seconds": 12 * 60},  # 12 min future
        {"route_id": "N", "direction_id": 1, "stop_suffix": "N", "delta_seconds": -3 * 60},  # 3 min PAST
    ])
    return feed.SerializeToString()


@pytest.fixture
def beyond_window_feed_bytes():
    """GTFS-RT feed where one arrival is beyond the 30-minute window."""
    feed = _build_feed("R16", [
        {"route_id": "N", "direction_id": 1, "stop_suffix": "N", "delta_seconds": 5 * 60},   # in window
        {"route_id": "N", "direction_id": 1, "stop_suffix": "N", "delta_seconds": 35 * 60},  # beyond window
    ])
    return feed.SerializeToString()


@pytest.fixture
def empty_feed_bytes():
    """GTFS-RT feed with no trip updates."""
    from google.transit import gtfs_realtime_pb2
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = int(time.time())
    return feed.SerializeToString()


@pytest.fixture
def unsorted_feed_bytes():
    """GTFS-RT feed where arrivals are not in time order."""
    feed = _build_feed("R16", [
        {"route_id": "N", "direction_id": 1, "stop_suffix": "N", "delta_seconds": 15 * 60},
        {"route_id": "N", "direction_id": 1, "stop_suffix": "N", "delta_seconds": 3 * 60},
        {"route_id": "N", "direction_id": 1, "stop_suffix": "N", "delta_seconds": 9 * 60},
    ])
    return feed.SerializeToString()


# ---------------------------------------------------------------------------
# Stops CSV fixtures
# ---------------------------------------------------------------------------

SAMPLE_STOPS_CSV = """\
Station ID,Complex ID,GTFS Stop ID,Division,Line,Stop Name,Borough,Daytime Routes,Structure,GTFS Latitude,GTFS Longitude,North Direction Label,South Direction Label
436,436,R16,IND,Queens Blvd,Times Sq-42 St,M,N Q R W,Subway,40.7549,-73.9878,Uptown & Queens,Downtown & Brooklyn
321,321,D17,IND,Concourse,Bedford Park Blvd,Bx,B D,Subway,40.8729,-73.8826,Norwood-205 St,Manhattan
289,289,A32,IND,8th Av,Fulton St,M,A C,Subway,40.7206,-74.0089,Uptown & The Bronx,Downtown & Brooklyn
"""


@pytest.fixture
def sample_stops_csv_path(tmp_path):
    p = tmp_path / "stops.csv"
    p.write_text(SAMPLE_STOPS_CSV)
    return str(p)


@pytest.fixture
def malformed_stops_csv_path(tmp_path):
    """CSV with one good row and one malformed (missing columns) row."""
    content = (
        "Station ID,Complex ID,GTFS Stop ID,Division,Line,Stop Name,Borough,"
        "Daytime Routes,Structure,GTFS Latitude,GTFS Longitude,North Direction Label,South Direction Label\n"
        "436,436,R16,IND,Queens Blvd,Times Sq-42 St,M,N Q R W,Subway,40.7549,-73.9878,Uptown & Queens,Downtown & Brooklyn\n"
        "BADROW,,\n"
    )
    p = tmp_path / "malformed.csv"
    p.write_text(content)
    return str(p)


# ---------------------------------------------------------------------------
# data.ny.gov API response fixture
# ---------------------------------------------------------------------------

DATANY_RESPONSE = {
    "data": [
        {
            "Station ID": "436",
            "Complex ID": "436",
            "GTFS Stop ID": "R16",
            "Division": "IND",
            "Line": "Queens Blvd",
            "Stop Name": "Times Sq-42 St",
            "Borough": "M",
            "Daytime Routes": "N Q R W",
            "Structure": "Subway",
            "GTFS Latitude": "40.7549",
            "GTFS Longitude": "-73.9878",
            "North Direction Label": "Uptown & Queens",
            "South Direction Label": "Downtown & Brooklyn",
        },
        {
            "Station ID": "321",
            "Complex ID": "321",
            "GTFS Stop ID": "D17",
            "Division": "IND",
            "Line": "Concourse",
            "Stop Name": "Bedford Park Blvd",
            "Borough": "Bx",
            "Daytime Routes": "B D",
            "Structure": "Subway",
            "GTFS Latitude": "40.8729",
            "GTFS Longitude": "-73.8826",
            "North Direction Label": "Norwood-205 St",
            "South Direction Label": "Manhattan",
        },
    ]
}


# ---------------------------------------------------------------------------
# TransitAgency stub for unit tests that don't need real agencies
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock


def make_mock_agency(agency_id="mta", feed_urls=None, headers=None, line_color="#FCCC0A"):
    agency = MagicMock()
    agency.agency_id = agency_id
    agency.get_feed_urls = Mock(return_value=feed_urls or ["http://feed.example.com/gtfs"])
    agency.get_api_headers = Mock(return_value=headers or {})
    agency.get_line_color = Mock(return_value=line_color)
    agency.name = "Test Agency"
    return agency
