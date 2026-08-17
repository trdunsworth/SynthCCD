"""Params-file loading, saving, and merging for generation requests.

A params file lets users persist a full run configuration (JSON, YAML, or
TOML) instead of repeating CLI flags. :func:`load_params_file` reads and
normalizes it, :func:`coerce_param` converts raw string values into the
types :class:`~synth911gen3.config.GenerationRequest` expects, and
:func:`build_request_from_params` merges file values with explicit CLI
flags (CLI wins) into a validated request.
"""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

import typer
import yaml

from .config import DatabaseDialect, DatasetKind, GenerationRequest, IdFormat, OutputFormat

_PARAMS_FILE_ALIASES = {
    "area": "area_query",
    "format": "output_format",
    "config": "realism_config_path",
}


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


def _to_plain(value: Any) -> Any:
    """Convert a GenerationRequest-compatible value to a plain JSON/YAML/TOML type."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _dump_toml(data: dict[str, Any]) -> str:
    """Serialize a flat dict of plain scalars to TOML."""
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, (int, float)):
            rendered = str(value)
        else:
            rendered = json.dumps(str(value))
        lines.append(f"{key} = {rendered}")
    return "\n".join(lines) + "\n"


def save_params_file(path: Path, params: dict[str, Any]) -> None:
    """Write generation parameters to a params file (JSON/YAML/TOML).

    ``params`` should be a mapping of canonical ``GenerationRequest`` field
    names to values (as built by ``build_request_from_params``). Enums, paths,
    and dates are serialized to plain string values so the file round-trips
    through ``load_params_file`` + ``coerce_param``.
    """
    suffix = path.suffix.lower()
    data = {key: _to_plain(value) for key, value in params.items() if value is not None}

    if suffix == ".json":
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    elif suffix in (".yaml", ".yml"):
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    elif suffix == ".toml":
        path.write_text(_dump_toml(data), encoding="utf-8")
    else:
        raise typer.BadParameter(
            f"Unsupported params file format: {suffix} (expected .json, .yaml, .yml, or .toml)."
        )


def coerce_param(key: str, value: Any) -> Any:
    """Coerce a raw params-file value into the type expected by GenerationRequest."""
    if key in ("output_format",):
        return OutputFormat(str(value))
    if key in ("dataset",):
        return DatasetKind(str(value))
    if key in ("id_format",):
        return IdFormat(str(value))
    if key in ("db_dialect",):
        return DatabaseDialect(str(value))
    if key in ("output_dir", "realism_config_path"):
        return Path(value)
    if key in ("start_date", "end_date"):
        return date.fromisoformat(str(value))
    if key in ("rows", "seed", "calltaker_pool_size", "dispatcher_pool_size", "max_memory_bytes", "population"):
        return int(value)
    if key in ("include_10_digit_emergency",):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    return value


def build_request_from_params(
    file_params: dict[str, Any], cli_params: dict[str, Any]
) -> GenerationRequest:
    """Merge params-file values with explicit CLI flags and build a GenerationRequest.

    Precedence: CLI flags > params file > GenerationRequest defaults.
    """
    allowed = {field.name for field in fields(GenerationRequest)}
    unknown = set(file_params) - allowed
    if unknown:
        raise typer.BadParameter(
            f"Unknown parameter(s) in params file: {', '.join(sorted(unknown))}"
        )

    merged = {key: coerce_param(key, value) for key, value in file_params.items()}
    merged.update(cli_params)
    return GenerationRequest(**merged)
