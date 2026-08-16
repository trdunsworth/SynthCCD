"""CLI tests: commands, flags, params-file merging, and error handling."""
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
import typer
import yaml
from typer.testing import CliRunner

from synth911gen3.addresses import Address, StaticAddressProvider
from synth911gen3.cli import (
    _coerce_param,
    _parse_date,
    app,
    build_request_from_params,
    load_params_file,
    save_params_file,
)
from synth911gen3.config import DatasetKind, IdFormat, OutputFormat
from synth911gen3.exceptions import ExportError
from synth911gen3.realism_config import RealismConfig

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def _install_static_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "synth911gen3.cli.OpenStreetMapAddressProvider",
        lambda: StaticAddressProvider(
            [
                Address("101 N Main St", "Kansas City", "Missouri"),
                Address("204 E 12th St", "Kansas City", "Missouri"),
                Address("55 W 39th St", "Kansas City", "Missouri"),
                Address("777 S Broadway Blvd", "Kansas City", "Missouri"),
                Address("890 N Oak Trafficway", "Kansas City", "Missouri"),
            ]
        ),
    )


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
    path = _write(tmp_path, "params.json", "[1, 2, 3]")
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


def test_coerce_param_id_format_enum() -> None:
    assert _coerce_param("id_format", "guid") is IdFormat.GUID


def test_build_request_coerces_id_format() -> None:
    request = build_request_from_params({"id_format": "guid"}, {})
    assert request.id_format is IdFormat.GUID


def test_build_request_unknown_id_format_raises() -> None:
    with pytest.raises(ValueError):
        build_request_from_params({"id_format": "hex"}, {})


def test_cli_params_help_lists_id_format_option() -> None:
    result = runner.invoke(app, ["generate", "--help"])
    assert result.exit_code == 0
    assert "--id-format" in _strip_ansi(result.output)


def test_cli_params_help_lists_params_option() -> None:
    result = runner.invoke(app, ["generate", "--help"])
    assert result.exit_code == 0
    assert "--params" in _strip_ansi(result.output)


def test_cli_params_help_lists_max_memory_bytes_option() -> None:
    result = runner.invoke(app, ["generate", "--help"])
    assert result.exit_code == 0
    assert "--max-memory-bytes" in _strip_ansi(result.output)


def test_coerce_param_max_memory_bytes_int() -> None:
    assert _coerce_param("max_memory_bytes", "500") == 500


def test_build_request_coerces_max_memory_bytes() -> None:
    request = build_request_from_params({"max_memory_bytes": "1048576"}, {})
    assert request.max_memory_bytes == 1_048_576


def test_cli_help_lists_verbosity_flags() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    output = _strip_ansi(result.output)
    assert "--verbose" in output
    assert "--quiet" in output


def test_cli_help_lists_schema_and_dry_run_flags() -> None:
    result = runner.invoke(app, ["generate", "--help"])
    assert result.exit_code == 0
    output = _strip_ansi(result.output)
    assert "--schema" in output
    assert "--dry-run" in output


def test_cli_help_lists_db_flags() -> None:
    result = runner.invoke(app, ["generate", "--help"])
    assert result.exit_code == 0
    output = _strip_ansi(result.output)
    for flag in (
        "--db-dialect",
        "--db-host",
        "--db-port",
        "--db-name",
        "--db-user",
        "--db-password",
        "--db-table-incidents",
        "--db-table-phone",
        "--db-schema",
        "--db-batch-size",
        "--db-if-exists",
        "--no-db-indexes",
    ):
        assert flag in output, f"expected {flag} in generate --help"


def test_cli_db_flags_map_to_request(tmp_path: Path) -> None:
    # Exercise the params merge with db flags via a dry-run (validates flag ->
    # field wiring through the CLI).
    result = runner.invoke(
        app,
        [
            "generate",
            "--dry-run",
            "--dataset",
            "incidents",
            "--rows",
            "2",
            "--format",
            "sqlite",
            "--db-name",
            "custom.db",
            "--db-table-incidents",
            "cad_incidents",
            "--db-batch-size",
            "50",
            "--db-if-exists",
            "replace",
            "--no-db-indexes",
        ],
    )
    assert result.exit_code == 0
    assert "id_number" in _strip_ansi(result.output)


def test_cli_generate_sqlite_writes_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlite3

    _install_static_provider(monkeypatch)
    result = runner.invoke(
        app,
        [
            "generate",
            "--rows",
            "5",
            "--dataset",
            "incidents",
            "--format",
            "sqlite",
            "--output-dir",
            str(tmp_path),
            "--output-stem",
            "cad",
        ],
    )
    assert result.exit_code == 0
    db_path = tmp_path / "cad.sqlite3"
    assert db_path.exists()
    con = sqlite3.connect(db_path)
    try:
        cur = con.execute("SELECT COUNT(*) FROM incidents")
        assert cur.fetchone()[0] == 5
    finally:
        con.close()


def test_cli_schema_prints_schema_without_writing_files(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "generate",
            "--schema",
            "--dataset",
            "incidents",
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    output = _strip_ansi(result.output)
    assert "id_number" in output
    assert "int64" in output
    assert "call_start_time" in output
    assert "sample rows" not in output
    assert not list(tmp_path.iterdir())


def test_cli_dry_run_prints_schema_and_sample_rows(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "generate",
            "--dry-run",
            "--dataset",
            "incidents",
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    output = _strip_ansi(result.output)
    assert "id_number" in output
    assert "sample rows" in output
    assert not list(tmp_path.iterdir())


def test_cli_dry_run_respects_dataset_selection() -> None:
    result = runner.invoke(app, ["generate", "--dry-run", "--dataset", "phone"])
    assert result.exit_code == 0
    output = _strip_ansi(result.output)
    assert "hourly_call_counts" in output
    assert "incidents schema" not in output


def test_parse_date_converts_iso_string() -> None:
    assert _parse_date("2024-03-01") == date(2024, 3, 1)
    assert _parse_date(None) is None


def test_cli_maps_all_flag_branches_to_params(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "generate",
            "--dry-run",
            "--dataset",
            "incidents",
            "--rows",
            "3",
            "--area",
            "Denver, CO",
            "--format",
            "parquet",
            "--id-format",
            "guid",
            "--output-dir",
            str(tmp_path),
            "--output-stem",
            "custom",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-01-05",
            "--seed",
            "7",
            "--calltaker-pool-size",
            "4",
            "--dispatcher-pool-size",
            "5",
            "--shift-preset",
            "3x8h-3shift",
            "--max-memory-bytes",
            "1048576",
        ],
    )
    assert result.exit_code == 0
    assert "id_number" in _strip_ansi(result.output)


def test_cli_generate_csv_writes_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_static_provider(monkeypatch)
    result = runner.invoke(
        app,
        [
            "generate",
            "--rows",
            "5",
            "--dataset",
            "incidents",
            "--output-dir",
            str(tmp_path),
            "--output-stem",
            "sample",
        ],
    )
    assert result.exit_code == 0
    assert "incidents: " in _strip_ansi(result.output)
    assert (tmp_path / "sample_incidents.csv").exists()


def test_cli_generate_pandas_prints_frame_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_static_provider(monkeypatch)
    result = runner.invoke(
        app,
        ["generate", "--rows", "5", "--dataset", "incidents", "--format", "pandas"],
    )
    assert result.exit_code == 0
    assert "incidents: 5 rows x" in _strip_ansi(result.output)


def test_cli_generate_polars_prints_frame_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_static_provider(monkeypatch)
    result = runner.invoke(
        app,
        ["generate", "--rows", "5", "--dataset", "incidents", "--format", "polars"],
    )
    assert result.exit_code == 0
    assert "incidents: 5 rows x" in _strip_ansi(result.output)


def test_cli_generate_validation_error_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_static_provider(monkeypatch)
    result = runner.invoke(
        app,
        ["generate", "--rows", "5", "--dataset", "incidents", "--area", "  "],
    )
    assert result.exit_code == 1
    assert "area_query must not be empty" in _strip_ansi(result.output)


def test_cli_generate_export_error_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _FailingApp:
        def __init__(self, address_provider=None) -> None:
            self._address_provider = address_provider

        def generate(self, request, on_progress=None):
            raise ExportError("boom")

    monkeypatch.setattr("synth911gen3.cli.Synth911Application", _FailingApp)
    result = runner.invoke(
        app,
        ["generate", "--rows", "5", "--dataset", "incidents", "--output-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "boom" in _strip_ansi(result.output)


def test_cli_generate_with_config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_static_provider(monkeypatch)
    config_path = _write(
        tmp_path,
        "center.yaml",
        "agency_names:\n  LAW: POLICE\n  FIRE: FIRE\n  EMS: EMS\n",
    )
    result = runner.invoke(
        app,
        [
            "generate",
            "--rows",
            "5",
            "--dataset",
            "incidents",
            "--output-dir",
            str(tmp_path),
            "--config",
            str(config_path),
        ],
    )
    assert result.exit_code == 0
    assert "incidents: " in _strip_ansi(result.output)


def test_module_entrypoint_prints_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "synth911gen3", "--help"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0
    assert "Synthetic 911" in result.stdout


def test_save_params_file_yaml(tmp_path: Path) -> None:
    path = tmp_path / "saved.yaml"
    save_params_file(
        path,
        {
            "rows": 2500,
            "area_query": "Denver, CO",
            "output_format": OutputFormat.PARQUET,
            "seed": 77,
        },
    )
    assert load_params_file(path) == {
        "rows": 2500,
        "area_query": "Denver, CO",
        "output_format": "parquet",
        "seed": 77,
    }


def test_save_params_file_json(tmp_path: Path) -> None:
    path = tmp_path / "saved.json"
    save_params_file(
        path,
        {"rows": 100, "dataset": DatasetKind.PHONE, "output_dir": Path("exports")},
    )
    assert load_params_file(path) == {
        "rows": 100,
        "dataset": "phone",
        "output_dir": "exports",
    }


def test_save_params_file_toml(tmp_path: Path) -> None:
    path = tmp_path / "saved.toml"
    save_params_file(
        path,
        {
            "rows": 500,
            "id_format": IdFormat.GUID,
            "include_10_digit_emergency": True,
        },
    )
    assert load_params_file(path) == {
        "rows": 500,
        "id_format": "guid",
        "include_10_digit_emergency": True,
    }


def test_save_params_file_round_trips_dates_and_paths(tmp_path: Path) -> None:
    path = tmp_path / "saved.yaml"
    save_params_file(
        path,
        {
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 1, 7),
            "realism_config_path": Path("config/center.yaml"),
            "db_create_indexes": False,
        },
    )
    request = build_request_from_params(load_params_file(path), {})
    assert request.start_date == date(2026, 1, 1)
    assert request.end_date == date(2026, 1, 7)
    assert request.realism_config_path == Path("config/center.yaml")
    assert request.db_create_indexes is False


def test_save_params_file_drops_none_values(tmp_path: Path) -> None:
    path = tmp_path / "saved.yaml"
    save_params_file(path, {"rows": 5, "end_date": None, "db_host": None})
    assert load_params_file(path) == {"rows": 5}


def test_save_params_file_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "saved.txt"
    with pytest.raises(typer.BadParameter):
        save_params_file(path, {"rows": 5})


def test_cli_save_params_short_circuits_and_writes_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_static_provider(monkeypatch)
    saved = tmp_path / "run.yaml"
    result = runner.invoke(
        app,
        [
            "generate",
            "--save-params",
            str(saved),
            "--rows",
            "2500",
            "--area",
            "Denver, CO",
            "--format",
            "parquet",
            "--seed",
            "77",
        ],
    )
    assert result.exit_code == 0
    assert "Saved parameters" in _strip_ansi(result.output)
    assert "incidents:" not in _strip_ansi(result.output)
    assert load_params_file(saved) == {
        "rows": 2500,
        "area_query": "Denver, CO",
        "output_format": "parquet",
        "seed": 77,
    }


def test_cli_save_params_merges_params_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_static_provider(monkeypatch)
    params = _write(tmp_path, "base.yaml", "rows: 100\ndataset: phone\narea: Seattle, WA\n")
    saved = tmp_path / "run.json"
    result = runner.invoke(
        app,
        ["generate", "--params", str(params), "--save-params", str(saved), "--rows", "500"],
    )
    assert result.exit_code == 0
    assert load_params_file(saved) == {
        "rows": 500,
        "dataset": "phone",
        "area_query": "Seattle, WA",
    }


def test_cli_help_lists_save_params_option() -> None:
    result = runner.invoke(app, ["generate", "--help"])
    assert result.exit_code == 0
    assert "--save-params" in _strip_ansi(result.output)


def test_cli_help_lists_validate_config_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "validate-config" in _strip_ansi(result.output)


def test_cli_validate_config_valid(tmp_path: Path) -> None:
    config_path = tmp_path / "valid.yaml"
    RealismConfig().to_yaml(config_path)
    result = runner.invoke(app, ["validate-config", str(config_path)])
    assert result.exit_code == 0
    assert "OK" in _strip_ansi(result.output)


def test_cli_validate_config_invalid_yaml_exits_1(tmp_path: Path) -> None:
    config_path = _write(tmp_path, "bad.yaml", "[invalid yaml")
    result = runner.invoke(app, ["validate-config", str(config_path)])
    assert result.exit_code == 1
    output = _strip_ansi(result.output)
    assert "bad.yaml" in output


def test_cli_validate_config_validation_error_exits_1(tmp_path: Path) -> None:
    config_path = _write(
        tmp_path,
        "bad_weights.yaml",
        "priority_weights:\n  UNKNOWN:\n    1: 1.0\n",
    )
    result = runner.invoke(app, ["validate-config", str(config_path)])
    assert result.exit_code == 1
    output = _strip_ansi(result.output)
    assert "bad_weights.yaml" in output
    assert "Priority weights defined for unknown agency: UNKNOWN" in output


def test_cli_validate_config_missing_file_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate-config", str(tmp_path / "missing.yaml")])
    assert result.exit_code == 2


def test_cli_validate_config_mixed_paths_reports_each(tmp_path: Path) -> None:
    good = tmp_path / "good.yaml"
    RealismConfig().to_yaml(good)
    bad = _write(tmp_path, "bad.yaml", "hourly_weights: [0.04]")
    result = runner.invoke(app, ["validate-config", str(good), str(bad)])
    assert result.exit_code == 1
    output = _strip_ansi(result.output)
    assert "good.yaml: OK" in output
    assert "bad.yaml" in output


def test_cli_help_lists_schema_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "schema" in _strip_ansi(result.output)


def test_cli_schema_exports_incidents_json() -> None:
    result = runner.invoke(app, ["schema", "--format", "json", "--dataset", "incidents"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["dataset"] == "incidents"
    assert data["version"] == "1.0"
    assert data["schema_hash"]
    assert "id_number" in data["datasets"]["incidents"]
    assert "agency" in data["datasets"]["incidents"]


def test_cli_schema_exports_phone_yaml() -> None:
    result = runner.invoke(app, ["schema", "--format", "yaml", "--dataset", "phone"])
    assert result.exit_code == 0
    data = yaml.safe_load(result.output)
    assert data["dataset"] == "phone"
    assert "hour_start" in data["datasets"]["hourly_call_counts"]


def test_cli_schema_dataset_all_includes_both() -> None:
    result = runner.invoke(app, ["schema", "--dataset", "all"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert set(data["datasets"]) == {"incidents", "hourly_call_counts"}


def test_cli_schema_respects_id_format() -> None:
    result = runner.invoke(app, ["schema", "--id-format", "guid", "--dataset", "incidents"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["datasets"]["incidents"]["id_number"] != "int64"


def test_cli_schema_writes_output_file(tmp_path: Path) -> None:
    out = tmp_path / "schema.json"
    result = runner.invoke(app, ["schema", "--output", str(out)])
    assert result.exit_code == 0
    assert "Schema written to" in _strip_ansi(result.output)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "id_number" in data["datasets"]["incidents"]


def test_cli_schema_unsupported_format_exits_2() -> None:
    result = runner.invoke(app, ["schema", "--format", "xml"])
    assert result.exit_code == 2
    assert "Unsupported format" in _strip_ansi(result.output)


def test_cli_schema_invalid_config_exits_1(tmp_path: Path) -> None:
    bad = _write(tmp_path, "bad.yaml", "priority_weights:\n  UNKNOWN:\n    1: 1.0\n")
    result = runner.invoke(app, ["schema", "--config", str(bad)])
    assert result.exit_code == 1
    assert "Priority weights defined for unknown agency" in _strip_ansi(result.output)
