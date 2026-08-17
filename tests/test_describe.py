"""Tests for schema/preview builders used by --schema, --dry-run, and the API."""
import pandas as pd

from synth911gen3.config import DatasetKind, GenerationRequest, IdFormat
from synth911gen3.describe import (
    SAMPLE_ROWS,
    SCHEMA_ROWS,
    build_preview_datasets,
    build_schema_definition,
)


def _request(dataset: DatasetKind = DatasetKind.ALL, **kwargs) -> GenerationRequest:
    return GenerationRequest(dataset=dataset, **kwargs)


def test_schema_only_builds_single_incident_row() -> None:
    preview = build_preview_datasets(_request(DatasetKind.INCIDENTS), schema_only=True)

    assert set(preview) == {"incidents"}
    frame = preview["incidents"]
    assert len(frame) == SCHEMA_ROWS
    assert {
        "id_number",
        "internal_reference_number",
        "agency",
        "call_start_time",
        "calltaker",
        "call_disposition",
        "total_elapsed_seconds",
    }.issubset(frame.columns)


def test_dry_run_builds_sample_rows() -> None:
    preview = build_preview_datasets(_request(DatasetKind.INCIDENTS), schema_only=False)

    assert len(preview["incidents"]) == SAMPLE_ROWS


def test_preview_phone_metrics_restricted_to_single_day() -> None:
    preview = build_preview_datasets(_request(DatasetKind.PHONE), schema_only=True)

    assert set(preview) == {"hourly_call_counts"}
    frame = preview["hourly_call_counts"]
    assert set(frame["hour_start"].dt.date.unique()) == {frame["hour_start"].iloc[0].date()}
    assert len(frame) == 24


def test_preview_respects_dataset_selection() -> None:
    assert set(build_preview_datasets(_request(DatasetKind.INCIDENTS), schema_only=True)) == {
        "incidents"
    }
    assert set(build_preview_datasets(_request(DatasetKind.PHONE), schema_only=True)) == {
        "hourly_call_counts"
    }
    assert set(build_preview_datasets(_request(DatasetKind.ALL), schema_only=True)) == {
        "incidents",
        "hourly_call_counts",
    }


def test_preview_guid_id_format_is_not_integer() -> None:
    preview = build_preview_datasets(
        _request(DatasetKind.INCIDENTS, id_format=IdFormat.GUID), schema_only=True
    )
    assert not pd.api.types.is_integer_dtype(preview["incidents"]["id_number"])


def test_preview_integer_id_format_is_integer() -> None:
    preview = build_preview_datasets(
        _request(DatasetKind.INCIDENTS, id_format=IdFormat.INTEGER), schema_only=True
    )
    assert pd.api.types.is_integer_dtype(preview["incidents"]["id_number"])


def test_preview_is_deterministic_for_same_seed() -> None:
    request = _request(DatasetKind.INCIDENTS, seed=77)

    first = build_preview_datasets(request, schema_only=False)["incidents"]
    second = build_preview_datasets(request, schema_only=False)["incidents"]

    assert first.equals(second)


def test_schema_definition_incidents_shape() -> None:
    definition = build_schema_definition(_request(DatasetKind.INCIDENTS))

    assert definition["dataset"] == "incidents"
    assert definition["version"] == "1.1"
    assert definition["schema_hash"]
    assert set(definition["datasets"]) == {"incidents"}
    columns = definition["datasets"]["incidents"]
    assert columns["id_number"] == "int64"
    assert "agency" in columns


def test_schema_definition_phone_shape() -> None:
    definition = build_schema_definition(_request(DatasetKind.PHONE))

    assert set(definition["datasets"]) == {"hourly_call_counts"}
    columns = definition["datasets"]["hourly_call_counts"]
    assert "hour_start" in columns
    assert "nine_one_one_calls_received" in columns


def test_schema_definition_respects_id_format() -> None:
    definition = build_schema_definition(
        _request(DatasetKind.INCIDENTS, id_format=IdFormat.GUID)
    )
    assert definition["datasets"]["incidents"]["id_number"] != "int64"


def test_schema_definition_hash_is_deterministic() -> None:
    first = build_schema_definition(_request(DatasetKind.INCIDENTS))
    second = build_schema_definition(_request(DatasetKind.INCIDENTS))
    assert first["schema_hash"] == second["schema_hash"]
