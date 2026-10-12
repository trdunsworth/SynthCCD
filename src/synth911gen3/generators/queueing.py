"""Vectorized Erlang-C and Erlang-A queueing models for the call centre.

Both models describe a Poisson arrival stream (``M``) served by ``c``
identical agents with exponential service times (``M``/``c``). They differ in
how patient the callers are, and that difference is why both are needed:

* **Erlang C** (``M/M/c``) assumes infinite patience — nobody hangs up. The
  queue is therefore unbounded and the system is only stable while the offered
  load stays below the server count. It supplies the *wait* distribution.
* **Erlang A** (``M/M/c+M``) adds exponential impatience: a queued caller gives
  up after a patience time of mean ``1 / theta``. That patience is what actually
  produces abandoned 9-1-1 calls, and it also keeps the system stable at loads
  where Erlang C would diverge. It supplies the *abandonment* probability.

Everything here is vectorized over the leading axis so a whole year of hourly
intervals can be solved in a handful of NumPy operations. That matters because
Erlang A has no closed form — it is a truncated birth–death sum — and a
per-interval Python loop over 8,760 hours per dataset would dominate runtime at
scale.

A scalar reference implementation of each model is vendored under
``tests/reference/``; ``tests/test_queueing.py`` cross-checks this vectorized
core against those, so the two implementations cannot silently diverge.

References:
    A. K. Erlang, "Probability and Telephone Conversations," 1909.
    Garnett, Mandelbaum & Reiman (2002); Gans, Koole & Mandelbaum (2003).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "ErlangAResult",
    "erlang_a_analysis",
    "erlang_c_mean_wait",
    "erlang_c_service_level",
    "erlang_c_wait_probability",
]

# Weights below this fraction of pi[0] are treated as tail. Matches the scalar
# reference's default so both implementations truncate at the same place.
_TAIL_TOLERANCE = 1e-12
# Hard stop on the birth-death recursion. A stable M/M/c+M system needs on the
# order of a few hundred states past the server count; this is a runaway guard,
# not a working assumption.
_MAX_STATES = 20_000


@dataclass(frozen=True, slots=True)
class ErlangAResult:
    """Steady-state metrics for an ``M/M/c+M`` system, one entry per input interval.

    Attributes:
        delay_probability: Fraction of arrivals that queue before being served.
        abandonment_probability: Fraction of arrivals that hang up instead.
        mean_wait_time: Mean queue wait across *all* arrivals, in seconds.
        mean_wait_delayed: Mean queue wait across arrivals that do queue.
        mean_occupancy: Expected callers in the system (Little's law input).
        offered_load: Offered load in erlangs.
    """

    delay_probability: np.ndarray
    abandonment_probability: np.ndarray
    mean_wait_time: np.ndarray
    mean_wait_delayed: np.ndarray
    mean_occupancy: np.ndarray
    offered_load: np.ndarray


def _as_arrays(*values: np.ndarray | float) -> tuple[np.ndarray, ...]:
    """Broadcast inputs to a common shape and coerce to float64."""
    out = tuple(np.asarray(v, dtype=np.float64) for v in values)
    return tuple(np.broadcast_arrays(*out))


def erlang_c_wait_probability(
    erlangs: np.ndarray | float,
    servers: np.ndarray | float,
) -> np.ndarray:
    """Probability an arrival must queue, for the ``M/M/c`` Erlang C model.

    ``P(wait) = (a^c/c! · 1/(1-a/c)) / (Σ_{n<c} a^n/n! + a^c/c! · 1/(1-a/c))``

    Args:
        erlangs: Offered load in erlangs. Must be positive and below
            ``servers`` for a stable system.
        servers: Number of agents on duty.

    Returns:
        ``P(wait)`` per element. Unstable intervals (zero load, or load at or
        above the server count) saturate at ``1.0`` rather than raising: the
        caller is a data generator that must degrade gracefully, and an
        over-subscribed hour really does queue essentially every call.
    """
    a, c = _as_arrays(erlangs, servers)
    stable = (a > 0.0) & (a < c) & (c >= 1.0)
    if not stable.any():
        return np.ones(np.broadcast(a, c).shape, dtype=np.float64)

    a_safe = np.where(stable, a, 0.5)
    c_int = np.maximum(np.ceil(np.where(stable, c, 1.0)), 1.0)
    max_c = int(c_int.max())

    # term_n = a^n / n!, built by the stable recurrence term_{n+1} = term_n * a/(n+1)
    # rather than pow(a, n) / factorial(n), which overflows for realistic loads.
    term = np.ones_like(a_safe)
    partial_sum = np.ones_like(a_safe)
    at_server_count = np.zeros_like(a_safe)

    for n in range(1, max_c + 1):
        term = term * a_safe / n
        partial_sum = partial_sum + np.where(n < c_int, term, 0.0)
        at_server_count = np.where(n == c_int, term, at_server_count)

    headroom = 1.0 - a_safe / c_int
    tail_term = at_server_count / headroom
    probability = tail_term / np.where(partial_sum + tail_term > 0.0, partial_sum + tail_term, 1.0)
    return np.where(stable, probability, 1.0)


def _decay_rate(erlangs: np.ndarray, servers: np.ndarray, service_rate: np.ndarray) -> np.ndarray:
    """``c*mu - lambda``: the exponential decay rate of Erlang C queue delay."""
    erlangs, servers, service_rate = _as_arrays(erlangs, servers, service_rate)
    return service_rate * (servers - erlangs)


def erlang_c_mean_wait(
    erlangs: np.ndarray | float,
    servers: np.ndarray | float,
    service_rate: np.ndarray | float,
) -> np.ndarray:
    """Mean queue wait in seconds for callers that do queue.

    Conditional on queuing, Erlang C delay is exponential with rate
    ``c*mu - lambda``, so its mean is the reciprocal. Unstable intervals return
    ``inf`` — the wait is genuinely unbounded there.
    """
    decay = _decay_rate(
        np.asarray(erlangs, dtype=np.float64),
        np.asarray(servers, dtype=np.float64),
        np.asarray(service_rate, dtype=np.float64),
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(decay > 0.0, 1.0 / decay, np.inf)


def erlang_c_service_level(
    erlangs: np.ndarray | float,
    servers: np.ndarray | float,
    service_rate: np.ndarray | float,
    threshold: float,
) -> np.ndarray:
    """``P(wait <= threshold)`` for Erlang C, i.e. ``1 - P(wait)·e^(-decay·t)``."""
    p_wait = erlang_c_wait_probability(erlangs, servers)
    decay = _decay_rate(
        np.asarray(erlangs, dtype=np.float64),
        np.asarray(servers, dtype=np.float64),
        np.asarray(service_rate, dtype=np.float64),
    )
    with np.errstate(over="ignore", invalid="ignore"):
        exceeded = np.where(decay > 0.0, p_wait * np.exp(-decay * threshold), 1.0)
    return np.clip(1.0 - exceeded, 0.0, 1.0)


def erlang_a_analysis(
    arrival_rate: np.ndarray | float,
    service_rate: np.ndarray | float,
    servers: np.ndarray | float,
    abandon_rate: np.ndarray | float,
) -> ErlangAResult:
    """Steady-state metrics for the ``M/M/c+M`` Erlang A model.

    Solves the birth–death chain whose stationary weights follow

    * ``n < c``:  ``w[n+1] = w[n] · lambda / ((n+1)·mu)``
    * ``n >= c``: ``w[n+1] = w[n] · lambda / (c·mu + (n+1-c)·theta)``

    and truncates once every interval's weight falls under ``_TAIL_TOLERANCE``.
    The running sums are accumulated *unnormalized* and divided by the total at
    the end, which keeps the whole solve to one pass and constant memory.

    Unlike Erlang C this stays finite above unit load — patience is what bounds
    the queue — so no saturation guard is needed.

    Args:
        arrival_rate: ``lambda``, calls per second.
        service_rate: ``mu``, calls per second per agent.
        servers: Number of agents on duty.
        abandon_rate: ``theta``, abandonments per second per waiting caller;
            mean patience is its reciprocal.

    Returns:
        An :class:`ErlangAResult` whose arrays match the broadcast input shape.
    """
    lam, mu, c, theta = _as_arrays(arrival_rate, service_rate, servers, abandon_rate)
    lam, mu, c, theta = np.broadcast_arrays(lam, mu, c, theta)
    shape = lam.shape

    lam = np.where(lam > 0.0, lam, 0.0)
    mu = np.where(mu > 0.0, mu, 1.0)
    c = np.maximum(c, 1.0)
    c_int = np.ceil(c)
    theta = np.where(theta > 0.0, theta, 0.0)

    weight = np.ones(shape, dtype=np.float64)
    total = weight.copy()
    delay_weight = np.zeros(shape, dtype=np.float64)
    queue_weight = np.zeros(shape, dtype=np.float64)
    abandon_weight = np.zeros(shape, dtype=np.float64)
    occupancy_weight = np.zeros(shape, dtype=np.float64)

    n = 0
    while True:
        in_service = n < c_int
        denominator = np.where(in_service, (n + 1) * mu, c * mu + (n + 1 - c_int) * theta)
        denominator = np.where(denominator > 0.0, denominator, 1.0)
        weight = weight * lam / denominator
        weight = np.where(np.isfinite(weight), weight, 0.0)

        total = total + weight
        occupancy_weight = occupancy_weight + (n + 1) * weight
        beyond = (n + 1) >= c_int
        queue_size = np.maximum((n + 1) - c_int, 0.0)
        delay_weight = delay_weight + np.where(beyond, weight, 0.0)
        queue_weight = queue_weight + np.where(beyond, queue_size * weight, 0.0)
        abandon_weight = abandon_weight + np.where(beyond, queue_size * theta * weight, 0.0)

        n += 1
        if n >= _MAX_STATES:
            break
        if not weight.any():
            break
        if np.all(weight < _TAIL_TOLERANCE):
            break

    safe_total = np.where(total > 0.0, total, 1.0)
    safe_lam = np.where(lam > 0.0, lam, 1.0)

    delay_probability = delay_weight / safe_total
    mean_wait = (queue_weight / safe_total) / safe_lam
    abandonment = (abandon_weight / safe_total) / safe_lam
    mean_wait_delayed = np.divide(
        mean_wait,
        delay_probability,
        out=np.zeros_like(mean_wait),
        where=delay_probability > 0.0,
    )

    return ErlangAResult(
        delay_probability=delay_probability,
        abandonment_probability=np.clip(abandonment, 0.0, 1.0),
        mean_wait_time=mean_wait,
        mean_wait_delayed=mean_wait_delayed,
        mean_occupancy=occupancy_weight / safe_total,
        offered_load=lam / mu,
    )
