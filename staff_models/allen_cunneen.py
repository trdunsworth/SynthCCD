"""Allen-Cunneen approximation (M/G/c delay system).

Extends Erlang C to service times with a general distribution by scaling
the Erlang C wait probability with a factor derived from the squared
coefficient of variation of service time ``scv``:

    Pw_MG = Pw_MM * (1 + scv**2) / 2

with the same utilization guard ``rho = R / c < 1``. Exponential service
(``scv = 1``) recovers Erlang C exactly; lower variability than exponential
(``scv < 1``) reduces delay, and deterministic-ish service cuts it roughly
in half.

Also reports the corresponding mean queue wait:

    Wq = Pw_MG / (c*mu - lam)

where ``Pw_MG`` already carries the ``(1 + scv**2)/2`` correction.

Reference: J. E. Angus, "On the M/G/s queue..." and F. P. Allen, D. W.
Cunneen, "A Survey of Queueing Models and Industrial Applications," 1964.
"""

from __future__ import annotations

from erlang_c import wait_probability


def wait_probability_mg(erlangs: float, servers: int, scv: float) -> float:
    """P(delay) for M/G/c via the Allen-Cunneen correction."""
    if scv < 0:
        raise ValueError("scv must be >= 0")
    p_c = wait_probability(erlangs, servers)
    return min(1.0, p_c * (1 + scv**2) / 2)


def mean_wait_mg(erlangs: float, servers: int, mu: float, scv: float) -> float:
    """Mean time in queue (seconds) for M/G/c via Allen-Cunneen."""
    if not 0 < erlangs < servers:
        raise ValueError("require 0 < erlangs < servers for stability")
    rho_guard = servers * mu - erlangs * mu
    p = wait_probability_mg(erlangs, servers, scv)
    return p / rho_guard


if __name__ == "__main__":
    load, c, aht = 8.0, 10, 300.0
    mu = 1 / aht
    for scv in (0.0, 0.5, 1.0, 1.5, 2.0):
        print(
            f"scv={scv:.1f}: P(wait)={wait_probability_mg(load, c, scv):.4f}, "
            f"mean wait={mean_wait_mg(load, c, mu, scv):.1f}s"
        )
