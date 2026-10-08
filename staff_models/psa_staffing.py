"""Pointwise Stationary Approximation (PSA) for intraday staffing.

Real arrival rates vary through the day, so a single Erlang-C calculation
mis-staffs the day. PSA treats each short interval as if its arrival rate
were stationary, evaluates the Erlang C level of service pointwise, and
staffs each interval independently. It works well when arrival rates
change slowly relative to the mean handle time.

Given intervals with arrival rates ``lam[i]``, a common service rate
``mu``, and target service level (fraction answered within ``SL_threshold``
seconds), PSA returns the per-interval agent count: the smallest ``c``
whose Erlang C service level meets the target.

Reference: Jennings, Mandelbaum, Massey & Whitt (1996), "Server Staffing
to Stabilize Queues with Time-Varying Arrival Rates."
"""

from __future__ import annotations

from erlang_c import service_level


def staff_for_interval(lam: float, mu: float, threshold: float, target_sl: float, max_agents: int = 10_000) -> int:
    """Smallest agent count whose Erlang C SL meets ``target_sl`` for rate ``lam``."""
    if lam <= 0 or mu <= 0 or not 0 < target_sl < 1:
        raise ValueError("require lam, mu > 0 and 0 < target_sl < 1")
    offered = lam / mu
    c = int(offered) + 1
    while c <= max_agents:
        if service_level(offered, c, mu, threshold) >= target_sl:
            return c
        c += 1
    raise RuntimeError("no feasible staffing within max_agents")


def intraday_staffing(rates: list[float], mu: float, threshold: float, target_sl: float) -> list[int]:
    """Return the per-interval agent counts for a list of arrival rates."""
    return [staff_for_interval(lam, mu, threshold, target_sl) for lam in rates]


if __name__ == "__main__":
    mu = 1 / 300.0
    rates = [0.05, 0.08, 0.14, 0.20, 0.16, 0.10, 0.06, 0.04]
    plan = intraday_staffing(rates, mu, threshold=20.0, target_sl=0.80)
    for i, (lam, c) in enumerate(zip(rates, plan)):
        print(f"interval {i}: lam={lam:.2f}/s -> {c} agents")
