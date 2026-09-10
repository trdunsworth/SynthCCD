"""Tests for auto-parquet threshold functionality."""

import pytest

from synth911gen3.config import GenerationRequest, OutputFormat


class TestAutoParquetThreshold:
    """Test cases for auto-parquet threshold logic."""

    def test_default_threshold(self):
        """Test that default threshold is 100000 rows."""
        request = GenerationRequest(rows=50000)
        assert request.resolved_output_format() == OutputFormat.CSV

        request = GenerationRequest(rows=100000)
        assert request.resolved_output_format() == OutputFormat.PARQUET

    def test_custom_threshold(self):
        """Test custom threshold values."""
        # Threshold of 50000
        request = GenerationRequest(rows=49999, auto_parquet_threshold=50000)
        assert request.resolved_output_format() == OutputFormat.CSV

        request = GenerationRequest(rows=50000, auto_parquet_threshold=50000)
        assert request.resolved_output_format() == OutputFormat.PARQUET

        # Threshold of 1000
        request = GenerationRequest(rows=999, auto_parquet_threshold=1000)
        assert request.resolved_output_format() == OutputFormat.CSV

        request = GenerationRequest(rows=1000, auto_parquet_threshold=1000)
        assert request.resolved_output_format() == OutputFormat.PARQUET

    def test_disabled_threshold(self):
        """Test that threshold of 0 disables auto-switching."""
        request = GenerationRequest(rows=200000, auto_parquet_threshold=0)
        assert request.resolved_output_format() == OutputFormat.CSV

    def test_non_csv_format_not_affected(self):
        """Test that non-CSV formats are not auto-switched."""
        # Parquet format should remain Parquet
        request = GenerationRequest(
            rows=200000,
            output_format=OutputFormat.PARQUET,
            auto_parquet_threshold=100000,
        )
        assert request.resolved_output_format() == OutputFormat.PARQUET

        # JSON format should remain JSON
        request = GenerationRequest(
            rows=200000,
            output_format=OutputFormat.JSON,
            auto_parquet_threshold=100000,
        )
        assert request.resolved_output_format() == OutputFormat.JSON

    def test_explicit_parquet_format(self):
        """Test that explicit Parquet format is not affected by threshold."""
        request = GenerationRequest(
            rows=50000,
            output_format=OutputFormat.PARQUET,
            auto_parquet_threshold=100000,
        )
        assert request.resolved_output_format() == OutputFormat.PARQUET

    def test_population_derived_rows(self):
        """Test auto-switching with population-derived row count."""
        # With population, rows are derived; should still auto-switch
        request = GenerationRequest(
            population=500000,
            auto_parquet_threshold=100000,
        )
        # Population-derived rows should exceed threshold
        resolved_rows = request.resolved_rows()
        assert resolved_rows > 100000
        assert request.resolved_output_format() == OutputFormat.PARQUET

    def test_database_formats_not_affected(self):
        """Test that database formats are not auto-switched."""
        request = GenerationRequest(
            rows=200000,
            output_format=OutputFormat.POSTGRESQL,
            auto_parquet_threshold=100000,
        )
        assert request.resolved_output_format() == OutputFormat.POSTGRESQL

    def test_in_memory_formats_not_affected(self):
        """Test that in-memory formats are not auto-switched."""
        request = GenerationRequest(
            rows=200000,
            output_format=OutputFormat.PANDAS,
            auto_parquet_threshold=100000,
        )
        assert request.resolved_output_format() == OutputFormat.PANDAS

        request = GenerationRequest(
            rows=200000,
            output_format=OutputFormat.POLARS,
            auto_parquet_threshold=100000,
        )
        assert request.resolved_output_format() == OutputFormat.POLARS

    def test_boundary_values(self):
        """Test boundary values at threshold."""
        # Exactly at threshold
        request = GenerationRequest(rows=100000, auto_parquet_threshold=100000)
        assert request.resolved_output_format() == OutputFormat.PARQUET

        # One below threshold
        request = GenerationRequest(rows=99999, auto_parquet_threshold=100000)
        assert request.resolved_output_format() == OutputFormat.CSV

    def test_negative_threshold(self):
        """Test that negative threshold is treated as disabled."""
        request = GenerationRequest(rows=200000, auto_parquet_threshold=-1)
        assert request.resolved_output_format() == OutputFormat.CSV


class TestAutoParquetParams:
    """Test auto-parquet threshold in params files."""

    def test_params_file_integer(self):
        """Test loading auto_parquet_threshold from params file."""
        from synth911gen3.params import build_request_from_params

        file_params = {"auto_parquet_threshold": "50000"}
        cli_params = {"rows": 60000}

        request = build_request_from_params(file_params, cli_params)
        assert request.auto_parquet_threshold == 50000
        assert request.resolved_output_format() == OutputFormat.PARQUET

    def test_params_file_zero(self):
        """Test loading auto_parquet_threshold=0 from params file."""
        from synth911gen3.params import build_request_from_params

        file_params = {"auto_parquet_threshold": "0"}
        cli_params = {"rows": 200000}

        request = build_request_from_params(file_params, cli_params)
        assert request.auto_parquet_threshold == 0
        assert request.resolved_output_format() == OutputFormat.CSV