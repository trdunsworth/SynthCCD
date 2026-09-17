"""Dataset writers for every supported output format.

File formats (CSV, Parquet, JSON, YAML, GeoJSON, Shapefile) write into
``output_dir`` using the ``{stem}_{dataset}.{ext}`` naming convention;
in-memory formats (pandas, polars) return the frames directly; database
formats are handled by :mod:`synth911gen3.db_exporter`. Large runs stream
through :func:`export_chunked_generator` to bound peak memory, and the
governance manifest lands as a JSON sidecar via
:func:`export_manifest`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import polars as pl
import yaml

if TYPE_CHECKING:
    import pyarrow as pa

from .config import OutputFormat
from .exceptions import ExportError
from .logging_conf import get_logger
from .manifest import Manifest, write_manifest

logger = get_logger("exporters")


def _write_parquet_with_metadata(
    frame: pd.DataFrame,
    path: Path,
    metadata: Mapping[str, str] | None,
) -> None:
    """Write a DataFrame to Parquet, embedding key-value footer metadata.

    Uses a ``pyarrow.parquet.ParquetWriter`` whose schema carries the custom
    metadata, so the keys land in the file's plain key-value metadata (visible
    to any Parquet reader, not just pyarrow).
    """
    import pyarrow as pa
    from pyarrow import parquet as pq

    table = pa.Table.from_pandas(frame, preserve_index=False)
    if not metadata:
        pq.write_table(table, path)
        return
    embedded = _merge_schema_metadata(table.schema, metadata)
    writer = pq.ParquetWriter(path, embedded)
    try:
        writer.write_table(table)
    finally:
        writer.close()


def _merge_schema_metadata(
    schema: pa.Schema,
    metadata: Mapping[str, str],
) -> pa.Schema:
    """Merge namespaced string metadata into a schema's existing metadata.

    ``schema.with_metadata`` replaces the whole dict (dropping pyarrow's
    ``pandas`` round-trip key), so merge instead.
    """
    merged = dict(schema.metadata or {})
    merged.update({k.encode(): str(v).encode() for k, v in metadata.items()})
    return schema.with_metadata(merged)


def _records_for_serialization(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame to JSON/YAML-safe records (datetimes as ISO strings)."""
    serializable = frame.copy()
    for column in serializable.select_dtypes(include=["datetime64[ns]"]).columns:
        serializable[column] = serializable[column].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return serializable.to_dict(orient="records")


def _build_geojson_features(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert incident DataFrame rows to GeoJSON Feature objects."""
    features = []
    for _, row in frame.iterrows():
        lon = row.get("longitude", 0.0)
        lat = row.get("latitude", 0.0)
        if pd.isna(lon) or pd.isna(lat) or lon == 0.0 or lat == 0.0:
            continue
        properties = row.to_dict()
        # Remove lat/lon from properties since they're in geometry
        properties.pop("latitude", None)
        properties.pop("longitude", None)
        # Convert datetime objects to ISO format strings
        for key, value in properties.items():
            if pd.isna(value):
                properties[key] = None
            elif hasattr(value, "isoformat"):
                properties[key] = value.isoformat()
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                "properties": properties,
            }
        )
    return features


def export_geojson(
    frame: pd.DataFrame,
    output_dir: Path,
    output_stem: str,
    dataset_name: str,
) -> Path:
    """Export incidents as GeoJSON FeatureCollection."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{output_stem}_{dataset_name}.geojson"

    features = _build_geojson_features(frame)
    geojson = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(geojson, indent=2), encoding="utf-8")
    logger.info("Wrote GeoJSON: %s (%d features)", path, len(features))
    return path


def export_shapefile(
    frame: pd.DataFrame,
    output_dir: Path,
    output_stem: str,
    dataset_name: str,
) -> Path:
    """Export incidents as ESRI Shapefile (requires geopandas)."""
    try:
        import geopandas as gpd
        from shapely.geometry import Point
    except ImportError as exc:
        raise ExportError(
            "Shapefile export requires 'geopandas' and 'shapely'. "
            "Install with: uv add geopandas shapely"
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    base_path = output_dir / f"{output_stem}_{dataset_name}"

    # Filter rows with valid coordinates
    valid = frame.dropna(subset=["latitude", "longitude"])
    valid = valid[(valid["latitude"] != 0.0) & (valid["longitude"] != 0.0)]

    geometry = [Point(xy) for xy in zip(valid["longitude"], valid["latitude"])]
    gdf = gpd.GeoDataFrame(valid, geometry=geometry, crs="EPSG:4326")

    # Shapefile requires all files to have same base name
    gdf.to_file(base_path.with_suffix(".shp"), driver="ESRI Shapefile")
    logger.info("Wrote Shapefile: %s (%d features)", base_path.with_suffix(".shp"), len(gdf))
    return base_path.with_suffix(".shp")


def export_chunked_generator(
    frames: Iterable[pd.DataFrame],
    output_format: OutputFormat,
    output_dir: Path,
    output_stem: str,
    dataset_name: str,
    parquet_metadata: Mapping[str, str] | None = None,
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
            chunk.to_csv(
                path, mode="a" if chunk_count else "w", header=chunk_count == 0, index=False
            )
            chunk_count += 1
    else:
        import pyarrow as pa
        from pyarrow import parquet as pq

        writer: pq.ParquetWriter | None = None
        try:
            for chunk in frames:
                table = pa.Table.from_pandas(chunk)
                if writer is None:
                    schema = table.schema
                    if parquet_metadata:
                        schema = _merge_schema_metadata(schema, parquet_metadata)
                    writer = pq.ParquetWriter(path, schema)
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
    parquet_metadata: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Write generated datasets in the requested format.

    Returns a mapping keyed by dataset name: paths for file formats,
    frames for the in-memory pandas/polars formats, or ``{"bundle": path}``
    for the bundled JSON/YAML formats.

    Raises:
        ExportError: For formats without a writer here (database dialects
            go through :mod:`synth911gen3.db_exporter` instead).
    """
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
            _write_parquet_with_metadata(frame, path, parquet_metadata)
            artifacts[dataset_name] = path
            logger.info("Wrote parquet: %s", path)
        return artifacts

    if output_format is OutputFormat.GEOJSON:
        artifacts = {}
        for dataset_name, frame in datasets.items():
            if dataset_name == "incidents":  # Only incidents have coordinates
                path = export_geojson(frame, output_dir, output_stem, dataset_name)
                artifacts[dataset_name] = path
            else:
                # Export phone metrics as JSON
                path = output_dir / f"{output_stem}_{dataset_name}.json"
                payload = _records_for_serialization(frame)
                path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                artifacts[dataset_name] = path
                logger.info("Wrote JSON (non-spatial): %s", path)
        return artifacts

    if output_format is OutputFormat.SHAPEFILE:
        artifacts = {}
        for dataset_name, frame in datasets.items():
            if dataset_name == "incidents":
                path = export_shapefile(frame, output_dir, output_stem, dataset_name)
                artifacts[dataset_name] = path
            else:
                path = output_dir / f"{output_stem}_{dataset_name}.json"
                payload = _records_for_serialization(frame)
                path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                artifacts[dataset_name] = path
                logger.info("Wrote JSON (non-spatial): %s", path)
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


def export_manifest(
    manifest: Manifest,
    output_dir: Path,
    output_stem: str,
    output_format: OutputFormat,
) -> Path:
    """Write the data governance manifest as a JSON sidecar file."""
    return write_manifest(manifest, output_dir, output_stem, output_format)


_DATA_DICT_DIR = Path(__file__).resolve().parent.parent.parent / "docs"


def export_data_dictionary(
    output_dir: Path,
    datasets: dict[str, Any],
) -> list[Path]:
    """Copy data-dict YAML files for the generated datasets into *output_dir*.

    The data dictionaries are maintained in ``docs/`` and bundled alongside
    the generated data files so consumers can validate or browse the schema.
    Returns the list of paths written (empty if no matching dictionaries
    exist).
    """
    mapping = {
        "incidents": "incidents_data_dict.yaml",
        "hourly_call_counts": "phone_volume_data_dict.yaml",
    }
    written: list[Path] = []
    for dataset_name in datasets:
        filename = mapping.get(dataset_name)
        if filename is None:
            continue
        src = _DATA_DICT_DIR / filename
        if not src.is_file():
            logger.debug("Data dictionary not found, skipping: %s", src)
            continue
        dst = output_dir / filename
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        written.append(dst)
        logger.info("Wrote data dictionary: %s", dst)
    return written
