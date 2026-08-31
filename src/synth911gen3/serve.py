"""FastAPI HTTP server exposing generation as a service.

Endpoints: ``GET /health``, ``GET /schema`` (preview without fetching
addresses), ``POST /generate`` (JSON summary or file download), and
``POST /generate/stream`` (chunked CSV/Parquet response). Callers supply
generation parameters inline in the JSON body — no server-side file paths
are accepted. Run with ``python -m synth911gen3.serve`` or the CLI serve
command.
"""

from __future__ import annotations

import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from synth911gen3.addresses import OpenStreetMapAddressProvider
from synth911gen3.app import Synth911Application
from synth911gen3.config import DatasetKind, GenerationRequest, IdFormat, OutputFormat
from synth911gen3.exceptions import AddressLookupError, ExportError, ValidationError
from synth911gen3.logging_conf import get_logger
from synth911gen3.metrics import (
    ACTIVE_REQUESTS,
    GENERATION_COUNT,
    GENERATION_DURATION,
    GENERATION_ERRORS,
    REQUEST_COUNT,
    REQUEST_DURATION,
    expose_metrics,
    init_server_info,
)
from synth911gen3.params import build_request_from_params
from synth911gen3.tls import maybe_inject_system_trust

logger = get_logger("serve")

# ---------------------------------------------------------------------------
# Simple sliding-window rate limiter (in-memory, per-IP).
# ---------------------------------------------------------------------------

_DEFAULT_RATE_LIMIT = 30  # requests per window
_DEFAULT_WINDOW_SECONDS = 60


class _RateLimitMiddleware(BaseHTTPMiddleware):
    """Reject clients exceeding *max_requests* per *window_seconds* with 429.

    Tracks request counts per client IP using a sliding-window counter.
    The counter is pruned on every request so stale entries don't leak memory.
    """

    def __init__(
        self,
        app: Any,
        max_requests: int = _DEFAULT_RATE_LIMIT,
        window_seconds: int = _DEFAULT_WINDOW_SECONDS,
    ) -> None:
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        cutoff = now - self.window_seconds

        # Prune expired entries and count current window
        timestamps = self._hits[client_ip]
        self._hits[client_ip] = timestamps = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= self.max_requests:
            retry_after = int(timestamps[0] - cutoff) + 1
            return Response(
                content='{"detail":"Rate limit exceeded. Try again later."}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(retry_after)},
            )

        timestamps.append(now)
        return await call_next(request)

    def reset(self) -> None:
        """Clear all hit counters (useful for testing)."""
        self._hits.clear()


# ---------------------------------------------------------------------------
# Prometheus metrics middleware
# ---------------------------------------------------------------------------


class _MetricsMiddleware(BaseHTTPMiddleware):
    """Track request count, duration, and active-request gauge per endpoint."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip metrics for the /metrics endpoint itself to avoid recursion
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        path = request.url.path
        ACTIVE_REQUESTS.inc()
        start = time.monotonic()
        try:
            response = await call_next(request)
            elapsed = time.monotonic() - start
            REQUEST_COUNT.labels(method=method, endpoint=path, status_code=response.status_code).inc()
            REQUEST_DURATION.labels(method=method, endpoint=path).observe(elapsed)
            return response
        except Exception:
            elapsed = time.monotonic() - start
            REQUEST_COUNT.labels(method=method, endpoint=path, status_code=500).inc()
            REQUEST_DURATION.labels(method=method, endpoint=path).observe(elapsed)
            raise
        finally:
            ACTIVE_REQUESTS.dec()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Inject the OS trust store before the server starts serving requests.

    Runs exactly once at startup (before any request) when
    ``SYNTHCCD_SYSTEM_TRUST=1`` so OSM address lookups work behind
    TLS-inspecting corporate proxies. The injection is a no-op unless the
    environment variable is set and is guarded internally so the global
    ``ssl`` module is patched at most once per process.

    Also initialises the ``synthccd_info`` Prometheus metric with package
    and Python version metadata.
    """
    import sys

    from synth911gen3 import __version__ as pkg_version

    maybe_inject_system_trust()
    init_server_info(version=pkg_version, python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    yield


app = FastAPI(
    title="SynthCCD API",
    description="Synthetic 911 CAD incident and hourly phone-center data generator",
    version="0.1.0",
    lifespan=_lifespan,
)
app.add_middleware(_RateLimitMiddleware)
app.add_middleware(_MetricsMiddleware)


class GenerationRequestModel(BaseModel):
    """Request model for data generation endpoint.

    Callers supply all parameters inline in the JSON body.  Server-side
    file paths (``params_file``, ``realism_config_path``) are intentionally
    excluded to prevent path-traversal attacks.
    """

    rows: int | None = Field(default=None, ge=1, description="Number of incident rows")
    area_query: str | None = Field(default=None, description="OpenStreetMap area query")
    output_format: str | None = Field(
        default=None, description="Output format: csv, parquet, json, yaml, pandas, polars"
    )
    dataset: str | None = Field(
        default=None, description="Dataset to generate: incidents, phone, all"
    )
    id_format: str | None = Field(default=None, description="ID format: integer or guid")
    output_dir: str | None = Field(default=None, description="Output directory")
    output_stem: str | None = Field(default=None, description="Filename stem for exports")
    start_date: str | None = Field(default=None, description="Start date YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="End date YYYY-MM-DD")
    seed: int | None = Field(default=None, description="Random seed")
    calltaker_pool_size: int | None = Field(default=None, ge=1, description="Calltaker pool size")
    dispatcher_pool_size: int | None = Field(default=None, ge=1, description="Dispatcher pool size")
    shift_preset: str | None = Field(default=None, description="Shift preset name")
    max_memory_bytes: int | None = Field(default=None, ge=1, description="Per-chunk memory budget")
    population: int | None = Field(
        default=None, ge=1, description="Service area population for phone-volume scaling"
    )
    psap_agency: str | None = Field(
        default=None,
        description="PSAP agency filter: all, law, fire, ems, fire_ems",
    )
    realism_config_path: str | None = Field(default=None, description="Path to YAML realism config")

    @field_validator("output_format", mode="before")
    @classmethod
    def _validate_output_format(cls, v: str | None) -> str | None:
        """Normalize and validate the output_format string."""
        if v is None:
            return None
        valid = {"csv", "parquet", "json", "yaml", "pandas", "polars"}
        if v.lower() not in valid:
            raise ValueError(f"output_format must be one of {valid}")
        return v.lower()

    @field_validator("dataset", mode="before")
    @classmethod
    def _validate_dataset(cls, v: str | None) -> str | None:
        """Normalize and validate the dataset string."""
        if v is None:
            return None
        valid = {"incidents", "phone", "all"}
        if v.lower() not in valid:
            raise ValueError(f"dataset must be one of {valid}")
        return v.lower()

    @field_validator("id_format", mode="before")
    @classmethod
    def _validate_id_format(cls, v: str | None) -> str | None:
        """Normalize and validate the id_format string."""
        if v is None:
            return None
        valid = {"integer", "guid"}
        if v.lower() not in valid:
            raise ValueError(f"id_format must be one of {valid}")
        return v.lower()

    @field_validator("psap_agency", mode="before")
    @classmethod
    def _validate_psap_agency(cls, v: str | None) -> str | None:
        """Normalize and validate the psap_agency string."""
        if v is None:
            return None
        valid = {"all", "law", "fire", "ems", "fire_ems"}
        if v.lower() not in valid:
            raise ValueError(f"psap_agency must be one of {valid}")
        return v.lower()


class SchemaResponse(BaseModel):
    """Schema information for a dataset."""

    dataset: str
    columns: list[dict[str, str]]
    row_count: int


class DryRunResponse(BaseModel):
    """Dry run response with schema and sample rows."""

    message: str
    schemas: list[SchemaResponse]


def _build_request(model: GenerationRequestModel) -> GenerationRequest:
    """Build GenerationRequest from API model.

    All parameters come from the JSON body — no server-side file I/O.
    """
    cli_params: dict[str, Any] = {}
    if model.rows is not None:
        cli_params["rows"] = model.rows
    if model.area_query is not None:
        cli_params["area_query"] = model.area_query
    if model.output_format is not None:
        cli_params["output_format"] = OutputFormat(model.output_format.upper())
    if model.dataset is not None:
        cli_params["dataset"] = DatasetKind(model.dataset.upper())
    if model.id_format is not None:
        cli_params["id_format"] = IdFormat(model.id_format.upper())
    if model.output_dir is not None:
        cli_params["output_dir"] = Path(model.output_dir)
    if model.output_stem is not None:
        cli_params["output_stem"] = model.output_stem
    if model.start_date is not None:
        cli_params["start_date"] = model.start_date
    if model.end_date is not None:
        cli_params["end_date"] = model.end_date
    if model.seed is not None:
        cli_params["seed"] = model.seed
    if model.calltaker_pool_size is not None:
        cli_params["calltaker_pool_size"] = model.calltaker_pool_size
    if model.dispatcher_pool_size is not None:
        cli_params["dispatcher_pool_size"] = model.dispatcher_pool_size
    if model.shift_preset is not None:
        cli_params["shift_preset"] = model.shift_preset
    if model.max_memory_bytes is not None:
        cli_params["max_memory_bytes"] = model.max_memory_bytes
    if model.population is not None:
        cli_params["population"] = model.population
    if model.psap_agency is not None:
        cli_params["psap_agency"] = model.psap_agency
    if model.realism_config_path is not None:
        cli_params["realism_config_path"] = Path(model.realism_config_path)

    return build_request_from_params({}, cli_params)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "SynthCCD"}


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint.

    Returns the full text exposition format for scraping by a Prometheus
    server or compatible collector.  Covers request counts, generation
    performance, active-request gauge, and address-cache statistics.
    """
    payload = expose_metrics()
    return Response(
        content=payload,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/schema")
async def get_schema(
    rows: int = Query(100, ge=1, description="Number of rows for schema probe"),
    dataset: str = Query("incidents", description="Dataset: incidents, phone, all"),
    output_format: str = Query("pandas", description="Output format for probe"),
    area_query: str = Query("Kansas City, MO", description="Area query for addresses"),
    seed: int = Query(911, description="Random seed"),
    config: str | None = Query(None, description="Path to realism config YAML"),
) -> DryRunResponse:
    """
    Get the schema (column names and types) for the generated datasets without
    fetching addresses or running a full generation. Uses a static address pool.
    """
    try:
        request = GenerationRequest(
            rows=rows,
            dataset=DatasetKind(dataset.upper()),
            output_format=OutputFormat(output_format.upper()),
            area_query=area_query,
            seed=seed,
            output_dir=Path("/tmp"),
            output_stem="schema_probe",
        )
        if config:
            request.realism_config_path = Path(config)

        from synth911gen3.describe import build_preview_datasets

        preview = build_preview_datasets(request, schema_only=True)

        schemas = []
        for name, frame in preview.items():
            schemas.append(
                SchemaResponse(
                    dataset=name,
                    columns=[
                        {"name": col, "type": str(dtype)} for col, dtype in frame.dtypes.items()
                    ],
                    row_count=len(frame),
                )
            )

        return DryRunResponse(
            message="Schema preview: no files written, no OpenStreetMap fetch (illustrative sample addresses).",
            schemas=schemas,
        )
    except (AddressLookupError, ExportError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Unexpected error in /schema")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/generate", response_model=None)
async def generate_data(
    request_model: GenerationRequestModel,
    download: bool = Query(
        False, description="If true, return file download; otherwise return JSON summary"
    ),
) -> Any:
    """
    Generate synthetic 911 data. Returns either a JSON summary of generated files
    or the file itself (for single-file formats like json/yaml).
    """
    dataset_label = request_model.dataset or "incidents"
    format_label = request_model.output_format or "csv"
    GENERATION_COUNT.labels(dataset=dataset_label, output_format=format_label).inc()
    gen_start = time.monotonic()
    try:
        request = _build_request(request_model)

        with TemporaryDirectory() as tmpdir:
            request.output_dir = Path(tmpdir)
            result = Synth911Application(address_provider=OpenStreetMapAddressProvider()).generate(
                request
            )

            if request.output_format in (OutputFormat.PANDAS, OutputFormat.POLARS):
                return {
                    "message": "In-memory format requested; no files written.",
                    "incidents_shape": result.incidents.shape
                    if result.incidents is not None
                    else None,
                    "hourly_call_counts_shape": result.hourly_call_counts.shape
                    if result.hourly_call_counts is not None
                    else None,
                }

            # For file-based formats, return the first artifact or all artifacts
            artifacts = result.exported_artifacts
            if not artifacts:
                return {"message": "No artifacts generated"}

            if download and len(artifacts) == 1:
                # Single file download
                _dataset_name, path = next(iter(artifacts.items()))
                return FileResponse(
                    path=path,
                    filename=Path(path).name,
                    media_type="application/octet-stream",
                )

            # Return summary of all generated files
            return {
                "message": "Generation complete",
                "files": {name: str(path) for name, path in artifacts.items()},
                "incidents_shape": result.incidents.shape if result.incidents is not None else None,
                "hourly_call_counts_shape": result.hourly_call_counts.shape
                if result.hourly_call_counts is not None
                else None,
            }

    except (AddressLookupError, ExportError, ValidationError) as exc:
        elapsed = time.monotonic() - gen_start
        GENERATION_DURATION.labels(dataset=dataset_label, output_format=format_label).observe(elapsed)
        GENERATION_ERRORS.labels(dataset=dataset_label, error_type=type(exc).__name__).inc()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        elapsed = time.monotonic() - gen_start
        GENERATION_DURATION.labels(dataset=dataset_label, output_format=format_label).observe(elapsed)
        GENERATION_ERRORS.labels(dataset=dataset_label, error_type="internal").inc()
        logger.exception("Unexpected error in /generate")
        raise HTTPException(status_code=500, detail="Internal server error")
    else:
        elapsed = time.monotonic() - gen_start
        GENERATION_DURATION.labels(dataset=dataset_label, output_format=format_label).observe(elapsed)


@app.post("/generate/stream")
async def generate_data_stream(
    request_model: GenerationRequestModel,
    dataset: str = Query("incidents", description="Dataset to stream: incidents or phone"),
) -> StreamingResponse:
    """
    Stream generated data as CSV or Parquet. For large datasets, this avoids
    loading the entire file into memory.
    """
    dataset_label = dataset
    format_label = request_model.output_format or "csv"
    GENERATION_COUNT.labels(dataset=dataset_label, output_format=format_label).inc()
    gen_start = time.monotonic()
    try:
        request = _build_request(request_model)

        with TemporaryDirectory() as tmpdir:
            request.output_dir = Path(tmpdir)
            request.dataset = DatasetKind(dataset.upper())

            result = Synth911Application(address_provider=OpenStreetMapAddressProvider()).generate(
                request
            )

            artifacts = result.exported_artifacts
            if not artifacts:
                raise HTTPException(status_code=404, detail="No data generated")

            dataset_key = f"{dataset}s" if dataset == "phone" else dataset
            if dataset_key not in artifacts:
                # Try exact match
                if dataset not in artifacts:
                    raise HTTPException(status_code=404, detail=f"Dataset {dataset} not found")
                dataset_key = dataset

            path = artifacts[dataset_key]
            suffix = Path(path).suffix.lower()

            if suffix == ".csv":
                media_type = "text/csv"
            elif suffix == ".parquet":
                media_type = "application/octet-stream"
            else:
                media_type = "application/octet-stream"

            def iter_file():
                with open(path, "rb") as f:
                    yield from f

            elapsed = time.monotonic() - gen_start
            GENERATION_DURATION.labels(dataset=dataset_label, output_format=format_label).observe(elapsed)
            return StreamingResponse(
                iter_file(),
                media_type=media_type,
                headers={"Content-Disposition": f'attachment; filename="{Path(path).name}"'},
            )

    except (AddressLookupError, ExportError, ValidationError) as exc:
        elapsed = time.monotonic() - gen_start
        GENERATION_DURATION.labels(dataset=dataset_label, output_format=format_label).observe(elapsed)
        GENERATION_ERRORS.labels(dataset=dataset_label, error_type=type(exc).__name__).inc()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        elapsed = time.monotonic() - gen_start
        GENERATION_DURATION.labels(dataset=dataset_label, output_format=format_label).observe(elapsed)
        GENERATION_ERRORS.labels(dataset=dataset_label, error_type="internal").inc()
        logger.exception("Unexpected error in /generate/stream")
        raise HTTPException(status_code=500, detail="Internal server error")


def run() -> None:
    """Entry point for the serve command.

    Binds to ``127.0.0.1:8000`` by default.  Override with the
    ``SYNTHCCD_SERVE_HOST`` and ``SYNTHCCD_SERVE_PORT`` environment
    variables, or use ``uvicorn synth911gen3.serve:app --host … --port …``
    directly for full control.
    """
    import os

    import uvicorn

    host = os.environ.get("SYNTHCCD_SERVE_HOST", "127.0.0.1")
    port = int(os.environ.get("SYNTHCCD_SERVE_PORT", "8000"))

    uvicorn.run(
        "synth911gen3.serve:app",
        host=host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    run()
