"""Tests for the vectorized Erlang-C and Erlang-A queueing models.

The scalar implementations in ``staff_models/`` are the independent reference:
they were written first, in plain Python, from the queueing-theory literature.
Every vectorized result here is checked against them rather than against a
hard-coded table, so the two implementations cannot silently diverge.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from synth911gen3.addresses import StaticAddressProvider
from synth911gen3.app import Synth911Application
from synth911gen3.config import DatasetKind, GenerationRequest, OutputFormat
from synth911gen3.domain import Address
from synth911gen3.generators.phone_metrics import _queue_service_level
from synth911gen3.generators.queueing import (
    erlang_a_analysis,
    erlang_c_mean_wait,
    erlang_c_service_level,
    erlang_c_wait_probability,
)
from synth911gen3.realism_config import RealismConfig

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_reference(module_name: str):
    """Import a scalar reference module from ``staff_models/`` by file path."""
    path = _REPO_ROOT / "staff_models" / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(f"_ref_{module_name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_reference_c = _load_reference("erlang_c")
_reference_a = _load_reference("erlang_a")


# Stable (offered load < servers) pairs spanning light to near-saturation.
_STABLE_PAIRS = [(a, c) for a in (0.5, 2.0, 5.0, 8.0, 12.5, 19.9) for c in (20, 40, 80) if a < c]


# ---------------------------------------------------------------------------
# Erlang C — agreement with the scalar reference
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("erlangs", "servers"), _STABLE_PAIRS)
def test_erlang_c_wait_probability_matches_scalar_reference(erlangs: float, servers: int) -> None:
    expected = _reference_c.wait_probability(erlangs, servers)
    assert float(erlang_c_wait_probability(erlangs, servers)) == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize(("erlangs", "servers"), _STABLE_PAIRS)
@pytest.mark.parametrize("threshold", [5.0, 15.0, 40.0])
def test_erlang_c_service_level_matches_scalar_reference(
    erlangs: float, servers: int, threshold: float
) -> None:
    expected = _reference_c.service_level(erlangs, servers, 1 / 240.0, threshold)
    got = float(erlang_c_service_level(erlangs, servers, 1 / 240.0, threshold))
    assert got == pytest.approx(expected, abs=1e-12)


def test_erlang_c_vectorized_matches_elementwise_calls() -> None:
    """One vector call must equal the same inputs evaluated one at a time."""
    loads = np.array([0.5, 3.0, 7.0, 11.0])
    servers = np.array([5.0, 5.0, 12.0, 30.0])
    vectorized = erlang_c_wait_probability(loads, servers)
    elementwise = np.array(
        [float(erlang_c_wait_probability(a, c)) for a, c in zip(loads, servers, strict=True)]
    )
    assert vectorized == pytest.approx(elementwise, abs=1e-15)


def test_erlang_c_wait_probability_rises_with_load() -> None:
    probabilities = erlang_c_wait_probability(np.array([1.0, 5.0, 9.0, 14.0]), 20)
    assert np.all(np.diff(probabilities) > 0)


def test_erlang_c_mean_wait_is_infinite_when_unstable() -> None:
    assert math.isinf(float(erlang_c_mean_wait(25.0, 10, 1 / 240.0)))
    assert float(erlang_c_mean_wait(5.0, 10, 1 / 240.0)) > 0.0


def test_erlang_c_saturates_rather_than_raising_when_overloaded() -> None:
    """A generator must degrade on an overloaded hour, not blow up."""
    assert float(erlang_c_wait_probability(50.0, 4)) == pytest.approx(1.0)
    assert float(erlang_c_wait_probability(0.0, 4)) == pytest.approx(1.0)
    assert float(erlang_c_service_level(50.0, 4, 1 / 240.0, 15.0)) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Erlang A — agreement with the scalar reference
# ---------------------------------------------------------------------------


_ERLANG_A_CASES = [
    (0.05, 1 / 240, 15, 1 / 60),
    (0.02, 1 / 300, 5, 1 / 45),
    (0.5, 1 / 200, 10, 1 / 90),
    (0.1, 1 / 120, 20, 1 / 30),
    (0.9, 1 / 240, 12, 1 / 120),
    (2.0, 1 / 240, 10, 1 / 60),
]


@pytest.mark.parametrize(("lam", "mu", "servers", "theta"), _ERLANG_A_CASES)
def test_erlang_a_matches_scalar_reference(
    lam: float, mu: float, servers: int, theta: float
) -> None:
    expected = _reference_a.analyze(lam=lam, mu=mu, c=servers, theta=theta)
    got = erlang_a_analysis(lam, mu, servers, theta)
    for field in (
        "delay_probability",
        "abandonment_probability",
        "mean_wait_time",
        "mean_wait_delayed",
        "mean_occupancy",
    ):
        assert float(getattr(got, field)[()]) == pytest.approx(expected[field], abs=1e-9), field


def test_erlang_a_stays_finite_where_erlang_c_diverges() -> None:
    """Patience is what bounds the queue: above unit load A stays finite."""
    over_subscribed = erlang_a_analysis(2.0, 1 / 240, 3, 1 / 60)
    assert math.isfinite(float(over_subscribed.mean_wait_delayed[()]))
    assert 0.0 <= float(over_subscribed.abandonment_probability[()]) <= 1.0
    assert math.isinf(float(erlang_c_mean_wait(2.0 * 240, 3, 1 / 240.0)))


def test_erlang_a_abandonment_rises_with_load() -> None:
    loads = np.array([0.02, 0.06, 0.12, 0.25, 0.5])
    abandonment = erlang_a_analysis(loads, 1 / 240, 8, 1 / 75).abandonment_probability
    assert np.all(np.diff(abandonment) > 0)


def test_erlang_a_impatient_callers_abandon_more() -> None:
    """Lower patience (higher theta) must mean more abandonment."""
    loads = np.array([0.08, 0.15, 0.3])
    patient = erlang_a_analysis(loads, 1 / 240, 6, 1 / 600).abandonment_probability
    impatient = erlang_a_analysis(loads, 1 / 240, 6, 1 / 20).abandonment_probability
    assert np.all(impatient > patient)


def test_erlang_a_vectorized_matches_elementwise_calls() -> None:
    loads = np.array([0.03, 0.08, 0.2, 0.45])
    servers = np.array([4.0, 9.0, 9.0, 16.0])
    vectorized = erlang_a_analysis(loads, 1 / 210, servers, 1 / 75).mean_wait_delayed
    elementwise = np.array(
        [
            float(erlang_a_analysis(lam, 1 / 210, int(c), 1 / 75).mean_wait_delayed[()])
            for lam, c in zip(loads, servers, strict=True)
        ]
    )
    assert vectorized == pytest.approx(elementwise, rel=1e-9)


# ---------------------------------------------------------------------------
# Integration — staffing must actually reach the generated data
# ---------------------------------------------------------------------------

_ADDRESSES = [
    Address("101 N Main St", "Kansas City", "Missouri"),
    Address("204 E 12th St", "Kansas City", "Missouri"),
    Address("55 W 39th St", "Kansas City", "Missouri"),
    Address("777 S Broadway Blvd", "Kansas City", "Missouri"),
]
_PROVIDER = StaticAddressProvider(_ADDRESSES)


def _phone(rows: int, days: int, pool: int, queue: bool) -> pd.DataFrame:
    realism = RealismConfig()
    realism.phone_metrics["queue_model_enabled"] = queue
    request = GenerationRequest(
        rows=rows,
        dataset=DatasetKind.PHONE,
        output_format=OutputFormat.PANDAS,
        seed=911,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, days),
        realism_config=realism,
        calltaker_pool_size=pool,
    )
    frame = Synth911Application(address_provider=_PROVIDER).generate(request).hourly_call_counts
    assert frame is not None
    return frame


def _received_columns(frame: pd.DataFrame) -> list[str]:
    return [c for c in frame.columns if c.endswith("calls_received")]


def _abandoned_columns(frame: pd.DataFrame) -> list[str]:
    return [c for c in frame.columns if c.endswith("calls_abandoned")]


def _abandonment_rate(frame: pd.DataFrame) -> float:
    received = frame[_received_columns(frame)].to_numpy().sum()
    abandoned = frame[_abandoned_columns(frame)].to_numpy().sum()
    return float(abandoned / received)


def test_queue_model_is_off_by_default() -> None:
    """The queue is opt-in, so the shipped defaults stay as calibrated.

    The tuned answer-time and abandonment values are end-to-end figures that
    already contain queueing, so switching the queue model on by default would
    charge the wait twice. Enabling it is a deliberate experimental treatment.
    """
    assert RealismConfig().phone_metrics["queue_model_enabled"] is False


def test_staffing_does_not_affect_phone_metrics_by_default() -> None:
    """With the queue off, staffing must not touch the phone-metrics dataset."""
    thin = _phone(rows=20_000, days=7, pool=4, queue=False)
    thick = _phone(rows=20_000, days=7, pool=400, queue=False)
    pd.testing.assert_frame_equal(thin[_abandoned_columns(thin)], thick[_abandoned_columns(thick)])
    pd.testing.assert_frame_equal(
        thin["nine_one_one_answered_15s_pct"].to_frame(),
        thick["nine_one_one_answered_15s_pct"].to_frame(),
    )


def test_queue_model_disabled_is_unchanged_by_staffing() -> None:
    """With the model off, staffing must not perturb the phone-metrics output."""
    thin = _phone(rows=5_000, days=7, pool=4, queue=False)
    thick = _phone(rows=5_000, days=7, pool=200, queue=False)
    pd.testing.assert_frame_equal(thin[_abandoned_columns(thin)], thick[_abandoned_columns(thick)])


def test_more_calltakers_reduce_abandonment() -> None:
    thin = _abandonment_rate(_phone(rows=20_000, days=7, pool=4, queue=True))
    thick = _abandonment_rate(_phone(rows=20_000, days=7, pool=96, queue=True))
    assert thin > thick


def test_queue_model_reaches_the_tuned_abandonment_floor() -> None:
    """Erlang-A only models queue hang-ups, so tuned rates must still hold below.

    With generous staffing the queue term is ~0 and the configured
    ``nine_one_one_abandonment_rate`` stands. If this fails, the model is
    replacing the tuned baseline instead of adding to it.
    """
    frame = _phone(rows=20_000, days=7, pool=400, queue=True)
    assert _abandonment_rate(frame) < 0.09


def test_more_calltakers_improve_answer_time_service_level() -> None:
    thin = _phone(rows=20_000, days=7, pool=4, queue=True)
    thick = _phone(rows=20_000, days=7, pool=96, queue=True)
    column = "nine_one_one_answered_15s_pct"
    assert thick[column].mean() > thin[column].mean()


def test_queue_service_level_is_a_probability() -> None:
    levels = _queue_service_level(
        [10.0, 15.0, 20.0, 40.0],
        p_wait=np.full(4, 0.45),
        decay=np.full(4, 0.02),
    )
    assert levels.shape == (4, 4)
    assert np.all(levels >= 0.0) and np.all(levels <= 1.0)
    # Service level is non-decreasing in the threshold.
    assert np.all(np.diff(levels, axis=0) >= 0.0)


def test_queue_service_level_tracks_staffing_without_a_reference() -> None:
    """No invented target utilisation sits between the caller's staffing and the output."""
    staffed_thinly = _queue_service_level([15.0], p_wait=np.array([0.9]), decay=np.array([0.002]))
    staffed_adequately = _queue_service_level(
        [15.0], p_wait=np.array([0.2]), decay=np.array([0.08])
    )
    assert float(staffed_thinly[0, 0]) < float(staffed_adequately[0, 0])


def test_queue_service_level_is_one_when_nobody_waits() -> None:
    levels = _queue_service_level([15.0], p_wait=np.array([0.0]), decay=np.array([0.05]))
    assert float(levels[0, 0]) == pytest.approx(1.0)


def test_sms_rtt_channel_is_not_collapsed_by_the_voice_queue() -> None:
    """Text is staffed separately, so cutting voice staff must not strand it.

    Exact equality is not assertable here: the shared RNG stream means the
    upstream voice-abandonment draws shift every downstream draw. What must hold
    is that the text channel does not track voice staffing the way 9-1-1 does.
    """
    thin = _phone(rows=20_000, days=7, pool=4, queue=True)
    thick = _phone(rows=20_000, days=7, pool=400, queue=True)
    voice = "nine_one_one_answered_15s_pct"
    text = "sms_rtt_answered_300s_pct"
    voice_gain = thick[voice].mean() - thin[voice].mean()
    text_gain = thick[text].mean() - thin[text].mean()
    assert voice_gain > 20.0, f"voice should track staffing, gained only {voice_gain:.1f}"
    assert abs(text_gain) < voice_gain / 4.0, (
        f"text channel moved {text_gain:.1f} with staffing; it should be largely unaffected"
    )
    assert thin[text].mean() > 30.0, "text engagement collapsed under thin voice staffing"


def test_opt_in_queue_model_responds_to_supplied_staffing() -> None:
    """The core research guarantee: staffing is an exogenous, effective input.

    With the queue model enabled, holding call volume fixed and varying only the
    supplied calltaker pool must move both abandonment and the answer-time
    service level. If this fails, staffing is no longer an independent variable
    and the queueing experiment is unrepresentable.
    """
    thin = _phone(rows=20_000, days=7, pool=4, queue=True)
    thick = _phone(rows=20_000, days=7, pool=400, queue=True)
    assert _abandonment_rate(thin) > _abandonment_rate(thick)
    column = "nine_one_one_answered_15s_pct"
    assert thick[column].mean() > thin[column].mean()


def test_opt_in_queue_model_is_deterministic_for_a_given_seed() -> None:
    first = _phone(rows=5_000, days=7, pool=12, queue=True)
    second = _phone(rows=5_000, days=7, pool=12, queue=True)
    pd.testing.assert_frame_equal(first, second)


def test_incident_queue_wait_rises_when_calltakers_are_cut() -> None:
    realism = RealismConfig()
    realism.phone_metrics["queue_model_enabled"] = True
    common = {
        "rows": 20_000,
        "dataset": DatasetKind.INCIDENTS,
        "output_format": OutputFormat.PANDAS,
        "seed": 911,
        "realism_config": realism,
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 1, 1),
    }
    thin = (
        Synth911Application(address_provider=_PROVIDER)
        .generate(GenerationRequest(calltaker_pool_size=4, **common))
        .incidents
    )
    thick = (
        Synth911Application(address_provider=_PROVIDER)
        .generate(GenerationRequest(calltaker_pool_size=768, **common))
        .incidents
    )
    assert thin is not None and thick is not None
    assert thin["pickup_delay_seconds"].mean() > thick["pickup_delay_seconds"].mean()


def test_queue_wait_does_not_delay_dispatch() -> None:
    """Queueing for an agent must not push ``time_call_enters_queue`` later.

    Callers waiting to be answered have not started an interview, so the wait
    belongs in the pickup slot; folding it into ``interview_seconds`` would make
    it look as though callers queueing delayed dispatch, which is backwards.
    """
    realism = RealismConfig()
    realism.phone_metrics["queue_model_enabled"] = True
    request = GenerationRequest(
        rows=20_000,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        seed=911,
        realism_config=realism,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        calltaker_pool_size=4,
    )
    frame = Synth911Application(address_provider=_PROVIDER).generate(request).incidents
    assert frame is not None
    # Timestamps stay causally ordered regardless of how long callers held.
    assert (frame["time_call_closed"] >= frame["call_start_time"]).all()
    assert (frame["time_call_enters_queue"] >= frame["time_phone_pickup"]).all()
    assert (frame["time_phone_pickup"] >= frame["call_start_time"]).all()
