from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True, slots=True)
class Address:
    street_address: str
    city: str
    state: str

    @property
    def location(self) -> str:
        return f"{self.street_address}, {self.city}, {self.state}"


@dataclass(frozen=True, slots=True)
class GenerationResult:
    incidents: pd.DataFrame | None
    hourly_call_counts: pd.DataFrame | None
    exported_artifacts: dict[str, Path | Any]
