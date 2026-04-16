from __future__ import annotations

from datetime import datetime, time

import numpy as np
import pandas as pd

from synth911gen3.config import GenerationRequest
from synth911gen3.constants import HOURLY_WEIGHTS


class HourlyCallCountGenerator:
    def generate(self, request: GenerationRequest) -> pd.DataFrame:
        request.validate()
        rng = np.random.default_rng(request.seed + 101)
        start_datetime = datetime.combine(request.resolved_start_date(), time.min)
        end_datetime = datetime.combine(request.resolved_end_date(), time(hour=23))
        hours = pd.date_range(start=start_datetime, end=end_datetime, freq="h")
        if hours.empty:
            return pd.DataFrame(
                columns=[
                    "hour_start",
                    "hour_of_day",
                    "nine_one_one_calls_received",
                    "nine_one_one_calls_abandoned",
                    "non_emergency_calls_received",
                    "non_emergency_calls_abandoned",
                    "outbound_calls_placed",
                ]
            )

        base_hourly_volume = max(2.0, request.rows / len(hours))
        average_weight = float(np.mean(HOURLY_WEIGHTS))

        records: list[dict[str, int | datetime]] = []
        for hour_start in hours:
            weight_multiplier = float(HOURLY_WEIGHTS[hour_start.hour] / average_weight)
            weekend_multiplier = 1.12 if hour_start.weekday() in (4, 5) else 1.0
            busy_factor = weight_multiplier * weekend_multiplier

            nine_one_one_calls_received = int(
                rng.poisson(max(1.0, base_hourly_volume * 0.48 * busy_factor))
            )
            non_emergency_calls_received = int(
                rng.poisson(max(1.0, base_hourly_volume * 0.58 * busy_factor))
            )
            outbound_calls_placed = int(
                rng.poisson(max(0.5, base_hourly_volume * 0.26 * busy_factor))
            )

            abandonment_rate = 0.02 + (0.03 if 0 <= hour_start.hour <= 5 else 0.0)
            nine_one_one_calls_abandoned = int(
                rng.binomial(nine_one_one_calls_received, min(abandonment_rate, 0.12))
            )
            non_emergency_calls_abandoned = int(
                rng.binomial(non_emergency_calls_received, 0.05)
            )

            records.append(
                {
                    "hour_start": hour_start.to_pydatetime(),
                    "hour_of_day": int(hour_start.hour),
                    "nine_one_one_calls_received": nine_one_one_calls_received,
                    "nine_one_one_calls_abandoned": nine_one_one_calls_abandoned,
                    "non_emergency_calls_received": non_emergency_calls_received,
                    "non_emergency_calls_abandoned": non_emergency_calls_abandoned,
                    "outbound_calls_placed": outbound_calls_placed,
                }
            )

        return pd.DataFrame.from_records(records)
