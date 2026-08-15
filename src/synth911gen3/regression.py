"""Statistical regression signatures for the synthetic-data generators.

The generators are deterministic for a given seed: the same seed and realism
configuration produce byte-identical datasets. That determinism lets us freeze
a *signature* of key statistics -- agency/priority/reception/disposition
fractions, per-cell timing means, hourly call-shape, and phone-metrics rates --
and then regenerate it on every test run. If the realism knobs drift (weights,
time profiles, phone metrics), the regenerated signature no longer matches the
committed baseline and the regression suite fails.

The baseline lives at ``tests/regression_baseline.json`` and is refreshed with
``scripts/update_regression_baseline.py`` whenever realism is *intentionally*
changed. See REALISMGUIDE.md for the workflow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from synth911gen3.addresses import StaticAddressProvider
from synth911gen3.app import Synth911Application
from synth911gen3.config import DatasetKind, GenerationRequest, OutputFormat
from synth911gen3.constants import DATA_SCHEMA_VERSION
from synth911gen3.domain import Address
from synth911gen3.manifest import _hash_realism_config
from synth911gen3.realism_config import RealismConfig

DEFAULT_BASELINE_SEED = 4242
DEFAULT_INCIDENT_ROWS = 20_000
DEFAULT_PHONE_ROWS = 100_000
DEFAULT_PHONE_DAYS = 28
DEFAULT_BASELINE_START = date(2026, 1, 1)
DEFAULT_BASELINE_END = date(2026, 12, 31)

_TIMING_FIELDS = (
    "interview_seconds",
    "dispatch_queue_seconds",
    "turnout_seconds",
    "travel_seconds",
    "on_scene_seconds",
    "closeout_seconds",
    "phone_duration_seconds",
)

_ADDRESS_POOL = [
    Address("101 N Main St", "Kansas City", "Missouri"),
    Address("204 E 12th St", "Kansas City", "Missouri"),
    Address("55 W 39th St", "Kansas City", "Missouri"),
    Address("777 S Broadway Blvd", "Kansas City", "Missouri"),
    Address("890 N Oak Trafficway NW", "Kansas City", "Missouri"),
]


@dataclass(frozen=True)
class RegressionTolerances:
    """Pass/fail bounds for signature comparison.

    Absolute bounds are expressed in the same units as the statistic (a
    fraction 0..1, a rate 0..1, a percentage 0..100). Relative bounds apply to
    timing means. Defaults sit at roughly 4-6 sampling standard errors for the
    default baseline sizes, so harmless pipeline shuffles pass while realism
    parameter drift trips the suite.
    """

    fraction_abs: float = 0.03
    mean_rel: float = 0.10
    mean_abs_floor: float = 2.0
    rate_abs: float = 0.005
    pct_abs: float = 2.0
    hour_abs: float = 0.01


def _normalized_counts(values: np.ndarray) -> dict[str, float]:
    """Unique-value counts as normalized fractions, keyed by string label."""
    labels, counts = np.unique(values, return_counts=True)
    total = int(counts.sum())
    if total == 0:
        return {}
    return {str(label): float(count / total) for label, count in zip(labels, counts)}


def incident_signature(frame: pd.DataFrame) -> dict[str, float]:
    """Flat map of statistic name -> value for one incident dataset.

    Keys are grouped by prefix so the comparator can apply the right
    tolerance: ``agency.`` / ``priority.`` / ``reception.`` / ``disposition.``
    / ``problem.`` are absolute fractions, ``hour.`` is an absolute fraction
    with a tighter bound, and ``timing.`` / ``total_elapsed_*`` are relative
    means.
    """
    signature: dict[str, float] = {}

    agency_values = frame["agency"].to_numpy()
    priority_values = frame["priority"].to_numpy()
    reception_values = frame["method_of_call_reception"].to_numpy()
    hour_values = frame["hour"].to_numpy()
    disposition_values = frame["call_disposition"].to_numpy()
    problem_values = frame["problem_nature"].to_numpy()

    signature.update({f"agency.{k}": v for k, v in _normalized_counts(agency_values).items()})
    signature.update(
        {f"reception.{k}": v for k, v in _normalized_counts(reception_values).items()}
    )

    observed_pairs: set[tuple[str, int]] = set()
    for agency, priority in zip(agency_values, priority_values, strict=False):
        observed_pairs.add((str(agency), int(priority)))
    for agency, priority in sorted(observed_pairs):
        cell_mask = (agency_values == agency) & (priority_values == priority)
        if not cell_mask.any():
            continue
        for field in _TIMING_FIELDS:
            field_values = frame[field].to_numpy()
            signature[f"timing.{agency}.{priority}.{field}"] = float(
                field_values[cell_mask].mean()
            )

    for agency in np.unique(agency_values):
        agency_mask = agency_values == agency
        for label, fraction in _normalized_counts(disposition_values[agency_mask]).items():
            signature[f"disposition.{agency}.{label}"] = fraction
        for label, fraction in _normalized_counts(problem_values[agency_mask]).items():
            signature[f"problem.{agency}.{label}"] = fraction

    elapsed = frame["total_elapsed_seconds"].to_numpy()
    signature["total_elapsed_mean"] = float(elapsed.mean())
    signature["total_elapsed_median"] = float(np.median(elapsed))

    total_hours = int(hour_values.size)
    hour_counts = np.bincount(hour_values.astype(np.int64), minlength=24)
    for hour in range(24):
        signature[f"hour.{hour}"] = (
            float(hour_counts[hour] / total_hours) if total_hours else 0.0
        )

    return signature


def phone_signature(frame: pd.DataFrame) -> dict[str, float]:
    """Flat map of statistic name -> value for one hourly phone-metrics dataset."""
    received_911 = frame["nine_one_one_calls_received"].to_numpy()
    received_non_emergency = frame["non_emergency_calls_received"].to_numpy()
    abandoned_911 = frame["nine_one_one_calls_abandoned"].to_numpy()
    abandoned_non_emergency = frame["non_emergency_calls_abandoned"].to_numpy()

    signature: dict[str, float] = {
        "phone.received_911_per_hour": float(received_911.mean()),
        "phone.received_non_emergency_per_hour": float(received_non_emergency.mean()),
        "phone.outbound_per_hour": float(frame["outbound_calls_placed"].to_numpy().mean()),
    }

    total_911 = float(received_911.sum())
    total_non_emergency = float(received_non_emergency.sum())
    signature["phone.911_abandonment_rate"] = (
        float(abandoned_911.sum() / total_911) if total_911 else 0.0
    )
    signature["phone.non_emergency_abandonment_rate"] = (
        float(abandoned_non_emergency.sum() / total_non_emergency)
        if total_non_emergency
        else 0.0
    )
    signature["phone.911_answered_10s_mean"] = float(
        frame["nine_one_one_answered_10s_pct"].to_numpy().mean()
    )
    signature["phone.911_answered_40s_mean"] = float(
        frame["nine_one_one_answered_40s_pct"].to_numpy().mean()
    )
    return signature


def _tolerance_for(
    key: str, tolerances: RegressionTolerances, baseline_value: float
) -> float:
    if key.startswith("hour."):
        return tolerances.hour_abs
    if key.startswith("phone."):
        if "abandonment_rate" in key:
            return tolerances.rate_abs
        if "answered" in key:
            return tolerances.pct_abs
        return max(tolerances.mean_rel * abs(baseline_value), 1.0)
    if key.startswith("timing.") or key.startswith("total_elapsed"):
        return max(tolerances.mean_rel * abs(baseline_value), tolerances.mean_abs_floor)
    return tolerances.fraction_abs


def compare(
    current: dict[str, float],
    baseline: dict[str, float],
    tolerances: RegressionTolerances | None = None,
) -> list[str]:
    """Return human-readable mismatches between ``current`` and ``baseline``.

    An empty list means the signature is within tolerance. Keys present in one
    map but not the other are reported as drift too, so adding a statistic to
    the signature forces a baseline refresh.
    """
    tolerance = tolerances or RegressionTolerances()
    issues: list[str] = []
    for key in sorted(set(baseline) | set(current)):
        base = baseline.get(key)
        cur = current.get(key)
        if base is None:
            issues.append(f"{key}: present in current ({cur:.4g}) but not in baseline")
            continue
        if cur is None:
            issues.append(f"{key}: present in baseline ({base:.4g}) but not in current")
            continue
        allowed = _tolerance_for(key, tolerance, base)
        delta = abs(cur - base)
        if delta > allowed:
            issues.append(
                f"{key}: baseline {base:.4g}, current {cur:.4g} "
                f"(delta {delta:.4g} > tolerance {allowed:.4g})"
            )
    return issues


def build_signature(
    seed: int = DEFAULT_BASELINE_SEED,
    incident_rows: int = DEFAULT_INCIDENT_ROWS,
    phone_rows: int = DEFAULT_PHONE_ROWS,
    phone_days: int = DEFAULT_PHONE_DAYS,
    start_date: date = DEFAULT_BASELINE_START,
    end_date: date = DEFAULT_BASELINE_END,
) -> tuple[dict[str, float], dict[str, float]]:
    """Generate reference datasets with the fixed seed and return their signatures.

    Both datasets use the same seed (the phone generator derives its own RNG
    stream internally). No files are written; the frames exist only in memory.
    """
    provider = StaticAddressProvider(_ADDRESS_POOL)
    app = Synth911Application(address_provider=provider)

    incident_request = GenerationRequest(
        rows=incident_rows,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        seed=seed,
        start_date=start_date,
        end_date=end_date,
    )
    incident_result = app.generate(incident_request)
    assert incident_result.incidents is not None

    phone_end = date.fromordinal(start_date.toordinal() + phone_days - 1)
    phone_request = GenerationRequest(
        rows=phone_rows,
        dataset=DatasetKind.PHONE,
        output_format=OutputFormat.PANDAS,
        seed=seed,
        start_date=start_date,
        end_date=phone_end,
    )
    phone_result = app.generate(phone_request)
    assert phone_result.hourly_call_counts is not None

    return incident_signature(incident_result.incidents), phone_signature(
        phone_result.hourly_call_counts
    )


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return version("synth911gen3")
    except Exception:
        return "0.0.0-dev"


def build_baseline(
    seed: int = DEFAULT_BASELINE_SEED,
    incident_rows: int = DEFAULT_INCIDENT_ROWS,
    phone_rows: int = DEFAULT_PHONE_ROWS,
    phone_days: int = DEFAULT_PHONE_DAYS,
    start_date: date = DEFAULT_BASELINE_START,
    end_date: date = DEFAULT_BASELINE_END,
) -> dict:
    """Return a full baseline document: metadata plus both signatures."""
    incident_sig, phone_sig = build_signature(
        seed=seed,
        incident_rows=incident_rows,
        phone_rows=phone_rows,
        phone_days=phone_days,
        start_date=start_date,
        end_date=end_date,
    )
    return {
        "meta": {
            "schema_version": DATA_SCHEMA_VERSION,
            "package_version": _package_version(),
            "realism_config_hash": _hash_realism_config(RealismConfig()),
            "seed": seed,
            "incident_rows": incident_rows,
            "phone_rows": phone_rows,
            "phone_days": phone_days,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "incidents": incident_sig,
        "phone": phone_sig,
    }


def save_baseline(signature: dict, path: Path) -> None:
    """Write a baseline document as deterministic, sorted JSON."""
    path.write_text(
        json.dumps(signature, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def load_baseline(path: Path) -> dict:
    """Load a baseline document previously written by :func:`save_baseline`."""
    return json.loads(path.read_text(encoding="utf-8"))
