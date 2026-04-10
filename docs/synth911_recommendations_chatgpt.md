# Synthetic 9-1-1 CAD Data Generator -- Enhanced Recommendations

## Overview

This document consolidates updated recommendations to improve realism in
synthetic 9-1-1 CAD datasets, especially focusing on time modeling,
dispatch behavior, and operational constraints.

------------------------------------------------------------------------

## 1. Priority & Agency-Based Time Modeling

Define time profiles:

``` python
TIME_PROFILES = {
    "LAW": {
        1: {"queue_mean": 3, "dispatch_mean": 20, "enroute_mean": 300},
        5: {"queue_mean": 120, "dispatch_mean": 300, "enroute_mean": 1200},
    }
}
```

Helper:

``` python
def generate_time(mean_seconds, variability=0.4):
    return int(np.random.lognormal(np.log(mean_seconds), variability))
```

------------------------------------------------------------------------

## 2. Poisson Call Arrival (Realistic Volume)

``` python
def hourly_call_rate(hour):
    if 15 <= hour <= 23:
        return 1.8
    elif 0 <= hour <= 6:
        return 0.6
    return 1.0
```

------------------------------------------------------------------------

## 3. Unit Availability (Queueing)

``` python
active_units = []
if len(active_units) >= capacity:
    queue_time += 60
```

------------------------------------------------------------------------

## 4. Parallel Call Handling (UPDATED)

Two timelines:

Call-taking: event_time → phone_time → disconnect

Dispatch: event_time → dispatch_ready → queue → dispatch

``` python
DISPATCH_INIT_FRACTION = {
    1: (0.05, 0.20),
    5: (0.90, 1.20),
}
```

``` python
dispatch_ready = event_time + timedelta(seconds=phone_time * fraction)
```

------------------------------------------------------------------------

## 5. Turnout vs Travel Time

``` python
turnout = np.random.gamma(2, 20)
travel = np.random.gamma(5, 90)
enroute_time = turnout + travel
```

------------------------------------------------------------------------

## 6. Geographic Modeling

``` python
DISTRICTS = {"URBAN":300,"SUBURBAN":600,"RURAL":1200}
```

------------------------------------------------------------------------

## 7. Personnel Constraints

``` python
if shift_part == "LATE":
    dispatch_time *= 1.1
```

------------------------------------------------------------------------

## 8. Disposition Modeling

``` python
DISPOSITION_PROFILES = {
    "LAW": {1: {"ARREST MADE":0.35}}
}
```

------------------------------------------------------------------------

## 9. Add Incident Start Field

``` python
df.with_columns(pl.col("event_time").alias("incident_start_time"))
```

------------------------------------------------------------------------

## 10. Config-Driven Design

``` python
import yaml
config = yaml.safe_load(open("config.yaml"))
```

------------------------------------------------------------------------

## Libraries

-   numpy
-   scipy
-   simpy
-   pyyaml

------------------------------------------------------------------------

## Conclusion

Move from independent random sampling → constrained simulation model for
realism.
