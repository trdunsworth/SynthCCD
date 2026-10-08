"""Erlang B model (M/M/c/c loss system).

The Erlang B formula gives the probability that an arriving call is blocked
(finds all servers busy) in a system with:

* Poisson arrivals at rate ``lam``
* Exponential service times with mean ``1 / mu``
* ``c`` identical servers
* No waiting room: calls that find all servers busy are lost

Offered load is measured in erlangs: ``a = lam / mu``.

Because there is no queue, the time-average blocking probability equals the
call-average (PASTA), so Erlang B reports a single blocking probability.

Reference: A. K. Erlang, "Solution of some Problems in the Theory of
Probabilities of Significance in Automatic Telephone Exchanges," 1917.
"""

from __future__ import annotations


def blocking_probability(erlangs: float, servers: int) -> float:
    """Return the Erlang B blocking probability for offered load ``erlangs`` and ``servers`` servers.

    Computed with the numerically stable iterative recursion:

        B(0, a) = 1
        B(c, a) = a * B(c-1, a) / (c + a * B(c-1, a))

    Args:
        erlangs: Offered load in erlangs (lambda / mu). Must be > 0.
        servers: Number of servers/trunks. Must be >= 1.

    Returns:
        Probability in [0, 1] that an arrival is blocked.
    """
    if erlangs <= 0:
        raise ValueError("erlangs must be positive")
    if servers < 1:
        raise ValueError("servers must be at least 1")

    b = 1.0
    for c in range(1, servers + 1):
        b = erlangs * b / (c + erlangs * b)
    return b


def required_servers(erlangs: float, target_blocking: float) -> int:
    """Return the smallest server count ``c`` achieving blocking <= ``target_blocking``."""
    if not 0 < target_blocking < 1:
        raise ValueError("target_blocking must be in (0, 1)")
    c = 1
    while blocking_probability(erlangs, c) > target_blocking:
        c += 1
    return c


if __name__ == "__main__":
    load = 10.0
    trunks = 15
    print(f"Erlang B: offered load {load} erlangs, {trunks} trunks")
    print(f"  Blocking probability: {blocking_probability(load, trunks):.6f}")
    goal = 0.01
    print(f"  Trunks needed for <= {goal:.0%} blocking: {required_servers(load, goal)}")
