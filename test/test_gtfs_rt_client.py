"""
Tests for GtfsRtClient — generic GTFS-RT protobuf fetcher/parser.

All tests are written BEFORE implementation (TDD RED phase).
"""

import pytest
from unittest.mock import Mock, patch


class TestParseArrivals:
    """Tests for the protobuf parsing logic."""

    def test_parse_arrivals_extracts_matching_stop(self, sample_feed_bytes):
        """Arrivals at stop R16 are extracted from the feed."""
        from transit.gtfs_rt_client import GtfsRtClient

        client = GtfsRtClient()
        arrivals = client._parse_feed_bytes(sample_feed_bytes, stop_id="R16")

        assert len(arrivals) > 0
        # All arrivals must have correct stop prefix
        stop_ids = [a.route_id for a in arrivals]  # route_ids are populated
        assert any(a.route_id == "N" for a in arrivals)

    def test_parse_arrivals_excludes_past_departures(self, sample_feed_bytes):
        """Arrivals with arrival_time < now are excluded (minutes < 0)."""
        from transit.gtfs_rt_client import GtfsRtClient

        client = GtfsRtClient()
        arrivals = client._parse_feed_bytes(sample_feed_bytes, stop_id="R16")

        assert all(a.minutes >= 0 for a in arrivals), (
            "No past arrivals (negative minutes) should be included"
        )

    def test_parse_arrivals_excludes_arrivals_beyond_window(self, beyond_window_feed_bytes):
        """Arrivals more than window_minutes in the future are excluded."""
        from transit.gtfs_rt_client import GtfsRtClient

        client = GtfsRtClient()
        arrivals = client._parse_feed_bytes(
            beyond_window_feed_bytes, stop_id="R16", window_minutes=30
        )

        assert all(a.minutes <= 30 for a in arrivals), (
            "No arrivals beyond 30-minute window should be included"
        )

    def test_parse_arrivals_returns_sorted_by_minutes(self, unsorted_feed_bytes):
        """Returned arrivals are sorted by minutes ascending."""
        from transit.gtfs_rt_client import GtfsRtClient

        client = GtfsRtClient()
        arrivals = client._parse_feed_bytes(unsorted_feed_bytes, stop_id="R16")

        minutes = [a.minutes for a in arrivals]
        assert minutes == sorted(minutes), f"Expected sorted minutes, got {minutes}"

    def test_parse_arrivals_handles_empty_feed(self, empty_feed_bytes):
        """Empty feed returns an empty list without error."""
        from transit.gtfs_rt_client import GtfsRtClient

        client = GtfsRtClient()
        arrivals = client._parse_feed_bytes(empty_feed_bytes, stop_id="R16")

        assert arrivals == []


class TestFetchArrivals:
    """Tests for the HTTP fetch layer."""

    def test_fetch_skips_failed_url_and_returns_empty_for_single_url(self, sample_feed_bytes):
        """A single URL returning non-200 is skipped with a warning; returns empty list."""
        from transit.gtfs_rt_client import GtfsRtClient

        client = GtfsRtClient()
        mock_response = Mock()
        mock_response.status_code = 503

        with patch("transit.gtfs_rt_client.requests.get", return_value=mock_response):
            result = client.fetch_arrivals(
                feed_urls=["http://feed.example.com/gtfs"],
                headers={},
                stop_id="R16",
            )
        assert result == [], "Failed single URL should return empty list, not raise"

    def test_fetch_returns_partial_arrivals_when_one_url_fails(self, sample_feed_bytes):
        """When one of multiple URLs fails, arrivals from the successful URL are returned."""
        from transit.gtfs_rt_client import GtfsRtClient

        client = GtfsRtClient()

        fail_response = Mock()
        fail_response.status_code = 503

        ok_response = Mock()
        ok_response.status_code = 200
        ok_response.content = sample_feed_bytes

        responses = [fail_response, ok_response]
        call_count = 0

        def fake_get(url, **kwargs):
            nonlocal call_count
            r = responses[call_count]
            call_count += 1
            return r

        with patch("transit.gtfs_rt_client.requests.get", side_effect=fake_get):
            result = client.fetch_arrivals(
                feed_urls=["http://bad.example.com/gtfs", "http://good.example.com/gtfs"],
                headers={},
                stop_id="R16",
            )

        assert len(result) > 0, (
            "Arrivals from the successful URL should be returned even when another URL fails"
        )

    def test_fetch_passes_headers_to_request(self, sample_feed_bytes):
        """Custom headers are forwarded to the HTTP GET request."""
        from transit.gtfs_rt_client import GtfsRtClient

        client = GtfsRtClient()
        headers = {"x-api-key": "secret123"}

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = sample_feed_bytes

        with patch("transit.gtfs_rt_client.requests.get", return_value=mock_response) as mock_get:
            client.fetch_arrivals(
                feed_urls=["http://feed.example.com/gtfs"],
                headers=headers,
                stop_id="R16",
            )
            call_kwargs = mock_get.call_args
            assert call_kwargs.kwargs.get("headers") == headers or (
                len(call_kwargs.args) > 1 and call_kwargs.args[1] == headers
            ), "Headers must be passed to requests.get"
