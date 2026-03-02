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
- **Imminent highlight** — arrivals within `live_threshold_mins` shown in yellow
- **Live priority** — pre-empts other plugins when a train is `< live_threshold_mins` away
- **Station search** — find stop IDs by name in the LEDMatrix web UI (SQLite-backed)
- **Resilient data** — stale arrivals kept on network error; SQLite persists stop data offline
- **Multi-agency** — NYC MTA built in; add any GTFS-RT city via the custom adapter or new presets

---

## Quick Start (NYC MTA)

1. Install the plugin (see [Installation](#installation))
2. Find your station's GTFS Stop ID (see [Finding your station ID](#finding-your-station-id))
3. Add to `config/config.json`:

```jsonc
{
  "transit-board": {
    "enabled": true,
    "agency_id": "mta",
    "station_id": "R16"
  }
}
```

4. Restart the display. The plugin bootstraps its station database on first run.

---

## Installation

### Via LEDMatrix Plugin Store

1. Open the LEDMatrix web UI → **Plugins** → **Store**
2. Search for **Transit Board** and click **Install**

### Manual / Development

The plugin ships as a git submodule inside the LEDMatrix repository at `plugin-repos/transit-board`.

```bash
# From the LEDMatrix root directory

# Initialise the submodule (included in a full --recursive clone, or run explicitly)
git submodule update --init plugin-repos/transit-board

# Create the runtime symlink (plugins/ is gitignored)
ln -sf "$PWD/plugin-repos/transit-board" plugins/transit-board

# Install Python dependencies into LEDMatrix's venv
.venv/bin/pip install -r plugin-repos/transit-board/requirements.txt
```

**Contributing / working on the plugin source directly:**

```bash
# Fork https://github.com/Olino3/ledmatrix-transit-board, then point the submodule at your fork
cd plugin-repos/transit-board
git remote set-url origin https://github.com/<your-fork>/ledmatrix-transit-board
git checkout -b my-feature

# Or clone your fork separately and link it
git clone https://github.com/<your-fork>/ledmatrix-transit-board
ln -sf "$PWD/ledmatrix-transit-board" /path/to/LEDMatrix/plugins/transit-board
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
| `live_threshold_mins` | integer | `2` | Minutes until arrival that triggers live priority **and** yellow highlight (1–10) |
| `window_minutes` | integer | `30` | How far ahead to show arrivals in minutes (5–60) |
| `gtfs_rt_url` | string | `""` | TripUpdates feed URL — **required** when `agency_id = "custom"` |
| `api_key` | string | `""` | API key for the feed (most open feeds don't need this — store in secrets, see below) |
| `api_key_header` | string | `"x-api-key"` | HTTP header name used to send `api_key` |

### Storing an API key securely

If your agency requires an API key, keep it out of `config.json` by placing it in `config/config_secrets.json` instead (this file is gitignored). The LEDMatrix runtime merges secrets into plugin configs automatically:

```jsonc
// config/config_secrets.json
{
  "transit-board": {
    "api_key": "your-actual-key-here"
  }
}
```

A template entry is provided in `config/config_secrets.template.json`.

---

## Agency Setup

### NYC MTA

Set `agency_id` to `"mta"`. No API key required — the MTA GTFS-RT feeds are open.

#### Finding your station ID

The `station_id` field expects the **GTFS Stop ID** for your station (e.g. `R16`, `B18`, `D17`).

**Option 1 — Station search in the web UI:**

Open the web UI → **Plugins** → **Transit Board** → use the **Search Stations** action and type part of the station name (e.g. `"79 St"`, `"Atlantic Av"`, `"Times Sq"`).

> The search requires the station database to be bootstrapped first. Enable the plugin and let it run once, then try again.

**Option 2 — MTA Stations CSV:**

Download [Stations.csv](http://web.mta.info/developers/data/nyct/subway/Stations.csv) from the MTA developer portal. The **GTFS Stop ID** column (third column) is your `station_id` — not the numeric **Station ID** column.

```
Station ID  Complex ID  GTFS Stop ID  ...  Stop Name        Daytime Routes
65          65          B18                79 St            D
436         436         R16                Times Sq-42 St   N Q R W
```

Use the value from **GTFS Stop ID** (`B18`, `R16`), not the numeric ID (`65`, `436`).

#### Station database

On first run the plugin downloads `Stations.csv` from the MTA developer site and stores it in a local SQLite database (in the LEDMatrix cache directory). This database is used for:

- Resolving direction labels (`"Uptown & Queens"`, `"Coney Island"`)
- Selecting only the relevant GTFS-RT feeds for your station's routes

If bootstrap fails (no network), the plugin still displays arrivals with generic `"Uptown"` / `"Downtown"` labels and fetches all feed groups until the database is available.

**Override with your own CSV:**

If you have a local MTA stations file, you can bootstrap the database from it:

1. Call `StopsDatabase.import_csv(path, column_map=MTA_CSV_COLUMN_MAP)` from a script, or
2. Pass `user_csv_path` to `db.bootstrap(agency, user_csv_path="/path/to/file.csv")`

The expected columns match the standard MTA Stations CSV:
`GTFS Stop ID`, `Station ID`, `Stop Name`, `Daytime Routes`, `North Direction Label`, `South Direction Label`, `GTFS Latitude`, `GTFS Longitude`.

### Custom / Any GTFS-RT Agency

Set `agency_id` to `"custom"` and supply:

```jsonc
{
  "transit-board": {
    "agency_id": "custom",
    "station_id": "place-davis",
    "gtfs_rt_url": "https://cdn.mbta.com/realtime/TripUpdates.pb",
    "api_key": "",
    "api_key_header": "x-api-key"
  }
}
```

The `station_id` must match a `stop_id` from the agency's GTFS static feed (`stops.txt`). The plugin matches by prefix — so stop ID `B18` matches both `B18N` and `B18S` in the feed.

For the station name search to work in the web UI you must bootstrap the stops database manually (see `StopsDatabase.import_csv`).

---

## Adding a New Agency Preset

1. Create `transit/agencies/<name>.py` implementing `TransitAgency`:

```python
from transit.agencies.base import TransitAgency
from transit.models import StopsSource

class MyAgency(TransitAgency):
    agency_id = "myagency"
    name = "My City Transit"

    def __init__(self, config: dict) -> None:
        self._config = config

    def get_feed_urls(self, stop_id: str, routes: list) -> list:
        return ["https://realtime.myagency.com/TripUpdates.pb"]

    def get_api_headers(self) -> dict:
        key = self._config.get("api_key", "")
        header = self._config.get("api_key_header", "x-api-key")
        return {header: key} if key else {}

    def get_stops_source(self) -> StopsSource:
        return StopsSource(
            primary_url="",
            fallback_url="https://myagency.com/stops.csv",
            column_map={
                "stop_id": "stop_id",       # GTFS stop_id column — must match station_id config
                "station_id": "station_id", # optional internal numeric ID
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
- **Arrival colors**: green for normal arrivals; yellow for arrivals within `live_threshold_mins` — the same threshold that controls live priority takeover
- **16-pixel-tall panels**: smaller badge (7×7 px) and fonts scale down automatically

---

## Development

### Running Tests

```bash
# From the LEDMatrix root
.venv/bin/pytest plugin-repos/transit-board/test/ -v

# Or from inside the plugin repo with LEDMatrix's venv
cd /path/to/ledmatrix-transit-board
/path/to/LEDMatrix/.venv/bin/pytest test/ -v
```

57 tests covering protobuf parsing, SQLite import/lookup/migration, renderer pixel output, MTA feed routing, and plugin lifecycle. Tests use real protobuf encoding and real PIL image rendering.

### Emulator Render Test

To visually verify the plugin against live data without hardware:

```bash
cd /path/to/LEDMatrix
EMULATOR=true .venv/bin/python scripts/render_plugin.py \
  --plugin transit-board \
  --config '{"agency_id":"mta","station_id":"R16"}' \
  --output /tmp/transit.png
```

### Repository Structure

```
ledmatrix-transit-board/
├── manager.py               # TransitBoardPlugin — BasePlugin implementation
├── manifest.json            # Plugin metadata (id, version, entry_point)
├── config_schema.json       # JSON Schema for web UI config form
├── requirements.txt         # gtfs-realtime-bindings, protobuf, requests, Pillow
├── scripts/
│   └── search_stations.py   # Web UI action: search station names → GTFS Stop IDs
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
    ├── test_manager.py
    └── test_search_stations.py
```

### Data Flow

```
config.station_id  ──► StopsDatabase.lookup(gtfs_stop_id)
                              │
                              ├──► north_label / south_label / routes
                              │
                              ▼
             MtaAgency.get_feed_urls(stop_id, routes)
                              │
                              ▼
  GtfsRtClient.fetch_arrivals(urls, headers, stop_id, window)
                              │
                              ▼
         List[Arrival]  (route_id, direction_label, minutes)
                              │
                              ▼
     _group_arrivals()  ──► List[DirectionGroup]
                              │
                              ▼
  TransitRenderer.draw_direction_group(group, image, imminent_threshold)
                              │
                              ▼
              display_manager.update_display()
```

---

## Changelog

### v0.3.0

- **Fix:** MTA CSV column mapping corrected — `station_id` config now correctly maps to the **GTFS Stop ID** column (`R16`, `B18`) rather than the numeric **Station ID** column (`436`, `65`). Station lookups now resolve direction labels and route-specific feed selection.
- **Fix:** Added `station_id` (numeric CSV ID) column to the stops database alongside `gtfs_stop_id` — both are now stored as in the reference implementation.
- **Fix:** data.ny.gov primary stops URL removed (endpoint requires Socrata app token; previously produced a silent 403 on every bootstrap).
- **Fix:** `live_threshold_mins` now drives the renderer's yellow highlight in addition to live priority — previously hardcoded at 2 minutes regardless of config.
- **Fix:** Added `compatible_versions` to `manifest.json` (was failing schema validation on install).
- **Infra:** `config_secrets.template.json` in the LEDMatrix repo now includes a `transit-board` entry for `api_key`.
- **Tests:** Fixtures updated to match real MTA CSV structure (numeric Station IDs); 57 tests pass.

### v0.2.2

- Register `search_stations` as a web UI action in `manifest.json`

### v0.2.1

- Add station search action script (`scripts/search_stations.py`)

### v0.2.0

- Full GTFS-RT implementation — NYC MTA + custom agency support
- SQLite-backed station search with CSV fallback
- Direction cycling with configurable dwell time
- Live priority takeover for imminent arrivals
- 48-test TDD suite

### v0.1.0

- Initial stub (display and update not implemented)
