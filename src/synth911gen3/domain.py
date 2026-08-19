"""Core domain models shared across the package.

Defines the :class:`Address` value object used by every address provider
and the :class:`GenerationResult` returned by the generation pipeline, plus
the street-address parsing helpers that split a free-form OSM street string
into its CAD-style components (number, name, type, directionals).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

_DIRECTIONS = frozenset(
    {
        "N",
        "S",
        "E",
        "W",
        "NE",
        "NW",
        "SE",
        "SW",
        "NORTH",
        "SOUTH",
        "EAST",
        "WEST",
        "NORTHEAST",
        "NORTHWEST",
        "SOUTHEAST",
        "SOUTHWEST",
    }
)

_DIRECTION_ABBREVIATIONS = {
    "NORTH": "N",
    "SOUTH": "S",
    "EAST": "E",
    "WEST": "W",
    "NORTHEAST": "NE",
    "NORTHWEST": "NW",
    "SOUTHEAST": "SE",
    "SOUTHWEST": "SW",
}

_STREET_TYPES = frozenset(
    {
        "ST",
        "STREET",
        "AVE",
        "AV",
        "AVENUE",
        "BLVD",
        "BOULEVARD",
        "RD",
        "ROAD",
        "DR",
        "DRIVE",
        "LN",
        "LANE",
        "CT",
        "COURT",
        "CIR",
        "CIRCLE",
        "PL",
        "PLACE",
        "PKWY",
        "PARKWAY",
        "WAY",
        "TRL",
        "TRAIL",
        "HWY",
        "HIGHWAY",
        "PK",
        "PARK",
        "PIKE",
        "TER",
        "TERRACE",
        "RTE",
        "ROUTE",
        "EXPY",
        "VIEW",
        "VW",
        "HTS",
        "HEIGHTS",
        "MALL",
        "PATH",
        "ROW",
        "RUN",
        "SQ",
        "SQUARE",
        "TPKE",
        "TURNPIKE",
        "XING",
        "CROSSING",
        "TRAFFICWAY",
        "LOOP",
        "COMMONS",
        "PASS",
        "GATEWAY",
    }
)


def _normalize_direction(value: str) -> str:
    """Abbreviate a compass direction (``NORTH`` → ``N``); pass through others."""
    return _DIRECTION_ABBREVIATIONS.get(value.upper(), value.upper())


def _is_house_number(token: str) -> bool:
    """Return True when a token looks like a street number.

    Accepts plain digits (``204``) and alphanumeric house numbers
    (``17A``), while rejecting ordinals such as ``12th`` that belong to
    the street name.
    """
    if token.isdigit():
        return True
    lower = token.lower()
    if lower.endswith(("st", "nd", "rd", "th")):
        return False
    return token[0].isdigit()


def parse_address_parts(
    street_address: str,
) -> tuple[str, str, str, str, str]:
    """Split a street address into (number, name, type, prefix direction, postfix direction).

    Handles common US patterns such as ``"204 E 12th St"`` or
    ``"890 N Oak Trafficway NW"``. Directionals are normalized to abbreviations
    (``NORTH`` → ``N``); unknown components fall back to empty strings.
    """
    tokens = [token for token in street_address.split() if token]
    if not tokens:
        return "", "", "", "", ""

    street_number = ""
    if _is_house_number(tokens[0]):
        street_number = tokens.pop(0)

    postfix_directional = ""
    if len(tokens) >= 2 and tokens[-1].upper() in _DIRECTIONS:
        postfix_directional = _normalize_direction(tokens.pop())

    street_type = ""
    if tokens and tokens[-1].upper() in _STREET_TYPES:
        street_type = tokens.pop()

    prefix_directional = ""
    if len(tokens) >= 2 and tokens[0].upper() in _DIRECTIONS:
        prefix_directional = _normalize_direction(tokens.pop(0))

    street_name = " ".join(tokens)
    return street_number, street_name, street_type, prefix_directional, postfix_directional


_ZIP_PLUS4_RE = re.compile(r"^\d{5}-\d{4}$")


def normalize_postal_code(postal_code: str) -> str:
    """Return *postal_code* with any US ZIP+4 suffix truncated to the 5-digit ZIP.

    OpenStreetMap's ``addr:postcode`` tag for US addresses is sometimes a
    plain 5-digit ZIP and sometimes a 9-digit ZIP+4 (e.g. ``64110-1234``).
    Analysts group by postal code, so both forms should collapse to the
    5-digit ZIP. Only the US-specific ``DDDDD-DDDD`` pattern is truncated;
    every other format (Canadian ``L4T 2D6``, UK ``SW1A 1AA``, German
    ``10115``, ...) is passed through unchanged.
    """
    if _ZIP_PLUS4_RE.match(postal_code):
        return postal_code[:5]
    return postal_code


@dataclass(frozen=True, slots=True)
class Address:
    """A street address in CAD-ready component form.

    Fields mirror the output schema (``street_number``, ``street_name``,
    ``street_type``, prefix/postfix directionals, ``postal_code``) plus
    the OSM-derived coordinates and geographic ``zone`` classification
    (URBAN, SUBURBAN, or RURAL) used for travel-time multipliers.

    When only the free-form ``street_address`` is supplied, the
    components are derived automatically via :func:`parse_address_parts`.
    """

    street_address: str
    city: str
    state: str
    street_number: str = ""
    street_name: str = ""
    street_type: str = ""
    prefix_directional: str = ""
    postfix_directional: str = ""
    postal_code: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    zone: str = "URBAN"

    def __post_init__(self) -> None:
        if not self.street_name:
            number, name, street_type, prefix, postfix = parse_address_parts(self.street_address)
            object.__setattr__(self, "street_number", self.street_number or number)
            object.__setattr__(self, "street_name", name)
            object.__setattr__(self, "street_type", street_type)
            object.__setattr__(self, "prefix_directional", prefix)
            object.__setattr__(self, "postfix_directional", postfix)
        if self.postal_code:
            normalized = normalize_postal_code(self.postal_code)
            if normalized != self.postal_code:
                object.__setattr__(self, "postal_code", normalized)

    @property
    def location(self) -> str:
        """Combined ``street_address, city, state`` string for output."""
        return f"{self.street_address}, {self.city}, {self.state}"


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Output of one generation run, before or after export.

    ``incidents`` and ``hourly_call_counts`` hold the generated frames
    (or ``None`` when that dataset was not requested); ``exported_artifacts``
    maps artifact descriptions to their written paths (or in-memory values
    for pandas/polars results).
    """

    incidents: pd.DataFrame | None
    hourly_call_counts: pd.DataFrame | None
    exported_artifacts: dict[str, Path | Any]
