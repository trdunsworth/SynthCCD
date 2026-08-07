# synth911gen3 Realism Guide

A companion to the [User Guide](USERSGUIDE.md) describing how the generator produces
realistic CAD and hourly phone-center statistics, the YAML realism configuration
file, and the default distribution parameters baked in at build time.

- User-facing interface, CLI reference, schema, and quick start: see `USERSGUIDE.md`
- Default statistical distributions and how they are tuned: this document

---

## Realism Configuration

For users who want to emulate a specific 9-1-1 center with known operational
characteristics, synth911gen3 supports a **YAML realism configuration file** that
overrides all default statistical distributions.

### Using a Config File

```bash
# Generate with custom realism config
uv run synth911gen3 generate --config path/to/realism_config.yaml --rows 50000
```

### Config File Structure

An example config file is provided at `config/example_realism.yaml`. Copy and modify
it to match your center's data:

```yaml
# Agency distribution (must sum to 1.0)
agency_weights:
  LAW: 0.52
  FIRE: 0.20
  EMS: 0.28

# Agency display names (used in output)
agency_names:
  LAW: "POLICE"
  FIRE: "FIRE"
  EMS: "EMS"

# Priority weights per agency (each agency must sum to 1.0)
# Priority 1 = highest, 5 = lowest
priority_weights:
  LAW:
    1: 0.12
    2: 0.18
    3: 0.28
    4: 0.26
    5: 0.16
  FIRE:
    1: 0.18
    2: 0.24
    3: 0.24
    4: 0.20
    5: 0.14
  EMS:
    1: 0.16
    2: 0.26
    3: 0.28
    4: 0.18
    5: 0.12

# Problem natures per agency and priority (weights must sum to 1.0 per priority pool)
# The problem is drawn only from the pool matching the incident's selected priority
problem_profiles:
  LAW:
    1:
      - ["Shots Fired", 0.20]
      - ["Burglary In Progress", 0.15]
      # ... more entries
    2:
      - ["Domestic Disturbance", 0.18]
      # ... more entries
  FIRE:
    1:
      - ["Structure Fire", 0.30]
      # ... more entries
  EMS:
    3:
      - ["Fall Injury", 0.18]
      # ... more entries

# Call reception methods (must sum to 1.0)
call_reception_weights:
  "E-911": 0.33
  "Phone": 0.38
  "OFFICER": 0.14
  "Radio": 0.06
  "C2C": 0.05
  "NOT CAPTURED": 0.02
  "Text": 0.01
  "CAD2CAD": 0.01

# Disposition codes per agency (must sum to 1.0 per agency)
disposition_profiles:
  LAW:
    - ["NR-No Report", 0.40]
    - ["RE-Report", 0.15]
    # ... more entries
  FIRE:
    - ["NR-No Report", 0.45]
    - ["UNDEFINED", 0.29]
    # ... more entries
  EMS:
    - ["NR-No Report", 0.45]
    - ["UNDEFINED", 0.38]
    # ... more entries

# Time profiles per agency and priority (mean seconds for lognormal distribution)
time_profiles:
  LAW:
    1:
      interview_mean: 12
      dispatch_mean: 4
      turnout_mean: 10
      travel_mean: 220
      scene_mean: 1500
      closeout_mean: 240
      phone_mean: 170
    # ... priorities 2-5
  FIRE:
    # ... all 5 priorities
  EMS:
    # ... all 5 priorities

# Fraction of the phone window that must elapse before dispatch can begin,
# per priority (lo, hi). Fractions < 1.0 dispatch while the caller is still on
# the phone (parallel dispatch); >= 1.0 defer dispatch until after the call ends.
dispatch_init_fraction:
  1: [0.05, 0.20]
  2: [0.20, 0.50]
  3: [0.40, 0.80]
  4: [0.90, 1.10]
  5: [1.00, 1.30]

# Phone-metric factors for hourly call counts (volume fractions of base hourly
# volume, abandonment rates, weekend multiplier)
phone_metrics:
  min_hourly_volume: 2.0
  nine_one_one_received_fraction: 0.48
  non_emergency_received_fraction: 0.58
  outbound_calls_fraction: 0.26
  nine_one_one_abandonment_rate: 0.02
  night_abandonment_increment: 0.03
  non_emergency_abandonment_rate: 0.05
  max_abandonment_rate: 0.12
  weekend_multiplier: 1.12

# Diurnal call volume pattern (24 values for hours 0-23, will be normalized)
hourly_weights:
  - 0.030
  - 0.025
  # ... 24 values total

# Shift structure: crew rotation pattern plus the shifts on the clock.
# rotation: one crew-group id per calendar day, repeating. Day 1 is the weekday
#   given by cycle_start_weekday (0 = Monday).
# shifts: each entry lists a shift name, a human label, its on-duty hours, its
#   crew rotation group, and staffing. Omit calltakers/dispatchers to fall back
#   to the global --calltaker-pool-size / --dispatcher-pool-size split.
shift_config:
  name: "2x12h-4shift-14day"
  cycle_start_weekday: 0
  rotation: [1, 1, 2, 2, 1, 1, 1, 2, 2, 1, 1, 2, 2, 2]
  shifts:
    - name: A
      label: DAY
      start_hour: 6
      start_minute: 0
      end_hour: 18
      end_minute: 0
      rotation: 1
      calltakers: 3
      dispatchers: 2
    - name: B
      label: DAY
      start_hour: 6
      start_minute: 0
      end_hour: 18
      end_minute: 0
      rotation: 2
      calltakers: 3
      dispatchers: 2
    - name: C
      label: NIGHT
      start_hour: 18
      start_minute: 0
      end_hour: 6
      end_minute: 0
      rotation: 1
      calltakers: 3
      dispatchers: 2
    - name: D
      label: NIGHT
      start_hour: 18
      start_minute: 0
      end_hour: 6
      end_minute: 0
      rotation: 2
      calltakers: 3
      dispatchers: 2
```

### Customizable Parameters

| Section | Description | Validation |
|---------|-------------|------------|
| `agency_weights` | Relative frequency of LAW/FIRE/EMS incidents | Must sum to 1.0 |
| `agency_names` | Display names for agencies in output | Must cover all agencies in `agency_weights` |
| `priority_weights` | Priority 1-5 distribution per agency | Each agency sums to 1.0 |
| `problem_profiles` | Call type distribution per agency | Each agency sums to 1.0 |
| `call_reception_weights` | How calls are received (911, Phone, etc.) | Must sum to 1.0 |
| `disposition_profiles` | Outcome codes per agency | Each agency sums to 1.0 |
| `time_profiles` | Mean seconds for 7 time intervals per agency/priority | All 7 intervals required per priority |
| `dispatch_init_fraction` | (lo, hi) fraction of the phone window before dispatch can begin, per priority | All 5 priorities, lo >= 0 and hi >= lo |
| `phone_metrics` | Volume fractions, abandonment rates, and weekend multiplier for hourly call counts | All required keys; max_abandonment_rate in [0, 1] |
| `hourly_weights` | 24-hour call volume pattern | 24 values, auto-normalized |
| `shift_config` | Crew rotation pattern and per-shift hours/rotation/staffing | Unique shift names, every rotation group covers all 24 hours |

> Note: the config key is `problem_profiles` (not `problem_problems`).

### Time Profile Intervals

Each agency/priority combination requires these 7 intervals (mean seconds):

| Interval | Description |
|----------|-------------|
| `interview_mean` | Caller questioning duration |
| `dispatch_mean` | Queue to unit assignment |
| `turnout_mean` | Station to wheels rolling |
| `travel_mean` | Wheels rolling to on-scene |
| `scene_mean` | On-scene duration |
| `closeout_mean` | Scene clear to incident close |
| `phone_mean` | Total call duration |

Dispatch runs on a parallel timeline to call-taking. `dispatch_init_fraction` controls
how far through the phone window dispatch may begin, per priority: values below 1.0
mean a unit can be dispatched while the caller is still on the phone (high-priority
calls), and values of 1.0+ defer dispatch until after the call ends (low-priority
calls).

### Shift Structures

Every incident is tagged with the shift on duty at its call time (`shift`,
`shift_label`, and `shift_group` columns). The default is a **2x12h center with
four shifts and a 14-day crew rotation**; `shift_preset` selects a built-in
structure, and `shift_config` in the realism YAML defines a fully custom one.
When `shift_preset` is omitted, the realism config's `shift_config` is used.

Built-in presets (selectable via `--shift-preset`):

| Preset | Structure |
|--------|-----------|
| `2x12h-4shift-14day` (default) | Shifts A/B (day 06:00-18:00) and C/D (night 18:00-06:00) on a repeating 14-day rotation `1,1,2,2,1,1,1,2,2,1,1,2,2,2` starting Monday; group 1 = A day + C night, group 2 = B day + D night |
| `2x12h-2shift` | Single day and single night shift, no crew cycling |
| `3x8h-3shift` | Morning (06-14), Swing (14-22), Midnight (22-06) |
| `4x10h-4shift` | Day (06-16), Coverage (10-21), Evening (16-02), Night (21-07) |

Each shift in the YAML defines:

| Key | Description |
|-----|-------------|
| `name` | Short identifier, written to the `shift` column (must be unique) |
| `label` | Human label (e.g., DAY, NIGHT), written to `shift_label` |
| `start_hour` / `start_minute` | On-duty start time (24-hour clock) |
| `end_hour` / `end_minute` | On-duty end time; an end before the start means the shift crosses midnight |
| `rotation` | Crew-group id; the day's active group is `rotation[days_since_cycle_start % len(rotation)]` |
| `calltakers` / `dispatchers` | Staffed positions on this shift; omit to split the global pool totals |

`rotation` is a repeating list of crew-group ids, one per calendar day, starting
on `cycle_start_weekday` (0 = Monday). Validation requires unique shift names,
at least one shift per rotation group, and that each rotation group's shifts
together cover all 24 hours. Overnight shifts and shifts with overlapping hours
(used to model peak coverage) are supported; when multiple shifts in the active
group are on duty, the one that started most recently is assigned.

Example custom structure (2x12h, one day shift and one night shift, no cycling):

```yaml
shift_config:
  name: "my-center"
  cycle_start_weekday: 0
  rotation: [1]
  shifts:
    - name: A
      label: DAY
      start_hour: 6
      end_hour: 18
      rotation: 1
      calltakers: 4
      dispatchers: 3
    - name: B
      label: NIGHT
      start_hour: 18
      end_hour: 6
      rotation: 1
      calltakers: 3
      dispatchers: 2
```

### Creating a Config from Your Data

1. **Analyze your CAD data** to compute:
   - Agency call volumes
   - Priority distribution per agency
   - Problem type frequencies
   - Average times for each interval by priority
   - Hourly call volume pattern
   - Disposition code frequencies
   - Call reception method breakdown

2. **Copy `config/example_realism.yaml`** and replace values with your computed statistics

3. **Validate** by running a small test generation:
   ```bash
   uv run synth911gen3 generate --config your_config.yaml --rows 1000 --format pandas
   ```

4. **Iterate** until generated statistics match your real data

### Python API Usage

```python
from synth911gen3 import Synth911Application, RealismConfig
from synth911gen3.addresses import OpenStreetMapAddressProvider
from synth911gen3.config import GenerationRequest, OutputFormat, DatasetKind
from pathlib import Path

# Load custom realism config
realism = RealismConfig.from_yaml(Path("config/my_center.yaml"))

# Or create programmatically
realism = RealismConfig(
    agency_weights={"LAW": 0.65, "FIRE": 0.20, "EMS": 0.15},
    agency_names={"LAW": "POLICE", "FIRE": "FIRE", "EMS": "EMS"},
    # ... other parameters
)

request = GenerationRequest(
    rows=50000,
    area_query="Denver, CO",
    output_format=OutputFormat.PARQUET,
    dataset=DatasetKind.ALL,
    realism_config=realism,
)

app = Synth911Application(address_provider=OpenStreetMapAddressProvider())
result = app.generate(request)
```

---

## Realism Features (Default Distributions)

The values below are the **built-in defaults**, which is exactly what you get when no
`--config` file is supplied. Override any of them through the realism configuration.

### Agency Distribution

- **LAW**: 52% of incidents
- **FIRE**: 20% of incidents
- **EMS**: 28% of incidents

### Shift Structure (Default)

The default shift structure is **2x12h-4shift-14day**: shifts A/B on day
(06:00-18:00) and C/D on night (18:00-06:00), rotating on the 14-day pattern
`1,1,2,2,1,1,1,2,2,1,1,2,2,2` (starting Monday), where group 1 = A day + C
night and group 2 = B day + D night. Each shift is staffed with 3 calltakers
and 2 dispatchers. This same structure is used when no `--shift-preset` or
`shift_config` is supplied. See [Shift Structures](#shift-structures) above.

### Priority Weights (by Agency)

| Priority | LAW | FIRE | EMS |
|----------|-----|------|-----|
| 1 (Highest) | 12% | 18% | 16% |
| 2 | 18% | 24% | 26% |
| 3 | 28% | 24% | 28% |
| 4 | 26% | 20% | 18% |
| 5 (Lowest) | 16% | 14% | 12% |

### Problem Natures (Weighted by Agency)

**LAW** (30): Shots Fired, Burglary In Progress, Vehicle Collision w/ Injury, Assault, Reckless Driving, Weapons Violation, DUI / Impaired Driver, Domestic Disturbance, Missing Person, Burglary, Drug/Narcotic Violation, Motor Vehicle Theft, Robbery, Disorderly Conduct, Theft Report, Burglary Alarm, Traffic Crash, Fraud, Harassment, Shoplifting, Vandalism, Trespass, Suspicious Person, Welfare Check, Noise Complaint, Traffic Stop, Animal Complaint, Found Property, Animal Bite, Public Assist

**FIRE** (20): Fire Alarm, Smoke Investigation, Medical Assist, Structure Fire, Vehicle Fire, Cooking Fire, Brush/Grass Fire, Gas Leak, CO Investigation, Hazardous Condition, Rescue Call, Mutual Aid, Odor Investigation, Overheat Investigation, Electrical Wiring Problem, Lockout / Public Service, Water Rescue, Vehicle Extrication, Assist Police, Elevator Rescue

**EMS** (22): Chest Pain, Difficulty Breathing, Fall Injury, Motor Vehicle Crash, Sick Person, Unconscious Person, Seizure, Altered Mental Status, Abdominal Pain, Overdose, Psychiatric Emergency, Stroke, Diabetic Problem, Heart Problems, Allergic Reaction, Hemorrhage / Bleeding, Traumatic Injury, Head Injury, Choking, Heat/Cold Exposure, Pregnancy / Childbirth, Animal Bite

> The problem vocabulary is keyed by agency and **priority pool**, so low-acuity
> problems do not appear at urgent priorities (and vice versa).

### Time Profiles (Lognormal Distributions)

Each agency/priority combination has calibrated time profiles (mean seconds):

| Interval | Description | Distribution |
|----------|-------------|--------------|
| Pickup Delay | Ring to answer | Lognormal(3s, σ=0.45) |
| Interview | Caller questioning | Lognormal(14-105s by priority) |
| Dispatch Queue | Queue to dispatch | Lognormal(4-320s by priority) |
| Turnout | Station to wheels rolling | Lognormal(10-84s by priority) |
| Travel | Wheels rolling to on-scene | Lognormal(220-560s by priority) |
| On Scene | On-scene duration | Lognormal(1380-3060s by priority) |
| Closeout | Scene clear to incident close | Lognormal(240-420s by priority) |

### Diurnal Call Patterns

Hourly weights follow real 9-1-1 center patterns:
**Peak**: 13:00-18:00 (6.2% per hour). **Valley**: 03:00-05:00 (2.0-2.2% per hour).
A weekend multiplier (+12% Fri/Sat) is configurable via `phone_metrics.weekend_multiplier`.

### Hourly Phone Metrics

Hourly call counts are driven by a base volume (`rows / hours`, floored at
`min_hourly_volume`) split by fractions per call type, with abandonment drawn
binomial on the received counts:

| Key | Default | Meaning |
|-----|---------|---------|
| `min_hourly_volume` | 2.0 | Floor on base calls-per-hour |
| `nine_one_one_received_fraction` | 0.48 | Share of base volume received as 9-1-1 |
| `non_emergency_received_fraction` | 0.58 | Share received as non-emergency |
| `outbound_calls_fraction` | 0.26 | Share placed as outbound |
| `nine_one_one_abandonment_rate` | 0.02 | Baseline 9-1-1 abandonment rate |
| `night_abandonment_increment` | 0.03 | Added to 9-1-1 rate during 00:00-05:59 |
| `non_emergency_abandonment_rate` | 0.05 | Non-emergency abandonment rate |
| `max_abandonment_rate` | 0.12 | Cap applied to abandonment draws |
| `weekend_multiplier` | 1.12 | Volume multiplier on Fri/Sat |

### Call Reception Methods

| Method | Weight |
|--------|--------|
| E-911 | 33% |
| Phone | 38% |
| OFFICER | 14% |
| Radio | 6% |
| C2C | 5% |
| NOT CAPTURED | 2% |
| Text | 1% |
| CAD2CAD | 1% |

### Disposition Codes (by Agency)

| Disposition | LAW | FIRE | EMS |
|-------------|-----|------|-----|
| NR-No Report | 40% | 45% | 45% |
| UNDEFINED | 28% | 29% | 38% |
| RE-Report | 15% |    |   |
| CI-Citation | 10% |   |   |
| FALSE-False Alarm |   | 15% | 10% |
| RAF-Reassign FD Call |   | 5% |   |
| CN-Cancellation | 4% | 5% | 5% |
| SUP-Supplement | 1% | 1% | 2% |
| ACOR-Animal Control | 2% |   |   |