"""
Synth911Gen2 TUI (Text-based User Interface)

This module provides a text-based user interface for generating synthetic 911 dispatch data.
It demonstrates the use of various TUI widgets including Input, Button, Static, ProgressBar,
and Vertical containers using the Textual library.
"""

import asyncio

from datetime import datetime
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Button, Input, ProgressBar, Static

from synth911gen import DEFAULT_LOCALE, generate_911_data

DEFAULTS = {
    "num_records": "10000",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "num_names": "8",
    "locale": DEFAULT_LOCALE,
    "output_file": "computer_aided_dispatch.csv",
    "selected_agencies": "",
    "agency_probabilities": "",
}

class ParamInput(Vertical):
    """A widget for parameter input in the TUI interface.

    This widget displays a labeled input box for a single parameter, allowing the user
    to enter or accept a default value for a configuration option.
    """
    def __init__(self, param, prompt, default):
        """Initialize the parameter input widget.

        Args:
            param (str): The parameter name.
            prompt (str): The prompt to display.
            default (Any): The default value for the parameter.
        """
        super().__init__()
        self.param = param
        self.prompt = prompt
        self.default = default
        self.input = None

    def compose(self):
        """Compose the widget layout for the parameter input.

        Returns:
            Input: The input widget for user entry.
        """
        input_widget = Input(placeholder=f"Default: {self.default}")
        input_widget.border_title = self.prompt
        input_widget.styles.border_title_color = "cyan"
        input_widget.styles.color = "yellow"
        self.input = input_widget
        yield input_widget

    def get_value(self):
        """Get the current value from the input widget.

        Returns:
            str: The value entered by the user, or the default if empty.
        """
        if self.input is not None and hasattr(self.input, 'value'):
            value = self.input.value
            if value is None:
                value = ""
            value = value.strip()
            return value if value else self.default
        return self.default

class SynthTUI(App):
    """Textual User Interface (TUI) application for Synth911Gen2.

    This class implements the main TUI application, allowing users to configure
    and generate synthetic 911 data interactively.
    """
    CSS_PATH = None
    params = list(DEFAULTS.keys())
    param_prompts = [
        "Number of records",
        "Start date (YYYY-MM-DD)",
        "End date (YYYY-MM-DD)",
        "Names per shift",
        "Faker locale",
        "Output file",
        "Agencies (comma-separated, blank for all)",
        "Agency probabilities (comma-separated, blank for default)",
    ]
    values = reactive({})

    def __init__(self):
        """Initialize the SynthTUI application."""
        super().__init__()
        self.inputs = []
        self.progress = ProgressBar(total=100)
        self.status = Static("")

    def compose(self) -> ComposeResult:
        """Compose the main layout of the TUI application.

        Returns:
            ComposeResult: The composed layout for the TUI.
        """
        for param, prompt in zip(self.params, self.param_prompts):
            inp = ParamInput(param, prompt, DEFAULTS[param])
            self.inputs.append(inp)
            yield inp
        yield Button("Generate Data", id="generate", variant="success")
        yield self.progress
        yield self.status

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events in the TUI.

        Args:
            event (Button.Pressed): The button press event.
        """
        if event.button.id == "generate":
            self.status.update("[b yellow]Generating data...[/b yellow]")
            self.progress.progress = 0
            await self.run_generation()

    async def run_generation(self):
        """Run the data generation process asynchronously.

        This method collects user input, validates parameters, generates the data,
        and saves it to a CSV file, updating the UI with progress and status.
        """
        params = {inp.param: inp.get_value() for inp in self.inputs}
        params["num_records"] = int(params["num_records"])
        params["num_names"] = int(params["num_names"])
        params["selected_agencies"] = (
            [a.strip() for a in params["selected_agencies"].split(",") if a.strip()]
            if params["selected_agencies"] else None
        )
        params["agency_probabilities"] = (
            [float(x) for x in params["agency_probabilities"].split(",") if x.strip()]
            if params["agency_probabilities"] else None
        )
        # Validate that end_date is after start_date
        try:
            start_date_obj = datetime.strptime(params["start_date"], "%Y-%m-%d")
            end_date_obj = datetime.strptime(params["end_date"], "%Y-%m-%d")
            if end_date_obj <= start_date_obj:
                self.status.update("[b red]Error: End date must be after start date.[/b red]")
                return
        except ValueError as e:
            self.status.update(f"[b red]Date error: {e}[/b red]")
            return
        await asyncio.sleep(0.5)
        df, _, dispatcher_names = generate_911_data(
            num_records=params["num_records"],
            start_date=params["start_date"],
            end_date=params["end_date"],
            num_names=params["num_names"],
            locale=params["locale"],
            selected_agencies=params["selected_agencies"],
            agency_probabilities=params["agency_probabilities"],
        )
        df.write_csv(params["output_file"])
        self.progress.progress = 100
        self.status.update(f"[b green]Done![/b green] File saved to [b]{params['output_file']}[/b]")

if __name__ == "__main__":
    SynthTUI().run()
