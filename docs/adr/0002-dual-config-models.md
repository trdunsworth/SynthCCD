# ADR-0002: Dual config models — pydantic for the public schema, slotted dataclasses for runtime

- Status: Accepted
- Date: 2026-08-09
- Deciders: Maintainers

## Context

Configuration flows through many surfaces: the CLI (Typer), the TUI (Textual),
params files (JSON/YAML/TOML), realism YAML files, the FastAPI serve endpoints,
and the Python API. Validation requirements grew beyond the original
hand-written checks in `config.py`: weight sums, date ranges, output-path
safety, database connection requirements, enum bounds.

Two styles were already in the tree: `config.py`/`realism_config.py` used
slotted dataclasses with manual `validate()` methods, and the serve layer
needed pydantic models for request parsing and OpenAPI generation. Keeping two
generators of truth (dataclass + pydantic re-declaration in `schema.py`)
duplicated every field three-plus times and invited drift.

## Decision

Keep both representations, with a deliberate division of labor:

- **Slotted dataclasses (`config.GenerationRequest`, `realism_config.RealismConfig`,
  `shifts.ShiftConfig`, `domain.*`)** remain the single runtime type. All
  generators, exporters, TUI, CLI, params, and manifest code operate on them.
  Validation stays in `GenerationRequest.validate()` /
  `RealismConfig._validate()`, which raise the package's own `ValidationError`.
- **Pydantic v2 models (`schema.py`)** are the *public contract*: they mirror
  the runtime types for the API surface (`/schema`, params-file schema, serve
  request models) and power OpenAPI docs. `schema.py` re-declares
  `GenerationRequest`, `RealismConfig`, `PhoneMetrics`, shift models, and the
  enums, with declarative `Field` constraints and `model_validator`s that
  reproduce the same rules.
- **No runtime path passes through pydantic.** Pydantic validation happens at
  the edges (API requests, schema export); generation always consumes the
  dataclass. The API layer converts pydantic models to the dataclass in
  `serve._build_request`.

## Consequences

### Positive

- Public schema is versioned, self-describing, and cheap to expose — OpenAPI,
  schema export, and manifest hashes come from one declarative source.
- Hot paths (10M-row runs) pay no pydantic overhead; runtime types stay fast,
  slotted, and hashable.
- Existing tests pin both sides: `tests/test_schema.py` (33 tests, 94%
  coverage) and `tests/test_realism_config.py` (33 tests, 100% coverage).

### Negative / Costs

- The field lists are duplicated between `config.py` and `schema.py`; adding a
  field means editing both plus tests. Drift between the two is the standing
  risk (the schema-export test suite is the net).
- `schema.py`'s `RealismConfig` mirrors the dataclass but is not the type the
  generators consume — a reader could reasonably expect otherwise.

## Alternatives considered

- **Pydantic everywhere.** Single source of truth, but adds runtime overhead
  on the hottest path and forces the whole package to depend on pydantic's
  validation model (including for the dataclass-heavy realism internals).
- **Dataclasses everywhere, hand-written API models.** Avoids the duplicate,
  but the serve layer loses free OpenAPI docs and the schema export feature
  (ADR-0007) loses its declarative backbone.
- **Runtime-to-pydantic conversion at module import.** Tried implicitly via
  `schema.py` importing constants; rejected because the cyclic dependency
  between `schema` and `config` made ordering fragile.
