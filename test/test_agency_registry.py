"""
Tests for agency_registry — maps agency_id strings to TransitAgency instances.

All tests are written BEFORE implementation (TDD RED phase).
"""

import pytest


class TestGetAgency:
    def test_get_agency_returns_mta_for_mta_id(self):
        """agency_id='mta' returns an MtaAgency instance."""
        from transit.agency_registry import get_agency
        from transit.agencies.mta import MtaAgency

        agency = get_agency("mta", {})

        assert isinstance(agency, MtaAgency)

    def test_get_agency_returns_custom_for_custom_id(self):
        """agency_id='custom' returns a CustomAgency instance."""
        from transit.agency_registry import get_agency
        from transit.agencies.custom import CustomAgency

        agency = get_agency("custom", {"gtfs_rt_url": "http://example.com/gtfs"})

        assert isinstance(agency, CustomAgency)

    def test_get_agency_raises_for_unknown_id(self):
        """Unknown agency_id raises ValueError."""
        from transit.agency_registry import get_agency

        with pytest.raises(ValueError, match="Unknown agency_id"):
            get_agency("notanagency", {})

    def test_custom_agency_uses_url_from_config(self):
        """CustomAgency.get_feed_urls() returns the URL from config."""
        from transit.agency_registry import get_agency

        url = "https://bart.gov/gtfs-rt/tripupdates.pb"
        agency = get_agency("custom", {"gtfs_rt_url": url})
        urls = agency.get_feed_urls(stop_id="MCAR_S", routes=[])

        assert url in urls
