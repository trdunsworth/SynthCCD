"""Offline US ZIP-code → city mapping via the ``zipcodes`` package.

The ``zipcodes`` package embeds USPS + GeoNames data (refreshed monthly)
entirely in-process — no network, no SQLite.  This module wraps it with
a focused API for the address-generation pipeline.
"""

from __future__ import annotations

import math

from .logging_conf import get_logger

logger = get_logger("postal")

# Lazy-loaded singleton — avoids import cost when unused.
_instance: PostalLookup | None = None


class PostalLookup:
    """Thin wrapper around the ``zipcodes`` package for US postal lookups."""

    def __init__(self) -> None:
        import zipcodes as _zipcodes

        self._zc = _zipcodes

    # -- single-record lookups -----------------------------------------------

    def lookup_city(self, zip_code: str) -> str | None:
        """Return the USPS canonical city name for *zip_code*, or ``None``."""
        try:
            results = self._zc.matching(zip_code)
        except (ValueError, TypeError):
            return None
        return results[0]["city"] if results else None

    def lookup_record(self, zip_code: str) -> dict | None:
        """Return the full ZIP record, or ``None`` if not found."""
        try:
            results = self._zc.matching(zip_code)
        except (ValueError, TypeError):
            return None
        return results[0] if results else None

    # -- bulk lookups --------------------------------------------------------

    def cities_in_county(self, county_name: str, state_code: str) -> list[str]:
        """Return deduplicated, sorted city names for *county_name*, *state_code*.

        Example::

            lookup.cities_in_county("Douglas County", "KS")
            # -> ["Baldwin City", "Eudora", "Lawrence", "Lecompton"]
        """
        records = self._zc.filter_by(county=county_name, state=state_code)
        return sorted({r["city"] for r in records if r.get("active")})

    def cities_in_bbox(
        self, south: float, west: float, north: float, east: float
    ) -> list[str]:
        """Return deduplicated city names for ZIPs whose centroid falls inside the bbox."""
        center_lat = (south + north) / 2
        center_lon = (west + east) / 2
        lat_span = abs(north - south) * 69.0  # ~69 miles per degree latitude
        lon_span = abs(east - west) * 69.0 * math.cos(math.radians(center_lat))
        radius = math.sqrt(lat_span**2 + lon_span**2) / 2 + 5  # +5 mi buffer

        records = self._zc.filter_by_coordinates(center_lat, center_lon, radius)
        return sorted(
            {
                r["city"]
                for r in records
                if south <= float(r["lat"]) <= north
                and west <= float(r["long"]) <= east
                and r.get("active")
            }
        )

    def city_for_coordinates(
        self, lat: float, lon: float, radius_miles: float = 5.0
    ) -> str | None:
        """Reverse lookup: find the nearest ZIP's city name."""
        records = self._zc.filter_by_coordinates(lat, lon, radius_miles)
        return records[0]["city"] if records else None


def get_postal_lookup() -> PostalLookup:
    """Return the module-level singleton (created on first call)."""
    global _instance
    if _instance is None:
        _instance = PostalLookup()
    return _instance
