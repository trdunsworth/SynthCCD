import pandas as pd

from synth911gen3.config import DatasetKind, GenerationRequest, IdFormat
from synth911gen3.describe import SCHEMA_ROWS, SAMPLE_ROWS, build_preview_datasets


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
    assert set(build_preview_datasets(_request(DatasetKind.INCIDENTS), schema_only=True)) == {"incidents"}
    assert set(build_preview_datasets(_request(DatasetKind.PHONE), schema_only=True)) == {"hourly_call_counts"}
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
