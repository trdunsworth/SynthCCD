"""Cross-street resolution from OpenStreetMap way geometry.

CAD records carry cross streets so responders can find a location when the
house number is missing, ambiguous, or unvalidated. Modern CAD systems refresh
them only once a caller address validates against the authoritative address
database; the per-row validation decision itself lives in the incident
generator (gated by the ``address_validation`` realism section), and this
module supplies the candidate intersections it draws from.

Pipeline: one Overpass query fetches named-street way geometry for an area
(``way[highway][name]`` plus its member nodes, via ``out body`` + the ``>``
recurse + ``out skel``). A node referenced by two or more distinctly named ways
is a street intersection. :class:`StreetGrid` indexes those intersections with
a KD-tree in local metre coordinates, so each address can find its nearest
crossings; the cross streets are the *other* streets at those nodes — the
address's own street is always excluded.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.spatial import KDTree

from .domain import DIRECTIONS, STREET_TYPES
from .logging_conf import get_logger

logger = get_logger("streets")

# Local equirectangular projection constants. A bounding box is small enough
# that the flat-earth approximation stays within a metre or two.
_EARTH_RADIUS_M = 6_371_000.0
# Addresses farther than this from any crossing of their own street get no
# cross streets (blank), mirroring how far a dispatcher's nearest crossing
# usually is in a grid street network.
_DEFAULT_MAX_DISTANCE_M = 500.0
# Upper bound on named ways pulled per geometry query, so one Overpass call can
# never return an unbounded payload.
_DEFAULT_MAX_WAYS = 50_000
# Target geometry-query cell size in degrees (~20 km at mid latitudes) and the
# padding added around the address pool: splitting the pool's bounding box into
# cells keeps every Overpass call spatially bounded, so a metro area is fetched
# as several small complete queries instead of one huge id-truncated slice.
_CELL_DEGREES = 0.2
_MAX_CELLS_PER_AXIS = 8
_BBOX_PADDING_DEGREES = 0.02


def build_street_geometry_query(
    south: float, west: float, north: float, east: float, max_ways: int = _DEFAULT_MAX_WAYS
) -> str:
    """Overpass QL for named-street ways plus their member nodes in a bbox.

    ``out body`` prints the ways (tags + node id references); the ``>``
    recurse-step then prints the nodes those ways are built from; ``out skel``
    keeps those nodes to id + coordinates. The result carries everything the
    intersection table needs: which named ways share which node.
    """
    bbox = f"{south},{west},{north},{east}"
    return (
        "[out:xml][timeout:120];"
        f'way["highway"]["name"]({bbox});'
        f"out body {max_ways};"
        ">;"
        "out skel qt;"
    )


def normalize_street_name(name: str) -> str:
    """Canonical form for matching ``addr:street`` values against way names.

    Uppercases, collapses whitespace, and strips directional prefixes/suffixes
    and a trailing street type, so ``"N Oak Trafficway"``, ``"North Oak
    Trafficway"``, and ``"Oak Trafficway"`` all match, and ``"Main St"``
    matches ``"Main Street"``. Returns an empty string for names that carry no
    identifying content (e.g. a name that is only a directional).
    """
    tokens = [token for token in name.replace(",", " ").split() if token]
    while tokens and tokens[0].upper() in DIRECTIONS:
        tokens.pop(0)
    while tokens and tokens[-1].upper() in DIRECTIONS:
        tokens.pop()
    if tokens and tokens[-1].upper() in STREET_TYPES:
        tokens.pop()
    return " ".join(tokens).upper()


@dataclass(frozen=True, slots=True)
class StreetIntersection:
    """A node where two or more distinct named streets cross."""

    lat: float
    lon: float
    names: tuple[str, ...]  # street names at the node, sorted


def split_into_query_cells(points: Sequence[tuple[float, float]]) -> list[tuple[float, float, float, float]]:
    """Split a point cloud's bounding box into bounded geometry-query cells.

    Returns ``(south, west, north, east)`` cells of roughly ``_CELL_DEGREES``,
    padded by ``_BBOX_PADDING_DEGREES`` so addresses near the edge still find
    their crossings. Degenerate clouds collapse to a single cell, and very wide
    clouds grow their cells instead of multiplying calls, capped at
    ``_MAX_CELLS_PER_AXIS`` per axis. Bounds are clamped to valid lat/lon.
    """
    valid = [
        (lat, lon)
        for lat, lon in points
        if math.isfinite(lat) and math.isfinite(lon) and (lat or lon)
    ]
    if not valid:
        return []
    lats = [lat for lat, _ in valid]
    lons = [lon for _, lon in valid]
    pad = _BBOX_PADDING_DEGREES
    south = max(-90.0, min(lats) - pad)
    north = min(90.0, max(lats) + pad)
    west = max(-180.0, min(lons) - pad)
    east = min(180.0, max(lons) + pad)
    width = east - west
    height = north - south
    if width <= 0.0 and height <= 0.0:
        width = height = _CELL_DEGREES
    cell_lon = max(_CELL_DEGREES, width / _MAX_CELLS_PER_AXIS)
    cell_lat = max(_CELL_DEGREES, height / _MAX_CELLS_PER_AXIS)

    cells: list[tuple[float, float, float, float]] = []
    lat = south
    while lat < north:
        cell_north = min(lat + cell_lat, north)
        lon = west
        while lon < east:
            cell_east = min(lon + cell_lon, east)
            cells.append((lat, lon, cell_north, cell_east))
            lon = cell_east
        lat = cell_north
    return cells


def merge_intersections(
    tables: Sequence[Sequence[StreetIntersection]],
) -> list[StreetIntersection]:
    """Union intersection tables, deduping by coordinate.

    A way that straddles a cell border is returned by both neighbouring cell
    queries, so identical crossings can appear in several tables. Coordinates
    are rounded to ~10 cm for the merge key and the name sets are unioned.
    """
    by_node: dict[tuple[int, int], set[str]] = {}
    coords: dict[tuple[int, int], tuple[float, float]] = {}
    for table in tables:
        for intersection in table:
            key = (round(intersection.lat * 10_000_000), round(intersection.lon * 10_000_000))
            coords.setdefault(key, (intersection.lat, intersection.lon))
            by_node.setdefault(key, set()).update(intersection.names)
    return [
        StreetIntersection(lat=coords[key][0], lon=coords[key][1], names=tuple(sorted(names)))
        for key, names in by_node.items()
        if len(names) >= 2
    ]


def build_intersections(result: Any) -> list[StreetIntersection]:
    """Derive street intersections from a way-geometry Overpass result.

    Each named way claims every member node; a node claimed by two or more
    distinctly named ways is an intersection of those streets. Ways whose
    member nodes are not present in the result (e.g. an over-limit way whose
    nodes were truncated) are skipped rather than failing the whole table.
    """
    coords: dict[int, tuple[float, float]] = {}
    for node in result.nodes:
        coords[node.id] = (float(node.lat), float(node.lon))

    names_at: dict[int, set[str]] = {}
    for way in result.ways:
        name = str((way.tags or {}).get("name") or "").strip()
        if not name:
            continue
        try:
            member_nodes = way.nodes
        except Exception as exc:
            # overpy raises DataIncomplete when a referenced node is absent.
            logger.debug("Street way %s has unresolved member nodes: %s", way.id, exc)
            continue
        for node in member_nodes:
            if node.id in coords:
                names_at.setdefault(node.id, set()).add(name)

    intersections: list[StreetIntersection] = []
    for node_id, names in names_at.items():
        if len(names) < 2:
            continue
        lat, lon = coords[node_id]
        intersections.append(StreetIntersection(lat=lat, lon=lon, names=tuple(sorted(names))))
    logger.info("Street intersection table: %d crossings", len(intersections))
    return intersections


def _local_xy(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    """Project ``(lat, lon)`` to metres in a plane tangent at ``(lat0, lon0)``."""
    x = math.radians(lon - lon0) * math.cos(math.radians(lat0)) * _EARTH_RADIUS_M
    y = math.radians(lat - lat0) * _EARTH_RADIUS_M
    return x, y


class StreetGrid:
    """KD-tree index of street intersections for nearest-cross-street lookup."""

    def __init__(
        self,
        intersections: Sequence[StreetIntersection] = (),
        max_distance_meters: float = _DEFAULT_MAX_DISTANCE_M,
    ) -> None:
        """Index ``intersections`` in local metre coordinates around their mean."""
        self._max_distance_meters = max_distance_meters
        self._intersections: list[StreetIntersection] = list(intersections)
        self._points: np.ndarray | None = None
        self._tree: KDTree | None = None
        self._origin: tuple[float, float] = (0.0, 0.0)
        if not self._intersections:
            return
        lat0 = sum(item.lat for item in self._intersections) / len(self._intersections)
        lon0 = sum(item.lon for item in self._intersections) / len(self._intersections)
        self._origin = (lat0, lon0)
        self._points = np.array(
            [_local_xy(item.lat, item.lon, lat0, lon0) for item in self._intersections],
            dtype=float,
        )
        self._tree = KDTree(self._points)

    def __len__(self) -> int:
        """Number of indexed intersections (0 when the grid is empty)."""
        return len(self._intersections)

    def cross_streets_for(
        self,
        lat: float,
        lon: float,
        street_name: str,
        max_results: int = 2,
    ) -> list[str]:
        """Nearest cross streets along ``street_name``, nearest first.

        Only intersections that include the address's own street are eligible
        (matched via :func:`normalize_street_name`, so directional and street
        type spelling differences do not matter). The returned names are the
        *other* streets at those nodes, so the address's own street never
        appears. Returns an empty list when the street cannot be identified,
        no coordinates are known, or no crossing lies within the grid's cutoff.
        """
        if self._tree is None or self._points is None:
            return []
        if not (math.isfinite(lat) and math.isfinite(lon)) or not (lat or lon):
            return []
        own = normalize_street_name(street_name)
        if not own:
            return []

        x, y = _local_xy(lat, lon, *self._origin)
        indices = self._tree.query_ball_point((x, y), r=self._max_distance_meters)
        if not indices:
            return []

        deltas = self._points[indices] - (x, y)
        distances = np.hypot(deltas[:, 0], deltas[:, 1])
        order = np.argsort(distances, kind="stable")

        crosses: list[str] = []
        for position in order:
            names = self._intersections[indices[position]].names
            if own not in {normalize_street_name(name) for name in names}:
                continue
            for name in names:
                if normalize_street_name(name) == own:
                    continue
                if name not in crosses:
                    crosses.append(name)
                break
            if len(crosses) >= max_results:
                break
        return crosses[:max_results]
