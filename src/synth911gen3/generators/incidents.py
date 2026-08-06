from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, time, timedelta

import numpy as np
import pandas as pd
from faker import Faker

from synth911gen3.addresses import AddressProvider
from synth911gen3.config import GenerationRequest, IdFormat
from synth911gen3.constants import DEFAULT_LOCALE
from synth911gen3.logging_conf import ProgressReporter, get_logger
from synth911gen3.realism_config import RealismConfig

_DAY_ABBREVIATIONS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")

logger = get_logger("incidents")


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


def _weighted_priority(rng: np.random.Generator, agency: str, realism: RealismConfig) -> int:
    weights_by_priority = realism.priority_weights[agency]
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


def _generate_event_times(request: GenerationRequest, rng: np.random.Generator, realism: RealismConfig) -> list[datetime]:
    start_datetime = datetime.combine(request.resolved_start_date(), time.min)
    total_days = (request.resolved_end_date() - request.resolved_start_date()).days + 1
    day_offsets = rng.integers(0, max(total_days, 1), size=request.rows)
    hours = rng.choice(np.arange(24), size=request.rows, p=realism.hourly_weights)
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

    def generate(
        self,
        request: GenerationRequest,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> pd.DataFrame:
        request.validate()
        realism = request.get_realism_config()
        rng = np.random.default_rng(request.seed)
        faker = Faker(self._faker_locale)
        faker.seed_instance(request.seed)

        calltakers = _build_personnel_pool(faker, request.calltaker_pool_size)
        dispatchers = _build_personnel_pool(faker, request.dispatcher_pool_size)
        logger.debug("Personnel pools built: %d calltakers, %d dispatchers", len(calltakers), len(dispatchers))
        logger.info("Loading addresses for '%s'...", request.area_query.strip())
        addresses = self._address_provider.load_addresses(request.area_query)
        logger.info("Loaded %d addresses for sampling", len(addresses))
        event_times = _generate_event_times(request, rng, realism)
        reference_counters: defaultdict[str, int] = defaultdict(int)

        progress = ProgressReporter(request.rows, logger)
        records: list[dict[str, object]] = []
        last_permille = -1
        for incident_index, call_start_time in enumerate(event_times, start=1):
            progress.update(incident_index)
            if on_progress is not None:
                permille = int(incident_index * 1000 / max(request.rows, 1))
                if permille != last_permille or incident_index == request.rows:
                    last_permille = permille
                    on_progress(incident_index, request.rows)
            agency = _weighted_choice(rng, realism.agency_weights)
            priority = _weighted_priority(rng, agency, realism)
            profile = realism.time_profiles[agency][priority]
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

            pre_cad_offset_seconds = int(rng.integers(0, 4))
            incident_start_time = call_start_time + timedelta(seconds=pre_cad_offset_seconds)
            time_phone_pickup = call_start_time + timedelta(seconds=pickup_delay_seconds)
            time_call_enters_queue = time_phone_pickup + timedelta(seconds=interview_seconds)

            dispatch_lo, dispatch_hi = realism.dispatch_init_fraction[priority]
            dispatch_fraction = float(rng.uniform(dispatch_lo, dispatch_hi))
            dispatch_init_seconds = int(phone_duration_seconds * dispatch_fraction)
            time_first_unit_assigned = time_phone_pickup + timedelta(
                seconds=dispatch_init_seconds + dispatch_queue_seconds
            )
            time_unit_enroute = time_first_unit_assigned + timedelta(seconds=turnout_seconds)
            time_unit_arrived = time_unit_enroute + timedelta(seconds=travel_seconds)
            time_last_unit_cleared = time_unit_arrived + timedelta(seconds=on_scene_seconds)
            time_call_closed = time_last_unit_cleared + timedelta(seconds=closeout_seconds)
            time_phone_disconnect = time_phone_pickup + timedelta(seconds=phone_duration_seconds)
            total_elapsed_seconds = int((time_call_closed - call_start_time).total_seconds())

            if request.id_format is IdFormat.GUID:
                id_number: int | str = str(faker.uuid4())
            else:
                id_number = incident_index

            records.append(
                {
                    "id_number": id_number,
                    "internal_reference_number": (
                        f"{agency}-{call_start_time:%y%m%d}-{reference_counters[agency]:06d}"
                    ),
                    "agency": agency,
                    "problem_nature": _weighted_choice_from_pairs(rng, realism.problem_profiles[agency][priority]),
                    "priority": priority,
                    "prefix_directional": address.prefix_directional,
                    "street_number": address.street_number,
                    "street_name": address.street_name,
                    "street_type": address.street_type,
                    "postfix_directional": address.postfix_directional,
                    "street_address": address.street_address,
                    "city": address.city,
                    "state": address.state,
                    "postal_code": address.postal_code,
                    "location": address.location,
                    "call_start_time": call_start_time,
                    "hour": call_start_time.hour,
                    "dow": _DAY_ABBREVIATIONS[call_start_time.weekday()],
                    "week_no": call_start_time.isocalendar().week,
                    "incident_start_time": incident_start_time,
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
                    "method_of_call_reception": _weighted_choice(rng, realism.call_reception_weights),
                    "call_disposition": _weighted_choice_from_pairs(
                        rng, realism.disposition_profiles[agency]
                    ),
                    "pickup_delay_seconds": pickup_delay_seconds,
                    "pre_cad_offset_seconds": pre_cad_offset_seconds,
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

        progress.finish()
        return pd.DataFrame.from_records(records)