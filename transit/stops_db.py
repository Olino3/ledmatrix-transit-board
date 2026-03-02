"""
SQLite-backed stops database.

Ported and generalised from:
  /root/star-wars-dashboard/backend/utils/subway.py :: initialize_stations_db()
  and get_station_info()

Strategy:
  bootstrap(): user CSV → agency primary API → agency fallback CSV URL
  All data persists in SQLite so the app survives external service outages.
"""

import csv
import io
import sqlite3
from pathlib import Path
from typing import List, Optional

import requests

from transit.models import StationInfo

try:
    from src.logging_config import get_logger as _get_logger
    logger = _get_logger("transit.stops_db")
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# Default column mapping for MTA Stations.csv
# Maps internal field name → CSV column header
CSV_COLUMN_MAP = {
    "stop_id": "GTFS Stop ID",
    "station_id": "Station ID",
    "name": "Stop Name",
    "routes": "Daytime Routes",
    "north_label": "North Direction Label",
    "south_label": "South Direction Label",
    "lat": "GTFS Latitude",
    "lng": "GTFS Longitude",
}

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS stops (
    stop_id      TEXT PRIMARY KEY,
    station_id   TEXT,
    name         TEXT NOT NULL,
    routes       TEXT,
    north_label  TEXT,
    south_label  TEXT,
    lat          REAL,
    lng          REAL,
    updated_at   TEXT DEFAULT (datetime('now'))
);
"""
_CREATE_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_stops_name ON stops(name COLLATE NOCASE);"
)
_CREATE_INDEX_STATION_ID = (
    "CREATE INDEX IF NOT EXISTS idx_stops_station_id ON stops(station_id);"
)


class StopsDatabase:
    """
    SQLite-backed store for GTFS static stop data.

    Usage:
        db = StopsDatabase("/path/to/stops.db")
        if db.needs_bootstrap():
            db.bootstrap(agency)
        info = db.lookup("R16")
        results = db.search("Times Sq")
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE)
            conn.execute(_CREATE_INDEX)
            conn.execute(_CREATE_INDEX_STATION_ID)
            # Migration: add station_id column when upgrading from pre-0.3 schema.
            # If ALTER TABLE succeeds, the column was missing — old data used numeric
            # stop_ids instead of GTFS IDs, so clear it to force a clean re-bootstrap.
            try:
                conn.execute("ALTER TABLE stops ADD COLUMN station_id TEXT DEFAULT ''")
                conn.execute("DELETE FROM stops")
                logger.info("stops_db: schema migrated (added station_id), stale data cleared")
            except sqlite3.OperationalError:
                pass  # Column already present — no migration needed

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def needs_bootstrap(self) -> bool:
        """Return True if the database has no stops yet."""
        return self.count() == 0

    def bootstrap(self, agency, user_csv_path: Optional[str] = None) -> None:
        """
        Populate the database with stop data.

        Priority order:
          1. user_csv_path (if provided)
          2. agency.get_stops_source().primary_url  (data.ny.gov API)
          3. agency.get_stops_source().fallback_url  (web.mta.info CSV)
        """
        source = agency.get_stops_source()
        column_map = source.column_map or CSV_COLUMN_MAP

        if user_csv_path:
            logger.info("Loading stops from user CSV: %s", user_csv_path)
            self.import_csv(user_csv_path, column_map=column_map)
            return

        if source.primary_url:
            try:
                self._import_from_url(source.primary_url, column_map=column_map)
                logger.info("Stops loaded from primary API: %s", source.primary_url)
                return
            except Exception as exc:
                logger.warning("Primary stops URL failed (%s): %s", source.primary_url, exc)

        if source.fallback_url:
            try:
                self._import_from_url(source.fallback_url, column_map=column_map)
                logger.info("Stops loaded from fallback URL: %s", source.fallback_url)
                return
            except Exception as exc:
                logger.error("Fallback stops URL also failed: %s", exc)

    def refresh(self, agency) -> None:
        """Re-fetch and overwrite stop data from agency sources."""
        self.bootstrap(agency)

    # ------------------------------------------------------------------
    # Import helpers
    # ------------------------------------------------------------------

    def import_csv(self, path: str, column_map: dict) -> None:
        """Import stops from a local CSV file."""
        with open(path, newline="", encoding="utf-8-sig") as fh:
            self._import_csv_stream(fh, column_map)

    def _import_from_url(self, url: str, column_map: dict) -> None:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")

        if "json" in content_type or url.endswith(".json"):
            self._import_datany_json(resp.json(), column_map)
        else:
            self._import_csv_stream(io.StringIO(resp.text), column_map)

    def _import_csv_stream(self, stream, column_map: dict) -> None:
        reader = csv.DictReader(stream)
        rows = []
        for row in reader:
            try:
                rows.append(self._row_from_csv(row, column_map))
            except (KeyError, ValueError):
                logger.debug("Skipping malformed CSV row: %s", row)
                continue
        self._upsert_rows(rows)

    def _row_from_csv(self, row: dict, column_map: dict) -> tuple:
        raw_id = row.get(column_map["stop_id"])
        if not raw_id:
            raise ValueError("empty stop_id")
        stop_id = raw_id.strip()
        if not stop_id:
            raise ValueError("empty stop_id")
        raw_name = row.get(column_map["name"])
        if not raw_name:
            raise ValueError("empty name")
        name = raw_name.strip()
        station_id = row.get(column_map.get("station_id", ""), "").strip()
        routes = row.get(column_map.get("routes", ""), "").strip()
        north = row.get(column_map.get("north_label", ""), "").strip()
        south = row.get(column_map.get("south_label", ""), "").strip()
        lat_raw = row.get(column_map.get("lat", ""), "0") or "0"
        lng_raw = row.get(column_map.get("lng", ""), "0") or "0"
        return (stop_id, station_id, name, routes, north, south, float(lat_raw), float(lng_raw))

    def _import_datany_json(self, payload: dict, column_map: dict) -> None:
        """Handle data.ny.gov API response (JSON with 'data' key)."""
        rows = []
        for item in payload.get("data", []):
            try:
                rows.append(self._row_from_csv(item, column_map))
            except (KeyError, ValueError):
                logger.debug("Skipping malformed JSON row: %s", item)
                continue
        self._upsert_rows(rows)

    def _upsert_rows(self, rows: list) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO stops (stop_id, station_id, name, routes, north_label, south_label, lat, lng)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(stop_id) DO UPDATE SET
                    station_id=excluded.station_id,
                    name=excluded.name,
                    routes=excluded.routes,
                    north_label=excluded.north_label,
                    south_label=excluded.south_label,
                    lat=excluded.lat,
                    lng=excluded.lng,
                    updated_at=datetime('now')
                """,
                rows,
            )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def search(self, query: str, limit: int = 10) -> List[StationInfo]:
        """Case-insensitive partial name search."""
        pattern = f"%{query}%"
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM stops WHERE name LIKE ? COLLATE NOCASE LIMIT ?",
                (pattern, limit),
            ).fetchall()
        return [self._row_to_station(r) for r in rows]

    def lookup(self, stop_id: str) -> Optional[StationInfo]:
        """Exact stop_id lookup. Returns None if not found."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM stops WHERE stop_id = ?", (stop_id,)
            ).fetchone()
        return self._row_to_station(row) if row else None

    def count(self) -> int:
        """Return the number of stops in the database."""
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM stops").fetchone()[0]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_station(row: sqlite3.Row) -> StationInfo:
        routes_raw = row["routes"] or ""
        routes = [r.strip() for r in routes_raw.split() if r.strip()]
        return StationInfo(
            stop_id=row["stop_id"],
            station_id=row["station_id"] or "",
            name=row["name"],
            routes=routes,
            north_label=row["north_label"] or "Uptown",
            south_label=row["south_label"] or "Downtown",
        )
