from __future__ import annotations

from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .constants import (
    DEFAULT_AREA_QUERY,
    DEFAULT_COUNTRY,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_OUTPUT_STEM,
    DEFAULT_ROWS,
)


class OutputFormat(str, Enum):
    CSV = "csv"
    PARQUET = "parquet"
    JSON = "json"
    YAML = "yaml"
    PANDAS = "pandas"
    POLARS = "polars"
    GEOJSON = "geojson"
    SHAPEFILE = "shapefile"
    POSTGRESQL = "postgresql"
    SQLSERVER = "sqlserver"
    MARIADB = "mariadb"
    DUCKDB = "duckdb"


class DatasetKind(str, Enum):
    INCIDENTS = "incidents"
    PHONE = "phone"
    ALL = "all"


class IdFormat(str, Enum):
    INTEGER = "integer"
    GUID = "guid"


class DatabaseDialect(str, Enum):
    POSTGRESQL = "postgresql"
    SQLSERVER = "sqlserver"
    MARIADB = "mariadb"
    DUCKDB = "duckdb"


class ShiftPreset(str, Enum):
    TWO_X_TWELVE_H_FOUR_SHIFT_FOURTEEN_DAY = "2x12h-4shift-14day"
    TWO_X_TWELVE_H_TWO_SHIFT = "2x12h-2shift"
    THREE_X_EIGHT_H_THREE_SHIFT = "3x8h-3shift"
    FOUR_X_TEN_H_FOUR_SHIFT = "4x10h-4shift"


class IfExistsMode(str, Enum):
    APPEND = "append"
    REPLACE = "replace"
    FAIL = "fail"


class TimeProfileIntervals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interview_mean: int = Field(ge=0, description="Caller questioning duration (seconds)")
    dispatch_mean: int = Field(ge=0, description="Queue to unit assignment (seconds)")
    turnout_mean: int = Field(ge=0, description="Station to wheels rolling (seconds)")
    travel_mean: int = Field(ge=0, description="Wheels rolling to on-scene (seconds)")
    scene_mean: int = Field(ge=0, description="On-scene duration (seconds)")
    closeout_mean: int = Field(ge=0, description="Scene clear to incident close (seconds)")
    phone_mean: int = Field(ge=0, description="Total call duration (seconds)")


class DispatchInitFraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lo: float = Field(ge=0, description="Lower bound of dispatch fraction")
    hi: float = Field(ge=0, description="Upper bound of dispatch fraction")

    @model_validator(mode="after")
    def validate_bounds(self) -> DispatchInitFraction:
        if self.hi < self.lo:
            raise ValueError("hi must be >= lo")
        return self


class LineMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    received_fraction: float | None = Field(default=None, ge=0, le=1)
    abandonment_rate: float | None = Field(default=None, ge=0, le=1)
    night_abandonment_increment: float | None = Field(default=None, ge=0, le=1)
    answer_time_mu: float | None = None
    answer_time_sigma: float | None = Field(default=None, gt=0)


class PhoneMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_hourly_volume: float = Field(ge=0)
    nine_one_one_received_fraction: float = Field(ge=0, le=1)
    non_emergency_received_fraction: float = Field(ge=0, le=1)
    outbound_calls_fraction: float = Field(ge=0, le=1)
    nine_one_one_abandonment_rate: float = Field(ge=0, le=1)
    night_abandonment_increment: float = Field(ge=0, le=1)
    non_emergency_abandonment_rate: float = Field(ge=0, le=1)
    max_abandonment_rate: float = Field(ge=0, le=1)
    weekend_multiplier: float = Field(ge=0)
    nine_one_one_answer_time_mu: float
    nine_one_one_answer_time_sigma: float = Field(gt=0)
    non_emergency_answer_time_mu: float
    non_emergency_answer_time_sigma: float = Field(gt=0)
    answer_time_thresholds: list[float] = Field(min_length=1)
    lines: dict[str, LineMetrics] = Field(default_factory=dict)


class ShiftConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    cycle_start_weekday: int = Field(ge=0, le=6)
    rotation: list[int] = Field(min_length=1)
    shifts: list[Shift] = Field(min_length=1)


class Shift(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    label: str
    start_hour: int = Field(ge=0, le=23)
    start_minute: int = Field(ge=0, le=59)
    end_hour: int = Field(ge=0, le=23)
    end_minute: int = Field(ge=0, le=59)
    rotation: int = Field(ge=1)
    calltakers: int | None = Field(default=None, ge=1)
    dispatchers: int | None = Field(default=None, ge=1)


class RealismConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    agency_weights: dict[str, float] = Field(default_factory=dict)
    priority_weights: dict[str, dict[int, float]] = Field(default_factory=dict)
    problem_profiles: dict[str, dict[int, list[list[Any]]]] = Field(default_factory=dict)
    call_reception_weights: dict[str, float] = Field(default_factory=dict)
    disposition_profiles: dict[str, list[list[Any]]] = Field(default_factory=dict)
    time_profiles: dict[str, dict[int, TimeProfileIntervals]] = Field(default_factory=dict)
    dispatch_init_fraction: dict[int, DispatchInitFraction] = Field(default_factory=dict)
    phone_metrics: PhoneMetrics | None = None
    hourly_weights: list[float] | None = None
    agency_names: dict[str, str] = Field(default_factory=dict)
    shift_config: ShiftConfig | None = None
    seasonal_multipliers: dict[str, list[float]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_weights(self) -> RealismConfig:
        # Validate agency weights sum to 1
        if self.agency_weights:
            total = sum(self.agency_weights.values())
            if abs(total - 1.0) > 0.001:
                raise ValueError("agency_weights must sum to 1.0")

        # Validate priority weights per agency
        for agency, weights in self.priority_weights.items():
            total = sum(weights.values())
            if abs(total - 1.0) > 0.001:
                raise ValueError(f"priority_weights for {agency} must sum to 1.0")

        # Validate call reception weights
        if self.call_reception_weights:
            total = sum(self.call_reception_weights.values())
            if abs(total - 1.0) > 0.001:
                raise ValueError("call_reception_weights must sum to 1.0")

        # Validate disposition profiles per agency
        for agency, profiles in self.disposition_profiles.items():
            total = sum(float(p[1]) for p in profiles)
            if abs(total - 1.0) > 0.001:
                raise ValueError(f"disposition_profiles for {agency} must sum to 1.0")

        # Validate problem profiles per agency/priority
        for agency, priorities in self.problem_profiles.items():
            for priority, profiles in priorities.items():
                total = sum(float(p[1]) for p in profiles)
                if abs(total - 1.0) > 0.001:
                    raise ValueError(f"problem_profiles for {agency} priority {priority} must sum to 1.0")

        # Validate hourly weights
        if self.hourly_weights is not None:
            if len(self.hourly_weights) != 24:
                raise ValueError("hourly_weights must have exactly 24 values")
            total = sum(self.hourly_weights)
            if total <= 0:
                raise ValueError("hourly_weights must sum to positive value")

        # Validate seasonal multipliers
        for problem, multipliers in self.seasonal_multipliers.items():
            if len(multipliers) != 4:
                raise ValueError(f"seasonal_multipliers for {problem} must have 4 values (Winter, Spring, Summer, Fall)")

        return self


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    rows: int = Field(default=DEFAULT_ROWS, gt=0, description="Number of incident rows to generate")
    area_query: str = Field(default=DEFAULT_AREA_QUERY, min_length=1, description="OpenStreetMap area query")
    output_format: OutputFormat = Field(default=OutputFormat.CSV, description="Output format")
    dataset: DatasetKind = Field(default=DatasetKind.ALL, description="Dataset to generate")
    id_format: IdFormat = Field(default=IdFormat.INTEGER, description="ID format")
    output_dir: Path = Field(default=Path(DEFAULT_OUTPUT_DIR), description="Output directory")
    output_stem: str = Field(default=DEFAULT_OUTPUT_STEM, min_length=1, description="Output file stem")
    start_date: date | None = Field(default=None, description="Start date (inclusive)")
    end_date: date | None = Field(default=None, description="End date (inclusive)")
    seed: int = Field(default=911, description="Random seed")
    calltaker_pool_size: int = Field(default=12, gt=0, description="Calltaker pool size")
    dispatcher_pool_size: int = Field(default=10, gt=0, description="Dispatcher pool size")
    shift_preset: ShiftPreset | None = Field(default=None, description="Shift structure preset")
    realism_config: RealismConfig | None = Field(default=None, description="Realism configuration")
    realism_config_path: Path | None = Field(default=None, description="Path to realism config YAML")
    max_memory_bytes: int | None = Field(default=None, gt=0, description="Memory budget for chunked export")
    country: str = Field(default=DEFAULT_COUNTRY, min_length=1, description="ISO 3166-1 alpha-2 country code")
    emergency_numbers: str | None = Field(default=None, description="Comma-separated emergency numbers (overrides registry)")
    include_10_digit_emergency: bool = Field(default=False, description="Include 10-digit direct-dial emergency lines")
    db_dialect: DatabaseDialect | None = Field(default=None, description="Database dialect")
    db_host: str | None = Field(default=None, description="Database host")
    db_port: int | None = Field(default=None, gt=0, lt=65536, description="Database port")
    db_name: str | None = Field(default=None, description="Database name")
    db_user: str | None = Field(default=None, description="Database user")
    db_password: str | None = Field(default=None, description="Database password")
    db_table_incidents: str = Field(default="incidents", description="Incidents table name")
    db_table_phone: str = Field(default="hourly_call_counts", description="Phone metrics table name")
    db_schema: str | None = Field(default=None, description="Database schema")
    db_batch_size: int = Field(default=10000, gt=0, description="Batch size for database inserts")
    db_if_exists: IfExistsMode = Field(default=IfExistsMode.APPEND, description="If table exists behavior")
    db_create_indexes: bool = Field(default=True, description="Create indexes on key columns")

    @field_validator("output_stem")
    @classmethod
    def validate_output_stem(cls, v: str) -> str:
        if v in (".", ".."):
            raise ValueError("output_stem must not be '.' or '..'")
        if any(c in v for c in ("/", "\\", "\x00")):
            raise ValueError("output_stem must not contain path separators or null bytes")
        stem_root = v.split(".", 1)[0].upper()
        reserved = {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}
        if stem_root in reserved:
            raise ValueError(f"output_stem must not be a reserved device name: {stem_root}")
        return v

    @field_validator("output_dir")
    @classmethod
    def validate_output_dir(cls, v: Path) -> Path:
        if "\x00" in str(v):
            raise ValueError("output_dir must not contain null bytes")
        if any(part == ".." for part in v.parts):
            raise ValueError("output_dir must not contain '..' path segments")
        return v

    @model_validator(mode="after")
    def validate_dates(self) -> GenerationRequest:
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self

    @model_validator(mode="after")
    def validate_database_options(self) -> GenerationRequest:
        db_formats = {
            OutputFormat.POSTGRESQL,
            OutputFormat.SQLSERVER,
            OutputFormat.MARIADB,
            OutputFormat.DUCKDB,
        }
        if self.output_format in db_formats:
            if self.output_format == OutputFormat.DUCKDB:
                if not self.db_name:
                    self.db_name = f"{self.output_stem}.duckdb"
            else:
                if not self.db_host:
                    raise ValueError("db_host is required for database exports")
                if not self.db_name:
                    raise ValueError("db_name is required for database exports")
                if not self.db_user:
                    raise ValueError("db_user is required for database exports")
                if self.db_port is None:
                    defaults = {
                        DatabaseDialect.POSTGRESQL: 5432,
                        DatabaseDialect.SQLSERVER: 1433,
                        DatabaseDialect.MARIADB: 3306,
                    }
                    dialect = self.db_dialect
                    if dialect is None:
                        dialect_map = {
                            OutputFormat.POSTGRESQL: DatabaseDialect.POSTGRESQL,
                            OutputFormat.SQLSERVER: DatabaseDialect.SQLSERVER,
                            OutputFormat.MARIADB: DatabaseDialect.MARIADB,
                            OutputFormat.DUCKDB: DatabaseDialect.DUCKDB,
                        }
                        dialect = dialect_map[self.output_format]
                    self.db_port = defaults.get(dialect)
        return self


class SchemaVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "1.0"
    generated_at: str
    package: str = "synth911gen3"
    package_version: str
    python_version: str
    platform: str


class OutputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    schema_hash: str
    incidents_columns: dict[str, str] = Field(default_factory=dict)
    phone_columns: dict[str, str] = Field(default_factory=dict)