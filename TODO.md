# TODO.md — Synth911Gen3 Backlog

Priorities use **P0** (must fix before release), **P1** (should have), **P2** (nice to have).
Items are sourced from `AGENTS.md` goals, the realism-improvement list, the previous-version
recommendation docs in `docs/`, and direct code review.

---

## Security

- [x] **P0 — Add `.gitignore` and untrack build artifacts.** Added `.gitignore` covering
      `.venv/`, `__pycache__/*.pyc`, `.pytest_cache/`, `.ruff_cache/`, `.DS_Store`,
      `output/*`, and IDE files; ran `git rm --cached` on the tracked artifacts (files
      remain on disk). Verified with `git check-ignore`; no artifacts remain in the index.
- [x] **P1 — Add a CI pipeline (GitHub Actions) that runs `pytest`, `ruff check .`,
      `ty check`, and the dependency audit on every push/PR.** Added
      `.github/workflows/ci.yml` (setup-uv + Python 3.12, `uv sync --locked`, ruff, ty,
      pytest, `scripts/audit_deps.py`) triggered on pushes to `main` and all PRs. To make
      the gate pass: fixed the 8 pre-existing `ty` diagnostics in `addresses.py` and
      excluded read-only `docs/` scripts from ruff scope in `pyproject.toml`.
- [x] **P1 — Add a dependency/security audit check.** Added `pip-audit` (dev group) and a
      wrapper script `scripts/audit_deps.py` (injects the OS trust store when
      `SYNTH911_SYSTEM_TRUST=1`). Ran it and fixed the findings: pinned `idna>=3.15`
      (PYSEC-2026-215) and `click>=8.3.3` (PYSEC-2026-2132). Audit is currently clean
      and wired into the CI gate via `scripts/audit_deps.py`. Remaining: enable
      dependabot for `uv.lock` (GitHub dependabot has no native `uv.lock` support; a
      `pip`-ecosystem config for `pyproject.toml` is the closest option).
- [x] **P1 — Trim unused runtime dependencies.** Removed from `pyproject.toml`:
      `pydantic`, `requests`, `scipy`, `rich`, `prompt_toolkit`, `inquirerpy`, `pyqt6`.
      `pyarrow` was kept (needed transitively for `pandas.to_parquet`).
      > Note: re-add `pyqt6` when the PyQt6 GUI is implemented.
- [x] **P2 — Validate `output_dir`/`output_stem` against path traversal and reserved
      names.** Added `_validate_output_path()` to `config.py` (rejects empty/`.`/`..`
      stems, separators and null bytes, `..` segments and null bytes in `output_dir`,
      and Windows reserved device names like `CON`/`NUL`/`COM1`); wired into
      `GenerationRequest.validate()`; covered by `tests/test_config.py`.
- [x] **P2 — Add timeouts and user-agent checks to address caching.** OSM Nominatim usage
      policy requires identifying User-Agent (present) and gentle rate limiting; added a
      shared `_nominatim_get()` helper that enforces a minimum 1 s request interval and
      retries 429/5xx with `Retry-After`-aware exponential backoff. Covered by
      `tests/test_addresses.py`.

---

## Functionality (AGENTS.md goal gaps)

- [x] **P1 — Implement GUID or integer incident ID option.** `AGENTS.md` goal: "Id number …
      either an integer or a GUID, depending on the user's preference." Added an `IdFormat`
      enum (`integer`/`guid`) wired through `GenerationRequest`, the `--id-format` CLI flag,
      the TUI ID-format select, and params files; GUIDs are seeded UUID v4 values via Faker
      so output stays reproducible.
- [x] **P1 — Add `incident_start_time` field** distinct from `call_start_time`. Added a
      `pre_cad_offset_seconds` draw (0–3 s, the CAD record opens a moment after the call is
      received) and the resulting `incident_start_time` column; covered by tests and
      documented in the schema.
- [x] **P1 — Model parallel dispatch and call-taking timelines** (recommendation #8). High
      priority calls are dispatched while the call is still in progress via a configurable
      `dispatch_init_fraction` keyed by priority (fractions < 1.0 dispatch mid-call,
      >= 1.0 defer until after the call ends).
- [x] **P1 — Add postal code / directional / street-component address columns.** Extended
      the `Address` model with `street_number`, `street_name`, `street_type`,
      `prefix_directional`, `postfix_directional`, and `postal_code` (auto-parsed from the
      street string, with OSM `addr:postcode` preserved through the cache); wired the
      components into the incident schema, OSM parsing, cache, and docs.
- [ ] **P1 — Add a business/landmark indicator column.** AGENTS.md: "If an address is a
      business address or a known landmark then that should be reflected in a column on its
      own." Requires mapping `amenity`/`shop`/`tourism` OSM tags onto address results.
- [x] **P2 — Make call reception and disposition use real CAD code vocabulary.** Reception
      methods now use E-911/Phone/OFFICER/Radio/C2C/NOT CAPTURED/Text/CAD2CAD and dispositions
      use code+label pairs (e.g., `NR-No Report`, `RE-Report`, `CI-Citation`),
      agency-calibrated and config-driven (recommendation #11/#12).
- [x] **P2 — Priority-weighted problem selection.** `problem_profiles` now split into per-
      priority pools (`{agency: {priority: [(name, weight)]}}`); after selecting priority,
      the problem is drawn only from the matching pool so high-acuity problems are not
      likely at low priorities (recommendation #10).
- [x] **P2 — Add hourly phone-metrics config for abandonment/volume rates.** Abandonment
      and volume factors in `phone_metrics.py` are now exposed through the `phone_metrics`
      section of `RealismConfig`/YAML (volume fractions, abandonment rates, night
      increment, max abandonment, weekend multiplier).

---

## Performance / Scalability

- [ ] **P1 — Vectorize incident generation for million-row scale.** `incidents.py` builds
      records in a Python `for` loop (one dict per row). At 10⁶ rows this is slow and
      memory-heavy. Replace per-row sampling with vectorized `numpy`/`polars` operations
      (numpy choice by agency/priority/problem, batched lognormal draws), then build the
      frame once.
- [ ] **P2 — Add a memory-budget guard / chunked export.** For very large datasets, write
      CSV/Parquet incrementally instead of holding the full frame in memory.

---

## Usability

- [x] **P1 — Add `logging` throughout the app.** Added `logging_conf.py` (package-scoped
      loggers, `configure_logging` with `--verbose/-v` and `--quiet/-q` global CLI flags and
      `SYNTH911_LOG_LEVEL` env support, plus a `ProgressReporter` that logs 5% completion steps
      for runs over 10k rows). Instrumented `app.py`, `incidents.py`, `phone_metrics.py`,
      `addresses.py`, `exporters.py`, and `cli.py`; status summaries still print via `typer.echo`
      while granular detail goes to the stderr logger.
- [x] **P1 — Finish the TUI.** Reworked `tui.py`: generation now runs on a Textual worker
      thread (UI stays responsive) with a live `ProgressBar` driven by a new
      `on_progress` hook threaded through `Synth911Application`/`IncidentGenerator`; fields are
      grouped into General/Geography/Personnel/Configuration sections with themed CSS; invalid
      fields are highlighted with an error border via aggregated `FieldValidationError`
      feedback (cleared on edit); status panel colors info/success/error states. The TUI
      already exposed seed, date range, pool sizes, output dir, and the realism-config path.
- [ ] **P2 — Implement the PyQt6 GUI** (AGENTS.md goal: "TUI or a GUI"). Requires re-adding
      the `pyqt6` dependency (removed in the dependency trim); a desktop GUI would serve
      non-technical operators.
- [x] **P2 — Document/reconcile env vars.** `USERSGUIDE.md` previously documented `SYNTH911_SEED` and
      `SYNTH911_OUTPUT_DIR`, but neither is read anywhere in `src/` (verified). Removed both rows from
      the env-var table, leaving only the implemented `SYNTH911_LOG_LEVEL` (and the documented
      `SYNTH911_SYSTEM_TRUST` TLS flag in Troubleshooting).
- [x] **P2 — Split the oversized `USERSGUIDE.md`.** It was ~1000 lines; moved all realism
      content (YAML realism configuration reference and default distribution tables) into a
      new companion `REALISMGUIDE.md` and kept the user guide to quick-start, CLI reference,
      params files, output formats, schema, examples, and troubleshooting, with cross-links
      between the two documents.
- [ ] **P2 — Provide a `--schema`/`--dry-run` CLI flag** to print the generated schema and a
      few sample rows without a full OSM fetch or long generation run.

---

## Testing / Quality

- [ ] **P1 — Enforce the 80% coverage requirement.** Add `pytest-cov` to dev deps and a
      `--cov` threshold; no coverage config exists despite the AGENTS.md requirement.
- [ ] **P1 — Add tests for `realism_config.py` round-trip (`to_yaml`/`from_yaml`) and
      weight-validation error paths.** Currently untested.
- [x] **P1 — Add tests for `tui.py` request building and `addresses.py` cache
      invalidation/corruption paths.** `test_tui.py` covers request building,
      defaults/customs, invalid-int/date field validation, aggregated
      `FieldValidationError`, params loading, reset, and worker generation;
      `test_addresses.py` now covers `_load_cache` returning `None` for missing,
      corrupt, and below-minimum frames, plus `load_addresses` recovering from a
      corrupt cache and refetching when the cached frame is below the minimum.
- [ ] **P2 — Clear the remaining pre-existing `ty` diagnostics and `docs/*` ruff errors.**
      `docs/` contains v2-era scripts (`synthgui.py`, `webgui.py`, `synth911.py`, …) that
      fail lint/type checks. The 8 `ty` diagnostics in `addresses.py` were fixed (Dec 2026)
      and `docs/` is now excluded from ruff scope; remaining: add an architecture decision
      note for the exclusion, and decide whether to move the scripts to `docs/archive/`.
- [ ] **P2 — Add a CHANGELOG and version bump discipline** (semver), wired to the `0.1.0`
      version in `pyproject.toml`.

---

## Realism Improvements (from AGENTS.md list)

- [x] **Priority-weighted time distributions** — done via `TIME_PROFILES`.
- [ ] **Config-driven design — complete the section set.** `RealismConfig` supports agency
      names, weights, problem/disposition/reception profiles, and time profiles, but the
      AGENTS.md list also names **shift structures, geographic zones, and personnel counts
      per shift** — none are implemented yet.
- [x] **Enhanced address generation via overpy/Overpass** — done.
- [ ] **Personnel modeling — workload weighting + ASCII normalization + late-shift penalty.**
      Pools are separate, but assignment is uniform random; add Zipf-like weighting and a
      late-shift dispatch-time penalty (recommendation #4, #14).
- [x] **Diurnal call volume patterns** — done via `hourly_weights`.
- [ ] **Geographic zone multipliers** (URBAN/SUBURBAN/RURAL) applied to travel time.
- [x] **Parallel dispatch/call-taking timelines** — see Functionality above.
- [x] **Separate turnout and travel times** — done.
- [x] **Priority-weighted problem selection** — see Functionality above.
- [x] **Enhanced reception/disposition vocabularies** — see Functionality above.
- [x] **Incident start time field** — see Functionality above.
- [ ] **Configurable personnel assignment with workload distribution** — see Personnel above.

---

## Future Expansion Opportunities

- **Multi-agency incidents & unit counts.** Add `num_units`/`units_available` and allow one
  incident to spawn LAW+FIRE+EMS records (mutual aid / multi-agency responses).
- **Cadence/queueing simulation.** The recommendation docs propose a constrained simulation
  (unit availability queues, simpy). Worth prototyping for dispatch realism at P2/P3.
- **Weather and seasonal correlation** (heat → heat-related EMS, winter → slip/fall).
- **Geospatial exports** (GeoJSON / shapefile) alongside tabular formats, using address
  coordinates cached from OSM.
- **Timezone-aware timestamps** and non-UTC/hourly-metric localization for deployments
  outside one timezone.
- **Database targets** (SQLite/Postgres) and streaming insert for very large datasets.
- **Data governance manifest.** Emit a sidecar metadata file (seed, params, config hash,
  schema version, generation timestamp) with every export for reproducibility/auditing.
- **`config/example_params` parity.** Add a TOML example alongside JSON/YAML, and a
  params-driven CI regression run.
- **Packaging/distribution.** Publish on PyPI and/or containerize; add a `uv.lock`-driven
  Docker build and a `synth911gen3 serve` (FastAPI) entrypoint for a hosted API.
- **Schema evolution** (pydantic models for `GenerationRequest`/`RealismConfig`) to
  formalize validation and produce versioned output schemas.
- **Long-form user's guide.** `USERSGUIDE.md` / `REALISMGUIDE.md` currently cover quick
  start, CLI, configuration, and realism defaults. A fuller "getting started" guide with
  tutorials (first 911 dataset, tuning realism to a center, large-scale cloud runs) plus a
  reference-style API section and FAQ would serve new operators end-to-end.
