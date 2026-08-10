from __future__ import annotations

from datetime import datetime, time

import numpy as np
import pandas as pd
from scipy.stats import lognorm

from synth911gen3.config import GenerationRequest
from synth911gen3.emergency_numbers import EmergencyNumber, column_prefix
from synth911gen3.logging_conf import get_logger
from synth911gen3.realism_config import RealismConfig

logger = get_logger("phone_metrics")

_DEFAULT_THRESHOLDS = (10.0, 15.0, 20.0, 40.0)


def _thresholds(realism: RealismConfig) -> list[float]:
    raw = realism.phone_metrics.get("answer_time_thresholds", list(_DEFAULT_THRESHOLDS))
    if isinstance(raw, list):
        return [float(t) for t in raw]
    return [float(raw)]


def phone_metrics_columns(request: GenerationRequest, realism: RealismConfig) -> list[str]:
    """Return the column names for the hourly phone-metrics dataset.

    Emergency-number columns are derived from the resolved registry (one set of
    received/abandoned/answered columns per number); the non-emergency line and
    the outbound counter are fixed.
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
    return columns


class HourlyCallCountGenerator:
    def generate(self, request: GenerationRequest) -> pd.DataFrame:
        request.validate()
        realism = request.get_realism_config()
        frame = self._generate_with_config(request, realism)
        logger.info("Hourly call counts generated: %d rows", len(frame))
        return frame

    def _generate_with_config(
        self, request: GenerationRequest, realism: RealismConfig
    ) -> pd.DataFrame:
        rng = np.random.default_rng(request.seed + 101)
        start_datetime = datetime.combine(request.resolved_start_date(), time.min)
        end_datetime = datetime.combine(request.resolved_end_date(), time(hour=23))
        hours = pd.date_range(start=start_datetime, end=end_datetime, freq="h")
        if hours.empty:
            return pd.DataFrame(columns=phone_metrics_columns(request, realism))

        pm = realism.phone_metrics
        line_overrides = realism.phone_metric_lines
        numbers: list[EmergencyNumber] = request.resolved_emergency_numbers()

        def _f(key: str) -> float:
            v = pm[key]
            return float(v) if isinstance(v, (int, float)) else float(v[0])  # type: ignore[return-value]

        def _flist(key: str) -> list[float]:
            v = pm[key]
            return [float(x) for x in v] if isinstance(v, list) else [float(v)]  # type: ignore[return-value]

        base_hourly_volume = max(_f("min_hourly_volume"), request.rows / len(hours))
        average_weight = float(np.mean(realism.hourly_weights))

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
            np.maximum(1.0, base_hourly_volume * _f("non_emergency_received_fraction") * busy_factor)
        )
        outbound_calls_placed = rng.poisson(
            np.maximum(0.5, base_hourly_volume * _f("outbound_calls_fraction") * busy_factor)
        )

        # Abandoned counts — same per-number then fixed-line draw order.
        abandoned: dict[str, np.ndarray] = {}
        for num in numbers:
            over = _line(num)
            rate = float(over.get("abandonment_rate", _f("nine_one_one_abandonment_rate")))
            night = float(over.get("night_abandonment_increment", _f("night_abandonment_increment")))
            rate_array = rate + np.where(
                (hour_of_day >= 0) & (hour_of_day <= 5), night, 0.0
            )
            abandoned[num.number] = rng.binomial(
                received[num.number],
                np.minimum(rate_array, _f("max_abandonment_rate")),
            )
        non_emergency_calls_abandoned = rng.binomial(
            non_emergency_calls_received, _f("non_emergency_abandonment_rate")
        )

        # Answer-time percentages (deterministic — no RNG draws).
        thresholds = _flist("answer_time_thresholds")
        emergency_answered: dict[str, float] = {}
        non_emergency_answered: dict[str, float] = {}
        for num in numbers:
            over = _line(num)
            mu = float(over.get("answer_time_mu", _f("nine_one_one_answer_time_mu")))
            sigma = float(over.get("answer_time_sigma", _f("nine_one_one_answer_time_sigma")))
            prefix = column_prefix(num.number)
            for threshold in thresholds:
                t = int(threshold)
                p = lognorm.cdf(threshold, s=sigma, scale=np.exp(mu))
                emergency_answered[f"{prefix}_answered_{t}s_pct"] = np.round(p * 100, 1)
        for threshold in thresholds:
            t = int(threshold)
            p = lognorm.cdf(
                threshold,
                s=_f("non_emergency_answer_time_sigma"),
                scale=np.exp(_f("non_emergency_answer_time_mu")),
            )
            non_emergency_answered[f"non_emergency_answered_{t}s_pct"] = np.round(p * 100, 1)

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

        return pd.DataFrame(data)
