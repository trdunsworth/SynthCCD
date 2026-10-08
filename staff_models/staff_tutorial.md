# Staffing Models Tutorial

This guide covers the staffing-model scripts in `staff_models/`, how to run
them through the evaluation TUI, and how each model maps to real PSAP
workload types.

## Quick start

```bash
uv run python staff_models/tui.py
```

The TUI lets you:

1. **Pick a model** from the *Model* dropdown.
2. **Edit parameters** — the parameter list rebuilds for each model; leave a
   field blank to use its default.
3. **Pick an output format** — `markdown` or `carve` (the Carve markup
   language from markup-carve/carve).
4. **Run** — the report (parameters + metrics) appears in the results pane.

Each model script is also standalone, e.g. `uv run python staff_models/erlang_c.py`,
which prints a demo with example parameters.

## Model reference

### Erlang B (`erlang_b`)
Loss system: blocked calls are lost, no queue. Inputs: `erlangs`,
`servers`. Outputs: blocking probability, trunk count for ≤1% blocking.
**Use for:** trunk/port sizing where unanswered calls do not queue (e.g.,
dedicated radio channels, NCIC query circuits treated as lossy resources).

### Erlang C (`erlang_c`)
Delay system: all calls queue, none abandon. Inputs: `erlangs`, `servers`,
`mean_handle_seconds`, `threshold_seconds`. Outputs: wait probability, ASA
for delayed callers, service level at the threshold. **Use for:** the
baseline sizing of a queued answering point (non-emergency line, NCIC unit)
when abandonment is ignored.

### Erlang A (`erlang_a`)
Erlang C plus exponential caller patience. Inputs: `lam_per_sec`,
`mean_handle_seconds`, `agents`, `mean_patience_seconds`. Outputs: delay
probability, abandonment probability, mean wait (overall and delayed),
occupancy. **Use for:** 9-1-1 and SMS/RTT lines where callers hang up; the
abandonment term directly models "caller cleared before answer."

### Engset (`engset`)
Finite-source loss model. Inputs: `sources`, `servers`, `gamma_over_mu`.
Outputs: time congestion, call congestion, carried traffic. **Use for:**
radio dispatching, where a *finite* fleet of field units contends for a
bounded set of channels, and unit-in-use sources cannot generate new calls.

### M/M/c/K (`mm_c_k`)
Finite-capacity queue: waiting room is bounded, overflow is blocked.
Inputs: `erlangs`, `servers`, `capacity`. **Use for:** any line with a
finite spill/backup queue, e.g. RTT queue depth limited by queue software.

### Allen-Cunneen (`allen_cunneen`)
M/G/c approximation scaling Erlang C by service-time variability.
Inputs: Erlang C params plus `scv` (squared coefficient of variation of
handle time). **Use for:** workloads with non-exponential handle times —
real CAD events range from seconds (hang-up) to tens of minutes (major
incidents), so this is usually more accurate than raw Erlang C.

### Erlang R (`erlang_r`)
Loss system with reattempts: blocked callers retry with probability `r`,
inflating offered load. Inputs: `lam_per_sec`, `mean_handle_seconds`,
`servers`, `retry_probability`. **Use for:** high-load conditions on the
9-1-1 trunk group, where failed callers immediately redial (call bursts).

### PSA (`psa`)
Pointwise stationary approximation for intraday staffing: Erlang C service
level computed at each interval's arrival rate. Inputs:
`rates_per_sec` (comma-separated), `mean_handle_seconds`,
`threshold_seconds`, `target_sl`. **Use for:** building an hourly
seating plan for each PSAP queue from its arrival-rate profile.

### Occupancy (`occupancy`)
Utilization floor: smallest staff for a target occupancy. Inputs:
`erlangs`, `target_occupancy`. **Use for:** a sanity floor under more
sophisticated models; never a service-level guarantee by itself.

### Square-root / QED (`square_root`)
Halfin-Whitt staffing: `c = R + β√R`. Inputs: `erlangs`, `beta`. **Use
for:** near-capacity staffing of large centres; β tunes the balance of
occupancy vs. delay in 9-1-1 answering.

### EFPA (`efpa`)
Erlang fixed-point approximation for skill-based routing, where routes
(call types) share agent pools. Input: `network_json`:

```json
{"capacities": [20, 15, 25],
 "routes": [{"name": "law", "erlangs": 12.0, "links": [0, 2]},
             {"name": "fire", "erlangs": 8.0, "links": [1, 2]},
             {"name": "ems_shared", "erlangs": 5.0, "links": [2]}]}
```

Outputs: per-pool blocking, per-route blocking and carried erlangs. **Use
for:** agency/skill-based routing (law/fire/EMS/NCIC sharing the same
console pool) and multi-PSAP overflow agreements.

## Mapping to PSAP workloads

| Workload | Best-fit models | Rationale |
|---|---|---|
| 9-1-1 emergency calls | Erlang C, Erlang A, square-root, PSA, Erlang R | Queued, abandonment-sensitive, subject to caller redial bursts, high-stakes SL |
| Non-emergency lines | Erlang C, Allen-Cunneen, occupancy, PSA | Longer AHT, tolerant of waits, strong diurnal pattern |
| SMS / RTT text | Erlang A, M/M/c/K | Callers abandon after minutes; bounded software queue; slower handling |
| Radio dispatch | Engset, Erlang B, EFPA | Finite fleet, channels as lossy trunks, shared talkgroups |
| NCIC / database comms | Engset, Erlang B, Erlang R | Query circuits modeled as finite-source loss or retry-prone channels |

Combined PSAP reality is multi-queue and skill-routed; run EFPA with pools
as console groups and routes as queue types above, feed each pool's traffic
parameters from the single-queue models, and use PSA on top for the
intraday profile.

## Adding a new model

1. Drop a script in `staff_models/` with typed functions and a docstring.
2. Add a `ModelSpec` entry in `runner.py` (params + `run` callable).
3. It appears automatically in the TUI and renders to both formats.
