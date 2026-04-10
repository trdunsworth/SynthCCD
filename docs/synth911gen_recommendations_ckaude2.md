# Synth911Gen — Code Review & Improvement Recommendations

**Prepared for:** Development Team  
**Source file reviewed:** `synth911gen.py`  
**Reference datasets:** `week07.csv`, `week08.csv`  
**Date:** 2026-02-27  
**Revision:** 2 — incorporates additional recommendations from second senior developer review

---

## Executive Summary

The generator produces plausible-looking data but uses distributions that do not match the statistical patterns found in real CAD exports. The most significant gaps are in elapsed-time modeling (times are either too short, too long, or not correlated with call priority), the hourly call-volume curve (calls are uniformly distributed across the day), the call reception / disposition vocabularies (values do not match real-world CAD codes), and personnel name generation (names are formatted but not constrained to a realistic shift headcount). A second reviewer also identified three structural improvements worth adopting: splitting the unit response time into turnout and travel components, modeling dispatch as a parallel timeline to call-taking, and introducing a config-driven design to support the product's customization requirements. Each recommendation below includes the relevant finding from the reference data and a corrected Python example.

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

#### 1a — Unify time parameters into a per-agency, per-priority profile dictionary

A second reviewer recommended consolidating all time parameters into a single `TIME_PROFILES` structure keyed by agency and priority. This is a good architectural pattern that makes the parameters easy to audit, tune, and eventually expose in the planned configuration system (see Recommendation 11). The values below are calibrated to the reference data rather than estimated.

```python
# TIME_PROFILES: each inner tuple is (lognormal_mu, lognormal_sigma, clip_max_seconds)
# Calibrated from week07.csv + week08.csv reference data.

TIME_PROFILES = {
    "LAW": {
        1: {"queue": (3.5, 0.7, 600),  "dispatch": (1.5, 0.7, 60),   "phone": (5.0, 0.6, 1800), "turnout": (0.7, 0.8, 120),  "travel": (5.0, 0.7, 1800)},
        2: {"queue": (3.7, 0.9, 1800), "dispatch": (2.5, 1.0, 600),  "phone": (4.8, 0.7, 1800), "turnout": (1.5, 0.9, 180),  "travel": (5.3, 0.7, 2400)},
        3: {"queue": (3.7, 0.9, 1800), "dispatch": (1.5, 0.7, 60),   "phone": (4.7, 0.7, 1800), "turnout": (1.8, 0.9, 240),  "travel": (5.5, 0.7, 3000)},
        4: {"queue": (3.9, 1.0, 3600), "dispatch": (5.5, 1.2, 3600), "phone": (4.5, 0.8, 1800), "turnout": (2.5, 1.0, 360),  "travel": (5.5, 0.8, 3600)},
        5: {"queue": (4.0, 1.1, 3600), "dispatch": (5.0, 1.3, 7200), "phone": (4.2, 0.9, 1800), "turnout": (3.0, 1.0, 600),  "travel": (5.8, 0.8, 3600)},
    },
    "EMS": {
        1: {"queue": (3.5, 0.7, 600),  "dispatch": (1.5, 0.6, 30),   "phone": (5.2, 0.6, 2400), "turnout": (0.7, 0.7, 90),   "travel": (5.0, 0.7, 1800)},
        2: {"queue": (3.6, 0.8, 900),  "dispatch": (2.0, 0.8, 300),  "phone": (5.0, 0.7, 2400), "turnout": (1.2, 0.8, 150),  "travel": (5.2, 0.7, 2400)},
        3: {"queue": (3.7, 0.9, 1800), "dispatch": (2.5, 1.0, 600),  "phone": (4.8, 0.7, 1800), "turnout": (1.8, 0.9, 240),  "travel": (5.5, 0.7, 3000)},
        4: {"queue": (3.9, 1.0, 3600), "dispatch": (4.5, 1.2, 3600), "phone": (4.5, 0.8, 1800), "turnout": (2.5, 1.0, 360),  "travel": (5.5, 0.8, 3600)},
        5: {"queue": (4.0, 1.1, 3600), "dispatch": (5.0, 1.3, 7200), "phone": (4.0, 1.0, 1800), "turnout": (3.0, 1.0, 600),  "travel": (5.8, 0.8, 3600)},
    },
    "FIRE": {
        1: {"queue": (3.5, 0.7, 600),  "dispatch": (1.5, 0.6, 30),   "phone": (5.0, 0.6, 1800), "turnout": (2.0, 0.6, 180),  "travel": (4.8, 0.7, 1800)},
        2: {"queue": (3.6, 0.8, 900),  "dispatch": (2.0, 0.8, 300),  "phone": (4.8, 0.7, 1800), "turnout": (2.2, 0.7, 240),  "travel": (5.0, 0.7, 2400)},
        3: {"queue": (3.7, 0.9, 1800), "dispatch": (2.5, 1.0, 600),  "phone": (4.6, 0.7, 1800), "turnout": (2.5, 0.8, 300),  "travel": (5.3, 0.7, 3000)},
        4: {"queue": (3.9, 1.0, 3600), "dispatch": (4.5, 1.2, 3600), "phone": (4.3, 0.8, 1800), "turnout": (3.0, 0.9, 420),  "travel": (5.5, 0.8, 3600)},
        5: {"queue": (4.0, 1.1, 3600), "dispatch": (5.0, 1.3, 7200), "phone": (4.0, 1.0, 1800), "turnout": (3.5, 1.0, 600),  "travel": (5.8, 0.8, 3600)},
    },
    "RESCUE": {
        1: {"queue": (3.5, 0.7, 600),  "dispatch": (1.5, 0.6, 30),   "phone": (5.2, 0.6, 2400), "turnout": (2.5, 0.7, 300),  "travel": (5.5, 0.8, 3600)},
        2: {"queue": (3.7, 0.9, 1800), "dispatch": (2.5, 1.0, 600),  "phone": (5.0, 0.7, 2400), "turnout": (3.0, 0.8, 420),  "travel": (5.8, 0.8, 3600)},
        3: {"queue": (3.9, 1.0, 3600), "dispatch": (3.5, 1.1, 1800), "phone": (4.8, 0.7, 1800), "turnout": (3.5, 0.9, 600),  "travel": (6.0, 0.8, 3600)},
        4: {"queue": (4.0, 1.1, 3600), "dispatch": (4.5, 1.2, 3600), "phone": (4.5, 0.8, 1800), "turnout": (3.8, 1.0, 720),  "travel": (6.0, 0.9, 3600)},
        5: {"queue": (4.2, 1.2, 7200), "dispatch": (5.0, 1.3, 7200), "phone": (4.0, 1.0, 1800), "turnout": (4.0, 1.0, 900),  "travel": (6.2, 0.9, 3600)},
    },
}

def sample_time(profile_tuple: tuple) -> int:
    """Draw one sample from a lognormal distribution defined by (mu, sigma, clip_max)."""
    mu, sigma, cap = profile_tuple
    return int(np.clip(int(np.random.lognormal(mu, sigma)), 0, cap))
```

#### 1b — Make all interval times priority- and agency-dependent

Using the `TIME_PROFILES` table, each interval (queue, dispatch, phone) is generated with a single helper. This replaces the five separate, uncorrelated generation calls in the current code.

```python
def generate_times_from_profile(
    metric: str,
    agencies: np.ndarray,
    priorities: np.ndarray,
) -> np.ndarray:
    """
    Generate an array of time values for `metric` conditioned on agency and priority.
    `metric` must be a key in TIME_PROFILES[agency][priority].
    """
    result = np.zeros(len(priorities), dtype=int)
    for i, (agency, priority) in enumerate(zip(agencies, priorities)):
        profile = TIME_PROFILES.get(agency, TIME_PROFILES["LAW"])
        params  = profile.get(int(priority), profile[3])  # default to P3
        result[i] = sample_time(params[metric])
    return result

# Usage:
# queue_time    = generate_times_from_profile("queue",    agencies, priorities)
# dispatch_time = generate_times_from_profile("dispatch", agencies, priorities)
# phone_time    = generate_times_from_profile("phone",    agencies, priorities)
```

#### 1c — Split `enroute_time` into `turnout_time` + `travel_time`

The current code uses a single `enroute_time` clipped between 300 and 900 s, which eliminates both sub-5-minute and over-15-minute responses that are common in real data. A second reviewer also correctly noted that this interval consists of two physically distinct components: **turnout time** (from dispatch notification to the unit leaving the station) and **travel time** (wheels-rolling to on-scene). Separating them produces more realistic data and directly supports NFPA 1710/1221 compliance analysis that 9-1-1 centers routinely perform.

Reference data calibration: rollout/turnout median ~5 s (p90 = 85 s); transit/travel median ~256 s (p90 = 754 s).

```python
def generate_unit_response_times(
    agencies: np.ndarray,
    priorities: np.ndarray,
) -> tuple:
    """
    Returns (turnout_time, travel_time, enroute_time) as integer arrays.

    turnout_time: dispatch notification → unit en-route. Median ~5 s.
    travel_time:  unit en-route → unit on-scene. Median ~256 s.
    enroute_time: sum of the two components (replaces the current single field).
    """
    turnout = generate_times_from_profile("turnout", agencies, priorities)
    travel  = generate_times_from_profile("travel",  agencies, priorities)
    return turnout, travel, turnout + travel
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

A second reviewer noted that call arrivals are correctly modeled as a Poisson process with a time-varying rate. The implementation below uses `np.random.choice` over hours weighted by `HOURLY_WEIGHTS`, which produces the correct marginal distribution and is equivalent to sampling from a non-homogeneous Poisson process with hourly-constant rates — without requiring the `simpy` simulation library.

### Recommendation

```python
# 24-element weight array, index = hour of day (0..23).
# Derived from reference data. Normalized to sum=1.
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
    total_days  = max(1, (end_date_dt - start_date_dt).days)
    day_offsets = np.sort(np.random.randint(0, total_days, size=num_records))
    hours       = np.random.choice(np.arange(24), size=num_records, p=HOURLY_WEIGHTS)
    intra_hour  = np.random.randint(0, 3600, size=num_records)

    return sorted([
        start_date_dt
        + timedelta(days=int(day_offsets[i]))
        + timedelta(hours=int(hours[i]))
        + timedelta(seconds=int(intra_hour[i]))
        for i in range(num_records)
    ])
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

Key differences: "Phone" (not "PHONE") and "E-911" are nearly equal in frequency; "OFFICER" is 14 %, not 10 %; "Radio" is a meaningful category that currently does not exist; "TEXT" is only ~1 %, not 10 %; "NOT CAPTURED" and "CAD2CAD" are absent.

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

## 4. Dispatch and Call-Taking Are Parallel Timelines — Not Sequential

### Current Behavior

The code models `time_call_dispatched` as `time_call_queued + dispatch_time`, implying dispatch cannot begin until the call is fully processed. In reality, for high-priority incidents the CAD system and dispatcher begin the dispatch workflow as soon as enough information is available — often while the call-taker is still on the phone. For lower-priority calls, dispatch may be intentionally deferred until after the call ends.

This recommendation originates from the second reviewer and reflects genuine CAD operational behavior.

### Recommendation

Introduce a `DISPATCH_INIT_FRACTION` that controls how far through the `phone_time` window the dispatch process can begin. For Priority 1 calls, dispatch can start as early as 5–20 % into the call. For Priority 4–5 calls, dispatch typically starts after the call ends (fraction ≥ 1.0).

```python
# (min_fraction, max_fraction) of phone_time elapsed before dispatch is initiated.
# Fractions < 1.0 mean dispatch starts while the caller is still on the phone.
DISPATCH_INIT_FRACTION = {
    1: (0.05, 0.20),   # dispatch very early — life-threatening calls
    2: (0.20, 0.50),
    3: (0.40, 0.80),
    4: (0.90, 1.10),   # dispatch after call ends
    5: (1.00, 1.30),   # deliberately deferred
}

def compute_dispatch_ready_offsets(
    phone_times: np.ndarray,
    priorities: np.ndarray,
) -> np.ndarray:
    """
    Returns seconds from event_time when dispatch can begin for each record,
    reflecting that high-priority calls are dispatched mid-call.
    """
    offsets = np.zeros(len(priorities), dtype=int)
    for i, (pt, p) in enumerate(zip(phone_times, priorities)):
        lo, hi    = DISPATCH_INIT_FRACTION.get(int(p), (0.5, 1.0))
        fraction  = np.random.uniform(lo, hi)
        offsets[i] = int(pt * fraction)
    return offsets

# Replace the current:
#   time_call_dispatched = time_call_queued + dispatch_time
# with:
#   dispatch_ready = compute_dispatch_ready_offsets(phone_time, priority_number)
#   time_call_dispatched = event_time + dispatch_ready + dispatch_time
```

---

## 5. Personnel Name Generation Should Reflect Realistic Shift Staffing

#### 5a — Separate call-taker and dispatcher pools

In real 9-1-1 centers, call-takers and dispatchers are different roles. Expose `num_call_takers` and `num_dispatchers` as independent parameters rather than sharing a single `num_names` count.

```python
def generate_911_data(
    num_records=10000,
    start_date=None,
    end_date=None,
    num_call_takers=5,    # was num_names
    num_dispatchers=3,
    locale=DEFAULT_LOCALE,
    selected_agencies=None,
    agency_probabilities=None,
):
    ...
    call_taker_names = {key: generate_names(num_call_takers) for key in ["A", "B", "C", "D"]}
    dispatcher_names = {key: generate_names(num_dispatchers) for key in ["A", "B", "C", "D"]}
```

#### 5b — Normalize names to ASCII

Faker can generate accented characters that real CAD systems reject or display incorrectly.

```python
import unicodedata

def generate_names(num_names: int = 5) -> list:
    names, attempts = [], 0
    while len(names) < num_names and attempts < num_names * 10:
        last  = unicodedata.normalize("NFKD", local_fake.last_name()).encode("ascii", "ignore").decode()
        first = unicodedata.normalize("NFKD", local_fake.first_name()).encode("ascii", "ignore").decode()
        if last and first:
            names.append(f"{last.upper()}, {first.upper()}")
        attempts += 1
    return names
```

#### 5c — Apply Zipf-like workload weighting to name assignment

Uniform random assignment produces an unrealistically even distribution. In practice, some staff handle significantly more calls due to seniority or specialization.

```python
def weighted_name_assignment(shift_names: list) -> str:
    """Assign a name with Zipf-like weighting — first name handles the most calls."""
    n       = len(shift_names)
    weights = [1.0 / (i + 1) for i in range(n)]
    total   = sum(weights)
    weights = [w / total for w in weights]
    return random.choices(shift_names, weights=weights, k=1)[0]
```

#### 5d — Apply a late-shift dispatch time penalty

Reduced late-shift staffing increases dispatch times during that portion of the shift. This is layered on top of the priority-based dispatch times from Recommendation 1b.

```python
SHIFT_PART_MULTIPLIERS = {"EARLY": 1.0, "MIDS": 1.0, "LATE": 1.15}

def apply_shift_penalty(dispatch_times: np.ndarray, shift_parts: np.ndarray) -> np.ndarray:
    result = dispatch_times.copy().astype(float)
    for part, multiplier in SHIFT_PART_MULTIPLIERS.items():
        result[shift_parts == part] *= multiplier
    return result.astype(int)
```

---

## 6. Add `Incident_Start_Time` as a Distinct Field

### Current Behavior

There is no `Incident_Start_Time` field in the output. In the reference data it is distinct from `Response_Date` (`event_time`): `Incident_Start_Time` is when the call-taker picked up the phone, while `Response_Date` is when the call was formally entered into CAD — typically 0–30 seconds later. Aliasing `event_time` directly to `incident_start_time` (as suggested in the second review) is incorrect; the two fields must differ.

### Recommendation

```python
pre_cad_offset = np.random.randint(0, 30, size=len(df_full))

df_full = df_full.with_columns(
    (pl.col("event_time") - pl.duration(seconds=pl.Series("pre_cad_offset", pre_cad_offset)))
    .alias("incident_start_time")
)
```

---

## 7. `on_scene_time` Clipping Is Too Aggressive

### Current Behavior

`on_scene_time` is clipped to a minimum of 300 s and a maximum of 7 200 s. The 300 s floor eliminates all fast-clear calls (unit cancelled on arrival), and the 7 200 s ceiling eliminates major incidents that run overnight.

### Recommendation

```python
def generate_on_scene_times(n: int) -> np.ndarray:
    """
    Bimodal: fast-clears (< 5 min) and extended scenes.
    No minimum floor; maximum extended to 86 400 s (24 h).
    """
    n_fast   = int(n * 0.15)
    fast     = np.random.exponential(scale=90,  size=n_fast)
    std      = np.random.gamma(shape=2.5, scale=900, size=n - n_fast)
    combined = np.concatenate([fast, std]).astype(int)
    np.random.shuffle(combined)
    return np.clip(combined, a_min=0, a_max=86400)
```

---

## 8. Problem Selection Uses Uniform Sampling — Should Use Priority-Weighted Sampling

### Current Behavior

`DynamicProvider` assigns problems with equal probability, so a `CARDIAC ARREST ALS` (Priority 1) appears as often as a `ROUTINE TRANSPORT` (Priority 5).

### Reference Data Priority Distribution

For POLICE calls the distribution is fairly flat (Priority 4 ~20 %, Priority 1 ~19 %). FIRE and EMS skew toward Priority 2.

### Recommendation

```python
PRIORITY_WEIGHTS = {
    "LAW":    [0.19, 0.24, 0.21, 0.20, 0.16],
    "FIRE":   [0.14, 0.30, 0.25, 0.20, 0.11],
    "EMS":    [0.18, 0.28, 0.22, 0.15, 0.17],
    "RESCUE": [0.25, 0.25, 0.20, 0.15, 0.15],
}

def assign_problem_weighted(agency: str) -> str:
    problem_list    = {"LAW": LAW_PROBLEMS, "FIRE": FIRE_PROBLEMS,
                       "EMS": EMS_PROBLEMS, "RESCUE": RESCUE_PROBLEMS}.get(agency, LAW_PROBLEMS)
    weights_by_pri  = PRIORITY_WEIGHTS.get(agency, [0.2] * 5)
    problem_weights = [weights_by_pri[max(1, min(p, 5)) - 1] for _, p in problem_list]
    total           = sum(problem_weights)
    problem_weights = [w / total for w in problem_weights]
    return random.choices(problem_list, weights=problem_weights, k=1)[0][0]
```

---

## 9. Disposition Values Do Not Match Real CAD Codes

### Current Behavior

The code uses plain-English strings (`"CANCELLED"`, `"UNIT CLEARED"`, `"ARREST MADE"`). Real CAD systems use short alphanumeric codes with human-readable labels. The second reviewer's pattern of keying dispositions to agency is the right architecture, but their suggested arrest rate of 35 % for Priority 1 LAW is not supported by the reference data — `NR-No Report` dominates at 43 % across all agencies.

### Reference Data Dispositions (weeks 07–08)

| Code | Label | Share |
|---|---|---|
| NR | NR-No Report | 43 % |
| (blank) | UNDEFINED | 28 % |
| RE | RE-Report | 12 % |
| CI | CI-Citation | 8 % |
| CAD2CAD | CAD2CAD | 5 % |
| FALSE | FALSE-False Alarm | 1 % |
| CN | CN-Cancellation | 1 % |
| ACOR | ACOR-Animal Control Report | < 1 % |

### Recommendation

```python
DISPOSITIONS = [
    ("NR",    "NR-No Report"),
    ("RE",    "RE-Report"),
    ("CI",    "CI-Citation"),
    ("CN",    "CN-Cancellation"),
    ("FALSE", "FALSE-False Alarm"),
    ("ACOR",  "ACOR-Animal Control"),
    ("SUP",   "SUP-Supplement"),
    ("RAF",   "RAF-Reassign FD Call"),
    ("UNDEF", "UNDEFINED"),
]

# Weights indexed to DISPOSITIONS list, per agency — calibrated to reference data
DISPOSITION_WEIGHTS_BY_AGENCY = {
    "LAW":    [0.40, 0.15, 0.10, 0.04, 0.00, 0.02, 0.01, 0.00, 0.28],
    "FIRE":   [0.45, 0.00, 0.00, 0.05, 0.15, 0.00, 0.01, 0.05, 0.29],
    "EMS":    [0.45, 0.00, 0.00, 0.05, 0.10, 0.00, 0.02, 0.00, 0.38],
    "RESCUE": [0.50, 0.00, 0.00, 0.05, 0.05, 0.00, 0.00, 0.00, 0.40],
}

def assign_disposition_realistic(agency: str) -> str:
    weights = DISPOSITION_WEIGHTS_BY_AGENCY.get(agency, DISPOSITION_WEIGHTS_BY_AGENCY["LAW"])
    chosen  = np.random.choice(len(DISPOSITIONS), p=weights)
    return DISPOSITIONS[chosen][1]
```

---

## 10. Agency Label Does Not Match Reference Data

### Current Behavior

The code uses `"LAW"`. The reference data uses `"POLICE"`.

### Recommendation

Rename `"LAW"` to `"POLICE"` throughout, or — preferred for a marketed product — make the label configurable so agencies can match their local CAD vocabulary:

```python
AGENCY_DISPLAY_NAMES = {
    "LAW":    "POLICE",   # alternatives: "SHERIFF", "MTP", "STATE POLICE"
    "EMS":    "EMS",
    "FIRE":   "FIRE",
    "RESCUE": "RESCUE",
}
```

---

## 11. Introduce a Config-Driven Design

### Recommendation (from second reviewer — strongly endorsed)

The second reviewer recommended externalizing generator parameters to a YAML configuration file. This is particularly important for a marketed product where each 9-1-1 center will have its own agency names, shift structures, priority scales, and call volume profiles. Hard-coded constants will require source changes for every customer deployment. A config file is also a natural home for `TIME_PROFILES`, `HOURLY_WEIGHTS`, `PRIORITY_WEIGHTS`, and `AGENCY_DISPLAY_NAMES`.

```python
# Additional library: pyyaml

import yaml

def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r") as fh:
        return yaml.safe_load(fh)
```

Example `config.yaml`:

```yaml
agency_display_names:
  LAW: POLICE        # change to SHERIFF, MTP, etc. per deployment
  EMS: EMS
  FIRE: FIRE
  RESCUE: RESCUE

agency_probabilities:
  LAW: 0.72
  EMS: 0.15
  FIRE: 0.10
  RESCUE: 0.03

num_shifts: 4
shift_labels: [A, B, C, D]
num_call_takers_per_shift: 5
num_dispatchers_per_shift: 3

geographic_zone: SUBURBAN    # URBAN | SUBURBAN | RURAL

hourly_weights:
  - 0.030   # 00:00
  - 0.025   # 01:00
  # ... 24 values total
```

The `geographic_zone` key (also suggested by the second reviewer) can scale the `travel` component of `TIME_PROFILES` without duplicating the entire table:

```python
ZONE_TRAVEL_MULTIPLIERS = {
    "URBAN":    0.6,
    "SUBURBAN": 1.0,
    "RURAL":    1.8,
}

def apply_zone_multiplier(travel_times: np.ndarray, zone: str) -> np.ndarray:
    multiplier = ZONE_TRAVEL_MULTIPLIERS.get(zone, 1.0)
    return (travel_times * multiplier).astype(int)
```

---

## 12. Minor Code-Quality Notes

### 12a — PyInquirer is deprecated

PyInquirer has not been actively maintained and does not work with newer versions of prompt-toolkit. Migrate to [**InquirerPy**](https://github.com/kazhala/InquirerPy) (API-compatible drop-in) or [**questionary**](https://github.com/tmbo/questionary).

```
# requirements change:
# remove:  PyInquirer
# add:     InquirerPy>=0.3.4
```

### 12b — Address pool re-use

The code generates 2 500 unique addresses and samples from them for every record. For datasets larger than 2 500 records, the same address will recur. This is acceptable but should be documented, and the pool size should be a configurable parameter.

### 12c — `call_id` counters do not chain across runs

When `start_date` is not January 1, the code picks a random starting counter between 1 000 and 100 000. For consecutive generation runs (e.g., building a full year in weekly batches), counters will not be contiguous. Accept an optional `starting_counters` dict so callers can chain runs:

```python
def generate_911_data(
    ...,
    starting_counters: dict | None = None,
):
    agency_counters = starting_counters or {
        "L": get_start_number(), "M": get_start_number(),
        "F": get_start_number(), "R": get_start_number(),
    }
```

### 12d — `map_elements` performance

`assign_problem`, `assign_call_taker`, `assign_dispatcher`, and `assign_disposition` all use row-by-row Python callbacks via `map_elements`. For datasets of 100 000+ records this is noticeably slow. Replace with vectorised `np.random.choice` calls where possible, as is already done for `reception_choices`.

---

## Summary of Additional Libraries Required

| Recommendation | Library | Notes |
|---|---|---|
| 11 — Config-driven design | `pyyaml>=6.0` | New dependency |
| 12a — Replace PyInquirer | `InquirerPy>=0.3.4` | Drop-in replacement, actively maintained |
| All time distributions | `numpy` | Already a dependency — no change |
| Distribution fitting (optional) | `scipy>=1.11` | Useful for re-fitting params to new reference data; not required at runtime |

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
