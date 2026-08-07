from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd
import polars as pl
import yaml

from .config import OutputFormat
from .exceptions import ExportError
from .logging_conf import get_logger

logger = get_logger("exporters")


def _records_for_serialization(frame: pd.DataFrame) -> list[dict[str, Any]]:
    serializable = frame.copy()
    for column in serializable.select_dtypes(include=["datetime64[ns]"]).columns:
        serializable[column] = serializable[column].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return serializable.to_dict(orient="records")


def export_chunked_generator(
    frames: Iterable[pd.DataFrame],
    output_format: OutputFormat,
    output_dir: Path,
    output_stem: str,
    dataset_name: str,
) -> Path:
    """Stream an iterable of DataFrame chunks to disk without holding the full frame.

    Supports CSV (header on the first chunk, then append) and PARQUET (via a
    single ``pyarrow.parquet.ParquetWriter``). Only one chunk's DataFrame is
    materialized at a time, bounding peak memory for very large runs.
    """
    if output_format not in (OutputFormat.CSV, OutputFormat.PARQUET):
        raise ExportError(
            f"Chunked export only supports CSV and PARQUET, got {output_format.value}."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    extension = "csv" if output_format is OutputFormat.CSV else "parquet"
    path = output_dir / f"{output_stem}_{dataset_name}.{extension}"

    chunk_count = 0
    if output_format is OutputFormat.CSV:
        for chunk in frames:
            chunk.to_csv(path, mode="a" if chunk_count else "w", header=chunk_count == 0, index=False)
            chunk_count += 1
    else:
        import pyarrow as pa
        from pyarrow import parquet as pq

        writer: pq.ParquetWriter | None = None
        try:
            for chunk in frames:
                table = pa.Table.from_pandas(chunk)
                if writer is None:
                    writer = pq.ParquetWriter(path, table.schema)
                writer.write_table(table)
                chunk_count += 1
        finally:
            if writer is not None:
                writer.close()

    logger.info("Wrote chunked %s: %s (%d chunks)", extension, path, chunk_count)
    return path


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
            logger.info("Wrote CSV: %s", path)
        return artifacts

    if output_format is OutputFormat.PARQUET:
        artifacts = {}
        for dataset_name, frame in datasets.items():
            path = output_dir / f"{output_stem}_{dataset_name}.parquet"
            frame.to_parquet(path, index=False)
            artifacts[dataset_name] = path
            logger.info("Wrote parquet: %s", path)
        return artifacts

    bundled_payload = {name: _records_for_serialization(frame) for name, frame in datasets.items()}
    if output_format is OutputFormat.JSON:
        path = output_dir / f"{output_stem}_bundle.json"
        path.write_text(json.dumps(bundled_payload, indent=2), encoding="utf-8")
        logger.info("Wrote JSON bundle: %s", path)
        return {"bundle": path}

    if output_format is OutputFormat.YAML:
        path = output_dir / f"{output_stem}_bundle.yaml"
        path.write_text(
            yaml.safe_dump(bundled_payload, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )
        logger.info("Wrote YAML bundle: %s", path)
        return {"bundle": path}

    raise ExportError(f"Unsupported output format: {output_format}")
