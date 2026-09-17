"""Discover populated places within a bounding box via the Overpass API.

When the area query resolves to a county (or other non-city feature),
the address pipeline needs a list of real city/town names to assign to
synthesized addresses.  This module queries Overpass for ``place=city|town|village``
nodes and returns them as :class:`CityPlace` objects.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .logging_conf import get_logger

logger = get_logger("city_discovery")


@dataclass(frozen=True, slots=True)
class CityPlace:
    """A populated place discovered via Overpass."""

    name: str
    place_type: str  # "city", "town", "village"
    lat: float
    lon: float
    population: int | None = None


def discover_cities_in_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    query_runner: Callable[[str], Any],
) -> list[CityPlace]:
    """Query Overpass for populated places inside a bounding box.

    Args:
        south, west, north, east: Bounding box in decimal degrees.
        query_runner: A callable that accepts an Overpass QL string and
            returns an ``overpy.Result``.

    Returns:
        Deduplicated :class:`CityPlace` objects sorted by population
        (descending, ``None`` populations last), then alphabetically.
    """
    import overpy

    bbox = f"{south},{west},{north},{east}"
    query = (
        "[out:xml][timeout:30];"
        f'node["place"~"city|town|village"]({bbox});'
        "out center;"
    )

    try:
        result = query_runner(query)
    except overpy.exception.OverPyException as exc:
        logger.warning("Overpass city-discovery query failed: %s", exc)
        return []

    places: list[CityPlace] = []
    for node in result.nodes:
        tags = node.tags or {}
        name = tags.get("name")
        if not name:
            continue
        place_type = str(tags.get("place", "unknown"))
        lat = float(getattr(node, "lat", 0) or 0)
        lon = float(getattr(node, "lon", 0) or 0)
        population = _parse_population(tags.get("population"))
        places.append(
            CityPlace(
                name=name,
                place_type=place_type,
                lat=lat,
                lon=lon,
                population=population,
            )
        )

    # Deduplicate by name, keeping the entry with the highest population.
    seen: dict[str, CityPlace] = {}
    for p in places:
        existing = seen.get(p.name)
        if existing is None or (p.population or 0) > (existing.population or 0):
            seen[p.name] = p

    deduped = sorted(seen.values(), key=lambda p: (-(p.population or 0), p.name))
    logger.info(
        "Discovered %d populated places in bbox (%.2f,%.2f,%.2f,%.2f)",
        len(deduped),
        south,
        west,
        north,
        east,
    )
    return deduped


def _parse_population(raw: str | None) -> int | None:
    """Parse an OSM ``population`` tag value, returning ``None`` on failure."""
    if not raw:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None
