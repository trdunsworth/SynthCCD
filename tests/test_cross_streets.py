"""Tests for cross-street resolution, address validation, and the hundred block.

Covers :mod:`synth911gen3.streets` (query building, intersection extraction,
nearest-crossing matching), the provider wiring in
``OpenStreetMapAddressProvider`` (attachment, failure tolerance, cache
round-trip), and the incident generator columns those feed
(``cross_street_1`` / ``cross_street_2`` / ``address_validated`` /
``hundred_block``).
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import numpy as np
import overpy
import pandas as pd
import pytest

from synth911gen3.addresses import (
    OpenStreetMapAddressProvider,
    StaticAddressProvider,
    _GeocodedArea,
)
from synth911gen3.config import DatasetKind, GenerationRequest, IdFormat, OutputFormat
from synth911gen3.domain import Address, parse_address_parts
from synth911gen3.exceptions import AddressLookupError
from synth911gen3.realism_config import RealismConfig
from synth911gen3.streets import (
    StreetGrid,
    StreetIntersection,
    build_intersections,
    build_street_geometry_query,
    merge_intersections,
    normalize_street_name,
    split_into_query_cells,
)

# ---------------------------------------------------------------------------
# Fixtures: a small grid where "Main St" crosses "W 10th St" at node 100 and
# "E 12th St" at node 103, while "Maple Ln" crosses nothing.
#   103 (39.0995, -94.5840)  Main St x E 12th St
#   101 (39.1000, -94.5840)
#   100 (39.1005, -94.5840)  Main St x W 10th St
#   102 (39.1010, -94.5840)
# ---------------------------------------------------------------------------

_NODE_COORDS = {
    101: (39.1000, -94.5840),
    100: (39.1005, -94.5840),
    102: (39.1010, -94.5840),
    103: (39.0995, -94.5840),
    201: (39.1005, -94.5850),
    202: (39.1005, -94.5830),
    301: (39.0995, -94.5850),
    302: (39.0995, -94.5830),
    401: (39.0980, -94.5840),
    402: (39.0985, -94.5840),
}


def _geometry_node(node_id: int) -> str:
    lat, lon = _NODE_COORDS[node_id]
    return f'<node id="{node_id}" lat="{lat}" lon="{lon}"/>'


def _geometry_way(way_id: int, name: str, node_ids: list[int]) -> str:
    nds = "".join(f'<nd ref="{node_id}"/>' for node_id in node_ids)
    return (
        f'<way id="{way_id}">{nds}'
        f'<tag k="highway" v="residential"/>'
        f'<tag k="name" v="{name}"/>'
        f"</way>"
    )


def _geometry_result(
    ways: list[tuple[int, str, list[int]]] | None = None,
) -> overpy.Result:
    elements = [_geometry_node(node_id) for node_id in _NODE_COORDS]
    for way_id, name, node_ids in ways if ways is not None else _DEFAULT_WAYS:
        elements.append(_geometry_way(way_id, name, node_ids))
    xml = b'<osm version="0.6">' + "".join(elements).encode("utf-8") + b"</osm>"
    return overpy.Overpass().parse_xml(xml)


_DEFAULT_WAYS = [
    (1, "Main St", [103, 101, 100, 102]),
    (2, "W 10th St", [201, 100, 202]),
    (3, "E 12th St", [301, 103, 302]),
    (4, "Maple Ln", [401, 402]),
]


class TestBuildStreetGeometryQuery:
    def test_includes_bbox_way_filter_and_recursion(self) -> None:
        query = build_street_geometry_query(39.09, -94.59, 39.11, -94.57)
        assert "39.09,-94.59,39.11,-94.57" in query
        assert 'way["highway"]["name"]' in query
        # ``out body`` for the ways, ``>`` recurse, ``out skel`` for their nodes.
        assert "out body" in query
        assert ">;" in query
        assert "out skel qt;" in query

    def test_max_ways_caps_the_way_output(self) -> None:
        query = build_street_geometry_query(39.0, -94.7, 39.2, -94.5, max_ways=1234)
        assert "out body 1234;" in query


class TestSplitIntoQueryCells:
    def test_single_cell_for_a_small_cloud(self) -> None:
        cells = split_into_query_cells([(39.10, -94.58), (39.11, -94.57)])
        assert len(cells) == 1
        south, west, north, east = cells[0]
        assert south <= 39.10 and north >= 39.11 and west <= -94.58 and east >= -94.57

    def test_wide_cloud_splits_into_a_grid(self) -> None:
        # A 0.9 deg span splits into ceil(0.9/0.2) = 5 cells per axis at minimum;
        # the cap limits it to 8 per axis.
        points = [(lat, lon) for lat in (39.0, 39.9) for lon in (-95.0, -94.1)]
        cells = split_into_query_cells(points)
        lats = {round(c[0], 4) for c in cells}
        lons = {round(c[1], 4) for c in cells}
        assert len(cells) == len(lats) * len(lons)
        assert len(cells) <= 8 * 8

    def test_very_wide_cloud_is_capped(self) -> None:
        points = [(lat, lon) for lat in (37.0, 41.0) for lon in (-102.0, -94.0)]
        cells = split_into_query_cells(points)
        distinct_south = {round(c[0], 6) for c in cells}
        assert len(distinct_south) <= 8

    def test_zero_coordinates_are_ignored(self) -> None:
        assert split_into_query_cells([(0.0, 0.0), (float("nan"), 0.0)]) == []
        assert split_into_query_cells([]) == []

    def test_cells_tile_the_padded_bbox_without_gaps(self) -> None:
        points = [(lat, lon) for lat in (39.0, 39.7) for lon in (-94.9, -94.2)]
        cells = split_into_query_cells(points)
        south, west = cells[0][0], cells[0][1]
        north, east = cells[0][2], cells[0][3]
        for cell in cells[1:]:
            south = min(south, cell[0])
            west = min(west, cell[1])
            north = max(north, cell[2])
            east = max(east, cell[3])
        assert south <= 38.98 and north >= 39.72
        assert west <= -94.92 and east >= -94.18


class TestMergeIntersections:
    def test_dedupes_by_coordinate_and_unions_names(self) -> None:
        first = [StreetIntersection(39.1, -94.5, ("Main St", "Oak Ave"))]
        second = [
            StreetIntersection(39.1, -94.5, ("Main St", "9th St")),  # border repeat + new name
            StreetIntersection(39.2, -94.6, ("Elm St", "9th St")),
        ]
        merged = merge_intersections([first, second])
        by_coords = {(round(i.lat, 5), round(i.lon, 5)): set(i.names) for i in merged}
        assert by_coords[(39.1, -94.5)] == {"Main St", "Oak Ave", "9th St"}
        assert by_coords[(39.2, -94.6)] == {"Elm St", "9th St"}

    def test_single_name_after_merge_is_dropped(self) -> None:
        # Two cells reporting the same single named node carry no crossing.
        tables = [
            [StreetIntersection(39.1, -94.5, ("Main St",))],
            [StreetIntersection(39.1, -94.5, ("Main St",))],
        ]
        assert merge_intersections(tables) == []

    def test_empty_input(self) -> None:
        assert merge_intersections([]) == []
        assert merge_intersections([[], []]) == []


class TestNormalizeStreetName:
    def test_strips_directionals_and_street_types(self) -> None:
        assert normalize_street_name("N Oak Trafficway") == "OAK"
        assert normalize_street_name("North Oak Trafficway") == "OAK"
        assert normalize_street_name("Oak Trafficway NW") == "OAK"
        assert normalize_street_name("Main St") == "MAIN"
        assert normalize_street_name("Main Street") == "MAIN"
        assert normalize_street_name("W 10th St") == "10TH"
        assert normalize_street_name("West 10th Street") == "10TH"

    def test_lowercase_and_extra_whitespace(self) -> None:
        assert normalize_street_name("  e   12th   street ") == "12TH"

    def test_directional_only_name_is_empty(self) -> None:
        assert normalize_street_name("North") == ""
        assert normalize_street_name("") == ""

    def test_parsed_street_name_matches_full_way_name(self) -> None:
        # ``parse_address_parts`` drops the street type, so the parsed
        # ``street_name`` ("Oak") must still match the way name.
        _, street_name, _, _, _ = parse_address_parts("890 N Oak Trafficway NW")
        assert normalize_street_name(street_name) == normalize_street_name("North Oak Trafficway")


class TestBuildIntersections:
    def test_shared_nodes_become_intersections(self) -> None:
        intersections = build_intersections(_geometry_result())
        by_coords = {(round(i.lat, 6), round(i.lon, 6)): i.names for i in intersections}
        assert by_coords[(39.1005, -94.5840)] == ("Main St", "W 10th St")
        assert by_coords[(39.0995, -94.5840)] == ("E 12th St", "Main St")

    def test_unshared_nodes_are_not_intersections(self) -> None:
        intersections = build_intersections(_geometry_result())
        coords = {(round(i.lat, 6), round(i.lon, 6)) for i in intersections}
        # Maple Ln endpoints cross nothing.
        assert (39.098, -94.584) not in coords
        assert (39.0985, -94.584) not in coords

    def test_three_way_intersection_keeps_all_names(self) -> None:
        ways = [
            (1, "Main St", [100]),
            (2, "Oak Ave", [100]),
            (3, "9th St", [100]),
        ]
        intersections = build_intersections(_geometry_result(ways))
        assert len(intersections) == 1
        assert intersections[0].names == ("9th St", "Main St", "Oak Ave")

    def test_unnamed_ways_are_ignored(self) -> None:
        ways = [
            (1, "Main St", [100, 101]),
            (2, "", [100, 201]),  # service road without a name tag
        ]
        intersections = build_intersections(_geometry_result(ways))
        assert intersections == []

    def test_empty_result(self) -> None:
        assert build_intersections(_geometry_result([])) == []


class TestStreetGrid:
    def _grid(self, **kwargs) -> StreetGrid:
        return StreetGrid(build_intersections(_geometry_result()), **kwargs)

    def test_nearest_crossings_nearest_first(self) -> None:
        grid = self._grid()
        # 22 m north of the W 10th St crossing, ~133 m north of E 12th St.
        crosses = grid.cross_streets_for(39.1007, -94.5840, "Main St")
        assert crosses == ["W 10th St", "E 12th St"]

    def test_own_street_is_excluded(self) -> None:
        grid = self._grid()
        crosses = grid.cross_streets_for(39.1004, -94.5840, "Main")
        assert crosses
        for name in crosses:
            assert normalize_street_name(name) != "MAIN"

    def test_name_matching_ignores_directionals_and_types(self) -> None:
        grid = self._grid()
        assert grid.cross_streets_for(39.1007, -94.5840, "N Main Street") == [
            "W 10th St",
            "E 12th St",
        ]

    def test_max_results_caps_the_list(self) -> None:
        grid = self._grid()
        assert len(grid.cross_streets_for(39.1007, -94.5840, "Main", max_results=1)) == 1

    def test_blank_beyond_cutoff(self) -> None:
        grid = self._grid(max_distance_meters=10.0)
        assert grid.cross_streets_for(39.1007, -94.5840, "Main St") == []

    def test_blank_when_street_has_no_crossing(self) -> None:
        grid = self._grid()
        assert grid.cross_streets_for(39.0982, -94.5840, "Maple Ln") == []

    def test_blank_for_unknown_street(self) -> None:
        grid = self._grid()
        assert grid.cross_streets_for(39.1004, -94.5840, "Unknown Rd") == []

    def test_blank_without_coordinates(self) -> None:
        grid = self._grid()
        assert grid.cross_streets_for(0.0, 0.0, "Main St") == []
        assert grid.cross_streets_for(float("nan"), -94.584, "Main St") == []

    def test_empty_grid_returns_blank(self) -> None:
        grid = StreetGrid([])
        assert len(grid) == 0
        assert grid.cross_streets_for(39.1, -94.58, "Main St") == []

    def test_grid_length(self) -> None:
        assert len(self._grid()) == 2

    def test_street_intersection_dataclass_is_sorted_tuple(self) -> None:
        node = StreetIntersection(lat=1.0, lon=2.0, names=("B St", "A St"))
        assert node.names == ("B St", "A St")


class TestProviderCrossStreets:
    _AREA = _GeocodedArea(
        south=39.0,
        west=-94.6,
        north=39.2,
        east=-94.4,
        city="Kansas City",
        state="Missouri",
    )

    def test_attaches_nearest_crossings_to_each_address(self, tmp_path: Path) -> None:
        addresses = [
            Address("4412 Main St", "Kansas City", "Missouri", latitude=39.1007, longitude=-94.5840),
            Address("12 Maple Ln", "Kansas City", "Missouri", latitude=39.0982, longitude=-94.5840),
        ]
        provider = OpenStreetMapAddressProvider(
            cache_dir=tmp_path, query_runner=lambda query: _geometry_result()
        )
        provider._attach_cross_streets(addresses, self._AREA)

        assert addresses[0].cross_street_1 == "W 10th St"
        assert addresses[0].cross_street_2 == "E 12th St"
        assert addresses[1].cross_street_1 == ""
        assert addresses[1].cross_street_2 == ""

    def test_query_failure_leaves_addresses_untouched(self, tmp_path: Path) -> None:
        addresses = [Address("4412 Main St", "Kansas City", "Missouri", latitude=39.1007, longitude=-94.5840)]

        def failing_runner(query: str) -> overpy.Result:
            raise AddressLookupError("overpass is down")

        provider = OpenStreetMapAddressProvider(cache_dir=tmp_path, query_runner=failing_runner)
        provider._attach_cross_streets(addresses, self._AREA)
        assert addresses[0].cross_street_1 == ""

    def test_empty_geometry_leaves_addresses_untouched(self, tmp_path: Path) -> None:
        addresses = [Address("4412 Main St", "Kansas City", "Missouri", latitude=39.1007, longitude=-94.5840)]
        provider = OpenStreetMapAddressProvider(
            cache_dir=tmp_path, query_runner=lambda query: _geometry_result([])
        )
        provider._attach_cross_streets(addresses, self._AREA)
        assert addresses[0].cross_street_1 == ""

    def test_cache_roundtrip_preserves_cross_streets(self, tmp_path: Path) -> None:
        path = tmp_path / "cache.parquet"
        addresses = [
            Address(
                "4412 Main St",
                "Kansas City",
                "Missouri",
                cross_street_1="W 10th St",
                cross_street_2="E 12th St",
            ),
            Address("12 Maple Ln", "Kansas City", "Missouri"),
        ]
        provider = OpenStreetMapAddressProvider(cache_dir=tmp_path, min_addresses=1)
        provider._write_cache(path, addresses)
        frame = pd.read_parquet(path)
        assert "cross_street_1" in frame.columns
        assert "cross_street_2" in frame.columns

        loaded = provider._load_cache(path)
        assert loaded is not None
        assert loaded[0].cross_street_1 == "W 10th St"
        assert loaded[0].cross_street_2 == "E 12th St"
        assert loaded[1].cross_street_1 == ""

    def test_attach_reports_completeness(self, tmp_path: Path) -> None:
        addresses = [Address("4412 Main St", "Kansas City", "Missouri", latitude=39.1007, longitude=-94.5840)]
        ok = OpenStreetMapAddressProvider(
            cache_dir=tmp_path, query_runner=lambda query: _geometry_result()
        )._attach_cross_streets(addresses, self._AREA)
        assert ok is True

        def failing_runner(query: str) -> overpy.Result:
            raise AddressLookupError("overpass is down")

        incomplete = OpenStreetMapAddressProvider(
            cache_dir=tmp_path, query_runner=failing_runner
        )._attach_cross_streets(addresses, self._AREA)
        assert incomplete is False

    def test_load_addresses_skips_cache_when_geometry_incomplete(self, tmp_path: Path) -> None:
        """A fetch with a failed geometry cell is not cached as final."""
        state = {"geometry_calls": 0}

        class _FakeClient:
            def get(self, url, **kwargs):
                payload = [
                    {
                        "boundingbox": ["39.0", "39.2", "-94.6", "-94.4"],
                        "address": {"city": "Kansas City", "state": "Missouri"},
                    }
                ]

                class _Response:
                    status_code = 200
                    headers: ClassVar[dict] = {}

                    def json(self):
                        return payload

                return _Response()

        def runner(query: str) -> overpy.Result:
            if "addr:housenumber" in query:
                way = (
                    '<way id="7"><center lat="39.1007" lon="-94.5840"/>'
                    '<tag k="addr:housenumber" v="4412"/><tag k="addr:street" v="Main St"/>'
                    "</way>"
                )
                xml = b'<osm version="0.6">' + way.encode("utf-8") + b"</osm>"
                return overpy.Overpass().parse_xml(xml)
            state["geometry_calls"] += 1
            if state["geometry_calls"] == 1:
                raise AddressLookupError("overpass is down")
            return _geometry_result()

        provider = OpenStreetMapAddressProvider(
            client=_FakeClient(),  # type: ignore[arg-type]
            cache_dir=tmp_path,
            query_runner=runner,
            min_addresses=1,
        )
        first = provider.load_addresses("Kansas City, MO")
        assert first[0].cross_street_1 == ""  # incomplete geometry left it blank
        cache_path = provider._cache_path("Kansas City, MO")
        assert not cache_path.exists(), "an incomplete table must not be cached as final"

        # The next run refetches and, with Overpass healthy, resolves and caches.
        second = provider.load_addresses("Kansas City, MO")
        assert second[0].cross_street_1 == "W 10th St"
        assert cache_path.exists()

    def test_load_addresses_attaches_cross_streets_end_to_end(self, tmp_path: Path) -> None:
        """A full fetch attaches cross streets after pulling the address pool."""

        class _FakeClient:
            def get(self, url, **kwargs):
                payload = [
                    {
                        "boundingbox": ["39.0", "39.2", "-94.6", "-94.4"],
                        "address": {"city": "Kansas City", "state": "Missouri"},
                    }
                ]

                class _Response:
                    status_code = 200
                    headers: ClassVar[dict] = {}

                    def json(self):
                        return payload

                return _Response()

        def runner(query: str) -> overpy.Result:
            if "addr:housenumber" in query:
                way = (
                    '<way id="7"><center lat="39.1007" lon="-94.5840"/>'
                    '<tag k="addr:housenumber" v="4412"/><tag k="addr:street" v="Main St"/>'
                    "</way>"
                )
                xml = b'<osm version="0.6">' + way.encode("utf-8") + b"</osm>"
                return overpy.Overpass().parse_xml(xml)
            return _geometry_result()

        provider = OpenStreetMapAddressProvider(
            client=_FakeClient(),  # type: ignore[arg-type]
            cache_dir=tmp_path,
            query_runner=runner,
            min_addresses=1,
        )
        addresses = provider.load_addresses("Kansas City, MO")
        assert len(addresses) == 1
        assert addresses[0].street_address == "4412 Main St"
        assert addresses[0].cross_street_1 == "W 10th St"
        assert addresses[0].cross_street_2 == "E 12th St"

    def test_wide_pool_queries_one_cell_per_bbox_tile(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A pool spread over a wide bbox is fetched as several bounded cells."""
        monkeypatch.setattr("synth911gen3.addresses._GEOMETRY_QUERY_INTERVAL", 0.0)
        queries: list[str] = []

        def runner(query: str) -> overpy.Result:
            queries.append(query)
            return _geometry_result()

        addresses = [
            Address("4412 Main St", "Kansas City", "Missouri", latitude=39.1007, longitude=-94.5840),
            Address("4412 Main St", "Kansas City", "Missouri", latitude=39.9, longitude=-94.3),
        ]
        provider = OpenStreetMapAddressProvider(cache_dir=tmp_path, query_runner=runner)
        provider._attach_cross_streets(addresses, self._AREA)

        geometry_queries = [q for q in queries if "addr:housenumber" not in q]
        assert len(geometry_queries) > 1, "wide pools must be split into bounded cells"
        # The near address matches the fixture geometry regardless of cell count.
        assert addresses[0].cross_street_1 == "W 10th St"

    def test_cache_digest_is_versioned(self, tmp_path: Path) -> None:
        """The cache key mixes in the schema version so stale caches refetch."""
        import hashlib

        from synth911gen3.addresses import _CACHE_VERSION

        provider = OpenStreetMapAddressProvider(cache_dir=tmp_path)
        digest = provider._digest("Kansas City, MO")
        unversioned = hashlib.md5(b"kansas city, mo").hexdigest()[:12]
        assert digest != unversioned, "cache digest must mix in _CACHE_VERSION"
        assert provider._cache_path("Kansas City, MO").name == f"addresses_{digest}.parquet"
        assert _CACHE_VERSION >= 3


class TestValidationAndHundredBlock:
    """Address validation gates cross streets and the hundred block per row."""

    @staticmethod
    def _pool() -> StaticAddressProvider:
        return StaticAddressProvider(
            [
                Address(
                    "4412 Main St",
                    "Kansas City",
                    "Missouri",
                    zone="URBAN",
                    cross_street_1="W 10th St",
                    cross_street_2="E 12th St",
                ),
                Address(
                    "17A Oak Trl",
                    "Kansas City",
                    "Missouri",
                    zone="URBAN",
                    cross_street_1="Elm St",
                ),
                Address(
                    "55 W 39th St",
                    "Kansas City",
                    "Missouri",
                    zone="RURAL",
                    cross_street_1="Rural Rd",
                ),
            ]
        )

    @staticmethod
    def _generate(realism: RealismConfig, rows: int = 900) -> pd.DataFrame:
        from synth911gen3.app import Synth911Application

        request = GenerationRequest(
            rows=rows,
            dataset=DatasetKind.INCIDENTS,
            output_format=OutputFormat.PANDAS,
            seed=7,
            realism_config=realism,
        )
        return Synth911Application(address_provider=TestValidationAndHundredBlock._pool()).generate(
            request
        ).incidents

    @staticmethod
    def _realism(urban: float, rural: float) -> RealismConfig:
        return RealismConfig(
            address_validation={"zone_rates": {"URBAN": urban, "RURAL": rural}}
        )

    def test_columns_exist_with_expected_dtypes(self) -> None:
        frame = self._generate(self._realism(1.0, 1.0))
        for column in ("cross_street_1", "cross_street_2", "address_validated", "hundred_block"):
            assert column in frame.columns
        assert frame["address_validated"].dtype == bool
        assert str(frame["hundred_block"].dtype) == "Int64"

    def test_full_validation_fills_cross_streets(self) -> None:
        frame = self._generate(self._realism(1.0, 1.0))
        assert frame["address_validated"].all()
        rows = frame.set_index("street_number")
        assert (rows.loc["4412", "cross_street_1"] == "W 10th St").all()
        assert (rows.loc["4412", "cross_street_2"] == "E 12th St").all()
        assert (rows.loc["17A", "cross_street_1"] == "Elm St").all()
        assert rows.loc["17A", "cross_street_2"].eq("").all()  # address carries no second crossing
        assert (rows.loc["55", "cross_street_1"] == "Rural Rd").all()

    def test_zero_validation_clears_cross_streets(self) -> None:
        frame = self._generate(self._realism(0.0, 0.0))
        assert not frame["address_validated"].any()
        assert frame["cross_street_1"].eq("").all()
        assert frame["cross_street_2"].eq("").all()
        assert frame["hundred_block"].isna().all()

    def test_zone_rates_are_independent(self) -> None:
        frame = self._generate(self._realism(1.0, 0.0))
        urban = frame[frame["zone"] == "URBAN"]["address_validated"]
        rural = frame[frame["zone"] == "RURAL"]["address_validated"]
        assert urban.all()
        assert not rural.any()

    def test_hundred_block_math(self) -> None:
        frame = self._generate(self._realism(1.0, 1.0))
        rows = frame.set_index("street_number")
        assert (rows.loc["4412", "hundred_block"] == 4400).all()
        # Alphanumeric and sub-100 house numbers never sit in a numbered range.
        assert rows.loc["17A", "hundred_block"].isna().all()
        assert rows.loc["55", "hundred_block"].isna().all()

    def test_hundred_block_matches_msag_convention(self) -> None:
        from synth911gen3.generators.incidents import _hundred_block_column

        street_numbers = np.array(["100", "199", "200", "4412", "9999", "99", "17A", ""])
        validated = np.ones(len(street_numbers), dtype=bool)
        blocks = _hundred_block_column(street_numbers, validated)
        assert blocks.fillna(-1).tolist() == [100, 100, 200, 4400, 9900, -1, -1, -1]

        # Unvalidated rows are NA even when the number is a plain integer.
        blocks = _hundred_block_column(street_numbers, np.zeros(len(street_numbers), dtype=bool))
        assert blocks.isna().all()

    def test_unvalidated_rows_are_na_even_for_numeric_numbers(self) -> None:
        frame = self._generate(self._realism(0.0, 0.0))
        numeric = frame[frame["street_number"].str.isdigit()]
        assert numeric["hundred_block"].isna().all()
        assert numeric["cross_street_1"].eq("").all()

    def test_generation_is_deterministic(self) -> None:
        """New columns do not disturb the seeded stream."""
        first = self._generate(self._realism(0.5, 0.5))
        second = self._generate(self._realism(0.5, 0.5))
        pd.testing.assert_frame_equal(first, second)

    def test_chunked_generation_carries_new_columns(self) -> None:
        """Chunked streaming keeps the new columns and stays reproducible."""
        from synth911gen3.generators.incidents import IncidentGenerator

        request = GenerationRequest(
            rows=60,
            dataset=DatasetKind.INCIDENTS,
            output_format=OutputFormat.PANDAS,
            seed=11,
            realism_config=RealismConfig(
                address_validation={"zone_rates": {"URBAN": 0.5, "RURAL": 0.5}}
            ),
        )
        generator = IncidentGenerator(self._pool())

        def run() -> list[pd.DataFrame]:
            return list(generator.generate_chunks(request, chunk_rows=13))

        first, second = run(), run()
        assert len(first) > 1
        for a, b in zip(first, second, strict=True):
            pd.testing.assert_frame_equal(a, b)
        for chunk in first:
            assert "cross_street_1" in chunk.columns
            assert "hundred_block" in chunk.columns
            assert str(chunk["hundred_block"].dtype) == "Int64"
        # Every row of every chunk is present exactly once.
        assert sum(len(chunk) for chunk in first) == 60


class TestRealismConfigIntegration:
    """The realism YAML drives validation rates and rejects bad input."""

    def test_defaults_from_constants(self) -> None:
        config = RealismConfig()
        assert config.validation_rate_for_zone("URBAN") > config.validation_rate_for_zone("SUBURBAN")
        assert config.validation_rate_for_zone("SUBURBAN") > config.validation_rate_for_zone("RURAL")

    def test_yaml_overrides_and_round_trips(self, tmp_path: Path) -> None:
        path = tmp_path / "realism.yaml"
        path.write_text(
            "address_validation:\n"
            "  zone_rates:\n"
            "    URBAN: 0.5\n"
            "    RURAL: 0.1\n",
            encoding="utf-8",
        )
        config = RealismConfig.from_yaml(path)
        assert config.validation_rate_for_zone("URBAN") == 0.5
        assert config.validation_rate_for_zone("RURAL") == 0.1
        # Partial override keeps the remaining default zones.
        assert config.validation_rate_for_zone("SUBURBAN") == 0.70

        out = tmp_path / "out.yaml"
        config.to_yaml(out)
        assert RealismConfig.from_yaml(out).validation_rate_for_zone("URBAN") == 0.5

    def test_unknown_zone_rejected(self, tmp_path: Path) -> None:
        from synth911gen3.exceptions import ValidationError

        path = tmp_path / "bad.yaml"
        path.write_text("address_validation:\n  zone_rates:\n    DOWNTOWN: 0.5\n", encoding="utf-8")
        try:
            RealismConfig.from_yaml(path)
        except ValidationError as exc:
            assert "unknown zone" in str(exc)
        else:
            raise AssertionError("unknown zone should be rejected")

    def test_out_of_range_rate_rejected(self, tmp_path: Path) -> None:
        from synth911gen3.exceptions import ValidationError

        path = tmp_path / "bad.yaml"
        path.write_text("address_validation:\n  zone_rates:\n    URBAN: 1.5\n", encoding="utf-8")
        try:
            RealismConfig.from_yaml(path)
        except ValidationError as exc:
            assert "between 0 and 1" in str(exc)
        else:
            raise AssertionError("out-of-range rate should be rejected")

    def test_unknown_key_rejected(self, tmp_path: Path) -> None:
        from synth911gen3.exceptions import ValidationError

        path = tmp_path / "bad.yaml"
        path.write_text("address_validation:\n  bogus: 1\n", encoding="utf-8")
        try:
            RealismConfig.from_yaml(path)
        except ValidationError as exc:
            assert "unknown key" in str(exc)
        else:
            raise AssertionError("unknown key should be rejected")

    def test_zone_rates_must_be_mapping(self, tmp_path: Path) -> None:
        from synth911gen3.exceptions import ValidationError

        path = tmp_path / "bad.yaml"
        path.write_text("address_validation:\n  zone_rates: []\n", encoding="utf-8")
        try:
            RealismConfig.from_yaml(path)
        except ValidationError as exc:
            assert "zone_rates" in str(exc)
        else:
            raise AssertionError("empty zone_rates should be rejected")

    def test_section_must_be_mapping(self, tmp_path: Path) -> None:
        from synth911gen3.exceptions import ValidationError

        path = tmp_path / "bad.yaml"
        path.write_text("address_validation: 5\n", encoding="utf-8")
        try:
            RealismConfig.from_yaml(path)
        except ValidationError as exc:
            assert "mapping" in str(exc)
        else:
            raise AssertionError("non-mapping section should be rejected")

    def test_unknown_zone_falls_back_to_midpoint(self) -> None:
        config = RealismConfig(address_validation={"zone_rates": {"URBAN": 0.9}})
        assert config.validation_rate_for_zone("ATLANTIS") == 0.5


def test_determinism_of_guid_runs_is_unaffected() -> None:
    """A GUID run keeps idempotent GUIDs alongside the new columns."""
    from synth911gen3.app import Synth911Application

    realism = RealismConfig(address_validation={"zone_rates": {"URBAN": 1.0, "RURAL": 1.0}})

    def run() -> pd.DataFrame:
        request = GenerationRequest(
            rows=40,
            dataset=DatasetKind.INCIDENTS,
            output_format=OutputFormat.PANDAS,
            seed=3,
            id_format=IdFormat.GUID,
            realism_config=realism,
        )
        return Synth911Application(address_provider=TestValidationAndHundredBlock._pool()).generate(
            request
        ).incidents

    frame = run()
    assert frame["address_validated"].all()  # rate 1.0 across both zones
    assert frame["cross_street_1"].ne("").any()
