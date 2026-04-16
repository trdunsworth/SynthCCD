from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta

import numpy as np
import pandas as pd
from faker import Faker

from synth911gen3.addresses import AddressProvider
from synth911gen3.config import GenerationRequest
from synth911gen3.constants import (
    AGENCY_WEIGHTS,
    CALL_RECEPTION_WEIGHTS,
    DEFAULT_LOCALE,
    DISPOSITION_PROFILES,
    HOURLY_WEIGHTS,
    PRIORITY_WEIGHTS,
    PROBLEM_PROFILES,
    TIME_PROFILES,
)


def _weighted_choice(rng: np.random.Generator, weights_by_value: dict[str, float]) -> str:
    values = list(weights_by_value)
    probabilities = list(weights_by_value.values())
    return str(rng.choice(values, p=probabilities))


def _weighted_choice_from_pairs(
    rng: np.random.Generator, weighted_pairs: list[tuple[str, float]]
) -> str:
    values = [item for item, _ in weighted_pairs]
    probabilities = [weight for _, weight in weighted_pairs]
    return str(rng.choice(values, p=probabilities))


def _weighted_priority(rng: np.random.Generator, agency: str) -> int:
    weights_by_priority = PRIORITY_WEIGHTS[agency]
    priorities = list(weights_by_priority)
    probabilities = list(weights_by_priority.values())
    return int(rng.choice(priorities, p=probabilities))


def _sample_lognormal_seconds(
    rng: np.random.Generator,
    mean_seconds: int,
    sigma: float = 0.55,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    mu = np.log(max(mean_seconds, 1)) - (sigma**2) / 2
    value = int(rng.lognormal(mu, sigma))
    if maximum is not None:
        value = min(value, maximum)
    return max(minimum, value)


def _generate_event_times(request: GenerationRequest, rng: np.random.Generator) -> list[datetime]:
    start_datetime = datetime.combine(request.resolved_start_date(), time.min)
    total_days = (request.resolved_end_date() - request.resolved_start_date()).days + 1
    day_offsets = rng.integers(0, max(total_days, 1), size=request.rows)
    hours = rng.choice(np.arange(24), size=request.rows, p=HOURLY_WEIGHTS)
    minute_offsets = rng.integers(0, 60, size=request.rows)
    second_offsets = rng.integers(0, 60, size=request.rows)

    event_times = [
        start_datetime
        + timedelta(days=int(day_offsets[index]))
        + timedelta(hours=int(hours[index]))
        + timedelta(minutes=int(minute_offsets[index]))
        + timedelta(seconds=int(second_offsets[index]))
        for index in range(request.rows)
    ]
    event_times.sort()
    return event_times


def _build_personnel_pool(faker: Faker, size: int) -> list[str]:
    faker.unique.clear()
    return [faker.unique.name() for _ in range(size)]


class IncidentGenerator:
    def __init__(self, address_provider: AddressProvider, faker_locale: str = DEFAULT_LOCALE) -> None:
        self._address_provider = address_provider
        self._faker_locale = faker_locale

    def generate(self, request: GenerationRequest) -> pd.DataFrame:
        request.validate()
        rng = np.random.default_rng(request.seed)
        faker = Faker(self._faker_locale)
        faker.seed_instance(request.seed)

        calltakers = _build_personnel_pool(faker, request.calltaker_pool_size)
        dispatchers = _build_personnel_pool(faker, request.dispatcher_pool_size)
        addresses = self._address_provider.load_addresses(request.area_query)
        event_times = _generate_event_times(request, rng)
        reference_counters: defaultdict[str, int] = defaultdict(int)

        records: list[dict[str, object]] = []
        for incident_index, call_start_time in enumerate(event_times, start=1):
            agency = _weighted_choice(rng, AGENCY_WEIGHTS)
            priority = _weighted_priority(rng, agency)
            profile = TIME_PROFILES[agency][priority]
            address = addresses[int(rng.integers(0, len(addresses)))]
            reference_counters[agency] += 1

            pickup_delay_seconds = _sample_lognormal_seconds(rng, 3, sigma=0.45, maximum=20)
            interview_seconds = _sample_lognormal_seconds(
                rng,
                profile["interview_mean"],
                sigma=0.65,
                maximum=1_800,
            )
            dispatch_queue_seconds = _sample_lognormal_seconds(
                rng,
                profile["dispatch_mean"],
                sigma=0.85,
                maximum=7_200,
            )
            turnout_seconds = _sample_lognormal_seconds(
                rng,
                profile["turnout_mean"],
                sigma=0.60,
                maximum=900,
            )
            travel_seconds = _sample_lognormal_seconds(
                rng,
                profile["travel_mean"],
                sigma=0.55,
                maximum=3_600,
            )
            on_scene_seconds = _sample_lognormal_seconds(
                rng,
                profile["scene_mean"],
                sigma=0.50,
                maximum=10_800,
            )
            closeout_seconds = _sample_lognormal_seconds(
                rng,
                profile["closeout_mean"],
                sigma=0.45,
                maximum=1_800,
            )
            phone_duration_seconds = max(
                interview_seconds + dispatch_queue_seconds,
                _sample_lognormal_seconds(
                    rng,
                    profile["phone_mean"],
                    sigma=0.70,
                    maximum=3_600,
                ),
            )

            time_phone_pickup = call_start_time + timedelta(seconds=pickup_delay_seconds)
            time_call_enters_queue = time_phone_pickup + timedelta(seconds=interview_seconds)
            time_first_unit_assigned = time_call_enters_queue + timedelta(
                seconds=dispatch_queue_seconds
            )
            time_unit_enroute = time_first_unit_assigned + timedelta(seconds=turnout_seconds)
            time_unit_arrived = time_unit_enroute + timedelta(seconds=travel_seconds)
            time_last_unit_cleared = time_unit_arrived + timedelta(seconds=on_scene_seconds)
            time_call_closed = time_last_unit_cleared + timedelta(seconds=closeout_seconds)
            time_phone_disconnect = time_phone_pickup + timedelta(seconds=phone_duration_seconds)
            total_elapsed_seconds = int((time_call_closed - call_start_time).total_seconds())

            records.append(
                {
                    "id_number": incident_index,
                    "internal_reference_number": (
                        f"{agency}-{call_start_time:%y%m%d}-{reference_counters[agency]:06d}"
                    ),
                    "agency": agency,
                    "problem_nature": _weighted_choice_from_pairs(rng, PROBLEM_PROFILES[agency]),
                    "priority": priority,
                    "street_address": address.street_address,
                    "city": address.city,
                    "state": address.state,
                    "location": address.location,
                    "call_start_time": call_start_time,
                    "time_phone_pickup": time_phone_pickup,
                    "time_call_enters_queue": time_call_enters_queue,
                    "time_first_unit_assigned": time_first_unit_assigned,
                    "time_unit_enroute": time_unit_enroute,
                    "time_unit_arrived": time_unit_arrived,
                    "time_last_unit_cleared": time_last_unit_cleared,
                    "time_call_closed": time_call_closed,
                    "time_phone_disconnect": time_phone_disconnect,
                    "calltaker": str(rng.choice(calltakers)),
                    "dispatcher": str(rng.choice(dispatchers)),
                    "method_of_call_reception": _weighted_choice(rng, CALL_RECEPTION_WEIGHTS),
                    "call_disposition": _weighted_choice_from_pairs(
                        rng, DISPOSITION_PROFILES[agency]
                    ),
                    "pickup_delay_seconds": pickup_delay_seconds,
                    "interview_seconds": interview_seconds,
                    "dispatch_queue_seconds": dispatch_queue_seconds,
                    "turnout_seconds": turnout_seconds,
                    "travel_seconds": travel_seconds,
                    "on_scene_seconds": on_scene_seconds,
                    "closeout_seconds": closeout_seconds,
                    "phone_duration_seconds": phone_duration_seconds,
                    "total_elapsed_seconds": total_elapsed_seconds,
                }
            )

        return pd.DataFrame.from_records(records)
