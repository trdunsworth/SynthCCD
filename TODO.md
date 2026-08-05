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
- [ ] **P1 — Add a CI pipeline (GitHub Actions) that runs `pytest`, `ruff check .`,
      `ty check`, and the dependency audit on every push/PR.** `AGENTS.md` PR
      requirements reference "All CI checks must pass" but no CI workflow exists yet
      (`.github/` is absent).
- [x] **P1 — Add a dependency/security audit check.** Added `pip-audit` (dev group) and a
      wrapper script `scripts/audit_deps.py` (injects the OS trust store when
      `SYNTH911_SYSTEM_TRUST=1`). Ran it and fixed the findings: pinned `idna>=3.15`
      (PYSEC-2026-215) and `click>=8.3.3` (PYSEC-2026-2132). Audit is currently clean.
      Remaining: wire into CI (blocked on the CI item) and enable dependabot for
      `uv.lock`.
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

- [ ] **P1 — Implement GUID or integer incident ID option.** `AGENTS.md` goal: "Id number …
      either an integer or a GUID, depending on the user's preference." Currently only
      sequential integers are emitted (`incidents.py` `id_number`).
- [ ] **P1 — Add `incident_start_time` field** distinct from `call_start_time` by a 0–30 s
      offset (recommendation #13). Mirrors real CAD where the phone pickup precedes the CAD
      open timestamp.
- [ ] **P1 — Model parallel dispatch and call-taking timelines** (recommendation #8). High
      priority calls are dispatched while the call is still in progress; add a
      `dispatch_init_fraction` concept keyed by priority (see `docs/synth911gen_recommendations_ckaude2.md`).
- [ ] **P1 — Add postal code / directional / street-component address columns.** Current
      `Address` only stores `street_address`, `city`, `state` combined. AGENTS.md requires
      prefix directional, street number, name, type, postfix directional, and postal code.
      Extend `Address` domain model + OSM parsing + schema + exports.
- [ ] **P1 — Add a business/landmark indicator column.** AGENTS.md: "If an address is a
      business address or a known landmark then that should be reflected in a column on its
      own." Requires mapping `amenity`/`shop`/`tourism` OSM tags onto address results.
- [ ] **P2 — Make call reception and disposition use real CAD code vocabulary.** Currently
      plain-English strings ("911", "Report Issued"). Recommendation #11/#12 suggest
      E-911/OFFICER/Radio/C2C and code+label pairs (e.g., `NR-No Report`). Config-driven so
      deployments can match local CAD.
- [ ] **P2 — Priority-weighted problem selection.** `problem_nature` is currently chosen
      independently of `priority`; weight problem choice by priority so high-acuity problems
      are not uniformly likely at low priorities (recommendation #10).
- [ ] **P2 — Add hourly phone-metrics config for abandonment/volume rates.** Abandonment
      and volume factors in `phone_metrics.py` are hardcoded; expose them through
      `RealismConfig`/YAML.

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

- [ ] **P1 — Add `logging` throughout the app.** Replace bare `typer.echo` status with a
      proper logger (module + level + optional `-v/--verbose`), and a progress indicator for
      long address fetches and large generations.
- [ ] **P1 — Finish the TUI.** `tui.py` exposes only rows/area/format/dataset/stem/config.
      Add seed, date range, pool sizes, output dir, and validation feedback; surface the
      same realism-config fields as the CLI.
- [ ] **P2 — Implement the PyQt6 GUI** (AGENTS.md goal: "TUI or a GUI"). Requires re-adding
      the `pyqt6` dependency (removed in the dependency trim); a desktop GUI would serve
      non-technical operators.
- [ ] **P2 — Document/reconcile env vars.** `USERSGUIDE.md` documents `SYNTH911_SEED` and
      `SYNTH911_OUTPUT_DIR`, but neither is read anywhere in `src/` (verified). Either
      implement them in `config.py`/`cli.py` or remove from docs.
- [ ] **P2 — Split the oversized `USERSGUIDE.md`.** It is 880 lines; move realism details
      into a dedicated document and keep the guide to quick-start + CLI reference.
- [ ] **P2 — Provide a `--schema`/`--dry-run` CLI flag** to print the generated schema and a
      few sample rows without a full OSM fetch or long generation run.

---

## Testing / Quality

- [ ] **P1 — Enforce the 80% coverage requirement.** Add `pytest-cov` to dev deps and a
      `--cov` threshold; no coverage config exists despite the AGENTS.md requirement.
- [ ] **P1 — Add tests for `realism_config.py` round-trip (`to_yaml`/`from_yaml`) and
      weight-validation error paths.** Currently untested.
- [ ] **P1 — Add tests for `tui.py` request building and `addresses.py` cache
      invalidation/corruption paths.**
- [ ] **P2 — Clear the pre-existing `ty` diagnostics (22) and `docs/*` ruff errors.**
      `docs/` contains v2-era scripts (`synthgui.py`, `webgui.py`, `synth911.py`, …) that
      fail lint/type checks. Move them to a `docs/archive/` or exclude from lint scope and
      add an architecture decision note.
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
- [ ] **Parallel dispatch/call-taking timelines** — see Functionality above.
- [x] **Separate turnout and travel times** — done.
- [ ] **Priority-weighted problem selection** — see Functionality above.
- [ ] **Enhanced reception/disposition vocabularies** — see Functionality above.
- [ ] **Incident start time field** — see Functionality above.
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
