# ADR-0009: Internationalization — emergency-number registry and locale-aware naming

- Status: Accepted
- Date: 2026-08-11
  (emergency-number registry landed 2026-08-10; locale-aware naming completed the decision 2026-08-11)
- Deciders: Maintainers

## Context

The schema hardcoded US/Canada 911 terminology: `nine_one_one_calls_received`,
`non_emergency_calls_received`. The generator is explicitly meant for
deployments worldwide (the name-locale work even covers Tokyo and Moscow), and
emergency numbers differ per country: 999/112 in the UK, 112/110 in Germany,
112 with a 15/17/18/196/191 family in France. Column names that say "911" are
wrong in those places.

Personnel names had the same US-centric assumption: a fixed `en_US` Faker
roster regardless of the region the addresses came from.

## Decision

- **`emergency_numbers.py` holds a registry** of 26 countries mapping to their
  short emergency numbers plus known 10-digit direct-dial lines. Resolution is
  driven by the request's `country` (ISO 3166-1 alpha-2), with overrides:
  `--emergency-numbers "999,112"` replaces the registry entry, and
  `--include-10-digit-emergency` appends the registry's 10-digit lines.
  Default remains US/CA → 911.
- **Column naming is dynamic**: `column_prefix(number)` maps a number to a
  snake_case prefix (`911` → `nine_one_one`, `999` → `nine_nine_nine`, a
  10-digit line → its digits), and `phone_metrics_columns()` builds the
  received/abandoned/answered-%-within columns per resolved number instead of
  hardcoding `nine_one_one_*`.
- **Per-line realism overrides**: the `phone_metric_lines` YAML section tunes
  received fraction, abandonment rate, night increment, and answer-time
  parameters independently per emergency number.
- **Country-matched personnel names**: address providers expose
  `resolved_country()` (persisted in the address cache's `.meta.json`,
  ADR-0003), which selects Faker locale blends from `COUNTRY_LOCALES` (equal
  weight per language, e.g. `en_CA` + `fr_CA` for Canada; a weighted
  multi-ethnic default for the US). The request's `country` is the fallback
  when the provider cannot tell. CJK locales flip to family-name-first order.
  The realism config can override per country via `name_locales`.

## Consequences

### Positive

- The output schema speaks the country's language: a `--country GB` run emits
  `nine_nine_nine_calls_received`, not a lie about 911.
- One code path serves all countries; new countries are a registry row plus
  locale entries, not a fork.
- Names match the geography the addresses came from, which matters for any
  training/evaluation use.

### Negative / Costs

- Dynamic column names complicate downstream consumers: schema, manifest hash,
  and tests all depend on the resolved registry, and `--schema` output changes
  with `--country`.
- `resolved_country()` depends on Nominatim address details; a failed or empty
  geocode degrades to the request's `country`, which may not match the actual
  area.
- `phone_metric_lines` keys are raw strings (numbers), so typos silently
  create orphan overrides instead of failing loudly.

## Alternatives considered

- **Global schema with `911` everywhere.** Rejected outright — it is factually
  wrong for non-US deployments and the TODO explicitly tracks this as a P2.
- **Locale bundles per country (data files).** More complete, but heavier than
  a registry + overrides; the registry pattern covers the common cases and
  lets users supply the rest via `--emergency-numbers` / `phone_metric_lines`.
- **Always emit both short-code and 10-digit columns.** Doubles the schema and
  models lines that most centers don't have; the opt-in
  `--include-10-digit-emergency` flag keeps the default clean.
