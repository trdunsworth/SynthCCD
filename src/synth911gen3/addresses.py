from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

import httpx

from .domain import Address
from .exceptions import AddressLookupError


class AddressProvider(Protocol):
    def load_addresses(self, area_query: str) -> list[Address]:
        """Load addresses for a requested geography."""


class StaticAddressProvider:
    def __init__(self, addresses: Sequence[Address]) -> None:
        self._addresses = list(addresses)

    def load_addresses(self, area_query: str) -> list[Address]:
        if not self._addresses:
            raise AddressLookupError("StaticAddressProvider requires at least one address.")
        return list(self._addresses)


class OpenStreetMapAddressProvider:
    SEARCH_URL = "https://nominatim.openstreetmap.org/search"

    def __init__(self, client: httpx.Client | None = None, limit: int = 75) -> None:
        self._client = client or httpx.Client(
            headers={
                "User-Agent": "synth911gen3/0.1.0 (synthetic CAD data generator)",
                "Accept": "application/json",
            },
            timeout=20.0,
        )
        self._limit = limit

    def load_addresses(self, area_query: str) -> list[Address]:
        try:
            response = self._client.get(
                self.SEARCH_URL,
                params={
                    "q": area_query,
                    "format": "jsonv2",
                    "addressdetails": 1,
                    "limit": self._limit,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AddressLookupError(f"Unable to query OpenStreetMap for '{area_query}'.") from exc

        addresses = self._parse_addresses(response.json())
        if len(addresses) < 5:
            raise AddressLookupError(
                f"OpenStreetMap returned too few usable addresses for '{area_query}'."
            )
        return addresses

    @staticmethod
    def _parse_addresses(payload: Any) -> list[Address]:
        if not isinstance(payload, list):
            raise AddressLookupError("OpenStreetMap returned an unexpected payload format.")

        parsed: list[Address] = []
        seen: set[tuple[str, str, str]] = set()
        for item in payload:
            if not isinstance(item, dict):
                continue
            components = item.get("address", {})
            if not isinstance(components, dict):
                continue

            road = (
                components.get("road")
                or components.get("pedestrian")
                or components.get("residential")
                or components.get("footway")
            )
            if not isinstance(road, str) or not road.strip():
                continue

            city = (
                components.get("city")
                or components.get("town")
                or components.get("village")
                or components.get("hamlet")
                or components.get("county")
            )
            state = components.get("state") or components.get("state_district")
            if not isinstance(city, str) or not city.strip():
                continue
            if not isinstance(state, str) or not state.strip():
                continue

            house_number = components.get("house_number")
            street_address = f"{house_number} {road}".strip() if house_number else road
            key = (street_address, city, state)
            if key in seen:
                continue
            seen.add(key)
            parsed.append(Address(street_address=street_address, city=city, state=state))
        return parsed
