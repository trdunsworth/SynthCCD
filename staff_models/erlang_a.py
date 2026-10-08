"""Erlang A model (M/M/c+M delay system with abandonment).

Adds customer impatience to the Erlang C model: each waiting caller abandons
after an exponentially distributed patience time with mean ``1 / theta``.

Birth-death steady state (state n = number in system):

* ``n < c``:  birth rate ``lam``, death rate ``n * mu``
* ``n >= c``: birth rate ``lam``, death rate ``c * mu + (n - c) * theta``

This has no simpler closed form than Erlang C, so the model is evaluated by
truncating the birth-death sum once the tail mass is negligible.

Key outputs:

* ``delay_probability`` — probability an arrival is queued before service
* ``abandonment_probability`` — fraction of arrivals that hang up
* ``mean_wait_time`` — average time in queue per arrival (Little's law)
* ``mean_wait_delayed`` — average queue wait given the caller is delayed

Reference: Garnett, Mandelbaum & Reiman (2002); Gans, Koole & Mandelbaum,
"Telephone Call Centers: Tutorial, Review, and Research Prospects," 2003.
"""

from __future__ import annotations


def _steady_state(lam: float, mu: float, c: int, theta: float, tol: float = 1e-12) -> list[float]:
    """Return the unnormalized-then-normalized stationary distribution pi[n]."""
    pi = [1.0]
    n = 0
    while True:
        if n < c:
            pi.append(pi[-1] * lam / ((n + 1) * mu))
        else:
            pi.append(pi[-1] * lam / (c * mu + (n + 1 - c) * theta))
        n += 1
        if pi[-1] < tol * pi[0] and n > c:
            break
        if n > 100_000:
            raise RuntimeError("birth-death sum did not converge")
    total = sum(pi)
    return [p / total for p in pi]


def analyze(lam: float, mu: float, c: int, theta: float) -> dict[str, float]:
    """Return summary metrics for an Erlang A system.

    Args:
        lam: Arrival rate.
        mu: Service rate per server.
        c: Number of servers.
        theta: Abandonment rate; mean patience is ``1/theta`` seconds.

    Returns:
        Dict with delay_probability, abandonment_probability, mean_wait_time,
        mean_wait_delayed, mean_occupancy, and offered_load (erlangs).
    """
    if min(lam, mu, theta) <= 0 or c < 1:
        raise ValueError("lam, mu, theta must be positive and c >= 1")
    pi = _steady_state(lam, mu, c, theta)
    p_delay = sum(pi[c:])
    p_abandon = sum(pi[n] * (n - c) * theta / lam for n in range(c + 1, len(pi)))
    lq = sum((n - c) * pi[n] for n in range(c + 1, len(pi)))
    mean_wq = lq / lam
    mean_wq_delayed = mean_wq / p_delay if p_delay > 0 else 0.0
    occupancy = sum(n * pi[n] for n in range(len(pi)))
    return {
        "delay_probability": p_delay,
        "abandonment_probability": p_abandon,
        "mean_wait_time": mean_wq,
        "mean_wait_delayed": mean_wq_delayed,
        "mean_occupancy": occupancy,
        "offered_load": lam / mu,
    }


if __name__ == "__main__":
    results = analyze(lam=0.05, mu=1 / 240, c=15, theta=1 / 60)
    print("Erlang A: lam=0.05/s, 240s AHT, 15 agents, 60s mean patience")
    for key, value in results.items():
        print(f"  {key}: {value:.4f}")
