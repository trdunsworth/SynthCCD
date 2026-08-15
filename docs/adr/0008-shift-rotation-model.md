# ADR-0008: Crew-rotation shift model with per-shift staffing

- Status: Accepted
- Date: 2026-08-07
- Deciders: Maintainers

## Context

Every incident must carry a calltaker, a dispatcher, and a shift label, and
realistic centers run crew rotations: the same personnel do not work every
hour. The realism recommendations ask for "shift structures" and "personnel
counts per shift" in config. The previous version's approach — a flat pool of
names assigned uniformly — could not express day/night crews, rotation cycles,
or per-shift staffing levels.

The generator must resolve, for any call timestamp, which shift is on duty and
which specific people staff it. Calls can land at any minute of any day across
a multi-year window, and the resolution must stay vectorizable (ADR-0001).

## Decision

- **`Shift`**: a named work block with a 24-hour start/end (an end earlier
  than the start means overnight), a `rotation` group id, and optional
  `calltakers`/`dispatchers` headcounts.
- **`ShiftConfig`**: a list of shifts plus a `rotation` sequence of group ids,
  one per calendar day, anchored at `cycle_start_weekday` (default Monday). A
  shift structure is valid only if each rotation group's shifts cover all 24
  hours (`_covers_full_day`) — so no call time can ever be uncovered.
- **Active-shift rule**: for a given moment, take the day's rotation group,
  then the covering shift in that group with the most recently started on-duty
  block (the shift that *just came on* wins ties). Scalar logic lives in
  `ShiftConfig.active_shift()`; the vectorized twin `_active_shift_index()`
  implements the same rule with array masks and a score matrix.
- **Presets**: four structures selectable via `--shift-preset` / TUI / params —
  `2x12h-4shift-14day` (default; A/B day + C/D night on a 14-day rotation),
  `2x12h-2shift`, `3x8h-3shift`, `4x10h-4shift` — each fully expressible as
  YAML through `shift_config` in the realism config.
- **Staffing**: shifts with explicit headcounts use them; shifts that omit
  them split the request's global pool totals (`_resolve_shift_staffing`).
  Each shift gets its own personnel pool (calltakers/dispatchers separately),
  and assignments within a pool are Zipf-weighted so a few people carry most
  of the workload (recommendation #4/#14).

## Consequences

### Positive

- Crew-rotation realism: night crews differ from day crews, and the 14-day
  pattern produces plausible staffing continuity.
- Validation is strong: a malformed structure that leaves an uncovered hour
  fails at config load, not at row 500,000 of generation.
- The vectorized resolver keeps shift resolution off the per-row path.

### Negative / Costs

- Two implementations of the same rule (scalar + vectorized) must not drift;
  the property tests and the active-shift tests pin both.
- `_covers_full_day` enforces coverage by *rotation group*, which is stricter
  than "someone is on duty" — a center that staffs sparse night coverage with
  on-call staff cannot express that here.
- Per-shift staffing defaults to a flat split when omitted; centers with
  asymmetric shifts must write explicit `calltakers`/`dispatchers` per shift.

## Alternatives considered

- **Single flat pool, uniform assignment (status quo).** No day/night
  distinction, no rotation — dropped when the recommendations demanded shift
  structures.
- **simpy queueing simulation of staff availability.** Captures occupancy and
  handoffs faithfully but is a runtime model, not a static assignment, and
  conflicts with the vectorized design; noted as future work in TODO.md.
- **Timezone/local-time resolution per shift.** Deferred (see ADR-0009); the
  current model resolves against a single local clock.
