from __future__ import annotations

import random as _random
import uuid as _uuid
from collections.abc import Callable, Iterator

import numpy as np
import pandas as pd
from faker import Faker

from synth911gen3.addresses import AddressProvider
from synth911gen3.config import GenerationRequest, IdFormat
from synth911gen3.constants import DEFAULT_LOCALE, DEFAULT_MAX_MEMORY_BYTES, MEMORY_PROBE_ROWS
from synth911gen3.exceptions import ValidationError
from synth911gen3.logging_conf import ProgressReporter, get_logger
from synth911gen3.realism_config import RealismConfig
from synth911gen3.shifts import ShiftConfig, apply_shift_preset

_DAY_ABBREVIATIONS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
_MINUTES_PER_DAY = 1440
_TIMING_FIELDS = (
    "interview_mean",
    "dispatch_mean",
    "turnout_mean",
    "travel_mean",
    "scene_mean",
    "closeout_mean",
    "phone_mean",
)
_ADDRESS_FIELDS = (
    "prefix_directional",
    "street_number",
    "street_name",
    "street_type",
    "postfix_directional",
    "street_address",
    "city",
    "state",
    "postal_code",
)

logger = get_logger("incidents")


def _weighted_choice_from_pairs(
    rng: np.random.Generator, weighted_pairs: list[tuple[str, float]]
) -> str:
    values = [item for item, _ in weighted_pairs]
    probabilities = [weight for _, weight in weighted_pairs]
    return str(rng.choice(values, p=probabilities))


def _distribute(amount: int, slots: int) -> list[int]:
    if slots <= 0:
        return []
    base, extra = divmod(max(amount, 1), slots)
    return [base + (1 if index < extra else 0) for index in range(slots)]


def _resolve_shift_staffing(
    shift_config: ShiftConfig, request: GenerationRequest
) -> list[tuple[str, int, int]]:
    """Per-shift (name, calltakers, dispatchers) staffing.

    Uses each shift's explicit staffing when present; shifts that omit staffing
    fall back to an even split of the request's global pool totals.
    """
    unnamed_ct = [shift for shift in shift_config.shifts if shift.calltakers is None]
    unnamed_dsp = [shift for shift in shift_config.shifts if shift.dispatchers is None]
    ct_split = _distribute(request.calltaker_pool_size, len(unnamed_ct))
    dsp_split = _distribute(request.dispatcher_pool_size, len(unnamed_dsp))
    ct_index = 0
    dsp_index = 0
    plan: list[tuple[str, int, int]] = []
    for shift in shift_config.shifts:
        calltakers = (
            shift.calltakers if shift.calltakers is not None else ct_split[ct_index]
        )
        if shift.calltakers is None:
            ct_index += 1
        dispatchers = (
            shift.dispatchers if shift.dispatchers is not None else dsp_split[dsp_index]
        )
        if shift.dispatchers is None:
            dsp_index += 1
        plan.append((shift.name, max(1, calltakers), max(1, dispatchers)))
    return plan


def _build_shift_pools(
    faker: Faker, staffing: list[tuple[str, int, int]]
) -> dict[str, dict[str, list[str]]]:
    faker.unique.clear()
    pools: dict[str, dict[str, list[str]]] = {}
    for name, calltakers, dispatchers in staffing:
        pools[name] = {
            "calltakers": [faker.unique.name() for _ in range(calltakers)],
            "dispatchers": [faker.unique.name() for _ in range(dispatchers)],
        }
    return pools


def _zipf_weights(count: int) -> np.ndarray:
    weights = np.array([1.0 / (index + 1) for index in range(count)])
    return weights / weights.sum()


def _zipf_pick(rng: np.random.Generator, names: list[str]) -> str:
    return str(rng.choice(np.asarray(names, dtype=object), p=_zipf_weights(len(names))))


def _zipf_choice(rng: np.random.Generator, names: list[str], size: int) -> np.ndarray:
    return rng.choice(
        np.asarray(names, dtype=object), size=size, p=_zipf_weights(len(names))
    )


def _categorical_choice(
    rng: np.random.Generator, values: list[str], weights: list[float], size: int
) -> np.ndarray:
    return rng.choice(
        np.asarray(values, dtype=object), size=size, p=np.asarray(weights, dtype=float)
    )


def _lognormal_seconds(
    rng: np.random.Generator,
    mean_seconds: float | np.ndarray,
    sigma: float,
    size: int,
    minimum: int = 0,
    maximum: int | None = None,
) -> np.ndarray:
    mu = np.log(np.maximum(np.asarray(mean_seconds, dtype=float), 1.0)) - (sigma**2) / 2
    values = rng.lognormal(mu, sigma, size=size)
    upper = maximum if maximum is not None else np.inf
    return np.clip(values, minimum, upper).astype(np.int64)


def _event_time_offsets(
    rng: np.random.Generator, request: GenerationRequest, realism: RealismConfig, n: int
) -> np.ndarray:
    """Vectorized call-start times as seconds since the start date."""
    total_days = (request.resolved_end_date() - request.resolved_start_date()).days + 1
    day_offsets = rng.integers(0, max(total_days, 1), size=n)
    hours = rng.choice(np.arange(24), size=n, p=realism.hourly_weights)
    minutes = rng.integers(0, 60, size=n)
    seconds = rng.integers(0, 60, size=n)
    return day_offsets * 86400 + hours * 3600 + minutes * 60 + seconds


def _active_shift_index(shift_config: ShiftConfig, event_times: np.ndarray) -> np.ndarray:
    """Vectorized active-shift resolution for a datetime64[s] array.

    Mirrors ``ShiftConfig.active_shift``: pick the covering shift in the day's
    rotation group with the most recently started on-duty block.
    """
    n = len(event_times)
    rotation = np.asarray(shift_config.rotation)
    days = event_times.astype("datetime64[D]").astype(np.int64)
    pairing = rotation[(days - shift_config.rotation_cycle_offset()) % len(rotation)]
    minutes = event_times.astype("datetime64[m]").astype(np.int64) % _MINUTES_PER_DAY

    best_score = np.full(n, np.inf)
    best_index = np.zeros(n, dtype=np.intp)
    for index, shift in enumerate(shift_config.shifts):
        start = shift.start_hour * 60 + shift.start_minute
        end = shift.end_hour * 60 + shift.end_minute
        if start < end:
            covers = (minutes >= start) & (minutes < end)
        else:
            covers = (minutes >= start) | (minutes < end)
        in_group = pairing == shift.rotation
        minutes_since = (minutes - start) % _MINUTES_PER_DAY
        score = np.where(in_group, minutes_since.astype(np.float64), np.inf)
        score = np.where(covers, score - 1e9, score)
        better = score < best_score
        best_index = np.where(better, index, best_index)
        best_score = np.where(better, score, best_score)
    return best_index


def _build_reference_numbers(
    agency: np.ndarray,
    agency_codes: np.ndarray,
    times_series: pd.Series,
    start_counts: np.ndarray | None = None,
) -> np.ndarray:
    ymd = (
        (times_series.dt.year % 100) * 10000
        + times_series.dt.month * 100
        + times_series.dt.day
    )
    ymd_str = np.char.zfill(ymd.to_numpy().astype("U6"), 6)

    counters = np.zeros(int(agency_codes.max()) + 1, dtype=np.int64)
    if start_counts is not None:
        counters = np.zeros(len(start_counts), dtype=np.int64)
        counters += np.asarray(start_counts, dtype=np.int64)
    counter = np.empty(len(agency_codes), dtype=np.int64)
    for agency_index in range(int(agency_codes.max()) + 1):
        mask = agency_codes == agency_index
        count = int(mask.sum())
        counter[mask] = counters[agency_index] + np.arange(1, count + 1)
        counters[agency_index] += count
    counter_str = np.char.zfill(counter.astype("U6"), 6)
    if start_counts is not None:
        start_counts[:] = counters

    prefix = np.char.add(np.char.add(agency, "-"), ymd_str)
    return np.char.add(np.char.add(prefix, "-"), counter_str)


class IncidentGenerator:
    def __init__(self, address_provider: AddressProvider, faker_locale: str = DEFAULT_LOCALE) -> None:
        self._address_provider = address_provider
        self._faker_locale = faker_locale

    def _prepare(
        self, request: GenerationRequest
    ) -> tuple[RealismConfig, ShiftConfig, dict[str, dict[str, list[str]]], list, np.random.Generator, Faker]:
        request.validate()
        realism = request.get_realism_config()
        shift_config = apply_shift_preset(realism.shift_config, request.shift_preset)
        rng = np.random.default_rng(request.seed)
        faker = Faker(self._faker_locale)
        faker.seed_instance(request.seed)

        staffing = _resolve_shift_staffing(shift_config, request)
        shift_pools = _build_shift_pools(faker, staffing)
        logger.info(
            "Personnel built for %d shifts: %d calltakers, %d dispatchers",
            len(shift_config.shifts),
            shift_config.total_calltakers(),
            shift_config.total_dispatchers(),
        )
        logger.info("Loading addresses for '%s'...", request.area_query.strip())
        addresses = self._address_provider.load_addresses(request.area_query)
        logger.info("Loaded %d addresses for sampling", len(addresses))
        if not addresses:
            raise ValidationError("Address provider returned no addresses for the requested area.")
        return realism, shift_config, shift_pools, addresses, rng, faker

    def generate(
        self,
        request: GenerationRequest,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> pd.DataFrame:
        realism, shift_config, shift_pools, addresses, rng, faker = self._prepare(request)
        records = self._build_records(request, realism, shift_config, shift_pools, addresses, rng, faker)

        progress = ProgressReporter(request.rows, logger)
        progress.update(request.rows)
        progress.finish()
        if on_progress is not None:
            on_progress(request.rows, request.rows)
        return pd.DataFrame(records)

    def resolve_chunk_rows(self, request: GenerationRequest) -> int:
        """Row count per chunk that keeps a chunk's DataFrame under the memory budget.

        Prepares addresses and personnel pools on demand, so callers that only
        need the plan (e.g. sizing checks) can call it standalone. Uses an
        independent probe run (separate RNG) so the estimate does not consume
        the seeded generation stream. Returns ``request.rows`` when the whole
        dataset fits in one chunk.
        """
        realism, shift_config, shift_pools, addresses, _rng, faker = self._prepare(request)
        return self._resolve_chunk_rows(
            request, realism, shift_config, shift_pools, addresses, faker
        )

    def _resolve_chunk_rows(
        self,
        request: GenerationRequest,
        realism: RealismConfig,
        shift_config: ShiftConfig,
        shift_pools: dict[str, dict[str, list[str]]],
        addresses: list,
        faker: Faker,
    ) -> int:
        budget = (
            request.max_memory_bytes
            if request.max_memory_bytes is not None
            else DEFAULT_MAX_MEMORY_BYTES
        )
        if budget <= 0:
            return request.rows
        probe_rng = np.random.default_rng(request.seed + 1001)
        probe_guid = _random.Random(request.seed + 1001)
        probe_n = min(request.rows, MEMORY_PROBE_ROWS)
        records = self._build_records(
            request,
            realism,
            shift_config,
            shift_pools,
            addresses,
            probe_rng,
            faker,
            n=probe_n,
            guid_rng=probe_guid,
        )
        bytes_per_row = pd.DataFrame(records).memory_usage(deep=True).sum() / probe_n
        chunk_rows = max(1, int(budget / max(bytes_per_row, 1.0)))
        return min(request.rows, chunk_rows)

    def generate_chunks(
        self,
        request: GenerationRequest,
        chunk_rows: int | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> Iterator[pd.DataFrame]:
        """Yield one ``pd.DataFrame`` per chunk, keeping peak memory bounded.

        ``chunk_rows`` defaults to the memory-budget-derived chunk size (see
        :meth:`resolve_chunk_rows`). Records are generated on a single shared
        RNG across chunks so the stream is deterministic for a given seed and
        chunk plan; ``internal_reference_number`` counters continue across
        chunks and ``id_number`` values stay globally sequential.
        """
        realism, shift_config, shift_pools, addresses, rng, faker = self._prepare(request)
        if chunk_rows is None:
            chunk_rows = self._resolve_chunk_rows(request, realism, shift_config, shift_pools, addresses, faker)
        chunk_rows = max(1, min(chunk_rows, request.rows))

        guid_rng = _random.Random(request.seed)
        agency_counts = np.zeros(len(realism.agency_weights), dtype=np.int64)
        progress = ProgressReporter(request.rows, logger)
        done = 0
        start_index = 0
        while start_index < request.rows:
            n = min(chunk_rows, request.rows - start_index)
            records = self._build_records(
                request,
                realism,
                shift_config,
                shift_pools,
                addresses,
                rng,
                faker,
                n=n,
                start_index=start_index,
                guid_rng=guid_rng,
                start_counts=agency_counts,
            )
            yield pd.DataFrame(records)
            done += n
            progress.update(done)
            if on_progress is not None:
                on_progress(done, request.rows)
            start_index += n
        progress.finish()

    def _build_records(
        self,
        request: GenerationRequest,
        realism: RealismConfig,
        shift_config: ShiftConfig,
        shift_pools: dict[str, dict[str, list[str]]],
        addresses: list,
        rng: np.random.Generator,
        faker: Faker,
        n: int | None = None,
        start_index: int = 0,
        guid_rng: _random.Random | None = None,
        start_counts: np.ndarray | None = None,
    ) -> dict[str, np.ndarray]:
        n = request.rows if n is None else n

        start = np.datetime64(request.resolved_start_date().isoformat()).astype("datetime64[s]")
        event_offsets = _event_time_offsets(rng, request, realism, n)
        event_offsets.sort()
        event_times = start + event_offsets.astype("timedelta64[s]")
        times = pd.DatetimeIndex(event_times)
        times_series = pd.Series(times)

        agency_keys = list(realism.agency_weights)
        agency_probs = np.asarray([realism.agency_weights[key] for key in agency_keys], dtype=float)
        agency_codes = rng.choice(len(agency_keys), size=n, p=agency_probs)
        agency = np.asarray(agency_keys, dtype=str)[agency_codes]

        priorities = np.empty(n, dtype=np.int64)
        priority_key_sets = {key: list(realism.priority_weights[key]) for key in agency_keys}
        for agency_index, agency_key in enumerate(agency_keys):
            keys = priority_key_sets[agency_key]
            probs = np.asarray([realism.priority_weights[agency_key][p] for p in keys], dtype=float)
            mask = agency_codes == agency_index
            priorities[mask] = rng.choice(keys, size=int(mask.sum()), p=probs)

        max_priority = max(max(keys) for keys in priority_key_sets.values())
        timing_tables = {field: self._timing_table(realism, agency_keys, max_priority, field) for field in _TIMING_FIELDS}
        means = {field: timing_tables[field][agency_codes, priorities] for field in _TIMING_FIELDS}

        dispatch_lo = np.zeros(max_priority + 1, dtype=float)
        dispatch_hi = np.zeros(max_priority + 1, dtype=float)
        for priority, (lo, hi) in realism.dispatch_init_fraction.items():
            dispatch_lo[int(priority)] = lo
            dispatch_hi[int(priority)] = hi

        address_fields = {
            field: np.asarray([getattr(address, field) for address in addresses], dtype=object)
            for field in _ADDRESS_FIELDS
        }
        address_index = rng.integers(0, len(addresses), size=n)
        address_columns = {
            field: address_fields[field][address_index] for field in _ADDRESS_FIELDS
        }

        pickup_delay_seconds = _lognormal_seconds(rng, 3, sigma=0.45, size=n, maximum=20)
        interview_seconds = _lognormal_seconds(rng, means["interview_mean"], sigma=0.65, size=n, maximum=1_800)
        dispatch_queue_seconds = _lognormal_seconds(rng, means["dispatch_mean"], sigma=0.85, size=n, maximum=7_200)
        turnout_seconds = _lognormal_seconds(rng, means["turnout_mean"], sigma=0.60, size=n, maximum=900)
        travel_seconds = _lognormal_seconds(rng, means["travel_mean"], sigma=0.55, size=n, maximum=3_600)
        on_scene_seconds = _lognormal_seconds(rng, means["scene_mean"], sigma=0.50, size=n, maximum=10_800)
        closeout_seconds = _lognormal_seconds(rng, means["closeout_mean"], sigma=0.45, size=n, maximum=1_800)
        phone_seconds = _lognormal_seconds(rng, means["phone_mean"], sigma=0.70, size=n, maximum=3_600)
        phone_duration_seconds = np.maximum(interview_seconds + dispatch_queue_seconds, phone_seconds)

        dispatch_fraction = rng.uniform(dispatch_lo[priorities], dispatch_hi[priorities])
        dispatch_init_seconds = (phone_duration_seconds * dispatch_fraction).astype(np.int64)

        pre_cad_offset_seconds = rng.integers(0, 4, size=n)
        incident_start_time = event_times + pre_cad_offset_seconds.astype("timedelta64[s]")
        time_phone_pickup = event_times + pickup_delay_seconds.astype("timedelta64[s]")
        time_call_enters_queue = time_phone_pickup + interview_seconds.astype("timedelta64[s]")
        time_first_unit_assigned = time_phone_pickup + (dispatch_init_seconds + dispatch_queue_seconds).astype("timedelta64[s]")
        time_unit_enroute = time_first_unit_assigned + turnout_seconds.astype("timedelta64[s]")
        time_unit_arrived = time_unit_enroute + travel_seconds.astype("timedelta64[s]")
        time_last_unit_cleared = time_unit_arrived + on_scene_seconds.astype("timedelta64[s]")
        time_call_closed = time_last_unit_cleared + closeout_seconds.astype("timedelta64[s]")
        time_phone_disconnect = time_phone_pickup + phone_duration_seconds.astype("timedelta64[s]")
        total_elapsed_seconds = (time_call_closed - event_times).astype(np.int64)

        shift_index = _active_shift_index(shift_config, event_times)
        shift_names = np.asarray([shift.name for shift in shift_config.shifts], dtype=object)
        shift_labels = np.asarray([shift.label for shift in shift_config.shifts], dtype=object)
        shift_groups = np.asarray([shift.rotation for shift in shift_config.shifts], dtype=np.int64)
        shift = shift_names[shift_index]
        shift_label = shift_labels[shift_index]
        shift_group = shift_groups[shift_index]

        calltakers = np.empty(n, dtype=object)
        dispatchers = np.empty(n, dtype=object)
        for index, shift_spec in enumerate(shift_config.shifts):
            mask = shift_index == index
            count = int(mask.sum())
            if count == 0:
                continue
            pool = shift_pools[shift_spec.name]
            calltakers[mask] = _zipf_choice(rng, pool["calltakers"], count)
            dispatchers[mask] = _zipf_choice(rng, pool["dispatchers"], count)

        reception = _categorical_choice(
            rng,
            list(realism.call_reception_weights),
            [realism.call_reception_weights[key] for key in realism.call_reception_weights],
            n,
        )

        problem_nature = np.empty(n, dtype=object)
        for agency_index, agency_key in enumerate(agency_keys):
            for priority in priority_key_sets[agency_key]:
                pool = realism.problem_profiles[agency_key][priority]
                mask = (agency_codes == agency_index) & (priorities == priority)
                if not mask.any():
                    continue
                problem_nature[mask] = _categorical_choice(
                    rng,
                    [item[0] for item in pool],
                    [item[1] for item in pool],
                    int(mask.sum()),
                )

        disposition = np.empty(n, dtype=object)
        for agency_index, agency_key in enumerate(agency_keys):
            pool = realism.disposition_profiles[agency_key]
            mask = agency_codes == agency_index
            disposition[mask] = _categorical_choice(
                rng,
                [item[0] for item in pool],
                [item[1] for item in pool],
                int(mask.sum()),
            )

        if request.id_format is IdFormat.GUID:
            guid_rng = guid_rng if guid_rng is not None else _random.Random(request.seed)
            id_number: np.ndarray = np.asarray(
                [str(_uuid.UUID(int=guid_rng.getrandbits(128), version=4)) for _ in range(n)],
                dtype=object,
            )
        else:
            id_number = np.arange(start_index + 1, start_index + n + 1)

        reference_numbers = _build_reference_numbers(agency, agency_codes, times_series, start_counts)

        street_address = address_columns["street_address"]
        location = np.char.add(street_address.astype("U"), ", ")
        location = np.char.add(location, address_columns["city"].astype("U"))
        location = np.char.add(location, ", ")
        location = np.char.add(location, address_columns["state"].astype("U"))

        hour = times_series.dt.hour.to_numpy()
        dow = np.asarray(_DAY_ABBREVIATIONS, dtype=str)[
            times_series.dt.dayofweek.to_numpy()
        ]
        week_no = times_series.dt.isocalendar().week.to_numpy()

        return {
            "id_number": id_number,
            "internal_reference_number": reference_numbers,
            "agency": agency,
            "shift": shift,
            "shift_label": shift_label,
            "shift_group": shift_group,
            "problem_nature": problem_nature,
            "priority": priorities,
            "prefix_directional": address_columns["prefix_directional"],
            "street_number": address_columns["street_number"],
            "street_name": address_columns["street_name"],
            "street_type": address_columns["street_type"],
            "postfix_directional": address_columns["postfix_directional"],
            "street_address": street_address,
            "city": address_columns["city"],
            "state": address_columns["state"],
            "postal_code": address_columns["postal_code"],
            "location": location,
            "call_start_time": event_times,
            "hour": hour,
            "dow": dow,
            "week_no": week_no,
            "incident_start_time": incident_start_time,
            "time_phone_pickup": time_phone_pickup,
            "time_call_enters_queue": time_call_enters_queue,
            "time_first_unit_assigned": time_first_unit_assigned,
            "time_unit_enroute": time_unit_enroute,
            "time_unit_arrived": time_unit_arrived,
            "time_last_unit_cleared": time_last_unit_cleared,
            "time_call_closed": time_call_closed,
            "time_phone_disconnect": time_phone_disconnect,
            "calltaker": calltakers,
            "dispatcher": dispatchers,
            "method_of_call_reception": reception,
            "call_disposition": disposition,
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

    @staticmethod
    def _timing_table(
        realism: RealismConfig, agency_keys: list[str], max_priority: int, field: str
    ) -> np.ndarray:
        table = np.zeros((len(agency_keys), max_priority + 1), dtype=np.float64)
        for agency_index, agency_key in enumerate(agency_keys):
            for priority, profile in realism.time_profiles[agency_key].items():
                table[agency_index, int(priority)] = float(profile[field])
        return table
