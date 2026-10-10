"""CAD incident record generation (vectorized, seed-deterministic).

:class:`IncidentGenerator` produces the full incident dataset for a
request: agency/priority weighted problem natures, seasonal weighting,
lognormal lifecycle timings, geographic zone travel multipliers,
shift-aware calltaker/dispatcher assignment (Zipf-weighted for workload
realism, with dispatcher pools split into LAW / FIRE / EMS discipline
consoles for medium/large centres), reception and disposition profiles,
and reference numbers per agency/day. All draws flow through a single
seeded NumPy RNG so a given seed plus realism config yields
byte-identical output; large runs stream chunks via
:meth:`IncidentGenerator.generate_chunks` under a memory budget.
"""

from __future__ import annotations

import random as _random
import sys
import uuid as _uuid
from collections.abc import Callable, Iterable, Iterator
from copy import copy
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from synth911gen3.addresses import AddressProvider
from synth911gen3.config import GenerationRequest, IdFormat
from synth911gen3.constants import (
    DEFAULT_COUNTRY,
    DEFAULT_MAX_MEMORY_BYTES,
    DEFAULT_PROBLEM_PHONE_MULTIPLIER,
    DEFAULT_SEASONAL_MULTIPLIER,
)
from synth911gen3.exceptions import ValidationError
from synth911gen3.logging_conf import ProgressReporter, get_logger
from synth911gen3.names import PersonnelNameGenerator, resolve_name_locales
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
    "latitude",
    "longitude",
    "zone",
    "commonplace_name",
    "unit_number",
)

# Per-row bytes pandas charges before an element's own payload: the 8-byte slot
# a `str` column value occupies, and the 8-byte pointer an `object` column holds.
# Measured on pandas 3.x: `str` columns report ``memory_usage(deep=True)`` as
# 8 bytes + UTF-8 byte length per row.
_ELEMENT_BASE_BYTES = 8
# Chunk sizing multiplies the raw estimate by this factor so a chunk never
# exceeds the budget when the statistical estimate lands slightly low.
_BYTES_PER_ROW_SAFETY_FACTOR = 1.1
# Address pools larger than this are stride-sampled when averaging field
# lengths, so estimator cost stays flat as the pool grows.
_ADDRESS_SAMPLE_CAP = 10_000
# Fixed-width columns in the generated frame and their per-row byte cost
# (int64 = 8, int32/uint32 = 4, datetime64[s] = 8).
_FIXED_WIDTH_BYTES: dict[str, int] = {
    "shift_group": 8,
    "priority": 8,
    "hour": 4,
    "week_no": 4,
    "call_start_time": 8,
    "incident_start_time": 8,
    "time_phone_pickup": 8,
    "time_call_enters_queue": 8,
    "time_first_unit_assigned": 8,
    "time_unit_enroute": 8,
    "time_unit_arrived": 8,
    "time_last_unit_cleared": 8,
    "time_call_closed": 8,
    "time_phone_disconnect": 8,
    "pickup_delay_seconds": 8,
    "pre_cad_offset_seconds": 8,
    "interview_seconds": 8,
    "dispatch_queue_seconds": 8,
    "turnout_seconds": 8,
    "travel_seconds": 8,
    "on_scene_seconds": 8,
    "closeout_seconds": 8,
    "phone_duration_seconds": 8,
    "total_elapsed_seconds": 8,
}

logger = get_logger("incidents")


@dataclass(slots=True)
class PreparedState:
    """Cached results of :meth:`IncidentGenerator._prepare`.

    Holds the resolved realism config, shift config, personnel pools,
    loaded addresses, and RNG so callers can pass pre-computed state
    into :meth:`generate_chunks` without re-running address fetches
    and personnel builds.
    """

    realism: RealismConfig
    shift_config: ShiftConfig
    shift_pools: dict[str, dict[str, Any]]
    addresses: list
    rng: np.random.Generator


def _weighted_choice_from_pairs(
    rng: np.random.Generator, weighted_pairs: list[tuple[str, float]]
) -> str:
    """Draw one label from ``(label, weight)`` pairs with normalized probabilities."""
    values = [item for item, _ in weighted_pairs]
    probabilities = [weight for _, weight in weighted_pairs]
    return str(rng.choice(values, p=probabilities))


def _distribute(amount: int, slots: int) -> list[int]:
    """Split ``amount`` across ``slots`` as evenly as possible (remainder first)."""
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
        calltakers = shift.calltakers if shift.calltakers is not None else ct_split[ct_index]
        if shift.calltakers is None:
            ct_index += 1
        dispatchers = shift.dispatchers if shift.dispatchers is not None else dsp_split[dsp_index]
        if shift.dispatchers is None:
            dsp_index += 1
        plan.append((shift.name, max(1, calltakers), max(1, dispatchers)))
    return plan


def _build_shift_pools(
    name_gen: PersonnelNameGenerator,
    staffing: list[tuple[str, int, int]],
    dispatcher_groups: dict[str, dict[str, int]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Create a unique-name roster per shift: ``{shift: {calltakers, dispatchers}}``.

    When ``dispatcher_groups`` carries discipline sub-pool sizes for a shift
    (from :func:`_resolve_dispatcher_groups`), the drawn dispatcher roster is
    partitioned into ``dispatchers_by_group`` in canonical group order so
    incidents draw their dispatcher from the console matching their agency.
    """
    pools: dict[str, dict[str, Any]] = {}
    for name, calltakers, dispatchers in staffing:
        calltaker_roster = [name_gen.unique_name() for _ in range(calltakers)]
        dispatcher_roster = [name_gen.unique_name() for _ in range(dispatchers)]
        entry: dict[str, Any] = {
            "calltakers": calltaker_roster,
            "dispatchers": dispatcher_roster,
        }
        groups = (dispatcher_groups or {}).get(name)
        if groups:
            offset = 0
            by_group: dict[str, list[str]] = {}
            for group, size in groups.items():
                by_group[group] = dispatcher_roster[offset : offset + size]
                offset += size
            entry["dispatchers_by_group"] = by_group
        pools[name] = entry
    return pools


# Dispatcher console disciplines: which agencies each discipline group covers.
_DISPATCHER_GROUP_AGENCIES: dict[str, frozenset[str]] = {
    "law": frozenset({"LAW"}),
    "fire_ems": frozenset({"FIRE", "EMS"}),
    "fire": frozenset({"FIRE"}),
    "ems": frozenset({"EMS"}),
}
# Canonical group ordering per breakdown mode (drives deterministic roster
# partitioning: remainder positions land on earlier disciplines, LAW first).
_DISPATCHER_GROUP_ORDER: dict[str, tuple[str, ...]] = {
    "two_way": ("law", "fire_ems"),
    "three_way": ("law", "fire", "ems"),
}
# ``auto`` mode escalates from two-way to a full three-way split once a shift
# staffs this many dispatcher positions.
_AUTO_THREE_WAY_MIN = 8


def _discipline_counts(
    count: int,
    mode: str,
    threshold: int,
    active_agencies: frozenset[str],
) -> dict[str, int]:
    """Dispatcher counts per discipline group for one shift (empty = combined).

    Splits only when more than one agency is active; single-agency PSAPs keep
    one combined console regardless of position count. ``auto`` honors the
    configured ``threshold`` and escalates to three-way at
    ``_AUTO_THREE_WAY_MIN`` positions; explicit ``two_way``/``three_way``
    modes split at any staffing level. Groups left with zero positions are
    dropped, and a lone remaining group collapses back to combined.
    """
    if count <= 0 or len(active_agencies) <= 1:
        return {}
    if mode == "auto":
        if count < threshold:
            return {}
        mode = "three_way" if count >= _AUTO_THREE_WAY_MIN else "two_way"
    order = [
        group
        for group in _DISPATCHER_GROUP_ORDER.get(mode, ())
        if _DISPATCHER_GROUP_AGENCIES[group] & active_agencies
    ]
    if not order:
        return {}
    counts = _distribute(count, len(order))
    groups = {
        group: size for group, size in zip(order, counts) if size > 0
    }
    return groups if len(groups) > 1 else {}


def _resolve_dispatcher_groups(
    staffing: list[tuple[str, int, int]],
    realism: RealismConfig,
    active_agencies: frozenset[str],
) -> dict[str, dict[str, int]]:
    """Per-shift dispatcher discipline sub-pool sizes (absent = combined).

    Reads ``realism.dispatcher_disciplines``: ``mode`` selects the breakdown
    and ``min_dispatchers_for_split`` gates ``auto`` splitting. See
    :func:`_discipline_counts` for the exact semantics.
    """
    disciplines = realism.dispatcher_disciplines
    mode = str(disciplines.get("mode", "auto"))
    threshold = max(1, int(disciplines.get("min_dispatchers_for_split", 4)))
    plan: dict[str, dict[str, int]] = {}
    for name, _calltakers, dispatchers in staffing:
        groups = _discipline_counts(dispatchers, mode, threshold, active_agencies)
        if groups:
            plan[name] = groups
    return plan


def _zipf_weights(count: int) -> np.ndarray:
    """Normalized Zipf-ish weights (1/k) so earlier pool members take more calls."""
    weights = np.array([1.0 / (index + 1) for index in range(count)])
    return weights / weights.sum()


def _zipf_pick(rng: np.random.Generator, names: list[str]) -> str:
    """Single Zipf-weighted pick from a name pool."""
    return str(rng.choice(np.asarray(names, dtype=object), p=_zipf_weights(len(names))))


def _zipf_choice(rng: np.random.Generator, names: list[str], size: int) -> np.ndarray:
    """Vectorized Zipf-weighted draws from a name pool."""
    return rng.choice(np.asarray(names, dtype=object), size=size, p=_zipf_weights(len(names)))


def _categorical_choice(
    rng: np.random.Generator, values: list[str], weights: list[float], size: int
) -> np.ndarray:
    """Vectorized weighted draw from a categorical label set."""
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
    """Draw lognormal durations (seconds) with a target mean, clipped to bounds."""
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
    """Per-agency daily reference numbers like ``LAW-260-00001``.

    The counter runs per agency over the whole dataset (continuing across
    chunks via ``start_counts``); the date portion is the incident's
    day-of-year (001-366).
    """
    doy = times_series.dt.dayofyear
    doy_str = np.char.zfill(doy.to_numpy().astype("U3"), 3)

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
    counter_str = np.char.zfill(counter.astype("U5"), 5)
    if start_counts is not None:
        start_counts[:] = counters

    prefix = np.char.add(np.char.add(agency, "-"), doy_str)
    return np.char.add(np.char.add(prefix, "-"), counter_str)


def _utf8_len(value: Any) -> int:
    """UTF-8 byte length pandas stores for ``value``; ``None`` stores nothing."""
    if not value:
        return 0
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    return len(str(value).encode("utf-8"))


def _mean_utf8(values: Iterable[Any]) -> float:
    """Mean UTF-8 length across ``values``; ``0.0`` when there are none."""
    total = 0
    count = 0
    for value in values:
        total += _utf8_len(value)
        count += 1
    return total / count if count else 0.0


def _weighted_mean_utf8(pairs: Iterable[tuple[Any, float]]) -> float:
    """Weighted mean UTF-8 length across ``(value, weight)`` pairs.

    Falls back to the unweighted mean when every weight is non-positive, so
    an unconfigured registry never reports zero-length values.
    """
    weighted = 0.0
    total_weight = 0.0
    unweighted = 0.0
    count = 0
    for value, weight in pairs:
        length = _utf8_len(value)
        unweighted += length
        count += 1
        if weight > 0:
            weighted += weight * length
            total_weight += weight
    if total_weight <= 0:
        return unweighted / count if count else 0.0
    return weighted / total_weight


def _mean_sizeof(values: Iterable[Any]) -> float:
    """Mean ``sys.getsizeof`` across ``values``; ``0.0`` when there are none."""
    total = 0
    count = 0
    for value in values:
        total += sys.getsizeof(value)
        count += 1
    return total / count if count else 0.0


def _sample_addresses(addresses: list) -> list:
    """Evenly spaced subset of ``addresses`` capped at ``_ADDRESS_SAMPLE_CAP``."""
    if len(addresses) <= _ADDRESS_SAMPLE_CAP:
        return addresses
    stride = -(-len(addresses) // _ADDRESS_SAMPLE_CAP)
    return addresses[::stride]


def _problem_nature_mean_bytes(realism: RealismConfig) -> float:
    """Agency × priority × label-weighted mean length of problem natures."""
    return _weighted_mean_utf8(
        (
            label,
            realism.agency_weights.get(agency, 0.0)
            * realism.priority_weights.get(agency, {}).get(priority, 0.0)
            * weight,
        )
        for agency, priorities in realism.problem_profiles.items()
        for priority, profile in priorities.items()
        for label, weight in profile
    )


def _disposition_mean_bytes(realism: RealismConfig) -> float:
    """Agency-weighted mean length of call-disposition labels."""
    return _weighted_mean_utf8(
        (label, realism.agency_weights.get(agency, 0.0) * weight)
        for agency, profile in realism.disposition_profiles.items()
        for label, weight in profile
    )


def _personnel_mean_bytes(pools: Iterable[list[str]]) -> float:
    """Mean length of personnel names pooled across shifts."""
    return _mean_utf8(name for pool in pools for name in pool)


def _dispatcher_pools(shift_pools: dict[str, dict[str, Any]]) -> list[list[str]]:
    """Dispatcher pools per shift, preferring discipline consoles when split."""
    pools = []
    for pool in shift_pools.values():
        groups = pool.get("dispatchers_by_group")
        if groups:
            pools.extend(groups.values())
        else:
            pools.append(pool["dispatchers"])
    return pools


def _estimate_bytes_per_row_contributions(
    request: GenerationRequest,
    realism: RealismConfig,
    shift_config: ShiftConfig,
    shift_pools: dict[str, dict[str, Any]],
    addresses: list,
) -> dict[str, float]:
    """Per-column bytes-per-row for the frame :meth:`_build_records` produces.

    Prices columns the way ``DataFrame.memory_usage(deep=True)`` does: numeric
    and datetime columns at their dtype width, ``str`` columns at
    ``_ELEMENT_BASE_BYTES`` plus UTF-8 payload averaged over the pools the
    values are drawn from, and ``object`` columns at a pointer plus
    ``sys.getsizeof`` of the pooled values. No records are generated and no RNG
    is consumed, so this is cheap and leaves the seeded stream untouched.
    """
    sample = _sample_addresses(addresses)
    contributions: dict[str, float] = {
        column: float(width) for column, width in _FIXED_WIDTH_BYTES.items()
    }
    contributions["id_number"] = (
        float(_ELEMENT_BASE_BYTES + 36)
        if request.id_format is IdFormat.GUID
        else 8.0
    )

    address_payloads = {
        field: _mean_utf8(getattr(address, field) for address in sample)
        for field in _ADDRESS_FIELDS
        if field not in ("latitude", "longitude")
    }
    agency_mean = _weighted_mean_utf8(realism.agency_weights.items())
    str_payloads = {
        # Reference numbers look like ``LAW-260-00001``: agency plus ten more chars.
        "internal_reference_number": agency_mean + 10.0,
        "agency": agency_mean,
        "shift": _mean_utf8(shift.name for shift in shift_config.shifts),
        "shift_label": _mean_utf8(shift.label for shift in shift_config.shifts),
        "problem_nature": _problem_nature_mean_bytes(realism),
        "dow": _mean_utf8(_DAY_ABBREVIATIONS),
        "method_of_call_reception": _weighted_mean_utf8(
            realism.call_reception_weights.items()
        ),
        "call_disposition": _disposition_mean_bytes(realism),
        "calltaker": _personnel_mean_bytes(
            pool["calltakers"] for pool in shift_pools.values()
        ),
        "dispatcher": _personnel_mean_bytes(_dispatcher_pools(shift_pools)),
        # ``location`` is "street_address, city, state" — two ", " separators.
        "location": (
            address_payloads["street_address"]
            + address_payloads["city"]
            + address_payloads["state"]
            + 4.0
        ),
    }

    for column, payload in address_payloads.items():
        contributions[column] = _ELEMENT_BASE_BYTES + payload
    for column, payload in str_payloads.items():
        contributions[column] = _ELEMENT_BASE_BYTES + payload
    for field in ("latitude", "longitude"):
        contributions[field] = _ELEMENT_BASE_BYTES + _mean_sizeof(
            getattr(address, field) for address in sample
        )

    return contributions


class IncidentGenerator:
    """Vectorized, seed-deterministic CAD incident dataset generator."""

    def __init__(self, address_provider: AddressProvider) -> None:
        """Bind the address provider used to sample incident locations."""
        self._address_provider = address_provider

    def _prepare(
        self, request: GenerationRequest
    ) -> tuple[
        RealismConfig, ShiftConfig, dict[str, dict[str, Any]], list, np.random.Generator
    ]:
        """Validate, merge realism config, load addresses, and build personnel rosters."""
        request.validate()
        realism = request.get_realism_config()

        # Apply PSAP agency filter: restrict agency_weights to the selected
        # agencies so all downstream tables (priority, problem, disposition,
        # timing) adapt automatically.
        from ..constants import PSAP_AGENCY_FILTERS

        allowed_agencies = PSAP_AGENCY_FILTERS[request.psap_agency]
        if allowed_agencies != frozenset(realism.agency_weights):
            filtered = {
                k: v for k, v in realism.agency_weights.items() if k in allowed_agencies
            }
            total = sum(filtered.values())
            if total > 0:
                filtered = {k: v / total for k, v in filtered.items()}
            # Replace agency_weights on a copy so the original config is untouched
            realism = copy(realism)
            realism.agency_weights = filtered
            logger.info("PSAP agency filter '%s': agencies=%s", request.psap_agency, list(filtered))

        shift_config = apply_shift_preset(realism.shift_config, request.shift_preset)
        rng = np.random.default_rng(request.seed)

        logger.info("Loading addresses for '%s'...", request.area_query.strip())
        addresses = self._address_provider.load_addresses(request.area_query)
        logger.info("Loaded %d addresses for sampling", len(addresses))
        if not addresses:
            raise ValidationError("Address provider returned no addresses for the requested area.")

        # Personnel names follow the region the addresses were drawn from; the
        # request's country acts as the fallback when the provider cannot tell.
        resolved_country = getattr(self._address_provider, "resolved_country", None)
        provider_country: str | None = None
        if callable(resolved_country):
            value = resolved_country()
            provider_country = str(value) if value else None
        country = provider_country or request.country or DEFAULT_COUNTRY
        name_locales = resolve_name_locales(country, override=realism.name_locales)
        logger.info(
            "Personnel name locales for country %s: %s",
            country,
            ", ".join(locale for locale, _ in name_locales),
        )
        name_gen = PersonnelNameGenerator(name_locales, seed=request.seed)
        staffing = _resolve_shift_staffing(shift_config, request)
        active_agencies = frozenset(realism.agency_weights) & allowed_agencies
        dispatcher_groups = _resolve_dispatcher_groups(staffing, realism, active_agencies)
        if dispatcher_groups:
            logger.info(
                "Dispatcher discipline consoles active for %d shift(s): %s",
                len(dispatcher_groups),
                {name: dict(groups) for name, groups in dispatcher_groups.items()},
            )
        shift_pools = _build_shift_pools(name_gen, staffing, dispatcher_groups)
        logger.info(
            "Personnel built for %d shifts: %d calltakers, %d dispatchers",
            len(shift_config.shifts),
            shift_config.total_calltakers(),
            shift_config.total_dispatchers(),
        )
        return realism, shift_config, shift_pools, addresses, rng

    def generate(
        self,
        request: GenerationRequest,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> pd.DataFrame:
        """Generate the full incident dataset as a single DataFrame."""
        realism, shift_config, shift_pools, addresses, rng = self._prepare(request)
        records = self._build_records(request, realism, shift_config, shift_pools, addresses, rng)

        progress = ProgressReporter(request.rows, logger)
        progress.update(request.rows)
        progress.finish()
        if on_progress is not None:
            on_progress(request.rows, request.rows)
        return pd.DataFrame(records)

    def resolve_chunk_rows(self, request: GenerationRequest) -> int:
        """Row count per chunk that keeps a chunk's DataFrame under the memory budget.

        Prepares addresses and personnel pools on demand, so callers that only
        need the plan (e.g. sizing checks) can call it standalone. Sizes the
        chunk from a statistical bytes-per-row estimate, so no sample records
        are generated and the seeded generation stream stays untouched. Returns
        ``request.rows`` when the whole dataset fits in one chunk.

        .. note::

           For callers that also intend to call :meth:`generate_chunks`, use
           :meth:`resolve_chunk_rows_with_state` instead to avoid running
           the expensive ``_prepare()`` twice.
        """
        realism, shift_config, shift_pools, addresses, _rng = self._prepare(request)
        return self._resolve_chunk_rows(request, realism, shift_config, shift_pools, addresses)

    def resolve_chunk_rows_with_state(
        self, request: GenerationRequest
    ) -> tuple[int, PreparedState]:
        """Like :meth:`resolve_chunk_rows` but also returns the :class:`PreparedState`.

        Callers that size the chunks *and* then generate can pass the
        returned state into :meth:`generate_chunks`, eliminating the
        duplicate address-fetch + personnel-build.
        """
        realism, shift_config, shift_pools, addresses, rng = self._prepare(request)
        state = PreparedState(
            realism=realism,
            shift_config=shift_config,
            shift_pools=shift_pools,
            addresses=addresses,
            rng=rng,
        )
        chunk_rows = self._resolve_chunk_rows(
            request, realism, shift_config, shift_pools, addresses
        )
        return chunk_rows, state

    def _resolve_chunk_rows(
        self,
        request: GenerationRequest,
        realism: RealismConfig,
        shift_config: ShiftConfig,
        shift_pools: dict[str, dict[str, Any]],
        addresses: list,
    ) -> int:
        """Chunk size that keeps one chunk under the memory budget (estimated)."""
        budget = (
            request.max_memory_bytes
            if request.max_memory_bytes is not None
            else DEFAULT_MAX_MEMORY_BYTES
        )
        if budget <= 0:
            return request.rows
        contributions = _estimate_bytes_per_row_contributions(
            request, realism, shift_config, shift_pools, addresses
        )
        bytes_per_row = sum(contributions.values()) * _BYTES_PER_ROW_SAFETY_FACTOR
        chunk_rows = max(1, int(budget / max(bytes_per_row, 1.0)))
        return min(request.rows, chunk_rows)

    def generate_chunks(
        self,
        request: GenerationRequest,
        chunk_rows: int | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        prepared: PreparedState | None = None,
    ) -> Iterator[pd.DataFrame]:
        """Yield one ``pd.DataFrame`` per chunk, keeping peak memory bounded.

        ``chunk_rows`` defaults to the memory-budget-derived chunk size (see
        :meth:`resolve_chunk_rows`). Records are generated on a single shared
        RNG across chunks so the stream is deterministic for a given seed and
        chunk plan; ``internal_reference_number`` counters continue across
        chunks and ``id_number`` values stay globally sequential.

        When *prepared* is supplied (from :meth:`resolve_chunk_rows_with_state`),
        the expensive address-fetch and personnel-build steps are skipped.
        """
        if prepared is not None:
            realism = prepared.realism
            shift_config = prepared.shift_config
            shift_pools = prepared.shift_pools
            addresses = prepared.addresses
            rng = prepared.rng
        else:
            realism, shift_config, shift_pools, addresses, rng = self._prepare(request)
        if chunk_rows is None:
            chunk_rows = self._resolve_chunk_rows(
                request, realism, shift_config, shift_pools, addresses
            )
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
        shift_pools: dict[str, dict[str, Any]],
        addresses: list,
        rng: np.random.Generator,
        n: int | None = None,
        start_index: int = 0,
        guid_rng: _random.Random | None = None,
        start_counts: np.ndarray | None = None,
    ) -> dict[str, np.ndarray]:
        """Draw one chunk of records as a dict of parallel NumPy columns.

        All random draws come from ``rng`` so the whole dataset is
        reproducible; ``start_index`` seeds sequential integer IDs and
        ``start_counts`` carries reference-number counters across chunks.
        """
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
        timing_tables = {
            field: self._timing_table(realism, agency_keys, max_priority, field)
            for field in _TIMING_FIELDS
        }
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
        address_columns = {field: address_fields[field][address_index] for field in _ADDRESS_FIELDS}

        # Determine season for each incident (0=Winter, 1=Spring, 2=Summer, 3=Fall)
        # Must be done before problem_nature generation for seasonal weighting
        months = times_series.dt.month.to_numpy()
        seasons = np.empty(n, dtype=np.int8)
        seasons[(months == 12) | (months <= 2)] = 0  # Winter: Dec, Jan, Feb
        seasons[(months >= 3) & (months <= 5)] = 1  # Spring: Mar, Apr, May
        seasons[(months >= 6) & (months <= 8)] = 2  # Summer: Jun, Jul, Aug
        seasons[(months >= 9) & (months <= 11)] = 3  # Fall: Sep, Oct, Nov

        # Generate problem_nature early so we can apply problem-specific phone duration multipliers
        problem_nature = np.empty(n, dtype=object)
        for agency_index, agency_key in enumerate(agency_keys):
            for priority in priority_key_sets[agency_key]:
                pool = realism.problem_profiles[agency_key][priority]
                mask = (agency_codes == agency_index) & (priorities == priority)
                if not mask.any():
                    continue

                problem_names = [item[0] for item in pool]
                base_weights = np.array([item[1] for item in pool], dtype=float)
                mask_indices = np.where(mask)[0]
                mask_seasons = seasons[mask_indices]

                # Apply seasonal multipliers per incident
                selected = np.empty(len(mask_indices), dtype=object)
                for i, season in enumerate(mask_seasons):
                    # Compute weights for this incident's season
                    incident_weights = base_weights.copy()
                    for idx, prob_name in enumerate(problem_names):
                        multipliers = realism.seasonal_multipliers.get(
                            prob_name, DEFAULT_SEASONAL_MULTIPLIER
                        )
                        incident_weights[idx] = base_weights[idx] * multipliers[season]
                    # Re-normalize
                    incident_weights = incident_weights / incident_weights.sum()
                    selected[i] = rng.choice(problem_names, p=incident_weights)

                problem_nature[mask_indices] = selected

        # Compute problem-specific phone duration multipliers
        problem_phone_multipliers = np.array(
            [
                realism.problem_phone_multipliers.get(problem, DEFAULT_PROBLEM_PHONE_MULTIPLIER)
                for problem in problem_nature
            ],
            dtype=float,
        )
        # Apply multipliers to phone_mean
        means["phone_mean"] = means["phone_mean"] * problem_phone_multipliers

        pickup_delay_seconds = _lognormal_seconds(rng, 3, sigma=0.45, size=n, maximum=20)
        interview_seconds = _lognormal_seconds(
            rng, means["interview_mean"], sigma=0.65, size=n, maximum=1_800
        )
        dispatch_queue_seconds = _lognormal_seconds(
            rng, means["dispatch_mean"], sigma=0.85, size=n, maximum=7_200
        )
        turnout_seconds = _lognormal_seconds(
            rng, means["turnout_mean"], sigma=0.60, size=n, maximum=900
        )
        travel_seconds = _lognormal_seconds(
            rng, means["travel_mean"], sigma=0.55, size=n, maximum=3_600
        )
        # Apply geographic zone travel multipliers
        zone_multipliers = np.array(
            [realism.zone_travel_multipliers.get(zone, 1.0) for zone in address_columns["zone"]],
            dtype=float,
        )
        travel_seconds = (travel_seconds * zone_multipliers).astype(np.int64)
        on_scene_seconds = _lognormal_seconds(
            rng, means["scene_mean"], sigma=0.50, size=n, maximum=10_800
        )
        closeout_seconds = _lognormal_seconds(
            rng, means["closeout_mean"], sigma=0.45, size=n, maximum=1_800
        )
        phone_seconds = _lognormal_seconds(
            rng, means["phone_mean"], sigma=0.70, size=n, maximum=3_600
        )
        phone_duration_seconds = np.maximum(
            interview_seconds + dispatch_queue_seconds, phone_seconds
        )

        dispatch_fraction = rng.uniform(dispatch_lo[priorities], dispatch_hi[priorities])
        dispatch_init_seconds = (phone_duration_seconds * dispatch_fraction).astype(np.int64)

        pre_cad_offset_seconds = rng.integers(0, 4, size=n)
        incident_start_time = event_times + pre_cad_offset_seconds.astype("timedelta64[s]")
        time_phone_pickup = event_times + pickup_delay_seconds.astype("timedelta64[s]")
        time_call_enters_queue = time_phone_pickup + interview_seconds.astype("timedelta64[s]")
        time_first_unit_assigned = time_phone_pickup + (
            dispatch_init_seconds + dispatch_queue_seconds
        ).astype("timedelta64[s]")
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
            group_pools = pool.get("dispatchers_by_group")
            if not group_pools:
                dispatchers[mask] = _zipf_choice(rng, pool["dispatchers"], count)
                continue
            # Discipline consoles: draw from the sub-pool matching each
            # incident's agency (FIRE/EMS share a console in two-way mode).
            agency_to_group: dict[str, str] = {}
            for group in group_pools:
                for covered_agency in _DISPATCHER_GROUP_AGENCIES[group]:
                    agency_to_group.setdefault(covered_agency, group)
            fallback_group = next(iter(group_pools))
            group_lookup = np.asarray(
                [agency_to_group.get(key, fallback_group) for key in agency_keys],
                dtype=object,
            )
            shift_rows = np.flatnonzero(mask)
            row_groups = group_lookup[agency_codes[shift_rows]]
            for group, names in group_pools.items():
                selected = shift_rows[row_groups == group]
                if selected.size:
                    dispatchers[selected] = _zipf_choice(rng, names, int(selected.size))

        reception = _categorical_choice(
            rng,
            list(realism.call_reception_weights),
            [realism.call_reception_weights[key] for key in realism.call_reception_weights],
            n,
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

        reference_numbers = _build_reference_numbers(
            agency, agency_codes, times_series, start_counts
        )

        street_address = address_columns["street_address"]
        location = np.char.add(street_address.astype("U"), ", ")
        location = np.char.add(location, address_columns["city"].astype("U"))
        location = np.char.add(location, ", ")
        location = np.char.add(location, address_columns["state"].astype("U"))

        hour = times_series.dt.hour.to_numpy()
        dow = np.asarray(_DAY_ABBREVIATIONS, dtype=str)[times_series.dt.dayofweek.to_numpy()]
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
            "latitude": address_columns["latitude"],
            "longitude": address_columns["longitude"],
            "zone": address_columns["zone"],
            "commonplace_name": address_columns["commonplace_name"],
            "unit_number": address_columns["unit_number"],
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
        """Lookup table of a timing field's mean per (agency, priority) cell."""
        table = np.zeros((len(agency_keys), max_priority + 1), dtype=np.float64)
        for agency_index, agency_key in enumerate(agency_keys):
            for priority, profile in realism.time_profiles[agency_key].items():
                table[agency_index, int(priority)] = float(profile[field])
        return table
