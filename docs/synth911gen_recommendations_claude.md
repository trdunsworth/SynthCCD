# Synth911Gen — Code Review & Improvement Recommendations

**Prepared for:** Development Team  
**Source file reviewed:** `synth911gen.py`  
**Reference datasets:** `week07.csv`, `week08.csv`  
**Date:** 2026-02-27

---

## Executive Summary

The generator produces plausible-looking data but uses distributions that do not match the statistical patterns found in real CAD exports. The most significant gaps are in elapsed-time modeling (times are either too short, too long, or not correlated with call priority), the hourly call-volume curve (calls are uniformly distributed across the day), the call reception / disposition vocabularies (values do not match real-world CAD codes), and personnel name generation (names are formatted but not constrained to a realistic shift headcount). Each recommendation below includes the relevant finding from the reference data and a corrected Python example.

---

## 1. Elapsed-Time Distributions Do Not Match Real Data

### Current Behavior

The code uses several independently-chosen statistical distributions with hard-clipped bounds. The resulting values differ substantially from the reference weeks:

| Metric | Current (approx. median) | Real Data Median |
|---|---|---|
| `queue_time` | ~200 s (normalized lognormal) | 49 s |
| `dispatch_time` | ~10 s (chi-square × 2) | 4 s (P1/P3), up to 361 s (P4) |
| `phone_time` | ~80 s (80% fast / 20% slow) | 132 s |
| `ack_time` (rollout) | ~60 s (gamma) | 5 s |
| `enroute_time` (transit) | 300–900 s (gamma, clipped) | 256 s median, range 0–3 583 s |
| `total_time` | hundreds of seconds | 2 842 s median (~47 min) |

### Recommendations

#### 1a — Calibrate `queue_time` to a lognormal with empirically derived parameters

The reference data shows `Time_To_Queue` with a median of ~49 s, mean ~67 s, 95th percentile ~191 s, and a long tail up to ~3 480 s. A lognormal fit to these percentiles yields approximately `μ=3.7, σ=0.9`.

```python
import numpy as np

def generate_queue_times(n: int) -> np.ndarray:
    """
    Generate queue_time values (seconds from call receipt to call queued).
    Calibrated to real CAD data: median ~49 s, p95 ~191 s.
    """
    raw = np.random.lognormal(mean=3.7, sigma=0.9, size=n).astype(int)
    return np.clip(raw, a_min=0, a_max=3600)
```

#### 1b — Make `dispatch_time` priority-dependent

Real data shows that `Time_To_Dispatch` is *bimodal by priority*: Priority 1 and 3 calls are dispatched almost instantly (median 3–4 s), while Priority 4 calls have a long tail (median ~361 s) because they are queued for deferred dispatch. A single chi-square distribution cannot capture this.

```python
# Additional library: none (uses numpy)

# Priority-keyed parameters: (lognormal_mu, lognormal_sigma, clip_max)
DISPATCH_PARAMS = {
    1: (1.5, 0.7, 60),    # immediate dispatch
    2: (2.5, 1.0, 600),
    3: (1.5, 0.7, 60),
    4: (5.5, 1.2, 3600),  # deferred/queued
    5: (5.0, 1.3, 7200),
}

def generate_dispatch_times(priorities: np.ndarray) -> np.ndarray:
    """
    Generate dispatch_time conditioned on priority_number.
    """
    result = np.zeros(len(priorities), dtype=int)
    for p, (mu, sigma, cap) in DISPATCH_PARAMS.items():
        mask = priorities == p
        n = int(mask.sum())
        if n > 0:
            vals = np.random.lognormal(mu, sigma, size=n).astype(int)
            result[mask] = np.clip(vals, 0, cap)
    # Fallback for any unmapped priorities
    unset = result == 0
    if unset.any():
        result[unset] = np.random.lognormal(3.5, 1.0, size=int(unset.sum())).astype(int)
    return result
```

#### 1c — Calibrate `phone_time` to real data

The reference data shows a median of 132 s and a 95th percentile of ~599 s. The current bimodal mix (80 % fast calls at `scale=80`, 20 % slow at `shape=2, scale=200`) produces a median well below this.

```python
def generate_phone_times(n: int) -> np.ndarray:
    """
    Generate phone_time (call duration in seconds).
    Calibrated: median ~132 s, p95 ~599 s.
    Two populations: short (welfare checks, C2C) and long (complex calls).
    """
    n_short = int(n * 0.35)
    n_long  = n - n_short
    short = np.random.exponential(scale=60,  size=n_short)   # ~1 min median
    long  = np.random.gamma(shape=2.5, scale=90, size=n_long) # ~3 min median
    combined = np.concatenate([short, long]).astype(int)
    np.random.shuffle(combined)
    return np.clip(combined, a_min=0, a_max=3600)
```

#### 1d — Fix `ack_time` (rollout time)

The reference `Rollout_Time` (time from first dispatch to unit marking enroute) has a median of only 5 s and a p90 of 85 s. The current gamma(2.0, 30.0) produces a median around 60 s — twelve times too high.

```python
def generate_ack_times(n: int) -> np.ndarray:
    """
    Generate ack_time (seconds from unit dispatched to unit enroute).
    Calibrated: median ~5 s, p90 ~85 s.
    """
    # Most units acknowledge immediately; a minority have delays
    raw = np.random.gamma(shape=1.2, scale=12.0, size=n).astype(int)
    return np.clip(raw, a_min=0, a_max=600)
```

#### 1e — Fix `enroute_time` (transit time) and remove incorrect clipping

The current code clips `enroute_time` to a minimum of 300 s and a maximum of 900 s, which eliminates all the short (< 5 min) and long (> 15 min) travel times that are common in real data. The real transit time has a median of ~256 s with values ranging from 0 to 3 583 s.

```python
def generate_enroute_times(n: int) -> np.ndarray:
    """
    Generate enroute_time (travel time from unit en-route to on-scene, in seconds).
    Calibrated: median ~256 s, p90 ~754 s.
    """
    raw = np.random.gamma(shape=2.5, scale=120.0, size=n).astype(int)
    return np.clip(raw, a_min=0, a_max=3600)
```

---

## 2. Call Volume Is Uniformly Distributed — Should Follow a Diurnal Curve

### Current Behavior

`event_time` values are generated with `np.random.randint(0, date_range)`, resulting in a flat distribution across all hours. Real CAD data shows strong time-of-day variation.

### Reference Data Hourly Distribution (weeks 07–08)

| Time Window | Share of Calls |
|---|---|
| 22:00–06:00 (night) | 19 % |
| 06:00–10:00 (morning) | 17 % |
| 10:00–14:00 (midday) | 22 % |
| 14:00–18:00 (afternoon) | 24 % |
| 18:00–22:00 (evening) | 18 % |

Afternoon and midday peaks are about 25 % more active than the overnight valley.

### Recommendation

Replace the uniform random seconds with stratified hourly sampling driven by a weight array:

```python
# Additional library: none (uses numpy)

# 24-element weight array, index = hour of day (0..23)
# Derived from reference data. Normalize to sum=1 before use.
HOURLY_WEIGHTS = np.array([
    0.030, 0.025, 0.022, 0.020, 0.022, 0.028,  # 00-05
    0.038, 0.048, 0.052, 0.055, 0.058, 0.060,  # 06-11
    0.062, 0.060, 0.058, 0.058, 0.055, 0.052,  # 12-17
    0.050, 0.048, 0.045, 0.042, 0.038, 0.034,  # 18-23
], dtype=float)
HOURLY_WEIGHTS /= HOURLY_WEIGHTS.sum()

def generate_event_times(
    num_records: int,
    start_date_dt: datetime,
    end_date_dt: datetime,
) -> list:
    """
    Generate event_time values following a realistic diurnal call-volume curve.
    """
    total_days = max(1, (end_date_dt - start_date_dt).days)

    # Step 1: distribute records across days uniformly
    day_offsets = np.sort(np.random.randint(0, total_days, size=num_records))

    # Step 2: for each record, pick an hour based on HOURLY_WEIGHTS
    hours = np.random.choice(np.arange(24), size=num_records, p=HOURLY_WEIGHTS)

    # Step 3: pick a random minute:second within that hour
    intra_hour = np.random.randint(0, 3600, size=num_records)

    datetimes = [
        start_date_dt
        + timedelta(days=int(day_offsets[i]))
        + timedelta(hours=int(hours[i]))
        + timedelta(seconds=int(intra_hour[i]))
        for i in range(num_records)
    ]
    return sorted(datetimes)
```

---

## 3. Call Reception Values Do Not Match Real CAD Vocabulary

### Current Behavior

The code uses `["E-911", "PHONE", "OFFICER", "TEXT", "C2C"]` with weights `[0.55, 0.20, 0.10, 0.10, 0.05]`.

### Reference Data (weeks 07–08, n ≈ 3 336)

| Value | Count | Share |
|---|---|---|
| Phone | 1 271 | 38 % |
| E-911 | 1 095 | 33 % |
| OFFICER | 465 | 14 % |
| Radio | 193 | 6 % |
| C2C | 171 | 5 % |
| NOT CAPTURED | 80 | 2 % |
| Text | 27 | < 1 % |
| CAD2CAD | 19 | < 1 % |
| VCIN | 9 | < 1 % |
| Other | 6 | < 1 % |

Key differences: "Phone" (not "PHONE") and "E-911" are nearly equal in frequency; "OFFICER" is 14 %, not 10 %; "Radio" is a meaningful category; "TEXT" is only ~1 %, not 10 %; no "NOT CAPTURED" or "CAD2CAD" categories currently exist.

### Recommendation

```python
RECEPTION_METHODS = ["E-911", "Phone", "OFFICER", "Radio", "C2C",
                     "NOT CAPTURED", "Text", "CAD2CAD"]
RECEPTION_WEIGHTS = [0.33, 0.38, 0.14, 0.06, 0.05, 0.02, 0.01, 0.01]

reception_choices = np.random.choice(
    RECEPTION_METHODS, size=len(df_full), p=RECEPTION_WEIGHTS
)
```

---

## 4. Disposition Values Do Not Match Real CAD Codes

### Current Behavior

The code uses plain-English strings like `"CANCELLED"`, `"UNIT CLEARED"`, `"ARREST MADE"`.

### Reference Data Dispositions

Real CAD systems typically use short alphanumeric codes with a human-readable label. The reference data shows values such as:

- `NR-No Report` (43 % of calls)
- `UNDEFINED` (28 % — calls closed without a specific code, or still-open incidents)
- `RE-Report` (12 %)
- `CI-Citation` (8 %)
- `CAD2CAD` (5 %)
- `FALSE-False Alarm` (1 %)
- `CN-Cancellation` (1 %)
- `ACOR-Animal Control Report` (< 1 %)
- `SUP-Supplement` (< 1 %)
- `RAF-Reassign FD Call` (< 1 %)

### Recommendation

Replace the plain-English list with code-label pairs and agency-appropriate weights:

```python
# (code, label, applicable_agencies)
DISPOSITIONS = [
    ("NR",   "NR-No Report",           ["LAW", "FIRE", "EMS", "RESCUE"]),
    ("RE",   "RE-Report",              ["LAW"]),
    ("CI",   "CI-Citation",            ["LAW"]),
    ("CN",   "CN-Cancellation",        ["LAW", "FIRE", "EMS", "RESCUE"]),
    ("FALSE","FALSE-False Alarm",      ["FIRE", "EMS"]),
    ("ACOR", "ACOR-Animal Control",    ["LAW"]),
    ("SUP",  "SUP-Supplement",         ["LAW", "FIRE", "EMS"]),
    ("RAF",  "RAF-Reassign FD Call",   ["FIRE"]),
    ("UNDEF","UNDEFINED",              ["LAW", "FIRE", "EMS", "RESCUE"]),
]

DISPOSITION_WEIGHTS_BY_AGENCY = {
    "LAW":    [0.40, 0.15, 0.10, 0.04, 0.00, 0.02, 0.01, 0.00, 0.28],
    "FIRE":   [0.45, 0.00, 0.00, 0.05, 0.15, 0.00, 0.01, 0.05, 0.29],
    "EMS":    [0.45, 0.00, 0.00, 0.05, 0.10, 0.00, 0.02, 0.00, 0.38],
    "RESCUE": [0.50, 0.00, 0.00, 0.05, 0.05, 0.00, 0.00, 0.00, 0.40],
}

def assign_disposition_realistic(agency: str) -> str:
    weights = DISPOSITION_WEIGHTS_BY_AGENCY.get(agency, DISPOSITION_WEIGHTS_BY_AGENCY["LAW"])
    chosen = np.random.choice(len(DISPOSITIONS), p=weights)
    return DISPOSITIONS[chosen][1]
```

---

## 5. Personnel Name Generation Should Reflect Realistic Shift Staffing

### Current Behavior

`generate_names(num_names)` generates `num_names` unique Faker names per shift and randomly assigns any of them to every record in that shift. This means every dispatcher or call-taker in the output appears in an essentially random order with no staffing logic.

### Recommendations

#### 5a — Separate call-taker and dispatcher pools

In real 9-1-1 centers, call-takers and dispatchers are different people in separate roles. The current code already tracks them separately, but uses the same `num_names` count for both. The recommended approach is to expose `num_call_takers` and `num_dispatchers` as independent parameters.

```python
def generate_911_data(
    num_records=10000,
    start_date=None,
    end_date=None,
    num_call_takers=5,    # was num_names
    num_dispatchers=3,    # separate pool
    locale=DEFAULT_LOCALE,
    selected_agencies=None,
    agency_probabilities=None,
):
    ...
    call_taker_names  = {key: generate_names(num_call_takers)  for key in ["A", "B", "C", "D"]}
    dispatcher_names  = {key: generate_names(num_dispatchers) for key in ["A", "B", "C", "D"]}
```

#### 5b — Use realistic name format

Real CAD exports use badge/login IDs or "LAST, FIRST" format consistently. The current code already uses `"Last, First"` format, which is correct. However, Faker can generate names where first or last names contain characters that real CAD systems would reject. Constrain to ASCII alphabetic characters only:

```python
import unicodedata

def generate_names(num_names: int = 5) -> list:
    names = []
    attempts = 0
    while len(names) < num_names and attempts < num_names * 10:
        last  = local_fake.last_name()
        first = local_fake.first_name()
        # Normalize to ASCII to avoid accented chars in CAD displays
        last  = unicodedata.normalize("NFKD", last).encode("ascii", "ignore").decode()
        first = unicodedata.normalize("NFKD", first).encode("ascii", "ignore").decode()
        if last and first:
            names.append(f"{last.upper()}, {first.upper()}")
        attempts += 1
    return names
```

#### 5c — Assign a dominant call-taker per record, not a random one

In practice, a call-taker handles a call end-to-end. Rather than picking uniformly from the shift pool, the code could weight assignments so that some staff handle more calls (reflecting workload imbalance, which is realistic and useful for training analysts):

```python
import random

def weighted_name_assignment(shift_names: list) -> str:
    """
    Assign a name from the shift pool with Zipf-like weighting
    so that some staff handle more calls than others.
    """
    n = len(shift_names)
    # Weights decay by 1/rank — first name in list handles more calls
    weights = [1.0 / (i + 1) for i in range(n)]
    total   = sum(weights)
    weights = [w / total for w in weights]
    return random.choices(shift_names, weights=weights, k=1)[0]
```

---

## 6. Add `Incident_Start_Time` as a Distinct Field

### Current Behavior

There is no `Incident_Start_Time` field in the output even though it exists in the reference data and is distinct from `Response_Date` (mapped to `event_time`). In the reference data, `Incident_Start_Time` is the moment the phone was picked up, while `Response_Date` is the CAD system timestamp when the call was formally opened — typically 0–30 seconds later.

### Recommendation

Add `incident_start_time` as `event_time` minus a small pre-call offset:

```python
# incident_start_time = event_time minus 0-30 seconds (call answered but not yet in CAD)
pre_cad_offset = np.random.randint(0, 30, size=len(df_full))

df_full = df_full.with_columns(
    (pl.col("event_time") - pl.duration(seconds=pl.Series("pre_cad_offset", pre_cad_offset)))
    .alias("incident_start_time")
)
```

---

## 7. `on_scene_time` Clipping Is Too Aggressive

### Current Behavior

`on_scene_time` is clipped to a minimum of 300 s and maximum of 7 200 s (2 hours). Real on-scene times can range from under a minute (unit cancelled on arrival) to many hours (major incidents). The current minimum of 300 s eliminates all fast-clear calls.

### Recommendation

Remove the minimum floor and extend the maximum to 86 400 s (24 hours) to allow for overnight incidents:

```python
def generate_on_scene_times(n: int) -> np.ndarray:
    """
    Generate on_scene_time in seconds.
    Calibrated using total_time - transit components from reference data.
    Bimodal: fast-clears (< 5 min) and extended scenes.
    """
    n_fast = int(n * 0.15)
    n_std  = n - n_fast
    fast = np.random.exponential(scale=90, size=n_fast)           # fast clears
    std  = np.random.gamma(shape=2.5, scale=900, size=n_std)      # typical scenes
    combined = np.concatenate([fast, std]).astype(int)
    np.random.shuffle(combined)
    return np.clip(combined, a_min=0, a_max=86400)
```

---

## 8. Problem Selection Uses Uniform Sampling — Should Use Priority-Weighted Sampling

### Current Behavior

`DynamicProvider` assigns problems with equal probability within each agency. This means high-priority problems appear just as often as low-priority ones.

### Reference Data Priority Distribution (weeks 07–08)

For POLICE/LAW calls: Priority 4 is the most common (~ 20 %), Priority 1 is least common (~ 19 %). The distribution is fairly flat in the reference data, but FIRE and EMS skew toward Priority 2.

### Recommendation

Use weighted sampling keyed to empirically plausible priority distributions:

```python
# Weight per priority level [P1, P2, P3, P4, P5]
PRIORITY_WEIGHTS = {
    "LAW":    [0.19, 0.24, 0.21, 0.20, 0.16],
    "FIRE":   [0.14, 0.30, 0.25, 0.20, 0.11],
    "EMS":    [0.18, 0.28, 0.22, 0.15, 0.17],
    "RESCUE": [0.25, 0.25, 0.20, 0.15, 0.15],
}

def assign_problem_weighted(agency: str, fake_instance) -> str:
    problem_list = {
        "LAW": LAW_PROBLEMS, "FIRE": FIRE_PROBLEMS,
        "EMS": EMS_PROBLEMS, "RESCUE": RESCUE_PROBLEMS,
    }.get(agency, LAW_PROBLEMS)

    weights_by_priority = PRIORITY_WEIGHTS.get(agency, [0.2] * 5)

    # Build per-problem weights by mapping each problem's priority to its weight
    problem_weights = []
    for _, p in problem_list:
        idx = max(1, min(p, 5)) - 1
        problem_weights.append(weights_by_priority[idx])

    total = sum(problem_weights)
    problem_weights = [w / total for w in problem_weights]
    chosen = random.choices(problem_list, weights=problem_weights, k=1)[0]
    return chosen[0]
```

---

## 9. Agency Label Does Not Match Reference Data

### Current Behavior

The code uses `"LAW"`. The reference data uses `"POLICE"`.

### Recommendation

Rename `"LAW"` to `"POLICE"` in all agency lists, prefix maps, and priority maps, or make the label configurable per deployment so that agencies adopting the software can match their local CAD vocabulary:

```python
# Option A: rename the constant
agencies = ["POLICE", "EMS", "FIRE", "RESCUE"]
agency_prefix = {"POLICE": "L", "EMS": "M", "FIRE": "F", "RESCUE": "R"}

# Option B: configurable mapping (preferred for a marketed product)
AGENCY_DISPLAY_NAMES = {
    "LAW": "POLICE",   # can be changed to "SHERIFF", "MTP", etc.
    "EMS": "EMS",
    "FIRE": "FIRE",
    "RESCUE": "RESCUE",
}
```

---

## 10. Minor Code-Quality Notes

### 10a — PyInquirer is deprecated

PyInquirer has not been actively maintained and does not work with newer versions of prompt-toolkit. Consider migrating the interactive UI to [**InquirerPy**](https://github.com/kazhala/InquirerPy) (API-compatible drop-in) or [**questionary**](https://github.com/tmbo/questionary).

```
# requirements change:
# remove:  PyInquirer
# add:     InquirerPy>=0.3.4
```

### 10b — `str_address_provider` generates 2 500 addresses but re-uses them

The code generates 2 500 unique addresses and then randomly samples from them for every record. For large datasets (> 2 500 records), the same address will appear repeatedly. This is acceptable but should be documented; or the pool size should be configurable.

### 10c — `call_id` counters restart at 1 per run regardless of date range

When `start_date` is not January 1, the code picks a random starting counter between 1 000 and 100 000. For consecutive data generation runs (e.g., building a full year in weekly batches), the counter will not be contiguous. Consider accepting an optional `starting_counters` parameter so callers can chain runs.

### 10d — Polars `map_elements` is slow for large DataFrames

`assign_problem`, `assign_call_taker`, `assign_dispatcher`, and `assign_disposition` all use `map_elements` (row-by-row Python callbacks). For datasets of 100 000+ records this will be noticeably slow. Replace with vectorised `np.random.choice` calls where possible, as is already done for `reception_choices`.

---

## Summary of Additional Libraries Required

| Recommendation | Library | Notes |
|---|---|---|
| 10a — Replace PyInquirer | `InquirerPy>=0.3.4` | Drop-in replacement, maintained |
| All time distributions | `numpy` (already used) | No change required |
| All time distributions | `scipy.stats` (optional) | Useful for fitting; not required for generation |

No other new dependencies are introduced by these recommendations.

---

## Appendix — Reference Statistics Used in This Review

Derived from `week07.csv` + `week08.csv` (n ≈ 3 336 incidents):

| Metric | Min | P25 | Median | P75 | P90 | P95 | Max | Mean |
|---|---|---|---|---|---|---|---|---|
| Time_To_Queue (s) | 0 | 19 | 49 | 85 | 142 | 191 | 3 480 | 67 |
| Time_To_Dispatch (s) | 0 | 2 | 4 | 201 | 913 | 1 661 | 3 565 | 277 |
| Phone_Time (s) | 0 | 40 | 132 | 233 | 400 | 599 | 3 465 | 187 |
| Rollout_Time (s) | 0 | 0 | 5 | 50 | 85 | 108 | 477 | 28 |
| Transit_Time (s) | 0 | 6 | 256 | 442 | 754 | 1 026 | 3 583 | 332 |
| Total_Call_Time (s) | 10 | 1 160 | 2 842 | 5 921 | 14 629 | 22 289 | 86 142 | 5 575 |
