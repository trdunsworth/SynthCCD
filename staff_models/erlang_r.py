"""Erlang-R model: loss system with reattempts (retry).

In busy call centres, blocked or abandoned callers often dial again
("redials"), so the offered load is not exogenous — it is amplified by the
retry behavior itself. The Erlang-R model captures this for an M/M/c/c
trunk group where each blocked call is retried with probability ``r``:

    lambda_eff = lambda / (1 - r * B(c, a_eff))

where ``a_eff = lambda_eff / mu`` is the effective offered load and
``B`` is the Erlang B blocking function. The model is solved by iterating
the fixed point to convergence.

Reference: commonly attributed to teletraffic engineering practice; see
e.g. discussions of retry/redial models in contact-centre workforce
management literature.
"""

from __future__ import annotations

from erlang_b import blocking_probability


def effective_offered_load(lam: float, mu: float, c: int, r: float, tol: float = 1e-10) -> float:
    """Return the retry-inflated offered load in erlangs via fixed-point iteration."""
    if lam <= 0 or mu <= 0 or c < 1 or not 0 <= r < 1:
        raise ValueError("require lam, mu > 0, c >= 1, 0 <= r < 1")
    a = lam / mu
    for _ in range(1000):
        b = blocking_probability(a, c)
        a_new = (lam / mu) / (1 - r * b)
        if abs(a_new - a) < tol:
            return a_new
        a = a_new
    raise RuntimeError("retry fixed-point iteration did not converge")


def retry_adjusted_blocking(lam: float, mu: float, c: int, r: float) -> float:
    """Blocking probability accounting for reattempt amplification."""
    a_eff = effective_offered_load(lam, mu, c, r)
    return blocking_probability(a_eff, c)


if __name__ == "__main__":
    lam_per_min, aht_s, trunks = 12.0, 180.0, 40
    mu = 1 / aht_s
    for r in (0.0, 0.3, 0.6, 0.9):
        a_eff = effective_offered_load(lam_per_min / 60, mu, trunks, r)
        b = retry_adjusted_blocking(lam_per_min / 60, mu, trunks, r)
        print(f"r={r:.1f}: effective load {a_eff:.2f} erlangs, blocking {b:.4%}")
