"""Tests for embedding generation metadata in Parquet file footers."""

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from synth911gen3.addresses import StaticAddressProvider
from synth911gen3.app import Synth911Application
from synth911gen3.config import DatasetKind, GenerationRequest, OutputFormat
from synth911gen3.constants import DATA_SCHEMA_VERSION
from synth911gen3.domain import Address
from synth911gen3.exporters import export_chunked_generator, export_generated_data
from synth911gen3.manifest import Manifest


def _provider() -> StaticAddressProvider:
    return StaticAddressProvider(
        [
            Address("101 N Main St", "Kansas City", "Missouri"),
            Address("204 E 12th St", "Kansas City", "Missouri"),
            Address("55 W 39th St", "Kansas City", "Missouri"),
            Address("777 S Broadway Blvd", "Kansas City", "Missouri"),
            Address("890 N Oak Trafficway", "Kansas City", "Missouri"),
        ]
    )


def _footer_metadata(path: Path) -> dict[str, str]:
    """Return the synth911 namespaced key-value metadata of a Parquet footer."""
    raw = pq.ParquetFile(path).metadata.metadata or {}
    return {k.decode(): v.decode() for k, v in raw.items() if k.decode().startswith("synth911:")}


METADATA = {
    "synth911:seed": "42",
    "synth911:schema_version": "1.1",
    "synth911:realism_config_hash": "abc123",
}


def test_export_generated_data_embeds_parquet_metadata(tmp_path: Path) -> None:
    frame = pd.DataFrame({"value": [1, 2]})

    artifacts = export_generated_data(
        datasets={"events": frame},
        output_format=OutputFormat.PARQUET,
        output_dir=tmp_path,
        output_stem="sample",
        parquet_metadata=METADATA,
    )

    meta = _footer_metadata(artifacts["events"])
    assert meta["synth911:seed"] == "42"
    assert meta["synth911:schema_version"] == DATA_SCHEMA_VERSION
    assert meta["synth911:realism_config_hash"] == "abc123"


def test_export_generated_data_parquet_without_metadata(tmp_path: Path) -> None:
    frame = pd.DataFrame({"value": [1, 2]})

    artifacts = export_generated_data(
        datasets={"events": frame},
        output_format=OutputFormat.PARQUET,
        output_dir=tmp_path,
        output_stem="sample",
    )

    assert _footer_metadata(artifacts["events"]) == {}
    assert pd.read_parquet(artifacts["events"]).equals(frame)


def test_export_generated_data_parquet_keeps_pandas_metadata(tmp_path: Path) -> None:
    """Without embedding, files still carry pyarrow's standard pandas metadata."""
    frame = pd.DataFrame({"value": [1, 2]})

    artifacts = export_generated_data(
        datasets={"events": frame},
        output_format=OutputFormat.PARQUET,
        output_dir=tmp_path,
        output_stem="sample",
        parquet_metadata=METADATA,
    )

    raw = pq.ParquetFile(artifacts["events"]).metadata.metadata or {}
    keys = {k.decode() for k in raw}
    assert "pandas" in keys
    assert "ARROW:schema" in keys


def test_chunked_parquet_embeds_metadata_across_chunks(tmp_path: Path) -> None:
    chunks = [pd.DataFrame({"a": [i, i + 1]}) for i in range(0, 6, 2)]

    path = export_chunked_generator(
        iter(chunks),
        output_format=OutputFormat.PARQUET,
        output_dir=tmp_path,
        output_stem="sample",
        dataset_name="incidents",
        parquet_metadata=METADATA,
    )

    meta = _footer_metadata(path)
    assert meta["synth911:seed"] == "42"
    assert meta["synth911:schema_version"] == DATA_SCHEMA_VERSION
    assert len(pd.read_parquet(path)) == 6


def test_chunked_parquet_without_metadata(tmp_path: Path) -> None:
    path = export_chunked_generator(
        iter([pd.DataFrame({"a": [1, 2]})]),
        output_format=OutputFormat.PARQUET,
        output_dir=tmp_path,
        output_stem="sample",
        dataset_name="incidents",
    )

    assert _footer_metadata(path) == {}


def test_app_parquet_export_embeds_manifest_metadata(tmp_path: Path) -> None:
    request = GenerationRequest(
        rows=25,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PARQUET,
        output_dir=tmp_path,
        output_stem="sample",
        seed=4242,
    )

    result = Synth911Application(address_provider=_provider()).generate(request)

    path = result.exported_artifacts["incidents"]
    meta = _footer_metadata(path)

    assert meta["synth911:seed"] == "4242"
    assert meta["synth911:schema_version"] == DATA_SCHEMA_VERSION
    assert meta["synth911:dataset"] == "incidents"
    assert meta["synth911:rows_requested"] == "25"
    assert "synth911:realism_config_hash" in meta
    assert "synth911:schema_hash" in meta
    # row/column counts stay in the sidecar manifest, not the footer
    assert "synth911:row_counts" not in meta
    assert "synth911:column_counts" not in meta


def test_app_chunked_parquet_embeds_metadata(tmp_path: Path) -> None:
    request = GenerationRequest(
        rows=40,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PARQUET,
        output_dir=tmp_path,
        output_stem="sample",
        seed=22,
        max_memory_bytes=1,
    )

    result = Synth911Application(address_provider=_provider()).generate(request)

    assert result.incidents is None  # streamed, not materialized
    meta = _footer_metadata(result.exported_artifacts["incidents"])
    assert meta["synth911:seed"] == "22"
    assert meta["synth911:schema_version"] == DATA_SCHEMA_VERSION
    assert meta["synth911:schema_hash"]  # derived from the first chunk
    assert len(pd.read_parquet(result.exported_artifacts["incidents"])) == 40


def test_app_parquet_metadata_matches_sidecar_manifest(tmp_path: Path) -> None:
    request = GenerationRequest(
        rows=25,
        dataset=DatasetKind.ALL,
        output_format=OutputFormat.PARQUET,
        output_dir=tmp_path,
        output_stem="sample",
        seed=7,
    )

    result = Synth911Application(address_provider=_provider()).generate(request)

    manifest_path = result.exported_artifacts["manifest"]
    import json

    with manifest_path.open() as fh:
        sidecar_data = json.load(fh)

    incidents_meta = _footer_metadata(result.exported_artifacts["incidents"])
    phone_meta = _footer_metadata(result.exported_artifacts["hourly_call_counts"])

    for key in ("seed", "schema_version", "realism_config_hash", "schema_hash"):
        assert incidents_meta[f"synth911:{key}"] == str(sidecar_data[key])
        assert phone_meta[f"synth911:{key}"] == str(sidecar_data[key])
    assert incidents_meta == phone_meta


def test_manifest_to_kv_metadata_flattening() -> None:
    request = GenerationRequest(
        rows=10,
        dataset=DatasetKind.ALL,
        output_format=OutputFormat.PARQUET,
        output_dir=Path("unused"),
        output_stem="sample",
        seed=5,
    )
    frame = pd.DataFrame({"value": [1, 2]})
    manifest = Manifest.from_request(request, {"events": frame})

    kv = manifest.to_kv_metadata()

    assert kv["synth911:seed"] == "5"
    assert kv["synth911:schema_version"] == DATA_SCHEMA_VERSION
    assert kv["synth911:datasets_generated"] == '["events"]'
    # None values are dropped
    assert "synth911:start_date" not in kv
    # dataset-dependent counts stay out of the footer metadata
    assert "synth911:row_counts" not in kv
    assert "synth911:column_counts" not in kv
    # every value is a plain string
    assert all(isinstance(v, str) for v in kv.values())
