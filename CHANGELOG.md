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

## [0.9.0] - 2026-08-10

### Added
- **Multi-agency assist problem types**: "Assist Police", "Assist Fire", "Assist EMS" added to problem profiles for all three agencies at priority 5, enabling cross-agency assist calls
- **Data governance manifest**: Sidecar `{output_stem}_manifest.json` with seed, config hash, schema hash, row/column counts, platform info, generation timestamp for reproducibility/auditing
- **Geospatial exports**: GeoJSON (RFC 7946) and ESRI Shapefile output formats with Point geometries from OSM coordinates; latitude/longitude added to Address model
- **Database streaming inserts**: Direct streaming to PostgreSQL (psycopg2), SQL Server (pyodbc), MariaDB/MySQL (pymysql), DuckDB (duckdb-engine); auto table creation, batch inserts, indexes on key columns
- **Seasonal correlations**: Per-problem seasonal multipliers (Winter/Spring/Summer/Fall) applied per-incident based on call month; configurable via realism YAML
- **Schema evolution**: Pydantic v2 models (`GenerationRequest`, `RealismConfig`, `ShiftConfig`, `Shift`, `TimeProfileIntervals`, `DispatchInitFraction`, `PhoneMetrics`, `OutputSchema`, `SchemaVersion`) with full validation; enums for all config types
- **Comprehensive documentation**: 5 tutorials (first dataset, tuning realism, large-scale cloud runs, geospatial analysis, database pipeline), full Python API reference, 50+ FAQ entries
- **Realism Tuning Guide**: SQL queries for parameter extraction from real CAD data, comparison methodology (KS-tests), common scenarios (rural, urban, college town, tourist), parameter sensitivity analysis

### Changed
- Documentation split: `USERSGUIDE.md` (user-facing) + `REALISMGUIDE.md` (realism configuration reference)
- Version bump to 0.9.0 (release candidate)

---

## [0.1.0] - 2026-08-09

Initial release candidate. All core AGENTS.md goals implemented.