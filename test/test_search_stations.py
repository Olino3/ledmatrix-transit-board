"""Tests for the search_stations action script."""
import json
import sqlite3
import sys
import os
from pathlib import Path
from unittest.mock import patch

import pytest

# Add transit-board root to path
PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

import scripts.search_stations as search_mod


@pytest.fixture
def populated_db(tmp_path):
    """Create a stops DB with sample stations."""
    db_path = str(tmp_path / "transit_stops_mta.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE stops (
            stop_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            routes TEXT,
            north_label TEXT,
            south_label TEXT,
            lat REAL,
            lng REAL,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.executemany(
        "INSERT INTO stops VALUES (?,?,?,?,?,?,?,datetime('now'))",
        [
            ("B18", "79 St", "D", "Manhattan", "Coney Island", 40.613501, -74.00061),
            ("R28", "79 St", "1", "Uptown", "Downtown", 40.784615, -73.979892),
            ("R16", "Times Sq-42 St", "N Q R W", "Uptown & Queens", "Downtown & Brooklyn", 40.7549, -73.9878),
        ],
    )
    conn.commit()
    conn.close()
    return db_path


def test_search_returns_matching_stations(populated_db):
    """Querying '79 St' returns both stations with that name."""
    results = search_mod.search_stops(populated_db, "79 St")
    assert len(results) == 2
    stop_ids = {r["stop_id"] for r in results}
    assert "B18" in stop_ids
    assert "R28" in stop_ids


def test_search_is_case_insensitive(populated_db):
    """Query is case-insensitive."""
    results = search_mod.search_stops(populated_db, "times sq")
    assert len(results) == 1
    assert results[0]["stop_id"] == "R16"


def test_search_partial_match(populated_db):
    """Partial station name matches."""
    results = search_mod.search_stops(populated_db, "Times")
    assert any(r["stop_id"] == "R16" for r in results)


def test_search_no_match_returns_empty(populated_db):
    """Non-matching query returns empty list."""
    results = search_mod.search_stops(populated_db, "ZZZNOMATCH")
    assert results == []


def test_format_results_table():
    """format_results returns a readable table string."""
    stations = [
        {"stop_id": "B18", "name": "79 St", "routes": "D",
         "north_label": "Manhattan", "south_label": "Coney Island"},
    ]
    output = search_mod.format_results(stations)
    assert "B18" in output
    assert "79 St" in output
    assert "Manhattan" in output


def test_run_outputs_json(populated_db, capsys):
    """run() reads params from stdin and prints JSON to stdout."""
    params = json.dumps({"query": "79 St"})
    with patch("sys.stdin") as mock_stdin:
        mock_stdin.read.return_value = params
        with patch.object(search_mod, "_find_db_path", return_value=populated_db):
            search_mod.run()

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["status"] == "success"
    assert "B18" in output["message"]


def test_run_handles_missing_db(capsys):
    """run() returns error JSON when DB doesn't exist yet."""
    params = json.dumps({"query": "anything"})
    with patch("sys.stdin") as mock_stdin:
        mock_stdin.read.return_value = params
        with patch.object(search_mod, "_find_db_path", return_value=None):
            search_mod.run()

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["status"] == "error"
    assert "bootstrap" in output["message"].lower() or "enable" in output["message"].lower()


def test_run_handles_empty_query(capsys):
    """Empty query returns an informative error."""
    params = json.dumps({"query": ""})
    with patch("sys.stdin") as mock_stdin:
        mock_stdin.read.return_value = params
        search_mod.run()

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["status"] == "error"


def test_run_handles_db_error(tmp_path, capsys):
    """run() returns error JSON when the DB raises an exception."""
    bad_db = str(tmp_path / "bad.db")
    # Write garbage so sqlite3 raises DatabaseError
    with open(bad_db, "w") as f:
        f.write("not a sqlite db")
    params = json.dumps({"query": "Times"})
    with patch("sys.stdin") as mock_stdin:
        mock_stdin.read.return_value = params
        with patch.object(search_mod, "_find_db_path", return_value=bad_db):
            search_mod.run()

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["status"] == "error"
    assert "database" in output["message"].lower() or "error" in output["message"].lower()
