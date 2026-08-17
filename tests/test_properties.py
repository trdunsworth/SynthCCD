"""Property-based tests for the synthetic-data generators.

The rest of the suite checks fixed seeds and fixed parameter values. These
tests use hypothesis to assert *statistical invariants* that must hold for
every valid seed / parameter combination:

- distribution shapes: lognormal timing draws stay within their clip bounds
  and track the configured per-agency/per-priority means; elapsed-second
  columns are never negative; generated category fractions converge to the
  configured weights.
- weight sums: every weight table normalizes to 1.0 (both the normalizing
  helper and the full YAML round trip) and the sample-draw helpers stay
  normalized and ordered.
- temporal patterns: call-lifecycle timestamps are strictly ordered and each
  derived column matches its source timestamps exactly; call-start hours track
  the configured diurnal weights; phone metrics keep abandonment <= received,
  answer-time curves monotone, and volume/abandonment rates tracking their
  configured targets.
"""

import re
import tempfile
from datetime import date
from pathlib import Path
from uuid import UUID

import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy.stats import chi2

from synth911gen3.addresses import StaticAddressProvider
from synth911gen3.app import Synth911Application
from synth911gen3.config import DatasetKind, GenerationRequest, IdFormat, OutputFormat
from synth911gen3.domain import Address
from synth911gen3.generators.incidents import (
    _DAY_ABBREVIATIONS,
    _distribute,
    _lognormal_seconds,
    _zipf_weights,
)
from synth911gen3.generators.phone_metrics import HourlyCallCountGenerator
from synth911gen3.realism_config import RealismConfig

_ADDRESSES = [
    Address("101 N Main St", "Kansas City", "Missouri"),
    Address("204 E 12th St", "Kansas City", "Missouri"),
    Address("55 W 39th St", "Kansas City", "Missouri"),
    Address("777 S Broadway Blvd", "Kansas City", "Missouri"),
    Address("890 N Oak Trafficway NW", "Kansas City", "Missouri"),
]
_PROVIDER = StaticAddressProvider(_ADDRESSES)

# Threshold used for every goodness-of-fit assertion: a 0.05% chance of a
# type-1 error per example, which keeps the whole suite flake-free while still
# catching distributional regressions.
_ALPHA = 0.9995

_SECOND_COLUMNS = (
    "pickup_delay_seconds",
    "pre_cad_offset_seconds",
    "interview_seconds",
    "dispatch_queue_seconds",
    "turnout_seconds",
    "travel_seconds",
    "on_scene_seconds",
    "closeout_seconds",
    "phone_duration_seconds",
    "total_elapsed_seconds",
)

_TIMING_FIELD_MAP = {
    "interview_seconds": "interview_mean",
    "dispatch_queue_seconds": "dispatch_mean",
    "turnout_seconds": "turnout_mean",
    "travel_seconds": "travel_mean",
    "on_scene_seconds": "scene_mean",
    "closeout_seconds": "closeout_mean",
}

_REFERENCE_PATTERN = re.compile(r"^[A-Z]+-\d{6}-\d{6}$")

_POSITIVE_FLOAT = st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False)


def _incidents(seed: int, rows: int, **overrides: object) -> pd.DataFrame:
    request = GenerationRequest(
        rows=rows,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        seed=seed,
        **overrides,
    )
    result = Synth911Application(address_provider=_PROVIDER).generate(request)
    assert result.incidents is not None
    return result.incidents


def _phone_frame(seed: int, rows: int, days: int) -> pd.DataFrame:
    request = GenerationRequest(
        rows=rows,
        dataset=DatasetKind.PHONE,
        output_format=OutputFormat.PANDAS,
        seed=seed,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, days),
    )
    return HourlyCallCountGenerator().generate(request)


def _chi2_stat(observed: pd.Series, expected: dict) -> float:
    """Pearson chi-square statistic of observed counts against a probability map."""
    labels = list(expected)
    total = int(observed.sum())
    obs = np.asarray([observed.get(label, 0) for label in labels], dtype=float)
    exp = np.asarray([expected[label] * total for label in labels], dtype=float)
    return float(np.sum((obs - exp) ** 2 / exp))


def _delta(frame: pd.DataFrame, later: str, earlier: str) -> np.ndarray:
    return (frame[later] - frame[earlier]).dt.total_seconds().to_numpy()


# ---------------------------------------------------------------------------
# Distribution shapes
# ---------------------------------------------------------------------------


@given(
    mean=st.floats(min_value=0.5, max_value=100_000.0, allow_nan=False, allow_infinity=False),
    sigma=st.floats(min_value=0.05, max_value=2.0, allow_nan=False, allow_infinity=False),
    minimum=st.integers(min_value=0, max_value=100),
    maximum=st.one_of(st.none(), st.integers(min_value=1, max_value=10**6)),
    size=st.integers(min_value=1, max_value=5_000),
)
@settings(max_examples=40, deadline=None)
def test_lognormal_seconds_respects_clip_bounds(mean, sigma, minimum, maximum, size):
    if maximum is not None and maximum < minimum:
        return
    rng = np.random.default_rng(seed=1234)
    values = _lognormal_seconds(rng, mean, sigma, size=size, minimum=minimum, maximum=maximum)
    assert values.shape == (size,)
    assert values.dtype == np.int64
    assert (values >= minimum).all()
    if maximum is not None:
        assert (values <= maximum).all()


@given(
    mean=st.floats(min_value=50.0, max_value=2_000.0, allow_nan=False, allow_infinity=False),
    sigma=st.floats(min_value=0.2, max_value=0.9, allow_nan=False, allow_infinity=False),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
)
@settings(max_examples=5, deadline=None)
def test_lognormal_seconds_mean_tracks_target_when_unclipped(mean, sigma, seed):
    # With the clip ceiling far above the distribution's tail, the sample mean
    # must track the requested mean: mu is derived as log(mean) - sigma^2 / 2.
    rng = np.random.default_rng(seed)
    values = _lognormal_seconds(rng, mean, sigma, size=20_000, maximum=int(mean * 50))
    estimate = float(values.mean())
    assert abs(estimate - mean) / mean < 0.15
    assert (values >= 0).all()


@given(
    seed=st.integers(min_value=0, max_value=2**31 - 1),
    rows=st.integers(min_value=50, max_value=300),
)
@settings(max_examples=10, deadline=None)
def test_incident_elapsed_columns_are_non_negative(seed, rows):
    frame = _incidents(seed, rows)
    for column in _SECOND_COLUMNS:
        assert (frame[column] >= 0).all(), column
    assert (frame["time_call_closed"] >= frame["call_start_time"]).all()


@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=3, deadline=None)
def test_incident_timing_means_track_profiles(seed):
    config = RealismConfig()
    frame = _incidents(seed, rows=3_000, realism_config=config)
    for field, profile_key in _TIMING_FIELD_MAP.items():
        for agency, priorities in config.time_profiles.items():
            for priority, profile in priorities.items():
                subset = frame.loc[
                    (frame["agency"] == agency) & (frame["priority"] == priority), field
                ]
                if len(subset) < 40:
                    continue
                target = float(profile[profile_key])
                estimate = float(subset.mean())
                tolerance = max(0.35 * target, 10.0)
                assert abs(estimate - target) <= tolerance, (
                    f"{agency} priority {priority} {field}: mean {estimate:.1f}s "
                    f"vs configured {target}s"
                )


# ---------------------------------------------------------------------------
# Weight sums
# ---------------------------------------------------------------------------


@given(
    weights=st.dictionaries(
        st.text(min_size=1),
        st.floats(min_value=0.001, max_value=1_000.0, allow_nan=False, allow_infinity=False),
        min_size=1,
    )
)
@settings(max_examples=20, deadline=None)
def test_normalize_weights_sums_to_one(weights):
    normalized = RealismConfig._normalize_weights(weights)
    assert set(normalized) == {str(key) for key in weights}
    assert all(value > 0 for value in normalized.values())
    assert abs(sum(normalized.values()) - 1.0) < 1e-9


@given(count=st.integers(min_value=1, max_value=200))
@settings(max_examples=20, deadline=None)
def test_zipf_weights_normalized_and_strictly_decreasing(count):
    weights = _zipf_weights(count)
    assert weights.shape == (count,)
    assert (weights > 0).all()
    assert (np.diff(weights) < 0).all()
    assert abs(float(weights.sum()) - 1.0) < 1e-9


@given(
    amount=st.integers(min_value=0, max_value=10**6),
    slots=st.integers(min_value=1, max_value=64),
)
@settings(max_examples=20, deadline=None)
def test_distribute_sums_to_max_of_amount_and_one(amount, slots):
    parts = _distribute(amount, slots)
    assert len(parts) == slots
    assert sum(parts) == max(amount, 1)
    assert max(parts) - min(parts) <= 1


@st.composite
def _mutated_config(draw):
    """A default realism config with every weight table randomized."""
    config = RealismConfig()
    config.agency_weights = {
        agency: draw(
            st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False)
        )
        for agency in config.agency_weights
    }
    for agency in config.priority_weights:
        config.priority_weights[agency] = {
            priority: draw(
                st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False)
            )
            for priority in config.priority_weights[agency]
        }
    for agency in config.problem_profiles:
        for priority, pool in config.problem_profiles[agency].items():
            raw = [draw(_POSITIVE_FLOAT) for _ in pool]
            total = sum(raw)
            config.problem_profiles[agency][priority] = [
                (name, weight / total) for (name, _), weight in zip(pool, raw)
            ]
    for agency, profiles in config.disposition_profiles.items():
        raw = [draw(_POSITIVE_FLOAT) for _ in profiles]
        total = sum(raw)
        config.disposition_profiles[agency] = [
            (label, weight / total) for (label, _), weight in zip(profiles, raw)
        ]
    config.hourly_weights = np.asarray([draw(_POSITIVE_FLOAT) for _ in range(24)], dtype=float)
    return config


@given(config=_mutated_config())
@settings(max_examples=5, deadline=None)
def test_yaml_roundtrip_preserves_normalized_weights(config):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "realism.yaml"
        config.to_yaml(path)
        restored = RealismConfig.from_yaml(path)

    assert abs(sum(restored.agency_weights.values()) - 1.0) < 1e-9
    for agency, weights in restored.priority_weights.items():
        assert abs(sum(weights.values()) - 1.0) < 1e-9, agency
    for agency, priorities in restored.problem_profiles.items():
        for priority, pool in priorities.items():
            total = sum(weight for _, weight in pool)
            assert abs(total - 1.0) < 1e-9, (agency, priority)
    for agency, profiles in restored.disposition_profiles.items():
        total = sum(weight for _, weight in profiles)
        assert abs(total - 1.0) < 1e-9, agency
    assert restored.hourly_weights.shape == (24,)
    assert abs(float(restored.hourly_weights.sum()) - 1.0) < 1e-9


@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=2, deadline=None)
def test_category_fractions_track_config_weights(seed):
    config = RealismConfig()
    frame = _incidents(seed, rows=6_000, realism_config=config)

    observed_agency = frame["agency"].value_counts()
    assert _chi2_stat(observed_agency, config.agency_weights) < chi2.ppf(
        _ALPHA, len(config.agency_weights) - 1
    )

    for agency, priority_map in config.priority_weights.items():
        observed = frame.loc[frame["agency"] == agency, "priority"].value_counts()
        assert _chi2_stat(observed, priority_map) < chi2.ppf(_ALPHA, len(priority_map) - 1), agency

    observed_reception = frame["method_of_call_reception"].value_counts()
    assert _chi2_stat(observed_reception, config.call_reception_weights) < chi2.ppf(
        _ALPHA, len(config.call_reception_weights) - 1
    )

    for agency, profiles in config.disposition_profiles.items():
        expected = dict(profiles)
        observed = frame.loc[frame["agency"] == agency, "call_disposition"].value_counts()
        assert _chi2_stat(observed, expected) < chi2.ppf(_ALPHA, len(expected) - 1), agency


# ---------------------------------------------------------------------------
# Temporal patterns
# ---------------------------------------------------------------------------


@given(
    seed=st.integers(min_value=0, max_value=2**31 - 1),
    rows=st.integers(min_value=10, max_value=400),
    id_format=st.sampled_from([IdFormat.INTEGER, IdFormat.GUID]),
    date_range=st.tuples(
        st.dates(min_value=date(2020, 1, 1), max_value=date(2026, 12, 31)),
        st.dates(min_value=date(2020, 1, 1), max_value=date(2026, 12, 31)),
    ).filter(lambda pair: pair[0] <= pair[1]),
)
@settings(max_examples=8, deadline=None)
def test_incident_temporal_invariants(seed, rows, id_format, date_range):
    start, end = date_range
    frame = _incidents(seed, rows, id_format=id_format, start_date=start, end_date=end)
    assert len(frame) == rows

    if id_format is IdFormat.INTEGER:
        assert frame["id_number"].tolist() == list(range(1, rows + 1))
    else:
        ids = frame["id_number"].tolist()
        assert len(set(ids)) == rows
        for value in ids:
            assert UUID(str(value)).version == 4

    for agency, sub in frame.groupby("agency"):
        assert sub["internal_reference_number"].is_unique
    for ref in frame["internal_reference_number"]:
        assert _REFERENCE_PATTERN.fullmatch(str(ref)), ref

    # Call starts stay inside the requested window.
    start_ts = np.datetime64(start.isoformat()).astype("datetime64[s]")
    end_ts = np.datetime64(end.isoformat()).astype("datetime64[s]") + np.timedelta64(1, "D")
    assert (frame["call_start_time"].to_numpy() >= start_ts).all()
    assert (frame["call_start_time"].to_numpy() < end_ts).all()

    # The lifecycle chain is non-decreasing and each derived column equals the
    # delta of its two source timestamps exactly.
    assert np.array_equal(
        _delta(frame, "incident_start_time", "call_start_time"),
        frame["pre_cad_offset_seconds"].to_numpy(),
    )
    pickup_minus_incident = _delta(frame, "time_phone_pickup", "incident_start_time")
    assert (pickup_minus_incident >= -3.0).all()  # pre_cad_offset <= 3
    late_pickup = frame["pickup_delay_seconds"] >= 3
    assert (pickup_minus_incident[late_pickup] >= 0.0).all()

    assert np.array_equal(
        _delta(frame, "time_call_enters_queue", "time_phone_pickup"),
        frame["interview_seconds"].to_numpy(),
    )
    assigned_offset = _delta(frame, "time_first_unit_assigned", "time_phone_pickup")
    assert (assigned_offset >= 0.0).all()
    # Dispatch can start mid-call, so the queue-relative delay can exceed the
    # queue time alone; it can never be less than it.
    assert (assigned_offset >= frame["dispatch_queue_seconds"].to_numpy()).all()

    assert np.array_equal(
        _delta(frame, "time_unit_enroute", "time_first_unit_assigned"),
        frame["turnout_seconds"].to_numpy(),
    )
    assert np.array_equal(
        _delta(frame, "time_unit_arrived", "time_unit_enroute"),
        frame["travel_seconds"].to_numpy(),
    )
    assert np.array_equal(
        _delta(frame, "time_last_unit_cleared", "time_unit_arrived"),
        frame["on_scene_seconds"].to_numpy(),
    )
    assert np.array_equal(
        _delta(frame, "time_call_closed", "time_last_unit_cleared"),
        frame["closeout_seconds"].to_numpy(),
    )
    assert np.array_equal(
        _delta(frame, "time_phone_disconnect", "time_phone_pickup"),
        frame["phone_duration_seconds"].to_numpy(),
    )
    assert np.array_equal(
        _delta(frame, "time_call_closed", "call_start_time"),
        frame["total_elapsed_seconds"].to_numpy(),
    )
    # No incident stays open for more than a day, even late on the last day.
    assert (frame["total_elapsed_seconds"] <= 86_400).all()

    # Derived day-of-week / hour / week columns match the call-start timestamp.
    assert (frame["hour"] == frame["call_start_time"].dt.hour).all()
    assert (frame["week_no"] == frame["call_start_time"].dt.isocalendar().week).all()
    expected_dow = np.asarray(_DAY_ABBREVIATIONS, dtype=str)[
        frame["call_start_time"].dt.dayofweek.to_numpy()
    ]
    assert (frame["dow"].to_numpy() == expected_dow).all()


@given(
    seed=st.integers(min_value=0, max_value=2**31 - 1),
    weights=st.lists(
        st.floats(min_value=0.5, max_value=10.0, allow_nan=False, allow_infinity=False),
        min_size=24,
        max_size=24,
    ),
)
@settings(max_examples=2, deadline=None)
def test_call_hours_track_hourly_weights(seed, weights):
    normalized = np.asarray(weights, dtype=float)
    normalized = normalized / normalized.sum()
    config = RealismConfig()
    config.hourly_weights = normalized
    frame = _incidents(seed, rows=10_000, realism_config=config)

    expected = {hour: float(normalized[hour]) for hour in range(24)}
    observed = frame["hour"].value_counts(sort=False)
    total = int(observed.sum())
    assert _chi2_stat(observed, expected) < chi2.ppf(_ALPHA, 23)
    for hour in range(24):
        assert abs(observed.get(hour, 0) / total - normalized[hour]) < 0.03, hour


@given(
    seed=st.integers(min_value=0, max_value=2**31 - 1),
    rows=st.integers(min_value=1_000, max_value=30_000),
    days=st.integers(min_value=1, max_value=7),
)
@settings(max_examples=3, deadline=None)
def test_phone_metrics_invariants(seed, rows, days):
    frame = _phone_frame(seed, rows, days)
    assert len(frame) == days * 24
    assert (frame["hour_of_day"] == frame["hour_start"].dt.hour).all()

    for column in frame.columns:
        if column.endswith("_calls_received") or column == "outbound_calls_placed":
            assert (frame[column] >= 0).all(), column

    for prefix in ("nine_one_one", "non_emergency"):
        received = frame[f"{prefix}_calls_received"]
        abandoned = frame[f"{prefix}_calls_abandoned"]
        assert (abandoned >= 0).all()
        assert (abandoned <= received).all()

    # Answer-time percentages are bounded and non-decreasing in threshold.
    for line in ("nine_one_one_answered", "non_emergency_answered"):
        columns = [c for c in frame.columns if c.startswith(line)]
        assert columns, line
        values = frame[columns].to_numpy(dtype=float)
        assert (values >= 0.0).all() and (values <= 100.0).all()
        assert (np.diff(values, axis=1) >= -0.11).all(), line


@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=2, deadline=None)
def test_phone_volume_tracks_hourly_load(seed):
    frame = _phone_frame(seed, rows=20_000, days=7)
    config = RealismConfig()
    weights = config.hourly_weights
    average = float(weights.mean())
    hour = frame["hour_of_day"].to_numpy()
    busy = weights[hour] / average
    weekend = np.where(
        np.isin(frame["hour_start"].dt.dayofweek.to_numpy(), (4, 5)),
        float(config.phone_metrics["weekend_multiplier"]),
        1.0,
    )
    busy = busy * weekend
    received = frame["nine_one_one_calls_received"].to_numpy(dtype=float)
    correlation = float(np.corrcoef(busy, received)[0, 1])
    assert correlation > 0.5, correlation


@given(
    seed=st.integers(min_value=0, max_value=2**31 - 1),
    rows=st.integers(min_value=10_000, max_value=50_000),
)
@settings(max_examples=3, deadline=None)
def test_phone_abandonment_tracks_configured_rate(seed, rows):
    frame = _phone_frame(seed, rows, days=7)
    config = RealismConfig()
    base = float(config.phone_metrics["nine_one_one_abandonment_rate"])
    night = float(config.phone_metrics["night_abandonment_increment"])
    hour = frame["hour_of_day"].to_numpy()
    rate = base + np.where(hour <= 5, night, 0.0)
    received = frame["nine_one_one_calls_received"].to_numpy()
    abandoned = frame["nine_one_one_calls_abandoned"].to_numpy()
    expected = float(np.sum(rate * received) / np.sum(received))
    observed = float(np.sum(abandoned) / np.sum(received))
    assert abs(observed - expected) < 0.012, (observed, expected)
