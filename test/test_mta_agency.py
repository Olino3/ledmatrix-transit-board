"""
Tests for MtaAgency — NYC MTA feed routing and stops source configuration.

All tests are written BEFORE implementation (TDD RED phase).
"""

import pytest


@pytest.fixture
def mta():
    from transit.agencies.mta import MtaAgency
    return MtaAgency({})


class TestFeedRouting:
    def test_ace_route_maps_to_ace_feed(self, mta):
        """A, C, E routes resolve to the 'ace' feed group."""
        for route in ("A", "C", "E"):
            urls = mta.get_feed_urls(stop_id="A27", routes=[route])
            assert any("gtfs-ace" in u for u in urls), (
                f"Route {route} should map to ace feed, got: {urls}"
            )

    def test_numbered_lines_map_to_123456_feed(self, mta):
        """1/2/3/4/5/6 routes resolve to the '123456' feed group."""
        for route in ("1", "2", "3", "4", "5", "6"):
            urls = mta.get_feed_urls(stop_id="123S", routes=[route])
            assert any("gtfs-123456" in u for u in urls), (
                f"Route {route} should map to 123456 feed, got: {urls}"
            )

    def test_multiline_stop_deduplicates_feed_groups(self, mta):
        """N+Q routes both map to 'nqrw'; only one nqrw URL is returned."""
        urls = mta.get_feed_urls(stop_id="R16", routes=["N", "Q"])

        nqrw_urls = [u for u in urls if "gtfs-nqrw" in u]
        assert len(nqrw_urls) == 1, (
            "N and Q both map to nqrw feed; it should appear only once"
        )

    def test_unknown_route_returns_all_major_feeds(self, mta):
        """Unknown route ID falls back to all major feed groups."""
        urls = mta.get_feed_urls(stop_id="X99", routes=["UNKNOWN_ROUTE"])

        assert len(urls) >= 4, (
            "Fallback for unknown route should return all major feeds"
        )

    def test_builds_correct_mta_api_endpoint_url(self, mta):
        """Feed URL follows the api-endpoint.mta.info/…/nyct%2Fgtfs-{group} pattern."""
        urls = mta.get_feed_urls(stop_id="R16", routes=["N"])

        assert len(urls) >= 1
        url = urls[0]
        assert "api-endpoint.mta.info" in url
        assert "nyct%2Fgtfs-" in url or "nyct/gtfs-" in url


class TestStopsSource:
    def test_stops_source_primary_url_is_empty(self, mta):
        """Primary URL is intentionally empty: data.ny.gov requires a Socrata app token."""
        source = mta.get_stops_source()
        assert source.primary_url == ""

    def test_stops_source_fallback_is_webmta_csv_url(self, mta):
        """Fallback stops source is the web.mta.info CSV."""
        source = mta.get_stops_source()
        assert "web.mta.info" in source.fallback_url


class TestLineColors:
    def test_n_train_has_yellow_color(self, mta):
        assert mta.get_line_color("N") == "#FCCC0A"

    def test_unknown_route_returns_gray_fallback(self, mta):
        color = mta.get_line_color("UNKNOWN")
        # Must be a valid hex color string starting with #
        assert color.startswith("#")
