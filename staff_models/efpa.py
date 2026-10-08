"""Erlang Fixed-Point Approximation (EFPA) for skill-based call routing.

In skill-based routing, several call types ("routes") share pools of
agents, and each route may require a resource (agent) from more than one
pool. EFPA decouples the network into per-pool Erlang B models whose
offered loads are computed from the other pools' blocking probabilities,
iterating to a fixed point.

* Pools: capacities ``C_j``
* Routes ``r``: offered load ``a_r`` (erlangs), requiring one agent from
  each pool in ``r.links``. A route call is blocked if any required pool
  is full.

Iteration:

    A_j = sum_{r uses j} a_r * prod_{l in r, l != j} (1 - B_l)
    B_j = ErlangB(C_j, A_j)
    B_r = 1 - prod_{j in r.links} (1 - B_j)

Reference: Jennings & Mandelbaum (1996), "Call Centers with Skill-Based
Routing," Operations Research; Kelly (1991) loss networks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from erlang_b import blocking_probability


@dataclass
class Route:
    """A skill/call type offered to an ordered set of agent pools."""

    name: str
    erlangs: float
    links: list[int] = field(default_factory=list)


def pool_blocking(
    capacities: list[int],
    routes: list[Route],
    tol: float = 1e-10,
    max_iter: int = 10_000,
) -> list[float]:
    """Return converged per-pool blocking probabilities."""
    if any(c < 1 for c in capacities):
        raise ValueError("capacities must be >= 1")
    for r in routes:
        if r.erlangs <= 0 or not r.links:
            raise ValueError(f"invalid route {r.name!r}")
        if any(i < 0 or i >= len(capacities) for i in r.links):
            raise ValueError(f"route {r.name!r} references unknown pool")

    b = [0.0] * len(capacities)
    for _ in range(max_iter):
        b_new = []
        for j, c_j in enumerate(capacities):
            offered = 0.0
            for r in routes:
                if j in r.links:
                    product = 1.0
                    for i in r.links:
                        if i != j:
                            product *= 1 - b[i]
                    offered += r.erlangs * product
            b_new.append(blocking_probability(offered, c_j) if offered > 0 else 0.0)
        if max(abs(x - y) for x, y in zip(b_new, b)) < tol:
            return b_new
        b = b_new
    raise RuntimeError("EFPA fixed-point iteration did not converge")


def route_blocking(route: Route, pool_blocking_probs: list[float]) -> float:
    """Blocking probability for a route: 1 - prod(1 - B_j) over its pools."""
    product = 1.0
    for j in route.links:
        product *= 1 - pool_blocking_probs[j]
    return 1 - product


def analyze(capacities: list[int], routes: list[Route]) -> dict:
    """Return per-pool blocking and per-route blocking/carried load."""
    b = pool_blocking(capacities, routes)
    per_route = {}
    for r in routes:
        rb = route_blocking(r, b)
        per_route[r.name] = {"blocking": rb, "carried_erlangs": r.erlangs * (1 - rb)}
    return {"pool_blocking": b, "routes": per_route}


if __name__ == "__main__":
    capacities = [20, 15, 25]
    routes = [
        Route("911 law", 12.0, [0, 2]),
        Route("fire", 8.0, [1, 2]),
        Route("ems shared", 5.0, [2]),
    ]
    result = analyze(capacities, routes)
    for j, b in enumerate(result["pool_blocking"]):
        print(f"pool {j}: blocking {b:.4%}")
    for name, stats in result["routes"].items():
        print(f"  {name}: blocking {stats['blocking']:.4%}, carried {stats['carried_erlangs']:.2f} Erl")
