#!/usr/bin/env python3
"""Example script demonstrating how to use Parquet files with analytics engines."""

import pandas as pd
import duckdb
from pathlib import Path


def analyze_with_pandas(parquet_path: Path):
    """Analyze Parquet data using pandas."""
    print("=== Pandas Analysis ===")
    
    # Read only specific columns (efficient with Parquet)
    df = pd.read_parquet(parquet_path, columns=['id_number', 'agency', 'priority', 'call_start_time'])
    
    print(f"Loaded {len(df):,} rows")
    print(f"\nAgency distribution:")
    print(df['agency'].value_counts())
    
    print(f"\nPriority distribution:")
    print(df['priority'].value_counts().sort_index())
    
    return df


def analyze_with_duckdb(parquet_path: Path):
    """Analyze Parquet data using DuckDB."""
    print("\n=== DuckDB Analysis ===")
    
    # DuckDB can query Parquet files directly
    conn = duckdb.connect()
    
    # Query directly from Parquet file
    result = conn.execute(f"""
        SELECT 
            agency,
            priority,
            COUNT(*) as call_count,
            AVG(priority) as avg_priority
        FROM read_parquet('{parquet_path}')
        GROUP BY agency, priority
        ORDER BY agency, priority
    """).fetchdf()
    
    print("Calls by Agency and Priority:")
    print(result)
    
    # Time-based analysis
    time_analysis = conn.execute(f"""
        SELECT 
            agency,
            DATE_TRUNC('hour', CAST(call_start_time AS TIMESTAMP)) as hour,
            COUNT(*) as calls_per_hour
        FROM read_parquet('{parquet_path}')
        GROUP BY agency, DATE_TRUNC('hour', CAST(call_start_time AS TIMESTAMP))
        ORDER BY agency, hour
        LIMIT 20
    """).fetchdf()
    
    print("\nHourly Call Distribution (sample):")
    print(time_analysis)
    
    conn.close()
    return result


def main():
    # Use the largest Parquet file for demonstration
    parquet_path = Path("output/ABQ_2026_APR_JUL_incidents.parquet")
    
    if not parquet_path.exists():
        print(f"Error: Parquet file not found: {parquet_path}")
        print("Please run the conversion script first:")
        print("  python scripts/convert_csv_to_parquet.py output/ABQ_2026_APR_JUL_incidents.csv")
        return
    
    # Analyze with pandas
    pandas_df = analyze_with_pandas(parquet_path)
    
    # Analyze with DuckDB
    duckdb_df = analyze_with_duckdb(parquet_path)
    
    print("\n=== Summary ===")
    print(f"Parquet file: {parquet_path}")
    print(f"File size: {parquet_path.stat().st_size / 1024 / 1024:.2f} MB")
    print("Both pandas and DuckDB can efficiently query this file!")
    print("\nFor GitHub uploads, this Parquet file is much smaller than the original CSV.")


if __name__ == "__main__":
    main()