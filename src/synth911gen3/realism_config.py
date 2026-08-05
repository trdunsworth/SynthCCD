from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .constants import (
    AGENCY_WEIGHTS as DEFAULT_AGENCY_WEIGHTS,
    CALL_RECEPTION_WEIGHTS as DEFAULT_CALL_RECEPTION_WEIGHTS,
    DISPOSITION_PROFILES as DEFAULT_DISPOSITION_PROFILES,
    HOURLY_WEIGHTS as DEFAULT_HOURLY_WEIGHTS,
    PRIORITY_WEIGHTS as DEFAULT_PRIORITY_WEIGHTS,
    PROBLEM_PROFILES as DEFAULT_PROBLEM_PROFILES,
    TIME_PROFILES as DEFAULT_TIME_PROFILES,
)
from .exceptions import ValidationError


@dataclass(slots=True)
class RealismConfig:
    agency_weights: dict[str, float] = field(default_factory=dict)
    priority_weights: dict[str, dict[int, float]] = field(default_factory=dict)
    problem_profiles: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    call_reception_weights: dict[str, float] = field(default_factory=dict)
    disposition_profiles: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    time_profiles: dict[str, dict[int, dict[str, int]]] = field(default_factory=dict)
    hourly_weights: np.ndarray = field(default_factory=lambda: np.array([]))
    agency_names: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.agency_weights:
            self.agency_weights = DEFAULT_AGENCY_WEIGHTS.copy()
        if not self.priority_weights:
            self.priority_weights = {k: v.copy() for k, v in DEFAULT_PRIORITY_WEIGHTS.items()}
        if not self.problem_profiles:
            self.problem_profiles = {k: v.copy() for k, v in DEFAULT_PROBLEM_PROFILES.items()}
        if not self.call_reception_weights:
            self.call_reception_weights = DEFAULT_CALL_RECEPTION_WEIGHTS.copy()
        if not self.disposition_profiles:
            self.disposition_profiles = {k: v.copy() for k, v in DEFAULT_DISPOSITION_PROFILES.items()}
        if not self.time_profiles:
            self.time_profiles = {k: {pk: pv.copy() for pk, pv in v.items()} for k, v in DEFAULT_TIME_PROFILES.items()}
        if self.hourly_weights.size == 0:
            self.hourly_weights = DEFAULT_HOURLY_WEIGHTS.copy()
        if not self.agency_names:
            self.agency_names = {"LAW": "LAW", "FIRE": "FIRE", "EMS": "EMS"}

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
            for agency, profiles in data["problem_profiles"].items():
                config.problem_profiles[agency] = [(str(p[0]), float(p[1])) for p in profiles]

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

        if "hourly_weights" in data:
            hw = np.array(data["hourly_weights"], dtype=float)
            if hw.shape != (24,):
                raise ValidationError("hourly_weights must have exactly 24 values")
            config.hourly_weights = hw / hw.sum()

        if "agency_names" in data:
            config.agency_names = data["agency_names"]

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

        for agency, profiles in self.problem_profiles.items():
            if agency not in self.agency_weights:
                raise ValidationError(f"Problem profiles defined for unknown agency: {agency}")
            total = sum(w for _, w in profiles)
            if abs(total - 1.0) > 0.001:
                raise ValidationError(f"Problem profiles for {agency} must sum to 1.0")

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

        for agency in self.agency_weights:
            if agency not in self.agency_names:
                raise ValidationError(f"Agency name mapping missing for: {agency}")

    def to_yaml(self, path: Path) -> None:
        data = {
            "agency_weights": self.agency_weights,
            "priority_weights": {k: v for k, v in self.priority_weights.items()},
            "problem_profiles": {k: [[p, w] for p, w in v] for k, v in self.problem_profiles.items()},
            "call_reception_weights": self.call_reception_weights,
            "disposition_profiles": {k: [[p, w] for p, w in v] for k, v in self.disposition_profiles.items()},
            "time_profiles": {k: {str(pk): pv for pk, pv in v.items()} for k, v in self.time_profiles.items()},
            "hourly_weights": self.hourly_weights.tolist(),
            "agency_names": self.agency_names,
        }
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, default_flow_style=None)

    def get_agency_display_name(self, agency: str) -> str:
        return self.agency_names.get(agency, agency)