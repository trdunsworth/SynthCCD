"""Shared validation rules for generation requests.

The runtime dataclass (:meth:`synth911gen3.config.GenerationRequest.validate`)
and the public pydantic contract (:mod:`synth911gen3.schema`) both apply the
same output-path, PSAP-agency, date-range, and database-option rules. Per
ADR-0002 the dataclass stays the single runtime type and pydantic stays the
edge contract, so the *rules* live here as pure functions and each layer keeps
its own error type: the dataclass wraps :class:`ValueError` messages in
:class:`synth911gen3.exceptions.ValidationError`, while pydantic validators
let :class:`ValueError` propagate natively.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .constants import PSAP_AGENCY_FILTERS, DatabaseDialect, OutputFormat

WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)

_DATABASE_DIALECT_BY_FORMAT: dict[OutputFormat, DatabaseDialect] = {
    OutputFormat.POSTGRESQL: DatabaseDialect.POSTGRESQL,
    OutputFormat.SQLSERVER: DatabaseDialect.SQLSERVER,
    OutputFormat.MARIADB: DatabaseDialect.MARIADB,
    OutputFormat.DUCKDB: DatabaseDialect.DUCKDB,
    OutputFormat.SQLITE: DatabaseDialect.SQLITE,
}

_DEFAULT_SERVER_PORTS: dict[DatabaseDialect, int] = {
    DatabaseDialect.POSTGRESQL: 5432,
    DatabaseDialect.SQLSERVER: 1433,
    DatabaseDialect.MARIADB: 3306,
}

_VALID_DB_IF_EXISTS = ("append", "replace", "fail")


def validate_output_stem(stem: str) -> None:
    """Reject empty, reserved, or path-traversing output file stems.

    Args:
        stem: The requested output file stem (filename without directory).

    Raises:
        ValueError: The stem is empty, ``.``/``..``, contains path
            separators or null bytes, or is a Windows reserved device name.
    """
    if not stem.strip():
        raise ValueError("output_stem must not be empty.")
    if stem in (".", ".."):
        raise ValueError("output_stem must not be '.' or '..'.")
    if any(char in stem for char in ("/", "\\", "\x00")):
        raise ValueError("output_stem must not contain path separators or null bytes.")
    stem_root = stem.split(".", 1)[0].upper()
    if stem_root in WINDOWS_RESERVED_NAMES:
        raise ValueError(f"output_stem must not be a reserved device name: {stem_root}.")


def validate_output_dir(directory: Path) -> None:
    """Reject output directories containing null bytes or ``..`` segments.

    Args:
        directory: The requested output directory.

    Raises:
        ValueError: The directory contains a null byte or a ``..`` segment.
    """
    if "\x00" in str(directory):
        raise ValueError("output_dir must not contain null bytes.")
    if any(part == ".." for part in directory.parts):
        raise ValueError("output_dir must not contain '..' path segments.")


def normalize_psap_agency(value: str) -> str:
    """Normalize a PSAP agency filter and validate it against the known set.

    Args:
        value: Raw filter string (case/whitespace tolerated).

    Returns:
        The stripped, lower-cased filter.

    Raises:
        ValueError: The normalized value is not a known PSAP agency filter.
    """
    normalized = value.strip().lower()
    if normalized not in PSAP_AGENCY_FILTERS:
        raise ValueError(
            f"Unknown psap_agency {value!r}. "
            f"Valid values: {', '.join(sorted(PSAP_AGENCY_FILTERS))}."
        )
    return normalized


def validate_date_range(start: date, end: date) -> None:
    """Reject an inverted date range.

    Args:
        start: Range start (inclusive).
        end: Range end (inclusive).

    Raises:
        ValueError: ``start`` is after ``end``.
    """
    if start > end:
        raise ValueError("start_date must be on or before end_date.")


def resolve_database_options(
    *,
    output_format: OutputFormat,
    db_dialect: DatabaseDialect | None,
    output_stem: str,
    db_name: str | None,
    db_host: str | None,
    db_port: int | None,
    db_user: str | None,
    db_if_exists: str,
    db_batch_size: int,
) -> dict[str, Any]:
    """Validate database-export options and compute missing defaults.

    A no-op (empty dict) unless ``output_format`` is one of the database
    targets. File-based dialects (DuckDB, SQLite) only need a file name,
    defaulted from ``output_stem`` when absent; server dialects require
    host/name/user and default their port.

    Args:
        output_format: Requested export format.
        db_dialect: Explicit dialect override, if any.
        output_stem: Output file stem (used to default file-based names).
        db_name: Database name or file path, if already set.
        db_host: Database host for server dialects.
        db_port: Database port; defaulted per dialect when ``None``.
        db_user: Database user for server dialects.
        db_if_exists: Table-exists behavior (``append``/``replace``/``fail``).
        db_batch_size: Insert batch size (must be positive).

    Returns:
        Field updates to apply (a subset of ``db_name``/``db_port``); the
        request object is never mutated here.

    Raises:
        ValueError: An option is missing or invalid for the resolved dialect.
    """
    if output_format not in _DATABASE_DIALECT_BY_FORMAT:
        return {}
    dialect = db_dialect or _DATABASE_DIALECT_BY_FORMAT[output_format]

    if db_if_exists not in _VALID_DB_IF_EXISTS:
        raise ValueError("db_if_exists must be 'append', 'replace', or 'fail'.")
    if db_batch_size <= 0:
        raise ValueError("db_batch_size must be greater than zero.")

    updates: dict[str, Any] = {}
    if dialect in (DatabaseDialect.DUCKDB, DatabaseDialect.SQLITE):
        # File-based databases only need a file path (resolved against output_dir).
        if not db_name:
            suffix = ".duckdb" if dialect == DatabaseDialect.DUCKDB else ".sqlite3"
            updates["db_name"] = f"{output_stem}{suffix}"
        return updates

    # Server dialects: validate connection parameters and fill port defaults.
    if not db_host:
        raise ValueError("db_host is required for database exports.")
    if not db_name:
        raise ValueError("db_name is required for database exports.")
    if not db_user:
        raise ValueError("db_user is required for database exports.")
    if db_port is None:
        updates["db_port"] = _DEFAULT_SERVER_PORTS[dialect]
    return updates
