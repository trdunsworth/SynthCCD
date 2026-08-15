# ADR-0010: Pluggable export layer with database targets

- Status: Accepted
- Date: 2026-08-09
- Deciders: Maintainers

## Context

AGENTS.md requires exporting to CSV, Parquet, pandas DataFrames, polars
DataFrames, or JSON/YAML "depending on the user's preference", and the future
work list adds geospatial formats and database targets. Format support
balloons fast: two tabular files, two in-memory formats, two serialized text
formats, two geospatial formats, five database dialects. Each format has its
own failure modes (missing optional deps, unsupported features, chunked
behavior).

The export path must: keep the generators format-agnostic, stream huge
datasets (ADR-0004), embed provenance (ADR-0007), and fail with actionable
messages when an optional dependency is missing.

## Decision

- **One `OutputFormat` enum** (StrEnum in `config.py`, mirrored in
  `schema.py`) enumerates every target: `csv`, `parquet`, `json`, `yaml`,
  `pandas`, `polars`, `geojson`, `shapefile`, `postgresql`, `sqlserver`,
  `mariadb`, `duckdb`, `sqlite`. The generators and `app.py` branch on it; the
  generators never touch the filesystem.
- **`exporters.py`** handles file and in-memory formats:
  - pandas/polars return objects in-memory (no files).
  - CSV/Parquet support both full-frame and chunked writes (ADR-0004);
    Parquet gets footer metadata via `pyarrow`'s `ParquetWriter`.
  - JSON/YAML bundle both datasets into one `{stem}_bundle.{json,yaml}` with
    datetimes normalized to ISO strings.
  - GeoJSON is RFC 7946 with Point geometry and full attribute fidelity;
    shapefile (ESRI) requires optional `geopandas`/`shapely` and raises a
    helpful `ExportError` with the install command when they're missing.
  - Non-spatial datasets under geospatial formats fall back to JSON.
- **`db_exporter.py`** targets five dialects — PostgreSQL (psycopg2),
  SQL Server (pyodbc), MariaDB/MySQL (pymysql), DuckDB (duckdb-engine), and
  SQLite (stdlib, zero extra deps). One `DatabaseExporter` handles
  table-exists/drop/index/type differences per dialect, batch inserts
  (`--db-batch-size`), `--db-if-exists` (append/replace/fail), and the
  SQLite bound-parameter cap (`999 // columns`). File-based dialects resolve
  `db_name` to `{stem}.duckdb`/`.sqlite3`; server dialects require
  host/name/user with default ports.
- **`app.py`** orchestrates: chunked path for CSV/Parquet, DB export for DB
  formats, manifest sidecar + Parquet metadata for file formats, and returns a
  `GenerationResult` with `exported_artifacts` for every consumer (CLI, TUI,
  API).
- **Dependency policy**: heavy optional integrations (geopandas, shapely,
  sqlalchemy, per-dialect drivers) are declared in `pyproject.toml` and
  imported lazily inside the exporters, so the core works with a lean install
  and the failures name the missing package.

## Consequences

### Positive

- Thirteen formats from one enum; adding a format touches exporters/app, not
  the generators.
- Optional deps degrade gracefully with install instructions, and SQLite
  works with no extra dependencies at all.
- Chunked + DB paths both stream, keeping memory bounded at scale.

### Negative / Costs

- The exporter modules carry dialect-specific branches (type mapping,
  placeholders, schema handling, index syntax) that are the densest, least
  testable-looking code in the package — the `tests/test_db_exporter.py`
  round-trip suite is the safety net.
- Shapefile's 10-character field-name limit silently truncates long column
  names; documented, but a known data-loss footgun.
- A growing optional-dependency surface complicates the dependency audit and
  Docker build; the audit script and CI gate exist to keep that honest.

## Alternatives considered

- **One exporter per format (full OO polymorphism).** Cleaner dispatch, but
  more plumbing for what is mostly `DataFrame.to_*` calls; the current
  function-per-format module keeps it flat.
- **Export everything through pandas/SQLAlchemy.** SQLAlchemy would flatten
  the five dialect branches but adds an abstraction layer and per-dialect
  engine quirks of its own; SQLite stays stdlib either way.
- **Push DB writes into the generators.** Rejected — the generators must stay
  format-agnostic for tests, previews, and in-memory use.
