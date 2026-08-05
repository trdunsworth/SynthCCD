from datetime import date
from pathlib import Path
import re

import pytest
import typer
from typer.testing import CliRunner

from synth911gen3.cli import _coerce_param, app, build_request_from_params, load_params_file
from synth911gen3.config import DatasetKind, OutputFormat

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_load_params_file_json(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "params.json",
        '{"rows": 500, "area": "Denver, CO", "format": "parquet", "dataset": "phone"}',
    )
    data = load_params_file(path)
    assert data == {
        "rows": 500,
        "area_query": "Denver, CO",
        "output_format": "parquet",
        "dataset": "phone",
    }


def test_load_params_file_yaml(tmp_path: Path) -> None:
    path = _write(tmp_path, "params.yaml", "rows: 100\ndataset: incidents\nseed: 7\n")
    assert load_params_file(path) == {"rows": 100, "dataset": "incidents", "seed": 7}


def test_load_params_file_toml(tmp_path: Path) -> None:
    path = _write(tmp_path, "params.toml", 'rows = 100\ndataset = "incidents"\n')
    assert load_params_file(path) == {"rows": 100, "dataset": "incidents"}


def test_load_params_file_canonical_keys_win_over_aliases(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "params.json",
        '{"area": "Seattle, WA", "area_query": "Portland, OR"}',
    )
    assert load_params_file(path) == {"area_query": "Portland, OR"}


def test_load_params_file_unsupported_extension(tmp_path: Path) -> None:
    path = _write(tmp_path, "params.txt", "rows: 100")
    with pytest.raises(typer.BadParameter):
        load_params_file(path)


def test_load_params_file_invalid_json(tmp_path: Path) -> None:
    path = _write(tmp_path, "params.json", "{not valid json")
    with pytest.raises(typer.BadParameter):
        load_params_file(path)


def test_load_params_file_non_mapping(tmp_path: Path) -> None:
    path = _write(tmp_path, "params.json", '[1, 2, 3]')
    with pytest.raises(typer.BadParameter):
        load_params_file(path)


def test_build_request_merges_file_and_cli(tmp_path: Path) -> None:
    file_params = {
        "rows": 500,
        "area_query": "Denver, CO",
        "output_format": "csv",
        "dataset": "all",
        "output_dir": "data/denver",
        "seed": "42",
    }
    cli_params = {"rows": 900, "output_format": OutputFormat.PARQUET}
    request = build_request_from_params(file_params, cli_params)

    assert request.rows == 900
    assert request.area_query == "Denver, CO"
    assert request.output_format is OutputFormat.PARQUET
    assert request.dataset is DatasetKind.ALL
    assert request.output_dir == Path("data/denver")
    assert request.seed == 42


def test_build_request_coerces_parameter_types() -> None:
    request = build_request_from_params(
        {
            "rows": "1000",
            "output_format": "json",
            "dataset": "phone",
            "output_dir": "exports",
            "start_date": "2024-01-01",
            "end_date": "2024-03-31",
            "seed": "7",
            "calltaker_pool_size": "8",
            "dispatcher_pool_size": "9",
        },
        {},
    )
    assert request.rows == 1000
    assert request.output_format is OutputFormat.JSON
    assert request.dataset is DatasetKind.PHONE
    assert request.output_dir == Path("exports")
    assert request.start_date == date(2024, 1, 1)
    assert request.end_date == date(2024, 3, 31)
    assert request.seed == 7
    assert request.calltaker_pool_size == 8
    assert request.dispatcher_pool_size == 9


def test_build_request_unknown_key_raises() -> None:
    with pytest.raises(typer.BadParameter):
        build_request_from_params({"bogus_option": 1}, {})


def test_build_request_uses_generation_request_defaults() -> None:
    request = build_request_from_params({"rows": 5}, {})
    assert request.area_query == "Kansas City, MO"
    assert request.output_stem == "synthetic_911"
    assert request.output_format is OutputFormat.CSV


def test_coerce_param_output_format_enum() -> None:
    assert _coerce_param("output_format", "parquet") is OutputFormat.PARQUET


def test_cli_params_help_lists_params_option() -> None:
    result = runner.invoke(app, ["generate", "--help"])
    assert result.exit_code == 0
    assert "--params" in _strip_ansi(result.output)
