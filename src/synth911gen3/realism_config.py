"""YAML-driven realism configuration.

Every distribution the generator uses — agency and priority weights,
problem profiles, call-reception and disposition weights, time profiles,
phone-metrics parameters, hourly weights, shift structure, seasonal and
zone multipliers, and name locales — can be overridden per run via a
realism YAML file. :class:`RealismConfig` holds the merged result: user
values take precedence, untouched sections fall back to the defaults in
:mod:`~synth911gen3.constants`. See REALISMGUIDE.md for the full schema
and validation rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .logging_conf import get_logger

logger = get_logger("realism_config")

import numpy as np
import yaml

from .calibration import lognormal_cdf
from .constants import (
    AGENCY_WEIGHTS as DEFAULT_AGENCY_WEIGHTS,
)
from .constants import (
    CALL_RECEPTION_WEIGHTS as DEFAULT_CALL_RECEPTION_WEIGHTS,
)
from .constants import (
    DISPATCH_INIT_FRACTION as DEFAULT_DISPATCH_INIT_FRACTION,
)
from .constants import (
    DISPATCHER_DISCIPLINES as DEFAULT_DISPATCHER_DISCIPLINES,
)
from .constants import (
    DISPOSITION_PROFILES as DEFAULT_DISPOSITION_PROFILES,
)
from .constants import (
    HOURLY_WEIGHTS as DEFAULT_HOURLY_WEIGHTS,
)
from .constants import (
    PHONE_METRICS as DEFAULT_PHONE_METRICS,
)
from .constants import (
    PRIORITY_WEIGHTS as DEFAULT_PRIORITY_WEIGHTS,
)
from .constants import (
    PROBLEM_PHONE_MULTIPLIERS as DEFAULT_PROBLEM_PHONE_MULTIPLIERS,
)
from .constants import (
    PROBLEM_PROFILES as DEFAULT_PROBLEM_PROFILES,
)
from .constants import (
    SEASONAL_MULTIPLIERS as DEFAULT_SEASONAL_MULTIPLIERS,
)
from .constants import (
    TIME_PROFILES as DEFAULT_TIME_PROFILES,
)
from .constants import (
    ZONE_TRAVEL_MULTIPLIERS as DEFAULT_ZONE_TRAVEL_MULTIPLIERS,
)
from .exceptions import ValidationError
from .names import normalize_name_locales, validate_name_locales
from .shifts import ShiftConfig, get_default_shift_config


def _scalar_float(value: object) -> float:
    """Coerce a realism-config scalar to ``float``.

    Phone-metric values are typed ``float | list[float]`` (lists arrive from
    YAML sequences); a single-element list collapses to its first item.
    """
    if isinstance(value, list):
        value = value[0]
    if isinstance(value, (int, float)):
        return float(value)
    raise TypeError(f"Expected a numeric scalar, got {type(value).__name__}")


def _normalize_target_line(line: str) -> str:
    """Map a user-facing answer-time target line name to its config key prefix."""
    key = line.strip().lower()
    if key in ("911", "nine_one_one", "emergency"):
        return "nine_one_one"
    if key in ("ne", "non_emergency", "nonemergency", "non-emergency"):
        return "non_emergency"
    return key


@dataclass(slots=True)
class AnswerTimeCheck:
    """Result of comparing one published answer-time target against the config."""

    line: str
    threshold: float
    target_pct: float
    implied_pct: float
    gap: float
    ok: bool
    note: str = ""


@dataclass(slots=True)
class RealismConfig:
    agency_weights: dict[str, float] = field(default_factory=dict)
    priority_weights: dict[str, dict[int, float]] = field(default_factory=dict)
    problem_profiles: dict[str, dict[int, list[tuple[str, float]]]] = field(default_factory=dict)
    call_reception_weights: dict[str, float] = field(default_factory=dict)
    disposition_profiles: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    time_profiles: dict[str, dict[int, dict[str, int]]] = field(default_factory=dict)
    dispatch_init_fraction: dict[int, tuple[float, float]] = field(default_factory=dict)
    phone_metrics: dict[str, float | list[float]] = field(default_factory=dict)
    phone_metric_lines: dict[str, dict[str, float]] = field(default_factory=dict)
    hourly_weights: np.ndarray = field(default_factory=lambda: np.array([]))
    agency_names: dict[str, str] = field(default_factory=dict)
    shift_config: ShiftConfig = field(default_factory=ShiftConfig)
    seasonal_multipliers: dict[str, list[float]] = field(default_factory=dict)
    name_locales: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    zone_travel_multipliers: dict[str, float] = field(default_factory=dict)
    problem_phone_multipliers: dict[str, float] = field(default_factory=dict)
    dispatcher_disciplines: dict[str, Any] = field(default_factory=dict)
    answer_time_targets: dict[str, list[tuple[float, float]]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Fill any empty section with its constants-module default."""
        if not self.agency_weights:
            self.agency_weights = DEFAULT_AGENCY_WEIGHTS.copy()
        if not self.priority_weights:
            self.priority_weights = {k: v.copy() for k, v in DEFAULT_PRIORITY_WEIGHTS.items()}
        if not self.problem_profiles:
            self.problem_profiles = {
                k: {pk: pv.copy() for pk, pv in v.items()}
                for k, v in DEFAULT_PROBLEM_PROFILES.items()
            }
        if not self.call_reception_weights:
            self.call_reception_weights = DEFAULT_CALL_RECEPTION_WEIGHTS.copy()
        if not self.disposition_profiles:
            self.disposition_profiles = {
                k: v.copy() for k, v in DEFAULT_DISPOSITION_PROFILES.items()
            }
        if not self.time_profiles:
            self.time_profiles = {
                k: {pk: pv.copy() for pk, pv in v.items()} for k, v in DEFAULT_TIME_PROFILES.items()
            }
        if not self.dispatch_init_fraction:
            self.dispatch_init_fraction = DEFAULT_DISPATCH_INIT_FRACTION.copy()
        if not self.phone_metrics:
            self.phone_metrics = DEFAULT_PHONE_METRICS.copy()
        if self.hourly_weights.size == 0:
            self.hourly_weights = DEFAULT_HOURLY_WEIGHTS.copy()
        if not self.agency_names:
            self.agency_names = {"LAW": "LAW", "FIRE": "FIRE", "EMS": "EMS"}
        if not self.seasonal_multipliers:
            self.seasonal_multipliers = DEFAULT_SEASONAL_MULTIPLIERS.copy()
        if not self.zone_travel_multipliers:
            self.zone_travel_multipliers = DEFAULT_ZONE_TRAVEL_MULTIPLIERS.copy()
        if not self.problem_phone_multipliers:
            self.problem_phone_multipliers = DEFAULT_PROBLEM_PHONE_MULTIPLIERS.copy()
        if not self.dispatcher_disciplines:
            self.dispatcher_disciplines = {
                k: v for k, v in DEFAULT_DISPATCHER_DISCIPLINES.items()
            }
        if not self.shift_config.shifts and not self.shift_config.rotation:
            self.shift_config = get_default_shift_config()

    @staticmethod
    def _convert_deprecated_answer_time_keys(
        phone_metrics: dict[str, float | list[float]],
        phone_metric_lines: dict[str, dict[str, float]],
    ) -> None:
        """Translate legacy log-scale ``*_answer_time_mu`` keys to mean seconds.

        Older realism configs expressed answer-time location as a raw lognormal
        ``mu`` (log-space). The current convention uses ``*_answer_time_mean``
        (population *mean seconds*), matching the incident phone-duration keys.
        We convert the legacy value faithfully so existing configs keep their
        observed distribution: ``mean = exp(mu + sigma^2 / 2)``. The legacy key
        is dropped and a deprecation warning is logged. New keys take precedence
        (the conversion is skipped when the new key is already present).
        """
        top_level = {
            "nine_one_one_answer_time_mu": "nine_one_one_answer_time_sigma",
            "non_emergency_answer_time_mu": "non_emergency_answer_time_sigma",
        }
        for old_key, sigma_key in top_level.items():
            new_key = old_key.replace("_mu", "_mean")
            if old_key not in phone_metrics:
                continue
            if new_key not in phone_metrics:
                sigma = _scalar_float(phone_metrics.get(sigma_key, 0.8))
                mu = _scalar_float(phone_metrics[old_key])
                phone_metrics[new_key] = float(np.exp(mu + sigma**2 / 2))
                logger.warning(
                    "Deprecated phone_metrics key %r ignored; converted to %r = %.3f s "
                    "(mean seconds). Rename it in your config to silence this warning.",
                    old_key,
                    new_key,
                    phone_metrics[new_key],
                )
            del phone_metrics[old_key]

        for number, overrides in phone_metric_lines.items():
            if "answer_time_mu" not in overrides:
                continue
            if "answer_time_mean" not in overrides:
                sigma = _scalar_float(overrides.get("answer_time_sigma", phone_metrics.get("nine_one_one_answer_time_sigma", 0.8)))
                mu = _scalar_float(overrides["answer_time_mu"])
                overrides["answer_time_mean"] = float(np.exp(mu + sigma**2 / 2))
                logger.warning(
                    "Deprecated phone_metric_lines[%r].answer_time_mu ignored; converted to "
                    "answer_time_mean = %.3f s (mean seconds). Rename it in your config.",
                    number,
                    overrides["answer_time_mean"],
                )
            del overrides["answer_time_mu"]

    @classmethod
    def from_yaml(cls, path: Path) -> RealismConfig:
        """Load a realism YAML file, applying overrides over the defaults.

        Raises:
            ValidationError: If any section fails validation after merging
                (e.g. weights not summing to 1.0, missing time-profile
                keys, malformed shift config).
        """
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        config = cls()

        if "agency_weights" in data:
            config.agency_weights = cls._normalize_weights(data["agency_weights"])

        if "priority_weights" in data:
            config.priority_weights = {}
            for agency, weights in data["priority_weights"].items():
                config.priority_weights[agency] = {
                    int(k): float(v) for k, v in cls._normalize_weights(weights).items()
                }

        if "problem_profiles" in data:
            config.problem_profiles = {}
            for agency, priorities in data["problem_profiles"].items():
                config.problem_profiles[agency] = {}
                for priority, profiles in priorities.items():
                    config.problem_profiles[agency][int(priority)] = [
                        (str(p[0]), float(p[1])) for p in profiles
                    ]

        if "call_reception_weights" in data:
            config.call_reception_weights = cls._normalize_weights(data["call_reception_weights"])

        if "disposition_profiles" in data:
            config.disposition_profiles = {}
            for agency, profiles in data["disposition_profiles"].items():
                config.disposition_profiles[agency] = [(str(p[0]), float(p[1])) for p in profiles]

        if "time_profiles" in data:
            config.time_profiles = {}
            for agency, priorities in data["time_profiles"].items():
                config.time_profiles[agency] = {}
                for priority, intervals in priorities.items():
                    config.time_profiles[agency][int(priority)] = {
                        k: int(v) for k, v in intervals.items()
                    }

        if "dispatch_init_fraction" in data:
            config.dispatch_init_fraction = {}
            for priority, bounds in data["dispatch_init_fraction"].items():
                config.dispatch_init_fraction[int(priority)] = (
                    float(bounds[0]),
                    float(bounds[1]),
                )

        if "phone_metrics" in data:
            config.phone_metrics = {}
            for k, v in data["phone_metrics"].items():
                if k == "lines":
                    config.phone_metric_lines = {
                        str(num): {str(key): float(val) for key, val in lines.items()}
                        for num, lines in v.items()
                    }
                elif isinstance(v, list):
                    config.phone_metrics[str(k)] = [float(x) for x in v]
                else:
                    config.phone_metrics[str(k)] = float(v)

        cls._convert_deprecated_answer_time_keys(
            config.phone_metrics, config.phone_metric_lines
        )

        if "hourly_weights" in data:
            hw = np.array(data["hourly_weights"], dtype=float)
            if hw.shape != (24,):
                raise ValidationError("hourly_weights must have exactly 24 values")
            config.hourly_weights = hw / hw.sum()

        if "agency_names" in data:
            config.agency_names = data["agency_names"]

        if "shift_config" in data:
            config.shift_config = ShiftConfig.from_dict(data["shift_config"])

        if "seasonal_multipliers" in data:
            config.seasonal_multipliers = {}
            for problem, multipliers in data["seasonal_multipliers"].items():
                config.seasonal_multipliers[problem] = [float(m) for m in multipliers]

        if "zone_travel_multipliers" in data:
            config.zone_travel_multipliers = {
                str(k): float(v) for k, v in data["zone_travel_multipliers"].items()
            }

        if "name_locales" in data:
            config.name_locales = normalize_name_locales(data["name_locales"])

        if "problem_phone_multipliers" in data:
            config.problem_phone_multipliers = {
                str(k): float(v) for k, v in data["problem_phone_multipliers"].items()
            }

        if "dispatcher_disciplines" in data:
            section = data["dispatcher_disciplines"]
            if not isinstance(section, dict):
                raise ValidationError("dispatcher_disciplines must be a mapping")
            config.dispatcher_disciplines = {
                str(k): v for k, v in section.items()
            }

        if "answer_time_targets" in data:
            raw = data["answer_time_targets"]
            if not isinstance(raw, dict):
                raise ValidationError("answer_time_targets must be a mapping of line -> points")
            parsed: dict[str, list[tuple[float, float]]] = {}
            for line, points in raw.items():
                norm_line = _normalize_target_line(str(line))
                if not isinstance(points, list):
                    raise ValidationError(
                        f"answer_time_targets[{line}] must be a list of (threshold, percentile) points"
                    )
                pts: list[tuple[float, float]] = []
                for point in points:
                    if isinstance(point, dict):
                        t = float(point.get("threshold", point.get("t")))  # type: ignore[attr-defined]
                        p = float(point.get("percentile", point.get("p")))  # type: ignore[attr-defined]
                    elif isinstance(point, (list, tuple)) and len(point) == 2:
                        t, p = float(point[0]), float(point[1])
                    else:
                        raise ValidationError(
                            f"answer_time_targets[{line}] point must be [threshold, percentile] or "
                            f"{{threshold, percentile}}, got {point!r}"
                        )
                    pts.append((t, p))
                parsed[norm_line] = pts
            config.answer_time_targets = parsed

        config._validate()
        return config

    @staticmethod
    def _normalize_weights(weights: dict[Any, float]) -> dict[str, float]:
        """Coerce a raw weights mapping to normalized floats summing to 1.0."""
        normalized = {str(k): float(v) for k, v in weights.items()}
        total = sum(normalized.values())
        if total <= 0:
            raise ValidationError("Weights must sum to a positive value")
        return {k: v / total for k, v in normalized.items()}

    def _validate(self) -> None:
        """Cross-validate every section after defaults are merged.

        Checks weights sum to 1.0, all priorities/keys exist per agency,
        time-profile keys are present, phone-metrics values are in range,
        agency display names exist, name locales are valid, and the shift
        config covers a full day per rotation group.
        """
        for agency, weights in self.priority_weights.items():
            if agency not in self.agency_weights:
                raise ValidationError(f"Priority weights defined for unknown agency: {agency}")
            total = sum(weights.values())
            if abs(total - 1.0) > 0.001:
                raise ValidationError(f"Priority weights for {agency} must sum to 1.0")

        for agency, priorities in self.problem_profiles.items():
            if agency not in self.agency_weights:
                raise ValidationError(f"Problem profiles defined for unknown agency: {agency}")
            for priority in (1, 2, 3, 4, 5):
                if priority not in priorities:
                    raise ValidationError(
                        f"Problem profiles missing for {agency} priority {priority}"
                    )
                total = sum(w for _, w in priorities[priority])
                if abs(total - 1.0) > 0.001:
                    raise ValidationError(
                        f"Problem profiles for {agency} priority {priority} must sum to 1.0"
                    )

        for agency, profiles in self.disposition_profiles.items():
            if agency not in self.agency_weights:
                raise ValidationError(f"Disposition profiles defined for unknown agency: {agency}")
            total = sum(w for _, w in profiles)
            if abs(total - 1.0) > 0.001:
                raise ValidationError(f"Disposition profiles for {agency} must sum to 1.0")

        for agency in self.agency_weights:
            if agency not in self.time_profiles:
                raise ValidationError(f"Time profiles missing for agency: {agency}")
            for priority in (1, 2, 3, 4, 5):
                if priority not in self.time_profiles[agency]:
                    raise ValidationError(f"Time profiles missing for {agency} priority {priority}")
                required_keys = {
                    "interview_mean",
                    "dispatch_mean",
                    "turnout_mean",
                    "travel_mean",
                    "scene_mean",
                    "closeout_mean",
                    "phone_mean",
                }
                missing = required_keys - set(self.time_profiles[agency][priority].keys())
                if missing:
                    raise ValidationError(
                        f"Time profiles for {agency} priority {priority} missing keys: {missing}"
                    )

        for priority in (1, 2, 3, 4, 5):
            if priority not in self.dispatch_init_fraction:
                raise ValidationError(f"dispatch_init_fraction missing for priority {priority}")
            lo, hi = self.dispatch_init_fraction[priority]
            if lo < 0 or hi < lo:
                raise ValidationError(
                    f"dispatch_init_fraction for priority {priority} must satisfy 0 <= lo <= hi"
                )

        required_phone_keys = {
            "min_hourly_volume",
            "nine_one_one_received_fraction",
            "non_emergency_received_fraction",
            "outbound_calls_fraction",
            "nine_one_one_abandonment_rate",
            "night_abandonment_increment",
            "non_emergency_abandonment_rate",
            "max_abandonment_rate",
            "weekend_multiplier",
            "nine_one_one_answer_time_mean",
            "nine_one_one_answer_time_sigma",
            "non_emergency_answer_time_mean",
            "non_emergency_answer_time_sigma",
            "answer_time_thresholds",
        }
        missing_phone_keys = required_phone_keys - set(self.phone_metrics)
        if missing_phone_keys:
            raise ValidationError(f"phone_metrics missing keys: {missing_phone_keys}")
        max_abandon = self.phone_metrics.get("max_abandonment_rate", 1.0)
        if isinstance(max_abandon, (int, float)) and (max_abandon < 0 or max_abandon > 1.0):
            raise ValidationError("phone_metrics.max_abandonment_rate must be between 0 and 1")
        min_vol = self.phone_metrics.get("min_hourly_volume", 0)
        if isinstance(min_vol, (int, float)) and min_vol < 0:
            raise ValidationError("phone_metrics.min_hourly_volume must be non-negative")

        _PHONE_LINE_KEYS = {
            "received_fraction",
            "abandonment_rate",
            "night_abandonment_increment",
            "answer_time_mean",
            "answer_time_sigma",
            "phone_duration_mu",
            "phone_duration_sigma",
        }
        for number, overrides in self.phone_metric_lines.items():
            if not str(number).strip():
                raise ValidationError("phone_metric_lines key must not be empty")
            unknown = set(overrides) - _PHONE_LINE_KEYS
            if unknown:
                raise ValidationError(
                    f"phone_metric_lines for {number} has unknown key(s): {', '.join(sorted(unknown))}"
                )
            for key, value in overrides.items():
                if not isinstance(value, (int, float)):
                    raise ValidationError(f"phone_metric_lines for {number}.{key} must be numeric")
                if (
                    key in ("received_fraction", "abandonment_rate", "night_abandonment_increment")
                    and not 0 <= float(value) <= 1
                ):
                    raise ValidationError(
                        f"phone_metric_lines for {number}.{key} must be between 0 and 1"
                    )
                if key in ("answer_time_sigma", "phone_duration_sigma") and float(value) <= 0:
                    raise ValidationError(
                        f"phone_metric_lines for {number}.{key} must be greater than 0"
                    )

        for agency in self.agency_weights:
            if agency not in self.agency_names:
                raise ValidationError(f"Agency name mapping missing for: {agency}")

        if self.name_locales:
            validate_name_locales(self.name_locales)

        self.shift_config.validate()

        allowed_discipline_keys = {"mode", "min_dispatchers_for_split"}
        unknown_discipline_keys = set(self.dispatcher_disciplines) - allowed_discipline_keys
        if unknown_discipline_keys:
            raise ValidationError(
                "dispatcher_disciplines has unknown key(s): "
                f"{', '.join(sorted(unknown_discipline_keys))}"
            )
        discipline_mode = str(self.dispatcher_disciplines.get("mode", "auto"))
        if discipline_mode not in {"auto", "combined", "two_way", "three_way"}:
            raise ValidationError(
                "dispatcher_disciplines.mode must be one of "
                f"auto/combined/two_way/three_way, got {discipline_mode!r}"
            )
        split_threshold = self.dispatcher_disciplines.get("min_dispatchers_for_split", 4)
        if isinstance(split_threshold, bool) or not isinstance(split_threshold, (int, float)):
            raise ValidationError("dispatcher_disciplines.min_dispatchers_for_split must be an integer")
        if int(split_threshold) < 1:
            raise ValidationError(
                "dispatcher_disciplines.min_dispatchers_for_split must be at least 1"
            )

        for line, points in self.answer_time_targets.items():
            if line not in ("nine_one_one", "non_emergency"):
                raise ValidationError(
                    f"answer_time_targets line must be 'nine_one_one' or 'non_emergency', got {line!r}"
                )
            for threshold, percentile in points:
                if threshold <= 0:
                    raise ValidationError(
                        f"answer_time_targets[{line}] threshold must be positive, got {threshold}"
                    )
                if not 0 < percentile < 1:
                    raise ValidationError(
                        f"answer_time_targets[{line}] percentile must be in (0, 1), got {percentile}"
                    )

    def check_answer_time_targets(self, tolerance: float = 0.02) -> list[AnswerTimeCheck]:
        """Compare published answer-time targets against the configured lognormal.

        Returns one :class:`AnswerTimeCheck` per ``(line, threshold)`` target. A
        check passes when ``|implied − target| <= tolerance`` (cumulative-probability
        units). Targets are an optional validation aid and never affect generated
        data; ``validate-config`` reports them and can fail under ``--strict``.
        """
        checks: list[AnswerTimeCheck] = []
        if not self.answer_time_targets:
            return checks
        for line, points in self.answer_time_targets.items():
            mean = _scalar_float(self.phone_metrics.get(f"{line}_answer_time_mean", 0.0))
            sigma = _scalar_float(self.phone_metrics.get(f"{line}_answer_time_sigma", 0.0))
            for threshold, target in points:
                if mean <= 0 or sigma <= 0:
                    checks.append(
                        AnswerTimeCheck(
                            line,
                            threshold,
                            target,
                            float("nan"),
                            float("nan"),
                            False,
                            "answer-time mean/sigma not configured",
                        )
                    )
                    continue
                implied = lognormal_cdf(mean, sigma, threshold)
                gap = implied - target
                checks.append(
                    AnswerTimeCheck(line, threshold, target, implied, gap, abs(gap) <= tolerance, "")
                )
        return checks

    def to_yaml(self, path: Path) -> None:
        """Serialize the full merged config to YAML (round-trips through from_yaml)."""
        data = {
            "agency_weights": self.agency_weights,
            "priority_weights": {k: v for k, v in self.priority_weights.items()},
            "problem_profiles": {
                k: {str(pk): [[p, w] for p, w in pv] for pk, pv in v.items()}
                for k, v in self.problem_profiles.items()
            },
            "call_reception_weights": self.call_reception_weights,
            "disposition_profiles": {
                k: [[p, w] for p, w in v] for k, v in self.disposition_profiles.items()
            },
            "time_profiles": {
                k: {str(pk): pv for pk, pv in v.items()} for k, v in self.time_profiles.items()
            },
            "dispatch_init_fraction": {
                str(k): [lo, hi] for k, (lo, hi) in self.dispatch_init_fraction.items()
            },
            "phone_metrics": self._phone_metrics_for_yaml(),
            "hourly_weights": self.hourly_weights.tolist(),
            "agency_names": self.agency_names,
            "shift_config": self.shift_config.to_dict(),
            "seasonal_multipliers": self.seasonal_multipliers,
            "zone_travel_multipliers": self.zone_travel_multipliers,
            "problem_phone_multipliers": self.problem_phone_multipliers,
            "dispatcher_disciplines": {
                "mode": str(self.dispatcher_disciplines.get("mode", "auto")),
                "min_dispatchers_for_split": int(
                    self.dispatcher_disciplines.get("min_dispatchers_for_split", 4)
                ),
            },
            "name_locales": self._name_locales_for_yaml(),
            "answer_time_targets": {
                line: [[t, p] for t, p in points]
                for line, points in self.answer_time_targets.items()
            },
        }
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, default_flow_style=None)

    def _name_locales_for_yaml(self) -> dict[str, Any]:
        """Emit name_locales as a list of locales when weights are equal, else a mapping."""
        result: dict[str, Any] = {}
        for country, items in self.name_locales.items():
            weights = {weight for _locale, weight in items}
            if len(weights) <= 1:
                result[country] = [locale for locale, _ in items]
            else:
                result[country] = {locale: weight for locale, weight in items}
        return result

    def _phone_metrics_for_yaml(self) -> dict[str, Any]:
        """Phone metrics plus the per-line overrides, nested under ``lines``."""
        data: dict[str, Any] = dict(self.phone_metrics)
        if self.phone_metric_lines:
            data["lines"] = {num: dict(over) for num, over in self.phone_metric_lines.items()}
        return data

    def get_agency_display_name(self, agency: str) -> str:
        """Human-readable agency name (e.g. ``POLICE``) or the code itself."""
        return self.agency_names.get(agency, agency)
