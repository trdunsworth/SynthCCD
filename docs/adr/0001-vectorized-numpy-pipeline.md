# ADR-0001: Vectorized NumPy pipeline for incident generation

- Status: Accepted
- Date: 2026-08-07
- Deciders: Maintainers

## Context

AGENTS.md requires generation from hundreds to millions of rows. The first
implementation of `generators/incidents.py` built records one row at a time in
a Python loop, drawing each value from Faker and numpy scalar calls. At scale
that measured ~335 µs/row — a 200k-row run took 67.1 s, and 1M rows was
minutes-to-hours territory with no bound on memory or wall time.

The lifecycle model complicates naive vectorization: agencies and priorities
are drawn per row, every timing value is a lognormal draw whose mean depends on
the (agency, priority) pair, call times must resolve to the active shift, and
reference numbers must be unique per agency per day. Column order and seeded
reproducibility were fixed requirements.

## Decision

Rewrite incident generation as a vectorized numpy pipeline that builds the
whole frame with array operations and no per-row Python loop:

- One `np.random.Generator` seeded from the request seed; every draw is a
  vectorized call (`rng.choice`, `rng.lognormal`, `rng.integers`,
  `rng.uniform`).
- Agency, priority, and problem selection via `rng.choice` with weight arrays;
  `agency_codes` becomes an index array used to look up per-row timing means
  from precomputed `(agency, priority)` tables.
- Call-start offsets drawn as one array, sorted, and converted to
  `datetime64[s]` once; all lifecycle timestamps are vector
  additions/subtractions of timedelta arrays.
- Active-shift resolution vectorized in `_active_shift_index`: rotation group
  via array indexing on days-since-epoch, coverage via boolean masks, and the
  "most recently started covering shift" rule via a score matrix.
- Reference numbers built with `np.char` string ops and per-agency running
  counters (`_build_reference_numbers`).
- Address and personnel sampling via `rng.integers` / `rng.choice` over object
  arrays; the frame is assembled once into a dict of arrays and converted to a
  single `pd.DataFrame`.

Chunked runs share one RNG across chunks so the stream is deterministic for a
given seed (see ADR-0004).

## Consequences

### Positive

- ~335 µs/row → ~7 µs/row on this machine; 200k rows in 1.16 s, 1M rows in
  ~7 s at ~514 MB.
- Column set, ordering, and seeded reproducibility were preserved; the whole
  test suite (including a regression baseline) passes unchanged.
- The array-shaped intermediates are the natural input for the memory-budget
  probe in ADR-0004.

### Negative / Costs

- The code reads like array algebra, not the CAD domain. `_active_shift_index`
  in particular needs the score-matrix trick to mirror the scalar
  `ShiftConfig.active_shift`; the two implementations must stay in lockstep
  (enforced by tests).
- Seasonal multipliers force a per-incident reweight loop (the base weights
  change per season), which is the last remaining Python-level inner loop and
  the obvious next vectorization target.
- Debugging distributions means reasoning about arrays, not individual rows.

## Alternatives considered

- **Per-row loop (status quo).** Simple and legible, but failed the scale
  requirement outright.
- **Multiprocessing / joblib over a row loop.** Kept the loop but added
  process overhead, pickling costs, and non-deterministic merge order unless
  results were sorted back — strictly worse than vectorizing.
- **Pure Faker row generation.** Rejected for the same scale reasons; Faker is
  retained only for personnel name generation (a per-shift pool, not per-row
  work).
