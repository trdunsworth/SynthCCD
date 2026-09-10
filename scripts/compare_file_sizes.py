#!/usr/bin/env python3
"""Compare file sizes across different formats."""

from pathlib import Path
import os


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def compare_formats(base_name: str, output_dir: Path):
    """Compare file sizes for different formats of the same data."""
    formats = {
        'CSV': f"{base_name}.csv",
        'Parquet': f"{base_name}.parquet",
        '7z': f"{base_name}.7z",
    }
    
    print(f"\n{'='*60}")
    print(f"File Format Comparison: {base_name}")
    print(f"{'='*60}")
    print(f"{'Format':<10} {'Size':<15} {'Ratio':<10}")
    print(f"{'-'*35}")
    
    base_size = None
    for format_name, filename in formats.items():
        filepath = output_dir / filename
        if filepath.exists():
            size = filepath.stat().st_size
            if base_size is None:
                base_size = size
                ratio = "1.00x"
            else:
                ratio = f"{base_size/size:.2f}x"
            
            print(f"{format_name:<10} {format_size(size):<15} {ratio:<10}")
        else:
            print(f"{format_name:<10} {'Not found':<15}")
    
    print(f"\nRecommendation:")
    print(f"  • For GitHub uploads: Use Parquet (33.41 MB)")
    print(f"  • For maximum compression: Use 7z (19.35 MB)")
    print(f"  • For analytics engines: Use Parquet (native support)")
    print(f"  • For general use: Keep CSV for compatibility")


def main():
    output_dir = Path("output")
    
    # Compare the main incident files
    compare_formats("ABQ_2026_APR_JUL_incidents", output_dir)
    
    # Show all available formats
    print(f"\n{'='*60}")
    print("Available Files in output/")
    print(f"{'='*60}")
    
    for format_ext in ['csv', 'parquet', '7z']:
        files = list(output_dir.glob(f"*.{format_ext}"))
        if files:
            print(f"\n{format_ext.upper()} files ({len(files)} total):")
            total_size = sum(f.stat().st_size for f in files)
            print(f"  Total size: {format_size(total_size)}")
            for f in sorted(files, key=lambda x: x.stat().st_size, reverse=True)[:5]:
                print(f"  - {f.name}: {format_size(f.stat().st_size)}")


if __name__ == "__main__":
    main()