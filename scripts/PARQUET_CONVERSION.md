# Parquet Conversion Tools

This document explains how to convert CSV files to Parquet format for better compression and analytics performance.

## Why Parquet?

Parquet is a columnar storage format that offers several advantages over CSV:

1. **Better Compression**: Parquet files are typically 3-10x smaller than CSV files
2. **Faster Queries**: Columnar storage allows reading only needed columns
3. **Schema Preservation**: Data types are preserved, no need to infer schemas
4. **Analytics Optimized**: Works efficiently with pandas, DuckDB, Apache Spark, and other analytics engines

## File Size Comparison

Original CSV file: **186.85 MB**
Parquet file: **33.41 MB**
Compression ratio: **5.59x smaller**

## Usage

### Convert a Single File

```bash
python scripts/convert_csv_to_parquet.py output/ABQ_2026_APR_JUL_incidents.csv
```

### Convert Multiple Files

```bash
# Convert all CSV files in the output directory
python scripts/convert_all_csv_to_parquet.py output/

# Convert specific files
python scripts/convert_all_csv_to_parquet.py file1.csv file2.csv

# Convert to a different output directory
python scripts/convert_all_csv_to_parquet.py output/ -o converted/
```

### Using the Python API

```python
from pathlib import Path
from synth911gen3.utils.parquet_converter import csv_to_parquet, batch_csv_to_parquet

# Convert a single file
csv_path = Path("output/data.csv")
parquet_path = csv_to_parquet(csv_path)

# Convert all files in a directory
parquet_files = batch_csv_to_parquet(Path("output"))
```

## Analyzing Parquet Files

### With Pandas

```python
import pandas as pd

# Read only specific columns (efficient!)
df = pd.read_parquet("output/data.parquet", columns=['agency', 'priority'])

# Full analysis
df = pd.read_parquet("output/data.parquet")
print(df.groupby('agency').size())
```

### With DuckDB

```python
import duckdb

conn = duckdb.connect()
result = conn.execute("""
    SELECT agency, priority, COUNT(*) as calls
    FROM read_parquet('output/data.parquet')
    GROUP BY agency, priority
""").fetchdf()
```

## GitHub Upload

The Parquet file (33.41 MB) is well within GitHub's file size limits:
- GitHub recommends files under 50 MB
- GitHub hard limit is 100 MB for individual files
- Parquet files are also more efficient to diff and merge

## Available Parquet Files

After running the batch conversion, you'll have these Parquet files:

| File | Size | Rows |
|------|------|------|
| ABQ_2026_APR_JUL_incidents.parquet | 33.41 MB | 376,147 |
| olathe_test_incidents.parquet | 0.31 MB | 2,500 |
| synthetic_911_incidents.parquet | 0.27 MB | 2,000 |
| IndyMo_incidents.parquet | 0.21 MB | 1,082 |
| oz_test_incidents.parquet | 0.19 MB | 1,275 |
| ABQ_2026_APR_JUL_hourly_call_counts.parquet | 0.18 MB | 2,688 |
| oz_phone_test_incidents.parquet | 0.06 MB | 168 |
| IndyMo_hourly_call_counts.parquet | 0.03 MB | 168 |
| oz_phone_test_hourly_call_counts.parquet | 0.01 MB | 168 |
| oz_test_hourly_call_counts.parquet | 0.01 MB | 168 |

## Testing

Run the tests to verify the conversion utilities work correctly:

```bash
python -m pytest tests/test_parquet_conversion.py -v
```