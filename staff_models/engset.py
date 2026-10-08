"""Engset model (finite-source loss system).

Models a trunk group serving a *finite* population of ``N`` sources, each
generating calls at rate ``gamma`` while idle and occupying a trunk for an
exponential time with mean ``1 / mu``. Blocked calls are lost and the source
must retry from scratch (classical Engset assumptions).

With offered traffic per idle source ``beta = gamma / mu``, the steady-state
probability of ``n`` busy trunks is

    pi(n) = pi(0) * C(N, n) * beta**n,   n = 0..min(N, c)

Unlike Erlang B, *time congestion* (fraction of time all trunks busy) and
*call congestion* (fraction of attempted calls lost) differ, because sources
with a call in progress do not generate new attempts.

Key outputs:

* ``time_congestion`` — P(all c trunks busy), a random observer in time
* ``call_congestion`` — blocking probability seen by an arriving attempt
* ``carried_traffic`` — mean number of busy trunks

Reference: T. Engset (1918), as described in e.g. Wolff, *Stochastic
Modeling and the Theory of Queues*.
"""

from __future__ import annotations

from math import comb


def _pi(beta: float, sources: int, servers: int) -> list[float]:
    n_max = min(sources, servers)
    w = [comb(sources, n) * beta**n for n in range(n_max + 1)]
    total = sum(w)
    return [x / total for x in w]


def time_congestion(sources: int, servers: int, gamma_over_mu: float) -> float:
    """Probability that all ``servers`` trunks are busy (time average)."""
    if sources < 1 or servers < 1 or gamma_over_mu <= 0:
        raise ValueError("require sources >= 1, servers >= 1, gamma/mu > 0")
    if servers > sources:
        return 0.0
    return _pi(gamma_over_mu, sources, servers)[servers]


def call_congestion(sources: int, servers: int, gamma_over_mu: float) -> float:
    """Blocking probability seen by a call attempt (Engset call congestion).

    An attempting source sees the other ``sources - 1`` sources in steady
    state, so call congestion is the time congestion of an ``N-1`` source
    system: ``pi_{N-1}(c)``.
    """
    if sources < 1 or servers < 1 or gamma_over_mu <= 0:
        raise ValueError("require sources >= 1, servers >= 1, gamma/mu > 0")
    if servers > sources - 1:
        return 0.0
    pi = _pi(gamma_over_mu, sources - 1, servers)
    return pi[servers]


def carried_traffic(sources: int, servers: int, gamma_over_mu: float) -> float:
    """Mean number of busy trunks."""
    pi = _pi(gamma_over_mu, sources, servers)
    return sum(n * p for n, p in enumerate(pi))


if __name__ == "__main__":
    N, c, beta = 50, 8, 0.2
    print(f"Engset: {N} sources, {c} trunks, gamma/mu = {beta}")
    print(f"  Time congestion: {time_congestion(N, c, beta):.6f}")
    print(f"  Call congestion: {call_congestion(N, c, beta):.6f}")
    print(f"  Carried traffic: {carried_traffic(N, c, beta):.3f} erlangs")
