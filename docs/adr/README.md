# Architecture Decision Records

This directory records the significant architecture decisions made for
synth911gen3. An ADR captures a decision, the context that forced it, and the
consequences — so future maintainers can see *why* the code is the way it is,
even when the alternatives look reasonable at a glance.

## Format

Each record follows a lightweight, Nygard-style template:

- **Status** — Accepted / Proposed / Superseded by ADR-xxxx
- **Date** — when the decision was made; for retrospective records, the date the
  decision landed in the codebase (git history is the source of truth)
- **Deciders** — who made it (default: maintainers)
- **Context** — the problem or constraint that forced a decision
- **Decision** — what was decided, in plain terms
- **Consequences** — positive and negative outcomes, plus costs
- **Alternatives considered** — the options that lost, and why

Records are numbered sequentially and never renumbered. When a decision
changes, write a new ADR that supersedes the old one and update the old
record's Status field to point at it.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-vectorized-numpy-pipeline.md) | Vectorized NumPy pipeline for incident generation | Accepted |
| [0002](0002-dual-config-models.md) | Dual config models: pydantic for the public schema, slotted dataclasses for runtime | Accepted |
| [0003](0003-osm-address-provider.md) | OpenStreetMap as the address source, cached as Parquet | Accepted |
| [0004](0004-chunked-streaming-export.md) | Memory-bounded chunked generation and streaming export | Accepted |
| [0005](0005-yaml-realism-config.md) | YAML-driven realism configuration with normalized weight tables | Accepted |
| [0006](0006-lognormal-time-profiles.md) | Lognormal timing models calibrated per agency and priority | Accepted |
| [0007](0007-seeded-reproducibility-manifest.md) | Deterministic generation and provenance manifest | Accepted |
| [0008](0008-shift-rotation-model.md) | Crew-rotation shift model with per-shift staffing | Accepted |
| [0009](0009-internationalization.md) | Internationalization: emergency-number registry and locale-aware naming | Accepted |
| [0010](0010-pluggable-export-layer.md) | Pluggable export layer with database targets | Accepted |

## How to add a record

1. Pick the next free number and a short kebab-case filename.
2. Fill in the template above. Keep Context and Consequences honest; the
   record's value decays with its length.
3. Add a row to the Index table.
4. Mark the corresponding TODO item done, and note the ADR in CHANGELOG.md
   under [Unreleased] → Added.
