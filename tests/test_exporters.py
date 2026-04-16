from pathlib import Path
from typing import cast

import polars as pl

from synth911gen3.addresses import StaticAddressProvider
from synth911gen3.app import Synth911Application
from synth911gen3.config import DatasetKind, GenerationRequest, OutputFormat
from synth911gen3.domain import Address


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
    assert result.exported_artifacts["hourly_call_counts"] == tmp_path / "sample_hourly_call_counts.csv"
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
