"""Unit tests for the shared validation rules in :mod:`synth911gen3.validation`."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from synth911gen3.constants import DatabaseDialect, OutputFormat
from synth911gen3.validation import (
    WINDOWS_RESERVED_NAMES,
    normalize_psap_agency,
    resolve_database_options,
    validate_date_range,
    validate_output_dir,
    validate_output_stem,
)


class TestValidateOutputStem:
    """validate_output_stem: empty/reserved/traversing stems are rejected."""

    @pytest.mark.parametrize("stem", ["synthetic_911", "kc.cad", "run-2026", "a"])
    def test_accepts_safe_stems(self, stem: str) -> None:
        validate_output_stem(stem)

    @pytest.mark.parametrize("stem", ["", "   ", "\t"])
    def test_rejects_empty_or_whitespace(self, stem: str) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            validate_output_stem(stem)

    @pytest.mark.parametrize("stem", [".", ".."])
    def test_rejects_dot_stems(self, stem: str) -> None:
        with pytest.raises(ValueError, match=r"'\.' or '\.\.'"):
            validate_output_stem(stem)

    @pytest.mark.parametrize("stem", ["a/b", "a\\b", "dir/name", "has\x00null"])
    def test_rejects_separators_and_null_bytes(self, stem: str) -> None:
        with pytest.raises(ValueError, match="path separators or null bytes"):
            validate_output_stem(stem)

    @pytest.mark.parametrize(
        "stem", ["CON", "con", "PRN", "AUX", "NUL", "COM1", "com9", "LPT1", "lpt9"]
    )
    def test_rejects_reserved_device_names(self, stem: str) -> None:
        with pytest.raises(ValueError, match="reserved device name"):
            validate_output_stem(stem)

    @pytest.mark.parametrize("stem", ["con.csv", "NUL.backup", "COM3.tar.gz"])
    def test_rejects_reserved_names_with_extensions(self, stem: str) -> None:
        with pytest.raises(ValueError, match="reserved device name"):
            validate_output_stem(stem)

    def test_reserved_names_constant_contents(self) -> None:
        assert WINDOWS_RESERVED_NAMES == {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }


class TestValidateOutputDir:
    """validate_output_dir: null bytes and ``..`` segments are rejected."""

    def test_accepts_normal_paths(self, tmp_path: Path) -> None:
        validate_output_dir(tmp_path / "exports")
        validate_output_dir(Path("output"))
        validate_output_dir(Path("."))

    def test_rejects_null_bytes(self) -> None:
        with pytest.raises(ValueError, match="null bytes"):
            validate_output_dir(Path("x\x00y"))

    @pytest.mark.parametrize(
        "directory", [Path("../outside"), Path("nested/../../escape"), Path("a/../b")]
    )
    def test_rejects_parent_segments(self, directory: Path) -> None:
        with pytest.raises(ValueError, match=r"'\.\.' path segments"):
            validate_output_dir(directory)


class TestNormalizePsapAgency:
    """normalize_psap_agency: normalizes case/whitespace, rejects unknown values."""

    @pytest.mark.parametrize("value", ["all", "law", "fire", "ems", "fire_ems"])
    def test_accepts_valid_values(self, value: str) -> None:
        assert normalize_psap_agency(value) == value

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("ALL", "all"),
            ("Law", "law"),
            ("FIRE_ems", "fire_ems"),
            ("  all  ", "all"),
            (" EMS ", "ems"),
        ],
    )
    def test_normalizes_case_and_whitespace(self, raw: str, expected: str) -> None:
        assert normalize_psap_agency(raw) == expected

    @pytest.mark.parametrize("value", ["invalid", "both", "police", "law_and_fire", ""])
    def test_rejects_unknown_values(self, value: str) -> None:
        with pytest.raises(ValueError, match="Unknown psap_agency"):
            normalize_psap_agency(value)


class TestValidateDateRange:
    """validate_date_range: inverted ranges are rejected."""

    def test_accepts_ordered_range(self) -> None:
        validate_date_range(date(2026, 1, 1), date(2026, 12, 31))
        validate_date_range(date(2026, 6, 1), date(2026, 6, 1))

    def test_rejects_inverted_range(self) -> None:
        with pytest.raises(ValueError, match="start_date must be on or before end_date"):
            validate_date_range(date(2026, 12, 31), date(2026, 1, 1))


class TestResolveDatabaseOptions:
    """resolve_database_options: no-ops for file formats, defaults/validates DB options."""

    @pytest.mark.parametrize(
        "output_format",
        [OutputFormat.CSV, OutputFormat.PARQUET, OutputFormat.JSON, OutputFormat.PANDAS],
    )
    def test_noop_for_non_database_formats(self, output_format: OutputFormat) -> None:
        updates = resolve_database_options(
            output_format=output_format,
            db_dialect=None,
            output_stem="run",
            db_name=None,
            db_host=None,
            db_port=None,
            db_user=None,
            db_if_exists="append",
            db_batch_size=10000,
        )
        assert updates == {}

    def test_sqlite_defaults_name_from_stem(self) -> None:
        updates = resolve_database_options(
            output_format=OutputFormat.SQLITE,
            db_dialect=None,
            output_stem="synthetic_911",
            db_name=None,
            db_host=None,
            db_port=None,
            db_user=None,
            db_if_exists="append",
            db_batch_size=10000,
        )
        assert updates == {"db_name": "synthetic_911.sqlite3"}

    def test_duckdb_defaults_name_from_stem(self) -> None:
        updates = resolve_database_options(
            output_format=OutputFormat.DUCKDB,
            db_dialect=None,
            output_stem="run",
            db_name=None,
            db_host=None,
            db_port=None,
            db_user=None,
            db_if_exists="append",
            db_batch_size=10000,
        )
        assert updates == {"db_name": "run.duckdb"}

    def test_file_dialect_preserves_explicit_name(self) -> None:
        updates = resolve_database_options(
            output_format=OutputFormat.SQLITE,
            db_dialect=None,
            output_stem="run",
            db_name="warehouse.db",
            db_host=None,
            db_port=None,
            db_user=None,
            db_if_exists="append",
            db_batch_size=10000,
        )
        assert updates == {}

    def test_explicit_dialect_overrides_output_format(self) -> None:
        updates = resolve_database_options(
            output_format=OutputFormat.DUCKDB,
            db_dialect=DatabaseDialect.SQLITE,
            output_stem="mixed",
            db_name=None,
            db_host=None,
            db_port=None,
            db_user=None,
            db_if_exists="append",
            db_batch_size=10000,
        )
        assert updates == {"db_name": "mixed.sqlite3"}

    @pytest.mark.parametrize(
        ("output_format", "port"),
        [
            (OutputFormat.POSTGRESQL, 5432),
            (OutputFormat.SQLSERVER, 1433),
            (OutputFormat.MARIADB, 3306),
        ],
    )
    def test_server_dialects_default_port(
        self, output_format: OutputFormat, port: int
    ) -> None:
        updates = resolve_database_options(
            output_format=output_format,
            db_dialect=None,
            output_stem="run",
            db_name="cad",
            db_host="localhost",
            db_port=None,
            db_user="user",
            db_if_exists="append",
            db_batch_size=10000,
        )
        assert updates == {"db_port": port}

    def test_server_dialect_preserves_explicit_port(self) -> None:
        updates = resolve_database_options(
            output_format=OutputFormat.POSTGRESQL,
            db_dialect=None,
            output_stem="run",
            db_name="cad",
            db_host="localhost",
            db_port=5433,
            db_user="user",
            db_if_exists="append",
            db_batch_size=10000,
        )
        assert updates == {}

    @pytest.mark.parametrize("missing_field", ["db_host", "db_name", "db_user"])
    def test_server_dialects_require_connection_params(self, missing_field: str) -> None:
        params = {
            "output_format": OutputFormat.POSTGRESQL,
            "db_dialect": None,
            "output_stem": "run",
            "db_name": "cad",
            "db_host": "localhost",
            "db_port": None,
            "db_user": "user",
            "db_if_exists": "append",
            "db_batch_size": 10000,
        }
        params[missing_field] = None
        with pytest.raises(ValueError, match=f"{missing_field} is required"):
            resolve_database_options(**params)

    @pytest.mark.parametrize("bad", ["drop", "invalid", "", "Upsert"])
    def test_rejects_invalid_if_exists(self, bad: str) -> None:
        with pytest.raises(ValueError, match="db_if_exists must be"):
            resolve_database_options(
                output_format=OutputFormat.SQLITE,
                db_dialect=None,
                output_stem="run",
                db_name=None,
                db_host=None,
                db_port=None,
                db_user=None,
                db_if_exists=bad,
                db_batch_size=10000,
            )

    @pytest.mark.parametrize("size", [0, -5])
    def test_rejects_non_positive_batch_size(self, size: int) -> None:
        with pytest.raises(ValueError, match="db_batch_size must be greater"):
            resolve_database_options(
                output_format=OutputFormat.POSTGRESQL,
                db_dialect=None,
                output_stem="run",
                db_name="cad",
                db_host="localhost",
                db_port=None,
                db_user="user",
                db_if_exists="append",
                db_batch_size=size,
            )
