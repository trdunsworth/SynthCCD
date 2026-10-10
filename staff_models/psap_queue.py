"""PSAP queueing model: M/M/c/K with abandonment, redial and callback workload.

Extends :mod:`mm_c_k`. Requires numpy and scipy (``mm_c_k`` itself needs neither).

What is modelled
----------------
* Inbound 9-1-1 attempts arrive as a Poisson stream, are served FCFS by ``c``
  call-takers at rate ``mu``, and are blocked when ``K`` calls are already in
  the system (``K`` counts inbound calls only, in service plus waiting).
* **Abandonment.** Each waiting call hangs up at rate ``theta`` (exponential
  patience, as in Erlang A). ``theta = 0`` means infinitely patient callers,
  which is the M/M/c/K model (Erlang C-like).
* **Callbacks.** With probability ``callback_probability`` an abandoned call
  creates a callback job (exponential duration, rate ``callback_service_rate``)
  that joins a backlog of at most ``callback_backlog_capacity`` jobs (jobs
  arriving to a full backlog are lost). Callbacks start only when a call-taker
  is idle and no inbound call is waiting. By default a callback in progress is
  not interrupted (``callbacks_preemptible=False``), so callbacks can delay
  inbound calls; if ``True`` an arriving inbound call takes a server from a
  callback in progress, which returns to the backlog, so inbound performance
  is unaffected and callbacks only use spare capacity.
* **Redials.** A blocked attempt retries with probability
  ``redial_probability_blocked``, an abandoned attempt with probability
  ``redial_probability_abandoned``. Redials are fresh inbound attempts.

How it is solved
----------------
The inbound/callback system is a continuous-time Markov chain on
``(n, m, b)`` = inbound calls in system, callbacks in service, callbacks
waiting. It is solved exactly (sparse linear solve) for a given total attempt
rate. Redials are handled by a flow-balance fixed point on that rate::

    lam_total = lam_fresh + r_blocked * lam_total * P(block)
                          + r_abandoned * (abandonment flow at lam_total)

This treats redials as an extra Poisson stream: it is exact for mean flows but
ignores redial delay and burstiness, so it is an approximation (the tests
compare it with a simulation that uses explicit redial delays).

Answer-time distribution. A tagged arrival that must wait is followed as a
small Markov chain on (rank in queue, callbacks in service): servers free up
at rate ``(c - m) * mu + m * mu_cb``, calls ahead abandon at rate ``theta``
each, and the tagged call abandons at rate ``theta``. Absorption in "served" by
time ``t`` gives the exact FCFS answer-time distribution under the model.

Which "service level"? Each attempt (including redials) is a call, as in a
count of "all calls arriving". ``basis="all_attempts"`` divides by all
attempts, so blocked and abandoned calls count as not answered quickly.
``basis="answered_only"`` divides by answered calls only, which resembles an
"exclude abandoned" filter and is always at least as flattering.

Limitations
-----------
One inbound call class (no mix of patient and impatient callers); exponential
service, patience and callback durations; callbacks only follow abandonment
(not blocking); callbacks do not consume the K inbound capacity; no
time-varying arrivals (run it per interval); steady state only.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property

import numpy as np
import scipy.sparse.linalg  # noqa: F401  (exposes sparse.linalg.MatrixRankWarning)
from mm_c_k import _as_count, _as_positive_float
from scipy import sparse
from scipy.optimize import brentq
from scipy.sparse import linalg as spla

__all__ = ["PSAPModel", "PSAPSolution", "minimum_servers"]

MAX_STATES = 400_000
_BASES = ("all_attempts", "answered_only")


def _as_probability(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a number, not bool")
    try:
        x = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise TypeError(f"{name} must be a number, got {value!r}") from None
    if not math.isfinite(x) or not 0.0 <= x <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value!r}")
    return x


@dataclass(frozen=True)
class PSAPModel:
    """Parameters of the PSAP model. Rates share one time unit (e.g. per second).

    Parameters
    ----------
    fresh_arrival_rate : lam0, rate of new (non-redial) inbound attempts.
    service_rate : mu = 1 / mean inbound handle time.
    servers : c, call-takers available for inbound and callback work.
    capacity : K >= c, maximum inbound calls in the system.
    patience_rate : theta >= 0, abandonment rate per waiting call.
    redial_probability_blocked : chance a blocked attempt tries again.
    redial_probability_abandoned : chance an abandoned attempt tries again.
    callback_probability : chance an abandoned call creates a callback job.
    callback_service_rate : mu_cb = 1 / mean callback duration (required if
        ``callback_probability > 0``).
    callback_backlog_capacity : B, maximum callbacks waiting.
    callbacks_preemptible : whether inbound calls interrupt callbacks in progress.
    """

    fresh_arrival_rate: float
    service_rate: float
    servers: int
    capacity: int
    patience_rate: float = 0.0
    redial_probability_blocked: float = 0.0
    redial_probability_abandoned: float = 0.0
    callback_probability: float = 0.0
    callback_service_rate: float | None = None
    callback_backlog_capacity: int = 50
    callbacks_preemptible: bool = False

    def __post_init__(self) -> None:
        sa = object.__setattr__
        sa(self, "fresh_arrival_rate", _as_positive_float(self.fresh_arrival_rate, "fresh_arrival_rate"))
        sa(self, "service_rate", _as_positive_float(self.service_rate, "service_rate"))
        c = _as_count(self.servers, "servers")
        k = _as_count(self.capacity, "capacity")
        if c < 1:
            raise ValueError(f"servers must be >= 1, got {c}")
        if k < c:
            raise ValueError(f"capacity must be >= servers ({c}), got {k}")
        sa(self, "servers", c)
        sa(self, "capacity", k)
        th = self.patience_rate
        if isinstance(th, bool) or not isinstance(th, (int, float)) or not math.isfinite(th) or th < 0:
            raise ValueError(f"patience_rate must be a finite number >= 0, got {th!r}")
        sa(self, "patience_rate", float(th))
        sa(self, "redial_probability_blocked", _as_probability(self.redial_probability_blocked, "redial_probability_blocked"))
        sa(self, "redial_probability_abandoned", _as_probability(self.redial_probability_abandoned, "redial_probability_abandoned"))
        sa(self, "callback_probability", _as_probability(self.callback_probability, "callback_probability"))
        b = _as_count(self.callback_backlog_capacity, "callback_backlog_capacity")
        if b < 0:
            raise ValueError(f"callback_backlog_capacity must be >= 0, got {b}")
        sa(self, "callback_backlog_capacity", b)
        if self.callback_probability > 0:
            if self.callback_service_rate is None:
                raise ValueError("callback_service_rate is required when callback_probability > 0")
            sa(self, "callback_service_rate", _as_positive_float(self.callback_service_rate, "callback_service_rate"))
            if self.patience_rate == 0:
                raise ValueError("callback_probability > 0 needs patience_rate > 0 (callbacks follow abandonment)")
        if not isinstance(self.callbacks_preemptible, bool):
            raise TypeError("callbacks_preemptible must be a bool")

    # -- derived settings ---------------------------------------------------
    @property
    def _cb(self) -> bool:
        return self.callback_probability > 0

    @property
    def _backlog_cap(self) -> int:
        return self.callback_backlog_capacity if self._cb else 0

    @property
    def _max_callbacks(self) -> int:
        return self.servers if self._cb else 0

    @property
    def offered_load_fresh(self) -> float:
        """Fresh offered load in erlangs, lam0 / mu."""
        return self.fresh_arrival_rate / self.service_rate

    # -- Markov chain -----------------------------------------------------------
    @cached_property
    def _chain(self) -> _Chain:
        c, K = self.servers, self.capacity
        mu, th = self.service_rate, self.patience_rate
        pcb = self.callback_probability
        mucb = self.callback_service_rate if self._cb else 0.0
        B = self._backlog_cap
        pre = self.callbacks_preemptible and self._cb

        def norm(n: int, m: int, b: int) -> tuple[int, int, int]:
            idle = c - m - n
            if idle > 0 and b > 0:  # an idle call-taker starts a waiting callback
                k = min(b, idle)
                m += k
                b -= k
            return n, m, b

        states: list[tuple[int, int, int]] = [(0, 0, 0)]
        index = {(0, 0, 0): 0}
        base_r: list[int] = []
        base_c: list[int] = []
        base_v: list[float] = []
        arr_r: list[int] = []
        arr_c: list[int] = []

        def lookup(s: tuple[int, int, int]) -> int:
            j = index.get(s)
            if j is None:
                j = len(states)
                if j >= MAX_STATES:
                    raise ValueError(
                        f"state space exceeds {MAX_STATES} states; reduce callback_backlog_capacity or capacity"
                    )
                index[s] = j
                states.append(s)
            return j

        i = 0
        while i < len(states):
            n, m, b = states[i]
            s_av = c - m
            inn = min(s_av, n)
            w = n - inn
            if n < K:  # arrival (unit rate; scaled by the attempt rate later)
                if pre and m > 0 and n == s_av:
                    nxt = norm(n + 1, m - 1, b + 1 if b < B else b)
                else:
                    nxt = norm(n + 1, m, b)
                arr_r.append(i)
                arr_c.append(lookup(nxt))
            if inn > 0:  # inbound completion
                base_r.append(i)
                base_c.append(lookup(norm(n - 1, m, b)))
                base_v.append(inn * mu)
            if m > 0:  # callback completion
                base_r.append(i)
                base_c.append(lookup(norm(n, m - 1, b)))
                base_v.append(m * mucb)
            if w > 0 and th > 0:  # abandonment of a waiting call
                rate = th * w
                if pcb > 0 and b < B:
                    base_r.append(i)
                    base_c.append(lookup(norm(n - 1, m, b + 1)))
                    base_v.append(rate * pcb)
                    if pcb < 1:
                        base_r.append(i)
                        base_c.append(lookup(norm(n - 1, m, b)))
                        base_v.append(rate * (1 - pcb))
                else:
                    base_r.append(i)
                    base_c.append(lookup(norm(n - 1, m, b)))
                    base_v.append(rate)
            i += 1

        size = len(states)
        arr = np.array(states, dtype=np.int64)
        q_base = sparse.coo_matrix((base_v, (base_r, base_c)), shape=(size, size)).tocsr()
        q_arr = sparse.coo_matrix((np.ones(len(arr_r)), (arr_r, arr_c)), shape=(size, size)).tocsr()
        return _Chain(size, arr[:, 0], arr[:, 1], arr[:, 2], q_base, q_arr)

    def _stationary(self, lam: float) -> _Stat:
        ch = self._chain
        q = ch.q_base + lam * ch.q_arr
        out = np.asarray(q.sum(axis=1)).ravel()
        qt = (q - sparse.diags(out)).T.tocsr()
        tol = 1e-8 * max(1.0, float(out.max()))
        pi = None
        for method in ("fast", "robust"):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", sparse.linalg.MatrixRankWarning)
                if method == "fast":
                    # pi Q = 0: fix pi(0) = 1, drop the first balance equation, solve, normalise.
                    # (Avoids a dense normalisation row, which makes the sparse LU ~10x slower.)
                    x = spla.spsolve(qt[1:, 1:].tocsc(), -qt[1:, 0].toarray().ravel())
                    cand = np.concatenate([[1.0], np.atleast_1d(x)])
                else:
                    # Fallback for badly scaled (heavily overloaded) chains: normalisation row.
                    a = sparse.vstack([qt[:-1, :], sparse.csr_matrix(np.ones((1, ch.size)))]).tocsc()
                    rhs = np.zeros(ch.size)
                    rhs[-1] = 1.0
                    cand = np.atleast_1d(spla.spsolve(a, rhs))
            if not np.all(np.isfinite(cand)):
                continue
            cand = np.clip(cand, 0.0, None)
            total = cand.sum()
            if total <= 0:
                continue
            cand /= total
            resid = np.abs((q.T @ cand) - out * cand).max()
            if np.isfinite(resid) and resid <= tol:
                pi = cand
                break
        if pi is None:
            raise RuntimeError("stationary solve failed; the chain is numerically unstable at this load")
        return _Stat(self, lam, pi)

    def solve(self) -> PSAPSolution:
        """Solve for the steady state, including the redial fixed point."""
        lam0 = self.fresh_arrival_rate
        rb, ra = self.redial_probability_blocked, self.redial_probability_abandoned
        if rb == 0 and ra == 0:
            return PSAPSolution(self, self._stationary(lam0))

        def g(lam: float) -> float:
            st = self._stationary(lam)
            return lam0 + rb * lam * st.p_block + ra * st.abandon_flow - lam

        lo, g_lo = lam0, g(lam0)
        if g_lo <= 1e-15 * lam0:
            return PSAPSolution(self, self._stationary(lo))
        r_max = max(rb, ra)
        unstable = RuntimeError(
            "redial feedback is unstable: attempts grow without bound at this load; "
            "lower the redial probabilities, the fresh arrival rate, or add servers"
        )
        # redial flow <= r_max * lam_total, so the root lies below lam0 / (1 - r_max)
        hi = lam0 / (1.0 - r_max) if r_max < 1.0 else 2.0 * lo
        for _ in range(45):  # at most ~1e13 x lam0
            try:
                g_hi = g(hi)
            except RuntimeError:
                raise unstable from None
            if g_hi < -1e-12 * hi:  # a genuine sign change, not rounding noise
                break
            lo, hi = hi, hi * 2.0
        else:
            raise unstable
        lam = brentq(g, lo, hi, xtol=1e-11 * lam0, rtol=1e-11, maxiter=300)
        return PSAPSolution(self, self._stationary(lam))


@dataclass(frozen=True)
class _Chain:
    size: int
    n: np.ndarray
    m: np.ndarray
    b: np.ndarray
    q_base: sparse.csr_matrix
    q_arr: sparse.csr_matrix


class _Stat:
    """Stationary distribution of the (n, m, b) chain at total attempt rate ``lam``."""

    def __init__(self, model: PSAPModel, lam: float, pi: np.ndarray) -> None:
        ch = model._chain
        c, K = model.servers, model.capacity
        s_av = c - ch.m
        inn = np.minimum(ch.n, s_av)
        self.model, self.lam, self.pi = model, lam, pi
        self.s_av, self.inn = s_av, inn
        self.wait = ch.n - inn
        self.idle = s_av - inn
        self.p_block = float(pi[ch.n == K].sum())
        self.lq = float(pi @ self.wait)
        self.abandon_flow = model.patience_rate * self.lq
        self.e_inn = float(pi @ inn)
        self.e_m = float(pi @ ch.m)
        self.e_b = float(pi @ ch.b)


class PSAPSolution:
    """Steady-state results of a :class:`PSAPModel`. All probabilities are per attempt."""

    def __init__(self, model: PSAPModel, stat: _Stat) -> None:
        self.model = model
        self._s = stat

    # ---- attempt flow ------------------------------------------------------------
    @property
    def total_attempt_rate(self) -> float:
        """lam_total: fresh attempts plus redials."""
        return self._s.lam

    @property
    def attempts_per_fresh_call(self) -> float:
        return self._s.lam / self.model.fresh_arrival_rate

    @property
    def offered_load_total(self) -> float:
        """Total offered inbound load including redials, in erlangs."""
        return self._s.lam / self.model.service_rate

    @property
    def blocking_probability(self) -> float:
        return self._s.p_block

    @property
    def abandonment_probability(self) -> float:
        """Fraction of all attempts that abandon while waiting."""
        return self._s.abandon_flow / self._s.lam

    @property
    def answered_probability(self) -> float:
        return 1.0 - self.blocking_probability - self.abandonment_probability

    @property
    def eventual_answer_probability(self) -> float:
        """Chance a fresh caller is eventually answered, allowing redials."""
        m = self.model
        denom = (
            1.0
            - m.redial_probability_blocked * self.blocking_probability
            - m.redial_probability_abandoned * self.abandonment_probability
        )
        return self.answered_probability / denom

    # ---- occupancy ----------------------------------------------------------------
    @property
    def mean_queue_length(self) -> float:
        return self._s.lq

    @property
    def inbound_utilization(self) -> float:
        return self._s.e_inn / self.model.servers

    @property
    def callback_utilization(self) -> float:
        return self._s.e_m / self.model.servers

    @property
    def total_utilization(self) -> float:
        return self.inbound_utilization + self.callback_utilization

    # ---- callbacks ----------------------------------------------------------------
    @property
    def callback_generation_rate(self) -> float:
        """Rate at which abandoned calls create callback jobs."""
        return self.model.callback_probability * self._s.abandon_flow

    @property
    def callback_completion_rate(self) -> float:
        mucb = self.model.callback_service_rate or 0.0
        return mucb * self._s.e_m

    @property
    def callback_completion_fraction(self) -> float:
        """Fraction of generated callbacks completed (nan if none are generated)."""
        g = self.callback_generation_rate
        return self.callback_completion_rate / g if g > 0 else float("nan")

    @property
    def mean_callback_backlog(self) -> float:
        """Expected number of callbacks waiting for a free call-taker."""
        return self._s.e_b

    @property
    def mean_callback_backlog_wait(self) -> float:
        """Mean time a callback job spends waiting in the backlog per stay (Little's law).

        A preempted callback re-enters the backlog, which counts as a new stay.
        """
        m, s, ch = self.model, self._s, self.model._chain
        if not m._cb:
            return float("nan")
        entry = m.callback_probability * m.patience_rate * float(
            s.pi @ (s.wait * (ch.b < m._backlog_cap))
        )
        if m.callbacks_preemptible:
            pre = (ch.m > 0) & (ch.n == s.s_av) & (ch.n < m.capacity) & (ch.b < m._backlog_cap)
            entry += s.lam * float(s.pi[pre].sum())
        return s.e_b / entry if entry > 0 else float("nan")

    # ---- answer-time distribution ----------------------------------------------------
    @cached_property
    def _tagged(self) -> _Tagged:
        return _Tagged(self)

    @property
    def immediate_answer_probability(self) -> float:
        """Probability an attempt is answered with no wait."""
        return self._tagged.imm

    @property
    def abandonment_probability_from_waits(self) -> float:
        """Abandonment probability from the tagged-call chain (cross-check)."""
        return self._tagged.p_abandon

    def service_level(self, t: float, *, basis: str = "all_attempts") -> float:
        """Fraction of calls answered within ``t`` time units.

        ``basis="all_attempts"``: of every attempt (blocked and abandoned calls
        count as not answered in time). ``basis="answered_only"``: of the calls
        that were answered at all.
        """
        if basis not in _BASES:
            raise ValueError(f"basis must be one of {_BASES}, got {basis!r}")
        served_by_t = self._tagged.served_by(t)
        if basis == "all_attempts":
            return served_by_t
        return served_by_t / self._tagged.p_served

    @property
    def mean_wait_answered(self) -> float:
        """Mean time in queue of calls that were answered."""
        return self._tagged.mean_wait_answered

    def summary(self, answer_times: Sequence[float] = (10.0, 15.0, 20.0)) -> dict[str, float]:
        out: dict[str, float] = {
            "total_attempt_rate": self.total_attempt_rate,
            "attempts_per_fresh_call": self.attempts_per_fresh_call,
            "blocking_probability": self.blocking_probability,
            "abandonment_probability": self.abandonment_probability,
            "answered_probability": self.answered_probability,
            "eventual_answer_probability": self.eventual_answer_probability,
            "mean_queue_length": self.mean_queue_length,
            "mean_wait_answered": self.mean_wait_answered,
            "inbound_utilization": self.inbound_utilization,
            "callback_utilization": self.callback_utilization,
        }
        if self.model._cb:
            out["callback_completion_fraction"] = self.callback_completion_fraction
            out["mean_callback_backlog"] = self.mean_callback_backlog
        for t in answer_times:
            out[f"answered_within_{t:g}_all"] = self.service_level(t)
            out[f"answered_within_{t:g}_answered_only"] = self.service_level(t, basis="answered_only")
        return out


class _Tagged:
    """Tagged-call chain: state (rank j in the waiting line, callbacks in service m)."""

    def __init__(self, sol: PSAPSolution) -> None:
        model, st = sol.model, sol._s
        ch = model._chain
        c, K = model.servers, model.capacity
        mu, th = model.service_rate, model.patience_rate
        mucb = model.callback_service_rate if model._cb else 0.0
        nm = model._max_callbacks + 1
        size = K * nm

        def idx(j: int, m: int) -> int:
            return (j - 1) * nm + m

        rows: list[int] = []
        cols: list[int] = []
        vals: list[float] = []
        diag = np.zeros(size)
        to_served = np.zeros(size)
        to_aband = np.zeros(size)
        for j in range(1, K + 1):
            for m in range(nm):
                i = idx(j, m)
                r1 = (c - m) * mu  # an inbound call finishes
                r2 = m * mucb  # a callback finishes (its server goes to the head of the line)
                r3 = th * (j - 1)  # a call ahead abandons
                diag[i] = -(r1 + r2 + r3 + th)
                to_aband[i] = th
                if j == 1:
                    to_served[i] = r1 + r2
                else:
                    rows.append(i)
                    cols.append(idx(j - 1, m))
                    vals.append(r1 + r3)
                    if m > 0 and r2 > 0:
                        rows.append(i)
                        cols.append(idx(j - 1, m - 1))
                        vals.append(r2)
        t_mat = sparse.coo_matrix((vals, (rows, cols)), shape=(size, size)).tocsr() + sparse.diags(diag)
        self.size, self.t_mat = size, t_mat.tocsr()
        self.to_served, self.to_aband = to_served, to_aband

        # Where an arriving attempt lands, weighted by the stationary distribution (PASTA).
        pre = model.callbacks_preemptible and model._cb
        admitted = ch.n < K
        immediate = admitted & ((st.idle > 0) | (pre & (ch.m > 0) & (ch.n == st.s_av)))
        waiting = admitted & ~immediate
        self.imm = float(st.pi[immediate].sum())
        p0 = np.zeros(size)
        j_idx = (st.wait[waiting] + 1 - 1) * nm + ch.m[waiting]
        np.add.at(p0, j_idx, st.pi[waiting])
        self.p0 = p0

        neg_t = (-self.t_mat).tocsc()
        if p0.any():
            self.h_served = spla.spsolve(neg_t, to_served)
            h_ab = spla.spsolve(neg_t, to_aband)
            self.p_abandon = float(p0 @ h_ab)
            occ = spla.spsolve(neg_t.T.tocsc(), p0)
            e_w_served = float(occ @ self.h_served)
            self.p_served = self.imm + float(p0 @ self.h_served)
            self.mean_wait_answered = e_w_served / self.p_served
        else:
            self.h_served = np.zeros(size)
            self.p_abandon = 0.0
            self.p_served = self.imm
            self.mean_wait_answered = 0.0

        aug = sparse.lil_matrix((size + 2, size + 2))
        aug[:size, :size] = self.t_mat
        aug[:size, size] = to_served.reshape(-1, 1)
        aug[:size, size + 1] = to_aband.reshape(-1, 1)
        self._gen_t = aug.tocsr().T.tocsr()
        self._start = np.concatenate([p0, [0.0, 0.0]])
        self._norm = float(np.abs(self._gen_t).sum(axis=0).max())
        self._max_scaled_time = 2000.0  # cap on norm * t passed to expm_multiply

    def served_by(self, t: float) -> float:
        """P(an attempt is answered within ``t``). For very large ``t`` the matrix
        exponential is skipped: the chain is advanced to a time by which it has
        essentially finished, and the remaining mass is credited at its eventual
        answer probability (an upper bound within the unabsorbed mass, ~1e-15)."""
        t = float(t)
        if math.isnan(t) or t < 0:
            raise ValueError(f"t must be >= 0, got {t!r}")
        if t == 0 or not self.p0.any():
            return self.imm
        t_cap = self._max_scaled_time / self._norm
        t_eff = min(t, t_cap)
        p_t = spla.expm_multiply(self._gen_t * t_eff, self._start)
        served = self.imm + float(p_t[self.size])
        if t > t_cap:
            served += float(p_t[: self.size] @ self.h_served)
        return min(served, 1.0)


def minimum_servers(
    *,
    fresh_arrival_rate: float,
    service_rate: float,
    targets: Sequence[tuple[float, float]] = ((15.0, 0.90), (20.0, 0.95)),
    basis: str = "all_attempts",
    capacity_slack: int = 10,
    min_servers: int | None = None,
    max_servers: int = 300,
    **params: object,
) -> tuple[int, PSAPSolution]:
    """Smallest number of call-takers meeting every ``(t, fraction)`` target.

    Defaults are the NENA/NFPA 1225 targets (90% within 15 s, 95% within 20 s)
    with times in seconds, so rates must be per second. ``capacity_slack`` is
    the number of waiting positions (K = c + slack). Other keyword arguments are
    passed to :class:`PSAPModel`. Searches upward from the smallest c whose
    fresh offered load fits; service level is assumed to improve with c.
    """
    start = max(1, math.ceil(fresh_arrival_rate / service_rate)) if min_servers is None else min_servers
    for c in range(start, max_servers + 1):
        sol = PSAPModel(
            fresh_arrival_rate=fresh_arrival_rate,
            service_rate=service_rate,
            servers=c,
            capacity=c + capacity_slack,
            **params,  # type: ignore[arg-type]
        ).solve()
        if all(sol.service_level(t, basis=basis) >= frac for t, frac in targets):
            return c, sol
    raise RuntimeError(f"no server count up to {max_servers} meets the targets")


if __name__ == "__main__":
    # 120 s mean handle time, 7.2 erlangs fresh, 10 call-takers, 10 waiting positions.
    base = {"fresh_arrival_rate": 0.06, "service_rate": 1 / 120, "servers": 10, "capacity": 20}
    scenarios = {
        "No abandonment (M/M/c/K)": {},
        "+ abandonment (mean patience 30 s)": {"patience_rate": 1 / 30},
        "+ redials (blocked 85%, abandoned 30%)": {
            "patience_rate": 1 / 30, "redial_probability_blocked": 0.85, "redial_probability_abandoned": 0.30
        },
        "+ callbacks (60 s, all abandoned calls)": {
            "patience_rate": 1 / 30,
            "redial_probability_blocked": 0.85,
            "redial_probability_abandoned": 0.30,
            "callback_probability": 1.0,
            "callback_service_rate": 1 / 60,
        },
    }
    print("Scenario                                     attempts/call  P(abandon)  <=15s (all)  <=15s (answered only)")
    for name, extra in scenarios.items():
        s = PSAPModel(**base, **extra).solve()
        print(
            f"{name:<44} {s.attempts_per_fresh_call:>8.3f}  {s.abandonment_probability:>10.4f}"
            f"  {s.service_level(15):>11.4f}  {s.service_level(15, basis='answered_only'):>12.4f}"
        )
    full = scenarios["+ callbacks (60 s, all abandoned calls)"]
    c_need, sol = minimum_servers(fresh_arrival_rate=0.06, service_rate=1 / 120, capacity_slack=10, **full)
    print(f"\nSmallest c meeting 90%/15 s and 95%/20 s (all attempts, full model): {c_need}")
