"""M/M/c/K finite-capacity delay-loss model.

Generalizes Erlang B (K = c) and Erlang C (K = infinity): calls wait in a
bounded queue of ``K - c`` positions and are blocked when the system is
full.

Steady state (birth-death):

    pi(n) = pi(0) * a**n / n!           n <= c
    pi(n) = pi(0) * a**n / (c! * c**(n-c))   c <= n <= K

with ``a = lam / mu`` offered load in erlangs. No stability requirement
beyond K being finite.

Key outputs:

* ``blocking_probability`` — pi(K), the Erlang-B-style loss probability
* ``delay_probability`` — probability an arrival must wait
* ``mean_queue_length`` / ``mean_system_size``

"""

from __future__ import annotations

import math


def _pi(erlangs: float, c: int, k: int) -> list[float]:
    a = erlangs
    w = []
    for n in range(k + 1):
        if n <= c:
            w.append(a**n / math.factorial(n))
        else:
            w.append(a**n / (math.factorial(c) * c ** (n - c)))
    total = sum(w)
    return [x / total for x in w]


def blocking_probability(erlangs: float, servers: int, capacity: int) -> float:
    """P(system full) = pi(K)."""
    if erlangs <= 0 or servers < 1 or capacity < servers:
        raise ValueError("require erlangs > 0, servers >= 1, capacity >= servers")
    return _pi(erlangs, servers, capacity)[capacity]


def delay_probability(erlangs: float, servers: int, capacity: int) -> float:
    """P(arrival must wait) = sum of pi(n) for c <= n < K."""
    if erlangs <= 0 or servers < 1 or capacity < servers:
        raise ValueError("require erlangs > 0, servers >= 1, capacity >= servers")
    pi = _pi(erlangs, servers, capacity)
    return sum(pi[servers:capacity])


def mean_queue_length(erlangs: float, servers: int, capacity: int) -> float:
    """Expected number of waiting calls."""
    if erlangs <= 0 or servers < 1 or capacity < servers:
        raise ValueError("require erlangs > 0, servers >= 1, capacity >= servers")
    pi = _pi(erlangs, servers, capacity)
    return sum((n - servers) * pi[n] for n in range(servers + 1, capacity + 1))


if __name__ == "__main__":
    load, c, k = 8.0, 10, 15
    print(f"M/M/c/K: {load} erlangs, {c} servers, capacity {k}")
    print(f"  Blocking probability: {blocking_probability(load, c, k):.6f}")
    print(f"  Delay probability:    {delay_probability(load, c, k):.6f}")
    print(f"  Mean queue length:    {mean_queue_length(load, c, k):.3f}")
