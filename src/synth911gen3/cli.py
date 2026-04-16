from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import typer

from .addresses import OpenStreetMapAddressProvider
from .app import Synth911Application
from .config import DatasetKind, GenerationRequest, OutputFormat
from .exceptions import AddressLookupError, ExportError, ValidationError
from .tui import run as run_tui

app = typer.Typer(
    help="Synthetic 911 CAD incident and hourly phone-center data generator.",
    no_args_is_help=True,
)


def _describe_frame(name: str, frame: pd.DataFrame) -> str:
    return f"{name}: {len(frame):,} rows x {len(frame.columns)} columns"


@app.command()
def generate(
    rows: int = typer.Option(10_000, "--rows", min=1, help="Number of incident rows to generate."),
    area: str = typer.Option(
        "Kansas City, MO",
        "--area",
        help="Area query sent to OpenStreetMap for address generation.",
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.CSV,
        "--format",
        case_sensitive=False,
        help="Output format for generated datasets.",
    ),
    dataset: DatasetKind = typer.Option(
        DatasetKind.ALL,
        "--dataset",
        case_sensitive=False,
        help="Dataset to generate: incidents, phone, or all.",
    ),
    output_dir: Path = typer.Option(
        Path("output"),
        "--output-dir",
        help="Directory where file exports should be written.",
    ),
    output_stem: str = typer.Option(
        "synthetic_911",
        "--output-stem",
        help="Filename stem used for exported datasets.",
    ),
    start_date: date | None = typer.Option(
        None,
        "--start-date",
        formats=["%Y-%m-%d"],
        help="Inclusive start date for generated data.",
    ),
    end_date: date | None = typer.Option(
        None,
        "--end-date",
        formats=["%Y-%m-%d"],
        help="Inclusive end date for generated data.",
    ),
    seed: int = typer.Option(911, "--seed", help="Random seed for reproducible output."),
) -> None:
    request = GenerationRequest(
        rows=rows,
        area_query=area,
        output_format=output_format,
        dataset=dataset,
        output_dir=output_dir,
        output_stem=output_stem,
        start_date=start_date,
        end_date=end_date,
        seed=seed,
    )

    try:
        result = Synth911Application(address_provider=OpenStreetMapAddressProvider()).generate(request)
    except (AddressLookupError, ExportError, ValidationError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if output_format in (OutputFormat.PANDAS, OutputFormat.POLARS):
        if result.incidents is not None:
            typer.echo(_describe_frame("incidents", result.incidents))
        if result.hourly_call_counts is not None:
            typer.echo(_describe_frame("hourly_call_counts", result.hourly_call_counts))
        return

    for dataset_name, artifact in result.exported_artifacts.items():
        typer.echo(f"{dataset_name}: {artifact}")


@app.command()
def tui() -> None:
    """Launch the TUI scaffold."""

    run_tui()


def main() -> None:
    app()
