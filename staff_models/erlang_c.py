"""Erlang C model (M/M/c delay system).

The Erlang C formula gives the probability that an arriving call must wait
for a server in a system with:

* Poisson arrivals at rate ``lam``
* Exponential service times with mean ``1 / mu``
* ``c`` identical servers
* An infinite waiting room; nobody abandons

Offered load: ``a = lam / mu`` erlangs. Stability requires ``a < c``.

Key outputs:

* ``p_wait`` — probability an arrival waits before service (Erlang C)
* ``asa`` — average speed of answer for delayed callers, ``p_wait / (c*mu - lam)``
* ``service_level(t)`` — probability a caller waits no longer than ``t``:
  ``1 - p_wait * exp(-(c*mu - lam) * t)``

Reference: A. K. Erlang, "Probability and Telephone Conversations," 1909.
"""

from __future__ import annotations

import math

from scipy.special import gammaln


def wait_probability(erlangs: float, servers: int) -> float:
    """Return the Erlang C probability that an arrival must wait."""
    if not 0 < erlangs < servers:
        raise ValueError("require 0 < erlangs < servers for stability")
    c = servers
    term = math.exp(c * math.log(erlangs) - gammaln(c + 1)) / (1 - erlangs / c)
    s = sum(erlangs**n / math.factorial(n) for n in range(c))
    return term / (s + term)


def average_speed_of_answer(erlangs: float, servers: int, mu: float) -> float:
    """Return the mean queue wait in seconds for delayed callers.

    ``erlangs / servers`` is utilization rho; the conditional expected wait is
    ``1 / (servers*mu - lam)`` where ``lam = erlangs * mu``.
    """
    if not 0 < erlangs < servers:
        raise ValueError("require 0 < erlangs < servers for stability")
    lam = erlangs * mu
    return 1.0 / (servers * mu - lam)


def service_level(erlangs: float, servers: int, mu: float, threshold: float) -> float:
    """Return P(wait <= threshold) for the Erlang C system."""
    if not 0 < erlangs < servers:
        raise ValueError("require 0 < erlangs < servers for stability")
    p_wait = wait_probability(erlangs, servers)
    lam = erlangs * mu
    return 1.0 - p_wait * math.exp(-(servers * mu - lam) * threshold)


if __name__ == "__main__":
    load, agents, mu = 8.0, 10, 1 / 300.0
    pw = wait_probability(load, agents)
    print(f"Erlang C: offered load {load} erlangs, {agents} agents, mean handle {1/mu:.0f}s")
    print(f"  P(wait) = {pw:.6f}")
    print(f"  ASA (delayed callers) = {average_speed_of_answer(load, agents, mu):.1f}s")
    for t in (10, 20, 30):
        print(f"  Service level @ {t}s = {service_level(load, agents, mu, t):.4f}")
