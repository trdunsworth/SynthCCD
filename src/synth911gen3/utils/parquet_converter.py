"""Parquet conversion utilities for synthetic 911 data."""

from pathlib import Path

import pandas as pd


def csv_to_parquet(csv_path: Path, parquet_path: Path | None = None, 
                   compression: str = 'snappy') -> Path:
    """Convert a CSV file to Parquet format.
    
    Args:
        csv_path: Path to the input CSV file
        parquet_path: Path for the output Parquet file (optional)
        compression: Compression algorithm ('snappy', 'gzip', 'brotli', 'lz4', 'zstd')
    
    Returns:
        Path to the created Parquet file
    """
    if parquet_path is None:
        parquet_path = csv_path.with_suffix('.parquet')
    
    # Read CSV
    df = pd.read_csv(csv_path)
    
    # Write to Parquet
    df.to_parquet(parquet_path, index=False, compression=compression)
    
    return parquet_path


def batch_csv_to_parquet(input_dir: Path, output_dir: Path | None = None,
                        compression: str = 'snappy') -> list[Path]:
    """Convert all CSV files in a directory to Parquet format.
    
    Args:
        input_dir: Directory containing CSV files
        output_dir: Output directory for Parquet files (optional, defaults to input_dir)
        compression: Compression algorithm
    
    Returns:
        List of paths to created Parquet files
    """
    if output_dir is None:
        output_dir = input_dir
    
    output_dir.mkdir(exist_ok=True)
    
    csv_files = list(input_dir.glob("*.csv"))
    parquet_files = []
    
    for csv_path in csv_files:
        parquet_path = output_dir / csv_path.with_suffix('.parquet').name
        csv_to_parquet(csv_path, parquet_path, compression)
        parquet_files.append(parquet_path)
    
    return parquet_files


def get_parquet_info(parquet_path: Path) -> dict:
    """Get information about a Parquet file.
    
    Args:
        parquet_path: Path to the Parquet file
    
    Returns:
        Dictionary with file information
    """
    df = pd.read_parquet(parquet_path)
    
    return {
        'path': parquet_path,
        'size_mb': parquet_path.stat().st_size / 1024 / 1024,
        'rows': len(df),
        'columns': list(df.columns),
        'dtypes': df.dtypes.to_dict()
    }