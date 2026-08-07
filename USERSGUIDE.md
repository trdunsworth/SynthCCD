# synth911gen3 User Guide

A synthetic data generator for 9-1-1 CAD incidents and hourly phone-center metrics.

## Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [Command-Line Interface (CLI)](#command-line-interface-cli)
4. [Textual User Interface (TUI)](#textual-user-interface-tui)
5. [Configuration Parameters](#configuration-parameters)
   - [Personnel and Shift Parameters](#personnel-and-shift-parameters)
   - [Shift Structures](#shift-structures)
6. [Params Files (Bundled Options)](#params-files-bundled-options)
7. [Output Formats](#output-formats)
8. [Generated Data Schema](#generated-data-schema)
9. [Examples](#examples)
10. [Troubleshooting](#troubleshooting)
11. [Advanced Configuration](#advanced-configuration)

Statistical realism details — the default distributions and the YAML realism
configuration — are documented in the companion [Realism Guide](REALISMGUIDE.md).

---

## Installation

```bash
# Clone the repository
git clone https://github.com/trdunsworth/synth911gen3.git
cd synth911gen3

# Create virtual environment and install dependencies
uv venv
uv sync

# Activate environment (Linux/macOS)
source .venv/bin/activate

# Activate environment (Windows PowerShell)
.venv\Scripts\Activate.ps1
```

---

## Quick Start

Generate default datasets (10,000 incidents + hourly phone counts) as CSV files in `output/`:

```bash
uv run synth911gen3 generate
```

Launch the interactive TUI:

```bash
uv run synth911gen3 tui
```

---

## Command-Line Interface (CLI)

### Main Commands

| Command | Description |
|---------|-------------|
| `generate` | Generate synthetic datasets |
| `tui` | Launch the Textual TUI |

### Generate Command Options

```bash
uv run synth911gen3 generate [OPTIONS]
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--params` | `-p` | *(none)* | Path to a JSON/YAML/TOML file specifying multiple generation parameters at once |
| `--rows` | `-r` | `10000` | Number of incident rows to generate (minimum: 1) |
| `--area` | `-a` | `"Kansas City, MO"` | Area query for OpenStreetMap address lookup |
| `--format` | `-f` | `csv` | Output format: `csv`, `parquet`, `json`, `yaml`, `pandas`, `polars` |
| `--dataset` | `-d` | `all` | Dataset to generate: `incidents`, `phone`, `all` |
| `--id-format` | | `integer` | id_number style: `integer` or `guid` |
| `--output-dir` | `-o` | `output` | Directory for exported files |
| `--output-stem` | `-s` | `synthetic_911` | Filename prefix for exported files |
| `--start-date` | | `Jan 1 current year` | Inclusive start date (YYYY-MM-DD) |
| `--end-date` | | `Dec 31 current year` | Inclusive end date (YYYY-MM-DD) |
| `--seed` | | `911` | Random seed for reproducible output |
| `--calltaker-pool-size` | | `12` | Number of unique calltaker names |
| `--dispatcher-pool-size` | | `10` | Number of unique dispatcher names |
| `--shift-preset` | | *(realism config)* | Shift structure preset: `2x12h-4shift-14day`, `2x12h-2shift`, `3x8h-3shift`, or `4x10h-4shift` |
| `--max-memory-bytes` | | `2147483648` | Approximate in-memory budget per incident chunk in bytes; CSV/Parquet exports stream in chunks to stay under it |
| `--config` | | *(none)* | Path to YAML realism configuration file |

### Global Options

Global options are accepted before the subcommand (e.g. `uv run synth911gen3 --verbose generate ...`).

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--verbose` | `-v` | *(off)* | Enable debug-level logging to stderr |
| `--quiet` | `-q` | *(off)* | Suppress all non-error logging |

Logging writes to stderr. The `SYNTH911_LOG_LEVEL` environment variable
(`DEBUG`, `INFO`, `WARNING`, `ERROR`) also controls verbosity and is used when
neither `--verbose` nor `--quiet` is given. On large runs the incident
generator reports percentage progress (5% steps) once `rows` exceeds 10,000.

```bash
uv run synth911gen3 --help          # Show all commands and options
uv run synth911gen3 generate --help # Show generate-specific options
uv run synth911gen3 --verbose generate --rows 50000 --format parquet
```

---

## Textual User Interface (TUI)

Launch the TUI for interactive data generation:

```bash
uv run synth911gen3 tui
```

### TUI Controls

| Key | Action |
|-----|--------|
| `G` | Generate data |
| `Q` | Quit |
| `Tab` | Navigate between fields |
| `Enter` | Activate focused button |

Generation runs in a background worker, so the interface stays responsive. A progress bar
tracks incident generation (updates ~0.1% granularity) and the status panel reflects each
phase; invalid inputs are highlighted with a red border and reported together in the status
panel, clearing as you edit.

### TUI Fields

Fields are grouped into sections — General, Geography, Personnel, and Configuration Files.
The status panel and help tab explain each field.

| Field | Description |
|-------|-------------|
| Rows | Number of incident rows (default: 10000) |
| Seed | Random seed for reproducible output (default: 911) |
| Area query | OpenStreetMap query (default: "Kansas City, MO") |
| Output format | csv, parquet, json, yaml, pandas, polars |
| Dataset | incidents, phone, all |
| ID format | id_number style: integer or guid |
| Output directory | Directory for exported files (default: output) |
| Output stem | Filename prefix (default: "synthetic_911") |
| Start date | Inclusive start date, YYYY-MM-DD (optional) |
| End date | Inclusive end date, YYYY-MM-DD (optional) |
| Calltaker pool size | Unique calltaker names (default: 12) |
| Dispatcher pool size | Unique dispatcher names (default: 10) |
| Shift preset | Shift structure preset (default: 2x12h-4shift-14day) |
| Max memory (bytes) | Per-chunk memory budget for CSV/Parquet streaming (blank = 2 GiB default) |
| Params file | JSON/YAML/TOML preset; Load Params fills the fields |
| Realism config file | YAML realism configuration (optional) |

---

## Configuration Parameters

### Core Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `rows` | int | 10000 | Number of CAD incidents to generate |
| `area_query` | str | "Kansas City, MO" | OpenStreetMap Nominatim query for address geocoding |
| `output_format` | enum | CSV | Export format (see [Output Formats](#output-formats)) |
| `dataset` | enum | ALL | Which dataset(s) to generate |
| `id_format` | enum | INTEGER | Incident id_number style: `integer` or `guid` |
| `output_dir` | Path | "output" | Output directory path |
| `output_stem` | str | "synthetic_911" | Base filename for exports |
| `start_date` | date | Jan 1 (current year) | Start of date range for incident timestamps |
| `end_date` | date | Dec 31 (current year) | End of date range for incident timestamps |
| `seed` | int | 911 | Random seed for reproducibility |
| `max_memory_bytes` | int | None (2 GiB) | Per-chunk memory budget in bytes for incident CSV/Parquet streaming; see [Memory Budget & Chunked Export](#memory-budget--chunked-export) |

### Personnel and Shift Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `calltaker_pool_size` | int | 12 | Unique calltaker names to generate |
| `dispatcher_pool_size` | int | 10 | Unique dispatcher names to generate |
| `shift_preset` | str | None | Shift structure preset name (see [Shift Structures](#shift-structures)); when None the realism config's `shift_config` is used |

### Shift Structures

Incidents are assigned to a named shift (`shift` column) using a configurable
crew-rotation schedule. A preset selects a complete structure up front; omit it
(or set it to `None`) to use whatever `shift_config` is defined in the realism
configuration file.

Available presets:

| Preset | Structure |
|--------|-----------|
| `2x12h-4shift-14day` (default) | 2x12h, shifts A/B (day) and C/D (night), 14-day crew rotation |
| `2x12h-2shift` | 2x12h, single day and single night shift (no crew cycling) |
| `3x8h-3shift` | 3x8h, Morning / Swing / Midnight |
| `4x10h-4shift` | 4x10h, Day / Coverage / Evening / Night |

```bash
# Use a different shift structure from the CLI
uv run synth911gen3 generate --shift-preset 3x8h-3shift

# Or programmatically
GenerationRequest(rows=10000, shift_preset="4x10h-4shift")
```

Each shift also carries its own staffing (calltakers/dispatchers). Shifts that
omit staffing fall back to splitting the global `calltaker_pool_size` /
`dispatcher_pool_size` totals. Custom structures — arbitrary shift hours,
overnight shifts, rotation patterns, and per-shift staffing — are defined in the
realism config's `shift_config` section; see the [Realism Guide](REALISMGUIDE.md).

### Supplying Parameters from a File

All parameters in this section can be supplied at once from a JSON, YAML, or TOML file with `--params`. See [Params Files](#params-files-bundled-options).

### Date Range Behavior

- If `start_date` and `end_date` are not specified, the full current calendar year is used
- Incidents are distributed across the date range using realistic diurnal patterns
- Hourly phone metrics cover every hour in the date range

### Address Generation

Addresses are fetched from OpenStreetMap using the `area_query` parameter. The query accepts **any valid location query** that OpenStreetMap's Nominatim API supports, which is geocoded to a bounding box. Real street addresses with `addr:housenumber` + `addr:street` tags are then pulled from that bounding box via the Overpass API (overpy). Where an area lacks mapped house numbers, the generator falls back to real named streets with synthesized house numbers so output is still produced.

Each address is emitted as individual components (`prefix_directional`, `street_number`, `street_name`, `street_type`, `postfix_directional`, `postal_code`) in addition to the combined `street_address`. Directionals are normalized to abbreviations (e.g., `NORTH` → `N`); a component is left empty when it cannot be determined from the source data.

Larger areas provide more address variety but take longer to fetch initially (addresses are cached locally after first query).

**Examples (not an exhaustive list):**

```
"Kansas City, MO"
"Seattle, WA"
"New York City, NY"
"Denver County, CO"
"London, UK"
"Chicago, IL"
"Los Angeles County, CA"
"Toronto, ON, Canada"
"Paris, France"
"Tokyo, Japan"
"Sydney, Australia"
"Berlin, Germany"
```

**Query flexibility:**

- City names: `"Portland, OR"`
- County/region: `"King County, WA"`
- State/province: `"Texas, USA"`
- Postal codes: `"90210, USA"`
- Landmarks: `"Central Park, New York, NY"`
- Bounding boxes: `"40.7128,-74.0060,40.7739,-73.9636"` (minlat,minlon,maxlat,maxlon)

Larger areas provide more address variety but may take longer to fetch initially (addresses are cached locally after first query).

---

## Realism Configuration

How the generator produces realistic statistics — agency/priority/problem
distributions, time profiles, the parallel dispatch timeline, and hourly phone
metrics — and how to override them with a YAML realism configuration file, is
documented in the dedicated [Realism Guide](REALISMGUIDE.md).

Key facts:

- No configuration is required; defaults are tuned to realistic 9-1-1 center behavior.
- A `--config path/to/realism.yaml` file overrides any or all default distributions.
- An example config ships at `config/example_realism.yaml`.
- Use `RealismConfig.from_yaml(...)` from Python (see [Python API Usage](#python-api-usage)).

---

## Params Files (Bundled Options)

Instead of typing every flag on the command line, you can store all generation parameters in a single file and pass it with `--params`. This is useful for repeatable runs, team-shared presets, and batch/CI workflows.

### Using a Params File

```bash
uv run synth911gen3 generate --params config/example_params.json
```

### Supported Formats

Params files may be JSON (`.json`), YAML (`.yaml`/`.yml`), or TOML (`.toml`). Format is detected from the file extension.

### File Structure

Keys mirror the CLI option names. Canonical `GenerationRequest` field names are also accepted.

```json
{
  "rows": 50000,
  "area": "Denver, CO",
  "format": "parquet",
  "dataset": "all",
  "output_dir": "output",
  "output_stem": "denver_911",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "seed": 42,
  "calltaker_pool_size": 20,
  "dispatcher_pool_size": 15,
  "shift_preset": "3x8h-3shift",
  "max_memory_bytes": 1073741824,
  "config": "config/example_realism.yaml"
}
```

The same file in YAML:

```yaml
rows: 25000
area: "Seattle, WA"
format: csv
dataset: incidents
output_dir: "output"
output_stem: "seattle_911"
start_date: "2024-07-01"
end_date: "2024-09-30"
seed: 2024
calltaker_pool_size: 16
dispatcher_pool_size: 12
shift_preset: "4x10h-4shift"
```

### Key Reference

| Key | Accepted Alias | Type | Description |
|-----|---------------|------|-------------|
| `rows` | | int | Number of incident rows |
| `area_query` | `area` | str | OpenStreetMap area query |
| `output_format` | `format` | str | csv, parquet, json, yaml, pandas, polars |
| `dataset` | | str | incidents, phone, all |
| `id_format` | | str | integer or guid |
| `output_dir` | | str | Output directory |
| `output_stem` | | str | Filename stem |
| `start_date` | | str (YYYY-MM-DD) | Inclusive start date |
| `end_date` | | str (YYYY-MM-DD) | Inclusive end date |
| `seed` | | int | Random seed |
| `calltaker_pool_size` | | int | Unique calltaker names |
| `dispatcher_pool_size` | | int | Unique dispatcher names |
| `shift_preset` | | str | Shift structure preset name |
| `max_memory_bytes` | | int | Per-chunk memory budget for CSV/Parquet streaming |
| `realism_config_path` | `config` | str | Path to YAML realism config |

### Precedence

Values are merged with the following precedence (highest wins):

1. **CLI flags** (e.g., `--rows 100` overrides the file)
2. **Params file** values
3. **Built-in defaults** (10,000 rows, Kansas City, MO, csv, etc.)

Omitted keys fall through to the next source, so a params file may contain only the subset you care about:

```bash
# File sets rows/area/dates; CLI overrides format and rows
uv run synth911gen3 generate --params my_run.json --format json --rows 75000
```

### Examples

```bash
# Full run from a params file
uv run synth911gen3 generate --params config/example_params.json

# Override selected values on top of a file
uv run synth911gen3 generate --params denver.json --rows 1000000 --format parquet

# YAML or TOML params files work too
uv run synth911gen3 generate --params config/example_params.yaml
uv run synth911gen3 generate --params run.toml
```

Two ready-made examples are included in the repo: `config/example_params.json` and `config/example_params.yaml`.

---

## Output Formats

| Format | Extension | Description | Use Case |
|--------|-----------|-------------|----------|
| `csv` | `.csv` | Comma-separated values | General purpose, Excel compatible |
| `parquet` | `.parquet` | Apache Parquet columnar | Analytics, big data workflows |
| `json` | `_bundle.json` | Single JSON file with all datasets | Web APIs, JavaScript |
| `yaml` | `_bundle.yaml` | Single YAML file with all datasets | Configuration, human-readable |
| `pandas` | (memory) | Returns `dict[str, pd.DataFrame]` | Python notebooks, pandas workflows |
| `polars` | (memory) | Returns `dict[str, pl.DataFrame]` | High-performance Python analytics |

### File Naming

- **CSV/Parquet**: `{output_stem}_{dataset}.{ext}` (e.g., `synthetic_911_incidents.csv`)
- **JSON/YAML**: `{output_stem}_bundle.{ext}` (single file containing all datasets)

### In-Memory Formats (pandas/polars)

When using `pandas` or `polars` format, no files are written. The generator returns DataFrame objects directly to the calling code.

### Memory Budget & Chunked Export

For very large CSV/Parquet runs, the incident generator avoids holding the full
frame in memory by **streaming records in chunks**. The per-chunk budget
(`max_memory_bytes`) defaults to 2 GiB and can be set via the CLI
(`--max-memory-bytes`), TUI, or a params file. Only the *incidents* dataset is
chunked; the hourly phone-metrics dataset is tiny and always built in one pass.

- When the estimated full frame fits in the budget, a single chunk is written and
  the file is byte-for-byte identical to a non-chunked run.
- When it does not fit, chunks are written incrementally: CSV writes a header on
  the first chunk and appends the rest; Parquet streams row groups through one
  `ParquetWriter`. Only one chunk's DataFrame is materialized at a time.
- `id_number` stays globally sequential (or globally unique for `guid`) and
  `internal_reference_number` remains unique per agency across chunk boundaries.
- Chunked output is reproducible for a given seed and chunk plan, but chunk
  boundaries cause per-chunk time sorting, so a chunked export may differ in row
  order from a non-chunked export of the same seed. In-memory formats
  (`pandas`/`polars`) always build the full frame.

```bash
# Stream a 5M-row run under a 1 GiB per-chunk budget
uv run synth911gen3 generate --rows 5000000 --format parquet --max-memory-bytes 1073741824
```

---

## Generated Data Schema

### CAD Incidents Dataset

| Column | Type | Description |
|--------|------|-------------|
| `id_number` | int or str | Incident ID: sequential integer (1 to N), or UUID v4 string when `id_format` is `guid` |
| `internal_reference_number` | str | Agency-specific reference: `{AGENCY}-{YYMMDD}-{SEQ:06d}` |
| `agency` | str | Responding agency: LAW, FIRE, EMS |
| `shift` | str | Shift on duty at `call_start_time` (e.g., A, B, C, D) |
| `shift_label` | str | Shift label (e.g., DAY, NIGHT) |
| `shift_group` | int | Crew rotation group the shift belongs to (1, 2, …) |
| `problem_nature` | str | Call type (e.g., "Traffic Crash", "Chest Pain") |
| `priority` | int | Priority level 1-5 (1=highest) |
| `prefix_directional` | str | Directional prefix (N/S/E/W/NE/…) or empty |
| `street_number` | str | House number (e.g., "101", "204A") |
| `street_name` | str | Street name without type (e.g., "Main", "12th") |
| `street_type` | str | Street suffix (e.g., St, Ave, Blvd) or empty |
| `postfix_directional` | str | Directional suffix (NW/SE/…) or empty |
| `street_address` | str | Full street address from OSM (all components) |
| `city` | str | City name |
| `state` | str | State/province |
| `postal_code` | str | ZIP/postal code from OSM when available |
| `location` | str | `street_address, city, state` |
| `call_start_time` | datetime | Call received timestamp |
| `hour` | int | Hour of day (0–23) of `call_start_time` |
| `dow` | str | Day of week abbreviation (MON–SUN) of `call_start_time` |
| `week_no` | int | ISO week number (1–53) of `call_start_time` |
| `incident_start_time` | datetime | CAD incident record opened; 0–3 s after `call_start_time` |
| `time_phone_pickup` | datetime | Call answered by calltaker |
| `time_call_enters_queue` | datetime | Call queued for dispatch |
| `time_first_unit_assigned` | datetime | First unit assigned (parallel to call-taking for high priority) |
| `time_unit_enroute` | datetime | Unit enroute (wheels rolling) |
| `time_unit_arrived` | datetime | Unit on scene |
| `time_last_unit_cleared` | datetime | Last unit cleared scene |
| `time_call_closed` | datetime | Incident closed in CAD |
| `time_phone_disconnect` | datetime | Caller disconnected |
| `calltaker` | str | Calltaker name |
| `dispatcher` | str | Dispatcher name |
| `method_of_call_reception` | str | E-911, Phone, OFFICER, Radio, C2C, NOT CAPTURED, Text, CAD2CAD |
| `call_disposition` | str | Code+label pair, e.g., NR-No Report, RE-Report, CI-Citation, UNDEFINED |
| `pickup_delay_seconds` | int | Ring-to-answer time |
| `pre_cad_offset_seconds` | int | Call start to CAD incident open (0–3 s) |
| `interview_seconds` | int | Caller interview duration |
| `dispatch_queue_seconds` | int | Queue-to-dispatch time |
| `turnout_seconds` | int | Station-to-wheels-rolling time |
| `travel_seconds` | int | Wheels-rolling to on-scene time |
| `on_scene_seconds` | int | On-scene duration |
| `closeout_seconds` | int | Scene-clear to incident-close time |
| `phone_duration_seconds` | int | Total call duration |
| `total_elapsed_seconds` | int | Call start to incident close |

### Hourly Phone Metrics Dataset

| Column | Type | Description |
|--------|------|-------------|
| `hour_start` | datetime | Hour interval start (UTC) |
| `hour_of_day` | int | Hour 0-23 |
| `nine_one_one_calls_received` | int | 9-1-1 calls received |
| `nine_one_one_calls_abandoned` | int | 9-1-1 calls abandoned |
| `non_emergency_calls_received` | int | Non-emergency calls received |
| `non_emergency_calls_abandoned` | int | Non-emergency calls abandoned |
| `outbound_calls_placed` | int | Outbound calls placed |

---

## Realism Features

The built-in default distributions — agency split, priority weights, problem
vocabularies, lognormal time profiles, diurnal patterns, hourly phone metrics,
call reception methods, and disposition codes — are described in the
[Realism Guide](REALISMGUIDE.md).

---

## Examples

### Basic Generation

```bash
# Default: 10K incidents + hourly counts, CSV, Kansas City
uv run synth911gen3 generate

# Custom row count
uv run synth911gen3 generate --rows 50000

# Different area
uv run synth911gen3 generate --area "Seattle, WA"
```

### Output Formats

```bash
# Parquet for analytics
uv run synth911gen3 generate --format parquet --rows 100000

# JSON bundle for web API
uv run synth911gen3 generate --format json

# In-memory pandas (for Jupyter/notebooks)
uv run synth911gen3 generate --format pandas
```

### Dataset Selection

```bash
# Only CAD incidents
uv run synth911gen3 generate --dataset incidents

# Only hourly phone metrics
uv run synth911gen3 generate --dataset phone

# Both (default)
uv run synth911gen3 generate --dataset all
```

### Date Range

```bash
# Specific date range
uv run synth911gen3 generate --start-date 2024-01-01 --end-date 2024-03-31

# Single day
uv run synth911gen3 generate --start-date 2024-07-04 --end-date 2024-07-04
```

### Reproducibility

```bash
# Fixed seed for reproducible results
uv run synth911gen3 generate --seed 42

# Different personnel pools
uv run synth911gen3 generate --calltaker-pool-size 20 --dispatcher-pool-size 15
```

### Custom Output Location

```bash
# Custom directory and filename stem
uv run synth911gen3 generate --output-dir /data/exports --output-stem kc_911_2024
```

### Large-Scale Generation

```bash
# 1 million incidents in Parquet (efficient for large datasets)
uv run synth911gen3 generate --rows 1000000 --format parquet --output-dir /big/data

# 5 million incidents with a tighter per-chunk memory budget
uv run synth911gen3 generate --rows 5000000 --format parquet --max-memory-bytes 536870912
```

### Realism Configuration

```bash
# Use custom realism config to match a specific 9-1-1 center
uv run synth911gen3 generate --config config/example_realism.yaml --rows 50000 --format parquet

# With custom output location
uv run synth911gen3 generate --config my_center.yaml --rows 100000 --output-dir /data/exports --output-stem my_center_2024
```

### Params Files

```bash
# Run with all parameters defined in a single file
uv run synth911gen3 generate --params config/example_params.json

# Override individual values on top of the file
uv run synth911gen3 generate --params config/example_params.json --rows 250000 --format csv

# YAML params file
uv run synth911gen3 generate --params config/example_params.yaml
```

---

## Python API Usage

```python
from synth911gen3 import Synth911Application
from synth911gen3.addresses import OpenStreetMapAddressProvider
from synth911gen3.config import GenerationRequest, OutputFormat, DatasetKind
from pathlib import Path

# Create application
app = Synth911Application(address_provider=OpenStreetMapAddressProvider())

# Configure request
request = GenerationRequest(
    rows=50000,
    area_query="Denver, CO",
    output_format=OutputFormat.PARQUET,
    dataset=DatasetKind.ALL,
    output_dir=Path("data/denver"),
    output_stem="denver_911",
    start_date=date(2024, 1, 1),
    end_date=date(2024, 12, 31),
    seed=12345,
    shift_preset="2x12h-4shift-14day",
    max_memory_bytes=2 * 1024**3,  # per-chunk budget for CSV/Parquet streaming
)

# Generate (returns GenerationResult with DataFrames and file paths)
result = app.generate(request)

# Access DataFrames directly
incidents_df = result.incidents
hourly_df = result.hourly_call_counts

# Access exported file paths
for dataset_name, path in result.exported_artifacts.items():
    print(f"{dataset_name}: {path}")
```

### In-Memory DataFrames

```python
request = GenerationRequest(
    rows=10000,
    output_format=OutputFormat.PANDAS,  # or POLARS
    dataset=DatasetKind.INCIDENTS,
)

result = app.generate(request)
incidents_df = result.incidents  # pd.DataFrame
```

---

## Troubleshooting

### Common Issues

#### "AddressLookupError: Failed to fetch addresses"
- Check internet connectivity (required for initial OSM fetch)
- Try a simpler area query: `"Kansas City"` instead of `"Kansas City, MO, USA"`
- Addresses are cached locally after first fetch

#### TLS errors on restricted networks (corporate proxy / MITM)

On networks where a TLS-inspecting proxy intercepts HTTPS traffic, Python and `uv` may reject the
proxy's certificate with errors like `invalid peer certificate: UnknownIssuer` or
`certificate verify failed: unable to get local issuer certificate`. The safe fix is to verify
against the **operating system trust store** instead of bundled CA lists (verification stays on):

```bash
# 1. Let uv use the OS trust store for package downloads
$env:UV_NATIVE_TLS = "true"        # PowerShell
# export UV_NATIVE_TLS=true         # Linux/macOS
uv sync

# 2. Let the generator use the OS trust store for OSM lookups (dev dependency: truststore)
$env:SYNTH911_SYSTEM_TRUST = "1"   # PowerShell
# export SYNTH911_SYSTEM_TRUST=1     # Linux/macOS
uv run synth911gen3 generate
```

The runtime flag is a no-op unless set, so production behavior is unchanged. If the OS trust
store does not trust the proxy's issuer, contact your network administrator instead — do not
disable TLS verification.

#### "ExportError: Unsupported output format"
- Valid formats: `csv`, `parquet`, `json`, `yaml`, `pandas`, `polars`
- Case-insensitive

#### "ValidationError: start_date must be on or before end_date"
- Ensure `--start-date` ≤ `--end-date`
- Dates must be YYYY-MM-DD format

#### Large generation is slow
- Use `--format parquet` for large datasets (faster I/O)
- First run fetches OSM addresses; subsequent runs use cache
- Consider reducing `rows` for testing
- For runs that would exceed available RAM, lower `--max-memory-bytes` so CSV/Parquet export streams in chunks instead of holding the full frame

#### TUI won't launch
- Ensure `textual` is installed: `uv add textual`
- Terminal must support ANSI colors and mouse events

### Performance Tips

| Dataset Size | Recommended Format | Notes |
|--------------|-------------------|-------|
| < 50K rows | CSV | Fast enough, human-readable |
| 50K - 500K | Parquet | Columnar, compressed, fast analytics |
| > 500K | Parquet | Essential for memory efficiency |
| Any (Python) | pandas/polars | Zero-copy, in-memory |

### Cache Location

OpenStreetMap addresses are cached in:
```
~/.cache/synth911gen3/addresses_{area_hash}.parquet
```

Delete cache files to force re-fetch for updated area boundaries.

---

## Advanced Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `SYNTH911_LOG_LEVEL` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, or `ERROR` (used when no `--verbose`/`--quiet` flag is given) |

### Extending with Custom Providers

```python
from synth911gen3.addresses import AddressProvider, Address
from synth911gen3.app import Synth911Application

class CustomAddressProvider(AddressProvider):
    def load_addresses(self, area_query: str) -> list[Address]:
        # Return list of Address objects
        return [...]

app = Synth911Application(address_provider=CustomAddressProvider())
```

---

## License

MIT License - see LICENSE file for details.

---

## Support

- Issues: [GitHub Issues](https://github.com/trdunsworth/synth911gen3/issues)
- Documentation: This guide + inline code docstrings
