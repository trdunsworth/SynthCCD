from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd
import polars as pl
import yaml

from .config import OutputFormat
from .exceptions import ExportError


def _records_for_serialization(frame: pd.DataFrame) -> list[dict[str, Any]]:
    serializable = frame.copy()
    for column in serializable.select_dtypes(include=["datetime64[ns]"]).columns:
        serializable[column] = serializable[column].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return serializable.to_dict(orient="records")


def export_generated_data(
    datasets: Mapping[str, pd.DataFrame],
    output_format: OutputFormat,
    output_dir: Path,
    output_stem: str,
) -> dict[str, Any]:
    if output_format is OutputFormat.PANDAS:
        return dict(datasets)

    if output_format is OutputFormat.POLARS:
        return {name: pl.from_pandas(frame) for name, frame in datasets.items()}

    output_dir.mkdir(parents=True, exist_ok=True)

    if output_format is OutputFormat.CSV:
        artifacts: dict[str, Path] = {}
        for dataset_name, frame in datasets.items():
            path = output_dir / f"{output_stem}_{dataset_name}.csv"
            frame.to_csv(path, index=False)
            artifacts[dataset_name] = path
        return artifacts

    if output_format is OutputFormat.PARQUET:
        artifacts = {}
        for dataset_name, frame in datasets.items():
            path = output_dir / f"{output_stem}_{dataset_name}.parquet"
            frame.to_parquet(path, index=False)
            artifacts[dataset_name] = path
        return artifacts

    bundled_payload = {name: _records_for_serialization(frame) for name, frame in datasets.items()}
    if output_format is OutputFormat.JSON:
        path = output_dir / f"{output_stem}_bundle.json"
        path.write_text(json.dumps(bundled_payload, indent=2), encoding="utf-8")
        return {"bundle": path}

    if output_format is OutputFormat.YAML:
        path = output_dir / f"{output_stem}_bundle.yaml"
        path.write_text(
            yaml.safe_dump(bundled_payload, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )
        return {"bundle": path}

    raise ExportError(f"Unsupported output format: {output_format}")
