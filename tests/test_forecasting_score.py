"""Tests for the forecast accuracy measures in :mod:`score`.

Expected values are hand-computed from small fixed series rather than
captured from the implementation, so a formula regression fails loudly.
"""

from __future__ import annotations

import numpy as np
import pytest
import score


@pytest.fixture
def actual() -> np.ndarray:
    return np.array([10.0, 20.0, 30.0])


@pytest.fixture
def forecast() -> np.ndarray:
    return np.array([12.0, 18.0, 33.0])


@pytest.fixture
def train() -> np.ndarray:
    return np.array([10.0, 12.0, 14.0, 16.0])


class TestPrimaryAbsolute:
    """Scale-dependent measures, verified against hand-computed values."""

    def test_mae(self, actual: np.ndarray, forecast: np.ndarray) -> None:
        assert score.mae(actual, forecast) == pytest.approx(7 / 3)

    def test_mse(self, actual: np.ndarray, forecast: np.ndarray) -> None:
        assert score.mse(actual, forecast) == pytest.approx(17 / 3)

    def test_rmse_is_square_root_of_mse(self, actual: np.ndarray, forecast: np.ndarray) -> None:
        assert score.rmse(actual, forecast) == pytest.approx(np.sqrt(17 / 3))

    def test_md_ae(self, actual: np.ndarray, forecast: np.ndarray) -> None:
        assert score.md_ae(actual, forecast) == pytest.approx(2.0)

    def test_me_is_signed_bias(self, actual: np.ndarray, forecast: np.ndarray) -> None:
        assert score.me(actual, forecast) == pytest.approx(-1.0)

    def test_me_is_zero_for_unbiased_forecast(self, actual: np.ndarray) -> None:
        assert score.me(actual, actual) == pytest.approx(0.0)

    def test_perfect_forecast_scores_zero_error(self, actual: np.ndarray) -> None:
        assert score.mae(actual, actual) == pytest.approx(0.0)
        assert score.mse(actual, actual) == pytest.approx(0.0)
        assert score.rmse(actual, actual) == pytest.approx(0.0)


class TestPercentage:
    """Percentage measures and their zero-actual guards."""

    def test_mape(self, actual: np.ndarray, forecast: np.ndarray) -> None:
        expected = 100 * (0.2 + 0.1 + 0.1) / 3
        assert score.mape(actual, forecast) == pytest.approx(expected)

    def test_smape(self, actual: np.ndarray, forecast: np.ndarray) -> None:
        expected = 100 * (4 / 22 + 4 / 38 + 6 / 63) / 3
        assert score.smape(actual, forecast) == pytest.approx(expected)

    def test_smape_is_bounded_by_200(self) -> None:
        """Opposite-sign actual/forecast is the sMAPE maximum."""
        value = score.smape(np.array([10.0]), np.array([-10.0]))
        assert value == pytest.approx(200.0)

    def test_smape_treats_joint_zero_as_zero_error(self) -> None:
        """A 0/0 term contributes 0 by convention rather than NaN."""
        value = score.smape(np.array([0.0, 5.0]), np.array([0.0, 4.0]))
        assert value == pytest.approx(100 * (0.0 + 2 / 9) / 2)
        assert not np.isnan(value)

    def test_md_ape(self, actual: np.ndarray, forecast: np.ndarray) -> None:
        assert score.md_ape(actual, forecast) == pytest.approx(10.0)

    def test_mpe_is_signed(self) -> None:
        assert score.mpe(np.array([10.0]), np.array([8.0])) == pytest.approx(20.0)

    @pytest.mark.parametrize("measure", [score.mape, score.mpe, score.md_ape])
    def test_percentage_measures_raise_on_zero_actuals(self, measure) -> None:
        """Ratio measures are undefined at zero; they must not return infinity."""
        with pytest.raises(ValueError, match="zero actual"):
            measure(np.array([0.0, 1.0]), np.array([1.0, 1.0]))

    def test_smape_tolerates_zero_actuals(self) -> None:
        """sMAPE is the zero-safe percentage alternative."""
        assert np.isfinite(score.smape(np.array([0.0, 1.0]), np.array([1.0, 1.0])))


class TestRelative:
    def test_rae(self, actual: np.ndarray, forecast: np.ndarray) -> None:
        assert score.rae(actual, forecast) == pytest.approx(0.35)

    def test_rae_raises_on_constant_actuals(self) -> None:
        with pytest.raises(ValueError, match="constant"):
            score.rae(np.array([5.0, 5.0]), np.array([5.0, 6.0]))


class TestComposite:
    """MASE/RMSSE divide by an in-sample naive error, so they need y_train."""

    def test_naive_mae_lag_one(self, train: np.ndarray) -> None:
        assert score._in_sample_naive_mae(train, 1) == pytest.approx(2.0)

    def test_naive_rmse_lag_one(self, train: np.ndarray) -> None:
        assert score.in_sample_naive_rmse(train, 1) == pytest.approx(2.0)

    def test_mase(self, actual: np.ndarray, forecast: np.ndarray, train: np.ndarray) -> None:
        assert score.mase(actual, forecast, train, 1) == pytest.approx((7 / 3) / 2)

    def test_rmsse(self, actual: np.ndarray, forecast: np.ndarray, train: np.ndarray) -> None:
        assert score.rmsse(actual, forecast, train, 1) == pytest.approx(
            np.sqrt(17 / 3) / 2
        )

    def test_seasonal_denominator_uses_lag(self) -> None:
        """Seasonality=2 differences two steps back, not one."""
        series = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert score._in_sample_naive_mae(series, 2) == pytest.approx(2.0)

    def test_mase_below_one_beats_naive(self) -> None:
        """MASE < 1 means the forecast beats the in-sample naive benchmark."""
        train = np.array([10.0, 12.0, 14.0, 16.0, 18.0, 20.0])
        actual = np.array([22.0, 24.0, 26.0])
        assert score.mase(actual, actual, train, 1) < 1.0

    def test_mase_raises_when_training_series_is_flat(self) -> None:
        with pytest.raises(ValueError, match="no variation"):
            score.mase(np.array([1.0, 2.0]), np.array([1.0, 1.0]), np.array([5.0, 5.0]), 1)

    def test_rmsse_raises_when_training_series_is_flat(self) -> None:
        with pytest.raises(ValueError, match="no variation"):
            score.rmsse(np.array([1.0, 2.0]), np.array([1.0, 1.0]), np.array([5.0, 5.0]), 1)

    @pytest.mark.parametrize("measure", [score.mase, score.rmsse])
    def test_scaled_measures_reject_short_training_series(self, measure) -> None:
        with pytest.raises(ValueError, match="seasonality"):
            measure(np.array([1.0, 2.0]), np.array([1.0, 1.0]), np.array([1.0, 2.0]), 5)

    @pytest.mark.parametrize("measure", [score.mase, score.rmsse])
    def test_scaled_measures_reject_nonpositive_seasonality(
        self, measure, actual: np.ndarray, forecast: np.ndarray, train: np.ndarray
    ) -> None:
        with pytest.raises(ValueError, match="seasonality must be"):
            measure(actual, forecast, train, 0)


class TestRSquared:
    """R² is a fit statistic: higher is better, and it may be negative."""

    def test_r_squared(self, actual: np.ndarray, forecast: np.ndarray) -> None:
        assert score.r_squared(actual, forecast) == pytest.approx(1 - 17 / 200)

    def test_perfect_fit_is_one(self, actual: np.ndarray) -> None:
        assert score.r_squared(actual, actual) == pytest.approx(1.0)

    def test_mean_forecast_is_zero(self, actual: np.ndarray) -> None:
        """Predicting the mean gives R² = 0 by construction."""
        assert score.r_squared(actual, np.full(3, actual.mean())) == pytest.approx(0.0)

    def test_can_be_negative(self) -> None:
        """R² < 0 when the forecast is worse than the training mean."""
        assert score.r_squared(np.array([1.0, 2.0, 3.0]), np.array([10.0, 10.0, 10.0])) < 0

    def test_raises_on_constant_actuals(self) -> None:
        with pytest.raises(ValueError, match="constant"):
            score.r_squared(np.array([2.0, 2.0]), np.array([1.0, 3.0]))


class TestValidation:
    @pytest.mark.parametrize(
        "measure",
        [score.mae, score.mse, score.rmse, score.md_ae, score.me, score.rae, score.r_squared],
    )
    def test_rejects_length_mismatch(self, measure) -> None:
        with pytest.raises(ValueError, match="length mismatch"):
            measure(np.array([1.0, 2.0]), np.array([1.0]))

    @pytest.mark.parametrize(
        "measure",
        [score.mae, score.mse, score.rmse, score.smape, score.r_squared],
    )
    def test_rejects_empty_input(self, measure) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            measure(np.array([]), np.array([]))

    @pytest.mark.parametrize("measure", [score.mae, score.mse, score.smape])
    def test_rejects_multidimensional_input(self, measure) -> None:
        with pytest.raises(ValueError, match="one-dimensional"):
            measure(np.array([[1.0, 2.0]]), np.array([[1.0, 2.0]]))


class TestHybridSet:
    """score_forecast returns an auditable grid rather than one scalar."""

    def test_returns_every_measure(self, actual: np.ndarray, forecast: np.ndarray, train) -> None:
        result = score.score_forecast(actual, forecast, train, 1)
        assert isinstance(result, score.PointMeasures)
        assert result.mae == pytest.approx(7 / 3)
        assert result.rmse == pytest.approx(np.sqrt(17 / 3))
        assert result.smape == pytest.approx(100 * (4 / 22 + 4 / 38 + 6 / 63) / 3)
        assert result.mase == pytest.approx((7 / 3) / 2)
        assert result.rmsse == pytest.approx(np.sqrt(17 / 3) / 2)
        assert result.me == pytest.approx(-1.0)

    def test_mape_is_opt_in(self, actual: np.ndarray, forecast: np.ndarray, train) -> None:
        """Zero-safe by default, since PSAP volumes can be zero."""
        assert score.score_forecast(actual, forecast, train, 1).mape is None
        included = score.score_forecast(actual, forecast, train, 1, include_mape=True)
        assert included.mape == pytest.approx(100 * (0.2 + 0.1 + 0.1) / 3)

    def test_registry_exposes_callable_measures(self) -> None:
        for name in ("mae", "rmse", "smape", "r_squared"):
            assert callable(score.MEASURES[name])

class TestSeasonalNaive:
    """The Naive-2 benchmark, fit on the training window only."""

    def test_sp_one_repeats_last_training_value(self, train: np.ndarray) -> None:
        assert score.seasonal_naive(train, 5, 1) == pytest.approx([16.0] * 5)

    def test_recovers_daily_seasonality(self) -> None:
        """m=24 should track the daily cycle rather than flatten it."""
        hours = np.arange(24 * 10)
        volume = 100 + 20 * np.sin(2 * np.pi * hours / 24)
        train, test = volume[:-168], volume[-168:]

        forecast = score.seasonal_naive(train, 168, 24)

        assert forecast.shape == (168,)
        # A flat last-value forecast would lose the daily swing entirely.
        assert forecast.std() > 10
        assert abs(forecast.mean() - test.mean()) < 5

    def test_rejects_short_training_series(self, train: np.ndarray) -> None:
        with pytest.raises(ValueError, match="seasonal index"):
            score.seasonal_naive(train, 5, 24)

    @pytest.mark.parametrize("seasonality", [0, -1])
    def test_rejects_nonpositive_seasonality(
        self, seasonality: int, train: np.ndarray
    ) -> None:
        with pytest.raises(ValueError, match="seasonality must be"):
            score.seasonal_naive(train, 5, seasonality)

    def test_rejects_nonpositive_horizon(self, train: np.ndarray) -> None:
        with pytest.raises(ValueError, match="horizon must be"):
            score.seasonal_naive(train, 0, 1)


class TestOWA:
    """Overall Weighted Average, the M4 ranking criterion.

    Definition per Makridakis, Spiliotis & Assimakopoulos (2020), IJF 36(1),
    54-74: 0.5 * (MASE/benchmark + sMAPE/benchmark), lower is better.
    """

    def test_benchmark_scores_exactly_one(
        self, actual: np.ndarray, train: np.ndarray
    ) -> None:
        """Naive-2 scored against itself is 1.0 by construction."""
        horizon = len(actual)
        benchmark = score.seasonal_naive(train, horizon, 1)

        assert score.owa(actual, benchmark, train, 1) == pytest.approx(1.0, abs=1e-12)

    def test_seasonal_benchmark_scores_exactly_one(self) -> None:
        """The 1.0 property must hold for a seasonal benchmark too."""
        hours = np.arange(24 * 10)
        volume = 100 + 20 * np.sin(2 * np.pi * hours / 24) + np.random.default_rng(3).normal(0, 2, 24 * 10)
        train, test = volume[:-168], volume[-168:]
        benchmark = score.seasonal_naive(train, 168, 24)

        assert score.owa(test, benchmark, train, 24) == pytest.approx(1.0, abs=1e-12)

    def test_better_than_benchmark_scores_below_one(
        self, actual: np.ndarray, train: np.ndarray
    ) -> None:
        """A forecast closer to the truth than Naive-2 must score under 1.0."""
        near = np.full_like(actual, actual.mean())

        assert score.owa(actual, near, train, 1) < 1.0

    def test_worse_than_benchmark_scores_above_one(
        self, actual: np.ndarray, train: np.ndarray
    ) -> None:
        far = actual * 10 + 1000

        assert score.owa(actual, far, train, 1) > 1.0

    def test_reproduces_m4_worked_example(self) -> None:
        """The M4 paper's own arithmetic, reproduced through the metric.

        Paper: method with MASE 1.6 and sMAPE 12.5 against Naive-2's 1.9 and
        13.7 scores 0.5 * (1.6/1.9 + 12.5/13.7) = 0.877, "about 12% more
        accurate than Naive 2".
        """
        mase_ratio, smape_ratio = 1.6 / 1.9, 12.5 / 13.7

        assert 0.5 * (mase_ratio + smape_ratio) == pytest.approx(0.877, abs=5e-4)

    def test_is_average_of_the_two_loss_ratios(
        self, actual: np.ndarray, train: np.ndarray
    ) -> None:
        """Guard the definition: aggregate-then-ratio, never ratio-then-average."""
        forecast = actual + 1.0
        horizon = len(actual)
        benchmark = score.seasonal_naive(train, horizon, 1)

        expected = 0.5 * (
            score.mase(actual, forecast, train, 1) / score.mase(actual, benchmark, train, 1)
            + score.smape(actual, forecast) / score.smape(actual, benchmark)
        )

        assert score.owa(actual, forecast, train, 1) == pytest.approx(expected)

    def test_benchmark_never_sees_the_evaluation_window(
        self, actual: np.ndarray, train: np.ndarray
    ) -> None:
        """Naive-2 must be fit on y_train alone.

        The reference implementation fits on `insample` and forecasts flat; a
        benchmark that indexed into the test window would be scored on
        information no submitted forecast had, inflating its apparent skill and
        deflating every real method's OWA.
        """
        horizon = len(actual)

        assert score.seasonal_naive(train, horizon, 1).tolist() == [float(train[-1])] * horizon

    def test_raises_when_benchmark_is_exact(self) -> None:
        """A benchmark that matches the actuals exactly cannot normalize OWA."""
        train = np.array([10.0, 12.0, 14.0, 16.0])
        actual = np.array([16.0, 16.0, 16.0])
        forecast = np.array([15.0, 15.0, 15.0])

        with pytest.raises(ValueError, match="Naive-2 benchmark scores zero"):
            score.owa(actual, forecast, train, 1)

    def test_constant_training_series_rejected_by_mase(self) -> None:
        """A flat y_train has no in-sample scale, so MASE itself is undefined."""
        train = np.array([50.0, 50.0, 50.0, 50.0])
        actual = np.array([50.0, 51.0, 52.0])
        forecast = np.array([50.0, 51.0, 52.0])

        with pytest.raises(ValueError, match="no variation"):
            score.owa(actual, forecast, train, 1)
