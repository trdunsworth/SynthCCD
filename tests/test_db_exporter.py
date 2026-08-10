import pytest
from unittest.mock import MagicMock, patch

import pandas as pd

from synth911gen3.config import (
    DatabaseDialect,
    GenerationRequest,
    OutputFormat,
)
from synth911gen3.db_exporter import DatabaseExporter, export_to_database


class TestDatabaseExporter:
    def test_get_dialect_from_output_format(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.POSTGRESQL,
            db_host="localhost",
            db_name="test",
            db_user="user",
            db_password="pass",
        )
        exporter = DatabaseExporter(request=request, engine=MagicMock())
        assert exporter._get_dialect() == DatabaseDialect.POSTGRESQL

    def test_get_dialect_explicit(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.POSTGRESQL,
            db_dialect=DatabaseDialect.MARIADB,
            db_host="localhost",
            db_name="test",
            db_user="user",
            db_password="pass",
        )
        exporter = DatabaseExporter(request=request, engine=MagicMock())
        assert exporter._get_dialect() == DatabaseDialect.MARIADB

    def test_column_type_mapping_datetime(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.POSTGRESQL,
            db_host="localhost",
            db_name="test",
            db_user="user",
            db_password="pass",
        )
        exporter = DatabaseExporter(request=request, engine=MagicMock())
        frame = pd.DataFrame({"ts": pd.to_datetime(["2024-01-01"])})
        dtype = exporter._get_column_types(frame, DatabaseDialect.POSTGRESQL)
        assert "ts" in dtype

    def test_column_type_mapping_integer(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.POSTGRESQL,
            db_host="localhost",
            db_name="test",
            db_user="user",
            db_password="pass",
        )
        exporter = DatabaseExporter(request=request, engine=MagicMock())
        frame = pd.DataFrame({"count": [1, 2, 3]})
        dtype = exporter._get_column_types(frame, DatabaseDialect.POSTGRESQL)
        assert "count" in dtype

    def test_column_type_mapping_string(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.POSTGRESQL,
            db_host="localhost",
            db_name="test",
            db_user="user",
            db_password="pass",
        )
        exporter = DatabaseExporter(request=request, engine=MagicMock())
        frame = pd.DataFrame({"name": ["a", "b", "c"]})
        dtype = exporter._get_column_types(frame, DatabaseDialect.POSTGRESQL)
        assert "name" in dtype

    def test_export_to_database_no_datasets(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.POSTGRESQL,
            db_host="localhost",
            db_name="test",
            db_user="user",
            db_password="pass",
        )
        result = export_to_database({}, request)
        assert result == {}

    @patch("synth911gen3.db_exporter.DatabaseExporter")
    def test_export_to_database_calls_exporter(self, mock_exporter_class):
        mock_exporter = MagicMock()
        mock_exporter.export_incidents.return_value = 100
        mock_exporter.export_phone_metrics.return_value = 50
        mock_exporter_class.return_value = mock_exporter

        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.POSTGRESQL,
            db_host="localhost",
            db_name="test",
            db_user="user",
            db_password="pass",
        )
        datasets = {
            "incidents": pd.DataFrame({"id": [1, 2]}),
            "hourly_call_counts": pd.DataFrame({"hour": [1]}),
        }
        result = export_to_database(datasets, request)

        assert result == {"incidents": 100, "hourly_call_counts": 50}
        mock_exporter.close.assert_called_once()


class TestDatabaseConfigValidation:
    def test_duckdb_requires_no_host(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.DUCKDB,
            db_name="test.duckdb",
        )
        # Should not raise
        request.validate()

    def test_postgresql_requires_host(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.POSTGRESQL,
            db_name="test",
            db_user="user",
            db_password="pass",
        )
        with pytest.raises(Exception, match="db_host is required"):
            request.validate()

    def test_postgresql_requires_db_name(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.POSTGRESQL,
            db_host="localhost",
            db_user="user",
            db_password="pass",
        )
        with pytest.raises(Exception, match="db_name is required"):
            request.validate()

    def test_postgresql_requires_user(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.POSTGRESQL,
            db_host="localhost",
            db_name="test",
            db_password="pass",
        )
        with pytest.raises(Exception, match="db_user is required"):
            request.validate()

    def test_invalid_if_exists(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.POSTGRESQL,
            db_host="localhost",
            db_name="test",
            db_user="user",
            db_password="pass",
            db_if_exists="invalid",
        )
        with pytest.raises(Exception, match="db_if_exists must be"):
            request.validate()

    def test_invalid_batch_size(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.POSTGRESQL,
            db_host="localhost",
            db_name="test",
            db_user="user",
            db_password="pass",
            db_batch_size=0,
        )
        with pytest.raises(Exception, match="db_batch_size must be greater"):
            request.validate()

    def test_default_ports_set(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.POSTGRESQL,
            db_host="localhost",
            db_name="test",
            db_user="user",
            db_password="pass",
            db_port=None,
        )
        request.validate()
        assert request.db_port == 5432

        request2 = GenerationRequest(
            rows=10,
            output_format=OutputFormat.SQLSERVER,
            db_host="localhost",
            db_name="test",
            db_user="user",
            db_password="pass",
            db_port=None,
        )
        request2.validate()
        assert request2.db_port == 1433

        request3 = GenerationRequest(
            rows=10,
            output_format=OutputFormat.MARIADB,
            db_host="localhost",
            db_name="test",
            db_user="user",
            db_password="pass",
            db_port=None,
        )
        request3.validate()
        assert request3.db_port == 3306