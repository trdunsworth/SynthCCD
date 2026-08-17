"""Schema and sample-preview helpers for dry runs and schema reports.

``--dry-run`` and ``--schema`` need a small peek at what a full run would
produce without hitting OpenStreetMap or writing files. This module runs
the real generators against a static address pool on a tiny row count and
assembles either preview frames (:func:`build_preview_datasets`) or a
serializable schema definition (:func:`build_schema_definition`) that
mirrors the manifest hash.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from .addresses import StaticAddressProvider
from .config import DatasetKind, GenerationRequest
from .constants import DATA_SCHEMA_VERSION
from .domain import Address
from .generators import HourlyCallCountGenerator, IncidentGenerator
from .manifest import _hash_schema

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
        today = date.today()  # noqa: DTZ011
        probe = replace(request, start_date=today, end_date=today)
        datasets["hourly_call_counts"] = HourlyCallCountGenerator().generate(probe)
    return datasets


def build_schema_definition(
    request: GenerationRequest,
) -> dict[str, Any]:
    """Build a serializable output-schema definition for the selected dataset.

    The column set and dtypes are derived from the same single-row probe used
    by ``--schema``/``--dry-run`` (static address pool, no OpenStreetMap fetch),
    so the definition reflects ``id_format``, ``--config``, ``country``, and
    emergency-number overrides. Includes the schema version, a deterministic
    ``schema_hash`` (matching the manifest/Parquet metadata hash), and
    package/environment provenance.
    """
    import platform
    import sys
    from importlib.metadata import version

    preview = build_preview_datasets(request, schema_only=True)
    try:
        package_version = version("SynthCCD")
    except Exception:
        package_version = "0.0.0-dev"

    return {
        "version": DATA_SCHEMA_VERSION,
        "schema_hash": _hash_schema(preview),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "package": "SynthCCD",
        "package_version": package_version,
        "python_version": (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        ),
        "platform": platform.platform(),
        "dataset": request.dataset.value,
        "datasets": {
            name: {col: str(dtype) for col, dtype in frame.dtypes.items()}
            for name, frame in preview.items()
        },
    }
