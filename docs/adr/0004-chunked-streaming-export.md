# ADR-0004: Memory-bounded chunked generation and streaming export

- Status: Accepted
- Date: 2026-08-07
- Deciders: Maintainers

## Context

ADR-0001 made generation fast, but a 1M-row DataFrame still costs ~514 MB —
and users can ask for 10M+. Holding the full frame in memory and exporting at
the end caps the useful dataset size at whatever the machine can spare. AGENTS.md
requires scaling "from hundreds to millions of rows", and the streaming API
(`/generate/stream`) wants to hand data out incrementally.

The existing `generate()` builds one frame and returns it; exporters write it
in one shot. Adding a chunked path must not change seeded output for
single-chunk runs, must keep `id_number` globally sequential, and must keep
`internal_reference_number` unique per agency across chunk boundaries.

## Decision

Add a memory-budget guard and a chunked pipeline:

- `GenerationRequest.max_memory_bytes` (default 2 GiB) is the per-chunk budget,
  exposed via CLI (`--max-memory-bytes`), TUI, params files, and the API.
- `IncidentGenerator.resolve_chunk_rows()` probes the pipeline on a small
  sample (`MEMORY_PROBE_ROWS`, default 10k) with a **separate RNG**
  (seed + 1001) so the probe does not consume the seeded generation stream,
  measures bytes/row via `DataFrame.memory_usage(deep=True)`, and derives the
  chunk size = `budget / bytes_per_row`.
- `generate_chunks()` yields one DataFrame per chunk from `_build_records()`,
  sharing a single RNG across chunks. `id_number` continues from a
  `start_index`; per-agency reference-number counters are threaded through
  `start_counts`, so uniqueness holds across the whole stream.
- `exporters.export_chunked_generator()` writes CSV (header on first chunk,
  append after) or Parquet (one `pyarrow.parquet.ParquetWriter` for the whole
  stream), materializing only one chunk at a time.
- `app.py` routes CSV/Parquet incident generation through the chunked path
  whenever the request would exceed the budget; single-chunk output is
  byte-identical to the non-chunked path.

## Consequences

### Positive

- Peak memory is bounded by `max_memory_bytes` regardless of total row count;
  10M-row runs are feasible on a laptop.
- The streaming API (`/generate/stream`) and future pipeline integrations
  reuse the same iterator.
- Determinism holds: same seed + same chunk plan → identical stream; a
  single-chunk run is byte-identical to `generate()`.

### Negative / Costs

- The chunked path is CSV/Parquet-only; JSON/YAML/geospatial exports still
  materialize the full frame.
- Chunk size is an estimate from a probe; pathological column-width variation
  (long names, long streets) can slightly exceed or under-shoot the budget.
- Reference-number counters and the shared RNG add state to `_build_records`
  that a reader must thread carefully.

## Alternatives considered

- **Single full-frame generate (status quo).** Simple, correct, memory-bound
  at ~514 MB/M rows.
- **Memory-mapped / out-of-core frames everywhere (dask/polars lazy).** Heavy
  new dependency and a second execution model for marginal gain over a plain
  iterator.
- **Export-then-generate (writer pulls from the RNG).** Inverted control makes
  the seeded stream harder to reason about and would complicate the manifest's
  need for full-frame statistics.
