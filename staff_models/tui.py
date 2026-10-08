"""Textual TUI for running staffing models and rendering their output."""

from __future__ import annotations

import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static, TextArea

sys.path.insert(0, str(Path(__file__).resolve().parent))

from render import RENDERERS, render
from runner import MODELS, get_model, parse_params

FORMATS = [(name, name) for name in RENDERERS]


class StaffModelApp(App):
    """Pick a model, supply parameters, and view a markdown/Carve report."""

    CSS = """
    #controls { width: 42; height: 100%; }
    #output { width: 1fr; }
    TextArea { height: 1fr; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="controls"):
                yield Label("Model")
                yield Select([(spec.label, spec.key) for spec in MODELS], id="model", allow_blank=False)
                yield Static("", id="description")
                yield Label("Parameters")
                yield Vertical(id="params")
                yield Label("Output format")
                yield Select(FORMATS, id="format", value="markdown", allow_blank=False)
                yield Button("Run", id="run", variant="primary")
            with Vertical(id="output"):
                yield TextArea(id="result", read_only=True)
        yield Footer()

    async def on_mount(self) -> None:
        select = self.query_one("#model", Select)
        if MODELS:
            select.value = MODELS[0].key
        await self._rebuild_params()

    async def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "model" and event.value is not Select.BLANK:
            await self._rebuild_params()

    async def _rebuild_params(self) -> None:
        select = self.query_one("#model", Select)
        if select.value in (None, Select.BLANK):
            return
        spec = get_model(str(select.value))
        self.query_one("#description", Static).update(spec.description)
        params_box = self.query_one("#params", Vertical)
        await params_box.remove_children()
        for p in spec.params:
            if isinstance(p.default, dict):
                import json

                default = json.dumps(p.default)
            elif isinstance(p.default, list):
                default = ",".join(map(str, p.default))
            else:
                default = str(p.default)
            await params_box.mount(Label(f"{p.name} ({p.help})"))
            await params_box.mount(Input(value=default, id=f"param-{p.name}"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "run":
            return
        try:
            spec = get_model(str(self.query_one("#model", Select).value))
            raw = {}
            for p in spec.params:
                raw[p.name] = self.query_one(f"#param-{p.name}", Input).value
            params = parse_params(spec, raw)
            fmt = str(self.query_one("#format", Select).value)
            results = spec.run(params)
            doc = render(fmt, spec.label, params, results)
            self.query_one("#result", TextArea).text = doc
        except Exception as exc:
            self.query_one("#result", TextArea).text = f"Error: {exc}\n"


if __name__ == "__main__":
    StaffModelApp().run()
