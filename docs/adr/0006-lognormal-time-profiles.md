# ADR-0006: Lognormal timing models calibrated per agency and priority

- Status: Accepted
- Date: 2026-08-05
- Deciders: Maintainers

## Context

The incident lifecycle is a chain of events with elapsed times between them:
pickup delay, call interview, dispatch queue, turnout, travel, on-scene,
closeout, and total phone duration. AGENTS.md requires elapsed times that are
"realistic for priority and agency", and the realism recommendations demand
"lognormal distributions with parameters calibrated to real data" per interval.

Real CAD data shows: elapsed times are right-skewed (most calls are quick, a
few take very long), higher priorities dispatch faster and travel harder, and
FIRE/EMS units turn out faster than LAW. Priority 1 calls are dispatched
*while the call is still in progress* — the dispatch and call-taking timelines
run in parallel, not in series.

## Decision

- **One `TIME_PROFILES` table** in `constants.py`: for each agency
  (LAW/FIRE/EMS) and priority (1–5), seven mean durations in seconds
  (`interview_mean`, `dispatch_mean`, `turnout_mean`, `travel_mean`,
  `scene_mean`, `closeout_mean`, `phone_mean`). Means are calibrated so the
  same priority ordering and agency character (LAW slower on scene, FIRE/EMS
  faster turnout) holds across the table, and are fully overridable via the
  realism YAML (`time_profiles` section).
- **All draws are lognormal**: `mu = ln(mean) - sigma²/2`, fixed per-interval
  `sigma` (0.45–0.85), with hard clip bounds (e.g. travel ≤ 3600 s, scene ≤
  10800 s) so pathological tails cannot produce absurd timestamps. See
  `_lognormal_seconds()` in `generators/incidents.py`.
- **Turnout and travel are separate intervals** — `time_unit_enroute` →
  `time_unit_arrived` splits at wheels-rolling, per recommendation #9.
- **Parallel dispatch/call-taking**: `dispatch_init_fraction[priority]` gives
  the (lo, hi) bounds of the phone-duration fraction at which the first unit is
  assigned. Priorities with fractions < 1.0 are dispatched mid-call;
  `phone_duration_seconds = max(interview + queue, phone_mean draw)` keeps the
  timeline consistent (dispatch never happens before the call exists).
- **Vectorization**: means are looked up from a precomputed
  `(agency × priority)` table indexed by `agency_codes`/`priorities` arrays
  (ADR-0001), so the whole lifecycle falls out of ~8 array draws.

## Consequences

### Positive

- Right-skewed, bounded durations that track agency and priority — verified by
  hypothesis tests (`tests/test_properties.py`) that clip bounds and per-cell
  means hold, and by the regression signature suite (`tests/test_regression.py`).
- Mid-call dispatch for high priorities produces the parallel timeline real
  centers show (first unit assigned before the call ends).
- Time profiles are operator-tunable via YAML without touching code.

### Negative / Costs

- The lognormal parameters are calibrated by hand from the source-material
  distributions, not fit by an offline pipeline; drift from a real center
  requires manual re-tuning (the regression baseline catches unintended drift,
  not miscalibration).
- Fixed clip bounds are a blunt instrument — a 3600 s travel cap exists because
  lognormal tails are unruly, and it slightly truncates the true distribution.
- `dispatch_init_fraction` bounds interact with `phone_duration_seconds`; the
  consistency rule (`max`) is a modeling approximation, not a simulation.

## Alternatives considered

- **Exponential distributions.** Memoryless and simple, but wrong shape for
  CAD work where the mode is far below the mean.
- **Normal distributions.** Symmetric tails would manufacture negative times
  and short calls that never happen in practice.
- **Fitted empirical distributions from source data.** Most accurate, but the
  source material is a small sample; a parametric lognormal per cell is the
  pragmatic middle ground, and the YAML override covers centers that want to
  drop in their own numbers.
