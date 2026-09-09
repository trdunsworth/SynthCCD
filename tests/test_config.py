"""Tests for the GenerationRequest dataclass and its validation."""
from pathlib import Path

import pytest

from synth911gen3.config import (
    DatabaseDialect,
    DatasetKind,
    GenerationRequest,
    IdFormat,
    OutputFormat,
)
from synth911gen3.exceptions import ValidationError


def test_generation_request_defaults() -> None:
    request = GenerationRequest()

    # Rows default to "unspecified" (None) and resolve to 10,000 without
    # population, or derive from population when set.
    assert request.rows is None
    assert request.resolved_rows() == 10_000
    assert request.area_query == "Kansas City, MO"
    assert request.output_format is OutputFormat.CSV
    assert request.dataset is DatasetKind.INCIDENTS
    assert request.id_format is IdFormat.INTEGER
    assert request.output_stem == "synthetic_911"
    assert request.max_memory_bytes is None


@pytest.mark.parametrize("budget", [0, -5])
def test_max_memory_bytes_rejects_non_positive_values(budget: int) -> None:
    with pytest.raises(ValidationError):
        GenerationRequest(max_memory_bytes=budget).validate()


def test_max_memory_bytes_accepts_positive_value_and_none() -> None:
    GenerationRequest(max_memory_bytes=1_048_576).validate()
    GenerationRequest(max_memory_bytes=None).validate()


@pytest.mark.parametrize("id_format", [IdFormat.INTEGER, IdFormat.GUID])
def test_generation_request_accepts_id_formats(id_format: IdFormat) -> None:
    assert GenerationRequest(id_format=id_format).id_format is id_format


@pytest.mark.parametrize(
    "stem", [".", "..", "a/b", "a\\b", "CON", "con.csv", "NUL", "COM1", "aux", "has\x00null"]
)
def test_output_stem_rejects_unsafe_values(stem: str) -> None:
    with pytest.raises(ValidationError):
        GenerationRequest(output_stem=stem).validate()


@pytest.mark.parametrize(
    "output_dir", [Path("../outside"), Path("nested/../../escape"), Path("x\x00y")]
)
def test_output_dir_rejects_unsafe_values(output_dir: Path) -> None:
    with pytest.raises(ValidationError):
        GenerationRequest(output_dir=output_dir).validate()


def test_output_dir_accepts_normal_paths(tmp_path: Path) -> None:
    request = GenerationRequest(output_dir=tmp_path / "exports", output_stem="kc_911")
    request.validate()
    assert request.output_dir == tmp_path / "exports"


def test_sqlite_output_format_requires_no_connection_params() -> None:
    request = GenerationRequest(rows=10, output_format=OutputFormat.SQLITE)
    request.validate()
    assert request.db_name == "synthetic_911.sqlite3"
    assert request.db_port is None


def test_sqlite_default_name_uses_output_stem() -> None:
    request = GenerationRequest(
        rows=10,
        output_format=OutputFormat.SQLITE,
        output_stem="kc_cad",
    )
    request.validate()
    assert request.db_name == "kc_cad.sqlite3"


def test_sqlite_explicit_db_name_is_preserved() -> None:
    request = GenerationRequest(
        rows=10,
        output_format=OutputFormat.SQLITE,
        db_name="warehouse.db",
    )
    request.validate()
    assert request.db_name == "warehouse.db"


def test_sqlite_dialect_enum_values() -> None:
    assert DatabaseDialect.SQLITE.value == "sqlite"
    assert OutputFormat.SQLITE.value == "sqlite"


def test_sqlite_dialect_override_defaults_file_name() -> None:
    request = GenerationRequest(
        rows=10,
        output_format=OutputFormat.DUCKDB,
        db_dialect=DatabaseDialect.SQLITE,
        output_stem="mixed",
    )
    request.validate()
    assert request.db_name == "mixed.sqlite3"


def test_sqlite_rejects_invalid_if_exists() -> None:
    request = GenerationRequest(
        rows=10,
        output_format=OutputFormat.SQLITE,
        db_if_exists="drop",
    )
    with pytest.raises(ValidationError, match="db_if_exists must be"):
        request.validate()


def test_sqlite_rejects_non_positive_batch_size() -> None:
    request = GenerationRequest(
        rows=10,
        output_format=OutputFormat.SQLITE,
        db_batch_size=0,
    )
    with pytest.raises(ValidationError, match="db_batch_size must be greater"):
        request.validate()


# ---------------------------------------------------------------------------
# PSAP agency filter
# ---------------------------------------------------------------------------


def test_psap_agency_defaults_to_all() -> None:
    request = GenerationRequest()
    assert request.psap_agency == "all"


@pytest.mark.parametrize("agency", ["all", "law", "fire", "ems", "fire_ems"])
def test_psap_agency_accepts_valid_values(agency: str) -> None:
    request = GenerationRequest(psap_agency=agency)
    assert request.psap_agency == agency


@pytest.mark.parametrize(
    "agency", ["ALL", "Law", "FIRE_ems", "  all  "],
)
def test_psap_agency_normalizes_case_and_whitespace(agency: str) -> None:
    """Validation normalizes before checking — case/whitespace variants should be accepted."""
    request = GenerationRequest(psap_agency=agency)
    request.validate()  # should not raise


@pytest.mark.parametrize("agency", ["invalid", "both", "police", "law_and_fire"])
def test_psap_agency_rejects_invalid_values(agency: str) -> None:
    with pytest.raises(ValidationError):
        GenerationRequest(psap_agency=agency).validate()
