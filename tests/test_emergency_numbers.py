import pytest

from synth911gen3.constants import DEFAULT_COUNTRY
from synth911gen3.emergency_numbers import (
    EMERGENCY_NUMBER_REGISTRY,
    SUPPORTED_COUNTRIES,
    TEN_DIGIT_LINES,
    EmergencyNumber,
    column_prefix,
    normalize_country,
    normalize_number,
    parse_emergency_numbers,
    resolve_emergency_numbers,
)


def test_default_country_is_us() -> None:
    assert DEFAULT_COUNTRY == "US"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("911", "911"),
        ("9-1-1", "911"),
        ("9 1 1", "911"),
        ("+44 999", "44999"),
        ("112", "112"),
        ("(816) 555-0100", "8165550100"),
    ],
)
def test_normalize_number(raw: str, expected: str) -> None:
    assert normalize_number(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("us", "US"),
        ("US", "US"),
        ("uk", "GB"),
        ("GBR", "GB"),
        ("UK", "GB"),
        ("irl", "IE"),
        ("fra", "FR"),
        ("deu", "DE"),
    ],
)
def test_normalize_country(raw: str, expected: str) -> None:
    assert normalize_country(raw) == expected


@pytest.mark.parametrize("raw", ["", "   "])
def test_normalize_country_rejects_empty(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_country(raw)


def test_emergency_number_defaults() -> None:
    num = EmergencyNumber(number="911")
    assert num.label == "911"
    assert num.kind == "emergency"
    assert num.description == ""


def test_emergency_number_normalizes_and_labels() -> None:
    num = EmergencyNumber(number="9-1-1", label="9-1-1")
    assert num.number == "911"
    assert num.label == "9-1-1"


@pytest.mark.parametrize("raw", ["", "abc", "!!!", "   "])
def test_emergency_number_rejects_non_digits(raw: str) -> None:
    with pytest.raises(ValueError):
        EmergencyNumber(number=raw)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("911", ["911"]),
        ("999,112", ["999", "112"]),
        ("999 112", ["999", "112"]),
        ("999;112", ["999", "112"]),
        ("9-9-9", ["999"]),
        (" 911 , 112 ", ["911", "112"]),
    ],
)
def test_parse_emergency_numbers(value: str, expected: list[str]) -> None:
    assert parse_emergency_numbers(value) == expected


@pytest.mark.parametrize("value", ["", "   ", "abc"])
def test_parse_emergency_numbers_rejects_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        parse_emergency_numbers(value)


def test_supported_countries_sorted_and_nonempty() -> None:
    assert SUPPORTED_COUNTRIES == sorted(EMERGENCY_NUMBER_REGISTRY)
    assert SUPPORTED_COUNTRIES == sorted(SUPPORTED_COUNTRIES)
    assert len(SUPPORTED_COUNTRIES) >= 3


def test_registry_contains_core_countries() -> None:
    for country in ("US", "CA", "GB", "IE", "FR", "DE", "AU", "NZ"):
        assert country in EMERGENCY_NUMBER_REGISTRY


def test_registry_us_canada_default_to_911() -> None:
    for country in ("US", "CA"):
        numbers = [n.number for n in EMERGENCY_NUMBER_REGISTRY[country]]
        assert numbers == ["911"]


def test_registry_entries_unique_per_country() -> None:
    for country, numbers in EMERGENCY_NUMBER_REGISTRY.items():
        digits = [n.number for n in numbers]
        assert len(digits) == len(set(digits)), f"duplicate numbers in registry for {country}"
        assert all(d for d in digits), f"empty number in registry for {country}"


def test_resolve_emergency_numbers_defaults_to_us() -> None:
    numbers = resolve_emergency_numbers()
    assert [n.number for n in numbers] == ["911"]


@pytest.mark.parametrize(
    ("country", "expected"),
    [
        ("US", ["911"]),
        ("CA", ["911"]),
        ("GB", ["999", "112"]),
        ("IE", ["999", "112"]),
        ("DE", ["112", "110"]),
        ("AU", ["000"]),
        ("NZ", ["111"]),
    ],
)
def test_resolve_emergency_numbers_by_country(country: str, expected: list[str]) -> None:
    numbers = resolve_emergency_numbers(country=country)
    assert [n.number for n in numbers] == expected


@pytest.mark.parametrize("country", ["uk", "GBR", "  UK "])
def test_resolve_emergency_numbers_normalizes_country(country: str) -> None:
    assert [n.number for n in resolve_emergency_numbers(country=country)] == ["999", "112"]


def test_resolve_emergency_numbers_unknown_country() -> None:
    with pytest.raises(ValueError, match="Unknown country"):
        resolve_emergency_numbers(country="ZZ")


def test_resolve_emergency_numbers_override_replaces_short_codes() -> None:
    numbers = resolve_emergency_numbers(country="US", override="999,112")
    assert [n.number for n in numbers] == ["999", "112"]


def test_resolve_emergency_numbers_override_dedupes() -> None:
    numbers = resolve_emergency_numbers(country="GB", override="999,999,112")
    assert [n.number for n in numbers] == ["999", "112"]


def test_resolve_emergency_numbers_include_10_digit_appends() -> None:
    numbers = resolve_emergency_numbers(country="US", include_10_digit=True)
    digits = [n.number for n in numbers]
    assert digits[0] == "911"
    assert all(d not in digits[:1] for d in digits[1:])
    expected_extra = [n.number for n in TEN_DIGIT_LINES["US"]]
    assert digits[1:] == expected_extra


def test_resolve_emergency_numbers_10_digit_on_top_of_override() -> None:
    numbers = resolve_emergency_numbers(country="US", override="911", include_10_digit=True)
    digits = [n.number for n in numbers]
    assert digits == ["911", *(n.number for n in TEN_DIGIT_LINES["US"])]


def test_resolve_emergency_numbers_10_digit_canada() -> None:
    numbers = resolve_emergency_numbers(country="CA", include_10_digit=True)
    digits = [n.number for n in numbers]
    assert digits == ["911", *(n.number for n in TEN_DIGIT_LINES["CA"])]


def test_resolve_emergency_numbers_no_10_digit_for_unsupported_country() -> None:
    numbers = resolve_emergency_numbers(country="GB", include_10_digit=True)
    assert [n.number for n in numbers] == ["999", "112"]


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        ("911", "nine_one_one"),
        ("999", "emergency_999"),
        ("112", "emergency_112"),
        ("8165550100", "emergency_8165550100"),
        ("9-1-1", "nine_one_one"),
    ],
)
def test_column_prefix(number: str, expected: str) -> None:
    assert column_prefix(number) == expected
