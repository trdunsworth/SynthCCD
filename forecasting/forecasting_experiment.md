# Forecasting Model Challenge: Proprietary vs. Linear

## Hypothesis

H0 (null): A proprietary forecasting model's 168 hourly point forecasts do
not produce lower forecast error than a simple linear (trend) forecast over
the same horizon.

H1 (alternative): The proprietary model has materially lower error
(RMSE / MAPE / MAE) on the same volumes.

Current belief: linear forecasting is at least as accurate — the proprietary
model's complexity does not pay off.

## Setup

- **Workload:** synthetic call volumes from the SynthCCD volume generator,
  parameterized by population and staffing, with diurnal and weekly
  patterns. Use at least 4–8 weeks of hourly volumes per scenario.
- **Forecast horizon:** 168 hourly points (7 days).
- **Scenario grid:** varies on volume level, noise level (SCV of arrivals),
  and trend strength (flat, ramping, seasonal drift). Recommend ≥ 3 levels
  per factor → ≥ 27 scenarios, fixed seeds.

## Procedure

1. Generate training history (e.g., 4 weeks, hourly) per scenario.
2. Fit/derive the 168-point proprietary-model forecast
   (`proprietary_forecast.py`) — treat its algorithm as a black box that
   returns a list of 168 hourly values.
3. Fit a linear forecast over the same training window
   (`linear_forecast.py`): `y_hat(t) = a + b*t` on hours; optionally a
   day-of-week/hour seasonal-naive baseline as a third arm.
4. Score both against the realized next 168 hours: RMSE, MAE, MAPE, and
   coverage of prediction intervals if available.
5. Record per-hour-of-day and per-day-of-week error breakdowns.

## Statistics

- Per scenario, paired comparison of squared errors (proprietary vs
  linear): Wilcoxon signed-rank on hourly errors, plus mean RMSE ratio with
  bootstrap CIs across seeds.
- Effect size and equivalence margin: declare "no practical difference"
  when the RMSE ratio lies within, say, ±5%.

## Staffing impact

- Translate each forecast into recommended hourly staffing (via the
  staff_models runner, e.g., PSA/Erlang A staffing from the forecast).
- Measure the cost of acting on each forecast: over/under-staffing hours,
  SL shortfalls vs realized volume. This is the decision-theoretic
  justification for accuracy — a forecast only needs to be accurate where
  it changes staffing.

## Model matrix

Combine each forecasting arm with each queuing/staffing arm. Forecasting arms:

1. **Linear baseline** — `y_hat(t) = a + b*t` over the training window.
2. **statsforecast** (nixtlaverse) — e.g., AutoETS, AutoARIMA, AutoTheta,
   Holt-Winters, MSTL-based decompositions.
3. **mlforecast** (nixtlaverse) — gradient-boosting/lightgbm with calendar
   features.
4. **neuralforecast** (nixtlaverse) — neural architectures (NHITS/TFT/NBEATS)
   where dependencies allow (Linux; ray-dependent).
5. **timecopilot** (nixtlaverse) — LLM/agentic forecasting flows; treat its
   outputs as a candidate forecast arm.
6. **Proprietary black box** — wrapper around the company's model.
7. **Seasonal-naive** — last 168-hour window, as a sanity floor.

Staffing arms: Erlang C, Erlang A, and a hybrid arm that applies C when
utilization is moderate and A once utilization exceeds a threshold
(captures C's stability-requirement conflict), scored via PSA over the
168-hour profile.

## Conformal predictive strategy

Note as a *separate* forecast treatment layered on any of the above point
forecasts: **conformal prediction intervals** following Manokhin's work
(MAPIE; also exposed through nixtlaverse's statsforecast conformal
utilities). For each forecasting arm, produce prediction intervals with
distribution-free coverage guarantees and score interval calibration
(PICP/interval width) in addition to point-error metrics. For staffing,
this translates directly into using the upper prediction bound as the input
to the Erlang-C/A/PSA sizing — a conservative staffing policy that
controls for forecast uncertainty.

## Scoring matrix

Two metric families, every (forecast arm × staffing arm × scenario) cell:

1. **Botchkarev taxonomy (B.)**: accuracy-oriented error measures —
   RMSE, MAE, MAPE, MASE, plus symmetric variants; scale-free (MAPE/
   SMAPE/MASE) for cross-volume comparison.
2. **Classic fit**: R² (coefficient of determination) per scenario. R² is
   **not** an error measure — it is a ratio of aggregate sums, may be
   negative (worse than predicting the mean), and cannot be normalized per
   observation. It is reported for goodness-of-fit only and is **excluded
   from OWA**; do not rank on it alone.
3. **Sekitani & Murakami overall weighted average (OWA)**: the M4
   competition's ranking criterion, as implemented in `forecasting/score.py`
   (`owa()`, `seasonal_naive()`). Definition per Makridakis, Spiliotis &
   Assimakopoulos (2020), *IJF* 36(1) 54–74, following Sekitani & Murakami
   (2008):

   ```
   OWA = 0.5 * ( MASE(model) / MASE(Naive-2) + sMAPE(model) / sMAPE(Naive-2) )
   ```

   Each loss is normalized by the same loss of the **Naive-2 benchmark**
   before the two are averaged with equal weight. Lower is better, and the
   benchmark itself scores exactly `1.0`, so the number reads directly as a
   fraction of the benchmark's error: `0.9` means 10% more accurate than
   Naive-2. Naive-2 is a random walk on the **seasonally adjusted** series,
   fit on the training window only and never on the evaluation window.

   Two implementation constraints, both load-bearing:
   - **Aggregate-then-ratio**, never ratio-then-aggregate. Compute each loss
     over the whole 168-hour horizon first, *then* divide. Dividing per step
     and averaging the ratios explodes when the benchmark happens to be exact
     at one step.
   - **Seasonality `m`**: M4 used `m=24` for hourly data, which is the right
     choice for this 168-hour horizon. A multiplicative seasonal index (as in
     the original M4 R code) is undefined when volume is zero, so the
     implementation uses additive adjustment, matching sktime's reference
     implementation.

   This corrects an earlier draft of this document that proposed averaging
   RMSE, MAPE and R² with a priori weights. That is not the authors'
   construction: it aggregates *incommensurable* quantities (RMSE is
   scale-dependent, R² is not an error), and R² cannot participate at all.
   OWA normalizes first, which is what makes the average meaningful.

   The raw metric grid is reported alongside the OWA so the aggregation stays
   auditable — a single scalar that hides its inputs is exactly what
   Botchkarev's hybrid-set argument warns against.

Supporting analyses: paired Wilcoxon signed-rank on hourly errors vs the
linear arm, bootstrap CIs on RMSE ratios, per-hour-of-day error profiles,
interval-calibration (PICP), and the staffing-impact cost table.

## Deliverables

- `forecasting/linear_forecast.py` — baseline implementation.
- `forecasting/proprietary_forecast.py` — wrapper importing the company's
  model (to be supplied).
- `forecasting/score.py` — metrics, Botchkarev-family errors, R²,
  Sekitani–Murakami weighted aggregation, Wilcoxon/bootstrap stats.
- `forecasting/conformal.py` — conformal interval layer (Manokhin-style)
  applied over point forecasts.
- `forecasting/run_experiment.py` — orchestrates scenario grid, writes
  results to `output/forecasting/`.
- Report in markdown + Carve with the verdict and per-scenario charts.

## Installed dependencies

Added to `pyproject.toml` (lockfile regeneration pending — move to the
Linux environment, where the ray/numba wheels resolve):

- `statsforecast`, `mlforecast`, `numba`, `llvmlite` (nixtlaverse core)
- `timecopilot`, `neuralforecast` (LLM/agentic + neural arms, Linux path)

## Viability notes

- Synthetic volumes make ground truth known, so "accuracy" is well-defined;
  risk is overfitting conclusions to synthetic noise structure — keep a
  pure-noise scenario (no pattern) to demonstrate linear's expected parity.
- The 168-point horizon matches one scheduling week, so staffing deltas
  will be interpretable to operations reviewers.
- For strict SLAs, treat the conformal upper bound as the staffing input
  rather than the point forecast; this is the decision-theoretically honest
  policy under arrival-rate uncertainty (consistent with the Robbins
  critique findings).

## Migration note (macOS → Linux)

On this machine (macOS, x86_64, Python 3.12), `numba`/`llvmlite` have no
compatible wheels — `llvmlite 0.44.x` is the last x86_64 macOS build and the
newer releases uv resolves only ship arm64 macOS wheels. The new forecasting
dependencies in `pyproject.toml` were therefore added with `--frozen` and
`uv.lock` is **intentionally stale**.

Before running anything in the Linux environment:

1. `UV_SYSTEM_CERTS=true uv lock` — regenerate the lockfile (ray-dependent
   `neuralforecast`/`timecopilot`/`darts` resolve there).
2. `UV_SYSTEM_CERTS=true uv sync` — install the full set.
3. Re-run `uv run pytest tests/ && uv run ruff check . && uv run ty check`
   before trusting any generated volumes.

Until then, only `statsforecast`-free arms of the experiment can run locally.
