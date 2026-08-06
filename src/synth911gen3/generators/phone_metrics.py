from __future__ import annotations

from datetime import datetime, time

import numpy as np
import pandas as pd

from synth911gen3.config import GenerationRequest
from synth911gen3.logging_conf import get_logger
from synth911gen3.realism_config import RealismConfig

logger = get_logger("phone_metrics")


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

        pm = realism.phone_metrics
        base_hourly_volume = max(pm["min_hourly_volume"], request.rows / len(hours))
        average_weight = float(np.mean(realism.hourly_weights))

        records: list[dict[str, int | datetime]] = []
        for hour_start in hours:
            weight_multiplier = float(realism.hourly_weights[hour_start.hour] / average_weight)
            weekend_multiplier = pm["weekend_multiplier"] if hour_start.weekday() in (4, 5) else 1.0
            busy_factor = weight_multiplier * weekend_multiplier

            nine_one_one_calls_received = int(
                rng.poisson(max(1.0, base_hourly_volume * pm["nine_one_one_received_fraction"] * busy_factor))
            )
            non_emergency_calls_received = int(
                rng.poisson(max(1.0, base_hourly_volume * pm["non_emergency_received_fraction"] * busy_factor))
            )
            outbound_calls_placed = int(
                rng.poisson(max(0.5, base_hourly_volume * pm["outbound_calls_fraction"] * busy_factor))
            )

            abandonment_rate = pm["nine_one_one_abandonment_rate"] + (
                pm["night_abandonment_increment"] if 0 <= hour_start.hour <= 5 else 0.0
            )
            nine_one_one_calls_abandoned = int(
                rng.binomial(nine_one_one_calls_received, min(abandonment_rate, pm["max_abandonment_rate"]))
            )
            non_emergency_calls_abandoned = int(
                rng.binomial(non_emergency_calls_received, pm["non_emergency_abandonment_rate"])
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