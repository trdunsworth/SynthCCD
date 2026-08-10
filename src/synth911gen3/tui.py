from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import TypeVar

import typer
from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.worker import Worker
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    ProgressBar,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from .addresses import OpenStreetMapAddressProvider
from .app import Synth911Application
from .config import DatasetKind, GenerationRequest, IdFormat, OutputFormat
from .constants import DEFAULT_AREA_QUERY, DEFAULT_COUNTRY, DEFAULT_MAX_MEMORY_BYTES, DEFAULT_OUTPUT_DIR, DEFAULT_OUTPUT_STEM
from .domain import GenerationResult
from .emergency_numbers import SUPPORTED_COUNTRIES
from .exceptions import AddressLookupError, ExportError, ValidationError
from .params import build_request_from_params, load_params_file
from .shifts import DEFAULT_SHIFT_PRESET, SHIFT_PRESETS
from .tls import maybe_inject_system_trust


class FieldValidationError(ValueError):
    """Raised when one or more parameter fields fail to parse.

    ``fields`` lists the offending widget IDs so the TUI can highlight them.
    """

    def __init__(self, message: str, fields: Sequence[str]) -> None:
        super().__init__(message)
        self.fields = list(fields)


_T = TypeVar("_T")


def _parse_int(value: str, field: str, min_value: int | None = None) -> int:
    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise ValueError(f"{field} must be an integer, got {value!r}.") from exc
    if min_value is not None and parsed < min_value:
        raise ValueError(f"{field} must be at least {min_value}.")
    return parsed


def _parse_date_field(value: str, field: str) -> date | None:
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return date.fromisoformat(stripped)
    except ValueError as exc:
        raise ValueError(f"{field} must be formatted as YYYY-MM-DD, got {value!r}.") from exc


def _field(label: str, widget_id: str, widget: Input | Select) -> Vertical:
    return Vertical(
        Static(label, classes="field-label"),
        widget,
        id=f"{widget_id}-field",
        classes="field",
    )


def _section_title(title: str) -> Static:
    return Static(title, classes="section-title")


_HELP_TEXT = (
    "Synth911Gen3 — synthetic CAD incidents and hourly phone-center call counts.\n\n"
    "PARAMETERS\n"
    "  Rows               Number of incident rows to generate (default: 10000).\n"
    "  Seed               Random seed for reproducible output (default: 911).\n"
    "  Dataset            incidents, phone, or all (default: all).\n"
    "  Output format      csv, parquet, json, yaml, pandas, or polars (default: csv).\n"
    "  ID format          integer or guid for id_number (default: integer).\n"
    "  Area query         OpenStreetMap search area for addresses (default: Kansas City, MO).\n"
    "  Output directory   Directory for exported files (default: output).\n"
    "  Output stem        Filename stem for exports (default: synthetic_911).\n"
    "  Start date         Inclusive start date, YYYY-MM-DD (optional).\n"
    "  End date           Inclusive end date, YYYY-MM-DD (optional).\n"
    "  Calltaker pool     Unique calltaker name count (default: 12).\n"
    "  Dispatcher pool    Unique dispatcher name count (default: 10).\n"
    "  Shift preset       Shift structure: 2x12h-4shift-14day (default),\n"
    "                     2x12h-2shift, 3x8h-3shift, or 4x10h-4shift.\n"
    "  Max memory         Per-chunk memory budget in bytes for CSV/Parquet\n"
    "                     streaming (blank uses the 2 GiB default).\n"
    "  Country            ISO country code selecting emergency numbers (default: US).\n"
    "  Emergency numbers  Comma-separated override of the emergency lines to model\n"
    "                     (blank uses the country registry, e.g. 999,112).\n"
    "  10-digit lines     Include 10-digit direct-dial emergency lines.\n"
    "  Params file        JSON/YAML/TOML preset; Load Params fills the fields above.\n"
    "  Config file        YAML realism configuration file (optional).\n\n"
    "KEYS\n"
    "  g                  Generate data\n"
    "  p                  Load params file into the fields\n"
    "  r                  Reset fields to defaults\n"
    "  q                  Quit\n"
)


class Synth911Tui(App[None]):
    TITLE = "Synth911Gen3"
    SUB_TITLE = "Synthetic CAD incidents and hourly phone-center call counts"
    CSS = """
    #app {
        width: 100%;
        height: 1fr;
        padding: 0 2;
    }

    #tabs {
        height: 3fr;
    }

    #parameters-scroll, #help-scroll {
        height: 1fr;
    }

    #form {
        padding: 0 0 1 0;
    }

    .section-title {
        color: $accent;
        text-style: bold;
        margin: 1 0 0 0;
        border-bottom: solid $accent 30%;
        padding-bottom: 0;
    }

    .fields {
        grid-size: 2;
        grid-columns: 1fr 1fr;
        grid-gutter: 1 2;
        height: auto;
    }

    .field {
        height: auto;
    }

    .field-label {
        color: $text-muted;
        margin-bottom: 0;
    }

    .field Input, .field Select {
        width: 100%;
    }

    .field Input:focus, .field Select:focus {
        border: round $accent;
    }

    .field Input.invalid {
        border: round $error;
        color: $error;
    }

    #buttons {
        height: auto;
        margin-top: 1;
    }

    #buttons Button {
        margin-right: 1;
        min-width: 16;
    }

    #output-area {
        height: auto;
        margin-top: 1;
    }

    #progress {
        margin-bottom: 1;
    }

    #status {
        height: auto;
        min-height: 3;
        border: round $primary;
        padding: 1;
    }

    #status.info {
        border: round $primary;
    }

    #status.error {
        border: round $error;
        color: $error;
    }

    #status.success {
        border: round $success;
        color: $success;
    }

    #help-text {
        padding: 1 2;
    }
    """

    BINDINGS = [
        ("g", "generate", "Generate"),
        ("p", "load_params", "Load Params"),
        ("r", "reset", "Reset"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._worker: Worker[None] | None = None

    def compose(self) -> ComposeResult:
        defaults = GenerationRequest()
        yield Header(show_clock=True)
        with Vertical(id="app"):
            with TabbedContent(id="tabs"):
                with TabPane("Parameters", id="tab-parameters"):
                    with VerticalScroll(id="parameters-scroll"):
                        with Vertical(id="form"):
                            yield _section_title("General")
                            with Grid(classes="fields"):
                                yield _field(
                                    "Rows", "rows", Input(str(defaults.rows), id="rows")
                                )
                                yield _field(
                                    "Seed", "seed", Input(str(defaults.seed), id="seed")
                                )
                                yield _field(
                                    "Dataset",
                                    "dataset",
                                    Select(
                                        [(kind.name, kind.value) for kind in DatasetKind],
                                        value=defaults.dataset.value,
                                        id="dataset",
                                    ),
                                )
                                yield _field(
                                    "Output format",
                                    "format",
                                    Select(
                                        [(fmt.name, fmt.value) for fmt in OutputFormat],
                                        value=defaults.output_format.value,
                                        id="format",
                                    ),
                                )
                                yield _field(
                                    "ID format",
                                    "id_format",
                                    Select(
                                        [(fmt.name, fmt.value) for fmt in IdFormat],
                                        value=defaults.id_format.value,
                                        id="id_format",
                                    ),
                                )
                                yield _field(
                                    "Max memory (bytes)",
                                    "max_memory_bytes",
                                    Input(
                                        "",
                                        id="max_memory_bytes",
                                        placeholder=f"default: {DEFAULT_MAX_MEMORY_BYTES:,}",
                                    ),
                                )
                            yield _section_title("Geography")
                            with Grid(classes="fields"):
                                yield _field(
                                    "Area query",
                                    "area",
                                    Input(defaults.area_query, id="area"),
                                )
                                yield _field(
                                    "Output directory",
                                    "output_dir",
                                    Input(str(defaults.output_dir), id="output_dir"),
                                )
                                yield _field(
                                    "Output stem",
                                    "output_stem",
                                    Input(defaults.output_stem, id="output_stem"),
                                )
                                yield _field(
                                    "Start date (YYYY-MM-DD)",
                                    "start_date",
                                    Input("", id="start_date", placeholder="optional"),
                                )
                                yield _field(
                                    "End date (YYYY-MM-DD)",
                                    "end_date",
                                    Input("", id="end_date", placeholder="optional"),
                                )
                            yield _section_title("Emergency Numbers")
                            with Grid(classes="fields"):
                                yield _field(
                                    "Country",
                                    "country",
                                    Select(
                                        [(code, code) for code in SUPPORTED_COUNTRIES],
                                        value=DEFAULT_COUNTRY,
                                        id="country",
                                    ),
                                )
                                yield _field(
                                    "Emergency numbers",
                                    "emergency_numbers",
                                    Input(
                                        "",
                                        id="emergency_numbers",
                                        placeholder="override, e.g. 999,112",
                                    ),
                                )
                                yield _field(
                                    "Include 10-digit lines",
                                    "include_10_digit_emergency",
                                    Select(
                                        [("No", "0"), ("Yes", "1")],
                                        value="0",
                                        id="include_10_digit_emergency",
                                    ),
                                )
                            yield _section_title("Personnel")
                            with Grid(classes="fields"):
                                yield _field(
                                    "Calltaker pool size",
                                    "calltaker_pool_size",
                                    Input(
                                        str(defaults.calltaker_pool_size),
                                        id="calltaker_pool_size",
                                    ),
                                )
                                yield _field(
                                    "Dispatcher pool size",
                                    "dispatcher_pool_size",
                                    Input(
                                        str(defaults.dispatcher_pool_size),
                                        id="dispatcher_pool_size",
                                    ),
                                )
                                yield _field(
                                    "Shift preset",
                                    "shift_preset",
                                    Select(
                                        [
                                            (label, name)
                                            for name, label in SHIFT_PRESETS.items()
                                        ]
                                        + [("Custom (via realism config)", "")],
                                        value=DEFAULT_SHIFT_PRESET,
                                        id="shift_preset",
                                    ),
                                )
                            yield _section_title("Configuration Files")
                            with Grid(classes="fields"):
                                yield _field(
                                    "Params file",
                                    "params",
                                    Input("", id="params", placeholder=".json / .yaml / .toml"),
                                )
                                yield _field(
                                    "Realism config file",
                                    "config",
                                    Input("", id="config", placeholder=".yaml"),
                                )
                            with Horizontal(id="buttons"):
                                yield Button("Load Params", id="load_params")
                                yield Button("Reset", id="reset")
                                yield Button("Generate", id="generate", variant="primary")
                with TabPane("Help", id="tab-help"):
                    with VerticalScroll(id="help-scroll"):
                        yield Static(_HELP_TEXT, id="help-text")
            with Vertical(id="output-area"):
                yield ProgressBar(id="progress", show_eta=False, total=1)
                yield Static("Ready. Press G to generate data.", id="status")
        yield Footer()

    def action_generate(self) -> None:
        self._generate()

    def action_load_params(self) -> None:
        self._load_params()

    def action_reset(self) -> None:
        self._reset()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "generate":
            self._generate()
        elif event.button.id == "load_params":
            self._load_params()
        elif event.button.id == "reset":
            self._reset()

    def on_input_changed(self, event: Input.Changed) -> None:
        event.input.remove_class("invalid")

    def _set_status(self, message: str, level: str = "info") -> None:
        status = self.query_one("#status", Static)
        status.update(message)
        for candidate in ("info", "success", "error"):
            status.set_class(candidate == level, candidate)

    def _clear_invalid_fields(self) -> None:
        for widget in self.query(".invalid"):
            widget.remove_class("invalid")

    def _style_invalid_fields(self, fields: Sequence[str]) -> None:
        for field_id in fields:
            widget = self.query_one(f"#{field_id}")
            widget.add_class("invalid")

    def _apply_request(self, request: GenerationRequest) -> None:
        self.query_one("#rows", Input).value = str(request.rows)
        self.query_one("#seed", Input).value = str(request.seed)
        self.query_one("#area", Input).value = request.area_query
        self.query_one("#format", Select).value = request.output_format.value
        self.query_one("#dataset", Select).value = request.dataset.value
        self.query_one("#id_format", Select).value = request.id_format.value
        self.query_one("#output_dir", Input).value = str(request.output_dir)
        self.query_one("#output_stem", Input).value = request.output_stem
        self.query_one("#start_date", Input).value = (
            request.start_date.isoformat() if request.start_date else ""
        )
        self.query_one("#end_date", Input).value = (
            request.end_date.isoformat() if request.end_date else ""
        )
        self.query_one("#calltaker_pool_size", Input).value = str(request.calltaker_pool_size)
        self.query_one("#dispatcher_pool_size", Input).value = str(request.dispatcher_pool_size)
        self.query_one("#shift_preset", Select).value = request.shift_preset or DEFAULT_SHIFT_PRESET
        self.query_one("#max_memory_bytes", Input).value = (
            str(request.max_memory_bytes) if request.max_memory_bytes is not None else ""
        )
        self.query_one("#country", Select).value = request.country
        self.query_one("#emergency_numbers", Input).value = (
            request.emergency_numbers if request.emergency_numbers else ""
        )
        self.query_one("#include_10_digit_emergency", Select).value = (
            "1" if request.include_10_digit_emergency else "0"
        )
        self.query_one("#config", Input).value = (
            str(request.realism_config_path) if request.realism_config_path else ""
        )

    def _load_params(self) -> None:
        status = self.query_one("#status", Static)
        raw = self.query_one("#params", Input).value.strip()
        if not raw:
            status.update("Enter a params file path first.")
            return
        path = Path(raw)
        if not path.is_file():
            status.update(f"Params file not found: {path}")
            return
        try:
            file_params = load_params_file(path)
            request = build_request_from_params(file_params, {})
        except (typer.BadParameter, ValueError) as exc:
            status.update(str(exc))
            return
        self._clear_invalid_fields()
        self._apply_request(request)
        status.update(f"Loaded params from {path}")

    def _reset(self) -> None:
        self._clear_invalid_fields()
        self._apply_request(GenerationRequest())
        self.query_one("#params", Input).value = ""
        self.query_one("#status", Static).update("Defaults restored.")

    def _build_request(self) -> GenerationRequest:
        errors: dict[str, str] = {}

        def parse(field_id: str, fn: Callable[[], _T]) -> _T | None:
            try:
                return fn()
            except ValueError as exc:
                errors[field_id] = str(exc)
                return None

        rows = parse(
            "rows",
            lambda: _parse_int(self.query_one("#rows", Input).value, "rows", min_value=1),
        )
        seed = parse("seed", lambda: _parse_int(self.query_one("#seed", Input).value, "seed"))
        calltaker_pool_size = parse(
            "calltaker_pool_size",
            lambda: _parse_int(
                self.query_one("#calltaker_pool_size", Input).value,
                "calltaker_pool_size",
                min_value=1,
            ),
        )
        dispatcher_pool_size = parse(
            "dispatcher_pool_size",
            lambda: _parse_int(
                self.query_one("#dispatcher_pool_size", Input).value,
                "dispatcher_pool_size",
                min_value=1,
            ),
        )
        max_memory_value = self.query_one("#max_memory_bytes", Input).value.strip()
        max_memory_bytes: int | None = None
        if max_memory_value:
            max_memory_bytes = parse(
                "max_memory_bytes",
                lambda: _parse_int(
                    max_memory_value, "max_memory_bytes", min_value=1
                ),
            )
        start_date = parse(
            "start_date",
            lambda: _parse_date_field(self.query_one("#start_date", Input).value, "start_date"),
        )
        end_date = parse(
            "end_date",
            lambda: _parse_date_field(self.query_one("#end_date", Input).value, "end_date"),
        )

        if errors:
            raise FieldValidationError("; ".join(errors.values()), list(errors))

        assert rows is not None and seed is not None
        assert calltaker_pool_size is not None and dispatcher_pool_size is not None

        area_query = self.query_one("#area", Input).value.strip() or DEFAULT_AREA_QUERY
        output_format = OutputFormat(self.query_one("#format", Select).value)
        dataset = DatasetKind(self.query_one("#dataset", Select).value)
        id_format = IdFormat(self.query_one("#id_format", Select).value)
        output_dir = Path(self.query_one("#output_dir", Input).value.strip() or DEFAULT_OUTPUT_DIR)
        output_stem = self.query_one("#output_stem", Input).value.strip() or DEFAULT_OUTPUT_STEM
        config_raw = self.query_one("#config", Input).value.strip()
        realism_config_path = Path(config_raw) if config_raw else None
        shift_preset_value = self.query_one("#shift_preset", Select).value
        shift_preset: str | None = str(shift_preset_value) if shift_preset_value else None
        country_value = self.query_one("#country", Select).value
        country = str(country_value) if country_value else DEFAULT_COUNTRY
        emergency_numbers_raw = self.query_one("#emergency_numbers", Input).value.strip()
        emergency_numbers: str | None = emergency_numbers_raw or None
        include_10_digit_emergency = (
            str(self.query_one("#include_10_digit_emergency", Select).value) == "1"
        )

        return GenerationRequest(
            rows=rows,
            area_query=area_query,
            output_format=output_format,
            dataset=dataset,
            id_format=id_format,
            output_dir=output_dir,
            output_stem=output_stem,
            start_date=start_date,
            end_date=end_date,
            seed=seed,
            calltaker_pool_size=calltaker_pool_size,
            dispatcher_pool_size=dispatcher_pool_size,
            shift_preset=shift_preset,
            realism_config_path=realism_config_path,
            max_memory_bytes=max_memory_bytes,
            country=country,
            emergency_numbers=emergency_numbers,
            include_10_digit_emergency=include_10_digit_emergency,
        )

    def _generate(self) -> None:
        self._clear_invalid_fields()
        try:
            request = self._build_request()
        except FieldValidationError as exc:
            self._style_invalid_fields(exc.fields)
            self._set_status(f"Invalid input: {exc}", "error")
            return

        self.query_one("#generate", Button).disabled = True
        progress = self.query_one("#progress", ProgressBar)
        progress.update(total=request.rows, progress=0)
        progress.display = True
        self._set_status("Generating…", "info")
        self._worker = self.run_worker(
            lambda: self._generation_worker(request), thread=True, exclusive=True
        )

    def _generation_worker(self, request: GenerationRequest) -> None:
        def on_progress(dataset: str, done: int, total: int) -> None:
            self.call_from_thread(self._report_progress, dataset, done, total)

        try:
            result = Synth911Application(
                address_provider=OpenStreetMapAddressProvider()
            ).generate(request, on_progress=on_progress)
        except (AddressLookupError, ExportError, ValidationError) as exc:
            self.call_from_thread(self._on_generation_error, str(exc))
            return
        except ValueError as exc:
            self.call_from_thread(self._on_generation_error, f"Invalid input: {exc}")
            return
        self.call_from_thread(self._on_generation_success, result, request.output_format)

    def _report_progress(self, dataset: str, done: int, total: int) -> None:
        progress = self.query_one("#progress", ProgressBar)
        progress.update(total=total, progress=done)
        self._set_status(f"Generating {dataset}: {done:,} / {total:,}", "info")

    def _on_generation_error(self, message: str) -> None:
        self.query_one("#progress", ProgressBar).display = False
        self.query_one("#generate", Button).disabled = False
        self._set_status(message, "error")

    def _on_generation_success(
        self, result: GenerationResult, output_format: OutputFormat
    ) -> None:
        self.query_one("#progress", ProgressBar).display = False
        self.query_one("#generate", Button).disabled = False

        if output_format in (OutputFormat.PANDAS, OutputFormat.POLARS):
            lines = []
            if result.incidents is not None:
                lines.append(
                    f"incidents: {len(result.incidents):,} rows x {len(result.incidents.columns)} columns"
                )
            if result.hourly_call_counts is not None:
                lines.append(
                    "hourly_call_counts: "
                    f"{len(result.hourly_call_counts):,} rows x "
                    f"{len(result.hourly_call_counts.columns)} columns"
                )
            self._set_status("\n".join(lines), "success")
            return

        lines = [
            f"{dataset_name}: {artifact}"
            for dataset_name, artifact in result.exported_artifacts.items()
        ]
        self._set_status("Generated files:\n" + "\n".join(lines), "success")


def run() -> None:
    maybe_inject_system_trust()
    Synth911Tui().run()
