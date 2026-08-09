# CHANGELOG.md — Synth911Gen3

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- Initial project structure and synthetic 911 CAD/phone data generator
- Core incident generation with vectorized numpy pipeline (million-row scale)
- Realistic address generation via OpenStreetMap/Overpass (overpy)
- Config-driven realism via YAML (`RealismConfig`):
  - Priority-weighted time distributions (interview, dispatch, turnout, travel, scene, closeout, phone)
  - Agency-specific weights and display names (LAW/FIRE/EMS)
  - Per-priority problem profiles with weighted selection
  - Call reception methods (E-911, Phone, OFFICER, Radio, C2C, Text, CAD2CAD)
  - Disposition codes (NR-No Report, RE-Report, CI-Citation, CN-Cancellation, etc.)
  - Hourly call volume patterns (diurnal weights)
  - Phone metrics (abandonment rates, volume fractions, weekend multiplier)
  - Dispatch initiation fractions by priority
  - Shift configurations (presets: 2x12h-4shift-14day, 2x12h-2shift, 3x8h-3shift, 4x10h-4shift)
- Personnel modeling:
  - Separate calltaker/dispatcher pools per shift
  - Zipf-like workload weighting
  - Per-shift staffing from `shift_config`
- Incident ID formats: integer (sequential) or GUID (seeded UUID v4)
- `incident_start_time` field distinct from `call_start_time` (0-3s offset)
- Parallel dispatch/call-taking timelines via `dispatch_init_fraction`
- Full address components: street_number, street_name, street_type, prefix_directional, postfix_directional, city, state, postal_code
- Memory-budget guard with chunked CSV/Parquet export (`max_memory_bytes`)
- CLI with Typer: generate, schema, dry-run, config file support, params file (JSON/YAML/TOML)
- TUI with Textual: live progress, field validation, params loading, worker-thread generation
- Structured logging (`SYNTH911_LOG_LEVEL`, `--verbose/-v`, `--quiet/-q`)
- `--schema` and `--dry-run` flags for preview without full generation
- TLS trust store injection for corporate proxies (`SYNTH911_SYSTEM_TRUST=1`)
- FastAPI REST API server (`synth911gen3 serve`) with endpoints: `/health`, `/schema`, `/generate`, `/generate/stream`
- Multi-stage Docker build with non-root user, health checks, and persistent volumes
- Docker Compose for API server and one-off generation jobs
- Pydantic models for request validation

### Changed
- N/A (initial release)

### Deprecated
- N/A

### Removed
- Unused runtime dependencies: pydantic, requests, scipy, rich, prompt_toolkit, inquirerpy, pyqt6

### Fixed
- Path traversal validation for `output_dir`/`output_stem`
- OSM Nominatim rate limiting with retry/backoff
- Type safety across source code (`ty check src/` passes)

### Security
- Dependency audit with pip-audit in CI
- Pinned `idna>=3.15` (PYSEC-2026-215) and `click>=8.3.3` (PYSEC-2026-2132)

---

## [0.1.0] - 2026-08-09

Initial release candidate. All core AGENTS.md goals implemented.