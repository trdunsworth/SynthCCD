from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .constants import (
    AGENCY_WEIGHTS as DEFAULT_AGENCY_WEIGHTS,
    CALL_RECEPTION_WEIGHTS as DEFAULT_CALL_RECEPTION_WEIGHTS,
    DISPATCH_INIT_FRACTION as DEFAULT_DISPATCH_INIT_FRACTION,
    DISPOSITION_PROFILES as DEFAULT_DISPOSITION_PROFILES,
    HOURLY_WEIGHTS as DEFAULT_HOURLY_WEIGHTS,
    PHONE_METRICS as DEFAULT_PHONE_METRICS,
    PRIORITY_WEIGHTS as DEFAULT_PRIORITY_WEIGHTS,
    PROBLEM_PROFILES as DEFAULT_PROBLEM_PROFILES,
    TIME_PROFILES as DEFAULT_TIME_PROFILES,
)
from .exceptions import ValidationError
from .shifts import ShiftConfig, get_default_shift_config


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
    hourly_weights: np.ndarray = field(default_factory=lambda: np.array([]))
    agency_names: dict[str, str] = field(default_factory=dict)
    shift_config: ShiftConfig = field(default_factory=ShiftConfig)

    def __post_init__(self) -> None:
        if not self.agency_weights:
            self.agency_weights = DEFAULT_AGENCY_WEIGHTS.copy()
        if not self.priority_weights:
            self.priority_weights = {k: v.copy() for k, v in DEFAULT_PRIORITY_WEIGHTS.items()}
        if not self.problem_profiles:
            self.problem_profiles = {
                k: {pk: pv.copy() for pk, pv in v.items()} for k, v in DEFAULT_PROBLEM_PROFILES.items()
            }
        if not self.call_reception_weights:
            self.call_reception_weights = DEFAULT_CALL_RECEPTION_WEIGHTS.copy()
        if not self.disposition_profiles:
            self.disposition_profiles = {k: v.copy() for k, v in DEFAULT_DISPOSITION_PROFILES.items()}
        if not self.time_profiles:
            self.time_profiles = {k: {pk: pv.copy() for pk, pv in v.items()} for k, v in DEFAULT_TIME_PROFILES.items()}
        if not self.dispatch_init_fraction:
            self.dispatch_init_fraction = DEFAULT_DISPATCH_INIT_FRACTION.copy()
        if not self.phone_metrics:
            self.phone_metrics = DEFAULT_PHONE_METRICS.copy()
        if self.hourly_weights.size == 0:
            self.hourly_weights = DEFAULT_HOURLY_WEIGHTS.copy()
        if not self.agency_names:
            self.agency_names = {"LAW": "LAW", "FIRE": "FIRE", "EMS": "EMS"}
        if not self.shift_config.shifts and not self.shift_config.rotation:
            self.shift_config = get_default_shift_config()

    @classmethod
    def from_yaml(cls, path: Path) -> RealismConfig:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        config = cls()

        if "agency_weights" in data:
            config.agency_weights = cls._normalize_weights(data["agency_weights"])

        if "priority_weights" in data:
            config.priority_weights = {}
            for agency, weights in data["priority_weights"].items():
                config.priority_weights[agency] = {int(k): float(v) for k, v in cls._normalize_weights(weights).items()}

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
                    config.time_profiles[agency][int(priority)] = {k: int(v) for k, v in intervals.items()}

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
                if isinstance(v, list):
                    config.phone_metrics[str(k)] = [float(x) for x in v]
                else:
                    config.phone_metrics[str(k)] = float(v)

        if "hourly_weights" in data:
            hw = np.array(data["hourly_weights"], dtype=float)
            if hw.shape != (24,):
                raise ValidationError("hourly_weights must have exactly 24 values")
            config.hourly_weights = hw / hw.sum()

        if "agency_names" in data:
            config.agency_names = data["agency_names"]

        if "shift_config" in data:
            config.shift_config = ShiftConfig.from_dict(data["shift_config"])

        config._validate()
        return config

    @staticmethod
    def _normalize_weights(weights: dict[Any, float]) -> dict[str, float]:
        normalized = {str(k): float(v) for k, v in weights.items()}
        total = sum(normalized.values())
        if total <= 0:
            raise ValidationError("Weights must sum to a positive value")
        return {k: v / total for k, v in normalized.items()}

    def _validate(self) -> None:
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
                    raise ValidationError(f"Problem profiles missing for {agency} priority {priority}")
                total = sum(w for _, w in priorities[priority])
                if abs(total - 1.0) > 0.001:
                    raise ValidationError(f"Problem profiles for {agency} priority {priority} must sum to 1.0")

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
                required_keys = {"interview_mean", "dispatch_mean", "turnout_mean", "travel_mean", "scene_mean", "closeout_mean", "phone_mean"}
                missing = required_keys - set(self.time_profiles[agency][priority].keys())
                if missing:
                    raise ValidationError(f"Time profiles for {agency} priority {priority} missing keys: {missing}")

        for priority in (1, 2, 3, 4, 5):
            if priority not in self.dispatch_init_fraction:
                raise ValidationError(f"dispatch_init_fraction missing for priority {priority}")
            lo, hi = self.dispatch_init_fraction[priority]
            if lo < 0 or hi < lo:
                raise ValidationError(f"dispatch_init_fraction for priority {priority} must satisfy 0 <= lo <= hi")

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
            "nine_one_one_answer_time_mu",
            "nine_one_one_answer_time_sigma",
            "non_emergency_answer_time_mu",
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

        for agency in self.agency_weights:
            if agency not in self.agency_names:
                raise ValidationError(f"Agency name mapping missing for: {agency}")

        self.shift_config.validate()

    def to_yaml(self, path: Path) -> None:
        data = {
            "agency_weights": self.agency_weights,
            "priority_weights": {k: v for k, v in self.priority_weights.items()},
            "problem_profiles": {
                k: {str(pk): [[p, w] for p, w in pv] for pk, pv in v.items()}
                for k, v in self.problem_profiles.items()
            },
            "call_reception_weights": self.call_reception_weights,
            "disposition_profiles": {k: [[p, w] for p, w in v] for k, v in self.disposition_profiles.items()},
            "time_profiles": {k: {str(pk): pv for pk, pv in v.items()} for k, v in self.time_profiles.items()},
            "dispatch_init_fraction": {str(k): [lo, hi] for k, (lo, hi) in self.dispatch_init_fraction.items()},
            "phone_metrics": self.phone_metrics,
            "hourly_weights": self.hourly_weights.tolist(),
            "agency_names": self.agency_names,
            "shift_config": self.shift_config.to_dict(),
        }
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, default_flow_style=None)

    def get_agency_display_name(self, agency: str) -> str:
        return self.agency_names.get(agency, agency)