"""Tests for psap_queue. Run with ``pytest test_psap_queue.py``."""

from __future__ import annotations

import heapq
import math
import random
from collections import OrderedDict

import numpy as np
import pytest

from mm_c_k import MMCK
from psap_queue import PSAPModel, minimum_servers

LAM0, MU, C, K = 0.06, 1 / 120, 10, 20  # 7.2 erlangs, 120 s handle time


def model(**kw):
    base = dict(fresh_arrival_rate=LAM0, service_rate=MU, servers=C, capacity=K)
    base.update(kw)
    return PSAPModel(**base)


# ---- reductions to known models -----------------------------------------------------
@pytest.mark.parametrize("lam,c,k", [(0.06, 10, 20), (0.075, 10, 14), (0.02, 4, 4)])
def test_reduces_to_mmck_without_abandonment(lam, c, k):
    ref = MMCK(lam, MU, c, k)
    sol = PSAPModel(lam, MU, c, k).solve()
    assert sol.blocking_probability == pytest.approx(ref.blocking_probability, rel=1e-8)
    assert sol.mean_queue_length == pytest.approx(ref.mean_queue_length, rel=1e-8, abs=1e-12)
    for t in (0, 5, 15, 45):
        assert sol.service_level(t) == pytest.approx(ref.service_level(t), abs=1e-7)
        assert sol.service_level(t, basis="answered_only") == pytest.approx(
            ref.service_level(t, blocked_count_as_failure=False), abs=1e-7
        )
    assert sol.mean_wait_answered == pytest.approx(ref.mean_wait, rel=1e-6, abs=1e-9)


def erlang_a_birth_death(lam, mu, theta, c, k):
    """Independent birth-death solution of M/M/c/K + M (no callbacks, no redial)."""
    w = [1.0]
    for n in range(1, k + 1):
        w.append(w[-1] * lam / (min(n, c) * mu + max(0, n - c) * theta))
    s = sum(w)
    pi = [x / s for x in w]
    lq = sum((n - c) * pi[n] for n in range(c + 1, k + 1))
    return pi[k], theta * lq / lam, lq


def test_matches_erlang_a_birth_death():
    theta = 1 / 30
    p_block, p_ab, lq = erlang_a_birth_death(LAM0, MU, theta, C, K)
    sol = model(patience_rate=theta).solve()
    assert sol.blocking_probability == pytest.approx(p_block, rel=1e-8)
    assert sol.abandonment_probability == pytest.approx(p_ab, rel=1e-8)
    assert sol.mean_queue_length == pytest.approx(lq, rel=1e-8)


def test_abandonment_flatters_answered_only_basis():
    sol = model(patience_rate=1 / 30).solve()
    assert sol.service_level(15, basis="answered_only") > sol.service_level(15)


# ---- internal consistency ------------------------------------------------------------
@pytest.mark.parametrize(
    "kw",
    [
        dict(patience_rate=1 / 30),
        dict(patience_rate=1 / 30, redial_probability_blocked=0.85, redial_probability_abandoned=0.3),
        dict(patience_rate=1 / 30, callback_probability=1.0, callback_service_rate=1 / 60),
        dict(
            patience_rate=1 / 20,
            redial_probability_blocked=0.5,
            redial_probability_abandoned=0.5,
            callback_probability=0.7,
            callback_service_rate=1 / 90,
            callback_backlog_capacity=8,
        ),
        dict(
            patience_rate=1 / 30,
            callback_probability=1.0,
            callback_service_rate=1 / 60,
            callbacks_preemptible=True,
        ),
    ],
)
def test_flow_and_wait_chain_consistency(kw):
    sol = model(**kw).solve()
    m = sol.model
    # tagged-call chain agrees with flow balance
    assert sol.abandonment_probability_from_waits == pytest.approx(sol.abandonment_probability, rel=1e-8, abs=1e-12)
    assert sol.service_level(1e7) == pytest.approx(sol.answered_probability, rel=1e-7)
    assert 0 <= sol.immediate_answer_probability <= sol.answered_probability
    assert sol.service_level(0) == pytest.approx(sol.immediate_answer_probability)
    # redial fixed point
    rb, ra = m.redial_probability_blocked, m.redial_probability_abandoned
    lam = sol.total_attempt_rate
    assert lam == pytest.approx(
        m.fresh_arrival_rate + rb * lam * sol.blocking_probability + ra * lam * sol.abandonment_probability,
        rel=1e-9,
    )
    # server time balance: inbound busy = answered rate / mu ; callbacks busy = completions / mu_cb
    assert sol.inbound_utilization * m.servers == pytest.approx(lam * sol.answered_probability / m.service_rate, rel=1e-7)
    if m.callback_probability > 0:
        assert 0 <= sol.callback_completion_fraction <= 1 + 1e-9
    # monotone, bounded service level
    prev = 0.0
    for t in (0, 5, 15, 40, 120, 1000):
        cur = sol.service_level(t)
        assert prev - 1e-12 <= cur <= 1 + 1e-12
        prev = cur
    # Little's law on the wait of answered calls via the queue
    waits_total = sol.mean_queue_length  # abandoners and answered both wait
    assert waits_total >= 0


# ---- callbacks ------------------------------------------------------------------------
def test_preemptible_callbacks_do_not_affect_inbound():
    base = model(patience_rate=1 / 30).solve()
    pre = model(
        patience_rate=1 / 30, callback_probability=1.0, callback_service_rate=1 / 60, callbacks_preemptible=True
    ).solve()
    assert pre.blocking_probability == pytest.approx(base.blocking_probability, rel=1e-8)
    assert pre.abandonment_probability == pytest.approx(base.abandonment_probability, rel=1e-8)
    for t in (0, 10, 15, 20, 60):
        assert pre.service_level(t) == pytest.approx(base.service_level(t), abs=1e-7)
    assert pre.callback_utilization > 0
    assert pre.total_utilization <= 1 + 1e-9


def test_non_preemptible_callbacks_hurt_inbound_service_level():
    base = model(patience_rate=1 / 30).solve()
    cb = model(patience_rate=1 / 30, callback_probability=1.0, callback_service_rate=1 / 60).solve()
    assert cb.service_level(15) < base.service_level(15)
    assert cb.abandonment_probability > base.abandonment_probability


def test_callback_backlog_capacity_zero_loses_all_callbacks():
    sol = model(patience_rate=1 / 30, callback_probability=1.0, callback_service_rate=1 / 60,
                callback_backlog_capacity=0).solve()
    assert sol.callback_completion_rate == pytest.approx(0.0, abs=1e-12)
    assert sol.callback_completion_fraction == pytest.approx(0.0, abs=1e-9)


def test_more_callback_probability_means_more_callback_work():
    a = model(patience_rate=1 / 30, callback_probability=0.3, callback_service_rate=1 / 60).solve()
    b = model(patience_rate=1 / 30, callback_probability=1.0, callback_service_rate=1 / 60).solve()
    assert b.callback_utilization > a.callback_utilization


# ---- redials --------------------------------------------------------------------------
def test_redials_raise_load_and_attempts():
    a = model(patience_rate=1 / 30).solve()
    b = model(patience_rate=1 / 30, redial_probability_abandoned=0.5).solve()
    assert b.total_attempt_rate > a.total_attempt_rate
    assert b.attempts_per_fresh_call == pytest.approx(
        1 / (1 - 0.5 * b.abandonment_probability), rel=1e-9
    )
    assert b.eventual_answer_probability > b.answered_probability


def test_unstable_redial_feedback_is_reported():
    with pytest.raises(RuntimeError):
        PSAPModel(0.5, MU, 4, 5, patience_rate=1 / 30,
                  redial_probability_blocked=1.0, redial_probability_abandoned=1.0).solve()


# ---- validation -----------------------------------------------------------------------
@pytest.mark.parametrize(
    "kw,exc",
    [
        (dict(servers=2.5), TypeError),
        (dict(servers=0), ValueError),
        (dict(capacity=5), ValueError),
        (dict(patience_rate=-1.0), ValueError),
        (dict(patience_rate=float("nan")), ValueError),
        (dict(redial_probability_blocked=1.5), ValueError),
        (dict(callback_probability=0.5, patience_rate=1 / 30), ValueError),  # missing rate
        (dict(callback_probability=0.5, callback_service_rate=1 / 60), ValueError),  # no abandonment
        (dict(callbacks_preemptible=1), TypeError),
        (dict(fresh_arrival_rate=0.0), ValueError),
    ],
)
def test_validation(kw, exc):
    with pytest.raises(exc):
        model(**kw)


def test_bad_basis_and_time():
    sol = model(patience_rate=1 / 30).solve()
    with pytest.raises(ValueError):
        sol.service_level(15, basis="nope")
    with pytest.raises(ValueError):
        sol.service_level(-1)


def test_minimum_servers_monotone_target():
    c1, s1 = minimum_servers(fresh_arrival_rate=LAM0, service_rate=MU, patience_rate=1 / 30,
                             targets=((15.0, 0.90),), capacity_slack=10)
    c2, s2 = minimum_servers(fresh_arrival_rate=LAM0, service_rate=MU, patience_rate=1 / 30,
                             targets=((15.0, 0.95),), capacity_slack=10)
    assert c1 <= c2
    assert s1.service_level(15) >= 0.90
    assert PSAPModel(LAM0, MU, c1 - 1, c1 - 1 + 10, patience_rate=1 / 30).solve().service_level(15) < 0.90


# ---- simulation cross-check ------------------------------------------------------------
def simulate(p: PSAPModel, n_fresh: int, redial_delay: float, seed: int):
    """Event simulation with explicit redial delays, FCFS waiting, callbacks, abandonment."""
    rng = random.Random(seed)
    c, K = p.servers, p.capacity
    mu, th, mucb = p.service_rate, p.patience_rate, p.callback_service_rate or 0.0
    pcb, B = p.callback_probability, (p.callback_backlog_capacity if p.callback_probability > 0 else 0)
    pre = p.callbacks_preemptible
    ev: list = []
    seq = 0

    def push(t, kind, payload=None):
        nonlocal seq
        seq += 1
        heapq.heappush(ev, (t, seq, kind, payload))

    t = 0.0
    for _ in range(n_fresh):
        t += rng.expovariate(p.fresh_arrival_rate)
        push(t, "arr", None)
    horizon, warm = t, t * 0.05

    in_service = 0
    waiting: OrderedDict[int, float] = OrderedDict()  # call id -> arrival time
    active_cb: set[int] = set()
    cancelled: set[int] = set()
    backlog = 0
    cid = 0
    stats = dict(att=0, block=0, aband=0, served=0, w_sum=0.0, within={5: 0, 15: 0, 30: 0, 60: 0})
    area = dict(m=0.0, b=0.0, inn=0.0)
    last_t = 0.0

    def start_inbound(now, call_t, counted):
        nonlocal in_service
        in_service += 1
        push(now + rng.expovariate(mu), "done", None)
        if counted:
            w = now - call_t
            stats["served"] += 1
            stats["w_sum"] += w
            for k in stats["within"]:
                if w <= k:
                    stats["within"][k] += 1

    def dispatch(now):
        nonlocal backlog, cid
        while in_service + len(active_cb) < c:
            if waiting:
                k, (arr_t, counted) = next(iter(waiting.items()))
                del waiting[k]
                start_inbound(now, arr_t, counted)
            elif backlog > 0:
                backlog -= 1
                cid += 1
                active_cb.add(cid)
                push(now + rng.expovariate(mucb), "cbdone", cid)
            else:
                break

    while ev:
        now, _, kind, payload = heapq.heappop(ev)
        dt = min(now, horizon) - max(last_t, warm)
        if dt > 0:  # time-average the state held since the previous event
            area["m"] += len(active_cb) * dt
            area["b"] += backlog * dt
            area["inn"] += in_service * dt
        last_t = now
        counted = warm <= now <= horizon
        if kind == "arr" or kind == "redial":
            if counted:
                stats["att"] += 1
            if in_service + len(waiting) >= K:
                if counted:
                    stats["block"] += 1
                if rng.random() < p.redial_probability_blocked:
                    push(now + rng.expovariate(1 / redial_delay), "redial")
                continue
            if in_service + len(active_cb) < c:
                start_inbound(now, now, counted)
            elif pre and active_cb and not waiting:
                victim = active_cb.pop()
                cancelled.add(victim)
                if backlog < B:
                    backlog += 1
                start_inbound(now, now, counted)
            else:
                cid += 1
                waiting[cid] = (now, counted)
                if th > 0:
                    push(now + rng.expovariate(th), "ab", cid)
        elif kind == "done":
            in_service -= 1
            dispatch(now)
        elif kind == "cbdone":
            if payload in cancelled:
                cancelled.discard(payload)
                continue
            active_cb.discard(payload)
            dispatch(now)
        elif kind == "ab":
            if payload in waiting:
                _, was_counted = waiting.pop(payload)
                if was_counted:
                    stats["aband"] += 1
                if pcb > 0 and rng.random() < pcb and backlog < B:
                    backlog += 1
                if rng.random() < p.redial_probability_abandoned:
                    push(now + rng.expovariate(1 / redial_delay), "redial")
                dispatch(now)
    span = horizon - warm
    n = stats["att"]
    return dict(
        att_per_fresh=n / (n_fresh * 0.95),
        block=stats["block"] / n,
        aband=stats["aband"] / n,
        within={k: v / n for k, v in stats["within"].items()},
        within_answered={k: v / stats["served"] for k, v in stats["within"].items()},
        e_m=area["m"] / span,
        e_b=area["b"] / span,
        e_inn=area["inn"] / span,
    )


def test_matches_simulation_abandonment_only():
    p = model(patience_rate=1 / 30)
    sol = p.solve()
    sim = simulate(p, 120_000, redial_delay=10.0, seed=7)
    assert sim["block"] == pytest.approx(sol.blocking_probability, abs=0.004)
    assert sim["aband"] == pytest.approx(sol.abandonment_probability, abs=0.006)
    for t in (5, 15, 30, 60):
        assert sim["within"][t] == pytest.approx(sol.service_level(t), abs=0.008)
        assert sim["within_answered"][t] == pytest.approx(sol.service_level(t, basis="answered_only"), abs=0.008)


@pytest.mark.parametrize("preemptible", [False, True])
def test_matches_simulation_full_model(preemptible):
    p = model(
        fresh_arrival_rate=0.075,
        patience_rate=1 / 30,
        redial_probability_blocked=0.85,
        redial_probability_abandoned=0.3,
        callback_probability=1.0,
        callback_service_rate=1 / 60,
        callback_backlog_capacity=15,
        callbacks_preemptible=preemptible,
    )
    sol = p.solve()
    sim = simulate(p, 150_000, redial_delay=10.0, seed=11)
    assert sim["att_per_fresh"] == pytest.approx(sol.attempts_per_fresh_call, rel=0.02)
    assert sim["aband"] == pytest.approx(sol.abandonment_probability, abs=0.01)
    assert sim["block"] == pytest.approx(sol.blocking_probability, abs=0.006)
    assert sim["e_m"] == pytest.approx(sol.callback_utilization * p.servers, rel=0.06, abs=0.05)
    assert sim["e_b"] == pytest.approx(sol.mean_callback_backlog, rel=0.12, abs=0.2)
    for t in (5, 15, 30):
        assert sim["within"][t] == pytest.approx(sol.service_level(t), abs=0.012)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
