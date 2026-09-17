# SynthCCD Incidents Dataset Schema

**Schema Version:** 1.2
**Generator:** `synth911gen3.generators.incidents.IncidentGenerator`
**Default Output:** CSV, 10,000 rows, Kansas City, MO

---

## Overview

The Incidents dataset emulates CAD (Computer-Aided Dispatch) archival records — the structured log entries created when a call enters a public-safety answering point (PSAP) and is dispatched to law, fire, or EMS units. Each row represents one call/incident and contains identifiers, location data, lifecycle timestamps, personnel assignments, and derived elapsed-time fields.

All timestamps and elapsed times are generated using **priority-weighted lognormal distributions** calibrated to real-world CAD data. Address components are sourced from OpenStreetMap and parsed into CAD-style fields. Personnel names are drawn from locale-aware Faker pools with Zipf-weighted workload distribution (front-line staff take more calls).

---

## Column Reference

### Identifiers

| # | Column | Type | Nullable | Description | Example |
|---|--------|------|----------|-------------|---------|
| 1 | `id_number` | `int64` or `string` | No | Row identifier. Sequential integers (default) or UUID v4 strings depending on `id_format`. | `1` or `"a3f1c8e2-..."` |
| 2 | `internal_reference_number` | `string` | No | Per-agency daily sequential reference. Format: `AGENCY-DDD-NNNNN` where DDD is the 3-digit day of year (001–366) and NNNNN is a 5-digit sequential counter. Counters reset daily per agency. | `LAW-260-00001` |

### Agency & Classification

| # | Column | Type | Nullable | Description | Values / Weights |
|---|--------|------|----------|-------------|------------------|
| 3 | `agency` | `string` | No | Responding agency type. | `LAW` (0.52), `FIRE` (0.20), `EMS` (0.28) |
| 4 | `shift` | `string` | No | Active shift identifier (e.g., `A`, `B`, `C`, `D`). | `A`, `B`, `C`, `D` |
| 5 | `shift_label` | `string` | No | Human-readable shift label. | `DAY`, `NIGHT` |
| 6 | `shift_group` | `int64` | No | Rotation group number for the active shift. | `1`, `2` |
| 7 | `problem_nature` | `string` | No | Call type / nature of incident. Weighted by agency, priority, and season. See [Problem Profiles](#problem-profiles) below. | `Shots Fired`, `Structure Fire`, `Cardiac Arrest` |
| 8 | `priority` | `int64` | No | Dispatch priority level. 1 = highest, 5 = lowest. Distribution varies by agency. See [Priority Weights](#priority-weights) below. | `1`, `2`, `3`, `4`, `5` |

### Address Fields

| # | Column | Type | Nullable | Description | Example |
|---|--------|------|----------|-------------|---------|
| 9 | `prefix_directional` | `string` | Yes | Street prefix directional (before street name). | `N`, `S`, `E`, `W`, `NE`, `NW`, `SE`, `SW` |
| 10 | `street_number` | `string` | Yes | Street address number. | `204`, `890`, `777` |
| 11 | `street_name` | `string` | Yes | Street name (without type or directional). | `Main`, `12th`, `Oak Trafficway` |
| 12 | `street_type` | `string` | Yes | Street type abbreviation. | `St`, `Ave`, `Blvd`, `Dr`, `Ln`, `Ct`, `Rd`, `Hwy` |
| 13 | `postfix_directional` | `string` | Yes | Street postfix directional (after street type). | `N`, `S`, `E`, `W`, `NE`, `NW`, `SE`, `SW` |
| 14 | `street_address` | `string` | No | Full street address (number + name + type + directionals). | `204 E 12th St` |
| 15 | `city` | `string` | No | City name. | `Kansas City` |
| 16 | `state` | `string` | No | State or province name. | `Missouri` |
| 17 | `postal_code` | `string` | Yes | Postal/ZIP code. US ZIP+4 is truncated to 5 digits. | `64110` |
| 18 | `latitude` | `float64` | No | WGS-84 latitude coordinate. | `39.1027` |
| 19 | `longitude` | `float64` | No | WGS-84 longitude coordinate. | `-94.5804` |
| 20 | `zone` | `string` | No | Geographic zone classification. Affects travel-time multipliers. | `URBAN` (0.8x), `SUBURBAN` (1.0x), `RURAL` (1.5x) |
| 21 | `commonplace_name` | `string` | Yes | Business or landmark name when the address is a named place (e.g., from OSM `amenity`, `shop`, `tourism` tags). Empty string if residential/unnamed. | `T-Mobile Center`, `` |
| 22 | `unit_number` | `string` | Yes | Sub-address component (suite, unit, floor). From OSM `addr:flats`/`addr:unit`/`addr:suite` tags. | `Suite 15`, `Unit C`, `` |
| 23 | `location` | `string` | No | Combined display string: `street_address, city, state`. | `204 E 12th St, Kansas City, Missouri` |

### Timestamps

All timestamps are `datetime64[s]` (second-precision). They are chronologically ordered per incident:

```
call_start_time
  < 0-30s >
incident_start_time
  < pickup_delay (3s mean) >
time_phone_pickup
  < interview_seconds >
time_call_enters_queue
  < dispatch_init + dispatch_queue >
time_first_unit_assigned
  < turnout_seconds >
time_unit_enroute
  < travel_seconds (zone-adjusted) >
time_unit_arrived
  < on_scene_seconds >
time_last_unit_cleared
  < closeout_seconds >
time_call_closed
```

| # | Column | Type | Nullable | Description | Constraints |
|---|--------|------|----------|-------------|-------------|
| 24 | `call_start_time` | `datetime64[s]` | No | When the call first enters the system (ringing). Distributed across hours via diurnal weights. | Earliest timestamp in lifecycle |
| 25 | `hour` | `int64` | No | Hour of day (0-23) extracted from `call_start_time`. | `0`–`23` |
| 26 | `dow` | `string` | No | Day-of-week abbreviation from `call_start_time`. | `MON`, `TUE`, `WED`, `THU`, `FRI`, `SAT`, `SUN` |
| 27 | `week_no` | `int64` | No | ISO week number from `call_start_time`. | `1`–`53` |
| 28 | `incident_start_time` | `datetime64[s]` | No | CAD system recording start. Offset 0–30 seconds after `call_start_time`. | >= `call_start_time` |
| 29 | `time_phone_pickup` | `datetime64[s]` | No | When calltaker picks up the line. Lognormal delay (mean ~3s, max 20s). | >= `call_start_time` |
| 30 | `time_call_enters_queue` | `datetime64[s]` | No | When call enters the dispatch queue (call-taking complete). | >= `time_phone_pickup` |
| 31 | `time_first_unit_assigned` | `datetime64[s]` | No | When first unit is assigned. May occur while call is still in progress for high-priority calls (parallel dispatch). | >= `time_phone_pickup` |
| 32 | `time_unit_enroute` | `datetime64[s]` | No | When assigned unit goes enroute (wheels rolling). | >= `time_first_unit_assigned` |
| 33 | `time_unit_arrived` | `datetime64[s]` | No | When unit arrives on scene. Travel time is zone-adjusted (urban/suburban/rural). | >= `time_unit_enroute` |
| 34 | `time_last_unit_cleared` | `datetime64[s]` | No | When last unit clears the scene. | >= `time_unit_arrived` |
| 35 | `time_call_closed` | `datetime64[s]` | No | When call is closed in the CAD system. | >= `time_last_unit_cleared` |
| 36 | `time_phone_disconnect` | `datetime64[s]` | No | When the phone call disconnects. May differ from `time_call_closed` when dispatch continues after hangup. | >= `time_phone_pickup` |

### Personnel

| # | Column | Type | Nullable | Description | Example |
|---|--------|------|----------|-------------|---------|
| 37 | `calltaker` | `string` | No | Name of the calltaker who handled the call. Drawn from the active shift's calltaker pool with Zipf weighting (earlier names take more calls). | `Maria Johnson` |
| 38 | `dispatcher` | `string` | No | Name of the dispatcher who dispatched the call. Drawn from the active shift's dispatcher pool. For medium/large centres, dispatchers are split by discipline console (LAW / FIRE / EMS). | `James Williams` |

### Call Metadata

| # | Column | Type | Nullable | Description | Values / Weights |
|---|--------|------|----------|-------------|------------------|
| 39 | `method_of_call_reception` | `string` | No | How the call was received. See [Call Reception Weights](#call-reception-weights). | See table below |
| 40 | `call_disposition` | `string` | No | Final disposition code. Varies by agency. See [Disposition Profiles](#disposition-profiles). | See table below |

### Elapsed Time Fields

All elapsed fields are `int64` seconds. They represent the raw drawn durations before accumulation into timestamps.

| # | Column | Type | Nullable | Description | Distribution |
|---|--------|------|----------|-------------|-------------|
| 41 | `pickup_delay_seconds` | `int64` | No | Delay from `call_start_time` to `time_phone_pickup`. | Lognormal, mean ~3s, sigma 0.45, max 20s |
| 42 | `pre_cad_offset_seconds` | `int64` | No | Offset from `call_start_time` to `incident_start_time`. | Uniform 0–3s |
| 43 | `interview_seconds` | `int64` | No | Calltaker questioning duration (phone_pickup → queue). | Lognormal, priority/agency mean, sigma 0.65, max 1800s |
| 44 | `dispatch_queue_seconds` | `int64` | No | Time in queue before unit assignment. | Lognormal, priority/agency mean, sigma 0.85, max 7200s |
| 45 | `turnout_seconds` | `int64` | No | Station-to-wheels-rolling time. | Lognormal, priority/agency mean, sigma 0.60, max 900s |
| 46 | `travel_seconds` | `int64` | No | Wheels-rolling to on-scene. Multiplied by zone factor (0.8 urban, 1.0 suburban, 1.5 rural). | Lognormal, priority/agency mean, sigma 0.55, max 3600s |
| 47 | `on_scene_seconds` | `int64` | No | On-scene duration. | Lognormal, priority/agency mean, sigma 0.50, max 10800s |
| 48 | `closeout_seconds` | `int64` | No | Scene-clear to incident-close time. | Lognormal, priority/agency mean, sigma 0.45, max 1800s |
| 49 | `phone_duration_seconds` | `int64` | No | Total phone call duration. May extend beyond dispatch for high-priority parallel dispatch. Adjusted by problem-specific multipliers. | Lognormal, priority/agency mean × problem multiplier, sigma 0.70, max 3600s |
| 50 | `total_elapsed_seconds` | `int64` | No | Total elapsed time from `call_start_time` to `time_call_closed`. | Sum of lifecycle intervals |

---

## Priority Weights

Priority 1 is the highest (most urgent), 5 is the lowest. Distributions are per-agency:

| Priority | LAW | FIRE | EMS |
|----------|-----|------|-----|
| 1 | 0.12 | 0.18 | 0.16 |
| 2 | 0.18 | 0.24 | 0.26 |
| 3 | 0.28 | 0.24 | 0.28 |
| 4 | 0.26 | 0.20 | 0.18 |
| 5 | 0.16 | 0.14 | 0.12 |

---

## Call Reception Weights

| Method | Weight |
|--------|--------|
| E-911 | 0.33 |
| Phone | 0.38 |
| OFFICER | 0.14 |
| Radio | 0.06 |
| C2C | 0.05 |
| NOT CAPTURED | 0.02 |
| Text | 0.01 |
| CAD2CAD | 0.01 |

---

## Disposition Profiles

### LAW

| Code | Weight |
|------|--------|
| NR-No Report | 0.40 |
| UNDEFINED | 0.28 |
| RE-Report | 0.15 |
| CI-Citation | 0.10 |
| CN-Cancellation | 0.04 |
| ACOR-Animal Control | 0.02 |
| SUP-Supplement | 0.01 |

### FIRE

| Code | Weight |
|------|--------|
| NR-No Report | 0.45 |
| UNDEFINED | 0.29 |
| FALSE-False Alarm | 0.15 |
| CN-Cancellation | 0.05 |
| RAF-Reassign FD Call | 0.05 |
| SUP-Supplement | 0.01 |

### EMS

| Code | Weight |
|------|--------|
| NR-No Report | 0.45 |
| UNDEFINED | 0.38 |
| FALSE-False Alarm | 0.10 |
| CN-Cancellation | 0.05 |
| SUP-Supplement | 0.02 |

---

## Problem Profiles

Problem natures are selected by **agency × priority × season**. Each cell contains a weighted list of problem types. Seasonal multipliers adjust weights at generation time (e.g., `Brush/Grass Fire` peaks in Summer).

### LAW Problem Natures

#### Priority 1
| Problem | Weight |
|---------|--------|
| Shots Fired | 0.20 |
| Burglary In Progress | 0.15 |
| Vehicle Collision w/ Injury | 0.15 |
| Assault | 0.12 |
| Reckless Driving | 0.10 |
| Weapons Violation | 0.08 |
| DUI / Impaired Driver | 0.08 |
| Domestic Disturbance | 0.07 |
| Missing Person | 0.05 |

#### Priority 2
| Problem | Weight |
|---------|--------|
| Domestic Disturbance | 0.18 |
| Assault | 0.15 |
| Burglary | 0.12 |
| Drug/Narcotic Violation | 0.10 |
| Motor Vehicle Theft | 0.10 |
| DUI / Impaired Driver | 0.10 |
| Vehicle Collision w/ Injury | 0.10 |
| Robbery | 0.08 |
| Disorderly Conduct | 0.07 |

#### Priority 3
| Problem | Weight |
|---------|--------|
| Theft Report | 0.20 |
| Burglary Alarm | 0.15 |
| Traffic Crash | 0.12 |
| Fraud | 0.10 |
| Harassment | 0.09 |
| Shoplifting | 0.08 |
| Vandalism | 0.08 |
| Trespass | 0.06 |
| Suspicious Person | 0.06 |
| Welfare Check | 0.06 |

#### Priority 4
| Problem | Weight |
|---------|--------|
| Noise Complaint | 0.19 |
| Traffic Stop | 0.17 |
| Suspicious Person | 0.15 |
| Welfare Check | 0.13 |
| Disorderly Conduct | 0.11 |
| Animal Complaint | 0.08 |
| Vandalism | 0.07 |
| Trespass | 0.05 |
| Harassment | 0.05 |

#### Priority 5
| Problem | Weight |
|---------|--------|
| Noise Complaint | 0.16 |
| Welfare Check | 0.15 |
| Found Property | 0.11 |
| Animal Complaint | 0.08 |
| Animal Bite | 0.05 |
| Traffic Stop | 0.08 |
| Public Assist | 0.08 |
| Vandalism | 0.06 |
| Suspicious Person | 0.05 |
| Assist Fire | 0.08 |
| Assist EMS | 0.10 |

### FIRE Problem Natures

#### Priority 1
| Problem | Weight |
|---------|--------|
| Structure Fire | 0.30 |
| Rescue Call | 0.15 |
| Vehicle Fire | 0.15 |
| Gas Leak | 0.12 |
| Hazardous Condition | 0.10 |
| Vehicle Extrication | 0.10 |
| Water Rescue | 0.08 |

#### Priority 2
| Problem | Weight |
|---------|--------|
| Structure Fire | 0.15 |
| Vehicle Fire | 0.20 |
| Cooking Fire | 0.15 |
| Brush/Grass Fire | 0.12 |
| Gas Leak | 0.10 |
| CO Investigation | 0.10 |
| Elevator Rescue | 0.10 |
| Electrical Wiring Problem | 0.08 |

#### Priority 3
| Problem | Weight |
|---------|--------|
| Fire Alarm | 0.22 |
| Smoke Investigation | 0.18 |
| Overheat Investigation | 0.12 |
| Odor Investigation | 0.12 |
| CO Investigation | 0.10 |
| Medical Assist | 0.10 |
| Chimney Fire | 0.08 |
| Mutual Aid | 0.05 |
| Brush/Grass Fire | 0.03 |

#### Priority 4
| Problem | Weight |
|---------|--------|
| Fire Alarm | 0.30 |
| Smoke Investigation | 0.20 |
| Odor Investigation | 0.15 |
| Overheat Investigation | 0.15 |
| Medical Assist | 0.10 |
| Mutual Aid | 0.10 |

#### Priority 5
| Problem | Weight |
|---------|--------|
| Fire Alarm | 0.22 |
| Smoke Investigation | 0.13 |
| Odor Investigation | 0.13 |
| Lockout / Public Service | 0.13 |
| Mutual Aid | 0.13 |
| Assist Police | 0.09 |
| Assist EMS | 0.09 |
| Overheat Investigation | 0.04 |
| Medical Assist | 0.04 |

### EMS Problem Natures

#### Priority 1
| Problem | Weight |
|---------|--------|
| Cardiac Arrest | 0.15 |
| Choking | 0.10 |
| Unconscious Person | 0.15 |
| Difficulty Breathing | 0.15 |
| Stroke | 0.12 |
| Hemorrhage / Bleeding | 0.13 |
| Seizure | 0.10 |
| Chest Pain | 0.10 |

#### Priority 2
| Problem | Weight |
|---------|--------|
| Chest Pain | 0.18 |
| Difficulty Breathing | 0.15 |
| Altered Mental Status | 0.12 |
| Heart Problems | 0.12 |
| Overdose | 0.12 |
| Head Injury | 0.10 |
| Seizure | 0.08 |
| Allergic Reaction | 0.08 |
| Traumatic Injury | 0.05 |

#### Priority 3
| Problem | Weight |
|---------|--------|
| Fall Injury | 0.18 |
| Motor Vehicle Crash | 0.15 |
| Abdominal Pain | 0.12 |
| Diabetic Problem | 0.10 |
| Sick Person | 0.10 |
| Traumatic Injury | 0.10 |
| Head Injury | 0.08 |
| Allergic Reaction | 0.07 |
| Pregnancy / Childbirth | 0.05 |
| Overdose | 0.05 |

#### Priority 4
| Problem | Weight |
|---------|--------|
| Fall Injury | 0.20 |
| Sick Person | 0.18 |
| Abdominal Pain | 0.14 |
| Motor Vehicle Crash | 0.12 |
| Traumatic Injury | 0.10 |
| Diabetic Problem | 0.08 |
| Psychiatric Emergency | 0.08 |
| Animal Bite | 0.05 |
| Heat/Cold Exposure | 0.05 |

#### Priority 5
| Problem | Weight |
|---------|--------|
| Sick Person | 0.20 |
| Fall Injury | 0.12 |
| Animal Bite | 0.10 |
| Psychiatric Emergency | 0.10 |
| Heat/Cold Exposure | 0.08 |
| Traumatic Injury | 0.06 |
| Abdominal Pain | 0.06 |
| Diabetic Problem | 0.08 |
| Assist Police | 0.10 |
| Assist Fire | 0.10 |

---

## Time Profile Means (seconds)

Each agency × priority cell defines the **mean** for a lognormal draw. The actual per-incident value is drawn from `Lognormal(mu, sigma)` where `mu = ln(mean) - sigma^2/2`.

### LAW

| Priority | Interview | Dispatch | Turnout | Travel | Scene | Closeout | Phone |
|----------|-----------|----------|---------|--------|-------|----------|-------|
| 1 | 12 | 4 | 10 | 220 | 1,500 | 240 | 170 |
| 2 | 25 | 12 | 22 | 260 | 1,650 | 270 | 210 |
| 3 | 45 | 25 | 35 | 320 | 1,920 | 330 | 250 |
| 4 | 70 | 140 | 55 | 410 | 2,220 | 360 | 300 |
| 5 | 95 | 320 | 70 | 520 | 2,460 | 390 | 340 |

### FIRE

| Priority | Interview | Dispatch | Turnout | Travel | Scene | Closeout | Phone |
|----------|-----------|----------|---------|--------|-------|----------|-------|
| 1 | 16 | 6 | 28 | 300 | 2,100 | 300 | 160 |
| 2 | 30 | 18 | 40 | 340 | 2,280 | 330 | 190 |
| 3 | 52 | 35 | 55 | 390 | 2,520 | 360 | 230 |
| 4 | 80 | 170 | 70 | 470 | 2,760 | 390 | 270 |
| 5 | 105 | 330 | 84 | 560 | 3,060 | 420 | 320 |

### EMS

| Priority | Interview | Dispatch | Turnout | Travel | Scene | Closeout | Phone |
|----------|-----------|----------|---------|--------|-------|----------|-------|
| 1 | 14 | 5 | 16 | 240 | 1,380 | 240 | 200 |
| 2 | 28 | 14 | 28 | 280 | 1,560 | 270 | 230 |
| 3 | 50 | 30 | 40 | 340 | 1,800 | 300 | 260 |
| 4 | 74 | 155 | 55 | 430 | 2,040 | 330 | 290 |
| 5 | 100 | 315 | 70 | 520 | 2,280 | 360 | 330 |

---

## Dispatch Init Fraction (Parallel Dispatch)

For each priority, a random fraction in `[lo, hi]` determines how much of the phone window must elapse before dispatch begins. Fractions < 1.0 mean the unit is dispatched while the caller is still on the phone (parallel dispatch).

| Priority | lo | hi |
|----------|----|----|
| 1 | 0.05 | 0.20 |
| 2 | 0.20 | 0.50 |
| 3 | 0.40 | 0.80 |
| 4 | 0.90 | 1.10 |
| 5 | 1.00 | 1.30 |

---

## Geographic Zone Multipliers

Applied to `travel_seconds` based on the address's zone classification:

| Zone | Multiplier | Description |
|------|------------|-------------|
| URBAN | 0.8 | Dense city center, shorter travel distances |
| SUBURBAN | 1.0 | Residential outskirts (baseline) |
| RURAL | 1.5 | Sparse areas, longer travel distances |

---

## Problem-Specific Phone Duration Multipliers

Applied to `phone_mean` per incident based on `problem_nature`. Values > 1.0 increase call duration; < 1.0 decrease it. Unlisted problems default to 1.0.

| Problem | Multiplier |
|---------|------------|
| Active Shooter | 2.5 |
| Hostage Situation | 2.5 |
| Barricaded Subject | 2.0 |
| Homicide | 1.8 |
| Cardiac Arrest | 1.6 |
| Water Rescue | 1.6 |
| Shots Fired | 1.6 |
| Structure Fire | 1.5 |
| Choking | 1.5 |
| Stroke | 1.5 |
| Burglary In Progress | 1.5 |
| Vehicle Extrication | 1.5 |
| Missing Person | 1.4 |
| Domestic Disturbance | 1.4 |
| Gas Leak | 1.4 |
| Hemorrhage / Bleeding | 1.4 |
| Unconscious Person | 1.4 |
| Overdose | 1.4 |
| Head Injury | 1.4 |
| Pregnancy / Childbirth | 1.4 |
| Rescue Call | 1.4 |
| Vehicle Collision w/ Injury | 1.3 |
| Assault | 1.3 |
| Weapons Violation | 1.3 |
| DUI / Impaired Driver | 1.3 |
| Hazardous Condition | 1.3 |
| Difficulty Breathing | 1.3 |
| Seizure | 1.3 |
| Chest Pain | 1.3 |
| Altered Mental Status | 1.3 |
| Heart Problems | 1.3 |
| Allergic Reaction | 1.3 |
| Traumatic Injury | 1.3 |
| Psychiatric Emergency | 1.3 |
| Brush/Grass Fire | 1.3 |
| Vehicle Fire | 1.3 |
| Motor Vehicle Crash | 1.3 |
| Burglary | 1.2 |
| Drug/Narcotic Violation | 1.2 |
| Traffic Crash | 1.2 |
| Fall Injury | 1.2 |
| Abdominal Pain | 1.2 |
| Diabetic Problem | 1.2 |
| Animal Bite | 1.2 |
| Assist Fire | 1.2 |
| Assist EMS | 1.2 |
| Elevator Rescue | 1.2 |
| Medical Assist | 1.2 |
| Mutual Aid | 1.2 |
| Assist Police | 1.2 |
| Motor Vehicle Theft | 1.1 |
| Disorderly Conduct | 1.1 |
| Theft Report | 1.1 |
| Fraud | 1.1 |
| Harassment | 1.1 |
| Shoplifting | 1.1 |
| Vandalism | 1.1 |
| Reckless Driving | 1.2 |
| Sick Person | 1.1 |
| Cooking Fire | 1.1 |
| CO Investigation | 1.1 |
| Electrical Wiring Problem | 1.1 |
| Smoke Investigation | 1.1 |
| Noise Complaint | 1.0 |
| Traffic Stop | 1.0 |
| Found Property | 1.0 |
| Animal Complaint | 1.0 |
| Public Assist | 1.0 |
| Burglary Alarm | 1.0 |
| Trespass | 1.0 |
| Suspicious Person | 1.1 |
| Welfare Check | 1.2 |
| Fire Alarm | 1.0 |
| Overheat Investigation | 1.0 |
| Odor Investigation | 1.0 |
| Lockout / Public Service | 1.0 |

---

## Sample Row

```
id_number:                         1
internal_reference_number:         LAW-260-00001
agency:                            LAW
shift:                             A
shift_label:                       DAY
shift_group:                       1
problem_nature:                    Theft Report
priority:                          3
prefix_directional:                E
street_number:                     204
street_name:                       12th
street_type:                       St
postfix_directional:
street_address:                    204 E 12th St
city:                              Kansas City
state:                             Missouri
postal_code:                       64110
latitude:                          39.1027
longitude:                         -94.5804
zone:                              URBAN
commonplace_name:
unit_number:
location:                          204 E 12th St, Kansas City, Missouri
call_start_time:                   2026-01-15 14:23:07
hour:                              14
dow:                               THU
week_no:                           3
incident_start_time:               2026-01-15 14:23:09
time_phone_pickup:                 2026-01-15 14:23:10
time_call_enters_queue:            2026-01-15 14:23:52
time_first_unit_assigned:          2026-01-15 14:24:18
time_unit_enroute:                 2026-01-15 14:24:49
time_unit_arrived:                 2026-01-15 14:29:33
time_last_unit_cleared:            2026-01-15 15:01:12
time_call_closed:                  2026-01-15 15:06:48
time_phone_disconnect:             2026-01-15 14:27:30
calltaker:                         Maria Johnson
dispatcher:                        James Williams
method_of_call_reception:          Phone
call_disposition:                  NR-No Report
pickup_delay_seconds:              3
pre_cad_offset_seconds:            2
interview_seconds:                 42
dispatch_queue_seconds:            26
turnout_seconds:                   31
travel_seconds:                    284
on_scene_seconds:                  1879
closeout_seconds:                  336
phone_duration_seconds:            260
total_elapsed_seconds:             2741
```

---

## Generation Notes

1. **Seed Determinism**: All random draws flow through a single seeded NumPy RNG. The same seed + realism config + request parameters produces byte-identical output.
2. **Chunked Generation**: Large runs (> memory budget) are streamed in chunks. Reference-number counters and ID sequences continue across chunks.
3. **Seasonal Weighting**: Problem natures are adjusted at draw time by seasonal multipliers based on the incident's calendar month.
4. **Parallel Dispatch**: High-priority calls (especially Priority 1) may be dispatched while the caller is still on the phone, creating overlapping timelines.
5. **Zone-Adjusted Travel**: Urban addresses get shorter travel times (0.8x); rural addresses get longer (1.5x).
6. **Personnel Workload**: Calltaker and dispatcher names follow Zipf-like weighting — the first-generated names in each shift pool handle more calls, reflecting real-world seniority patterns.
7. **Dispatcher Disciplines**: For medium/large centres (4+ dispatchers per shift), dispatchers are split into discipline consoles (LAW / FIRE-EMS or LAW / FIRE / EMS) so each incident is handled by the appropriate console.
