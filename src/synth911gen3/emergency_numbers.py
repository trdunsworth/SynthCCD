from __future__ import annotations

import re
from dataclasses import dataclass

from .constants import DEFAULT_COUNTRY

# Country-code aliases mapped onto the canonical ISO 3166-1 alpha-2 code.
_COUNTRY_ALIASES = {
    "UK": "GB",
    "GBR": "GB",
    "USA": "US",
    "CAN": "CA",
    "FRA": "FR",
    "DEU": "DE",
    "IRL": "IE",
}


@dataclass(frozen=True, slots=True)
class EmergencyNumber:
    """A phone line that carries emergency traffic in one or more countries.

    ``number`` is the raw digits as dialed (e.g. ``"911"`` or a full 10-digit
    direct-dial line). ``label`` is the human display string and ``description``
    explains which agency/service the line reaches. ``kind`` is metadata only —
    every registered line is treated as an emergency line in the phone-metrics
    output.
    """

    number: str
    label: str = ""
    description: str = ""
    kind: str = "emergency"

    def __post_init__(self) -> None:
        object.__setattr__(self, "number", normalize_number(self.number))
        if not self.number:
            raise ValueError("EmergencyNumber.number must contain at least one digit")
        if not self.label:
            object.__setattr__(self, "label", self.number)


def normalize_number(number: str) -> str:
    """Reduce a dial string to bare digits, e.g. ``"9-1-1"`` -> ``"911"``."""
    return re.sub(r"\D", "", number)


def normalize_country(country: str) -> str:
    """Normalize a country code to uppercase ISO 3166-1 alpha-2."""
    code = _COUNTRY_ALIASES.get(country.strip().upper(), country.strip().upper())
    if not code:
        raise ValueError("country must not be empty")
    return code


def parse_emergency_numbers(value: str) -> list[str]:
    """Parse a comma/space/semicolon separated emergency-number list."""
    parts = [p.strip() for p in re.split(r"[,;\s]+", value) if p.strip()]
    if not parts:
        raise ValueError("emergency_numbers must contain at least one number")
    numbers = []
    for part in parts:
        digits = normalize_number(part)
        if not digits:
            raise ValueError(f"Invalid emergency number: {part!r}")
        numbers.append(digits)
    return numbers


# Registry of short-code emergency numbers per country. Numbers are listed in
# display order (primary service first). See REALISMGUIDE.md for the reference.
EMERGENCY_NUMBER_REGISTRY: dict[str, list[EmergencyNumber]] = {
    "US": [EmergencyNumber("911", "9-1-1", "Primary emergency number")],
    "CA": [EmergencyNumber("911", "9-1-1", "Primary emergency number")],
    "GB": [
        EmergencyNumber("999", "9-9-9", "Primary emergency number"),
        EmergencyNumber("112", "1-1-2", "Pan-European emergency number"),
    ],
    "IE": [
        EmergencyNumber("999", "9-9-9", "Primary emergency number"),
        EmergencyNumber("112", "1-1-2", "Pan-European emergency number"),
    ],
    "FR": [
        EmergencyNumber("112", "1-1-2", "Pan-European emergency number"),
        EmergencyNumber("15", "15 (SAMU)", "Medical emergency dispatch"),
        EmergencyNumber("17", "17 (Police)", "Police"),
        EmergencyNumber("18", "18 (Fire)", "Fire and rescue"),
        EmergencyNumber("114", "114 (SMS)", "SMS emergency for the hearing/speech impaired"),
        EmergencyNumber("191", "191 (Aviation)", "Aviation rescue"),
        EmergencyNumber("196", "196 (Maritime)", "Maritime rescue"),
    ],
    "DE": [
        EmergencyNumber("112", "1-1-2", "Fire and medical emergency"),
        EmergencyNumber("110", "1-1-0 (Police)", "Police"),
    ],
    "AU": [EmergencyNumber("000", "0-0-0", "Primary emergency number")],
    "NZ": [EmergencyNumber("111", "1-1-1", "Primary emergency number")],
    "NL": [EmergencyNumber("112", "1-1-2", "Primary emergency number")],
    "IT": [
        EmergencyNumber("112", "1-1-2", "Pan-European emergency number"),
        EmergencyNumber("113", "1-1-3 (Police)", "Police"),
        EmergencyNumber("115", "1-1-5 (Fire)", "Fire"),
        EmergencyNumber("118", "1-1-8 (Medical)", "Medical emergency"),
    ],
    "JP": [
        EmergencyNumber("110", "1-1-0 (Police)", "Police"),
        EmergencyNumber("119", "1-1-9 (Fire/ambulance)", "Fire and ambulance"),
        EmergencyNumber("118", "1-1-8 (Maritime)", "Coast guard"),
    ],
    "KR": [
        EmergencyNumber("112", "1-1-2 (Police)", "Police"),
        EmergencyNumber("119", "1-1-9 (Fire/ambulance)", "Fire and ambulance"),
    ],
    "ES": [
        EmergencyNumber("112", "1-1-2", "Primary emergency number"),
        EmergencyNumber("091", "0-9-1 (Police)", "National police"),
        EmergencyNumber("092", "0-9-2 (Local police)", "Local police"),
        EmergencyNumber("061", "0-6-1 (Medical)", "Emergency medical services"),
        EmergencyNumber("085", "0-8-5 (Fire)", "Fire"),
    ],
    "CH": [
        EmergencyNumber("112", "1-1-2", "Pan-European emergency number"),
        EmergencyNumber("117", "1-1-7 (Police)", "Police"),
        EmergencyNumber("118", "1-1-8 (Fire)", "Fire"),
        EmergencyNumber("144", "1-4-4 (Medical)", "Medical emergency"),
    ],
    "SE": [EmergencyNumber("112", "1-1-2", "Primary emergency number")],
    "NO": [
        EmergencyNumber("112", "1-1-2 (Police)", "Police"),
        EmergencyNumber("110", "1-1-0 (Fire)", "Fire"),
        EmergencyNumber("113", "1-1-3 (Medical)", "Medical emergency"),
    ],
    "DK": [EmergencyNumber("112", "1-1-2", "Primary emergency number")],
    "FI": [EmergencyNumber("112", "1-1-2", "Primary emergency number")],
    "BE": [
        EmergencyNumber("112", "1-1-2", "Primary emergency number"),
        EmergencyNumber("100", "1-0-0 (Medical/fire)", "Medical and fire"),
        EmergencyNumber("101", "1-0-1 (Police)", "Police"),
    ],
    "IN": [
        EmergencyNumber("112", "1-1-2", "National emergency number"),
        EmergencyNumber("100", "1-0-0 (Police)", "Police"),
        EmergencyNumber("101", "1-0-1 (Fire)", "Fire"),
        EmergencyNumber("102", "1-0-2 (Ambulance)", "Ambulance"),
    ],
    "BR": [
        EmergencyNumber("190", "1-9-0 (Police)", "Police"),
        EmergencyNumber("192", "1-9-2 (Medical)", "Emergency medical services"),
        EmergencyNumber("193", "1-9-3 (Fire)", "Fire"),
    ],
    "ZA": [
        EmergencyNumber("10111", "1-0-1-1-1 (Police)", "Police"),
        EmergencyNumber("10177", "1-0-1-7-7 (Ambulance)", "Ambulance"),
        EmergencyNumber("112", "1-1-2", "Mobile emergency number"),
    ],
    "RU": [
        EmergencyNumber("112", "1-1-2", "National emergency number"),
        EmergencyNumber("101", "1-0-1 (Fire)", "Fire"),
        EmergencyNumber("102", "1-0-2 (Police)", "Police"),
        EmergencyNumber("103", "1-0-3 (Medical)", "Ambulance"),
        EmergencyNumber("104", "1-0-4 (Gas)", "Gas emergency"),
    ],
    "CN": [
        EmergencyNumber("110", "1-1-0 (Police)", "Police"),
        EmergencyNumber("119", "1-1-9 (Fire)", "Fire"),
        EmergencyNumber("120", "1-2-0 (Medical)", "Ambulance"),
        EmergencyNumber("122", "1-2-2 (Traffic)", "Traffic police"),
    ],
    "HK": [
        EmergencyNumber("999", "9-9-9", "Primary emergency number"),
        EmergencyNumber("112", "1-1-2", "Mobile emergency number"),
    ],
}

# Optional 10-digit direct-dial emergency lines, enabled with the
# ``--include-10-digit-emergency`` flag. The default entries use the 555-01XX
# block reserved for fictional use in US media — replace them with real direct-
# dial agency numbers (or use ``--emergency-numbers``) in production datasets.
TEN_DIGIT_LINES: dict[str, list[EmergencyNumber]] = {
    "US": [
        EmergencyNumber(
            "8165550100",
            "10-digit direct-dial (example)",
            "Illustrative agency direct-dial line; replace with a real number",
        ),
        EmergencyNumber(
            "8165550122",
            "10-digit direct-dial (example)",
            "Illustrative agency direct-dial line; replace with a real number",
        ),
    ],
    "CA": [
        EmergencyNumber(
            "4165550100",
            "10-digit direct-dial (example)",
            "Illustrative agency direct-dial line; replace with a real number",
        ),
    ],
}

SUPPORTED_COUNTRIES: list[str] = sorted(EMERGENCY_NUMBER_REGISTRY)


def resolve_emergency_numbers(
    country: str = DEFAULT_COUNTRY,
    override: str | None = None,
    include_10_digit: bool = False,
) -> list[EmergencyNumber]:
    """Resolve the emergency numbers to model for a run.

    Without ``override`` the country's registry short codes are used. An
    ``override`` (comma/space separated) replaces those short codes entirely.
    ``include_10_digit`` appends the country's registered 10-digit direct-dial
    lines (when no override is given, or on top of an override).
    """
    country = normalize_country(country)
    if country not in EMERGENCY_NUMBER_REGISTRY:
        raise ValueError(
            f"Unknown country code {country!r}. Supported countries: "
            f"{', '.join(SUPPORTED_COUNTRIES)}"
        )

    if override:
        numbers = [EmergencyNumber(number=n) for n in parse_emergency_numbers(override)]
    else:
        numbers = list(EMERGENCY_NUMBER_REGISTRY[country])

    if include_10_digit:
        existing = {n.number for n in numbers}
        for line in TEN_DIGIT_LINES.get(country, []):
            if line.number not in existing:
                numbers.append(line)

    seen: set[str] = set()
    deduped: list[EmergencyNumber] = []
    for number in numbers:
        if number.number not in seen:
            seen.add(number.number)
            deduped.append(number)
    return deduped


def column_prefix(number: str) -> str:
    """Return the phone-metrics column-name prefix for an emergency number.

    ``911`` keeps the legacy ``nine_one_one`` naming so existing schemas stay
    byte-identical; every other number uses a ``emergency_<digits>`` suffix.
    """
    digits = normalize_number(number)
    if digits == "911":
        return "nine_one_one"
    return f"emergency_{digits}"
