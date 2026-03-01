# Transit Board — LEDMatrix Plugin

Displays real-time transit arrivals on your LED matrix using live **GTFS-RT** feeds.

Ships with a built-in **NYC MTA** preset and a **Custom** adapter for any GTFS-RT compatible agency worldwide.

```
┌──────────────────────────────┐
│ [N] Uptown & Queens          │
│  2m   7m  15m                │
└──────────────────────────────┘
```

---

## Features

- **Real-time arrivals** — polls GTFS-RT TripUpdates feeds every 30 seconds
- **Direction cycling** — one route+direction card at a time, cycling every N seconds
- **Colored route badges** — filled rectangle using each route's official color
- **Imminent highlight** — arrivals within the threshold shown in yellow for urgency
- **Live priority** — pre-empts other plugins when a train is < N minutes away
- **Station search** — find stop IDs by name in the LEDMatrix web UI (SQLite-backed)
- **Resilient data** — stale arrivals kept on network error; SQLite persists stop data offline
- **Multi-agency** — NYC MTA built in; add any GTFS-RT city via the custom adapter or new presets

---

## Installation

### Via LEDMatrix Plugin Store

1. Open the LEDMatrix web UI → **Plugins** → **Store**
2. Search for **Transit Board** and click **Install**

### Manual / Development

```bash
# Clone into LEDMatrix plugin repos
git clone https://github.com/your-org/ledmatrix-transit-board \
    /root/ledmatrix-transit-board

# Create the runtime symlink
ln -sf /root/ledmatrix-transit-board /root/LEDMatrix/plugins/transit-board

# Install Python dependencies into LEDMatrix's venv
/root/LEDMatrix/.venv/bin/pip install -r /root/ledmatrix-transit-board/requirements.txt
```

---

## Configuration

Open the web UI → **Plugins** → **Transit Board** → **Configure**, or edit `config/config.json`:

```jsonc
{
  "transit-board": {
    "enabled": true,
    "agency_id": "mta",
    "station_id": "R16",
    "route_ids": [],
    "display_duration": 15,
    "per_direction_secs": 4,
    "max_arrivals": 3,
    "live_priority": true,
    "live_threshold_mins": 2,
    "window_minutes": 30
  }
}
```

### Reference

| Field | Type | Default | Description |
|---|---|---|---|
| `agency_id` | string | `"mta"` | Agency preset. `"mta"` = NYC MTA; `"custom"` = supply your own URL |
| `station_id` | string | `""` | GTFS Stop ID to monitor (e.g. `"R16"` for Times Sq). **Required.** |
| `route_ids` | array | `[]` | Filter to specific routes (e.g. `["N","Q"]`). Empty = all routes at station |
| `display_duration` | number | `15` | Seconds this plugin holds the display before the next plugin cycles in |
| `per_direction_secs` | number | `4` | Seconds per direction card before cycling to the next direction |
| `max_arrivals` | integer | `3` | Max upcoming arrivals shown per direction (1–5) |
| `live_priority` | boolean | `false` | Pre-empt other plugins when a train is imminent |
| `live_threshold_mins` | integer | `2` | Minutes until arrival that triggers live priority (1–10) |
| `window_minutes` | integer | `30` | How far ahead to show arrivals in minutes (5–60) |
| `gtfs_rt_url` | string | `""` | TripUpdates feed URL — **required** when `agency_id = "custom"` |
| `api_key` | string | `""` | API key for the feed (most open feeds don't need this) |
| `api_key_header` | string | `"x-api-key"` | HTTP header name used to send `api_key` |

---

## Agency Setup

### NYC MTA

Set `agency_id` to `"mta"`. No API key required.

**Finding your station ID:**

1. Open the web UI → **Plugins** → **Transit Board** → search the **Station** field by name
   (e.g. `"Times Sq"` → select `R16`)
2. Or look up the [MTA Stations CSV](http://web.mta.info/developers/data/nyct/subway/Stations.csv) — the **Station ID** column is your `station_id`

Station data is downloaded automatically on first run from [data.ny.gov](https://data.ny.gov/api/v3/views/5f5g-n3cz/query.json) and cached locally in SQLite so the app works even when the endpoint is unreachable.

**Override with your own CSV:**

If you have a local MTA stations file, you can bootstrap the database from it by temporarily setting
`user_csv_path` to its absolute path and restarting (the plugin will import it and remove the setting).
The expected columns are: `Station ID`, `Stop Name`, `Daytime Routes`,
`North Direction Label`, `South Direction Label`, `GTFS Latitude`, `GTFS Longitude`.

### Custom / Any GTFS-RT Agency

Set `agency_id` to `"custom"` and supply:

```jsonc
{
  "transit-board": {
    "agency_id": "custom",
    "station_id": "place-davis",          // GTFS stop_id for your station
    "gtfs_rt_url": "https://cdn.mbta.com/realtime/TripUpdates.pb",
    "api_key": "",                         // optional
    "api_key_header": "x-api-key"         // optional
  }
}
```

The `stop_id` must match what appears in the agency's GTFS static feed (`stops.txt`).
For the stop name search to work in the web UI, you must also provide the agency's stops
via a custom CSV (same columns as MTA, or adapt the column map — see **Adding an Agency** below).

---

## Adding a New Agency Preset

1. Create `transit/agencies/<name>.py` implementing `TransitAgency`:

```python
from transit.agencies.base import TransitAgency, StopsSource

class MyAgency(TransitAgency):
    agency_id = "myagency"
    name = "My City Transit"

    def __init__(self, config: dict) -> None:
        self._config = config

    def get_feed_urls(self, stop_id: str, routes: list) -> list:
        # Return one or more GTFS-RT TripUpdates URLs for these routes.
        return ["https://realtime.myagency.com/TripUpdates.pb"]

    def get_api_headers(self) -> dict:
        # Return auth headers, or {} if the feed is open.
        key = self._config.get("api_key", "")
        header = self._config.get("api_key_header", "x-api-key")
        return {header: key} if key else {}

    def get_stops_source(self) -> StopsSource:
        return StopsSource(
            primary_url="https://myagency.com/stops.json",  # or ""
            fallback_url="https://myagency.com/stops.csv",  # or ""
            column_map={                                      # or None for MTA defaults
                "stop_id": "stop_id",
                "name": "stop_name",
                "routes": "routes",
                "north_label": "north_label",
                "south_label": "south_label",
                "lat": "stop_lat",
                "lng": "stop_lon",
            },
        )

    def get_line_color(self, route_id: str) -> str:
        colors = {"Red": "#DA291C", "Orange": "#ED8B00"}
        return colors.get(route_id, "#808183")
```

2. Register it in `transit/agency_registry.py`:

```python
from transit.agencies.myagency import MyAgency

REGISTRY = {
    "mta": MtaAgency,
    "custom": CustomAgency,
    "myagency": MyAgency,    # add this line
}
```

3. Add `"myagency"` to the `agency_id` enum in `config_schema.json`.

---

## Display Layout

```
Row  0-11:  [BADGE] Direction label (truncated to fit)
Row 12-22:  Arrival times   "2m  7m  15m"
```

- **Badge**: 10×10 px filled rectangle in the route's official color; route letter centered in contrasting white or black
- **Arrival colors**: green for normal arrivals; yellow for arrivals within `live_threshold_mins`
- **16-pixel-tall panels**: smaller badge (7×7 px) and fonts scale down automatically

---

## Development

### Running Tests

```bash
cd /root/ledmatrix-transit-board
/root/LEDMatrix/.venv/bin/pytest test/ -v
```

All 48 tests should pass. Tests use real protobuf parsing and real PIL image rendering — no mock shortcuts.

### Repository Structure

```
ledmatrix-transit-board/
├── manager.py               # TransitBoardPlugin — BasePlugin implementation
├── manifest.json            # Plugin metadata (id, version, entry_point)
├── config_schema.json       # JSON Schema for web UI config form
├── requirements.txt         # gtfs-realtime-bindings, protobuf, requests, Pillow
├── transit/
│   ├── models.py            # Arrival, StationInfo, StopsSource, DirectionGroup
│   ├── agency_registry.py   # REGISTRY dict + get_agency() factory
│   ├── gtfs_rt_client.py    # GTFS-RT protobuf fetch + parse → List[Arrival]
│   ├── stops_db.py          # SQLite-backed station name/ID store
│   ├── renderer.py          # PIL-based LED renderer (badge, times, no-data)
│   └── agencies/
│       ├── base.py          # TransitAgency ABC
│       ├── mta.py           # NYC MTA — feed mapping, line colors, stops source
│       └── custom.py        # Generic pass-through for user-supplied URL
└── test/
    ├── conftest.py          # Shared fixtures (protobuf feeds, CSV files, mocks)
    ├── test_gtfs_rt_client.py
    ├── test_stops_db.py
    ├── test_mta_agency.py
    ├── test_agency_registry.py
    ├── test_renderer.py
    └── test_manager.py
```

### Data Flow

```
config.station_id + config.route_ids
        │
        ▼
StopsDatabase.lookup(station_id)  ──► north_label / south_label
        │
        ▼
MtaAgency.get_feed_urls(stop_id, routes)  ──► ["https://api-endpoint.mta.info/..."]
        │
        ▼
GtfsRtClient.fetch_arrivals(urls, headers, stop_id, window)  ──► List[Arrival]
        │
        ▼
TransitBoardPlugin._group_arrivals(arrivals, station_info)  ──► List[DirectionGroup]
        │
        ▼
TransitRenderer.draw_direction_group(group, image)  ──► PIL Image
        │
        ▼
display_manager.update_display()
```

---

## Changelog

### v0.2.0
- Full GTFS-RT implementation — NYC MTA + custom agency support
- SQLite-backed station search with data.ny.gov API and CSV fallback
- Direction cycling with configurable dwell time
- Live priority takeover for imminent arrivals
- 48-test TDD suite

### v0.1.0
- Initial stub (display and update not implemented)
