from __future__ import annotations

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
    return _DIRECTION_ABBREVIATIONS.get(value.upper(), value.upper())


def _is_house_number(token: str) -> bool:
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


@dataclass(frozen=True, slots=True)
class Address:
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

    def __post_init__(self) -> None:
        if not self.street_name:
            number, name, street_type, prefix, postfix = parse_address_parts(self.street_address)
            object.__setattr__(self, "street_number", self.street_number or number)
            object.__setattr__(self, "street_name", name)
            object.__setattr__(self, "street_type", street_type)
            object.__setattr__(self, "prefix_directional", prefix)
            object.__setattr__(self, "postfix_directional", postfix)

    @property
    def location(self) -> str:
        return f"{self.street_address}, {self.city}, {self.state}"


@dataclass(frozen=True, slots=True)
class GenerationResult:
    incidents: pd.DataFrame | None
    hourly_call_counts: pd.DataFrame | None
    exported_artifacts: dict[str, Path | Any]
