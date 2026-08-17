"""Real address acquisition from OpenStreetMap with local caching.

The CAD generator needs a pool of real street addresses for the chosen
geography. :class:`OpenStreetMapAddressProvider` geocodes an area query
(place name or bounding box) via Nominatim, pulls addressed
buildings/ways from the Overpass API, classifies each into a geographic
zone (URBAN/SUBURBAN/RURAL), and caches the result as parquet plus a
small JSON metadata file. :class:`StaticAddressProvider` wraps a fixed
in-memory pool for tests and offline runs.

Nominatim rate limits and retry/backoff are handled inside the provider;
see the module constants for the request policy.
"""

from __future__ import annotations

import hashlib
import json
import ssl
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
import overpy
import pandas as pd

from .domain import Address
from .emergency_numbers import normalize_country
from .exceptions import AddressConnectionError, AddressLookupError
from .logging_conf import get_logger

logger = get_logger("addresses")

_NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_USER_AGENT = "SynthCCD/0.1.0 (synthetic CAD data generator)"
_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "SynthCCD"
_NOMINATIM_MIN_REQUEST_INTERVAL = 1.0  # seconds; Nominatim usage policy: max 1 req/s
_RETRYABLE_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})

_US_STATE_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}

_LOCAL_HIGHWAY_PATTERN = (
    "^(residential|living_street|unclassified|service|tertiary|secondary|primary)$"
)


class AddressProvider(Protocol):
    def load_addresses(self, area_query: str) -> list[Address]:
        """Load addresses for a requested geography."""

    def resolved_country(self) -> str | None:
        """ISO 3166-1 alpha-2 country code of the loaded region, or ``None`` when unknown."""


class StaticAddressProvider:
    """Address provider backed by a fixed in-memory list (tests, offline runs)."""

    def __init__(self, addresses: Sequence[Address]) -> None:
        """Store the address pool; the area query is ignored."""
        self._addresses = list(addresses)

    def load_addresses(self, area_query: str) -> list[Address]:
        """Return the static pool; raises when the pool is empty."""
        if not self._addresses:
            raise AddressLookupError("StaticAddressProvider requires at least one address.")
        return list(self._addresses)

    def resolved_country(self) -> str | None:
        """Static address pools carry no region metadata, so the country is unknown."""
        return None


@dataclass(frozen=True, slots=True)
class _GeocodedArea:
    """A bounding box plus the place-name metadata Nominatim returned for it."""

    south: float
    west: float
    north: float
    east: float
    city: str
    state: str
    country_code: str = ""


def _normalize_country_code(value: str) -> str:
    """Normalize a raw country code from Nominatim (e.g. ``"us"`` -> ``"US"``)."""
    value = value.strip()
    if not value:
        return ""
    try:
        return normalize_country(value)
    except ValueError:
        return ""


def _parse_bbox(area_query: str) -> tuple[float, float, float, float] | None:
    """Parse an area query of the form "minlat,minlon,maxlat,maxlon" into (south, west, north, east)."""
    parts = [part.strip() for part in area_query.split(",")]
    if len(parts) != 4:
        return None
    try:
        south, west, north, east = (float(part) for part in parts)
    except ValueError:
        return None
    if not (-90 <= south <= north <= 90 and -180 <= west <= east <= 180):
        return None
    return south, west, north, east


def _tls_cause(exc: BaseException) -> ssl.SSLCertVerificationError | None:
    """Return the first certificate-verification error in an exception chain."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ssl.SSLCertVerificationError):
            return current
        current = current.__cause__ or current.__context__
    return None


def _describe_http_error(exc: httpx.HTTPError) -> str:
    """Human-readable description of an HTTP failure, flagging proxy TLS issues."""
    tls = _tls_cause(exc)
    if tls is not None:
        message = getattr(tls, "verify_message", "") or str(tls)
        return (
            f"certificate verification failed ({message}). If you are behind a "
            "TLS-inspecting proxy, set SYNTHCCD_SYSTEM_TRUST=1 to verify against the "
            "OS trust store."
        )
    detail = str(exc.__cause__ or exc)
    return detail or type(exc).__name__


def _normalize_state(state: str) -> str:
    """Expand US state abbreviations to full names; pass through anything else."""
    normalized = state.strip()
    if normalized.upper() in _US_STATE_NAMES:
        return _US_STATE_NAMES[normalized.upper()]
    return normalized


def _extract_city(components: dict[str, Any]) -> str:
    """Pick the first populated place-name component (city, town, county, ...)."""
    for key in ("city", "town", "village", "hamlet", "municipality", "county"):
        value = components.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _build_real_address_query(
    south: float, west: float, north: float, east: float, limit: int
) -> str:
    """Overpass query for ways/nodes carrying addr:housenumber + addr:street tags."""
    bbox = f"{south},{west},{north},{east}"
    return (
        "[out:xml][timeout:60];("
        f'way["addr:housenumber"]["addr:street"]({bbox});'
        f'node["addr:housenumber"]["addr:street"]({bbox});'
        f");out center {limit};"
    )


def _build_named_street_query(
    south: float, west: float, north: float, east: float, limit: int
) -> str:
    """Overpass query for named local streets (fallback pool when addressed ways are scarce)."""
    bbox = f"{south},{west},{north},{east}"
    return (
        "[out:xml][timeout:60];"
        f'way["highway"~"{_LOCAL_HIGHWAY_PATTERN}"]["name"]({bbox});'
        f"out center {limit};"
    )


class OpenStreetMapAddressProvider:
    """Fetch, cache, and classify real addresses from OpenStreetMap.

    Two-step pipeline: geocode the area query (place name or bbox) via
    Nominatim, then query Overpass for addressed elements inside the
    bounding box. Results are cached as parquet keyed by the area query so
    repeat runs are offline. ``query_runner`` overrides the Overpass call
    for tests.
    """

    def __init__(
        self,
        client: httpx.Client | None = None,
        cache_dir: Path = _DEFAULT_CACHE_DIR,
        query_runner: Callable[[str], overpy.Result] | None = None,
        min_addresses: int = 5,
        max_addresses: int = 1_000,
        max_retries: int = 3,
        nominatim_min_interval: float = _NOMINATIM_MIN_REQUEST_INTERVAL,
    ) -> None:
        """Configure the HTTP client, cache location, and fetch limits."""
        self._client = client or httpx.Client(
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "application/json, application/osm3s+xml",
            },
            timeout=120.0,
        )
        self._cache_dir = Path(cache_dir)
        self._query_runner = query_runner or self._run_overpass_query
        self._min_addresses = min_addresses
        self._max_addresses = max_addresses
        self._max_retries = max_retries
        self._nominatim_min_interval = nominatim_min_interval
        self._last_nominatim_request = 0.0
        self._resolved_country = ""

    def load_addresses(self, area_query: str) -> list[Address]:
        """Return the address pool for ``area_query``, using cache when possible."""
        cache_path = self._cache_path(area_query)
        meta_path = self._meta_path(area_query)
        cached = self._load_cache(cache_path)
        if cached is not None:
            logger.debug("Cache hit for '%s' (%d addresses)", area_query, len(cached))
            self._resolved_country = self._load_meta(meta_path)
            return cached

        logger.info("Fetching addresses for '%s' (no cache at %s)", area_query, cache_path)
        addresses = self._fetch_addresses(area_query)
        logger.info("Fetched %d addresses", len(addresses))
        self._write_cache(cache_path, addresses)
        self._write_meta(meta_path, self._resolved_country)
        return addresses

    def resolved_country(self) -> str | None:
        """ISO 3166-1 alpha-2 country of the last loaded area, or ``None`` when unknown."""
        return self._resolved_country or None

    @staticmethod
    def _digest(area_query: str) -> str:
        """Stable short hex digest of an area query, used as the cache key."""
        return hashlib.md5(area_query.strip().lower().encode("utf-8")).hexdigest()[:12]

    def _cache_path(self, area_query: str) -> Path:
        """Path to the parquet cache file for an area query."""
        return self._cache_dir / f"addresses_{self._digest(area_query)}.parquet"

    def _meta_path(self, area_query: str) -> Path:
        """Path to the JSON metadata file (country code) for an area query."""
        return self._cache_dir / f"addresses_{self._digest(area_query)}.meta.json"

    @staticmethod
    def _write_meta(path: Path, country_code: str) -> None:
        """Persist the resolved country code next to the cached address pool."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"country_code": country_code}), encoding="utf-8")

    @staticmethod
    def _load_meta(path: Path) -> str:
        """Read the cached country code; returns ``""`` when absent or unreadable."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return str(data.get("country_code") or "")
        except (OSError, ValueError, TypeError):
            return ""

    def _load_cache(self, path: Path) -> list[Address] | None:
        """Read the parquet cache into Address objects; ``None`` on miss/corruption."""
        if not path.is_file():
            return None
        try:
            frame = pd.read_parquet(path)
        except Exception:
            return None
        if len(frame) < self._min_addresses:
            return None
        postal_codes = frame["postal_code"] if "postal_code" in frame.columns else [""] * len(frame)
        latitudes = frame["latitude"] if "latitude" in frame.columns else [0.0] * len(frame)
        longitudes = frame["longitude"] if "longitude" in frame.columns else [0.0] * len(frame)
        zones = frame["zone"] if "zone" in frame.columns else ["URBAN"] * len(frame)
        return [
            Address(
                str(street),
                str(city),
                str(state),
                postal_code=str(postal) if pd.notna(postal) else "",
                latitude=float(lat) if pd.notna(lat) else 0.0,
                longitude=float(lon) if pd.notna(lon) else 0.0,
                zone=str(zone) if pd.notna(zone) else "URBAN",
            )
            for street, city, state, postal, lat, lon, zone in zip(
                frame["street_address"],
                frame["city"],
                frame["state"],
                postal_codes,
                latitudes,
                longitudes,
                zones,
            )
        ]

    def _write_cache(self, path: Path, addresses: list[Address]) -> None:
        """Persist the address pool as parquet for offline repeat runs."""
        frame = pd.DataFrame(
            {
                "street_address": [address.street_address for address in addresses],
                "street_number": [address.street_number for address in addresses],
                "street_name": [address.street_name for address in addresses],
                "street_type": [address.street_type for address in addresses],
                "prefix_directional": [address.prefix_directional for address in addresses],
                "postfix_directional": [address.postfix_directional for address in addresses],
                "postal_code": [address.postal_code for address in addresses],
                "city": [address.city for address in addresses],
                "state": [address.state for address in addresses],
                "latitude": [address.latitude for address in addresses],
                "longitude": [address.longitude for address in addresses],
                "zone": [address.zone for address in addresses],
            }
        )
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False)

    def _fetch_addresses(self, area_query: str) -> list[Address]:
        """Geocode the area, pull addressed elements, and fall back to named streets."""
        bbox = _parse_bbox(area_query)
        if bbox is None:
            area = self._geocode_area(area_query)
        else:
            area = self._geocode_bbox(bbox)
        self._resolved_country = _normalize_country_code(area.country_code)

        addresses = self._query_real_addresses(area)
        if len(addresses) < self._min_addresses:
            street_addresses = self._query_named_streets(area)
            addresses = self._dedupe(addresses + street_addresses)

        if len(addresses) < self._min_addresses:
            raise AddressLookupError(
                f"OpenStreetMap returned too few usable addresses for '{area_query}'."
            )
        return addresses[: self._max_addresses]

    def _nominatim_get(self, url: str, params: dict[str, Any]) -> Any:
        """GET a Nominatim endpoint honoring the 1 req/s usage policy with retry/backoff.

        Returns the parsed JSON payload. Retries on rate-limit (429) and server
        errors (5xx) up to ``max_retries`` with exponential backoff, honoring a
        ``Retry-After`` header when present.
        """
        for attempt in range(self._max_retries):
            elapsed = time.monotonic() - self._last_nominatim_request
            if elapsed < self._nominatim_min_interval:
                time.sleep(self._nominatim_min_interval - elapsed)

            try:
                response = self._client.get(url, params=params)
            except httpx.HTTPError as exc:
                raise AddressConnectionError(
                    "Unable to reach the OpenStreetMap Nominatim service: "
                    f"{_describe_http_error(exc)}"
                ) from exc
            self._last_nominatim_request = time.monotonic()

            if response.status_code == 200:
                return response.json()
            if response.status_code in _RETRYABLE_HTTP_STATUS:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else (2**attempt)
                time.sleep(min(delay, 30))
                continue
            raise AddressLookupError(
                f"OpenStreetMap Nominatim request failed (HTTP {response.status_code})."
            )
        raise AddressLookupError(
            "OpenStreetMap Nominatim request failed after retries (HTTP rate limit or server error)."
        )

    def _geocode_area(self, area_query: str) -> _GeocodedArea:
        """Resolve a place-name query to a bounding box via Nominatim search."""
        payload = self._nominatim_get(
            _NOMINATIM_SEARCH_URL,
            params={"q": area_query, "format": "jsonv2", "addressdetails": 1, "limit": 1},
        )

        if not isinstance(payload, list) or not payload:
            raise AddressLookupError(f"Unable to geocode area query '{area_query}'.")

        item = payload[0]
        if not isinstance(item, dict) or "boundingbox" not in item:
            raise AddressLookupError(f"Unable to geocode area query '{area_query}'.")

        south, north, west, east = (float(value) for value in item["boundingbox"])
        components = item.get("address") if isinstance(item.get("address"), dict) else {}
        return _GeocodedArea(
            south=south,
            west=west,
            north=north,
            east=east,
            city=_extract_city(components),
            state=_normalize_state(str(components.get("state") or "")),
            country_code=_normalize_country_code(str(components.get("country_code") or "")),
        )

    def _geocode_bbox(self, bbox: tuple[float, float, float, float]) -> _GeocodedArea:
        """Attach place metadata to a caller-supplied bbox via Nominatim reverse lookup."""
        south, west, north, east = bbox
        payload = self._nominatim_get(
            _NOMINATIM_REVERSE_URL,
            params={
                "format": "jsonv2",
                "lat": (south + north) / 2,
                "lon": (west + east) / 2,
                "addressdetails": 1,
            },
        )

        components = payload.get("address") if isinstance(payload, dict) else {}
        return _GeocodedArea(
            south=south,
            west=west,
            north=north,
            east=east,
            city=_extract_city(components),
            state=_normalize_state(str(components.get("state") or "")),
            country_code=_normalize_country_code(str(components.get("country_code") or "")),
        )

    def _run_overpass_query(self, query: str) -> overpy.Result:
        """POST an Overpass QL query to the public API with retry/backoff."""
        last_status: int | None = None
        for attempt in range(self._max_retries):
            try:
                response = self._client.post(_OVERPASS_URL, content=query.encode("utf-8"))
            except httpx.HTTPError as exc:
                raise AddressConnectionError(
                    "Unable to reach the OpenStreetMap Overpass API: "
                    f"{_describe_http_error(exc)}"
                ) from exc
            last_status = response.status_code
            if response.status_code == 200:
                return overpy.Overpass().parse_xml(response.content)
            if response.status_code in (429, 503, 504):
                time.sleep((attempt + 1) * 2)
                continue
            break
        raise AddressLookupError(f"Overpass API request failed (HTTP {last_status}).")

    def _query_real_addresses(self, area: _GeocodedArea) -> list[Address]:
        """Query Overpass for addressed elements in the area's bounding box."""
        query = _build_real_address_query(
            area.south, area.west, area.north, area.east, self._max_addresses
        )
        try:
            result = self._query_runner(query)
        except AddressConnectionError:
            raise
        except AddressLookupError:
            return []
        return self._parse_elements(result, area.city, area.state)

    def _classify_zone(self, tags: dict[str, str], lat: float, lon: float) -> str:
        """Classify address zone as URBAN, SUBURBAN, or RURAL based on OSM tags."""
        landuse = tags.get("landuse", "").lower()
        place = tags.get("place", "").lower()
        highway = tags.get("highway", "").lower()
        building = tags.get("building", "").lower()
        residential = tags.get("residential", "").lower()

        if place in ("city", "town"):
            return "URBAN"
        if landuse in ("commercial", "industrial", "retail", "residential") and place not in ("village", "hamlet"):
            return "URBAN"
        if building in ("apartments", "commercial", "office", "retail", "hotel"):
            return "URBAN"
        if highway in ("primary", "secondary", "tertiary", "motorway", "trunk"):
            return "URBAN"

        if place in ("suburb", "neighbourhood"):
            return "SUBURBAN"
        if landuse == "residential" and place in ("village", "hamlet"):
            return "SUBURBAN"
        if residential in ("urban", "suburban"):
            return "SUBURBAN"
        if building in ("house", "detached", "semi_detached", "terrace"):
            return "SUBURBAN"

        if place in ("village", "hamlet", "isolated_dwelling", "farm"):
            return "RURAL"
        if landuse in ("farmland", "forest", "meadow", "orchard", "vineyard"):
            return "RURAL"
        if highway in ("unclassified", "residential", "service", "track", "path"):
            return "RURAL"

        return "URBAN"

    def _query_named_streets(self, area: _GeocodedArea) -> list[Address]:
        """Fallback: synthesize addresses on named local streets when real ones are scarce."""
        query = _build_named_street_query(
            area.south, area.west, area.north, area.east, self._max_addresses
        )
        try:
            result = self._query_runner(query)
        except AddressConnectionError:
            raise
        except AddressLookupError:
            return []
        street_names = self._named_streets(result)
        return self._synthesize_addresses(street_names, area.city, area.state, self._max_addresses)

    def _parse_elements(
        self, result: overpy.Result, fallback_city: str, fallback_state: str
    ) -> list[Address]:
        """Convert Overpass ways/nodes with address tags into deduplicated Addresses."""
        addresses: list[Address] = []
        for element in [*result.ways, *result.nodes]:
            tags = element.tags or {}
            housenumber = tags.get("addr:housenumber")
            street = tags.get("addr:street")
            if not housenumber or not street:
                continue
            city = tags.get("addr:city") or fallback_city
            state = _normalize_state(tags.get("addr:state") or fallback_state)
            if not city or not state:
                continue
            # Extract coordinates — Nodes have lat/lon; Ways have center_lat/center_lon
            lat = getattr(element, "lat", None)
            lon = getattr(element, "lon", None)
            if lat is None:
                lat = getattr(element, "center_lat", None)
                lon = getattr(element, "center_lon", None)
            lat_val = float(lat) if lat is not None else 0.0
            lon_val = float(lon) if lon is not None else 0.0
            zone = self._classify_zone(tags, lat_val, lon_val)
            addresses.append(
                Address(
                    f"{housenumber} {street}".strip(),
                    city,
                    state,
                    street_number=housenumber,
                    postal_code=tags.get("addr:postcode") or "",
                    latitude=lat_val,
                    longitude=lon_val,
                    zone=zone,
                )
            )
        return self._dedupe(addresses)

    @staticmethod
    def _named_streets(result: overpy.Result) -> list[tuple[str, float, float]]:
        """Unique (street_name, lat, lon) from named-street query results, in order.

        For Way elements the centre coordinates come from ``center_lat`` /
        ``center_lon``; for Nodes they come from ``lat`` / ``lon``.
        """
        entries: list[tuple[str, float, float]] = []
        seen: set[str] = set()
        for way in result.ways:
            name = (way.tags or {}).get("name")
            if name and name not in seen:
                lat = getattr(way, "center_lat", None)
                lon = getattr(way, "center_lon", None)
                seen.add(name)
                entries.append((name, float(lat) if lat else 0.0, float(lon) if lon else 0.0))
        return entries

    @staticmethod
    def _synthesize_addresses(
        street_names: list[tuple[str, float, float]],
        city: str,
        state: str,
        count: int,
    ) -> list[Address]:
        """Build plausible house numbers on the given streets (deterministic by name).

        Each entry in *street_names* is ``(name, lat, lon)`` — the centre
        coordinate of the source Way.  Synthesised addresses inherit those
        coordinates so the output carries real location data.
        """
        if not street_names:
            return []
        addresses: list[Address] = []
        seen: set[tuple[str, str, str]] = set()
        index = 0
        while len(addresses) < count and index < count * len(street_names):
            name, src_lat, src_lon = street_names[index % len(street_names)]
            offset = index // len(street_names)
            number = (
                100 + (int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) + offset * 97) % 8_900
            )
            address = Address(
                f"{number} {name}",
                city,
                state,
                zone="SUBURBAN",
                latitude=src_lat,
                longitude=src_lon,
            )
            key = (address.street_address, city, state)
            if key not in seen:
                seen.add(key)
                addresses.append(address)
            index += 1
        return addresses

    @staticmethod
    def _dedupe(addresses: list[Address]) -> list[Address]:
        """Drop exact (street_address, city, state) duplicates, keeping first occurrence."""
        seen: set[tuple[str, str, str]] = set()
        unique: list[Address] = []
        for address in addresses:
            key = (address.street_address, address.city, address.state)
            if key not in seen:
                seen.add(key)
                unique.append(address)
        return unique
