# ADR-0005: YAML-driven realism configuration with normalized weight tables

- Status: Accepted
- Date: 2026-08-04
- Deciders: Maintainers

## Context

AGENTS.md asks for realism "keyed by agency and priority" and "config-driven
design" — operators want to tune a generator to their own center without
editing Python. The realism surface is large: agency mix, priority mix, problem
types, call reception methods, dispositions, time profiles, dispatch
fractions, phone metrics, hourly call shape, seasonal multipliers, shift
structure, name locales.

Early versions hardcoded all of it in `constants.py` and validated with
ad-hoc checks. The recommendation docs explicitly call for YAML configuration
with sensible defaults and validation.

## Decision

- **Defaults live in `constants.py`** (`AGENCY_WEIGHTS`, `PRIORITY_WEIGHTS`,
  `PROBLEM_PROFILES`, `TIME_PROFILES`, `DISPATCH_INIT_FRACTION`,
  `HOURLY_WEIGHTS`, `PHONE_METRICS`, `SEASONAL_MULTIPLIERS`, …).
- **`RealismConfig` (slotted dataclass)** is the runtime container; an empty
  instance fills itself with the defaults (`__post_init__`). `from_yaml()` /
  `to_yaml()` round-trip every section through `yaml.safe_load`/`safe_dump`.
- **Every categorical distribution is a weight table** — agency, priority,
  reception method, disposition, and per-(agency, priority) problem pools all
  normalize to 1.0. `_normalize_weights()` rescales partial input so users can
  specify relative weights instead of exact sums, but `_validate()` rejects
  tables that do not sum to 1.0 after load and any unknown agency keys.
- **Validation is central and strict**: weight sums, required time-profile
  keys per agency/priority, `dispatch_init_fraction` bounds, phone-metric
  bounds, shift coverage (ADR-0008), and name-locale structure. A separate
  `synth911gen3 validate-config` CLI runs the same rules without generating
  data.
- **Pydantic mirrors the same structure** in `schema.py` for the public
  contract (ADR-0002); `tests/test_realism_config.py` and
  `tests/test_schema.py` pin both views.

## Consequences

### Positive

- Operators tune realism via YAML, not code; `config/example_realism.yaml`
  documents every section.
- Weight-table normalization is forgiving (relative weights accepted) but
  validated (bad tables fail loudly at load, not mid-generation).
- The round-trip (`to_yaml` → `from_yaml`) and the manifest hash (ADR-0007)
  both depend on a canonical serialization, which `to_yaml()` provides.

### Negative / Costs

- Every new realism knob must be added in four places: `constants.py`
  defaults, the dataclass + YAML round-trip, the pydantic mirror, and
  validation — plus tests.
- The dataclass mixes plain dicts, numpy arrays, and tuples
  (`dispatch_init_fraction` as `(lo, hi)` tuples), which makes
  `to_yaml`/`from_yaml` plumbing less uniform than a schema-first design.

## Alternatives considered

- **JSON config.** YAML won on readability, comments, and the existing tooling
  (`PyYAML`), and params files already cover JSON for automation.
- **Python-module config.** Compile-time evaluation is hostile to
  validate-config tooling and to users who shouldn't run code.
- **Schema-first (pydantic) as the one truth.** Rejected in ADR-0002 — the
  dataclass stays the runtime type for speed and simplicity, with the pydantic
  mirror only at the edges.
