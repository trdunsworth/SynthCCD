"""Square-root staffing rule (Halfin-Whitt QED regime).

In the Quality-and-Efficiency-Driven (QED) regime, staff a call centre so
that utilization converges to 100% as volume grows, while keeping delay
probabilitybounded away from both 0 and 1:

    c = R + beta * sqrt(R),   R = offered load in erlangs

* ``beta = 0``  -> maximal utilization, ~100% of callers delayed
* ``beta ~= 1`` -> classic "square-root staffing"
* higher beta  -> more slack, lower delay probability, lower occupancy

The delay probability interpolates between Erlang B and Erlang C behavior
via the Halfin-Whitt function ``alpha(beta) = [1 + beta * Phi(beta)/phi(beta)]^-1``.

Reference: Halfin & Whitt, "Heavy-Traffic Limits for Queues with Many
Exponential Servers," Operations Research 1981.
"""

from __future__ import annotations

import math


def staffing_level(offered_load: float, beta: float) -> int:
    """Return the agent count ``c = ceil(R + beta*sqrt(R))``."""
    if offered_load <= 0 or beta < 0:
        raise ValueError("require offered_load > 0, beta >= 0")
    return math.ceil(offered_load + beta * math.sqrt(offered_load))


def delay_probability(offered_load: float, beta: float) -> float:
    """Approximate probability an arrival is delayed in the QED regime."""
    if offered_load <= 0 or beta < 0:
        raise ValueError("require offered_load > 0, beta >= 0")
    phi = math.exp(-0.5 * beta**2) / math.sqrt(2 * math.pi)
    cdf = 0.5 * (1 + math.erf(beta / math.sqrt(2)))
    if beta == 0:
        return 1.0
    return 1.0 / (1.0 + beta * cdf / phi)


def implied_occupancy(offered_load: float, beta: float) -> float:
    """Approximate occupancy ``R / c`` under square-root staffing."""
    c = staffing_level(offered_load, beta)
    return offered_load / c


if __name__ == "__main__":
    for beta in (0.5, 1.0, 1.5, 2.0):
        c = staffing_level(50.0, beta)
        print(
            f"beta={beta:.1f}: agents={c}, occupancy={implied_occupancy(50.0, beta):.3f}, "
            f"delay ~ {delay_probability(50.0, beta):.3f}"
        )
