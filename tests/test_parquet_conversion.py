"""Tests for Parquet conversion utilities."""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from synth911gen3.utils.parquet_converter import (
    batch_csv_to_parquet,
    csv_to_parquet,
    get_parquet_info,
)


@pytest.fixture
def sample_csv(tmp_path):
    """Create a sample CSV file for testing."""
    data = {
        'id': [1, 2, 3, 4, 5],
        'name': ['Alice', 'Bob', 'Charlie', 'David', 'Eve'],
        'value': [10.5, 20.3, 30.7, 40.1, 50.9]
    }
    df = pd.DataFrame(data)
    csv_path = tmp_path / "test_data.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


def test_csv_to_parquet_basic(sample_csv, tmp_path):
    """Test basic CSV to Parquet conversion."""
    parquet_path = tmp_path / "test_data.parquet"
    result_path = csv_to_parquet(sample_csv, parquet_path)
    
    assert result_path.exists()
    assert result_path.stat().st_size > 0
    
    # Verify data can be read back
    df = pd.read_parquet(result_path)
    assert len(df) == 5
    assert list(df.columns) == ['id', 'name', 'value']


def test_csv_to_parquet_auto_path(sample_csv):
    """Test CSV to Parquet conversion with automatic path."""
    result_path = csv_to_parquet(sample_csv)
    
    assert result_path.exists()
    assert result_path.suffix == '.parquet'
    assert result_path.parent == sample_csv.parent


def test_csv_to_parquet_compression(sample_csv, tmp_path):
    """Test different compression algorithms."""
    for compression in ['snappy', 'gzip', 'brotli']:
        parquet_path = tmp_path / f"test_{compression}.parquet"
        result_path = csv_to_parquet(sample_csv, parquet_path, compression=compression)
        
        assert result_path.exists()
        df = pd.read_parquet(result_path)
        assert len(df) == 5


def test_batch_csv_to_parquet(tmp_path):
    """Test batch conversion of multiple CSV files."""
    # Create multiple CSV files
    for i in range(3):
        data = {'id': [i], 'value': [i * 10]}
        df = pd.DataFrame(data)
        csv_path = tmp_path / f"file_{i}.csv"
        df.to_csv(csv_path, index=False)
    
    # Convert all to Parquet
    parquet_files = batch_csv_to_parquet(tmp_path)
    
    assert len(parquet_files) == 3
    for parquet_path in parquet_files:
        assert parquet_path.exists()
        df = pd.read_parquet(parquet_path)
        assert len(df) == 1


def test_get_parquet_info(sample_csv, tmp_path):
    """Test getting Parquet file information."""
    parquet_path = tmp_path / "test_info.parquet"
    csv_to_parquet(sample_csv, parquet_path)
    
    info = get_parquet_info(parquet_path)
    
    assert info['path'] == parquet_path
    assert info['size_mb'] > 0
    assert info['rows'] == 5
    assert 'id' in info['columns']
    assert 'name' in info['columns']
    assert 'value' in info['columns']