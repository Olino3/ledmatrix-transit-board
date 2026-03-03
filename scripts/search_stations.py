"""
Station search action script for the transit-board plugin.

Invoked by the LEDMatrix web UI via execute_plugin_action.
Reads JSON params from stdin, queries the stops DB, writes JSON to stdout.

Input (stdin):  {"query": "station name"}
Output (stdout): {"status": "success"|"error", "results": [...], "message": "..."}
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
    agency_id = (params.get("agency_id") or "mta").strip()

    if not query:
        print(json.dumps({"status": "success", "results": [], "message": ""}))
        return

    db_path = _find_db_path(agency_id)
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
            "results": [],
            "message": f"No stations found matching '{query}'.",
        }))
        return

    n = len(stations)
    print(json.dumps({
        "status": "success",
        "results": stations,
        "message": f"Found {n} station{'s' if n != 1 else ''} matching '{query}'",
    }))


if __name__ == "__main__":
    run()
