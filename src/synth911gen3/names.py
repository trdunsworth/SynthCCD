"""Personnel name generation with per-country locale profiles.

Realistic calltaker/dispatcher rosters should match the region the data
simulates. This module maps ISO countries to Faker locales
(:data:`COUNTRY_LOCALES`), provides a weighted multi-ethnic blend for US
deployments (:data:`US_ETHNIC_BLEND`), and exposes
:class:`PersonnelNameGenerator`, which produces unique full names from a
chosen locale profile. The realism config's ``name_locales`` section can
override the country mapping via :func:`normalize_name_locales`.
"""

from __future__ import annotations

import random as _random
import unicodedata
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

# Cyrillic → Latin transliteration table (subset covering common name characters).
_CYRILLIC_TO_LATIN: dict[str, str] = {
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "Yo",
    "Ж": "Zh", "З": "Z", "И": "I", "Й": "Y", "К": "K", "Л": "L", "М": "M",
    "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
    "Ф": "F", "Х": "Kh", "Ц": "Ts", "Ч": "Ch", "Ш": "Sh", "Щ": "Shch",
    "Ъ": "", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "Yu", "Я": "Ya",
}

# Arabic → Latin approximate romanization (common name prefixes/roots).
_ARABIC_TO_LATIN: dict[str, str] = {
    "ا": "a", "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h", "خ": "kh",
    "د": "d", "ذ": "dh", "ر": "r", "ز": "z", "س": "s", "ش": "sh", "ص": "s",
    "ض": "d", "ط": "t", "ظ": "z", "ع": "a", "غ": "gh", "ف": "f", "ق": "q",
    "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "w", "ي": "y",
    "ة": "a", "ى": "a", "أ": "a", "إ": "i", "آ": "a", "ؤ": "u", "ئ": "i",
    "ـ": "",
}


def _to_ascii(text: str) -> str:
    """Transliterate *text* to clean ASCII.

    Decomposes accented Latin (é → e), transliterates Cyrillic and Arabic
    via explicit tables, and strips any remaining non-ASCII characters.
    """
    # 1. NFKD decomposition handles most accented Latin (é → e + combining accent)
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_parts: list[str] = []
    for char in decomposed:
        code = ord(char)
        # Stripping combining marks left over from decomposition
        if 0x0300 <= code <= 0x036F:
            continue
        if code < 128:
            ascii_parts.append(char)
            continue
        # Cyrillic block
        if 0x0400 <= code <= 0x04FF:
            upper = char.upper()
            ascii_parts.append(_CYRILLIC_TO_LATIN.get(upper, _CYRILLIC_TO_LATIN.get(char, "")))
            # Preserve case for lowercase
            if char.islower() and upper in _CYRILLIC_TO_LATIN:
                ascii_parts[-1] = ascii_parts[-1].lower()
            continue
        # Arabic block
        if 0x0600 <= code <= 0x06FF:
            ascii_parts.append(_ARABIC_TO_LATIN.get(char, ""))
            continue
        # CJK ideographs — use a placeholder (names are rarely generated in-script
        # for US deployments, but if they are, map to a reasonable Latin stand-in)
        if 0x4E00 <= code <= 0x9FFF:
            # CJK Unified Ideographs — no standard romanization table;
            # strip to avoid garbled output.
            continue
        # Devanagari, Thai, and other Indic scripts — strip
        continue
    result = "".join(ascii_parts).strip()
    # Collapse multiple spaces
    while "  " in result:
        result = result.replace("  ", " ")
    return result


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
# section. All locales produce Latin-script names; non-Latin scripts (CJK,
# Devanagari, Cyrillic, Arabic) are replaced by Latin-script equivalents that
# preserve ethnic diversity.
US_ETHNIC_BLEND: dict[str, float] = {
    "en_US": 0.64,
    "es_MX": 0.16,
    "en_NG": 0.07,
    "en_IN": 0.03,  # Indian sub-continent names in Latin script
    "fil_PH": 0.03,
    "fr_CA": 0.02,
    "en_KE": 0.02,  # East African names in Latin script
    "de_DE": 0.02,
    "it_IT": 0.02,
    "pt_BR": 0.02,
    "nl_NL": 0.01,
    "pl_PL": 0.01,
    "tr_TR": 0.01,  # Turkish names in Latin script
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

    Faker instances are lazily initialized on first draw to avoid unnecessary
    object creation when the generator is created but not immediately used.
    """

    _MAX_UNIQUE_ATTEMPTS = 5_000

    def __init__(self, locales: list[tuple[str, float]], seed: int) -> None:
        """Initialize the name generator with locale weights and master seed.

        Args:
            locales: ``(locale, weight)`` pairs; weights are normalized at
                draw time.
            seed: Master seed; each locale's Faker gets a derived seed so
                rosters are reproducible across runs.

        Raises:
            ValidationError: If ``locales`` is empty or names an unknown
                Faker locale.
        """
        if not locales:
            raise ValidationError("At least one name locale is required.")
        self._locales = locales
        self._rng = _random.Random(seed)
        self._weights: list[float] = []
        self._cjk_flags: list[bool] = []
        self._fakers: list[Faker] | None = None
        self._used: set[str] = set()
        # Validate locales and collect weights
        for locale, weight in locales:
            if not is_valid_faker_locale(locale):
                raise ValidationError(f"Unknown Faker locale for name generation: {locale!r}")
            self._weights.append(float(weight))
        # Determine CJK flags
        cjk_set: set[str] = set()
        for locale, _weight in locales:
            prefix = locale.split("_", 1)[0]
            if prefix in _CJK_LANGUAGES:
                cjk_set.add(locale)
        for locale, _weight in locales:
            self._cjk_flags.append(locale in cjk_set)
        # Fallback Faker for locales that strip to empty after ASCII normalization
        # (e.g. CJK or Devanagari supplied via realism config overrides).
        self._fallback: Faker | None = None
        self._fallback_seed: int = seed + 9999

    @property
    def _fakers_list(self) -> list[Faker]:
        """Lazily create and return the Faker instances for each locale."""
        if self._fakers is not None:
            return self._fakers
        fakers: list[Faker] = []
        for index, (locale, _weight) in enumerate(self._locales):
            faker = Faker(locale)
            faker.seed_instance(self._rng.randint(0, 2**31 - 1))
            fakers.append(faker)
        # Set a deterministic seed for the fallback Faker
        fallback_rng = _random.Random(self._fallback_seed)
        self._fallback = Faker(DEFAULT_LOCALE)
        self._fallback.seed_instance(fallback_rng.randint(0, 2**31 - 1))
        self._fakers = fakers
        return self._fakers

    def _draw(self) -> str:
        """Draw one raw name from a locale picked by the shared weighted RNG.

        Names are normalized to ASCII so the output stays clean regardless
        of the source locale. If normalization strips the name to empty
        (CJK, Devanagari, etc.), a fallback name is drawn from the default
        locale.
        """
        # Ensure Fakers are initialized on first draw
        fakers = self._fakers_list
        index = self._rng.choices(range(len(fakers)), weights=self._weights, k=1)[0]
        faker = fakers[index]
        first = str(faker.first_name())
        last = str(faker.last_name())
        if not first and not last:
            name = str(faker.name()).strip()
        elif self._cjk_flags[index]:
            name = f"{last} {first}".strip()
        else:
            name = f"{first} {last}".strip()
        result = _to_ascii(name)
        if not result.strip():
            fb = self._fallback
            result = f"{fb.first_name()} {fb.last_name()}"
        return result

    def unique_name(self) -> str:
        """Return a fresh name not previously returned by this generator.

        Retries up to ``_MAX_UNIQUE_ATTEMPTS`` draws per call; raises when
        the underlying locale pool is exhausted.
        """
        for _ in range(self._MAX_UNIQUE_ATTEMPTS):
            name = self._draw()
            if name not in self._used:
                self._used.add(name)
                return name
        raise ValidationError(
            "Exhausted the personnel-name pool; increase locale diversity or reduce pool sizes."
        )
