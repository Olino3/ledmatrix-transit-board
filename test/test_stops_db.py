"""
Tests for StopsDatabase — SQLite-backed stops persistence layer.

All tests are written BEFORE implementation (TDD RED phase).
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import json


@pytest.fixture
def tmp_db(tmp_path):
    """A fresh StopsDatabase backed by a temp file."""
    from transit.stops_db import StopsDatabase
    db_path = str(tmp_path / "test_stops.db")
    return StopsDatabase(db_path)


class TestImportFromCsv:
    def test_import_from_csv_populates_rows(self, tmp_db, sample_stops_csv_path):
        """Importing a valid CSV populates the stops table."""
        from transit.stops_db import CSV_COLUMN_MAP

        tmp_db.import_csv(sample_stops_csv_path, column_map=CSV_COLUMN_MAP)

        assert tmp_db.count() == 3

    def test_import_skips_malformed_csv_rows(self, tmp_db, malformed_stops_csv_path):
        """Malformed rows are skipped without crashing; valid rows are inserted."""
        from transit.stops_db import CSV_COLUMN_MAP

        tmp_db.import_csv(malformed_stops_csv_path, column_map=CSV_COLUMN_MAP)

        # 1 valid row should be inserted; malformed row skipped
        assert tmp_db.count() >= 1


class TestSearch:
    def test_search_by_name_case_insensitive(self, tmp_db, sample_stops_csv_path):
        """Search is case-insensitive: 'times sq' finds 'Times Sq-42 St'."""
        from transit.stops_db import CSV_COLUMN_MAP

        tmp_db.import_csv(sample_stops_csv_path, column_map=CSV_COLUMN_MAP)
        results = tmp_db.search("times sq")

        assert len(results) >= 1
        names = [r.name.lower() for r in results]
        assert any("times sq" in n for n in names)

    def test_search_returns_partial_matches(self, tmp_db, sample_stops_csv_path):
        """Partial query 'fulton' returns matching stations."""
        from transit.stops_db import CSV_COLUMN_MAP

        tmp_db.import_csv(sample_stops_csv_path, column_map=CSV_COLUMN_MAP)
        results = tmp_db.search("fulton")

        assert len(results) >= 1
        assert any("fulton" in r.name.lower() for r in results)


class TestLookup:
    def test_lookup_by_stop_id_returns_station_info(self, tmp_db, sample_stops_csv_path):
        """lookup('R16') returns a StationInfo with correct fields."""
        from transit.stops_db import CSV_COLUMN_MAP

        tmp_db.import_csv(sample_stops_csv_path, column_map=CSV_COLUMN_MAP)
        info = tmp_db.lookup("R16")

        assert info is not None
        assert info.stop_id == "R16"
        assert "Times Sq" in info.name
        assert "N" in info.routes

    def test_lookup_returns_none_for_unknown_stop(self, tmp_db, sample_stops_csv_path):
        """lookup() returns None when stop_id is not in the database."""
        from transit.stops_db import CSV_COLUMN_MAP

        tmp_db.import_csv(sample_stops_csv_path, column_map=CSV_COLUMN_MAP)
        result = tmp_db.lookup("NOTREAL999")

        assert result is None


class TestRefresh:
    def test_refresh_updates_existing_rows_no_duplicates(self, tmp_db, sample_stops_csv_path):
        """Importing the same CSV twice does not duplicate rows."""
        from transit.stops_db import CSV_COLUMN_MAP

        tmp_db.import_csv(sample_stops_csv_path, column_map=CSV_COLUMN_MAP)
        count_after_first = tmp_db.count()

        tmp_db.import_csv(sample_stops_csv_path, column_map=CSV_COLUMN_MAP)
        count_after_second = tmp_db.count()

        assert count_after_second == count_after_first, (
            "Re-importing the same data should not create duplicate rows"
        )


class TestPersistence:
    def test_db_persists_after_reopen(self, tmp_path, sample_stops_csv_path):
        """Data inserted in one StopsDatabase instance is visible after reopen."""
        from transit.stops_db import StopsDatabase, CSV_COLUMN_MAP

        db_path = str(tmp_path / "persist.db")
        db1 = StopsDatabase(db_path)
        db1.import_csv(sample_stops_csv_path, column_map=CSV_COLUMN_MAP)
        count = db1.count()

        # Open a fresh instance pointing to the same file
        db2 = StopsDatabase(db_path)
        assert db2.count() == count, "Data must survive closing and reopening the database"
