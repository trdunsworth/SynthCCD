from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import typer

from .addresses import OpenStreetMapAddressProvider
from .app import Synth911Application
from .config import (
    DatabaseDialect,
    DatasetKind,
    GenerationRequest,
    IdFormat,
    OutputFormat,
)
from .exceptions import AddressLookupError, ExportError, ValidationError
from .logging_conf import configure_logging, get_logger
from .params import (
    build_request_from_params,
    coerce_param as _coerce_param,  # noqa: F401  (re-exported for tests)
    load_params_file,
)
from .tls import maybe_inject_system_trust
from .tui import run as run_tui


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


app = typer.Typer(
    help="Synthetic 911 CAD incident and hourly phone-center data generator.",
    no_args_is_help=True,
)

logger = get_logger("cli")


@app.callback()
def configure(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug-level logging."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error logging."),
) -> None:
    configure_logging(verbose=verbose, quiet=quiet)


def _describe_frame(name: str, frame: pd.DataFrame) -> str:
    return f"{name}: {len(frame):,} rows x {len(frame.columns)} columns"


def _print_schema(name: str, frame: pd.DataFrame) -> None:
    typer.echo(f"{name} schema ({len(frame.columns)} columns):")
    for column in frame.columns:
        typer.echo(f"  {column:<28} {frame[column].dtype}")
    typer.echo()


def _print_samples(name: str, frame: pd.DataFrame, rows: int) -> None:
    typer.echo(f"{name} sample rows ({min(len(frame), rows)}):")
    typer.echo(frame.head(rows).to_string(index=False))
    typer.echo()


def _describe(request: GenerationRequest, *, dry_run: bool) -> None:
    from .describe import SAMPLE_ROWS, build_preview_datasets

    preview = build_preview_datasets(request, schema_only=not dry_run)
    mode = "Dry run" if dry_run else "Schema preview"
    typer.echo(f"{mode}: no files written, no OpenStreetMap fetch (illustrative sample addresses).")
    typer.echo()
    for name, frame in preview.items():
        _print_schema(name, frame)
        if dry_run:
            _print_samples(name, frame, SAMPLE_ROWS)


@app.command()
def generate(
    params: Path | None = typer.Option(
        None,
        "--params",
        "-p",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to a JSON/YAML/TOML file of generation parameters. CLI flags override file values.",
    ),
    rows: int | None = typer.Option(
        None,
        "--rows",
        min=1,
        show_default=False,
        help="Number of incident rows to generate (default: 10000).",
    ),
    area: str | None = typer.Option(
        None,
        "--area",
        show_default=False,
        help='Area query sent to OpenStreetMap for address generation (default: "Kansas City, MO").',
    ),
    output_format: OutputFormat | None = typer.Option(
        None,
        "--format",
        metavar="FORMAT",
        case_sensitive=False,
        show_default=False,
        help=(
            "Output format: csv, parquet, json, yaml, pandas, polars, geojson, "
            "shapefile, postgresql, sqlserver, mariadb, duckdb, sqlite (default: csv)."
        ),
    ),
    dataset: DatasetKind | None = typer.Option(
        None,
        "--dataset",
        case_sensitive=False,
        show_default=False,
        help="Dataset to generate: incidents, phone, or all (default: all).",
    ),
    id_format: IdFormat | None = typer.Option(
        None,
        "--id-format",
        case_sensitive=False,
        show_default=False,
        help="id_number style: integer or guid (default: integer).",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        show_default=False,
        help="Directory where file exports should be written (default: output).",
    ),
    output_stem: str | None = typer.Option(
        None,
        "--output-stem",
        show_default=False,
        help="Filename stem used for exported datasets (default: synthetic_911).",
    ),
    start_date: str | None = typer.Option(
        None,
        "--start-date",
        help="Inclusive start date for generated data (YYYY-MM-DD).",
    ),
    end_date: str | None = typer.Option(
        None,
        "--end-date",
        help="Inclusive end date for generated data (YYYY-MM-DD).",
    ),
    seed: int | None = typer.Option(
        None,
        "--seed",
        show_default=False,
        help="Random seed for reproducible output (default: 911).",
    ),
    calltaker_pool_size: int | None = typer.Option(
        None,
        "--calltaker-pool-size",
        show_default=False,
        help="Number of unique calltaker names (default: 12).",
    ),
    dispatcher_pool_size: int | None = typer.Option(
        None,
        "--dispatcher-pool-size",
        show_default=False,
        help="Number of unique dispatcher names (default: 10).",
    ),
    shift_preset: str | None = typer.Option(
        None,
        "--shift-preset",
        case_sensitive=False,
        show_default=False,
        help=(
            "Shift structure preset: 2x12h-4shift-14day, 2x12h-2shift, "
            "3x8h-3shift, or 4x10h-4shift (default: realism config)."
        ),
    ),
    max_memory_bytes: int | None = typer.Option(
        None,
        "--max-memory-bytes",
        min=1,
        show_default=False,
        help=(
            "Approximate in-memory budget per incident chunk in bytes; "
            "CSV/Parquet exports are streamed in chunks to stay under it "
            "(default: 2147483648 / 2 GiB)."
        ),
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to YAML realism configuration file.",
    ),
    country: str | None = typer.Option(
        None,
        "--country",
        show_default=False,
        help="ISO 3166-1 alpha-2 country code selecting emergency numbers (default: US).",
    ),
    emergency_numbers: str | None = typer.Option(
        None,
        "--emergency-numbers",
        show_default=False,
        help='Comma-separated emergency numbers to model, overriding the country registry (e.g. "999,112").',
    ),
    include_10_digit_emergency: bool = typer.Option(
        False,
        "--include-10-digit-emergency",
        help="Include 10-digit direct-dial emergency lines from the registry.",
    ),
    db_dialect: DatabaseDialect | None = typer.Option(
        None,
        "--db-dialect",
        metavar="DIALECT",
        case_sensitive=False,
        show_default=False,
        help="Database dialect override (postgresql, sqlserver, mariadb, duckdb, sqlite).",
    ),
    db_host: str | None = typer.Option(
        None,
        "--db-host",
        show_default=False,
        help="Database host (not needed for file-based duckdb/sqlite).",
    ),
    db_port: int | None = typer.Option(
        None,
        "--db-port",
        min=1,
        max=65535,
        show_default=False,
        help="Database port (defaults: postgresql 5432, sqlserver 1433, mariadb 3306).",
    ),
    db_name: str | None = typer.Option(
        None,
        "--db-name",
        show_default=False,
        help=("Database name; for duckdb/sqlite the file path (defaults to the output stem)."),
    ),
    db_user: str | None = typer.Option(
        None,
        "--db-user",
        show_default=False,
        help="Database username (not needed for file-based duckdb/sqlite).",
    ),
    db_password: str | None = typer.Option(
        None,
        "--db-password",
        show_default=False,
        help="Database password (not needed for file-based duckdb/sqlite).",
    ),
    db_table_incidents: str | None = typer.Option(
        None,
        "--db-table-incidents",
        show_default=False,
        help="Incidents table name (default: incidents).",
    ),
    db_table_phone: str | None = typer.Option(
        None,
        "--db-table-phone",
        show_default=False,
        help="Hourly phone metrics table name (default: hourly_call_counts).",
    ),
    db_schema: str | None = typer.Option(
        None,
        "--db-schema",
        show_default=False,
        help="Database schema (ignored for sqlite).",
    ),
    db_batch_size: int | None = typer.Option(
        None,
        "--db-batch-size",
        min=1,
        show_default=False,
        help="Rows per insert batch (default: 10000).",
    ),
    db_if_exists: str | None = typer.Option(
        None,
        "--db-if-exists",
        case_sensitive=False,
        show_default=False,
        help="Table-exists behavior: append, replace, or fail (default: append).",
    ),
    db_create_indexes: bool | None = typer.Option(
        None,
        "--no-db-create-indexes",
        help="Skip creating indexes on key columns (default: create them).",
    ),
    schema: bool = typer.Option(
        False,
        "--schema",
        help="Print the generated schema (columns and types) without generating data or fetching addresses.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print the schema plus a few sample rows without writing files or fetching addresses.",
    ),
) -> None:
    cli_params: dict[str, Any] = {}
    if rows is not None:
        cli_params["rows"] = rows
    if area is not None:
        cli_params["area_query"] = area
    if output_format is not None:
        cli_params["output_format"] = output_format
    if dataset is not None:
        cli_params["dataset"] = dataset
    if id_format is not None:
        cli_params["id_format"] = id_format
    if output_dir is not None:
        cli_params["output_dir"] = output_dir
    if output_stem is not None:
        cli_params["output_stem"] = output_stem
    if start_date is not None:
        cli_params["start_date"] = _parse_date(start_date)
    if end_date is not None:
        cli_params["end_date"] = _parse_date(end_date)
    if seed is not None:
        cli_params["seed"] = seed
    if calltaker_pool_size is not None:
        cli_params["calltaker_pool_size"] = calltaker_pool_size
    if dispatcher_pool_size is not None:
        cli_params["dispatcher_pool_size"] = dispatcher_pool_size
    if shift_preset is not None:
        cli_params["shift_preset"] = shift_preset
    if max_memory_bytes is not None:
        cli_params["max_memory_bytes"] = max_memory_bytes
    if config is not None:
        cli_params["realism_config_path"] = config
    if country is not None:
        cli_params["country"] = country
    if emergency_numbers is not None:
        cli_params["emergency_numbers"] = emergency_numbers
    if include_10_digit_emergency:
        cli_params["include_10_digit_emergency"] = True
    if db_dialect is not None:
        cli_params["db_dialect"] = db_dialect
    if db_host is not None:
        cli_params["db_host"] = db_host
    if db_port is not None:
        cli_params["db_port"] = db_port
    if db_name is not None:
        cli_params["db_name"] = db_name
    if db_user is not None:
        cli_params["db_user"] = db_user
    if db_password is not None:
        cli_params["db_password"] = db_password
    if db_table_incidents is not None:
        cli_params["db_table_incidents"] = db_table_incidents
    if db_table_phone is not None:
        cli_params["db_table_phone"] = db_table_phone
    if db_schema is not None:
        cli_params["db_schema"] = db_schema
    if db_batch_size is not None:
        cli_params["db_batch_size"] = db_batch_size
    if db_if_exists is not None:
        cli_params["db_if_exists"] = db_if_exists
    if db_create_indexes is not None:
        cli_params["db_create_indexes"] = False

    file_params = load_params_file(params) if params is not None else {}
    request = build_request_from_params(file_params, cli_params)

    logger.info(
        "Generating %d rows (%s, %s)",
        request.rows,
        request.dataset.value,
        request.output_format.value,
    )
    try:
        if dry_run or schema:
            _describe(request, dry_run=dry_run)
            return
        result = Synth911Application(address_provider=OpenStreetMapAddressProvider()).generate(
            request
        )
    except (AddressLookupError, ExportError, ValidationError) as exc:
        logger.error("%s: %s", type(exc).__name__, exc)
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if request.output_format in (OutputFormat.PANDAS, OutputFormat.POLARS):
        if result.incidents is not None:
            typer.echo(_describe_frame("incidents", result.incidents))
        if result.hourly_call_counts is not None:
            typer.echo(_describe_frame("hourly_call_counts", result.hourly_call_counts))
        return

    for dataset_name, artifact in result.exported_artifacts.items():
        logger.info("Exported %s -> %s", dataset_name, artifact)
        typer.echo(f"{dataset_name}: {artifact}")


@app.command()
def tui() -> None:
    """Launch the TUI scaffold."""

    run_tui()


def main() -> None:
    maybe_inject_system_trust()
    app()
