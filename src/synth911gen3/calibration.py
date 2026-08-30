"""Calibrate answer-time lognormal parameters from real PSAP data.

Open 911 data (data.gov, city portals, NENA scorecards) rarely publishes raw
per-call answer-time histograms. What it publishes is *percentile compliance* —
e.g. "90% of calls answered within 15 s, 95% within 20 s". Those points let us
fit the lognormal that drives SynthCCD's answer-time simulation, so a center's
defaults can be anchored to its own published performance instead of a
hand-picked number.

Two fitting strategies are provided:

* :func:`fit_lognormal_from_percentiles` — given ``(threshold_seconds,
  cumulative_probability)`` points, solve the lognormal CDF
  ``p = Φ((ln t − μ)/σ)`` linearly (``ln t = μ + σ·Φ⁻¹(p)``). Two points solve
  exactly; more than two use ordinary least squares.
* :func:`fit_lognormal_from_samples` — maximum-likelihood fit from raw per-call
  answer times (e.g. CAD event logs / NYC 911 End-to-End data), the gold
  standard when microdata is available.

Both return ``(mean_seconds, sigma)`` matching the
``*_answer_time_mean`` / ``*_answer_time_sigma`` keys consumed by
:mod:`synth911gen3.generators.phone_metrics`.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from scipy.stats import norm

__all__ = [
    "answer_time_config_block",
    "fit_lognormal_from_percentiles",
    "fit_lognormal_from_samples",
    "lognormal_cdf",
]


def fit_lognormal_from_percentiles(
    points: Sequence[tuple[float, float]],
) -> tuple[float, float]:
    """Fit ``(mean_seconds, sigma)`` of a lognormal from CDF points.

    Each point is ``(threshold_seconds, cumulative_probability)`` with
    ``0 < p < 1`` and ``threshold > 0``. The lognormal CDF satisfies
    ``p = Φ((ln t − μ)/σ)`` which rearranges to ``ln t = μ + σ·Φ⁻¹(p)`` — a
    straight line in ``Φ⁻¹(p)`` with intercept ``μ`` and slope ``σ``. With
    exactly two points this solves exactly; with more it uses ordinary least
    squares. Returns ``(mean_seconds, sigma)`` where
    ``mean_seconds = exp(μ + σ²/2)``.
    """
    pts = [(float(t), float(p)) for t, p in points]
    if len(pts) < 2:
        raise ValueError("At least two (threshold, probability) points are required.")
    t = np.array([tt for tt, _ in pts], dtype=float)
    p = np.array([pp for _, pp in pts], dtype=float)
    if np.any(t <= 0):
        raise ValueError("Threshold seconds must be positive.")
    if np.any((p <= 0) | (p >= 1)):
        raise ValueError("Cumulative probabilities must lie strictly between 0 and 1.")
    x = norm.ppf(p)  # Φ⁻¹(p)
    y = np.log(t)
    # Ordinary least squares of y on x: slope = σ, intercept = μ.
    sigma, mu = np.polyfit(x, y, 1)
    if sigma <= 0:
        raise ValueError(
            "Fitted sigma is non-positive; ensure larger thresholds pair with "
            "larger probabilities (monotonic CDF)."
        )
    mean = float(np.exp(mu + sigma**2 / 2))
    return mean, float(sigma)


def fit_lognormal_from_samples(
    samples: Sequence[float],
) -> tuple[float, float]:
    """Maximum-likelihood ``(mean_seconds, sigma)`` from raw answer times.

    ``samples`` are per-call answer times in seconds (all positive). The MLE of
    a lognormal is the normal MLE on the log-transformed data:
    ``μ = mean(ln x)``, ``σ = std(ln x, ddof=1)``. Returns
    ``(mean_seconds, sigma)`` with ``mean_seconds = exp(μ + σ²/2)``.
    """
    arr = np.asarray(samples, dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if arr.size < 2:
        raise ValueError("At least two positive, finite samples are required.")
    log_x = np.log(arr)
    mu = float(log_x.mean())
    sigma = float(log_x.std(ddof=1))
    if sigma <= 0:
        raise ValueError("Sample variance is zero; cannot fit a lognormal.")
    mean = float(np.exp(mu + sigma**2 / 2))
    return mean, float(sigma)


def lognormal_cdf(mean_seconds: float, sigma: float, threshold: float) -> float:
    """Cumulative probability a lognormal answer time is ``<= threshold`` seconds."""
    if mean_seconds <= 0 or sigma <= 0 or threshold <= 0:
        raise ValueError("mean_seconds, sigma, and threshold must be positive.")
    mu = np.log(mean_seconds) - sigma**2 / 2
    return float(norm.cdf((np.log(threshold) - mu) / sigma))


def answer_time_config_block(
    nine_one_one: tuple[float, float],
    non_emergency: tuple[float, float] | None = None,
) -> dict[str, float]:
    """Build the four ``phone_metrics`` answer-time keys from fitted pairs.

    ``nine_one_one`` and ``non_emergency`` are ``(mean_seconds, sigma)`` tuples
    from either fit function. If ``non_emergency`` is omitted it defaults to the
    9-1-1 pair (callers can then edit it by hand). Returns a dict ready to drop
    into a realism YAML ``phone_metrics:`` section.
    """
    mean_911, sigma_911 = nine_one_one
    if non_emergency is None:
        mean_ne, sigma_ne = mean_911, sigma_911
    else:
        mean_ne, sigma_ne = non_emergency
    return {
        "nine_one_one_answer_time_mean": float(mean_911),
        "nine_one_one_answer_time_sigma": float(sigma_911),
        "non_emergency_answer_time_mean": float(mean_ne),
        "non_emergency_answer_time_sigma": float(sigma_ne),
    }
