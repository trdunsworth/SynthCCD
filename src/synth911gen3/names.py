from __future__ import annotations

import random as _random
from typing import Any

from faker import Faker
from faker.config import AVAILABLE_LOCALES

from .constants import DEFAULT_COUNTRY, DEFAULT_LOCALE
from .emergency_numbers import normalize_country
from .exceptions import ValidationError

# Default fallback locale used when a country has no entry (and the realism
# config does not override it). Kept in sync with constants.DEFAULT_LOCALE.
FALLBACK_LOCALE = DEFAULT_LOCALE

# Languages whose native written order is family-name-first. Faker provides the
# given and family names as separate fields, so we flip the order to match how
# the name is written in the native script. Vietnamese is intentionally absent:
# faker's vi_VN first_name provider is unreliable.
_CJK_LANGUAGES = frozenset({"zh", "ja", "ko"})


def is_valid_faker_locale(locale: str) -> bool:
    """Return True when ``locale`` is a locale Faker can instantiate."""
    return locale in AVAILABLE_LOCALES


# Primary Faker locale(s) per country (ISO 3166-1 alpha-2, uppercase).
# Multi-locale countries list each language's locale; entries share equal weight
# unless the realism config overrides them with explicit weights.
COUNTRY_LOCALES: dict[str, list[str]] = {
    "US": ["en_US"],
    "CA": ["en_CA", "fr_CA"],
    "GB": ["en_GB"],
    "IE": ["en_IE"],
    "AU": ["en_AU"],
    "NZ": ["en_NZ"],
    "FR": ["fr_FR"],
    "DE": ["de_DE"],
    "IT": ["it_IT"],
    "ES": ["es_ES"],
    "NL": ["nl_NL"],
    "BE": ["fr_BE", "nl_BE"],
    "CH": ["de_CH", "fr_CH", "it_CH"],
    "SE": ["sv_SE"],
    "NO": ["no_NO"],
    "DK": ["da_DK"],
    "FI": ["fi_FI"],
    "PL": ["pl_PL"],
    "PT": ["pt_PT"],
    "BR": ["pt_BR"],
    "RU": ["ru_RU"],
    "UA": ["uk_UA"],
    "TR": ["tr_TR"],
    "GR": ["el_GR"],
    "JP": ["ja_JP"],
    "KR": ["ko_KR"],
    "CN": ["zh_CN"],
    "HK": ["zh_TW", "en_GB"],
    "IN": ["en_IN", "hi_IN"],
    "PK": ["en_PK"],
    "BD": ["en_BD"],
    "TH": ["th_TH"],
    "ID": ["id_ID"],
    "PH": ["fil_PH", "en_PH"],
    "IL": ["he_IL"],
    "ZA": ["en_GB", "en_NG"],
    "AR": ["es_AR"],
    "CO": ["es_CO"],
    "CL": ["es_CL"],
    "MX": ["es_MX"],
    "NG": ["en_NG"],
    "KE": ["en_KE"],
    "SA": ["ar_SA"],
    # ar_AE and ar_EG are unreliable in Faker (they fall back to English names);
    # ar_SA provides a working Arabic-script provider used as their stand-in.
    "AE": ["ar_SA"],
    "EG": ["ar_SA"],
}

# Weighted Faker-locale blend used for US deployments. It approximates the ethnic
# mix of a typical large American call center so rosters do not read as
# uniformly Anglo-American. Weights need not sum to 1; they are normalized at
# generation time. Override per-country via the realism config `name_locales`
# section. Locale choices favor providers with reliable name data; several
# groups use native scripts (Chinese/Japanese/Korean/Devanagari/Arabic).
US_ETHNIC_BLEND: dict[str, float] = {
    "en_US": 0.64,
    "es_MX": 0.16,
    "en_NG": 0.07,
    "zh_CN": 0.03,
    "fil_PH": 0.03,
    "fr_CA": 0.02,
    "hi_IN": 0.02,
    "de_DE": 0.02,
    "it_IT": 0.02,
    "pt_BR": 0.02,
    "ja_JP": 0.01,
    "ko_KR": 0.01,
    "ru_RU": 0.01,
    "ar_SA": 0.01,
}


def _parse_locale_spec(spec: Any) -> list[tuple[str, float]]:
    """Normalize a single country's name_locales value to [(locale, weight)].

    Accepts either a bare list of locale names (equal weight) or a mapping of
    locale name to positive weight.
    """
    if isinstance(spec, dict):
        items = [(str(locale), float(weight)) for locale, weight in spec.items()]
    elif isinstance(spec, list):
        items = [(str(locale), 1.0) for locale in spec]
    else:
        raise ValidationError(
            "name_locales values must be a list of locales or a mapping of locale to weight."
        )
    if not items:
        raise ValidationError("name_locales entries must not be empty.")
    for locale, weight in items:
        if not locale.strip():
            raise ValidationError("name_locales locales must not be empty.")
        if weight <= 0:
            raise ValidationError(f"name_locales weight for {locale!r} must be positive.")
        if not is_valid_faker_locale(locale):
            raise ValidationError(f"Unknown Faker locale for name generation: {locale!r}")
    return items


def normalize_name_locales(value: dict[str, Any]) -> dict[str, list[tuple[str, float]]]:
    """Normalize a YAML ``name_locales`` mapping into {COUNTRY: [(locale, weight)]}.

    Country keys are normalized to uppercase ISO 3166-1 alpha-2 (aliases such as
    ``UK`` and ``USA`` are mapped to their canonical code).
    """
    result: dict[str, list[tuple[str, float]]] = {}
    for raw_country, spec in value.items():
        country = normalize_country(str(raw_country))
        result[country] = _parse_locale_spec(spec)
    return result


def validate_name_locales(value: dict[str, list[tuple[str, float]]]) -> None:
    """Validate an already-normalized ``name_locales`` mapping.

    Used by :class:`~synth911gen3.realism_config.RealismConfig._validate` for
    configs assembled programmatically (not via YAML, where
    :func:`normalize_name_locales` already enforces these rules).
    """
    for raw_country, items in value.items():
        raw = str(raw_country)
        country = normalize_country(raw)
        if raw != country:
            raise ValidationError(f"name_locales country keys must be uppercase ISO codes: {raw!r}")
        if not items:
            raise ValidationError(f"name_locales entries for {country} must not be empty.")
        for locale, weight in items:
            if not str(locale).strip():
                raise ValidationError(f"name_locales locales for {country} must not be empty.")
            if weight <= 0:
                raise ValidationError(
                    f"name_locales weight for {country}/{locale!r} must be positive."
                )
            if not is_valid_faker_locale(str(locale)):
                raise ValidationError(f"Unknown Faker locale for name generation: {locale!r}")


def resolve_name_locales(
    country: str,
    override: dict[str, list[tuple[str, float]]] | None = None,
    fallback_locale: str = FALLBACK_LOCALE,
) -> list[tuple[str, float]]:
    """Resolve the name locale profile for a country.

    Priority: a ``name_locales`` override from the realism config for this
    country, then the built-in country map, then the US ethnic blend (for the
    default country), then ``fallback_locale``.
    """
    country = normalize_country(country) if country else DEFAULT_COUNTRY
    if override and country in override:
        return list(override[country])
    if country == DEFAULT_COUNTRY:
        return [(locale, weight) for locale, weight in US_ETHNIC_BLEND.items()]
    locales = COUNTRY_LOCALES.get(country)
    if locales:
        return [(locale, 1.0) for locale in locales]
    return [(fallback_locale, 1.0)]


class PersonnelNameGenerator:
    """Weighted multi-locale generator for unique personnel full names.

    Each locale gets its own seeded Faker instance; a shared RNG selects which
    locale produces the next name according to the locale weights. Names are
    emitted as "Given Family" in Latin order, except for CJK locales where the
    family name is written first to match the native script convention. Names
    are never repeated within the lifetime of the generator (mirrors Faker's
    ``unique`` behavior across the whole shift pool).
    """

    _MAX_UNIQUE_ATTEMPTS = 5_000

    def __init__(self, locales: list[tuple[str, float]], seed: int) -> None:
        if not locales:
            raise ValidationError("At least one name locale is required.")
        self._rng = _random.Random(seed)
        self._fakers: list[Faker] = []
        self._cjk_flags: list[bool] = []
        for index, (locale, _weight) in enumerate(locales):
            if not is_valid_faker_locale(locale):
                raise ValidationError(f"Unknown Faker locale for name generation: {locale!r}")
            faker = Faker(locale)
            faker.seed_instance(seed + 1 + index)
            self._fakers.append(faker)
            self._cjk_flags.append(locale.split("_", 1)[0] in _CJK_LANGUAGES)
        self._weights = [float(weight) for _locale, weight in locales]
        self._used: set[str] = set()

    def _draw(self) -> str:
        index = self._rng.choices(range(len(self._fakers)), weights=self._weights, k=1)[0]
        faker = self._fakers[index]
        first = str(faker.first_name())
        last = str(faker.last_name())
        if not first and not last:
            return str(faker.name()).strip()
        if self._cjk_flags[index]:
            return f"{last} {first}".strip()
        return f"{first} {last}".strip()

    def unique_name(self) -> str:
        for _ in range(self._MAX_UNIQUE_ATTEMPTS):
            name = self._draw()
            if name not in self._used:
                self._used.add(name)
                return name
        raise ValidationError(
            "Exhausted the personnel-name pool; increase locale diversity or reduce pool sizes."
        )
