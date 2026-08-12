from __future__ import annotations

from dataclasses import replace
from datetime import date

import pandas as pd

from .addresses import StaticAddressProvider
from .config import DatasetKind, GenerationRequest
from .domain import Address
from .generators import HourlyCallCountGenerator, IncidentGenerator

SCHEMA_ROWS = 1
SAMPLE_ROWS = 5

_STATIC_ADDRESSES = [
    Address("101 N Main St", "Kansas City", "Missouri"),
    Address("204 E 12th St", "Kansas City", "Missouri"),
    Address("55 W 39th St", "Kansas City", "Missouri"),
    Address("777 S Broadway Blvd", "Kansas City", "Missouri"),
    Address("890 N Oak Trafficway", "Kansas City", "Missouri"),
]


def build_preview_datasets(
    request: GenerationRequest, *, schema_only: bool
) -> dict[str, pd.DataFrame]:
    """Build small schema/sample frames without an OpenStreetMap fetch.

    Incident rows are probed through the normal vectorized pipeline against a
    static address pool (a single row for schema-only, ``SAMPLE_ROWS`` for a
    dry run); phone metrics are restricted to a single day so the preview stays
    small. Nothing is written to disk and the selected ``dataset`` and realism
    configuration are respected.
    """
    datasets: dict[str, pd.DataFrame] = {}
    if request.dataset in (DatasetKind.INCIDENTS, DatasetKind.ALL):
        probe_rows = SCHEMA_ROWS if schema_only else SAMPLE_ROWS
        probe = replace(request, rows=probe_rows)
        datasets["incidents"] = IncidentGenerator(
            StaticAddressProvider(_STATIC_ADDRESSES)
        ).generate(probe)
    if request.dataset in (DatasetKind.PHONE, DatasetKind.ALL):
        today = date.today()
        probe = replace(request, start_date=today, end_date=today)
        datasets["hourly_call_counts"] = HourlyCallCountGenerator().generate(probe)
    return datasets
