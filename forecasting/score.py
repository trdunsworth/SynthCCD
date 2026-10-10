"""Forecast accuracy measures organised by Botchkarev's taxonomy.

Reference
---------
A. Botchkarev, "Performance Metrics (Error Measures) in Machine Learning
Regression, Forecasting and Prognostics: Properties and Typology",
arXiv:1809.03006 (2018); published in *Interdisciplinary Journal of
Information, Knowledge and Management* 14 (2019) 45-79,
doi:10.28945/4184.

Botchkarev groups error measures into four categories, used verbatim here:

``primary metrics``
    The largest group. Each is built from three choices: how point distance
    is measured, how (if at all) it is normalised, and how point distances
    are aggregated over the data set.
``extended metrics``
    A primary metric with further normalisation applied *after* aggregation,
    which is what separates them from primary metrics.
``composite metrics``
    Two or more primary metrics combined into one result. MASE is the
    canonical example: it is MAE divided by an in-sample naive MAE.
``hybrid sets of metrics``
    Several metrics reported side by side, deliberately *not* reduced to a
    single number, because each captures a property the others miss.

Why the taxonomy matters here
-----------------------------
The experiment grid varies volume level and noise, so scale-dependent
measures (MAE, MSE, RMSE) are comparable only *within* one series.
Botchkarev's recommended scale-free measures -- MASE and RMSSE -- divide by
an in-sample naive error and are therefore comparable *across* series. The
scenario grid in ``forecasting_experiment.md`` is exactly the case where that
distinction decides the ranking, so both families are provided and the choice
is documented per function.

Known defects, carried over from Botchkarev's critique
------------------------------------------------------
* Ratio measures (MAPE, MPE) are asymmetric -- over- and under-prediction are
  penalised differently -- and are undefined when an actual is zero. Call
  volumes can legitimately be zero, so :func:`mape` and :func:`mpe` raise on
  zero actuals rather than returning a silently infinite score. Prefer
  :func:`smape` or :func:`mase` when zeros are possible.
* Squared-error measures (MSE, RMSE) are outlier-sensitive: one large error
  dominates. :func:`mae` is the robust counterpart.
* A single composite number can mask a breakdown -- good MAE but pathological
  MAPE. Botchkarev therefore prefers *hybrid sets*: this module returns a dict
  of measures from :func:`score_forecast` rather than collapsing to one
  scalar. Sekitani-Murakami OWA (:func:`owa`) is provided as an explicit,
  opt-in ranking device, not as a summary of the grid.

Interval and density measures (PICP, interval score, Winkler) are outside
Botchkarev's four categories; see Gneiting & Raftery (2007). They are not
implemented here.

Conventions
-----------
* Inputs are ``float`` arrays of equal, non-zero length; ``y_true`` is actual
  and ``y_pred`` is forecast. MASE and RMSSE additionally require the
  in-sample ``y_train`` series, because their denominators are in-sample
  naive errors.
* Percentage measures return percent (0-100 for MAPE, 0-200 for sMAPE).
* Every measure returns a ``float``; lower is better except
  :func:`r_squared`, where higher is better and which is a fit statistic
  rather than an error measure (Botchkarev includes it only within a
  composite).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "MEASURES",
    "PointMeasures",
    "in_sample_naive_rmse",
    "mae",
    "mape",
    "mase",
    "md_ae",
    "md_ape",
    "me",
    "mpe",
    "mse",
    "r_squared",
    "rae",
    "rmse",
    "rmsse",
    "score_forecast",
    "smape",
]

FloatArray = NDArray[np.float64]


class PointMeasures(NamedTuple):
    """A scored forecast: one value per measure, in the taxonomy's order.

    Bundling the measures keeps them travelling together, so a ranking built
    on RMSE cannot silently drop the scale-free MASE that makes it auditable
    across scenarios.
    """

    mae: float
    mse: float
    rmse: float
    mape: float | None
    smape: float
    mase: float
    rmsse: float
    r_squared: float
    me: float


def _as_pair(y_true: FloatArray, y_pred: FloatArray) -> tuple[FloatArray, FloatArray]:
    """Validate and coerce an (actual, forecast) pair to equal-length float arrays."""
    actual = np.asarray(y_true, dtype=np.float64)
    forecast = np.asarray(y_pred, dtype=np.float64)
    if actual.ndim != 1 or forecast.ndim != 1:
        raise ValueError("y_true and y_pred must be one-dimensional")
    if actual.shape != forecast.shape:
        raise ValueError(f"length mismatch: y_true={actual.size}, y_pred={forecast.size}")
    if actual.size == 0:
        raise ValueError("y_true and y_pred must be non-empty")
    return actual, forecast


def _in_sample_naive_mae(y_train: FloatArray, seasonality: int) -> float:
    """Mean |y_t - y_{t-m}| over the training series; the MASE denominator.

    With ``seasonality=1`` this is the ordinary in-sample one-step naive MAE
    of Hyndman & Koehler (2006); with ``seasonality=24`` it is the same
    measure applied to the daily lag, which is the appropriate denominator for
    hourly PSAP volume.
    """
    train = np.asarray(y_train, dtype=np.float64)
    if train.ndim != 1:
        raise ValueError("y_train must be one-dimensional")
    m = int(seasonality)
    if m < 1:
        raise ValueError(f"seasonality must be >= 1, got {m}")
    if train.size <= m:
        raise ValueError(
            f"y_train needs more than seasonality={m} points to form a naive lag, "
            f"got {train.size}"
        )
    return float(np.mean(np.abs(train[m:] - train[:-m])))


def in_sample_naive_rmse(y_train: FloatArray, seasonality: int) -> float:
    """Root mean square of the in-sample naive differences; the RMSSE denominator.

    The squared-error analogue of :func:`_in_sample_naive_mae`, per Hyndman &
    Koehler (2006).
    """
    train = np.asarray(y_train, dtype=np.float64)
    m = int(seasonality)
    if m < 1:
        raise ValueError(f"seasonality must be >= 1, got {m}")
    if train.size <= m:
        raise ValueError(
            f"y_train needs more than seasonality={m} points to form a naive lag, "
            f"got {train.size}"
        )
    return float(np.sqrt(np.mean((train[m:] - train[:-m]) ** 2)))


# ---------------------------------------------------------------------------
# Primary metrics -- absolute / squared error (scale-dependent)
# ---------------------------------------------------------------------------


def mae(y_true: FloatArray, y_pred: FloatArray) -> float:
    """Mean Absolute Error: ``mean(|y - y_hat|)``.

    Scale-dependent and outlier-robust. The default within-series measure;
    not comparable across scenarios of differing volume.
    """
    actual, forecast = _as_pair(y_true, y_pred)
    return float(np.mean(np.abs(actual - forecast)))


def mse(y_true: FloatArray, y_pred: FloatArray) -> float:
    """Mean Squared Error: ``mean((y - y_hat)^2)``.

    Scale-dependent and outlier-sensitive: a single large error dominates the
    average. Reported alongside :func:`mae` rather than instead of it.
    """
    actual, forecast = _as_pair(y_true, y_pred)
    return float(np.mean((actual - forecast) ** 2))


def rmse(y_true: FloatArray, y_pred: FloatArray) -> float:
    """Root Mean Squared Error: ``sqrt(mean((y - y_hat)^2))``.

    Same units as ``y``, so it is directly comparable to the actuals and is
    the form used for the M4/M5 competition error ratios.
    """
    actual, forecast = _as_pair(y_true, y_pred)
    return float(np.sqrt(np.mean((actual - forecast) ** 2)))


def md_ae(y_true: FloatArray, y_pred: FloatArray) -> float:
    """Median Absolute Error: ``median(|y - y_hat|)``.

    The outlier-robust counterpart to :func:`mae`; reported in Botchkarev's
    taxonomy as a primary metric differing only in aggregation.
    """
    actual, forecast = _as_pair(y_true, y_pred)
    return float(np.median(np.abs(actual - forecast)))


def me(y_true: FloatArray, y_pred: FloatArray) -> float:
    """Mean Error: ``mean(y - y_hat)``, i.e. signed bias.

    Positive means the forecast under-predicts on average. A measure of
    systematic bias, not of accuracy -- an unbiased forecast can still be
    badly wrong, which is why it belongs in a hybrid set alongside :func:`mae`.
    """
    actual, forecast = _as_pair(y_true, y_pred)
    return float(np.mean(actual - forecast))


def rae(y_true: FloatArray, y_pred: FloatArray) -> float:
    """Relative Absolute Error: ``sum|y - y_hat| / sum|y - mean(y)``.

    Normalises by the in-sample absolute deviation of the actuals, so it is
    scale-free. Zero denotes a perfect fit. Botchkarev notes the denominator
    degenerates for a series that is nearly constant.
    """
    actual, forecast = _as_pair(y_true, y_pred)
    denominator = float(np.sum(np.abs(actual - actual.mean())))
    if denominator == 0.0:
        raise ValueError("rae is undefined: y_true is constant, so the denominator is zero")
    return float(np.sum(np.abs(actual - forecast)) / denominator)


# ---------------------------------------------------------------------------
# Primary metrics -- percentage error (asymmetric, zero-unsafe)
# ---------------------------------------------------------------------------


def _require_nonzero_actuals(actual: FloatArray, name: str) -> None:
    """Reject zero actuals, which make a ratio-based percentage error undefined."""
    if np.any(actual == 0.0):
        zeros = int(np.count_nonzero(actual == 0.0))
        raise ValueError(
            f"{name} is undefined with {zeros} zero actual(s); use smape or mase instead"
        )


def mape(y_true: FloatArray, y_pred: FloatArray) -> float:
    """Mean Absolute Percentage Error: ``100 * mean(|(y - y_hat) / y|)``.

    Scale-free but asymmetric, and undefined when any actual is zero -- a real
    risk for PSAP volumes. Raises on zero actuals instead of returning
    infinity; use :func:`smape` or :func:`mase` when zeros are possible.
    """
    actual, forecast = _as_pair(y_true, y_pred)
    _require_nonzero_actuals(actual, "mape")
    return float(100.0 * np.mean(np.abs((actual - forecast) / actual)))


def mpe(y_true: FloatArray, y_pred: FloatArray) -> float:
    """Mean Percentage Error: ``100 * mean((y - y_hat) / y)``.

    Signed, so it measures directional bias rather than accuracy; shares
    MAPE's asymmetry and its undefinedness at zero.
    """
    actual, forecast = _as_pair(y_true, y_pred)
    _require_nonzero_actuals(actual, "mpe")
    return float(100.0 * np.mean((actual - forecast) / actual))


def smape(y_true: FloatArray, y_pred: FloatArray) -> float:
    """Symmetric MAPE: ``100 * mean(2|y - y_hat| / (|y| + |y_hat|))``.

    Bounded in [0, 200] and symmetric in actual and forecast, so it fixes
    MAPE's asymmetry. A pair that is jointly zero contributes 0 by
    convention rather than producing a 0/0. The M4 competition's preferred
    percentage measure, though Botchkarev rates MASE more stable still when
    comparing series of very different scale.
    """
    actual, forecast = _as_pair(y_true, y_pred)
    denominator = np.abs(actual) + np.abs(forecast)
    terms = np.divide(
        2.0 * np.abs(actual - forecast),
        denominator,
        out=np.zeros_like(denominator),
        where=denominator != 0.0,
    )
    return float(100.0 * np.mean(terms))


def md_ape(y_true: FloatArray, y_pred: FloatArray) -> float:
    """Median Absolute Percentage Error: ``100 * median(|(y - y_hat) / y|)``.

    Robust percentage error; raises on zero actuals as :func:`mape` does.
    """
    actual, forecast = _as_pair(y_true, y_pred)
    _require_nonzero_actuals(actual, "md_ape")
    return float(100.0 * np.median(np.abs((actual - forecast) / actual)))


# ---------------------------------------------------------------------------
# Composite metrics -- primary measure divided by an in-sample naive benchmark
# ---------------------------------------------------------------------------


def mase(
    y_true: FloatArray,
    y_pred: FloatArray,
    y_train: FloatArray,
    seasonality: int = 1,
) -> float:
    """Mean Absolute Scaled Error (Hyndman & Koehler 2006).

    ``mean(|y - y_hat|) / mean(|y_t - y_{t-m}|)`` with the denominator taken
    over the *in-sample* training series and ``m = seasonality``.

    Botchkarev classes MASE as a **composite** metric: it is MAE divided by
    an in-sample naive MAE. Being scale-free it is comparable across
    scenarios of different volume and noise, which is why it is the primary
    ranking measure for the scenario grid. ``MASE < 1`` means the forecast
    beats the in-sample naive benchmark on this series.

    ``seasonality=1`` gives the non-seasonal naive denominator; ``24`` is the
    appropriate choice for hourly call volume, matching the daily cycle.
    """
    actual, forecast = _as_pair(y_true, y_pred)
    denominator = _in_sample_naive_mae(y_train, seasonality)
    if denominator == 0.0:
        raise ValueError(
            "mase is undefined: the in-sample naive MAE is zero, so y_train has no "
            "variation at this seasonality"
        )
    return float(np.mean(np.abs(actual - forecast)) / denominator)


def rmsse(
    y_true: FloatArray,
    y_pred: FloatArray,
    y_train: FloatArray,
    seasonality: int = 1,
) -> float:
    """Root Mean Squared Scaled Error (Hyndman & Koehler 2006).

    ``rmse(y, y_hat) / rmse_of_in_sample_naive_differences``. The squared-error
    analogue of :func:`mase`, and likewise scale-free, but outlier-sensitive
    in the same way :func:`rmse` is. Used by the M5 competition.
    """
    actual, forecast = _as_pair(y_true, y_pred)
    denominator = in_sample_naive_rmse(y_train, seasonality)
    if denominator == 0.0:
        raise ValueError(
            "rmsse is undefined: the in-sample naive RMSE is zero, so y_train has no "
            "variation at this seasonality"
        )
    return float(np.sqrt(np.mean((actual - forecast) ** 2)) / denominator)


# ---------------------------------------------------------------------------
# Fit statistic (not an error measure)
# ---------------------------------------------------------------------------


def r_squared(y_true: FloatArray, y_pred: FloatArray) -> float:
    """Coefficient of determination: ``1 - SS_res / SS_tot``.

    **Higher is better**, and it is not an error measure: Botchkarev includes
    R² only as one term of a composite index, never as a standalone accuracy
    score. It is negative whenever the forecast is worse than simply
    predicting the training mean, and it rewards a forecast that chases the
    realised noise. Reported for goodness-of-fit only; do not rank on it alone
    and do not feed it to :func:`owa`, which needs a direction-consistent,
    per-observation loss.
    """
    actual, forecast = _as_pair(y_true, y_pred)
    ss_total = float(np.sum((actual - actual.mean()) ** 2))
    if ss_total == 0.0:
        raise ValueError("r_squared is undefined: y_true is constant")
    return float(1.0 - np.sum((actual - forecast) ** 2) / ss_total)


# ---------------------------------------------------------------------------
# Hybrid set -- report many measures, do not collapse to one
# ---------------------------------------------------------------------------


def score_forecast(
    y_true: FloatArray,
    y_pred: FloatArray,
    y_train: FloatArray,
    seasonality: int = 1,
    *,
    include_mape: bool = False,
) -> PointMeasures:
    """Score one forecast arm across the taxonomy, as a hybrid set.

    Returns every measure at once so a ranking can be audited against the raw
    grid -- Botchkarev's argument for hybrid sets over a single composite.
    The scale-free members (:attr:`mase`, :attr:`rmsse`) are what make the
    result comparable across scenarios; :attr:`mae`, :attr:`rmse` and
    :attr:`mse` are only meaningful within a single scenario.

    :attr:`mape` is ``None`` unless *include_mape* is set, because it raises
    on zero actuals and PSAP volumes can be zero. Pass ``include_mape=True``
    only for series known to have no zero actuals.

    ``y_train`` is the in-sample series the scaled measures divide by; it must
    be the training window, not the evaluation window.
    """
    actual, forecast = _as_pair(y_true, y_pred)
    mape_value = mape(actual, forecast) if include_mape else None
    return PointMeasures(
        mae=mae(actual, forecast),
        mse=mse(actual, forecast),
        rmse=rmse(actual, forecast),
        mape=mape_value,
        smape=smape(actual, forecast),
        mase=mase(actual, forecast, y_train, seasonality),
        rmsse=rmsse(actual, forecast, y_train, seasonality),
        r_squared=r_squared(actual, forecast),
        me=me(actual, forecast),
    )


MEASURES: dict[str, Callable[..., float]] = {
    "mae": mae,
    "mse": mse,
    "rmse": rmse,
    "smape": smape,
    "mase": mase,
    "rmsse": rmsse,
    "r_squared": r_squared,
}
"""Registry of single-argument-callable measures, for name-driven reporting."""