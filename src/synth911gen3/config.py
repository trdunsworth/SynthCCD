"""Runtime generation request and output-format configuration.

:class:`GenerationRequest` is the single in-memory description of what a
generation run should produce — row count, area, format, dataset, date
range, seed, personnel pools, realism overrides, and database-export
options. Every entry point (CLI, TUI, params files, REST API) builds one
of these and hands it to :class:`synth911gen3.app.Synth911Application`.

The enums here are the canonical string values used across the CLI flags,
params files, and REST payloads; the parallel enums in
:mod:`synth911gen3.schema` are the pydantic validation layer over the
same vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

from .constants import (
    DEFAULT_AREA_QUERY,
    DEFAULT_COUNTRY,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_OUTPUT_STEM,
    DEFAULT_ROWS,
)
from .emergency_numbers import EmergencyNumber, resolve_emergency_numbers
from .exceptions import ValidationError
from .realism_config import RealismConfig
from .shifts import SHIFT_PRESETS

_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)


class OutputFormat(StrEnum):
    """Supported export targets for generated datasets.

    File formats (csv, parquet, json, yaml, geojson, shapefile), in-memory
    formats (pandas, polars), and direct database targets (postgresql,
    sqlserver, mariadb, duckdb, sqlite).
    """

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
    SQLITE = "sqlite"


class DatabaseDialect(StrEnum):
    """SQL dialects supported by the database exporter."""

    POSTGRESQL = "postgresql"
    SQLSERVER = "sqlserver"
    MARIADB = "mariadb"
    DUCKDB = "duckdb"
    SQLITE = "sqlite"


class DatasetKind(StrEnum):
    """Which datasets a run generates: incidents, phone, or both."""

    INCIDENTS = "incidents"
    PHONE = "phone"
    ALL = "all"


class IdFormat(StrEnum):
    """How incident ``id_number`` values are produced: sequential ints or UUIDs."""

    INTEGER = "integer"
    GUID = "guid"


@dataclass(slots=True)
class GenerationRequest:
    """Everything needed to run one generation, with defaults.

    Defaults match the CLI defaults: 10,000 rows, Kansas City MO,
    CSV output, incidents only, integer IDs, seed 911. Optional values
    (``None``) mean "use the built-in default" and are resolved lazily by
    the ``resolved_*`` methods, so a request always carries an explicit
    value once resolved.
    """

    rows: int = DEFAULT_ROWS
    area_query: str = DEFAULT_AREA_QUERY
    output_format: OutputFormat = OutputFormat.CSV
    dataset: DatasetKind = DatasetKind.INCIDENTS
    id_format: IdFormat = IdFormat.INTEGER
    output_dir: Path = Path(DEFAULT_OUTPUT_DIR)
    output_stem: str = DEFAULT_OUTPUT_STEM
    start_date: date | None = None
    end_date: date | None = None
    seed: int = 911
    calltaker_pool_size: int = 12
    dispatcher_pool_size: int = 10
    shift_preset: str | None = None
    realism_config: RealismConfig | None = None
    realism_config_path: Path | None = None
    max_memory_bytes: int | None = None
    # Population of the service area — when set, phone-metrics volume is
    # derived from population (calls per 1 000 residents per year) instead
    # of the incident row count.
    population: int | None = None
    # Emergency-number registry selection
    country: str = DEFAULT_COUNTRY
    emergency_numbers: str | None = None
    include_10_digit_emergency: bool = False
    # Database export options
    db_dialect: DatabaseDialect | None = None
    db_host: str | None = None
    db_port: int | None = None
    db_name: str | None = None
    db_user: str | None = None
    db_password: str | None = None
    db_table_incidents: str = "incidents"
    db_table_phone: str = "hourly_call_counts"
    db_schema: str | None = None
    db_batch_size: int = 10000
    db_if_exists: str = "append"  # "append", "replace", "fail"
    db_create_indexes: bool = True

    def resolved_start_date(self) -> date:
        """Effective start date: the request value, or Jan 1 of this year."""
        today = date.today()  # noqa: DTZ011
        return self.start_date or date(today.year, 1, 1)

    def resolved_end_date(self) -> date:
        """Effective end date: the request value, or Dec 31 of this year."""
        today = date.today()  # noqa: DTZ011
        return self.end_date or date(today.year, 12, 31)

    def get_realism_config(self) -> RealismConfig:
        """Resolve the realism config: explicit object, YAML path, or defaults."""
        if self.realism_config is not None:
            return self.realism_config
        if self.realism_config_path is not None:
            return RealismConfig.from_yaml(self.realism_config_path)
        return RealismConfig()

    def resolved_emergency_numbers(self) -> list[EmergencyNumber]:
        """Resolve the emergency-number registry for the request's country."""
        return resolve_emergency_numbers(
            self.country, self.emergency_numbers, self.include_10_digit_emergency
        )

    def validate(self) -> None:
        """Validate the request, raising :class:`ValidationError` on any problem.

        Checks row counts, output paths, personnel pools, date ordering,
        shift-preset names, emergency-number overrides, realism config,
        and database options (for database formats).
        """
        if self.rows <= 0:
            raise ValidationError("rows must be greater than zero.")
        if not self.area_query.strip():
            raise ValidationError("area_query must not be empty.")
        self._validate_output_path()
        if self.calltaker_pool_size <= 0:
            raise ValidationError("calltaker_pool_size must be greater than zero.")
        if self.dispatcher_pool_size <= 0:
            raise ValidationError("dispatcher_pool_size must be greater than zero.")
        if self.max_memory_bytes is not None and self.max_memory_bytes <= 0:
            raise ValidationError("max_memory_bytes must be greater than zero when set.")
        if self.population is not None and self.population <= 0:
            raise ValidationError("population must be greater than zero when set.")
        if self.resolved_start_date() > self.resolved_end_date():
            raise ValidationError("start_date must be on or before end_date.")
        if self.shift_preset is not None and self.shift_preset not in SHIFT_PRESETS:
            raise ValidationError(
                f"Unknown shift_preset {self.shift_preset!r}. Available presets: "
                f"{', '.join(sorted(SHIFT_PRESETS))}."
            )
        try:
            self.resolved_emergency_numbers()
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        # Validate realism config if provided
        self.get_realism_config()

        # Validate database options if using database output format
        if self.output_format in (
            OutputFormat.POSTGRESQL,
            OutputFormat.SQLSERVER,
            OutputFormat.MARIADB,
            OutputFormat.DUCKDB,
            OutputFormat.SQLITE,
        ):
            self._validate_database_options()

    def _validate_database_options(self) -> None:
        """Validate DB options and fill defaults (file names, ports) for the dialect.

        File-based dialects (duckdb, sqlite) only require a file name
        (resolved against ``output_dir``); server dialects require
        host/name/user and default their port.
        """
        # Determine dialect from output_format if not explicitly set
        dialect_map = {
            OutputFormat.POSTGRESQL: DatabaseDialect.POSTGRESQL,
            OutputFormat.SQLSERVER: DatabaseDialect.SQLSERVER,
            OutputFormat.MARIADB: DatabaseDialect.MARIADB,
            OutputFormat.DUCKDB: DatabaseDialect.DUCKDB,
            OutputFormat.SQLITE: DatabaseDialect.SQLITE,
        }
        dialect = self.db_dialect or dialect_map.get(self.output_format)

        if dialect is None:
            raise ValidationError(
                f"Unknown database dialect for output format: {self.output_format}"
            )

        # Common option validation applies to every dialect
        if self.db_if_exists not in ("append", "replace", "fail"):
            raise ValidationError("db_if_exists must be 'append', 'replace', or 'fail'.")
        if self.db_batch_size <= 0:
            raise ValidationError("db_batch_size must be greater than zero.")

        if dialect in (DatabaseDialect.DUCKDB, DatabaseDialect.SQLITE):
            # File-based databases only need a file path (resolved against output_dir)
            if not self.db_name:
                suffix = ".duckdb" if dialect == DatabaseDialect.DUCKDB else ".sqlite3"
                self.db_name = f"{self.output_stem}{suffix}"
            return

        # For other databases, validate connection parameters
        if not self.db_host:
            raise ValidationError("db_host is required for database exports.")
        if not self.db_name:
            raise ValidationError("db_name is required for database exports.")
        if not self.db_user:
            raise ValidationError("db_user is required for database exports.")
        if self.db_port is None:
            # Set default ports per dialect
            defaults: dict[DatabaseDialect, int] = {
                DatabaseDialect.POSTGRESQL: 5432,
                DatabaseDialect.SQLSERVER: 1433,
                DatabaseDialect.MARIADB: 3306,
            }
            self.db_port = defaults[dialect]

    def _validate_output_path(self) -> None:
        """Reject empty, reserved, or path-traversing output stem/directory values."""
        if not self.output_stem.strip():
            raise ValidationError("output_stem must not be empty.")
        if self.output_stem in (".", ".."):
            raise ValidationError("output_stem must not be '.' or '..'.")
        if any(char in self.output_stem for char in ("/", "\\", "\x00")):
            raise ValidationError("output_stem must not contain path separators or null bytes.")
        stem_root = self.output_stem.split(".", 1)[0].upper()
        if stem_root in _WINDOWS_RESERVED_NAMES:
            raise ValidationError(f"output_stem must not be a reserved device name: {stem_root}.")

        if "\x00" in str(self.output_dir):
            raise ValidationError("output_dir must not contain null bytes.")
        if any(part == ".." for part in self.output_dir.parts):
            raise ValidationError("output_dir must not contain '..' path segments.")
