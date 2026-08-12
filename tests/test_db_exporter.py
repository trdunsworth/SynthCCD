import sqlite3

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

    def test_get_dialect_sqlite(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.SQLITE,
        )
        exporter = DatabaseExporter(request=request, engine=MagicMock())
        assert exporter._get_dialect() == DatabaseDialect.SQLITE

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

    def test_column_type_mapping_sqlite(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.SQLITE,
        )
        exporter = DatabaseExporter(request=request, engine=MagicMock())
        frame = pd.DataFrame(
            {
                "ts": pd.to_datetime(["2024-01-01"]),
                "count": [1],
                "ratio": [1.5],
                "active": [True],
                "label": ["x"],
            }
        )
        dtype = exporter._get_column_types(frame, DatabaseDialect.SQLITE)
        assert "ts" in dtype
        assert "count" in dtype
        assert "ratio" in dtype
        assert "active" in dtype
        assert "label" in dtype

    def test_sqlite_engine_creates_file_in_output_dir(self, tmp_path):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.SQLITE,
            output_dir=tmp_path,
            output_stem="cad",
        )
        exporter = DatabaseExporter(request=request)
        try:
            with exporter.engine.connect():
                pass
            assert (tmp_path / "cad.sqlite3").exists()
        finally:
            exporter.close()

    def test_sqlite_engine_honors_absolute_db_name(self, tmp_path):
        target = tmp_path / "custom" / "nested.db"
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.SQLITE,
            output_dir=tmp_path,
            db_name=str(target),
        )
        exporter = DatabaseExporter(request=request)
        try:
            with exporter.engine.connect():
                pass
            assert target.exists()
        finally:
            exporter.close()

    def test_sqlite_round_trip_export(self, tmp_path):
        request = GenerationRequest(
            rows=50,
            output_format=OutputFormat.SQLITE,
            output_dir=tmp_path,
            output_stem="cad",
            db_name="cad.sqlite3",
            db_batch_size=7,
        )
        request.validate()

        incidents = pd.DataFrame(
            {
                "id_number": list(range(50)),
                "agency": ["LAW"] * 50,
                "priority": [1] * 50,
                "call_start_time": pd.to_datetime(["2024-01-01"] * 50),
                "street_name": ["Main St"] * 50,
                "internal_reference_number": [f"REF-{i}" for i in range(50)],
            }
        )
        phone = pd.DataFrame({"hour": list(range(24)), "nine_one_one_calls_received": [1] * 24})

        exporter = DatabaseExporter(request=request)
        try:
            assert exporter.export_incidents(incidents) == 50
            assert exporter.export_phone_metrics(phone) == 24
        finally:
            exporter.close()

        con = sqlite3.connect(tmp_path / "cad.sqlite3")
        try:
            cur = con.execute("SELECT COUNT(*) FROM incidents")
            assert cur.fetchone()[0] == 50
            cur = con.execute("SELECT COUNT(*) FROM hourly_call_counts")
            assert cur.fetchone()[0] == 24
            cur = con.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")
            index_names = [row[0] for row in cur.fetchall()]
            assert "idx_incidents_agency" in index_names
            assert "idx_incidents_call_start_time" in index_names
            assert "idx_incidents_internal_reference_number" in index_names
            assert "idx_incidents_priority" in index_names
            cur = con.execute("SELECT id_number, agency FROM incidents LIMIT 3")
            assert cur.fetchall() == [(0, "LAW"), (1, "LAW"), (2, "LAW")]
        finally:
            con.close()

    def test_sqlite_export_table_exists_check(self, tmp_path):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.SQLITE,
            output_dir=tmp_path,
            db_name="check.sqlite3",
        )
        request.validate()
        exporter = DatabaseExporter(request=request)
        try:
            frame = pd.DataFrame({"id": [1]})
            exporter.export_incidents(frame)
            with exporter._connection() as conn:
                assert exporter._table_exists(conn, "incidents", None) is True
                assert exporter._table_exists(conn, "nope", None) is False
        finally:
            exporter.close()

    def test_sqlite_export_fail_when_table_exists(self, tmp_path):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.SQLITE,
            output_dir=tmp_path,
            db_name="fail.sqlite3",
            db_if_exists="fail",
        )
        request.validate()
        frame = pd.DataFrame({"id": [1]})
        exporter = DatabaseExporter(request=request)
        try:
            exporter.export_incidents(frame)
            with pytest.raises(Exception, match="already exists"):
                exporter.export_incidents(frame)
        finally:
            exporter.close()

    def test_sqlite_export_replace_drops_table(self, tmp_path):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.SQLITE,
            output_dir=tmp_path,
            db_name="replace.sqlite3",
            db_if_exists="replace",
        )
        request.validate()
        frame = pd.DataFrame({"id": [1, 2, 3]})
        exporter = DatabaseExporter(request=request)
        try:
            exporter.export_incidents(frame)
            exporter.export_incidents(pd.DataFrame({"id": [4, 5]}))
            con = sqlite3.connect(tmp_path / "replace.sqlite3")
            try:
                cur = con.execute("SELECT COUNT(*) FROM incidents")
                assert cur.fetchone()[0] == 2
            finally:
                con.close()
        finally:
            exporter.close()

    def test_sqlite_ignores_db_schema(self, tmp_path):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.SQLITE,
            output_dir=tmp_path,
            db_name="schema.sqlite3",
            db_schema="custom_schema",
        )
        request.validate()
        frame = pd.DataFrame({"id": [1]})
        exporter = DatabaseExporter(request=request)
        try:
            exporter.export_incidents(frame)
            con = sqlite3.connect(tmp_path / "schema.sqlite3")
            try:
                cur = con.execute("SELECT COUNT(*) FROM incidents")
                assert cur.fetchone()[0] == 1
            finally:
                con.close()
        finally:
            exporter.close()

    def test_export_to_database_sqlite_end_to_end(self, tmp_path):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.SQLITE,
            output_dir=tmp_path,
            db_name="e2e.sqlite3",
        )
        request.validate()
        datasets = {
            "incidents": pd.DataFrame({"id": [1, 2]}),
            "hourly_call_counts": pd.DataFrame({"hour": [1]}),
        }
        results = export_to_database(datasets, request)
        assert results == {"incidents": 2, "hourly_call_counts": 1}
        assert (tmp_path / "e2e.sqlite3").exists()

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

    def test_sqlite_requires_no_host(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.SQLITE,
        )
        # Should not raise and should default the db file name
        request.validate()
        assert request.db_name == "synthetic_911.sqlite3"

    def test_sqlite_default_name_uses_output_stem(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.SQLITE,
            output_stem="kansas_cad",
        )
        request.validate()
        assert request.db_name == "kansas_cad.sqlite3"

    def test_sqlite_ignores_connection_params(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.SQLITE,
            db_host="localhost",
            db_user="user",
            db_password="pass",
        )
        # Connection params should be accepted but not required for sqlite
        request.validate()

    def test_sqlite_validates_if_exists(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.SQLITE,
            db_if_exists="invalid",
        )
        with pytest.raises(Exception, match="db_if_exists must be"):
            request.validate()

    def test_sqlite_validates_batch_size(self):
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.SQLITE,
            db_batch_size=0,
        )
        with pytest.raises(Exception, match="db_batch_size must be greater"):
            request.validate()

    def test_sqlite_default_name_via_dialect_only(self):
        # db_dialect=sqlite with a file-based output_format should still default
        request = GenerationRequest(
            rows=10,
            output_format=OutputFormat.DUCKDB,
            db_dialect=DatabaseDialect.SQLITE,
        )
        request.validate()
        assert request.db_name == "synthetic_911.sqlite3"

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
