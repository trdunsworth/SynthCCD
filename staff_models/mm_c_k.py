"""M/M/c/K finite-capacity delay-loss model.

Poisson arrivals, exponential service, ``c`` servers, and a hard limit of
``K`` calls in the *whole system* (those in service plus those waiting). A
call that arrives when K are present is blocked and lost; the queue therefore
has ``K - c`` waiting positions.

Relation to the classical Erlang formulas
-----------------------------------------
* ``K = c`` is Erlang B (M/M/c/c): no waiting room, exact.
* ``K -> infinity`` approaches Erlang C (M/M/c), but only when the offered
  load ``a = lam / mu`` is below ``c``. For ``a >= c`` the finite-K system
  still has a steady state, but the infinite system does not: for ``a > c``
  the blocking probability tends to ``1 - c/a`` as K grows, and at ``a = c``
  it tends to 0 while the mean queue length diverges. So there is no Erlang C
  limit there. Erlang C is the limit, not a special case, of this model.

Steady state (birth-death chain)
--------------------------------
    pi(n) = pi(0) * a**n / n!                    for 0 <= n <= c
    pi(n) = pi(0) * a**n / (c! * c**(n - c))     for c <= n <= K

No stability condition is needed because K is finite. The code uses the
equivalent recurrence ``w(n) = w(n-1) * a / min(n, c)`` evaluated in log
space, which does not overflow for large ``a``, ``c`` or ``K``.

Definitions (read these before using the numbers)
-------------------------------------------------
* ``blocking_probability``: pi(K). By PASTA this is also the fraction of
  arriving calls that are blocked.
* ``queued_probability`` (alias ``delay_probability``): probability that an
  arriving call is admitted AND must wait, i.e. sum of pi(n) for c <= n < K.
  This is averaged over *all* arrivals, blocked ones included. It is zero when
  K = c and approaches Erlang C's probability of waiting as K grows (a < c).
* ``wait_probability_given_admitted``: the same quantity divided by
  ``1 - pi(K)``; the probability that a call that gets in has to wait.
* ``effective_arrival_rate``: ``lam * (1 - pi(K))``. Little's law must use
  this rate, not ``lam``, for waiting-time results.
* Waiting-time results (``mean_wait``, ``wait_exceeds``, ``service_level``)
  are for FCFS service. An admitted call that finds ``n >= c`` calls present
  waits for ``n - c + 1`` departures at rate ``c * mu`` each, so its wait is
  Erlang(n - c + 1, c * mu); the distribution is a pi-weighted mixture.

Limitations
-----------
Blocked calls are permanently lost: there is no abandonment, redial,
retrial, or callback workload. Results other than the K = c case depend on
the exponential service-time assumption (only Erlang B is insensitive to the
service-time distribution).
"""

from __future__ import annotations

import math
import operator
from dataclasses import dataclass
from functools import cached_property

__all__ = [
    "MMCK",
    "blocking_probability",
    "delay_probability",
    "mean_queue_length",
    "mean_system_size",
    "queued_probability",
    "wait_probability_given_admitted",
]


def _as_count(value: object, name: str) -> int:
    """Return ``value`` as an int, rejecting floats, bools and non-numbers."""
    if isinstance(value, bool):
        raise TypeError(f"{name} must be an integer, not bool")
    try:
        return operator.index(value)  # type: ignore[arg-type]
    except TypeError:
        raise TypeError(
            f"{name} must be an integer, got {type(value).__name__} ({value!r})"
        ) from None


def _as_positive_float(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a number, not bool")
    try:
        x = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise TypeError(f"{name} must be a number, got {value!r}") from None
    if not math.isfinite(x) or x <= 0:
        raise ValueError(f"{name} must be finite and > 0, got {value!r}")
    return x


def _state_probabilities(a: float, c: int, k: int) -> tuple[float, ...]:
    """Normalized steady-state distribution pi(0..K), computed in log space."""
    log_a = math.log(a)
    log_w = [0.0]
    for n in range(1, k + 1):
        log_w.append(log_w[-1] + log_a - math.log(min(n, c)))
    top = max(log_w)
    w = [math.exp(x - top) for x in log_w]
    total = math.fsum(w)
    return tuple(x / total for x in w)


@dataclass(frozen=True)
class MMCK:
    """An M/M/c/K system.

    Parameters
    ----------
    arrival_rate : lam, calls per unit time.
    service_rate : mu, completions per unit time per busy server
        (1 / mean handle time, in the same time unit as ``arrival_rate``).
    servers : c, number of servers (integer >= 1).
    capacity : K, maximum calls in the system (integer >= servers).
    """

    arrival_rate: float
    service_rate: float
    servers: int
    capacity: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "arrival_rate", _as_positive_float(self.arrival_rate, "arrival_rate")
        )
        object.__setattr__(
            self, "service_rate", _as_positive_float(self.service_rate, "service_rate")
        )
        c = _as_count(self.servers, "servers")
        k = _as_count(self.capacity, "capacity")
        if c < 1:
            raise ValueError(f"servers must be >= 1, got {c}")
        if k < c:
            raise ValueError(f"capacity must be >= servers ({c}), got {k}")
        object.__setattr__(self, "servers", c)
        object.__setattr__(self, "capacity", k)

    @classmethod
    def from_erlangs(cls, erlangs: float, servers: int, capacity: int) -> MMCK:
        """Build from offered load in erlangs (time unit chosen so mu = 1)."""
        return cls(_as_positive_float(erlangs, "erlangs"), 1.0, servers, capacity)

    # ------------------------------------------------------------------
    # Steady-state quantities that do not depend on the time scale
    # ------------------------------------------------------------------
    @property
    def erlangs(self) -> float:
        """Offered load a = lam / mu."""
        return self.arrival_rate / self.service_rate

    @cached_property
    def pi(self) -> tuple[float, ...]:
        """Steady-state probabilities pi(0), ..., pi(K)."""
        return _state_probabilities(self.erlangs, self.servers, self.capacity)

    @property
    def blocking_probability(self) -> float:
        """pi(K): probability the system is full (= fraction of arrivals blocked)."""
        return self.pi[self.capacity]

    @property
    def queued_probability(self) -> float:
        """P(arrival is admitted and must wait) = sum of pi(n), c <= n < K."""
        return math.fsum(self.pi[self.servers : self.capacity])

    @property
    def wait_probability_given_admitted(self) -> float:
        """P(wait | admitted) = queued_probability / (1 - pi(K))."""
        return self.queued_probability / (1.0 - self.blocking_probability)

    @property
    def mean_queue_length(self) -> float:
        """Lq: expected number of calls waiting (not in service)."""
        c = self.servers
        return math.fsum(
            (n - c) * self.pi[n] for n in range(c + 1, self.capacity + 1)
        )

    @property
    def mean_busy_servers(self) -> float:
        """Expected number of busy servers; equals a * (1 - pi(K))."""
        c = self.servers
        return math.fsum(min(n, c) * p for n, p in enumerate(self.pi))

    @property
    def mean_system_size(self) -> float:
        """L = Lq + expected number in service: expected calls in the system."""
        return math.fsum(n * p for n, p in enumerate(self.pi))

    @property
    def utilization(self) -> float:
        """Fraction of server capacity in use (mean busy servers / c)."""
        return self.mean_busy_servers / self.servers

    # ------------------------------------------------------------------
    # Quantities that need the time scale (lam and mu in real units)
    # ------------------------------------------------------------------
    @property
    def effective_arrival_rate(self) -> float:
        """Rate of admitted calls, lam * (1 - pi(K)); use this in Little's law."""
        return self.arrival_rate * (1.0 - self.blocking_probability)

    @property
    def mean_wait(self) -> float:
        """Wq: mean wait in queue of an admitted call (Little's law)."""
        return self.mean_queue_length / self.effective_arrival_rate

    @property
    def mean_time_in_system(self) -> float:
        """W: mean time from admission to departure of an admitted call."""
        return self.mean_system_size / self.effective_arrival_rate

    def wait_exceeds(self, t: float) -> float:
        """P(W > t) for an admitted call, FCFS.

        Sums ``pi(n) * P(Poisson(c*mu*t) <= n - c)`` over ``c <= n < K`` and
        divides by ``1 - pi(K)``. Calls that find an idle server wait zero.
        """
        t = float(t)
        if math.isnan(t) or t < 0:
            raise ValueError(f"t must be >= 0, got {t!r}")
        c, k = self.servers, self.capacity
        if k == c:
            return 0.0  # no waiting room: nobody waits
        x = c * self.service_rate * t
        log_x = math.log(x) if x > 0 else None
        cdf = 0.0
        acc = 0.0
        for j in range(k - c):  # j = n - c, for n = c .. K-1
            if log_x is None:
                pmf = 1.0 if j == 0 else 0.0
            else:
                pmf = math.exp(-x + j * log_x - math.lgamma(j + 1))
            cdf += pmf
            acc += self.pi[c + j] * min(cdf, 1.0)
        return min(max(acc / (1.0 - self.blocking_probability), 0.0), 1.0)

    def service_level(self, t: float, *, blocked_count_as_failure: bool = True) -> float:
        """Fraction of calls answered within ``t`` time units.

        With ``blocked_count_as_failure=True`` (default) the denominator is
        all arriving calls and blocked calls count as not answered, which is
        how a standard measured over "all calls arriving" would treat them.
        With ``False`` the result is the fraction among *admitted* calls only.
        Abandonment is not modelled.
        """
        among_admitted = 1.0 - self.wait_exceeds(t)
        if blocked_count_as_failure:
            return (1.0 - self.blocking_probability) * among_admitted
        return among_admitted


# ----------------------------------------------------------------------
# Erlang-denominated convenience functions (service rate normalised to 1).
# Signatures match the original module.
# ----------------------------------------------------------------------
def blocking_probability(erlangs: float, servers: int, capacity: int) -> float:
    """pi(K): probability the system is full (= fraction of arrivals blocked)."""
    return MMCK.from_erlangs(erlangs, servers, capacity).blocking_probability


def queued_probability(erlangs: float, servers: int, capacity: int) -> float:
    """P(arrival is admitted and must wait), averaged over all arrivals."""
    return MMCK.from_erlangs(erlangs, servers, capacity).queued_probability


def delay_probability(erlangs: float, servers: int, capacity: int) -> float:
    """Alias of :func:`queued_probability` (kept for compatibility).

    Not P(wait | admitted); see :func:`wait_probability_given_admitted`.
    """
    return queued_probability(erlangs, servers, capacity)


def wait_probability_given_admitted(erlangs: float, servers: int, capacity: int) -> float:
    """P(wait | admitted) = queued_probability / (1 - pi(K))."""
    return MMCK.from_erlangs(erlangs, servers, capacity).wait_probability_given_admitted


def mean_queue_length(erlangs: float, servers: int, capacity: int) -> float:
    """Lq: expected number of waiting calls."""
    return MMCK.from_erlangs(erlangs, servers, capacity).mean_queue_length


def mean_system_size(erlangs: float, servers: int, capacity: int) -> float:
    """L: expected number of calls in the system (waiting plus in service)."""
    return MMCK.from_erlangs(erlangs, servers, capacity).mean_system_size


if __name__ == "__main__":
    load, c, k = 8.0, 10, 15
    m = MMCK.from_erlangs(load, c, k)
    print(f"M/M/c/K: {load} erlangs, {c} servers, capacity {k}")
    print(f"  Blocking probability:        {m.blocking_probability:.6f}")
    print(f"  P(queued), all arrivals:     {m.queued_probability:.6f}")
    print(f"  P(wait | admitted):          {m.wait_probability_given_admitted:.6f}")
    print(f"  Mean queue length (Lq):      {m.mean_queue_length:.3f}")
    print(f"  Mean system size (L):        {m.mean_system_size:.3f}")
    print(f"  Utilization:                 {m.utilization:.3f}")

    # Time-scaled example: 120 s mean handle time, 8 erlangs offered.
    handle_s = 120.0
    t = MMCK(arrival_rate=load / handle_s, service_rate=1.0 / handle_s, servers=c, capacity=k)
    print("\nSame system with a 120 s mean handle time (rates per second):")
    print(f"  Mean wait, admitted calls:   {t.mean_wait:.2f} s")
    for secs in (10, 15, 20):
        print(
            f"  Answered within {secs:>2} s:      "
            f"{t.service_level(secs):.4f} of all calls, "
            f"{t.service_level(secs, blocked_count_as_failure=False):.4f} of admitted"
        )
