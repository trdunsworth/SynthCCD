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