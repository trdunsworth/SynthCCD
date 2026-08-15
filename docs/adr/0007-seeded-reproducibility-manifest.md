# ADR-0007: Deterministic generation and provenance manifest

- Status: Accepted
- Date: 2026-08-09
  (manifest sidecar; Parquet footer metadata followed 2026-08-11, regression baseline 2026-08-14)
- Deciders: Maintainers

## Context

Synthetic data is only useful for testing, training, and auditing if a run can
be reproduced exactly and its provenance can be proven. AGENTS.md's data
governance goals and the previous-version recommendations both demand
reproducibility: the same parameters must produce the same rows, and every
artifact must record how it was made.

The generator mixes several RNG sources (numpy for arrays, `random` for GUIDs,
Faker for names) across multiple stages (address cache, personnel pools,
incident draws, phone metrics), which makes reproducibility a deliberate
engineering choice rather than an accident.

## Decision

- **One seed, propagated everywhere.** `GenerationRequest.seed` (default 911)
  seeds a single `np.random.Generator` for the incident stream, a
  `random.Random` for GUID generation, and the `PersonnelNameGenerator`'s
  Faker instance. The chunked path reuses one numpy RNG across chunks; only
  the memory probe gets a derived seed (seed + 1001) so it cannot disturb the
  stream (ADR-0004).
- **Deterministic reference numbers.** `internal_reference_number` is
  `{AGENCY}-{YYMMDD}-{6-digit per-agency daily counter}` — a function of the
  row's agency, date, and position in the stream, so it needs no global RNG
  state.
- **Manifest sidecar.** Every file-based export writes
  `{output_stem}_manifest.json` with the full run signature: seed, rows,
  dataset, format, area, date range, ID format, personnel pools, shift preset,
  `realism_config_hash` (SHA-256 of the canonical YAML), `schema_hash`
  (SHA-256 over sorted `column:dtype` pairs), schema version, row/column
  counts, package version, Python version, platform, and UTC timestamp.
- **Parquet self-documentation.** The manifest flattens to namespaced
  `synth911:*` key-value pairs embedded in every Parquet file's footer
  metadata, so files carry their own provenance even when the sidecar is lost
  or the file is copied.
- **Regression baseline.** `tests/regression_baseline.json` commits a
  statistical signature (fractions, per-cell timing means, diurnal shape,
  phone rates) generated from a fixed seed; `tests/test_regression.py`
  regenerates and compares within tolerances, turning accidental realism drift
  into a failing test (see also ADR-0006).

## Consequences

### Positive

- Identical seed + params + config + package version ⇒ byte-identical output;
  this is exercised by the full test suite and the `--save-params` /
  `--schema` CLIs round-tripping requests.
- The manifest and Parquet metadata give auditors a complete, machine-readable
  account of every run.
- The regression baseline makes "did realism change" a question the CI answers.

### Negative / Costs

- Reproducibility is version-sensitive: a new pandas/numpy release or a
  changed default can break byte-identity even with the same seed. The
  manifest records versions, so the break is *explainable* even when not
  avoidable.
- Two hashes (config, schema) must stay in sync across three writers:
  manifest, Parquet metadata, and `synth911gen3 schema` export — any of them
  drifting breaks tests.
- `generated_at` and `row_counts` are by definition not reproducible; the
  manifest distinguishes the reproducible signature (seed, hashes) from the
  run facts (timestamp, counts).

## Alternatives considered

- **No manifest, rely on git history.** Useless for generated artifacts; the
  whole point is provenance at the file, not the repo.
- **Only a sidecar JSON.** Fine until someone copies a Parquet file out of the
  output folder; the footer metadata was added precisely because that happens.
- **Embed the full params in every file.** Clutters footers and bloats output;
  the hash + seed pair is the compact, verifiable middle ground.
