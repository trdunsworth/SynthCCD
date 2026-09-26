# SynthCCD Hourly Call Counts (Phone Volume) Dataset Schema

**Schema Version:** 1.2
**Generator:** `synth911gen3.generators.phone_metrics.HourlyCallCountGenerator`
**Default Output:** CSV, 10,000 rows, Kansas City, MO

---

## Overview

The Hourly Call Counts dataset simulates call-center phone metrics — one row per hour of the requested date range. It models traffic on each emergency line a PSAP answers (e.g., 9-1-1, 9-9-9, 1-1-2), plus a non-emergency line and outbound calls. Each hour includes received/abandoned counts, answer-time service-level percentages, mean phone durations, and aggregate totals.

Volumes follow a **diurnal call-volume pattern** (peak midday, valley overnight) with weekend multipliers. Per-line fractions and abandonment rates are configurable. Answer times are drawn from lognormal distributions calibrated to NENA standards (90% of 9-1-1 calls answered within 15 seconds). The column set is dynamic — emergency-number columns expand based on the configured country's emergency-number registry.

---

## Column Reference

The column set varies by country because each country may register multiple emergency numbers (e.g., US has `911`; France has `112`, `15`, `17`, `18`, `114`, `191`, `196`). The schema below documents the **US default** (single `911` line). For multi-line countries, the per-number columns repeat with the appropriate prefix.

### Column Name Prefixes

Emergency-number columns use a prefix derived from the digit string:
- `911` → `nine_one_one` (legacy naming for backward compatibility)
- All other numbers → `emergency_<digits>` (e.g., `emergency_999`, `emergency_112`)

### Core Columns

| # | Column | Type | Nullable | Description | Example |
|---|--------|------|----------|-------------|---------|
| 1 | `hour_start` | `datetime64[s]` | No | Start of the hour (midnight-aligned). | `2026-01-15 00:00:00` |
| 2 | `hour_of_day` | `int64` | No | Hour of day (0–23). | `14` |

### Emergency Line: Calls Received

| # | Column | Type | Nullable | Description | Distribution |
|---|--------|------|----------|-------------|-------------|
| 3 | `nine_one_one_calls_received` | `int64` | No | Number of 9-1-1 calls received this hour. | Poisson; base volume × line fraction × diurnal weight × weekend multiplier |

### Non-Emergency & Outbound: Calls Received

| # | Column | Type | Nullable | Description | Distribution |
|---|--------|------|----------|-------------|-------------|
| 4 | `non_emergency_calls_received` | `int64` | No | Non-emergency calls received this hour. Floored to at least `non_emergency_floor_ratio` × total emergency received. | Poisson; base volume × fraction × diurnal weight |
| 5 | `outbound_calls_placed` | `int64` | No | Outbound calls placed by the centre. | Poisson; base volume × fraction × diurnal weight |

### Emergency Line: Calls Abandoned

| # | Column | Type | Nullable | Description | Distribution |
|---|--------|------|----------|-------------|-------------|
| 6 | `nine_one_one_calls_abandoned` | `int64` | No | 9-1-1 calls abandoned (hung up before answer). Night hours (0–5) have a higher abandonment rate. | Binomial(received, rate + night_increment) |

### Non-Emergency: Calls Abandoned

| # | Column | Type | Nullable | Description | Distribution |
|---|--------|------|----------|-------------|-------------|
| 7 | `non_emergency_calls_abandoned` | `int64` | No | Non-emergency calls abandoned. | Binomial(received, abandonment_rate) |

### Emergency Line: Answer-Time Service Levels

Each threshold `T` produces a column showing the percentage of answered calls that were answered within `T` seconds. The percentages are **non-decreasing** in `T` and bounded by the answered pool.

| # | Column | Type | Nullable | Description | Distribution |
|---|--------|------|----------|-------------|-------------|
| 8 | `nine_one_one_answered_10s_pct` | `float64` | No | % of answered 9-1-1 calls answered within 10 seconds. | Sequential binomial allocation from lognormal answer times |
| 9 | `nine_one_one_answered_15s_pct` | `float64` | No | % within 15 seconds (NENA 020.1-2020 target: 90%). | Same |
| 10 | `nine_one_one_answered_20s_pct` | `float64` | No | % within 20 seconds (NENA target: 95%). | Same |
| 11 | `nine_one_one_answered_40s_pct` | `float64` | No | % within 40 seconds. | Same |

### Non-Emergency: Answer-Time Service Levels

| # | Column | Type | Nullable | Description |
|---|--------|------|----------|-------------|
| 12 | `non_emergency_answered_10s_pct` | `float64` | No | % of answered non-emergency calls within 10 seconds. |
| 13 | `non_emergency_answered_15s_pct` | `float64` | No | % within 15 seconds. |
| 14 | `non_emergency_answered_20s_pct` | `float64` | No | % within 20 seconds. |
| 15 | `non_emergency_answered_40s_pct` | `float64` | No | % within 40 seconds. |

### Mean Phone Duration Columns

Per-category mean phone duration (seconds) for the hour. Computed as the arithmetic mean of per-call lognormal draws for answered calls (received minus abandoned). Hours with zero answered calls have `0.0`.

| # | Column | Type | Nullable | Description | Distribution |
|---|--------|------|----------|-------------|-------------|
| 16 | `nine_one_one_mean_duration` | `float64` | No | Mean phone duration for answered 9-1-1 calls. Population mean ~210s. | Sample mean of lognormal draws; mu=5.10, sigma=0.70 |
| 17 | `non_emergency_mean_duration` | `float64` | No | Mean phone duration for answered non-emergency calls. Population mean ~120s. | Sample mean; mu=4.54, sigma=0.70 |
| 18 | `outbound_mean_duration` | `float64` | No | Mean phone duration for outbound calls. Population mean ~60s. | Sample mean; mu=3.85, sigma=0.70 |
| 19 | `call_mean_duration` | `float64` | No | Volume-weighted overall mean phone duration across all categories. | Weighted average of the above three means |

### Aggregate Totals

| # | Column | Type | Nullable | Description |
|---|--------|------|----------|-------------|
| 20 | `total_emergency_calls` | `int64` | No | Sum of all emergency-line received calls. |
| 21 | `total_nonemergency_calls` | `int64` | No | Non-emergency calls received. |
| 22 | `total_calls` | `int64` | No | Total of all received + outbound calls. |

---

## Multi-Line Countries

When the configured country registers multiple emergency numbers (e.g., France with 7 numbers), the per-number columns repeat with the appropriate prefix. For a country with `N` emergency numbers, the dataset has:

- `N` × `calls_received` columns
- `N` × `calls_abandoned` columns
- `N` × `answered_<T>s_pct` columns per threshold
- `N` × `mean_duration` columns

**Example: France** (emergency numbers: 112, 15, 17, 18, 114, 191, 196)

| Prefix | Columns |
|--------|---------|
| `emergency_112` | `calls_received`, `calls_abandoned`, `answered_10s_pct`, `answered_15s_pct`, `answered_20s_pct`, `answered_40s_pct`, `mean_duration` |
| `emergency_15` | (same set) |
| `emergency_17` | (same set) |
| `emergency_18` | (same set) |
| `emergency_114` | (same set) |
| `emergency_191` | (same set) |
| `emergency_196` | (same set) |

---

## Phone Metrics Configuration Parameters

These parameters control the phone-volume simulation. All are configurable via the `phone_metrics` section of the realism YAML.

### Volume Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_hourly_volume` | 2.0 | Minimum base hourly call volume (floor) |
| `nine_one_one_received_fraction` | 0.55 | Fraction of base volume for 9-1-1 received calls |
| `non_emergency_received_fraction` | 0.52 | Fraction of base volume for non-emergency received calls |
| `outbound_calls_fraction` | 0.26 | Fraction of base volume for outbound calls |
| `non_emergency_floor_ratio` | 1.2 | Minimum ratio of non-emergency to emergency received calls per hour |
| `weekend_multiplier` | 1.12 | Multiplier for Friday/Saturday hours |

### Abandonment Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `nine_one_one_abandonment_rate` | 0.07 | Base abandonment rate for 9-1-1 calls (7%) |
| `night_abandonment_increment` | 0.03 | Additional abandonment rate for hours 0–5 |
| `non_emergency_abandonment_rate` | 0.05 | Abandonment rate for non-emergency calls (5%) |
| `max_abandonment_rate` | 0.20 | Hard cap on any line's abandonment rate |

### Answer-Time Parameters (Lognormal)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `nine_one_one_answer_time_mean` | 7.44 | Mean answer time for 9-1-1 (seconds). NENA-calibrated: 90% ≤ 15s, 95% ≤ 20s. |
| `nine_one_one_answer_time_sigma` | 0.79 | Lognormal shape parameter for 9-1-1 answer times |
| `non_emergency_answer_time_mean` | 18.0 | Mean answer time for non-emergency (seconds). Slower due to lower staffing. |
| `non_emergency_answer_time_sigma` | 0.90 | Lognormal shape parameter for non-emergency answer times |
| `answer_time_thresholds` | [10, 15, 20, 40] | Service-level thresholds (seconds) for the `_pct` columns |
| `answer_time_load_sensitivity` | 0.25 | How much answer times degrade during busy hours (0 = no effect) |
| `answer_time_mu_noise_sd` | 0.05 | Per-hour random noise on the answer-time log-scale location |

### Phone Duration Parameters (Lognormal)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `nine_one_one_phone_duration_mu` | 5.10 | Log-scale location for 9-1-1 call duration. Population mean: e^(5.10 + 0.70²/2) ≈ 210s |
| `nine_one_one_phone_duration_sigma` | 0.70 | Log-scale shape for 9-1-1 call duration |
| `non_emergency_phone_duration_mu` | 4.54 | Log-scale location for non-emergency duration. Mean ≈ 120s |
| `non_emergency_phone_duration_sigma` | 0.70 | Log-scale shape for non-emergency duration |
| `outbound_phone_duration_mu` | 3.85 | Log-scale location for outbound duration. Mean ≈ 60s |
| `outbound_phone_duration_sigma` | 0.70 | Log-scale shape for outbound duration |

### Per-Line Overrides

The `lines` sub-dictionary allows per-emergency-number overrides of any of the above parameters. Keyed by the digit string (e.g., `"911"`, `"999"`):

```yaml
lines:
  "911":
    received_fraction: 0.40
    abandonment_rate: 0.06
    answer_time_mean: 8.0
    phone_duration_mu: 5.20
```

---

## Diurnal Call Volume Pattern

The `hourly_weights` array (24 values, one per hour 0–23) controls the shape of call arrivals throughout the day. Values are normalized at generation time. The default pattern reflects typical 9-1-1 call volumes:

| Hour | Weight | Relative Volume |
|------|--------|----------------|
| 0 (midnight) | 0.030 | Low |
| 1 | 0.025 | Low |
| 2 | 0.022 | Lowest |
| 3 | 0.020 | Lowest |
| 4 | 0.022 | Low |
| 5 | 0.028 | Low |
| 6 | 0.038 | Rising |
| 7 | 0.048 | Rising |
| 8 | 0.052 | Moderate |
| 9 | 0.055 | Moderate |
| 10 | 0.058 | Moderate-High |
| 11 | 0.060 | High |
| 12 (noon) | 0.062 | Peak |
| 13 | 0.060 | High |
| 14 | 0.058 | Moderate-High |
| 15 | 0.058 | Moderate-High |
| 16 | 0.055 | Moderate |
| 17 | 0.052 | Moderate |
| 18 | 0.050 | Moderate |
| 19 | 0.048 | Moderate |
| 20 | 0.045 | Moderate-Low |
| 21 | 0.042 | Moderate-Low |
| 22 | 0.038 | Low |
| 23 | 0.034 | Low |

**Peak hours:** 11:00–14:00 (midday)
**Valley hours:** 02:00–05:00 (overnight)

---

## Volume Scaling Logic

The base hourly volume is determined by two mechanisms:

### 1. Row-Count Derived (default)
When `rows` is set and `population` is not:
```
base_hourly_volume = max(min_hourly_volume, total_rows / total_hours)
```

### 2. Population Derived
When `population` is set:
```
emergency_rate = tiered_rate_for_population(population)  # per 1,000 residents/year
emergency_annual = population / 1000 * emergency_rate
base_hourly_volume = max(min_hourly_volume, emergency_annual / 8760 / emergency_fraction)
```

**Population Tier Rates (9-1-1 calls per 1,000 residents/year):**

| Population | Rate |
|------------|------|
| < 100,000 | 400 |
| 100,000–500,000 | 650 |
| 500,000–1,000,000 | 1,000 |
| > 1,000,000 | 1,100 |

---

## Per-Hour Volume Calculation

For each hour in the date range:

```
busy_factor = (hourly_weight / average_weight) × weekend_multiplier

911_received = Poisson(max(1, base_volume × 911_fraction × busy_factor))
non_emergency_received = max(floor, Poisson(max(1, base_volume × ne_fraction × busy_factor)))
outbound_placed = Poisson(max(0.5, base_volume × outbound_fraction × busy_factor))

911_abandoned = Binomial(911_received, min(rate + night_increment, max_rate))
ne_abandoned = Binomial(non_emergency_received, ne_abandonment_rate)
```

Where:
- `floor = ceil(total_emergency_received × non_emergency_floor_ratio)`
- `night_increment` applies only for hours 0–5
- Answer-time percentages are derived from binomial allocations against lognormal CDFs

---

## Sample Row (US, single 9-1-1 line)

```
hour_start:                         2026-01-15 14:00:00
hour_of_day:                        14
nine_one_one_calls_received:        8
non_emergency_calls_received:       7
outbound_calls_placed:              3
nine_one_one_calls_abandoned:       0
non_emergency_calls_abandoned:      0
nine_one_one_answered_10s_pct:      62.5
nine_one_one_answered_15s_pct:      87.5
nine_one_one_answered_20s_pct:     100.0
nine_one_one_answered_40s_pct:     100.0
non_emergency_answered_10s_pct:     14.3
non_emergency_answered_15s_pct:     28.6
non_emergency_answered_20s_pct:     42.9
non_emergency_answered_40s_pct:     85.7
nine_one_one_mean_duration:         198.4
non_emergency_mean_duration:        112.7
outbound_mean_duration:             54.2
call_mean_duration:                 131.5
total_emergency_calls:              8
total_nonemergency_calls:           7
total_calls:                        18
```

---

## Generation Notes

1. **Seed Determinism**: All random draws use a single seeded NumPy RNG (`seed + 101`). Same seed + config = identical output.
2. **Non-Emergency Floor**: Non-emergency received calls are always >= `floor_ratio` × total emergency received, ensuring non-emergency volume exceeds emergency volume (matching real-world patterns).
3. **Night Abandonment**: Hours 0–5 have an incrementally higher abandonment rate (default +3%), reflecting reduced overnight staffing.
4. **Answer-Time Load Sensitivity**: During busy hours (high diurnal weight), answer times degrade proportionally via the `load_sensitivity` parameter. This creates realistic service-level fluctuations.
5. **Per-Hour Duration Noise**: Each hour's mean phone duration includes small random noise (`mu_noise_sd`) so consecutive hours don't show identical durations.
6. **Volume-Weighted Overall Mean**: `call_mean_duration` is the volume-weighted average of all category means, not a simple arithmetic average.
7. **Multi-Line Expansion**: For countries with multiple emergency numbers, the per-number columns are generated independently with per-line overrides, then aggregated into the total columns.
