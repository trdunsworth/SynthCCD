"""Tests for answer-time lognormal calibration helpers."""

import numpy as np
import pytest

from synth911gen3.calibration import (
    answer_time_config_block,
    fit_lognormal_from_percentiles,
    fit_lognormal_from_samples,
    lognormal_cdf,
)


def test_fit_from_percentiles_recovers_nena_like_parameters() -> None:
    # NENA 020.1-2020: 90% within 15s, 95% within 20s.
    mean, sigma = fit_lognormal_from_percentiles([(15.0, 0.90), (20.0, 0.95)])
    assert mean == pytest.approx(7.43, rel=0.02)
    assert sigma == pytest.approx(0.79, rel=0.02)
    # The fit should reproduce the supplied percentiles.
    assert lognormal_cdf(mean, sigma, 15.0) == pytest.approx(0.90, abs=1e-2)
    assert lognormal_cdf(mean, sigma, 20.0) == pytest.approx(0.95, abs=1e-2)


def test_fit_from_percentiles_more_than_two_points_least_squares() -> None:
    # A known distribution: true mean=10, sigma=0.5 -> true mu = ln(10) - 0.125.
    true_mean, true_sigma = 10.0, 0.5
    targets = [(5.0, lognormal_cdf(true_mean, true_sigma, 5.0)),
               (10.0, lognormal_cdf(true_mean, true_sigma, 10.0)),
               (25.0, lognormal_cdf(true_mean, true_sigma, 25.0))]
    mean, sigma = fit_lognormal_from_percentiles(targets)
    assert mean == pytest.approx(true_mean, rel=0.05)
    assert sigma == pytest.approx(true_sigma, rel=0.05)


def test_fit_from_percentiles_rejects_few_points() -> None:
    with pytest.raises(ValueError):
        fit_lognormal_from_percentiles([(15.0, 0.9)])


def test_fit_from_percentiles_rejects_bad_probability() -> None:
    with pytest.raises(ValueError):
        fit_from = fit_lognormal_from_percentiles
        fit_from([(15.0, 1.0), (20.0, 1.2)])


def test_fit_from_percentiles_rejects_nonpositive_threshold() -> None:
    with pytest.raises(ValueError):
        fit_lognormal_from_percentiles([(0.0, 0.5), (-1.0, 0.9)])


def test_fit_from_percentiles_rejects_non_monotonic() -> None:
    # Larger threshold paired with smaller probability -> negative sigma.
    with pytest.raises(ValueError):
        fit_lognormal_from_percentiles([(20.0, 0.90), (15.0, 0.95)])


def test_fit_from_samples_recovers_parameters() -> None:
    rng = np.random.default_rng(20240829)
    true_mu, true_sigma = 1.8, 0.6
    raw = rng.lognormal(true_mu, true_sigma, size=20000)
    mean, sigma = fit_lognormal_from_samples(raw)
    assert mean == pytest.approx(np.exp(true_mu + true_sigma**2 / 2), rel=0.05)
    assert sigma == pytest.approx(true_sigma, rel=0.05)


def test_fit_from_samples_rejects_too_few() -> None:
    with pytest.raises(ValueError):
        fit_lognormal_from_samples([1.0])


def test_fit_from_samples_drops_nonpositive() -> None:
    rng = np.random.default_rng(1)
    raw = rng.lognormal(1.8, 0.6, size=5000).tolist()
    raw += [0.0, -1.0, float("nan")]
    mean, sigma = fit_lognormal_from_samples(raw)
    assert mean > 0 and sigma > 0


def test_lognormal_cdf_matches_scipy() -> None:
    from scipy.stats import lognorm

    mean, sigma = 7.0, 0.7
    mu = np.log(mean) - sigma**2 / 2
    for thr in (5.0, 10.0, 15.0, 40.0):
        expected = float(lognorm.cdf(thr, s=sigma, scale=np.exp(mu)))
        assert lognormal_cdf(mean, sigma, thr) == pytest.approx(expected, rel=1e-9)


def test_lognormal_cdf_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        lognormal_cdf(0.0, 0.7, 10.0)


def test_answer_time_config_block_keys() -> None:
    block = answer_time_config_block((7.0, 0.7), (18.0, 0.9))
    assert block == {
        "nine_one_one_answer_time_mean": 7.0,
        "nine_one_one_answer_time_sigma": 0.7,
        "non_emergency_answer_time_mean": 18.0,
        "non_emergency_answer_time_sigma": 0.9,
    }


def test_answer_time_config_block_defaults_ne_to_911() -> None:
    block = answer_time_config_block((7.0, 0.7))
    assert block["non_emergency_answer_time_mean"] == 7.0
    assert block["non_emergency_answer_time_sigma"] == 0.7
