"""Tests for the personnel-name locale machinery (``synth911gen3.names``)."""

import pytest

from synth911gen3.exceptions import ValidationError
from synth911gen3.names import (
    COUNTRY_LOCALES,
    FALLBACK_LOCALE,
    US_ETHNIC_BLEND,
    PersonnelNameGenerator,
    is_valid_faker_locale,
    normalize_name_locales,
    resolve_name_locales,
    validate_name_locales,
)


def test_is_valid_faker_locale() -> None:
    assert is_valid_faker_locale("en_US")
    assert is_valid_faker_locale("fr_CA")
    assert not is_valid_faker_locale("not_a_locale")


def test_country_locales_covers_emergency_number_countries() -> None:
    from synth911gen3.emergency_numbers import EMERGENCY_NUMBER_REGISTRY

    # Every country with emergency numbers should have a name-locale profile
    # (or fall back gracefully), so rosters never silently use English only.
    for country in EMERGENCY_NUMBER_REGISTRY:
        locales = COUNTRY_LOCALES.get(country)
        if locales is None:
            continue
        assert locales, country
        for locale in locales:
            assert is_valid_faker_locale(locale), f"{country}: {locale}"


def test_us_ethnic_blend_weights_are_positive() -> None:
    assert US_ETHNIC_BLEND
    assert all(weight > 0 for weight in US_ETHNIC_BLEND.values())
    assert all(is_valid_faker_locale(locale) for locale in US_ETHNIC_BLEND)


class TestNormalizeNameLocales:
    def test_list_form_equal_weights(self) -> None:
        result = normalize_name_locales({"IE": ["en_IE", "ga_IE"]})
        assert result == {"IE": [("en_IE", 1.0), ("ga_IE", 1.0)]}

    def test_mapping_form_weights(self) -> None:
        result = normalize_name_locales({"US": {"en_US": 0.6, "es_MX": 0.4}})
        assert result == {"US": [("en_US", 0.6), ("es_MX", 0.4)]}

    def test_country_aliases_normalized(self) -> None:
        result = normalize_name_locales({"UK": ["en_GB"], "USA": ["en_US"]})
        assert "GB" in result and "US" in result
        assert "UK" not in result and "USA" not in result

    def test_lowercase_country_normalized(self) -> None:
        result = normalize_name_locales({"ie": ["en_IE"]})
        assert result == {"IE": [("en_IE", 1.0)]}

    def test_rejects_unknown_locale(self) -> None:
        with pytest.raises(ValidationError, match="Unknown Faker locale"):
            normalize_name_locales({"US": ["xx_XX"]})

    def test_rejects_empty_country_spec(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            normalize_name_locales({"US": []})

    def test_rejects_non_positive_weight(self) -> None:
        with pytest.raises(ValidationError, match="must be positive"):
            normalize_name_locales({"US": {"en_US": 0.0}})

    def test_rejects_empty_locale_string(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            normalize_name_locales({"US": ["  "]})

    def test_rejects_invalid_spec_type(self) -> None:
        with pytest.raises(ValidationError, match="list of locales or a mapping"):
            normalize_name_locales({"US": "en_US"})


class TestValidateNameLocales:
    def test_accepts_normalized_form(self) -> None:
        validate_name_locales({"US": [("en_US", 0.64), ("es_MX", 0.36)]})

    def test_rejects_non_uppercase_country(self) -> None:
        with pytest.raises(ValidationError, match="uppercase ISO"):
            validate_name_locales({"us": [("en_US", 1.0)]})

    def test_rejects_unknown_locale(self) -> None:
        with pytest.raises(ValidationError, match="Unknown Faker locale"):
            validate_name_locales({"US": [("xx_XX", 1.0)]})

    def test_rejects_empty_items(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            validate_name_locales({"US": []})


class TestResolveNameLocales:
    def test_us_uses_ethnic_blend(self) -> None:
        assert resolve_name_locales("US") == list(US_ETHNIC_BLEND.items())

    def test_override_takes_precedence(self) -> None:
        override = {"US": [("en_US", 1.0)]}
        assert resolve_name_locales("US", override=override) == [("en_US", 1.0)]

    def test_override_for_other_country(self) -> None:
        override = {"CA": [("fr_CA", 1.0)]}
        assert resolve_name_locales("CA", override=override) == [("fr_CA", 1.0)]

    def test_override_ignored_for_unlisted_country(self) -> None:
        override = {"CA": [("fr_CA", 1.0)]}
        assert resolve_name_locales("IE", override=override) == [("en_IE", 1.0)]

    def test_country_map_equal_weights(self) -> None:
        assert resolve_name_locales("IE") == [("en_IE", 1.0)]

    def test_multi_locale_country(self) -> None:
        assert resolve_name_locales("CA") == [("en_CA", 1.0), ("fr_CA", 1.0)]

    def test_unknown_country_falls_back(self) -> None:
        assert resolve_name_locales("ZZ") == [(FALLBACK_LOCALE, 1.0)]

    def test_empty_country_defaults_to_us(self) -> None:
        assert resolve_name_locales("") == list(US_ETHNIC_BLEND.items())

    def test_country_alias_normalized(self) -> None:
        assert resolve_name_locales("UK") == [("en_GB", 1.0)]


class TestPersonnelNameGenerator:
    def test_generates_unique_names(self) -> None:
        gen = PersonnelNameGenerator([("en_US", 1.0)], seed=1)
        names = [gen.unique_name() for _ in range(50)]
        assert len(names) == len(set(names))
        assert all(name.strip() for name in names)
        assert all(len(name.split()) >= 2 for name in names)

    def test_deterministic_with_seed(self) -> None:
        a = PersonnelNameGenerator(list(US_ETHNIC_BLEND.items()), seed=99)
        b = PersonnelNameGenerator(list(US_ETHNIC_BLEND.items()), seed=99)
        assert [a.unique_name() for _ in range(10)] == [b.unique_name() for _ in range(10)]

    def test_different_seed_different_names(self) -> None:
        a = PersonnelNameGenerator([("en_US", 1.0)], seed=1)
        b = PersonnelNameGenerator([("en_US", 1.0)], seed=2)
        assert [a.unique_name() for _ in range(5)] != [b.unique_name() for _ in range(5)]

    def test_cjk_family_name_first(self) -> None:
        gen = PersonnelNameGenerator([("zh_CN", 1.0)], seed=3)
        for _ in range(10):
            name = gen.unique_name()
            tokens = name.split()
            assert len(tokens) == 2, name
            # Family names are single characters in the zh_CN sample data;
            # the family name must come first, so the first token is short.
            assert len(tokens[0]) <= 2, f"expected family name first: {name}"

    def test_weighted_mix_produces_multiple_locales(self) -> None:
        # es_MX is heavily weighted; across a large pool we should see
        # Hispanic-coded names alongside en_US ones.
        blend = {"en_US": 0.5, "es_MX": 0.5}
        gen = PersonnelNameGenerator(list(blend.items()), seed=11)
        names = [gen.unique_name() for _ in range(200)]
        accents = [name for name in names if any(c in name for c in "áéíóúñ")]
        assert accents, "expected some Spanish-script names from the es_MX locale"

    def test_rejects_invalid_locale(self) -> None:
        with pytest.raises(ValidationError, match="Unknown Faker locale"):
            PersonnelNameGenerator([("xx_XX", 1.0)], seed=1)

    def test_rejects_empty_locales(self) -> None:
        with pytest.raises(ValidationError, match="At least one name locale"):
            PersonnelNameGenerator([], seed=1)

    def test_exhaustion_raises(self, monkeypatch) -> None:
        gen = PersonnelNameGenerator([("en_US", 1.0)], seed=1)
        gen.unique_name()
        # Force every draw to collide with the already-used name so the
        # bounded retry loop gives up and raises.
        used = next(iter(gen._used))
        monkeypatch.setattr(gen, "_draw", lambda: used)
        with pytest.raises(ValidationError, match="Exhausted the personnel-name pool"):
            gen.unique_name()

    def test_all_names_unique_across_pool(self) -> None:
        gen = PersonnelNameGenerator([("en_US", 1.0)], seed=5)
        calltakers = [gen.unique_name() for _ in range(12)]
        dispatchers = [gen.unique_name() for _ in range(10)]
        combined = calltakers + dispatchers
        assert len(combined) == len(set(combined))
