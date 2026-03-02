"""
Station search action script for the transit-board plugin.

Invoked by the LEDMatrix web UI via execute_plugin_action.
Reads JSON params from stdin, queries the stops DB, writes JSON to stdout.

Input (stdin):  {"query": "station name"}
Output (stdout): {"status": "success"|"error", "message": "..."}
"""
import json
import os
import sqlite3
import sys
from typing import List, Optional


# ---------------------------------------------------------------------------
# DB location
# ---------------------------------------------------------------------------

_CANDIDATE_CACHE_DIRS = [
    "/var/cache/ledmatrix",
    os.path.expanduser("~/.ledmatrix_cache"),
]


def _find_db_path(agency_id: str = "mta") -> Optional[str]:
    """Return the first existing stops DB path, or None."""
    db_name = f"transit_stops_{agency_id}.db"
    for d in _CANDIDATE_CACHE_DIRS:
        candidate = os.path.join(d, db_name)
        if os.path.exists(candidate):
            return candidate
    return None


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

def search_stops(db_path: str, query: str, limit: int = 10) -> List[dict]:
    """Case-insensitive partial name search against the stops DB."""
    pattern = f"%{query}%"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT stop_id, name, routes, north_label, south_label "
            "FROM stops WHERE name LIKE ? COLLATE NOCASE LIMIT ?",
            (pattern, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_results(stations: List[dict]) -> str:
    """Return a human-readable table of search results."""
    if not stations:
        return "No stations found."

    col_id = max(len(s["stop_id"]) for s in stations)
    col_name = max(len(s["name"]) for s in stations)
    col_routes = max(len(s.get("routes") or "") for s in stations)

    col_id = max(col_id, 7)       # "GTFS ID"
    col_name = max(col_name, 12)  # "Station Name"
    col_routes = max(col_routes, 6)  # "Routes"

    header = (
        f"{'GTFS ID':<{col_id}}  {'Station Name':<{col_name}}  "
        f"{'Routes':<{col_routes}}  Northbound -> Southbound"
    )
    sep = "-" * len(header)
    lines = [header, sep]
    for s in stations:
        north = s.get("north_label") or "-"
        south = s.get("south_label") or "-"
        lines.append(
            f"{s['stop_id']:<{col_id}}  {s['name']:<{col_name}}  "
            f"{(s.get('routes') or ''):<{col_routes}}  {north} -> {south}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run() -> None:
    """Read params from stdin, search, write JSON result to stdout."""
    raw = sys.stdin.read()
    try:
        params = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "message": f"Invalid JSON input: {exc}"}))
        return

    query = (params.get("query") or "").strip()

    if not query:
        print(json.dumps({
            "status": "error",
            "message": "Enter a station name to search (e.g. '79 St', 'Times Square', 'Atlantic Av').",
        }))
        return

    db_path = _find_db_path()
    if not db_path:
        print(json.dumps({
            "status": "error",
            "message": (
                "Stops database not found. Enable the transit-board plugin and "
                "let it run once to bootstrap the station database, then try again."
            ),
        }))
        return

    try:
        stations = search_stops(db_path, query)
    except Exception as exc:
        print(json.dumps({"status": "error", "message": f"Database error: {exc}"}))
        return

    if not stations:
        print(json.dumps({
            "status": "success",
            "message": f"No stations found matching '{query}'. Try a shorter or different search term.",
        }))
        return

    table = format_results(stations)
    print(json.dumps({
        "status": "success",
        "message": table,
    }))


if __name__ == "__main__":
    run()
