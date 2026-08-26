"""Tests for the TUI: field parsing, validation, and worker callbacks."""
import asyncio
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from textual.widgets import Input, ProgressBar, Select, Static

from synth911gen3.addresses import StaticAddressProvider
from synth911gen3.app import Synth911Application
from synth911gen3.config import DatasetKind, GenerationRequest, IdFormat, OutputFormat
from synth911gen3.domain import Address, GenerationResult
from synth911gen3.generators.incidents import IncidentGenerator
from synth911gen3.tui import FieldValidationError, Synth911Tui

TUI_INPUT_IDS = {
    "rows",
    "seed",
    "area",
    "output_dir",
    "output_stem",
    "start_date",
    "end_date",
    "calltaker_pool_size",
    "dispatcher_pool_size",
    "max_memory_bytes",
    "params",
    "config",
}


def _run(coro):
    return asyncio.run(coro)


def test_tui_composes_all_parameters() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            input_ids = {widget.id for widget in app.query(Input)}
            assert TUI_INPUT_IDS <= input_ids

            select_ids = {widget.id for widget in app.query(Select)}
            assert {"format", "dataset", "id_format"} <= select_ids

            assert app.query_one("#rows", Input).value == "10000"
            assert app.query_one("#area", Input).value == "Kansas City, MO"
            assert app.query_one("#format", Select).value == "csv"
            assert app.query_one("#dataset", Select).value == "incidents"
            assert app.query_one("#id_format", Select).value == "integer"
            assert app.query_one("#seed", Input).value == "911"
            assert app.query_one("#calltaker_pool_size", Input).value == "12"
            assert app.query_one("#dispatcher_pool_size", Input).value == "10"

    _run(scenario())


def test_tui_build_request_defaults() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            request = app._build_request()
            assert request.rows == 10_000
            assert request.area_query == "Kansas City, MO"
            assert request.output_format is OutputFormat.CSV
            assert request.dataset is DatasetKind.INCIDENTS
            assert request.id_format is IdFormat.INTEGER
            assert request.seed == 911
            assert request.start_date is None
            assert request.end_date is None

    _run(scenario())


def test_tui_build_request_custom_values() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            app.query_one("#rows", Input).value = "500"
            app.query_one("#seed", Input).value = "7"
            app.query_one("#area", Input).value = "Denver, CO"
            app.query_one("#format", Select).value = "parquet"
            app.query_one("#dataset", Select).value = "phone"
            app.query_one("#id_format", Select).value = "guid"
            app.query_one("#output_dir", Input).value = "exports"
            app.query_one("#output_stem", Input).value = "denver_911"
            app.query_one("#start_date", Input).value = "2024-01-01"
            app.query_one("#end_date", Input).value = "2024-03-31"
            app.query_one("#calltaker_pool_size", Input).value = "8"
            app.query_one("#dispatcher_pool_size", Input).value = "9"
            app.query_one("#max_memory_bytes", Input).value = "1048576"

            request = app._build_request()
            assert request.rows == 500
            assert request.seed == 7
            assert request.area_query == "Denver, CO"
            assert request.output_format is OutputFormat.PARQUET
            assert request.dataset is DatasetKind.PHONE
            assert request.id_format is IdFormat.GUID
            assert request.output_dir == Path("exports")
            assert request.output_stem == "denver_911"
            assert request.start_date == date(2024, 1, 1)
            assert request.end_date == date(2024, 3, 31)
            assert request.calltaker_pool_size == 8
            assert request.dispatcher_pool_size == 9
            assert request.max_memory_bytes == 1_048_576

    _run(scenario())


def test_tui_build_request_invalid_integer_reports() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            app.query_one("#rows", Input).value = "abc"
            with pytest.raises(ValueError):
                app._build_request()

    _run(scenario())


def test_tui_build_request_invalid_date_reports() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            app.query_one("#start_date", Input).value = "01/01/2024"
            with pytest.raises(ValueError):
                app._build_request()

    _run(scenario())


def test_tui_load_params_prefills_fields(tmp_path: Path) -> None:
    params = tmp_path / "params.yaml"
    params.write_text("rows: 500\narea: Denver, CO\nformat: parquet\nseed: 7\n", encoding="utf-8")

    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            app.query_one("#params", Input).value = str(params)
            app._load_params()
            assert app.query_one("#rows", Input).value == "500"
            assert app.query_one("#area", Input).value == "Denver, CO"
            assert app.query_one("#format", Select).value == "parquet"
            assert app.query_one("#seed", Input).value == "7"
            assert "Loaded params" in str(app.query_one("#status", Static).content)

    _run(scenario())


def test_tui_load_params_missing_file_reports() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            app.query_one("#params", Input).value = "does_not_exist.yaml"
            app._load_params()
            assert "Params file not found" in str(app.query_one("#status", Static).content)

    _run(scenario())


def test_tui_load_params_empty_reports() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            app._load_params()
            assert "Enter a params file path first." in str(
                app.query_one("#status", Static).content
            )

    _run(scenario())


def test_tui_load_params_unknown_key_reports(tmp_path: Path) -> None:
    params = tmp_path / "params.yaml"
    params.write_text("bogus_option: 1\n", encoding="utf-8")

    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            app.query_one("#params", Input).value = str(params)
            app._load_params()
            assert "Unknown parameter" in str(app.query_one("#status", Static).content)

    _run(scenario())


def test_tui_reset_restores_defaults() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            app.query_one("#rows", Input).value = "1"
            app.query_one("#seed", Input).value = "2"
            app._reset()
            assert app.query_one("#rows", Input).value == "10000"
            assert app.query_one("#seed", Input).value == "911"
            assert app.query_one("#params", Input).value == ""

    _run(scenario())


def test_tui_generate_reports_exported_artifacts() -> None:
    result = GenerationResult(
        incidents=None,
        hourly_call_counts=None,
        exported_artifacts={
            "incidents": Path("incidents.csv"),
            "hourly_call_counts": Path("hourly_call_counts.csv"),
        },
    )

    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            with patch("synth911gen3.tui.Synth911Application") as fake_cls:
                fake_cls.return_value.generate.return_value = result
                app._generate()
                assert app._worker is not None
                await app._worker.wait()
            text = str(app.query_one("#status", Static).content)
            assert "Generated files:" in text
            assert "incidents.csv" in text
            assert "hourly_call_counts.csv" in text
            assert app.query_one("#generate").disabled is False

    _run(scenario())


def test_tui_generate_invalid_input_updates_status() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            app.query_one("#rows", Input).value = "nope"
            with patch("synth911gen3.tui.Synth911Application") as fake_cls:
                app._generate()
                fake_cls.assert_not_called()
            assert "Invalid input" in str(app.query_one("#status", Static).content)

    _run(scenario())


def test_tui_generate_marks_invalid_fields() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            app.query_one("#rows", Input).value = "nope"
            app.query_one("#start_date", Input).value = "01/01/2024"
            app._generate()
            assert app.query_one("#rows").has_class("invalid")
            assert app.query_one("#start_date").has_class("invalid")
            status = str(app.query_one("#status", Static).content)
            assert "Invalid input" in status
            assert "rows must be an integer" in status

    _run(scenario())


def test_tui_build_request_aggregates_multiple_field_errors() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            app.query_one("#rows", Input).value = "abc"
            app.query_one("#start_date", Input).value = "not a date"
            with pytest.raises(ValueError) as excinfo:
                app._build_request()
            assert isinstance(excinfo.value, FieldValidationError)
            assert set(excinfo.value.fields) == {"rows", "start_date"}

    _run(scenario())


def test_tui_progress_updates_bar_and_status() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            app._report_progress("incidents", 500, 1000)
            progress = app.query_one("#progress", ProgressBar)
            assert progress.progress == 500
            assert progress.total == 1000
            assert "500" in str(app.query_one("#status", Static).content)

    _run(scenario())


def test_tui_form_overflow_allows_scroll() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test(size=(80, 20)):
            scroll = app.query_one("#parameters-scroll")
            assert scroll.max_scroll_y > 0

    _run(scenario())


def test_tui_tab_scrolls_focused_field_into_view() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test(size=(80, 20)) as pilot:
            targets = ["format", "emergency_numbers", "config"]
            for target in targets:
                for _ in range(40):
                    await pilot.press("tab")
                    if app.focused is not None and app.focused.id == target:
                        break
                assert app.focused is not None and app.focused.id == target
                assert app.screen.can_view_entire(app.focused)

    _run(scenario())


def test_tui_input_change_clears_invalid_mark() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test() as pilot:
            rows = app.query_one("#rows", Input)
            rows.add_class("invalid")
            rows.post_message(Input.Changed(rows, "100"))
            for _ in range(50):
                await pilot.pause()
                if not rows.has_class("invalid"):
                    break
            assert not rows.has_class("invalid")

    _run(scenario())


def test_tui_generate_pandas_format_describes_frames() -> None:
    import pandas as pd

    result = GenerationResult(
        incidents=pd.DataFrame({"id": [1, 2]}),
        hourly_call_counts=pd.DataFrame({"hour": [0]}),
        exported_artifacts={},
    )

    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            app.query_one("#format", Select).value = "pandas"
            with patch("synth911gen3.tui.Synth911Application") as fake_cls:
                fake_cls.return_value.generate.return_value = result
                app._generate()
                assert app._worker is not None
                await app._worker.wait()
            text = str(app.query_one("#status", Static).content)
            assert "incidents: 2 rows x 1 columns" in text
            assert "hourly_call_counts: 1 rows x 1 columns" in text

    _run(scenario())


def test_incident_generator_reports_progress() -> None:
    provider = StaticAddressProvider(
        [
            Address("101 N Main St", "Kansas City", "Missouri"),
            Address("204 E 12th St", "Kansas City", "Missouri"),
        ]
    )
    request = GenerationRequest(
        rows=50,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        seed=3,
    )
    updates: list[tuple[int, int]] = []
    IncidentGenerator(provider).generate(request, on_progress=lambda d, t: updates.append((d, t)))

    assert updates
    assert updates[0][0] > 0
    assert updates[-1] == (50, 50)
    assert all(1 <= done <= total <= 50 for done, total in updates)
    assert updates == sorted(updates)


def test_application_reports_incident_progress() -> None:
    provider = StaticAddressProvider(
        [
            Address("101 N Main St", "Kansas City", "Missouri"),
            Address("204 E 12th St", "Kansas City", "Missouri"),
        ]
    )
    request = GenerationRequest(
        rows=60,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        seed=4,
    )
    updates: list[tuple[str, int, int]] = []
    Synth911Application(address_provider=provider).generate(
        request, on_progress=lambda ds, d, t: updates.append((ds, d, t))
    )

    assert updates
    assert {dataset for dataset, _, _ in updates} == {"incidents"}
    assert updates[-1][1:] == (60, 60)


def test_tui_composes_dispatcher_discipline_fields() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            assert app.query_one("#dispatcher_mode", Select).value == "auto"
            assert app.query_one("#console_split_threshold", Input).value == "4"

    _run(scenario())


def test_tui_build_request_disciplines_default_has_no_realism_config() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            request = app._build_request()
            assert request.realism_config is None
            assert request.realism_config_path is None

    _run(scenario())


def test_tui_build_request_disciplines_custom_values() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            app.query_one("#dispatcher_mode", Select).value = "two_way"
            app.query_one("#console_split_threshold", Input).value = "6"
            request = app._build_request()
            assert request.realism_config is not None
            assert request.realism_config.dispatcher_disciplines == {
                "mode": "two_way",
                "min_dispatchers_for_split": 6,
            }

    _run(scenario())


def test_tui_build_request_disciplines_apply_over_config_file(tmp_path: Path) -> None:
    async def scenario() -> None:
        config_path = tmp_path / "realism.yaml"
        config_path.write_text("agency_names:\n  LAW: POLICE\n  FIRE: FIRE\n  EMS: EMS\n")
        app = Synth911Tui()
        async with app.run_test():
            app.query_one("#config", Input).value = str(config_path)
            request = app._build_request()
            # The YAML values load, and the form's discipline fields apply
            # over the file (defaults here: auto / 4).
            assert request.realism_config is not None
            assert request.realism_config.agency_names["LAW"] == "POLICE"
            assert request.realism_config.dispatcher_disciplines == {
                "mode": "auto",
                "min_dispatchers_for_split": 4,
            }

    _run(scenario())


def test_tui_build_request_invalid_config_marks_field(tmp_path: Path) -> None:
    async def scenario() -> None:
        config_path = tmp_path / "bad.yaml"
        config_path.write_text("agency_weights:\n  LAW: 0.5\n")
        app = Synth911Tui()
        async with app.run_test():
            app.query_one("#config", Input).value = str(config_path)
            with pytest.raises(FieldValidationError) as excinfo:
                app._build_request()
            assert "config" in excinfo.value.fields

    _run(scenario())


def test_tui_build_request_invalid_threshold_reports() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            app.query_one("#console_split_threshold", Input).value = "0"
            with pytest.raises(FieldValidationError) as excinfo:
                app._build_request()
            assert "console_split_threshold" in excinfo.value.fields

    _run(scenario())


def test_tui_registers_dma_themes_and_toggles() -> None:
    async def scenario() -> None:
        app = Synth911Tui()
        async with app.run_test():
            registered = {theme.name for theme in app.available_themes.values()}
            assert {"dma-light", "dma-dark"} <= registered
            assert app.theme == "dma-light"
            app.action_toggle_theme()
            assert app.theme == "dma-dark"
            app.action_toggle_theme()
            assert app.theme == "dma-light"

    _run(scenario())
