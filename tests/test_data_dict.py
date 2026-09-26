"""Integration tests: validate generated data against data-dict.yaml schemas."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from synth911gen3.addresses import StaticAddressProvider
from synth911gen3.app import Synth911Application
from synth911gen3.config import DatasetKind, GenerationRequest, OutputFormat
from synth911gen3.domain import Address

_DOCS = Path(__file__).resolve().parent.parent / "docs"

_DATA_DICT_BIN = shutil.which("data-dict")
if _DATA_DICT_BIN is None:
    pytest.skip("data-dict CLI not found on PATH", allow_module_level=True)

_PROVIDER = StaticAddressProvider(
    [
        Address("101 N Main St", "Kansas City", "Missouri"),
        Address("204 E 12th St", "Kansas City", "Missouri"),
        Address("55 W 39th St", "Kansas City", "Missouri"),
        Address("777 S Broadway Blvd", "Kansas City", "Missouri"),
        Address("890 N Oak Trafficway", "Kansas City", "Missouri"),
    ]
)


def _run_data_dict(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Invoke ``data-dict`` and return the result."""
    return subprocess.run(
        [_DATA_DICT_BIN, *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# Spec-only validation (no data files required)
# ---------------------------------------------------------------------------


class TestDataDictSpecValidation:
    def test_incidents_spec_valid(self) -> None:
        result = _run_data_dict(
            ["validate-spec", str(_DOCS / "incidents_data_dict.yaml"), "--json"]
        )
        payload = json.loads(result.stdout)
        assert payload["status"] == "ok", payload.get("problems")

    def test_phone_volume_spec_valid(self) -> None:
        result = _run_data_dict(
            ["validate-spec", str(_DOCS / "phone_volume_data_dict.yaml"), "--json"]
        )
        payload = json.loads(result.stdout)
        assert payload["status"] == "ok", payload.get("problems")


# ---------------------------------------------------------------------------
# Data validation (generate parquet, then validate)
# ---------------------------------------------------------------------------


def _generate_parquet(
    tmp_path: Path,
    dataset: DatasetKind,
    stem: str = "test",
) -> None:
    """Generate a small Parquet export into *tmp_path*."""
    request = GenerationRequest(
        rows=25,
        dataset=dataset,
        output_format=OutputFormat.PARQUET,
        output_dir=tmp_path,
        output_stem=stem,
        seed=42,
    )
    Synth911Application(address_provider=_PROVIDER).generate(request)


def _prepare_dict(
    tmp_path: Path,
    dict_name: str,
    parquet_src: str,
    parquet_dst: str,
) -> Path:
    """Copy a data-dict YAML and its matching parquet into *tmp_path*.

    Returns the path to the copied YAML.
    """
    yaml_src = _DOCS / dict_name
    yaml_dst = tmp_path / dict_name
    shutil.copy2(yaml_src, yaml_dst)

    src_parquet = tmp_path / parquet_src
    dst_parquet = tmp_path / parquet_dst
    if src_parquet.exists() and src_parquet != dst_parquet:
        shutil.copy2(src_parquet, dst_parquet)

    return yaml_dst


class TestDataDictDataValidation:
    def test_incidents_data_valid(self, tmp_path: Path) -> None:
        _generate_parquet(tmp_path, DatasetKind.INCIDENTS)
        yaml_path = _prepare_dict(
            tmp_path,
            "incidents_data_dict.yaml",
            "test_incidents.parquet",
            "incidents.parquet",
        )
        result = _run_data_dict(
            ["validate-data", str(yaml_path), "--json"]
        )
        payload = json.loads(result.stdout)
        problems = [
            step["problem"]
            for table in payload.get("tables", [])
            for step in table.get("steps", [])
            if step.get("problem")
        ]
        assert payload.get("status") == "ok" or not problems, problems

    def test_phone_volume_data_valid(self, tmp_path: Path) -> None:
        _generate_parquet(tmp_path, DatasetKind.PHONE)
        yaml_path = _prepare_dict(
            tmp_path,
            "phone_volume_data_dict.yaml",
            "test_hourly_call_counts.parquet",
            "phone_volume.parquet",
        )
        result = _run_data_dict(
            ["validate-data", str(yaml_path), "--json"]
        )
        payload = json.loads(result.stdout)
        problems = [
            step["problem"]
            for table in payload.get("tables", [])
            for step in table.get("steps", [])
            if step.get("problem")
        ]
        assert payload.get("status") == "ok" or not problems, problems

    def test_validate_meta_incidents(self, tmp_path: Path) -> None:
        _generate_parquet(tmp_path, DatasetKind.INCIDENTS)
        yaml_path = _prepare_dict(
            tmp_path,
            "incidents_data_dict.yaml",
            "test_incidents.parquet",
            "incidents.parquet",
        )
        result = _run_data_dict(
            ["validate-meta", str(yaml_path), "--json"]
        )
        payload = json.loads(result.stdout)
        problems = [
            step["problem"]
            for table in payload.get("tables", [])
            for step in table.get("steps", [])
            if step.get("problem")
        ]
        assert payload.get("status") == "ok" or not problems, problems
