"""Occupancy-based staffing.

The simplest industry staffing heuristic: choose the smallest agent count
that keeps long-run occupancy (utilization) at or below a target.

    c = ceil(R / target_occupancy),   R = lambda / mu

Unlike Erlang C/A, it ignores service-level thresholds entirely, so it is
used as a capacity floor or sanity bound rather than a primary model.
Typical call-centre targets are 0.80-0.90.

Reference: standard contact-centre workforce management practice.
"""

from __future__ import annotations

import math


def staffing_level(offered_load: float, target_occupancy: float) -> int:
    """Return ``ceil(R / target_occupancy)``."""
    if offered_load <= 0 or not 0 < target_occupancy <= 1:
        raise ValueError("require offered_load > 0, 0 < target_occupancy <= 1")
    return max(1, math.ceil(offered_load / target_occupancy))


def achieved_occupancy(offered_load: float, agents: int) -> float:
    """Occupancy implied by a given agent count."""
    if offered_load <= 0 or agents < 1:
        raise ValueError("require offered_load > 0, agents >= 1")
    return offered_load / agents


if __name__ == "__main__":
    for target in (0.80, 0.85, 0.90):
        c = staffing_level(12.0, target)
        print(f"target occupancy {target:.0%}: {c} agents (actual {achieved_occupancy(12.0, c):.3f})")
