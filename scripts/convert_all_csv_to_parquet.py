#!/usr/bin/env python3
"""Batch convert CSV files to Parquet format for better compression and performance."""

import argparse
import sys
from pathlib import Path

import pandas as pd


def convert_csv_to_parquet(csv_path: Path, parquet_path: Path | None = None, 
                          chunk_size: int = 100000) -> Path:
    """Convert a CSV file to Parquet format.
    
    Args:
        csv_path: Path to the input CSV file
        parquet_path: Path for the output Parquet file (optional, defaults to same name with .parquet extension)
        chunk_size: Number of rows to read at a time for large files
    
    Returns:
        Path to the created Parquet file
    """
    if parquet_path is None:
        parquet_path = csv_path.with_suffix('.parquet')
    
    print(f"\nConverting: {csv_path.name}")
    print(f"  Original size: {csv_path.stat().st_size / 1024 / 1024:.2f} MB")
    
    # Read CSV in chunks to handle large files
    chunks = []
    row_count = 0
    
    for chunk in pd.read_csv(csv_path, chunksize=chunk_size):
        chunks.append(chunk)
        row_count += len(chunk)
        if row_count % 1000000 == 0:
            print(f"  Read {row_count:,} rows...")
    
    df = pd.concat(chunks, ignore_index=True)
    print(f"  Total rows: {len(df):,}")
    
    # Write to Parquet with compression
    df.to_parquet(parquet_path, index=False, compression='snappy')
    
    parquet_size = parquet_path.stat().st_size
    compression_ratio = csv_path.stat().st_size / parquet_size
    print(f"  Parquet size: {parquet_size / 1024 / 1024:.2f} MB")
    print(f"  Compression: {compression_ratio:.2f}x smaller")
    
    return parquet_path


def main():
    parser = argparse.ArgumentParser(description="Batch convert CSV files to Parquet format")
    parser.add_argument("paths", nargs="*", 
                       help="CSV files or directories to convert (default: output/ directory)")
    parser.add_argument("-o", "--output-dir", 
                       help="Output directory for Parquet files (optional)")
    parser.add_argument("--chunk-size", type=int, default=100000, 
                       help="Chunk size for reading large CSV files (default: 100000)")
    parser.add_argument("--skip-existing", action="store_true",
                       help="Skip conversion if Parquet file already exists")
    
    args = parser.parse_args()
    
    # Default to output directory if no paths specified
    if not args.paths:
        paths = [Path("output")]
    else:
        paths = [Path(p) for p in args.paths]
    
    # Collect all CSV files
    csv_files = []
    for path in paths:
        if path.is_file() and path.suffix.lower() == '.csv':
            csv_files.append(path)
        elif path.is_dir():
            csv_files.extend(path.glob("*.csv"))
        else:
            print(f"Warning: Skipping {path} (not a CSV file or directory)")
    
    if not csv_files:
        print("No CSV files found to convert.")
        sys.exit(0)
    
    print(f"Found {len(csv_files)} CSV file(s) to convert")
    
    # Convert each file
    converted = 0
    skipped = 0
    errors = 0
    
    for csv_path in csv_files:
        try:
            # Determine output path
            if args.output_dir:
                output_dir = Path(args.output_dir)
                output_dir.mkdir(exist_ok=True)
                parquet_path = output_dir / csv_path.with_suffix('.parquet').name
            else:
                parquet_path = csv_path.with_suffix('.parquet')
            
            # Skip if exists and flag is set
            if args.skip_existing and parquet_path.exists():
                print(f"\nSkipping {csv_path.name} (Parquet file already exists)")
                skipped += 1
                continue
            
            convert_csv_to_parquet(csv_path, parquet_path, args.chunk_size)
            converted += 1
            
        except Exception as e:
            print(f"\nError converting {csv_path.name}: {e}")
            errors += 1
    
    # Summary
    print(f"\n{'='*50}")
    print(f"Conversion Summary:")
    print(f"  Converted: {converted}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()