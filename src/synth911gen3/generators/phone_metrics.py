"""Hourly call-center phone metrics generation.

:class:`HourlyCallCountGenerator` simulates one row per hour of the
requested date range with received/abandoned/answered counts for each
emergency line plus the non-emergency and outbound lines. Volumes follow
the diurnal ``hourly_weights`` (scaled so the run's total volume matches
``request.rows`` or, when *population* is set, the population-derived
call rate), weekend multipliers, per-line fractions and abandonment
rates, and load-sensitive lognormal answer-time service levels.
"""

from __future__ import annotations

from datetime import datetime, time

import numpy as np
import pandas as pd
from scipy.stats import lognorm

from synth911gen3.config import GenerationRequest
from synth911gen3.constants import NON_EMERGENCY_FLOOR_RATIO
from synth911gen3.constants import (
    PHONE_METRICS as DEFAULT_PHONE_METRICS,
)
from synth911gen3.emergency_numbers import EmergencyNumber, column_prefix
from synth911gen3.logging_conf import get_logger
from synth911gen3.realism_config import RealismConfig

logger = get_logger("phone_metrics")

_DEFAULT_THRESHOLDS = (10.0, 15.0, 20.0, 40.0)


def _thresholds(realism: RealismConfig) -> list[float]:
    """Answer-time thresholds (seconds) for the service-level percentage columns."""
    raw = realism.phone_metrics.get("answer_time_thresholds", list(_DEFAULT_THRESHOLDS))
    if isinstance(raw, list):
        return sorted(float(t) for t in raw)
    return [float(raw)]


def _mean_duration(
    rng: np.random.Generator,
    counts: np.ndarray,
    mu: float,
    sigma: float,
) -> np.ndarray:
    """Per-hour sample mean of ``counts`` lognormal phone-duration draws.

    Hours with zero calls yield ``0.0`` — no duration was observed. Hours with
    calls get the arithmetic mean of one lognormal draw per call, so the result
    is a consistent, noisy estimate of the population mean ``e^(mu + sigma^2/2)``.
    """
    total = int(counts.sum())
    if total == 0:
        return np.zeros(len(counts), dtype=float)
    draws = rng.lognormal(mu, sigma, size=total)
    draw_cum = np.concatenate(([0.0], np.cumsum(draws)))
    ends = np.cumsum(counts)
    starts = np.concatenate(([0], ends[:-1]))
    sums = draw_cum[ends] - draw_cum[starts]
    return np.where(counts > 0, sums / np.maximum(counts, 1), 0.0)


def phone_metrics_columns(request: GenerationRequest, realism: RealismConfig) -> list[str]:
    """Return the column names for the hourly phone-metrics dataset.

    Emergency-number columns are derived from the resolved registry (one set of
    received/abandoned/answered columns per number); the non-emergency line and
    the outbound counter are fixed.  Three aggregate total columns are appended.
    """
    thresholds = _thresholds(realism)
    columns = ["hour_start", "hour_of_day"]
    for number in request.resolved_emergency_numbers():
        prefix = column_prefix(number.number)
        columns.append(f"{prefix}_calls_received")
    columns.append("non_emergency_calls_received")
    columns.append("outbound_calls_placed")
    for number in request.resolved_emergency_numbers():
        prefix = column_prefix(number.number)
        columns.append(f"{prefix}_calls_abandoned")
    columns.append("non_emergency_calls_abandoned")
    for number in request.resolved_emergency_numbers():
        prefix = column_prefix(number.number)
        columns.extend(f"{prefix}_answered_{int(t)}s_pct" for t in thresholds)
    columns.extend(f"non_emergency_answered_{int(t)}s_pct" for t in thresholds)
    # Mean phone-duration columns (per emergency number, non-emergency, outbound,
    # and the volume-weighted overall mean).
    for number in request.resolved_emergency_numbers():
        prefix = column_prefix(number.number)
        columns.append(f"{prefix}_mean_duration")
    columns.append("non_emergency_mean_duration")
    columns.append("outbound_mean_duration")
    columns.append("call_mean_duration")
    # Aggregate totals
    columns.append("total_emergency_calls")
    columns.append("total_nonemergency_calls")
    columns.append("total_calls")
    return columns


class HourlyCallCountGenerator:
    """Hourly phone-metrics dataset generator (seeded, realism-aware)."""

    def generate(self, request: GenerationRequest) -> pd.DataFrame:
        """Generate hourly call counts for the request's date range."""
        request.validate()
        realism = request.get_realism_config()
        frame = self._generate_with_config(request, realism)
        logger.info("Hourly call counts generated: %d rows", len(frame))
        return frame

    def _generate_with_config(
        self, request: GenerationRequest, realism: RealismConfig
    ) -> pd.DataFrame:
        """Build the hourly frame from a resolved realism config (shared with previews)."""
        rng = np.random.default_rng(request.seed + 101)
        start_datetime = datetime.combine(request.resolved_start_date(), time.min)
        end_datetime = datetime.combine(request.resolved_end_date(), time(hour=23))
        hours = pd.date_range(start=start_datetime, end=end_datetime, freq="h")
        if hours.empty:
            return pd.DataFrame(columns=phone_metrics_columns(request, realism))

        pm = realism.phone_metrics
        line_overrides = realism.phone_metric_lines
        numbers: list[EmergencyNumber] = request.resolved_emergency_numbers()

        def _f(key: str, default: float | None = None) -> float:
            v = pm.get(key, default)
            if v is None:
                raise KeyError(f"Missing phone_metrics key: {key}")
            return float(v) if isinstance(v, (int, float)) else float(v[0])  # type: ignore[return-value]

        def _flist(key: str) -> list[float]:
            v = pm[key]
            return [float(x) for x in v] if isinstance(v, list) else [float(v)]  # type: ignore[return-value]

        rows = request.rows if request.rows is not None else request.resolved_rows()
        base_hourly_volume = max(_f("min_hourly_volume"), rows / len(hours))
        average_weight = float(np.mean(realism.hourly_weights))

        # Population-based volume scaling: when ``population`` is set on the
        # request, anchor the base volume to the tiered 911-only rate
        # (``population_rates.emergency_tiers``) instead of the incident row
        # count. The base is set so the *expected* 911 draw equals the
        # population-implied 911 volume; non-emergency and outbound lines
        # follow from the same base via their configured fractions.
        if request.population is not None:
            emergency_rate = realism.emergency_rate_for_population(request.population)
            emergency_annual = request.population / 1_000.0 * emergency_rate
            hours_in_year = 8_760.0
            emergency_fraction_total = sum(
                float(
                    line_overrides.get(num.number, {}).get(
                        "received_fraction", _f("nine_one_one_received_fraction")
                    )
                )
                for num in numbers
            ) or 1.0
            # Blend: use the population-derived 911 volume as the anchor,
            # distributed across hours via the diurnal weights.  The per-hour
            # draw is the anchor hourly rate divided by the emergency
            # fraction, then scaled by busy_factor.
            base_hourly_volume = max(
                _f("min_hourly_volume"),
                (emergency_annual / hours_in_year) / emergency_fraction_total,
            )

        hour_of_day = hours.to_series().dt.hour.to_numpy()
        weight_multiplier = realism.hourly_weights[hour_of_day] / average_weight
        weekend = np.where(
            np.isin(hours.to_series().dt.dayofweek.to_numpy(), (4, 5)),
            _f("weekend_multiplier"),
            1.0,
        )
        busy_factor = weight_multiplier * weekend

        def _line(num: EmergencyNumber) -> dict[str, float]:
            return line_overrides.get(num.number, {})

        # Received counts — one draw per emergency number first (keeps the
        # legacy single-911 random stream byte-identical), then the fixed lines.
        received: dict[str, np.ndarray] = {}
        default_emergency_fraction = _f("nine_one_one_received_fraction") / max(len(numbers), 1)
        for num in numbers:
            fraction = _line(num).get("received_fraction", default_emergency_fraction)
            received[num.number] = rng.poisson(
                np.maximum(1.0, base_hourly_volume * float(fraction) * busy_factor)
            )
        non_emergency_calls_received = rng.poisson(
            np.maximum(
                1.0, base_hourly_volume * _f("non_emergency_received_fraction") * busy_factor
            )
        )
        outbound_calls_placed = rng.poisson(
            np.maximum(0.5, base_hourly_volume * _f("outbound_calls_fraction") * busy_factor)
        )

        # Non-emergency floor: ensure non-emergency received calls are at
        # least ``non_emergency_floor_ratio`` × total emergency received calls
        # per hour. The national default (1.2) reflects the real-world pattern
        # that non-emergency volume usually exceeds emergency volume; urban
        # centers with a 911 share above ~45% (e.g. Kansas City's 51.5%)
        # override it to ~0.9 via realism config.
        floor_ratio = float(pm.get("non_emergency_floor_ratio", NON_EMERGENCY_FLOOR_RATIO))
        total_emergency_received = np.sum(
            [received[num.number] for num in numbers], axis=0
        )
        floor = np.ceil(total_emergency_received * floor_ratio).astype(int)
        non_emergency_calls_received = np.maximum(
            non_emergency_calls_received, floor
        )

        # Abandoned counts — same per-number then fixed-line draw order.
        abandoned: dict[str, np.ndarray] = {}
        for num in numbers:
            over = _line(num)
            rate = float(over.get("abandonment_rate", _f("nine_one_one_abandonment_rate")))
            night = float(
                over.get("night_abandonment_increment", _f("night_abandonment_increment"))
            )
            rate_array = rate + np.where((hour_of_day >= 0) & (hour_of_day <= 5), night, 0.0)
            abandoned[num.number] = rng.binomial(
                received[num.number],
                np.minimum(rate_array, _f("max_abandonment_rate")),
            )
        non_emergency_calls_abandoned = rng.binomial(
            non_emergency_calls_received, _f("non_emergency_abandonment_rate")
        )

        # Answer-time percentages — derived from the hour's actual call counts
        # so the service-level percentages stay consistent with the received /
        # abandoned volumes (e.g. 5 received calls only step in 20-point
        # increments, and 100% is achievable whenever every answered call is
        # fast). Each call answered during the hour gets a lognormal answer-time
        # draw and is binned against the thresholds via a sequential-binomial
        # allocation, so the counts are integers, non-decreasing in the
        # threshold, and bounded by the answered pool.
        thresholds = sorted(_flist("answer_time_thresholds"))
        load_sensitivity = _f("answer_time_load_sensitivity", 0.25)
        mu_noise_sd = _f("answer_time_mu_noise_sd", 0.05)

        def _answered_pct(
            received: np.ndarray,
            abandoned: np.ndarray,
            mean: float,
            sigma: float,
        ) -> dict[str, np.ndarray]:
            """Per-threshold % of calls answered within T seconds, per hour.

            ``mean`` is the population *mean answer time in seconds*; it is
            converted to lognormal log-scale location via
            ``mu = ln(mean) - sigma^2 / 2`` so the drawn distribution has the
            requested mean (matching the incident generator's
            :func:`_lognormal_seconds` convention).
            """
            answered = np.maximum(received - abandoned, 0)
            mu_log = np.log(max(mean, 1e-6)) - (sigma**2) / 2
            mu_adj = mu_log * (1.0 + load_sensitivity * (busy_factor - 1.0))
            mu_noise = rng.normal(0.0, mu_noise_sd, size=len(hours))
            scale = np.exp(mu_adj + mu_noise)
            probs = np.asarray([lognorm.cdf(t, s=sigma, scale=scale) for t in thresholds])

            cumulative = np.zeros(len(hours), dtype=np.int64)
            remaining = answered.copy()
            prev_p = np.zeros(len(hours))
            base = np.maximum(received, 1)
            pct: dict[str, np.ndarray] = {}
            for t, p in zip(thresholds, probs, strict=False):
                cond = np.clip(
                    (p - prev_p) / np.maximum(1.0 - prev_p, 1e-9), 0.0, 1.0
                )
                within = rng.binomial(remaining, cond)
                cumulative = cumulative + within
                remaining = remaining - within
                prev_p = p
                pct[f"answered_{int(t)}s"] = np.round(cumulative / base * 100.0, 1)
            return pct

        emergency_answered: dict[str, np.ndarray] = {}
        non_emergency_answered: dict[str, np.ndarray] = {}

        for num in numbers:
            over = _line(num)
            mean = float(over.get("answer_time_mean", _f("nine_one_one_answer_time_mean")))
            sigma = float(over.get("answer_time_sigma", _f("nine_one_one_answer_time_sigma")))
            prefix = column_prefix(num.number)
            for key, values in _answered_pct(
                received[num.number], abandoned[num.number], mean, sigma
            ).items():
                emergency_answered[f"{prefix}_{key}_pct"] = values

        ne_mean = _f("non_emergency_answer_time_mean")
        ne_sigma = _f("non_emergency_answer_time_sigma")
        for key, values in _answered_pct(
            non_emergency_calls_received, non_emergency_calls_abandoned, ne_mean, ne_sigma
        ).items():
            non_emergency_answered[f"non_emergency_{key}_pct"] = values

        # Mean phone duration per category — sample mean of the lognormal call
        # durations drawn per answered call (received minus abandoned; outbound
        # calls have no abandonment), plus a volume-weighted overall mean.
        def _duration_default(key: str) -> float:
            v = DEFAULT_PHONE_METRICS[key]
            return float(v) if isinstance(v, (int, float)) else float(v[0])  # type: ignore[return-value]

        duration_means: dict[str, np.ndarray] = {}
        duration_counts: dict[str, np.ndarray] = {}

        for num in numbers:
            over = _line(num)
            mu = float(
                over.get("phone_duration_mu", _f("nine_one_one_phone_duration_mu", _duration_default("nine_one_one_phone_duration_mu")))
            )
            sigma = float(
                over.get("phone_duration_sigma", _f("nine_one_one_phone_duration_sigma", _duration_default("nine_one_one_phone_duration_sigma")))
            )
            label = column_prefix(num.number)
            duration_counts[label] = np.maximum(received[num.number] - abandoned[num.number], 0)
            duration_means[label] = _mean_duration(rng, duration_counts[label], mu, sigma)

        duration_counts["non_emergency"] = np.maximum(
            non_emergency_calls_received - non_emergency_calls_abandoned, 0
        )
        duration_means["non_emergency"] = _mean_duration(
            rng,
            duration_counts["non_emergency"],
            _f("non_emergency_phone_duration_mu", _duration_default("non_emergency_phone_duration_mu")),
            _f("non_emergency_phone_duration_sigma", _duration_default("non_emergency_phone_duration_sigma")),
        )
        duration_counts["outbound"] = outbound_calls_placed
        duration_means["outbound"] = _mean_duration(
            rng,
            duration_counts["outbound"],
            _f("outbound_phone_duration_mu", _duration_default("outbound_phone_duration_mu")),
            _f("outbound_phone_duration_sigma", _duration_default("outbound_phone_duration_sigma")),
        )

        weighted_sum = np.zeros(len(hours))
        total_duration_calls = np.zeros(len(hours))
        for label, counts in duration_counts.items():
            weighted_sum += duration_means[label] * counts
            total_duration_calls += counts
        duration_means["call_mean_duration"] = np.where(
            total_duration_calls > 0,
            weighted_sum / np.maximum(total_duration_calls, 1),
            0.0,
        )

        data: dict[str, object] = {
            "hour_start": hours.to_numpy(),
            "hour_of_day": hour_of_day,
        }
        for num in numbers:
            data[f"{column_prefix(num.number)}_calls_received"] = received[num.number]
        data["non_emergency_calls_received"] = non_emergency_calls_received
        data["outbound_calls_placed"] = outbound_calls_placed
        for num in numbers:
            data[f"{column_prefix(num.number)}_calls_abandoned"] = abandoned[num.number]
        data["non_emergency_calls_abandoned"] = non_emergency_calls_abandoned
        data.update(emergency_answered)
        data.update(non_emergency_answered)
        for num in numbers:
            data[f"{column_prefix(num.number)}_mean_duration"] = duration_means[
                column_prefix(num.number)
            ]
        data["non_emergency_mean_duration"] = duration_means["non_emergency"]
        data["outbound_mean_duration"] = duration_means["outbound"]
        data["call_mean_duration"] = duration_means["call_mean_duration"]

        # Aggregate totals per hourly row
        total_emergency = np.sum(
            [received[num.number] for num in numbers], axis=0
        )
        total_nonemergency = non_emergency_calls_received
        data["total_emergency_calls"] = total_emergency
        data["total_nonemergency_calls"] = total_nonemergency
        data["total_calls"] = total_emergency + total_nonemergency + outbound_calls_placed

        return pd.DataFrame(data)
