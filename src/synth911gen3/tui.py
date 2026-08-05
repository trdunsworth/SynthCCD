from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Button, Footer, Header, Input, Static

from .addresses import OpenStreetMapAddressProvider
from .app import Synth911Application
from .config import DatasetKind, GenerationRequest, OutputFormat
from .exceptions import AddressLookupError, ExportError, ValidationError


class Synth911Tui(App[None]):
    CSS = """
    Screen {
        align: center top;
    }

    #panel {
        width: 88;
        padding: 1 2;
    }

    Input, Button, Static {
        margin: 0 0 1 0;
    }

    #status {
        height: 8;
        border: round $primary;
        padding: 1;
    }
    """

    BINDINGS = [("g", "generate", "Generate"), ("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="panel"):
            yield Static(
                "Synth911Gen3\n"
                "TUI-first scaffold for synthetic CAD incidents and hourly phone counts."
            )
            yield Input("10000", id="rows", placeholder="Rows")
            yield Input("Kansas City, MO", id="area", placeholder="Area query")
            yield Input("csv", id="format", placeholder="Output format")
            yield Input("all", id="dataset", placeholder="Dataset")
            yield Input("synthetic_911", id="stem", placeholder="Output stem")
            yield Input("", id="config", placeholder="Config file (optional)")
            yield Button("Generate", id="generate", variant="primary")
            yield Static("Ready. Press G or use the button to generate data.", id="status")
        yield Footer()

    def action_generate(self) -> None:
        self._generate()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "generate":
            self._generate()

    def _build_request(self) -> GenerationRequest:
        rows = int(self.query_one("#rows", Input).value.strip())
        area = self.query_one("#area", Input).value.strip()
        output_format = OutputFormat(self.query_one("#format", Input).value.strip().lower())
        dataset = DatasetKind(self.query_one("#dataset", Input).value.strip().lower())
        output_stem = self.query_one("#stem", Input).value.strip()
        config_path = self.query_one("#config", Input).value.strip()
        return GenerationRequest(
            rows=rows,
            area_query=area,
            output_format=output_format,
            dataset=dataset,
            output_dir=Path("output"),
            output_stem=output_stem,
            realism_config_path=Path(config_path) if config_path else None,
        )

    def _generate(self) -> None:
        status = self.query_one("#status", Static)
        try:
            request = self._build_request()
            result = Synth911Application(address_provider=OpenStreetMapAddressProvider()).generate(
                request
            )
        except ValueError as exc:
            status.update(f"Invalid input: {exc}")
            return
        except (AddressLookupError, ExportError, ValidationError) as exc:
            status.update(str(exc))
            return

        if request.output_format in (OutputFormat.PANDAS, OutputFormat.POLARS):
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
            status.update("\n".join(lines))
            return

        lines = [f"{dataset_name}: {artifact}" for dataset_name, artifact in result.exported_artifacts.items()]
        status.update("Generated files:\n" + "\n".join(lines))


def run() -> None:
    Synth911Tui().run()
