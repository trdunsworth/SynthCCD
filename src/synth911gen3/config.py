from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

from .constants import DEFAULT_AREA_QUERY, DEFAULT_OUTPUT_DIR, DEFAULT_OUTPUT_STEM, DEFAULT_ROWS
from .exceptions import ValidationError
from .realism_config import RealismConfig


class OutputFormat(StrEnum):
    CSV = "csv"
    PARQUET = "parquet"
    JSON = "json"
    YAML = "yaml"
    PANDAS = "pandas"
    POLARS = "polars"


class DatasetKind(StrEnum):
    INCIDENTS = "incidents"
    PHONE = "phone"
    ALL = "all"


@dataclass(slots=True)
class GenerationRequest:
    rows: int = DEFAULT_ROWS
    area_query: str = DEFAULT_AREA_QUERY
    output_format: OutputFormat = OutputFormat.CSV
    dataset: DatasetKind = DatasetKind.ALL
    output_dir: Path = Path(DEFAULT_OUTPUT_DIR)
    output_stem: str = DEFAULT_OUTPUT_STEM
    start_date: date | None = None
    end_date: date | None = None
    seed: int = 911
    calltaker_pool_size: int = 12
    dispatcher_pool_size: int = 10
    realism_config: RealismConfig | None = None
    realism_config_path: Path | None = None

    def resolved_start_date(self) -> date:
        today = date.today()
        return self.start_date or date(today.year, 1, 1)

    def resolved_end_date(self) -> date:
        today = date.today()
        return self.end_date or date(today.year, 12, 31)

    def get_realism_config(self) -> RealismConfig:
        if self.realism_config is not None:
            return self.realism_config
        if self.realism_config_path is not None:
            return RealismConfig.from_yaml(self.realism_config_path)
        return RealismConfig()

    def validate(self) -> None:
        if self.rows <= 0:
            raise ValidationError("rows must be greater than zero.")
        if not self.area_query.strip():
            raise ValidationError("area_query must not be empty.")
        if not self.output_stem.strip():
            raise ValidationError("output_stem must not be empty.")
        if self.calltaker_pool_size <= 0:
            raise ValidationError("calltaker_pool_size must be greater than zero.")
        if self.dispatcher_pool_size <= 0:
            raise ValidationError("dispatcher_pool_size must be greater than zero.")
        if self.resolved_start_date() > self.resolved_end_date():
            raise ValidationError("start_date must be on or before end_date.")
        # Validate realism config if provided
        self.get_realism_config()
