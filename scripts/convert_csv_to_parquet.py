#!/usr/bin/env python3
"""Convert CSV files to Parquet format for better compression and performance."""

import argparse
import sys
from pathlib import Path

import pandas as pd


def convert_csv_to_parquet(csv_path: Path, parquet_path: Path | None = None) -> Path:
    """Convert a CSV file to Parquet format.
    
    Args:
        csv_path: Path to the input CSV file
        parquet_path: Path for the output Parquet file (optional, defaults to same name with .parquet extension)
    
    Returns:
        Path to the created Parquet file
    """
    if parquet_path is None:
        parquet_path = csv_path.with_suffix('.parquet')
    
    print(f"Reading CSV file: {csv_path}")
    print(f"File size: {csv_path.stat().st_size / 1024 / 1024:.2f} MB")
    
    # Read CSV in chunks to handle large files
    chunk_size = 100000
    chunks = []
    
    for chunk in pd.read_csv(csv_path, chunksize=chunk_size):
        chunks.append(chunk)
        print(f"  Read {len(chunks) * chunk_size:,} rows...")
    
    df = pd.concat(chunks, ignore_index=True)
    print(f"Total rows: {len(df):,}")
    
    # Write to Parquet with compression
    print(f"Writing Parquet file: {parquet_path}")
    df.to_parquet(parquet_path, index=False, compression='snappy')
    
    parquet_size = parquet_path.stat().st_size
    print(f"Parquet file size: {parquet_size / 1024 / 1024:.2f} MB")
    print(f"Compression ratio: {csv_path.stat().st_size / parquet_size:.2f}x")
    
    return parquet_path


def main():
    parser = argparse.ArgumentParser(description="Convert CSV files to Parquet format")
    parser.add_argument("csv_file", help="Path to the CSV file to convert")
    parser.add_argument("-o", "--output", help="Output Parquet file path (optional)")
    parser.add_argument("--chunk-size", type=int, default=100000, 
                       help="Chunk size for reading large CSV files (default: 100000)")
    
    args = parser.parse_args()
    
    csv_path = Path(args.csv_file)
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)
    
    parquet_path = Path(args.output) if args.output else None
    
    try:
        convert_csv_to_parquet(csv_path, parquet_path)
        print("Conversion completed successfully!")
    except Exception as e:
        print(f"Error during conversion: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()