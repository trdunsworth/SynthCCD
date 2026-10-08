"""Tests for mm_c_k. Run with ``pytest test_mm_c_k.py`` or ``python test_mm_c_k.py``."""

from __future__ import annotations

import heapq
import math
import random

import pytest

import mm_c_k as m
from mm_c_k import MMCK


# ---- independent reference implementations --------------------------------
def erlang_b(a: float, c: int) -> float:
    b = 1.0
    for n in range(1, c + 1):
        b = a * b / (n + a * b)
    return b


def erlang_c(a: float, c: int) -> float:
    b = erlang_b(a, c)
    return b / (1.0 - (a / c) * (1.0 - b))


def solve_balance(a: float, c: int, k: int) -> list[float]:
    """Solve global balance by forward substitution with exact fractions."""
    from fractions import Fraction

    a_f = Fraction(a).limit_denominator(10**9)
    w = [Fraction(1)]
    for n in range(1, k + 1):
        w.append(w[-1] * a_f / min(n, c))
    s = sum(w)
    return [float(x / s) for x in w]


# ---- correctness against known limits -------------------------------------
@pytest.mark.parametrize("a,c", [(8.0, 10), (3.5, 5), (40.0, 45), (60.0, 50)])
def test_k_equals_c_is_erlang_b(a, c):
    assert m.blocking_probability(a, c, c) == pytest.approx(erlang_b(a, c), rel=1e-12)
    assert m.queued_probability(a, c, c) == 0.0
    assert m.mean_queue_length(a, c, c) == 0.0


@pytest.mark.parametrize("a,c", [(8.0, 10), (40.0, 45), (95.0, 100)])
def test_large_k_approaches_erlang_c(a, c):
    model = MMCK.from_erlangs(a, c, c + 4000)
    assert model.queued_probability == pytest.approx(erlang_c(a, c), rel=1e-9)
    # Erlang C: Wq = C(a,c) / (c*mu - lam), with mu = 1
    assert model.mean_wait == pytest.approx(erlang_c(a, c) / (c - a), rel=1e-6)


def test_matches_balance_equations():
    a, c, k = 8.0, 10, 15
    ref = solve_balance(a, c, k)
    model = MMCK.from_erlangs(a, c, k)
    assert list(model.pi) == pytest.approx(ref, rel=1e-9)
    assert model.blocking_probability == pytest.approx(0.030038033652419, rel=1e-9)
    assert model.mean_queue_length == pytest.approx(
        sum((n - c) * ref[n] for n in range(c + 1, k + 1)), rel=1e-9
    )


def test_overloaded_system_has_steady_state():
    # offered load above c is fine for finite K; blocking tends to 1 - c/a
    assert m.blocking_probability(20.0, 10, 15) == pytest.approx(0.5011050672983691)
    assert m.blocking_probability(20.0, 10, 5000) == pytest.approx(1 - 10 / 20, abs=1e-6)


# ---- identities -----------------------------------------------------------
@pytest.mark.parametrize("a,c,k", [(8.0, 10, 15), (30.0, 25, 40), (12.0, 12, 12)])
def test_identities(a, c, k):
    model = MMCK.from_erlangs(a, c, k)
    assert math.fsum(model.pi) == pytest.approx(1.0, abs=1e-12)
    # L = Lq + mean busy servers, and busy servers = a * (1 - P_K)
    assert model.mean_system_size == pytest.approx(
        model.mean_queue_length + model.mean_busy_servers, rel=1e-12, abs=1e-15
    )
    assert model.mean_busy_servers == pytest.approx(
        a * (1 - model.blocking_probability), rel=1e-10
    )
    assert model.queued_probability == pytest.approx(
        model.wait_probability_given_admitted * (1 - model.blocking_probability),
        rel=1e-12,
        abs=1e-15,
    )


def test_wait_distribution_consistency():
    model = MMCK(arrival_rate=0.06, service_rate=1 / 120, servers=10, capacity=15)
    # P(W > 0) equals P(wait | admitted); distribution decreases to zero
    assert model.wait_exceeds(0.0) == pytest.approx(
        model.wait_probability_given_admitted, rel=1e-12
    )
    prev = 1.0
    for t in (0, 5, 15, 60, 300, 3000):
        cur = model.wait_exceeds(t)
        assert 0.0 <= cur <= prev + 1e-15
        prev = cur
    assert model.wait_exceeds(1e6) == pytest.approx(0.0, abs=1e-12)
    # integral of the survival function equals the mean wait
    dt, total = 0.05, 0.0
    t = 0.0
    while t < 4000:
        total += model.wait_exceeds(t + dt / 2) * dt
        t += dt
    assert total == pytest.approx(model.mean_wait, rel=1e-3)


def test_service_level_blocked_handling():
    model = MMCK(arrival_rate=0.08, service_rate=1 / 120, servers=10, capacity=15)
    among = model.service_level(15, blocked_count_as_failure=False)
    overall = model.service_level(15)
    assert overall == pytest.approx(among * (1 - model.blocking_probability))
    assert overall <= among


def test_no_waiting_room_means_no_wait():
    model = MMCK.from_erlangs(5.0, 8, 8)
    assert model.wait_exceeds(0.0) == 0.0
    assert model.service_level(0.0, blocked_count_as_failure=False) == 1.0


# ---- robustness -------------------------------------------------------------
def test_large_float_inputs_do_not_overflow():
    # the original module raised OverflowError for these
    for a, c, k in [(100.0, 100, 200), (150.5, 160, 400), (450.0, 520, 900)]:
        p = m.blocking_probability(a, c, k)
        assert 0.0 <= p <= 1.0
    assert m.blocking_probability(150.5, 160, 400) == pytest.approx(8.400099575676883e-09, rel=1e-6)
    assert 0.0 < m.blocking_probability(5000.0, 5000, 6000) < 1.0


@pytest.mark.parametrize(
    "args,exc",
    [
        ((8.0, 10.5, 15), TypeError),
        ((8.0, 10, 15.5), TypeError),
        ((8.0, True, 15), TypeError),
        ((float("nan"), 10, 15), ValueError),
        ((float("inf"), 10, 15), ValueError),
        ((0.0, 10, 15), ValueError),
        ((-1.0, 10, 15), ValueError),
        ((8.0, 0, 15), ValueError),
        ((8.0, 10, 9), ValueError),
    ],
)
def test_validation(args, exc):
    with pytest.raises(exc):
        m.blocking_probability(*args)


def test_negative_time_rejected():
    with pytest.raises(ValueError):
        MMCK.from_erlangs(8.0, 10, 15).wait_exceeds(-1.0)


# ---- Monte Carlo cross-check of the waiting-time distribution -----------------
def simulate(lam, mu, c, k, n_arrivals, seed):
    """FCFS M/M/c/K event simulation; returns (blocked fraction, waits of admitted)."""
    rng = random.Random(seed)
    free = [0.0] * c  # server free times
    heapq.heapify(free)
    departures: list[float] = []  # departure times of admitted calls
    waits: list[float] = []
    blocked = 0
    now = 0.0
    for _ in range(n_arrivals):
        now += rng.expovariate(lam)
        while departures and departures[0] <= now:
            heapq.heappop(departures)
        if len(departures) >= k:
            blocked += 1
            continue
        start = max(now, heapq.heappop(free))
        end = start + rng.expovariate(mu)
        heapq.heappush(free, end)
        heapq.heappush(departures, end)
        waits.append(start - now)
    return blocked / n_arrivals, waits


def test_matches_simulation():
    lam, mu, c, k = 0.075, 1 / 120, 10, 14  # 9 erlangs, heavy enough to queue and block
    model = MMCK(lam, mu, c, k)
    blocked, waits = simulate(lam, mu, c, k, 400_000, seed=20261008)
    assert blocked == pytest.approx(model.blocking_probability, abs=0.004)
    assert sum(waits) / len(waits) == pytest.approx(model.mean_wait, rel=0.05)
    for t in (5, 15, 30, 60):
        emp = sum(w <= t for w in waits) / len(waits)
        assert emp == pytest.approx(1 - model.wait_exceeds(t), abs=0.005)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
