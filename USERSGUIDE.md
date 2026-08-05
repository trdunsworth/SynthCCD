# synth911gen3 User Guide

A synthetic data generator for 9-1-1 CAD incidents and hourly phone-center metrics.

## Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [Command-Line Interface (CLI)](#command-line-interface-cli)
4. [Textual User Interface (TUI)](#textual-user-interface-tui)
5. [Configuration Parameters](#configuration-parameters)
6. [Realism Configuration](#realism-configuration)
7. [Params Files (Bundled Options)](#params-files-bundled-options)
8. [Output Formats](#output-formats)
9. [Generated Data Schema](#generated-data-schema)
10. [Realism Features](#realism-features)
11. [Examples](#examples)
12. [Troubleshooting](#troubleshooting)
13. [Advanced Configuration](#advanced-configuration)

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
| `--output-dir` | `-o` | `output` | Directory for exported files |
| `--output-stem` | `-s` | `synthetic_911` | Filename prefix for exported files |
| `--start-date` | | `Jan 1 current year` | Inclusive start date (YYYY-MM-DD) |
| `--end-date` | | `Dec 31 current year` | Inclusive end date (YYYY-MM-DD) |
| `--seed` | | `911` | Random seed for reproducible output |
| `--calltaker-pool-size` | | `12` | Number of unique calltaker names |
| `--dispatcher-pool-size` | | `10` | Number of unique dispatcher names |
| `--config` | | *(none)* | Path to YAML realism configuration file |

### Global Options

```bash
uv run synth911gen3 --help          # Show all commands and options
uv run synth911gen3 generate --help # Show generate-specific options
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

### TUI Fields

| Field | Description |
|-------|-------------|
| Rows | Number of incident rows (default: 10000) |
| Area | OpenStreetMap query (default: "Kansas City, MO") |
| Format | Output format: csv, parquet, json, yaml, pandas, polars |
| Dataset | Dataset type: incidents, phone, all |
| Output Stem | Filename prefix (default: "synthetic_911") |
| Config | Path to YAML realism configuration file (optional) |

---

## Configuration Parameters

### Core Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `rows` | int | 10000 | Number of CAD incidents to generate |
| `area_query` | str | "Kansas City, MO" | OpenStreetMap Nominatim query for address geocoding |
| `output_format` | enum | CSV | Export format (see [Output Formats](#output-formats)) |
| `dataset` | enum | ALL | Which dataset(s) to generate |
| `output_dir` | Path | "output" | Output directory path |
| `output_stem` | str | "synthetic_911" | Base filename for exports |
| `start_date` | date | Jan 1 (current year) | Start of date range for incident timestamps |
| `end_date` | date | Dec 31 (current year) | End of date range for incident timestamps |
| `seed` | int | 911 | Random seed for reproducibility |

### Personnel Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `calltaker_pool_size` | int | 12 | Unique calltaker names to generate |
| `dispatcher_pool_size` | int | 10 | Unique dispatcher names to generate |

### Supplying Parameters from a File

All parameters in this section can be supplied at once from a JSON, YAML, or TOML file with `--params`. See [Params Files](#params-files-bundled-options).

### Date Range Behavior

- If `start_date` and `end_date` are not specified, the full current calendar year is used
- Incidents are distributed across the date range using realistic diurnal patterns
- Hourly phone metrics cover every hour in the date range

### Address Generation

Addresses are fetched from OpenStreetMap using the `area_query` parameter. The query accepts **any valid location query** that OpenStreetMap's Nominatim API supports, which is geocoded to a bounding box. Real street addresses with `addr:housenumber` + `addr:street` tags are then pulled from that bounding box via the Overpass API (overpy). Where an area lacks mapped house numbers, the generator falls back to real named streets with synthesized house numbers so output is still produced.

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

For users who want to emulate a specific 9-1-1 center with known operational characteristics, synth911gen3 supports a **YAML realism configuration file** that overrides all default statistical distributions.

### Using a Config File

```bash
# Generate with custom realism config
uv run synth911gen3 generate --config path/to/realism_config.yaml --rows 50000
```

### Config File Structure

An example config file is provided at `config/example_realism.yaml`. Copy and modify it to match your center's data:

```yaml
# Agency distribution (must sum to 1.0)
agency_weights:
  LAW: 0.52
  FIRE: 0.20
  EMS: 0.28

# Agency display names (used in output)
agency_names:
  LAW: "POLICE"
  FIRE: "FIRE"
  EMS: "EMS"

# Priority weights per agency (each agency must sum to 1.0)
# Priority 1 = highest, 5 = lowest
priority_weights:
  LAW:
    1: 0.12
    2: 0.18
    3: 0.28
    4: 0.26
    5: 0.16
  FIRE:
    1: 0.18
    2: 0.24
    3: 0.24
    4: 0.20
    5: 0.14
  EMS:
    1: 0.16
    2: 0.26
    3: 0.28
    4: 0.18
    5: 0.12

# Problem natures per agency (weights must sum to 1.0 per agency)
problem_profiles:
  LAW:
    - ["Traffic Crash", 0.12]
    - ["Domestic Disturbance", 0.12]
    - ["Suspicious Person", 0.14]
    # ... more entries
  FIRE:
    - ["Fire Alarm", 0.22]
    # ... more entries
  EMS:
    - ["Chest Pain", 0.16]
    # ... more entries

# Call reception methods (must sum to 1.0)
call_reception_weights:
  "911": 0.38
  "Phone": 0.31
  "Radio": 0.16
  "Walk In": 0.09
  "Flag Down": 0.06

# Disposition codes per agency (must sum to 1.0 per agency)
disposition_profiles:
  LAW:
    - ["Report Issued", 0.34]
    # ... more entries
  FIRE:
    - ["Report Issued", 0.49]
    # ... more entries
  EMS:
    - ["Report Issued", 0.44]
    # ... more entries

# Time profiles per agency and priority (mean seconds for lognormal distribution)
time_profiles:
  LAW:
    1:
      interview_mean: 12
      dispatch_mean: 4
      turnout_mean: 10
      travel_mean: 220
      scene_mean: 1500
      closeout_mean: 240
      phone_mean: 170
    # ... priorities 2-5
  FIRE:
    # ... all 5 priorities
  EMS:
    # ... all 5 priorities

# Diurnal call volume pattern (24 values for hours 0-23, will be normalized)
hourly_weights:
  - 0.030
  - 0.025
  # ... 24 values total
```

### Customizable Parameters

| Section | Description | Validation |
|---------|-------------|------------|
| `agency_weights` | Relative frequency of LAW/FIRE/EMS incidents | Must sum to 1.0 |
| `agency_names` | Display names for agencies in output | Must cover all agencies in `agency_weights` |
| `priority_weights` | Priority 1-5 distribution per agency | Each agency sums to 1.0 |
| `problem_problems` | Call type distribution per agency | Each agency sums to 1.0 |
| `call_reception_weights` | How calls are received (911, Phone, etc.) | Must sum to 1.0 |
| `disposition_profiles` | Outcome codes per agency | Each agency sums to 1.0 |
| `time_profiles` | Mean seconds for 7 time intervals per agency/priority | All 7 intervals required per priority |
| `hourly_weights` | 24-hour call volume pattern | 24 values, auto-normalized |

### Time Profile Intervals

Each agency/priority combination requires these 7 intervals (mean seconds):

| Interval | Description |
|----------|-------------|
| `interview_mean` | Caller questioning duration |
| `dispatch_mean` | Queue to unit assignment |
| `turnout_mean` | Station to wheels rolling |
| `travel_mean` | Wheels rolling to on-scene |
| `scene_mean` | On-scene duration |
| `closeout_mean` | Scene clear to incident close |
| `phone_mean` | Total call duration |

### Creating a Config from Your Data

1. **Analyze your CAD data** to compute:
   - Agency call volumes
   - Priority distributions per agency
   - Problem type frequencies
   - Average times for each interval by priority
   - Hourly call volume pattern
   - Disposition code frequencies
   - Call reception method breakdown

2. **Copy `config/example_realism.yaml`** and replace values with your computed statistics

3. **Validate** by running a small test generation:
   ```bash
   uv run synth911gen3 generate --config your_config.yaml --rows 1000 --format pandas
   ```

4. **Iterate** until generated statistics match your real data

### Python API Usage

```python
from synth911gen3 import Synth911Application, RealismConfig
from synth911gen3.addresses import OpenStreetMapAddressProvider
from synth911gen3.config import GenerationRequest, OutputFormat, DatasetKind
from pathlib import Path

# Load custom realism config
realism = RealismConfig.from_yaml(Path("config/my_center.yaml"))

# Or create programmatically
realism = RealismConfig(
    agency_weights={"LAW": 0.65, "FIRE": 0.20, "EMS": 0.15},
    agency_names={"LAW": "POLICE", "FIRE": "FIRE", "EMS": "EMS"},
    # ... other parameters
)

request = GenerationRequest(
    rows=50000,
    area_query="Denver, CO",
    output_format=OutputFormat.PARQUET,
    dataset=DatasetKind.ALL,
    realism_config=realism,
)

app = Synth911Application(address_provider=OpenStreetMapAddressProvider())
result = app.generate(request)
```

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
```

### Key Reference

| Key | Accepted Alias | Type | Description |
|-----|---------------|------|-------------|
| `rows` | | int | Number of incident rows |
| `area_query` | `area` | str | OpenStreetMap area query |
| `output_format` | `format` | str | csv, parquet, json, yaml, pandas, polars |
| `dataset` | | str | incidents, phone, all |
| `output_dir` | | str | Output directory |
| `output_stem` | | str | Filename stem |
| `start_date` | | str (YYYY-MM-DD) | Inclusive start date |
| `end_date` | | str (YYYY-MM-DD) | Inclusive end date |
| `seed` | | int | Random seed |
| `calltaker_pool_size` | | int | Unique calltaker names |
| `dispatcher_pool_size` | | int | Unique dispatcher names |
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

---

## Generated Data Schema

### CAD Incidents Dataset

| Column | Type | Description |
|--------|------|-------------|
| `id_number` | int | Sequential incident ID (1 to N) |
| `internal_reference_number` | str | Agency-specific reference: `{AGENCY}-{YYMMDD}-{SEQ:06d}` |
| `agency` | str | Responding agency: LAW, FIRE, EMS |
| `problem_nature` | str | Call type (e.g., "Traffic Crash", "Chest Pain") |
| `priority` | int | Priority level 1-5 (1=highest) |
| `street_address` | str | Full street address from OSM |
| `city` | str | City name |
| `state` | str | State/province |
| `location` | str | Additional location context |
| `call_start_time` | datetime | Call received timestamp |
| `time_phone_pickup` | datetime | Call answered by calltaker |
| `time_call_enters_queue` | datetime | Call queued for dispatch |
| `time_first_unit_assigned` | datetime | First unit assigned |
| `time_unit_enroute` | datetime | Unit enroute (wheels rolling) |
| `time_unit_arrived` | datetime | Unit on scene |
| `time_last_unit_cleared` | datetime | Last unit cleared scene |
| `time_call_closed` | datetime | Incident closed in CAD |
| `time_phone_disconnect` | datetime | Caller disconnected |
| `calltaker` | str | Calltaker name |
| `dispatcher` | str | Dispatcher name |
| `method_of_call_reception` | str | 911, Phone, Radio, Walk In, Flag Down |
| `call_disposition` | str | Report Issued, No Report Issued, Cancelled, No Action Taken |
| `pickup_delay_seconds` | int | Ring-to-answer time |
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

### Agency Distribution
- **LAW**: 52% of incidents
- **FIRE**: 20% of incidents
- **EMS**: 28% of incidents

### Priority Weights (by Agency)

| Priority | LAW | FIRE | EMS |
|----------|-----|------|-----|
| 1 (Highest) | 12% | 18% | 16% |
| 2 | 18% | 24% | 26% |
| 3 | 28% | 24% | 28% |
| 4 | 26% | 20% | 18% |
| 5 (Lowest) | 16% | 14% | 12% |

### Problem Natures (Weighted by Agency)

**LAW** (24): Noise Complaint, Suspicious Person, Traffic Crash, Traffic Stop, Welfare Check, Theft Report, Domestic Disturbance, Disorderly Conduct, Burglary Alarm, Assault, Shots Fired, Motor Vehicle Theft, Drug/Narcotic Violation, Trespass, Vandalism, Reckless Driving, Vehicle Collision w/ Injury, Burglary In Progress, Fraud, Harassment, DUI / Impaired Driver, Weapons Violation, Missing Person, Shoplifting

**FIRE** (20): Fire Alarm, Smoke Investigation, Medical Assist, Structure Fire, Vehicle Fire, Cooking Fire, Brush/Grass Fire, Gas Leak, CO Investigation, Hazardous Condition, Rescue Call, Mutual Aid, Odor Investigation, Overheat Investigation, Electrical Wiring Problem, Lockout / Public Service, Water Rescue, Vehicle Extrication, Assist Police, Elevator Rescue

**EMS** (22): Chest Pain, Difficulty Breathing, Fall Injury, Motor Vehicle Crash, Sick Person, Unconscious Person, Seizure, Altered Mental Status, Abdominal Pain, Overdose, Psychiatric Emergency, Stroke, Diabetic Problem, Heart Problems, Allergic Reaction, Hemorrhage / Bleeding, Traumatic Injury, Head Injury, Choking, Heat/Cold Exposure, Pregnancy / Childbirth, Animal Bite

### Time Profiles (Lognormal Distributions)

Each agency/priority combination has calibrated time profiles:

| Interval | Description | Distribution |
|----------|-------------|--------------|
| Pickup Delay | Ring to answer | Lognormal(3s, σ=0.45) |
| Interview | Caller questioning | Lognormal(14-105s by priority) |
| Dispatch Queue | Queue to dispatch | Lognormal(4-320s by priority) |
| Turnout | Station to wheels rolling | Lognormal(10-84s by priority) |
| Travel | Wheels rolling to on-scene | Lognormal(220-560s by priority) |
| On Scene | On-scene duration | Lognormal(1380-3060s by priority) |
| Closeout | Scene clear to incident close | Lognormal(240-420s by priority) |

### Diurnal Call Patterns

Hourly weights follow real 9-1-1 center patterns:
- **Peak**: 13:00-18:00 (6.2% per hour)
- **Valley**: 03:00-05:00 (2.0-2.2% per hour)
- Weekend multiplier: +12% Fri/Sat

### Call Reception Methods

| Method | Weight |
|--------|--------|
| 911 | 38% |
| Phone | 31% |
| Radio | 16% |
| Walk In | 9% |
| Flag Down | 6% |

### Disposition Codes (by Agency)

| Disposition | LAW | FIRE | EMS |
|-------------|-----|------|-----|
| Report Issued | 34% | 49% | 44% |
| No Report Issued | 26% | 18% | 23% |
| Cancelled | 18% | 14% | 12% |
| No Action Taken | 22% | 19% | 21% |

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
| `SYNTH911_SEED` | Default random seed (overridden by --seed) |
| `SYNTH911_OUTPUT_DIR` | Default output directory |

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