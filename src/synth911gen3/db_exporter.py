"""SQL database export for generated datasets.

Bridges the pandas/sqlalchemy stack to every supported dialect: DuckDB
and SQLite (local file databases) plus PostgreSQL, SQL Server, and
MariaDB (server databases). Handles table existence checks, ``if_exists``
semantics, schema-qualified names, batch-size capping (SQLite's 999
bound-parameter limit), column types per dialect, and index creation on
key columns. Missing optional drivers raise :class:`ExportError` with an
install hint.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pandas as pd
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from .config import DatabaseDialect, GenerationRequest, OutputFormat
from .exceptions import ExportError
from .logging_conf import get_logger

logger = get_logger("db_exporter")


@dataclass(slots=True)
class DatabaseExporter:
    """Wraps a SQLAlchemy engine built from a GenerationRequest's DB options."""

    request: GenerationRequest
    engine: Engine | None = None

    def __post_init__(self) -> None:
        """Build the engine when one was not injected (e.g. for tests)."""
        if self.engine is None:
            self.engine = self._create_engine()

    def _create_engine(self) -> Engine:
        """Route to the dialect-specific engine factory."""
        dialect = self._get_dialect()
        if dialect == DatabaseDialect.DUCKDB:
            return self._create_duckdb_engine()
        elif dialect == DatabaseDialect.SQLITE:
            return self._create_sqlite_engine()
        elif dialect == DatabaseDialect.POSTGRESQL:
            return self._create_postgresql_engine()
        elif dialect == DatabaseDialect.SQLSERVER:
            return self._create_sqlserver_engine()
        elif dialect == DatabaseDialect.MARIADB:
            return self._create_mariadb_engine()
        else:
            raise ExportError(f"Unsupported database dialect: {dialect}")

    def _get_dialect(self) -> DatabaseDialect:
        """Resolve the dialect from the request (explicit option wins over format)."""
        dialect_map = {
            OutputFormat.POSTGRESQL: DatabaseDialect.POSTGRESQL,
            OutputFormat.SQLSERVER: DatabaseDialect.SQLSERVER,
            OutputFormat.MARIADB: DatabaseDialect.MARIADB,
            OutputFormat.DUCKDB: DatabaseDialect.DUCKDB,
            OutputFormat.SQLITE: DatabaseDialect.SQLITE,
        }
        return self.request.db_dialect or dialect_map[self.request.output_format]

    def _create_duckdb_engine(self) -> Engine:
        """DuckDB engine over a local ``.duckdb`` file in the output directory."""
        try:
            import duckdb_engine  # noqa: F401
        except ImportError as exc:
            raise ExportError(
                "DuckDB export requires 'duckdb-engine' package. Install with: uv add duckdb-engine"
            ) from exc

        db_path: str = self.request.db_name or f"{self.request.output_stem}.duckdb"
        path_obj = Path(db_path)
        if not path_obj.is_absolute():
            path_obj = self.request.output_dir / path_obj
        path_obj.parent.mkdir(parents=True, exist_ok=True)

        # Use SQLAlchemy with duckdb-engine
        try:
            return sa.create_engine(f"duckdb:///{path_obj}")
        except Exception as exc:
            raise ExportError(f"Failed to create DuckDB engine: {exc}") from exc

    def _create_sqlite_engine(self) -> Engine:
        """Create a SQLite engine backed by a local file (stdlib sqlite3 driver)."""
        db_path: str = self.request.db_name or f"{self.request.output_stem}.sqlite3"
        path_obj = Path(db_path)
        if not path_obj.is_absolute():
            path_obj = self.request.output_dir / path_obj
        path_obj.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Absolute path so the file lands in output_dir regardless of CWD
            return sa.create_engine(f"sqlite:///{path_obj}")
        except Exception as exc:
            raise ExportError(f"Failed to create SQLite engine: {exc}") from exc

    def _create_postgresql_engine(self) -> Engine:
        """PostgreSQL engine via psycopg2 (requires the optional driver)."""
        try:
            import psycopg2  # noqa: F401
        except ImportError as exc:
            raise ExportError(
                "PostgreSQL export requires 'psycopg2' package. Install with: uv add psycopg2-binary"
            ) from exc

        url = sa.URL.create(
            drivername="postgresql+psycopg2",
            username=self.request.db_user,
            password=self.request.db_password,
            host=self.request.db_host,
            port=self.request.db_port,
            database=self.request.db_name,
        )
        return sa.create_engine(url, pool_pre_ping=True)

    def _create_sqlserver_engine(self) -> Engine:
        """SQL Server engine via pyodbc with the ODBC Driver 17 DSN."""
        pyodbc_module = None
        try:
            import pyodbc

            pyodbc_module = pyodbc
        except ImportError:
            pass
        if pyodbc_module is None:
            raise ExportError(
                "SQL Server export requires 'pyodbc' package. Install with: uv add pyodbc"
            )

        url = sa.URL.create(
            drivername="mssql+pyodbc",
            username=self.request.db_user,
            password=self.request.db_password,
            host=self.request.db_host,
            port=self.request.db_port,
            database=self.request.db_name,
            query={"driver": "ODBC Driver 17 for SQL Server"},
        )
        return sa.create_engine(url, pool_pre_ping=True)

    def _create_mariadb_engine(self) -> Engine:
        """MariaDB/MySQL engine via PyMySQL (requires the optional driver)."""
        try:
            import pymysql  # noqa: F401
        except ImportError as exc:
            raise ExportError(
                "MariaDB/MySQL export requires 'pymysql' package. Install with: uv add pymysql"
            ) from exc

        url = sa.URL.create(
            drivername="mysql+pymysql",
            username=self.request.db_user,
            password=self.request.db_password,
            host=self.request.db_host,
            port=self.request.db_port,
            database=self.request.db_name,
        )
        return sa.create_engine(url, pool_pre_ping=True)

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        """Yield a committed-on-success connection; roll back on any exception."""
        if self.engine is None:
            raise ExportError("Database engine not initialized")
        conn = self.engine.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def export_incidents(self, frame: pd.DataFrame) -> int:
        """Write the incidents frame to the configured incidents table; returns row count."""
        return self._export_table(frame, self.request.db_table_incidents)

    def export_phone_metrics(self, frame: pd.DataFrame) -> int:
        """Write the phone-metrics frame to its table; returns row count."""
        return self._export_table(frame, self.request.db_table_phone)

    def _export_table(self, frame: pd.DataFrame, table_name: str) -> int:
        """Create (if needed) and stream a frame into ``table_name`` in batches."""
        if frame.empty:
            logger.info("No data to export for table %s", table_name)
            return 0

        dialect = self._get_dialect()
        schema = self.request.db_schema
        if dialect == DatabaseDialect.SQLITE:
            # SQLite has no schema concept; ignore any requested schema
            if self.request.db_schema:
                logger.warning(
                    "SQLite has no schemas; ignoring db_schema=%r", self.request.db_schema
                )
            schema = None
        if_exists = self.request.db_if_exists
        batch_size = self.request.db_batch_size
        if dialect == DatabaseDialect.SQLITE and len(frame.columns) > 0:
            # SQLite caps bound parameters per statement at 999
            # (SQLITE_MAX_VARIABLE_NUMBER); cap the batch so that
            # rows * columns stays under the limit.
            max_rows_per_statement = max(1, 999 // len(frame.columns))
            if batch_size > max_rows_per_statement:
                logger.debug(
                    "Capping SQLite batch size from %d to %d for %d columns",
                    batch_size,
                    max_rows_per_statement,
                    len(frame.columns),
                )
                batch_size = max_rows_per_statement

        # Prepare column types for better schema control
        dtype = self._get_column_types(frame, dialect)

        total_rows = 0
        with self._connection() as conn:
            # Handle if_exists behavior
            if if_exists == "replace":
                self._drop_table(conn, table_name, schema)
            elif if_exists == "fail" and self._table_exists(conn, table_name, schema):
                raise ExportError(f"Table {table_name} already exists and if_exists='fail'")

            # Create table if it doesn't exist
            if not self._table_exists(conn, table_name, schema):
                self._create_table(conn, frame, table_name, schema, dtype, dialect)

            # Create indexes after table creation
            if self.request.db_create_indexes:
                self._create_indexes(conn, table_name, schema, frame, dialect)

            # Stream insert in batches
            for i in range(0, len(frame), batch_size):
                batch = frame.iloc[i : i + batch_size]
                batch.to_sql(
                    name=table_name,
                    con=conn,
                    schema=schema,
                    if_exists="append",
                    index=False,
                    dtype=cast(Any, dtype),
                    method="multi",
                )
                total_rows += len(batch)
                logger.debug("Inserted batch %d-%d into %s", i, i + len(batch), table_name)

        logger.info("Exported %d rows to %s.%s", total_rows, schema or "public", table_name)
        return total_rows

    def _table_exists(self, conn: Connection, table_name: str, schema: str | None) -> bool:
        """Dialect-specific existence check against the catalog tables."""
        dialect = self._get_dialect()
        if dialect == DatabaseDialect.DUCKDB:
            result = conn.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_name = :name"),
                {"name": table_name},
            ).fetchone()
        elif dialect == DatabaseDialect.SQLITE:
            result = conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name"),
                {"name": table_name},
            ).fetchone()
        elif dialect == DatabaseDialect.POSTGRESQL:
            result = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = COALESCE(:schema, 'public') AND table_name = :name"
                ),
                {"schema": schema, "name": table_name},
            ).fetchone()
        elif dialect == DatabaseDialect.SQLSERVER:
            result = conn.execute(
                text(
                    "SELECT 1 FROM INFORMATION_SCHEMA.TABLES "
                    "WHERE TABLE_SCHEMA = COALESCE(:schema, 'dbo') AND TABLE_NAME = :name"
                ),
                {"schema": schema, "name": table_name},
            ).fetchone()
        elif dialect == DatabaseDialect.MARIADB:
            result = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = COALESCE(:schema, DATABASE()) AND table_name = :name"
                ),
                {"schema": schema, "name": table_name},
            ).fetchone()
        else:
            return False
        return result is not None

    def _drop_table(self, conn: Connection, table_name: str, schema: str | None) -> None:
        """Dialect-specific ``DROP TABLE IF EXISTS`` (quotes/schema syntax vary)."""
        dialect = self._get_dialect()
        if dialect == DatabaseDialect.DUCKDB or dialect == DatabaseDialect.SQLITE:
            conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
        elif dialect == DatabaseDialect.POSTGRESQL:
            schema_part = f'"{schema}".' if schema else ""
            conn.execute(text(f'DROP TABLE IF EXISTS {schema_part}"{table_name}" CASCADE'))
        elif dialect == DatabaseDialect.SQLSERVER:
            schema_part = f"[{schema}]." if schema else "[dbo]."
            conn.execute(text(f"DROP TABLE IF EXISTS {schema_part}[{table_name}]"))
        elif dialect == DatabaseDialect.MARIADB:
            schema_part = f"`{schema}`." if schema else ""
            conn.execute(text(f"DROP TABLE IF EXISTS {schema_part}`{table_name}`"))

    def _create_table(
        self,
        conn: Connection,
        frame: pd.DataFrame,
        table_name: str,
        schema: str | None,
        dtype: dict[str, sa.types.TypeEngine],
        dialect: DatabaseDialect,
    ) -> None:
        """Create the table structure via pandas ``to_sql`` on an empty head."""
        # Use pandas to_sql with a single row to create the table structure
        frame.head(0).to_sql(
            name=table_name,
            con=conn,
            schema=schema,
            if_exists="replace",
            index=False,
            dtype=cast(Any, dtype),
        )

    def _create_indexes(
        self,
        conn: Connection,
        table_name: str,
        schema: str | None,
        frame: pd.DataFrame,
        dialect: DatabaseDialect,
    ) -> None:
        """Create indexes on common query columns present in the frame."""
        # Common indexes for incident data
        index_columns = [
            "call_start_time",
            "agency",
            "priority",
            "internal_reference_number",
        ]
        for col in index_columns:
            if col in frame.columns:
                self._create_index(conn, table_name, schema, col, dialect)

    def _create_index(
        self,
        conn: Connection,
        table_name: str,
        schema: str | None,
        column: str,
        dialect: DatabaseDialect,
    ) -> None:
        """Create one index with dialect-appropriate quoting; failures are logged, not fatal."""
        schema_prefix = f"{schema}." if schema else ""
        idx_name = f"idx_{table_name}_{column}"

        try:
            if dialect == DatabaseDialect.DUCKDB or dialect == DatabaseDialect.SQLITE or dialect == DatabaseDialect.POSTGRESQL:
                conn.execute(
                    text(
                        f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON {schema_prefix}"{table_name}" ("{column}")'
                    )
                )
            elif dialect == DatabaseDialect.SQLSERVER:
                conn.execute(
                    text(f"CREATE INDEX [{idx_name}] ON {schema_prefix}[{table_name}] ([{column}])")
                )
            elif dialect == DatabaseDialect.MARIADB:
                conn.execute(
                    text(f"CREATE INDEX `{idx_name}` ON {schema_prefix}`{table_name}` (`{column}`)")
                )
        except Exception as exc:
            # Index creation might fail if already exists or column type doesn't support indexing
            logger.debug("Could not create index %s on %s: %s", idx_name, table_name, exc)

    def _get_column_types(
        self, frame: pd.DataFrame, dialect: DatabaseDialect
    ) -> dict[str, sa.types.TypeEngine]:
        """Map pandas dtypes to SQLAlchemy column types appropriate for the dialect."""
        dtype: dict[str, sa.types.TypeEngine] = {}
        for col in frame.columns:
            series = frame[col]
            if pd.api.types.is_datetime64_any_dtype(series):
                if dialect == DatabaseDialect.DUCKDB:
                    dtype[col] = sa.TIMESTAMP()
                elif dialect == DatabaseDialect.SQLITE:
                    dtype[col] = sa.DateTime()
                elif dialect == DatabaseDialect.POSTGRESQL:
                    dtype[col] = sa.TIMESTAMP(timezone=False)
                elif dialect == DatabaseDialect.SQLSERVER or dialect == DatabaseDialect.MARIADB:
                    dtype[col] = sa.DateTime()
            elif pd.api.types.is_integer_dtype(series):
                dtype[col] = sa.BIGINT()
            elif pd.api.types.is_float_dtype(series):
                dtype[col] = sa.DOUBLE_PRECISION()
            elif pd.api.types.is_bool_dtype(series):
                dtype[col] = sa.BOOLEAN()
            else:
                dtype[col] = sa.Text()
        return dtype

    def close(self) -> None:
        """Dispose the engine (releases pooled connections)."""
        if self.engine:
            self.engine.dispose()
            self.engine = None


def export_to_database(
    datasets: dict[str, pd.DataFrame],
    request: GenerationRequest,
) -> dict[str, int]:
    """Export datasets to database. Returns dict of table_name -> row_count."""
    exporter = DatabaseExporter(request)
    try:
        results = {}
        if "incidents" in datasets:
            results["incidents"] = exporter.export_incidents(datasets["incidents"])
        if "hourly_call_counts" in datasets:
            results["hourly_call_counts"] = exporter.export_phone_metrics(
                datasets["hourly_call_counts"]
            )
        return results
    finally:
        exporter.close()
