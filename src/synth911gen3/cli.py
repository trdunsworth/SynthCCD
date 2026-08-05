from __future__ import annotations

import json
from dataclasses import fields
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import typer
import yaml

from .addresses import OpenStreetMapAddressProvider
from .app import Synth911Application
from .config import DatasetKind, GenerationRequest, OutputFormat
from .exceptions import AddressLookupError, ExportError, ValidationError
from .tls import maybe_inject_system_trust
from .tui import run as run_tui

_PARAMS_FILE_ALIASES = {
    "area": "area_query",
    "format": "output_format",
    "config": "realism_config_path",
}


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


app = typer.Typer(
    help="Synthetic 911 CAD incident and hourly phone-center data generator.",
    no_args_is_help=True,
)


def _describe_frame(name: str, frame: pd.DataFrame) -> str:
    return f"{name}: {len(frame):,} rows x {len(frame.columns)} columns"


def load_params_file(path: Path) -> dict[str, Any]:
    """Load a params file and normalize key names to GenerationRequest fields.

    Supports JSON (``.json``), YAML (``.yaml``/``.yml``), and TOML (``.toml``).
    Keys may use the CLI option names (``area``, ``format``, ``config``) or the
    canonical ``GenerationRequest`` field names (``area_query``, ``output_format``,
    ``realism_config_path``).
    """
    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
        elif suffix in (".yaml", ".yml"):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        elif suffix == ".toml":
            import tomllib

            data = tomllib.loads(path.read_text(encoding="utf-8"))
        else:
            raise typer.BadParameter(
                f"Unsupported params file format: {suffix} (expected .json, .yaml, .yml, or .toml)."
            )
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON in params file: {exc}") from exc
    except yaml.YAMLError as exc:
        raise typer.BadParameter(f"Invalid YAML in params file: {exc}") from exc

    if not isinstance(data, dict):
        raise typer.BadParameter("Params file must contain a top-level mapping of parameters.")

    for alias, canonical in _PARAMS_FILE_ALIASES.items():
        if alias in data:
            data.setdefault(canonical, data[alias])
            data.pop(alias)

    return data


def _coerce_param(key: str, value: Any) -> Any:
    if key in ("output_format",):
        return OutputFormat(str(value))
    if key in ("dataset",):
        return DatasetKind(str(value))
    if key in ("output_dir", "realism_config_path"):
        return Path(value)
    if key in ("start_date", "end_date"):
        return date.fromisoformat(str(value))
    if key in ("rows", "seed", "calltaker_pool_size", "dispatcher_pool_size"):
        return int(value)
    return value


def build_request_from_params(file_params: dict[str, Any], cli_params: dict[str, Any]) -> GenerationRequest:
    """Merge params-file values with explicit CLI flags and build a GenerationRequest.

    Precedence: CLI flags > params file > GenerationRequest defaults.
    """
    allowed = {field.name for field in fields(GenerationRequest)}
    unknown = set(file_params) - allowed
    if unknown:
        raise typer.BadParameter(f"Unknown parameter(s) in params file: {', '.join(sorted(unknown))}")

    merged = {key: _coerce_param(key, value) for key, value in file_params.items()}
    merged.update(cli_params)
    return GenerationRequest(**merged)


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
        case_sensitive=False,
        show_default=False,
        help="Output format: csv, parquet, json, yaml, pandas, polars (default: csv).",
    ),
    dataset: DatasetKind | None = typer.Option(
        None,
        "--dataset",
        case_sensitive=False,
        show_default=False,
        help="Dataset to generate: incidents, phone, or all (default: all).",
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
    config: Path | None = typer.Option(
        None,
        "--config",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to YAML realism configuration file.",
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
    if config is not None:
        cli_params["realism_config_path"] = config

    file_params = load_params_file(params) if params is not None else {}
    request = build_request_from_params(file_params, cli_params)

    try:
        result = Synth911Application(address_provider=OpenStreetMapAddressProvider()).generate(request)
    except (AddressLookupError, ExportError, ValidationError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if request.output_format in (OutputFormat.PANDAS, OutputFormat.POLARS):
        if result.incidents is not None:
            typer.echo(_describe_frame("incidents", result.incidents))
        if result.hourly_call_counts is not None:
            typer.echo(_describe_frame("hourly_call_counts", result.hourly_call_counts))
        return

    for dataset_name, artifact in result.exported_artifacts.items():
        typer.echo(f"{dataset_name}: {artifact}")


@app.command()
def tui() -> None:
    """Launch the TUI scaffold."""

    run_tui()


def main() -> None:
    maybe_inject_system_trust()
    app()
