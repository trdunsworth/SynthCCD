"""Integration tests for county-wide PSAP support."""

from __future__ import annotations

from typing import Any

import overpy

from synth911gen3.addresses import (
    OpenStreetMapAddressProvider,
    _detect_feature_type,
    _GeocodedArea,
)


class TestDetectFeatureType:
    def test_county_from_type(self) -> None:
        assert _detect_feature_type({}, "county") == "county"

    def test_county_from_components(self) -> None:
        assert _detect_feature_type({"county": "Douglas"}, "administrative") == "county"

    def test_city_from_type(self) -> None:
        assert _detect_feature_type({}, "city") == "city"

    def test_city_from_components(self) -> None:
        assert _detect_feature_type({"city": "Lawrence"}, "place") == "city"

    def test_state_fallback(self) -> None:
        assert _detect_feature_type({"state": "Kansas"}, "boundary") == "state"

    def test_county_component_only(self) -> None:
        # county in components but type doesn't match -> still county fallback
        assert _detect_feature_type({"county": "Douglas"}, "place") == "county"

    def test_unknown_defaults_to_city(self) -> None:
        assert _detect_feature_type({}, "") == "city"


# ---------------------------------------------------------------------------
# Fake Nominatim / Overpass helpers
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError(
                "error", request=httpx.Request("GET", "http://fake"), response=self
            )


class _FakeClient:
    def __init__(self, search_payload: Any = None) -> None:
        self._search_payload = search_payload if search_payload is not None else []

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(self._search_payload)


def _make_way_xml(way_id: int, name: str, city: str = "", zip_code: str = "") -> str:
    """Build minimal Overpass XML for a way with address tags."""
    city_tag = f'k="addr:city" v="{city}"' if city else ""
    zip_tag = f'k="addr:postcode" v="{zip_code}"' if zip_code else ""
    return f"""
    <way id="{way_id}">
        <nd ref="1"/>
        <tag k="addr:housenumber" v="{100 + way_id}"/>
        <tag k="addr:street" v="{name}"/>
        {city_tag}
        {zip_tag}
        <tag k="name" v="{name}"/>
    </way>
    """


def _result_from_xml(xml: str) -> overpy.Result:
    """Parse Overpass XML into an overpy.Result."""
    full_xml = b'<osm version="0.6">' + xml.encode("utf-8") + b"</osm>"
    return overpy.Overpass().parse_xml(full_xml)


def _county_search_payload() -> list[dict]:
    """Nominatim search response for a county-level query."""
    return [
        {
            "boundingbox": ["38.7", "39.1", "-95.4", "-95.0"],
            "address": {"county": "Douglas County", "state": "Kansas"},
            "type": "county",
            "class": "boundary",
        }
    ]


def _city_search_payload() -> list[dict]:
    """Nominatim search response for a city-level query."""
    return [
        {
            "boundingbox": ["38.8", "39.1", "-95.3", "-95.1"],
            "address": {"city": "Lawrence", "state": "Kansas"},
            "type": "city",
            "class": "place",
        }
    ]


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestCountyFeatureDetection:
    def test_geocode_area_detects_county(self, tmp_path) -> None:
        client = _FakeClient(_county_search_payload())
        provider = OpenStreetMapAddressProvider(
            client=client,  # type: ignore[arg-type]
            cache_dir=tmp_path,
            query_runner=lambda q: _result_from_xml(""),
        )
        area = provider._geocode_area("Douglas County, KS")
        assert area.feature_type == "county"
        assert area.city == "Douglas County"

    def test_geocode_area_detects_city(self, tmp_path) -> None:
        client = _FakeClient(_city_search_payload())
        provider = OpenStreetMapAddressProvider(
            client=client,  # type: ignore[arg-type]
            cache_dir=tmp_path,
            query_runner=lambda q: _result_from_xml(""),
        )
        area = provider._geocode_area("Lawrence, KS")
        assert area.feature_type == "city"
        assert area.city == "Lawrence"


class TestCountyAddressGeneration:
    def test_county_addresses_get_correct_cities(self, tmp_path) -> None:
        """When area is a county, synthesized addresses should use real city names."""
        # Minimal Overpass result with named streets
        xml = (
            _make_way_xml(1, "Main St")
            + _make_way_xml(2, "Oak Ave")
            + _make_way_xml(3, "Elm St")
        )
        result = _result_from_xml(xml)

        def runner(query: str) -> overpy.Result:
            return result

        # Fake city discovery returning real cities
        from synth911gen3.city_discovery import CityPlace

        fake_cities = [
            CityPlace(name="Lawrence", place_type="city", lat=38.97, lon=-95.23, population=95000),
            CityPlace(name="Eudora", place_type="city", lat=38.95, lon=-95.10, population=6500),
        ]

        provider = OpenStreetMapAddressProvider(
            client=_FakeClient(_county_search_payload()),  # type: ignore[arg-type]
            cache_dir=tmp_path,
            query_runner=runner,
        )
        # Inject discovered cities
        provider._discovered_cities = fake_cities
        provider._postal_lookup = None  # skip postal for this test

        addresses = provider._query_named_streets(
            _GeocodedArea(
                south=38.7, west=-95.4, north=39.1, east=-95.0,
                city="Douglas County", state="Kansas",
                country_code="US", feature_type="county",
            )
        )

        cities_used = {a.city for a in addresses}
        # Should use real city names, not "Douglas County"
        assert "Douglas County" not in cities_used
        assert cities_used <= {"Lawrence", "Eudora"}

    def test_city_area_addresses_all_same_city(self, tmp_path) -> None:
        """When area is a city, all synthesized addresses should get that city."""
        xml = (
            _make_way_xml(1, "Main St")
            + _make_way_xml(2, "Oak Ave")
        )
        result = _result_from_xml(xml)

        def runner(query: str) -> overpy.Result:
            return result

        provider = OpenStreetMapAddressProvider(
            client=_FakeClient(_city_search_payload()),  # type: ignore[arg-type]
            cache_dir=tmp_path,
            query_runner=runner,
        )

        addresses = provider._query_named_streets(
            _GeocodedArea(
                south=38.8, west=-95.3, north=39.1, east=-95.1,
                city="Lawrence", state="Kansas",
                country_code="US", feature_type="city",
            )
        )

        cities_used = {a.city for a in addresses}
        assert cities_used == {"Lawrence"}
