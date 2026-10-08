"""Render model results as Markdown or Carve documents."""

from __future__ import annotations

from typing import Any

CARVE_HEADER_PREFIX = "|="


def _fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, (dict, list)):
        import json

        return json.dumps(value)
    return str(value)


def render_markdown(model_label: str, params: dict[str, Any], results: dict[str, object]) -> str:
    """Render a model run as a Markdown document."""
    lines = [f"# {model_label}", "", "## Parameters", "", "| Parameter | Value |", "|---|---|"]
    for k, v in params.items():
        lines.append(f"| {k} | {_fmt(v)} |")
    lines += ["", "## Results", "", "| Metric | Value |", "|---|---|"]
    for k, v in results.items():
        lines.append(f"| {k} | {_fmt(v)} |")
    return "\n".join(lines) + "\n"


def render_carve(model_label: str, params: dict[str, Any], results: dict[str, object]) -> str:
    """Render a model run as a Carve document (markup-carve/carve syntax)."""
    lines = [f"# {model_label}", "", "## Parameters", ""]
    lines.append("|= Parameter |= Value")
    for k, v in params.items():
        lines.append(f"| {k} | {_fmt(v)}")
    lines += ["", "## Results", ""]
    lines.append("|= Metric |= Value")
    for k, v in results.items():
        lines.append(f"| {k} | {_fmt(v)}")
    return "\n".join(lines) + "\n"


RENDERERS = {"markdown": render_markdown, "carve": render_carve}


def render(fmt: str, model_label: str, params: dict[str, Any], results: dict[str, object]) -> str:
    """Render results in the requested format ('markdown' or 'carve')."""
    try:
        fn = RENDERERS[fmt]
    except KeyError:
        raise ValueError(f"unknown format {fmt!r}; choose from {sorted(RENDERERS)}") from None
    return fn(model_label, params, results)
