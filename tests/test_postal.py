"""Tests for the postal lookup service (zipcodes wrapper)."""

from __future__ import annotations

import pytest

from synth911gen3.postal import PostalLookup, get_postal_lookup


@pytest.fixture(scope="module")
def lookup() -> PostalLookup:
    return get_postal_lookup()


class TestLookupCity:
    def test_valid_zip_returns_city(self, lookup: PostalLookup) -> None:
        assert lookup.lookup_city("66046") == "Lawrence"

    def test_valid_zip_another_state(self, lookup: PostalLookup) -> None:
        assert lookup.lookup_city("90210") == "Beverly Hills"

    def test_invalid_zip_returns_none(self, lookup: PostalLookup) -> None:
        assert lookup.lookup_city("00000") is None

    def test_short_zip_returns_none(self, lookup: PostalLookup) -> None:
        assert lookup.lookup_city("123") is None

    def test_zip_plus_four(self, lookup: PostalLookup) -> None:
        city = lookup.lookup_city("66046-1234")
        assert city == "Lawrence"


class TestLookupRecord:
    def test_valid_zip_returns_record(self, lookup: PostalLookup) -> None:
        record = lookup.lookup_record("66046")
        assert record is not None
        assert record["city"] == "Lawrence"
        assert record["state"] == "KS"
        assert "county" in record

    def test_invalid_zip_returns_none(self, lookup: PostalLookup) -> None:
        assert lookup.lookup_record("00000") is None


class TestCitiesInCounty:
    def test_douglas_county_ks(self, lookup: PostalLookup) -> None:
        cities = lookup.cities_in_county("Douglas County", "KS")
        assert "Lawrence" in cities
        assert "Eudora" in cities
        assert "Baldwin City" in cities
        assert "Lecompton" in cities
        # Deduplicated and sorted
        assert cities == sorted(set(cities))

    def test_empty_county(self, lookup: PostalLookup) -> None:
        cities = lookup.cities_in_county("Nonexistent County", "XX")
        assert cities == []


class TestCitiesInBbox:
    def test_bbox_around_lawrence(self, lookup: PostalLookup) -> None:
        # Bbox roughly around Douglas County, KS
        cities = lookup.cities_in_bbox(38.7, -95.4, 39.1, -95.0)
        assert "Lawrence" in cities
        assert len(cities) >= 2

    def test_empty_bbox(self, lookup: PostalLookup) -> None:
        # Mid-ocean bbox with no ZIP centroids nearby
        cities = lookup.cities_in_bbox(-30.0, -30.0, -29.99, -29.99)
        assert cities == []


class TestCityForCoordinates:
    def test_lawrence_coordinates(self, lookup: PostalLookup) -> None:
        city = lookup.city_for_coordinates(38.97, -95.23)
        assert city == "Lawrence"


class TestSingleton:
    def test_get_postal_lookup_returns_same_instance(self) -> None:
        a = get_postal_lookup()
        b = get_postal_lookup()
        assert a is b
