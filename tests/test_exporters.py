import json
from pathlib import Path
from typing import cast

import pandas as pd
import polars as pl
import pytest
import yaml

from synth911gen3.addresses import StaticAddressProvider
from synth911gen3.app import Synth911Application
from synth911gen3.config import DatasetKind, GenerationRequest, OutputFormat
from synth911gen3.domain import Address
from synth911gen3.exceptions import ExportError
from synth911gen3.exporters import export_chunked_generator, export_generated_data


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


def test_csv_export_writes_expected_output_files(tmp_path: Path) -> None:
    request = GenerationRequest(
        rows=10,
        dataset=DatasetKind.ALL,
        output_format=OutputFormat.CSV,
        output_dir=tmp_path,
        output_stem="sample",
        seed=4321,
    )

    result = Synth911Application(address_provider=_provider()).generate(request)

    assert result.exported_artifacts["incidents"] == tmp_path / "sample_incidents.csv"
    assert (
        result.exported_artifacts["hourly_call_counts"]
        == tmp_path / "sample_hourly_call_counts.csv"
    )
    assert (tmp_path / "sample_incidents.csv").exists()
    assert (tmp_path / "sample_hourly_call_counts.csv").exists()


def test_polars_export_returns_polars_frames() -> None:
    request = GenerationRequest(
        rows=5,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.POLARS,
        seed=9876,
    )

    result = Synth911Application(address_provider=_provider()).generate(request)

    incidents = cast(pl.DataFrame, result.exported_artifacts["incidents"])
    assert incidents.__class__.__module__.startswith("polars")
    assert incidents.height == 5


def test_json_export_writes_bundle_and_serializes_datetimes(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {
            "value": [1, 2],
            "at": pd.to_datetime(["2024-01-01T08:00:00", "2024-01-02T09:30:15"]),
        }
    )

    artifacts = export_generated_data(
        datasets={"events": frame},
        output_format=OutputFormat.JSON,
        output_dir=tmp_path,
        output_stem="sample",
    )

    assert artifacts == {"bundle": tmp_path / "sample_bundle.json"}
    payload = json.loads((tmp_path / "sample_bundle.json").read_text(encoding="utf-8"))
    assert payload["events"][0]["at"] == "2024-01-01T08:00:00"
    assert payload["events"][1]["value"] == 2


def test_yaml_export_writes_bundle(tmp_path: Path) -> None:
    frame = pd.DataFrame({"value": [1, 2]})

    artifacts = export_generated_data(
        datasets={"events": frame},
        output_format=OutputFormat.YAML,
        output_dir=tmp_path,
        output_stem="sample",
    )

    assert artifacts == {"bundle": tmp_path / "sample_bundle.yaml"}
    payload = yaml.safe_load((tmp_path / "sample_bundle.yaml").read_text(encoding="utf-8"))
    assert payload == {"events": [{"value": 1}, {"value": 2}]}


def test_pandas_export_returns_frames_unmodified() -> None:
    frame = pd.DataFrame({"value": [1, 2]})

    artifacts = export_generated_data(
        datasets={"events": frame},
        output_format=OutputFormat.PANDAS,
        output_dir=Path("unused"),
        output_stem="sample",
    )

    assert artifacts == {"events": frame}


def test_parquet_export_writes_files(tmp_path: Path) -> None:
    frame = pd.DataFrame({"value": [1, 2]})

    artifacts = export_generated_data(
        datasets={"events": frame},
        output_format=OutputFormat.PARQUET,
        output_dir=tmp_path,
        output_stem="sample",
    )

    assert artifacts == {"events": tmp_path / "sample_events.parquet"}
    assert pd.read_parquet(tmp_path / "sample_events.parquet").equals(frame)


def test_chunked_export_rejects_unsupported_format(tmp_path: Path) -> None:
    with pytest.raises(ExportError, match="only supports CSV and PARQUET"):
        export_chunked_generator(
            iter(()),
            output_format=OutputFormat.JSON,
            output_dir=tmp_path,
            output_stem="sample",
            dataset_name="incidents",
        )
