"""Tests for Overpass-based city discovery."""

from __future__ import annotations

from typing import Any

import overpy

from synth911gen3.city_discovery import CityPlace, discover_cities_in_bbox


def _result_from_nodes_xml(nodes_xml: str) -> overpy.Result:
    """Parse minimal Overpass XML with node elements into an overpy.Result."""
    xml = b'<osm version="0.6">' + nodes_xml.encode("utf-8") + b"</osm>"
    return overpy.Overpass().parse_xml(xml)


def _node_xml(node_id: int, name: str, place: str, lat: float, lon: float, population: str | None = None) -> str:
    """Build minimal Overpass XML for a node with place tags."""
    pop_tag = f'<tag k="population" v="{population}"/>' if population else ""
    return (
        f'<node id="{node_id}" lat="{lat}" lon="{lon}">'
        f'<tag k="name" v="{name}"/>'
        f'<tag k="place" v="{place}"/>'
        f"{pop_tag}"
        f"</node>"
    )


def _make_runner(result: overpy.Result) -> Any:
    """Return a query_runner callable that always returns *result*."""
    return lambda query: result


class TestDiscoverCitiesInBbox:
    def test_returns_named_places(self) -> None:
        nodes_xml = (
            _node_xml(1, "Lawrence", "city", 38.97, -95.23, "95000")
            + _node_xml(2, "Eudora", "city", 38.95, -95.10, "6500")
        )
        result = _result_from_nodes_xml(nodes_xml)
        runner = _make_runner(result)
        places = discover_cities_in_bbox(38.7, -95.4, 39.1, -95.0, runner)

        names = [p.name for p in places]
        assert "Lawrence" in names
        assert "Eudora" in names

    def test_deduplicates_by_name(self) -> None:
        nodes_xml = (
            _node_xml(1, "Lawrence", "city", 38.97, -95.23, "95000")
            + _node_xml(2, "Lawrence", "town", 38.98, -95.22, "94000")
        )
        result = _result_from_nodes_xml(nodes_xml)
        runner = _make_runner(result)
        places = discover_cities_in_bbox(38.7, -95.4, 39.1, -95.0, runner)

        lawrence = [p for p in places if p.name == "Lawrence"]
        assert len(lawrence) == 1
        # Higher population wins
        assert lawrence[0].population == 95000

    def test_sorted_by_population_desc(self) -> None:
        nodes_xml = (
            _node_xml(1, "Small Town", "village", 38.80, -95.20, "500")
            + _node_xml(2, "Lawrence", "city", 38.97, -95.23, "95000")
            + _node_xml(3, "Eudora", "town", 38.95, -95.10, "6500")
        )
        result = _result_from_nodes_xml(nodes_xml)
        runner = _make_runner(result)
        places = discover_cities_in_bbox(38.7, -95.4, 39.1, -95.0, runner)

        assert places[0].name == "Lawrence"
        assert places[1].name == "Eudora"
        assert places[2].name == "Small Town"

    def test_skips_unnamed_nodes(self) -> None:
        nodes_xml = (
            _node_xml(1, "", "city", 38.97, -95.23)
            + _node_xml(2, "Lawrence", "city", 38.97, -95.23)
        )
        result = _result_from_nodes_xml(nodes_xml)
        runner = _make_runner(result)
        places = discover_cities_in_bbox(38.7, -95.4, 39.1, -95.0, runner)

        assert len(places) == 1
        assert places[0].name == "Lawrence"

    def test_handles_overpy_exception(self) -> None:
        import overpy.exception

        def bad_runner(query: str) -> Any:
            raise overpy.exception.OverPyException("test error")

        places = discover_cities_in_bbox(38.7, -95.4, 39.1, -95.0, bad_runner)
        assert places == []

    def test_empty_result(self) -> None:
        result = _result_from_nodes_xml("")
        runner = _make_runner(result)
        places = discover_cities_in_bbox(38.7, -95.4, 39.1, -95.0, runner)
        assert places == []


class TestCityPlaceDataclass:
    def test_fields(self) -> None:
        p = CityPlace(name="Test", place_type="city", lat=1.0, lon=2.0, population=100)
        assert p.name == "Test"
        assert p.place_type == "city"
        assert p.lat == 1.0
        assert p.lon == 2.0
        assert p.population == 100

    def test_optional_population(self) -> None:
        p = CityPlace(name="Test", place_type="town", lat=1.0, lon=2.0)
        assert p.population is None
