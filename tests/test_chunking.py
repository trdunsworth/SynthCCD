from pathlib import Path

import pandas as pd
import pytest

from synth911gen3.addresses import StaticAddressProvider
from synth911gen3.app import Synth911Application
from synth911gen3.config import DatasetKind, GenerationRequest, IdFormat, OutputFormat
from synth911gen3.domain import Address
from synth911gen3.generators.incidents import IncidentGenerator


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


def _request(
    rows: int,
    *,
    seed: int = 911,
    chunk_rows: int | None = None,
    max_memory_bytes: int | None = None,
    id_format: IdFormat = IdFormat.INTEGER,
) -> GenerationRequest:
    request = GenerationRequest(
        rows=rows,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        seed=seed,
        id_format=id_format,
    )
    if chunk_rows is not None:
        request.max_memory_bytes = 1  # forces one row per chunk regardless of bytes/row
    if max_memory_bytes is not None:
        request.max_memory_bytes = max_memory_bytes
    return request


def test_generate_chunks_single_chunk_equals_generate() -> None:
    provider = _provider()
    request = _request(rows=40, seed=17)

    single = IncidentGenerator(provider).generate(request)
    chunked = pd.concat(
        list(IncidentGenerator(provider).generate_chunks(request, chunk_rows=request.rows))
    )

    assert chunked.equals(single)


def test_generate_chunks_yields_multiple_chunks_covering_all_rows() -> None:
    provider = _provider()
    request = _request(rows=50, seed=3, chunk_rows=7)

    chunks = list(IncidentGenerator(provider).generate_chunks(request, chunk_rows=7))

    assert len(chunks) > 1
    assert sum(len(chunk) for chunk in chunks) == 50
    assert all(1 <= len(chunk) <= 7 for chunk in chunks)
    assert all(set(chunk.columns) == set(chunks[0].columns) for chunk in chunks)


def test_generate_chunks_id_numbers_stay_globally_sequential() -> None:
    provider = _provider()
    request = _request(rows=50, seed=5, chunk_rows=6)

    ids = pd.concat(
        list(IncidentGenerator(provider).generate_chunks(request, chunk_rows=6))
    )["id_number"].tolist()

    assert sorted(ids) == list(range(1, 51))


def test_generate_chunks_guid_ids_unique_across_chunks() -> None:
    provider = _provider()
    request = _request(rows=30, seed=8, chunk_rows=5, id_format=IdFormat.GUID)

    ids = pd.concat(
        list(IncidentGenerator(provider).generate_chunks(request, chunk_rows=5))
    )["id_number"].tolist()

    assert len(ids) == len(set(ids)) == 30


def test_generate_chunks_reference_numbers_unique_per_agency() -> None:
    provider = _provider()
    request = _request(rows=60, seed=11, chunk_rows=4)

    frame = pd.concat(
        list(IncidentGenerator(provider).generate_chunks(request, chunk_rows=4))
    )

    for _, group in frame.groupby("agency"):
        assert group["internal_reference_number"].nunique() == len(group), (
            "internal_reference_number must stay unique per agency across chunks"
        )


def test_generate_chunks_is_deterministic_for_same_seed() -> None:
    provider = _provider()

    def run() -> pd.DataFrame:
        request = _request(rows=60, seed=42, chunk_rows=5)
        return pd.concat(
            list(IncidentGenerator(provider).generate_chunks(request, chunk_rows=5))
        )

    assert run().equals(run())


def test_generate_chunks_reports_monotonic_progress() -> None:
    provider = _provider()
    request = _request(rows=40, seed=13, chunk_rows=6)
    updates: list[tuple[int, int]] = []

    for _ in IncidentGenerator(provider).generate_chunks(
        request, chunk_rows=6, on_progress=lambda done, total: updates.append((done, total))
    ):
        pass

    assert updates
    assert updates[-1] == (40, 40)
    assert updates == sorted(updates)


def test_resolve_chunk_rows_respects_memory_budget() -> None:
    provider = _provider()
    request = _request(rows=100_000, max_memory_bytes=64 * 1024)
    gen = IncidentGenerator(provider)

    chunk_rows = gen.resolve_chunk_rows(request)

    assert 0 < chunk_rows < 100_000


def test_resolve_chunk_rows_returns_rows_without_budget() -> None:
    provider = _provider()
    request = _request(rows=200)
    gen = IncidentGenerator(provider)

    chunk_rows = gen.resolve_chunk_rows(request)

    assert chunk_rows == 200


def test_app_streams_csv_when_budget_exceeded(tmp_path: Path) -> None:
    request = GenerationRequest(
        rows=40,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.CSV,
        output_dir=tmp_path,
        output_stem="sample",
        seed=21,
        max_memory_bytes=1,
    )

    result = Synth911Application(address_provider=_provider()).generate(request)

    assert result.incidents is None
    path = result.exported_artifacts["incidents"]
    assert path == tmp_path / "sample_incidents.csv"
    written = pd.read_csv(path)
    assert len(written) == 40
    assert written["id_number"].tolist() == list(range(1, 41))


def test_app_streams_parquet_when_budget_exceeded(tmp_path: Path) -> None:
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

    assert result.incidents is None
    path = result.exported_artifacts["incidents"]
    assert path == tmp_path / "sample_incidents.parquet"
    written = pd.read_parquet(path)
    assert len(written) == 40
    assert written["id_number"].tolist() == list(range(1, 41))


def test_app_chunked_parquet_matches_generated_chunks(tmp_path: Path) -> None:
    request = GenerationRequest(
        rows=30,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PARQUET,
        output_dir=tmp_path,
        output_stem="sample",
        seed=23,
        max_memory_bytes=1,
    )
    provider = _provider()

    Synth911Application(address_provider=provider).generate(request)

    written = pd.read_parquet(tmp_path / "sample_incidents.parquet")
    chunks = pd.concat(
        list(IncidentGenerator(provider).generate_chunks(request, chunk_rows=1))
    )
    assert list(written.columns) == list(chunks.columns)
    assert len(written) == len(chunks)
    assert written["internal_reference_number"].tolist() == chunks[
        "internal_reference_number"
    ].tolist()


def test_app_non_chunked_csv_keeps_incidents_in_result(tmp_path: Path) -> None:
    request = GenerationRequest(
        rows=15,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.CSV,
        output_dir=tmp_path,
        output_stem="sample",
        seed=24,
    )

    result = Synth911Application(address_provider=_provider()).generate(request)

    assert result.incidents is not None
    assert len(result.incidents) == 15
    assert (tmp_path / "sample_incidents.csv").exists()
    assert len(pd.read_csv(tmp_path / "sample_incidents.csv")) == 15


def test_app_streaming_all_datasets_exports_both_files(tmp_path: Path) -> None:
    request = GenerationRequest(
        rows=30,
        dataset=DatasetKind.ALL,
        output_format=OutputFormat.CSV,
        output_dir=tmp_path,
        output_stem="sample",
        seed=25,
        max_memory_bytes=1,
    )

    result = Synth911Application(address_provider=_provider()).generate(request)

    assert result.incidents is None
    assert (tmp_path / "sample_incidents.csv").exists()
    assert (tmp_path / "sample_hourly_call_counts.csv").exists()
    assert len(pd.read_csv(tmp_path / "sample_incidents.csv")) == 30


@pytest.mark.parametrize("budget", [0, -1])
def test_generation_request_rejects_non_positive_budget(budget: int) -> None:
    from synth911gen3.exceptions import ValidationError

    with pytest.raises(ValidationError):
        GenerationRequest(max_memory_bytes=budget).validate()


def test_generation_request_accepts_positive_budget() -> None:
    GenerationRequest(max_memory_bytes=1_048_576).validate()
