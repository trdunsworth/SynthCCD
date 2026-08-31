"""Prometheus metrics for the SynthCCD API server and generation pipeline.

Exposes counters, histograms, and gauges for request tracking, generation
performance, and resource usage.  All metrics live under the ``synthccd_``
namespace so they coexist cleanly with other exporters in a shared
Prometheus scrape.

Usage from serve.py::

    from synth911gen3.metrics import (
        REQUEST_COUNT,
        REQUEST_DURATION,
        GENERATION_ROWS,
        GENERATION_DURATION,
        ACTIVE_REQUESTS,
        GENERATION_ERRORS,
    )

Middleware and endpoints increment these directly; the ``/metrics`` endpoint
serves the text exposition format via ``prometheus_client.generate_latest()``.
"""

from __future__ import annotations

from prometheus_client import (
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)

# ---------------------------------------------------------------------------
# Server request metrics
# ---------------------------------------------------------------------------

REQUEST_COUNT = Counter(
    "synthccd_requests_total",
    "Total HTTP requests served",
    ["method", "endpoint", "status_code"],
)

REQUEST_DURATION = Histogram(
    "synthccd_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

ACTIVE_REQUESTS = Gauge(
    "synthccd_active_requests",
    "Number of requests currently being processed",
)

# ---------------------------------------------------------------------------
# Generation pipeline metrics
# ---------------------------------------------------------------------------

GENERATION_COUNT = Counter(
    "synthccd_generations_total",
    "Total generation runs started",
    ["dataset", "output_format"],
)

GENERATION_ROWS = Counter(
    "synthccd_generation_rows_total",
    "Total rows generated",
    ["dataset"],
)

GENERATION_DURATION = Histogram(
    "synthccd_generation_duration_seconds",
    "Time spent generating data (from request to result)",
    ["dataset", "output_format"],
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

GENERATION_ERRORS = Counter(
    "synthccd_generation_errors_total",
    "Total generation errors",
    ["dataset", "error_type"],
)

# ---------------------------------------------------------------------------
# Resource / system metrics
# ---------------------------------------------------------------------------

ADDRESS_CACHE_HITS = Counter(
    "synthccd_address_cache_hits_total",
    "Address cache hits (served from local Parquet cache)",
)

ADDRESS_CACHE_MISSES = Counter(
    "synthccd_address_cache_misses_total",
    "Address cache misses (required OSM fetch)",
)

CHUNK_COUNT = Counter(
    "synthccd_chunks_total",
    "Total chunks exported during chunked generation",
    ["dataset"],
)

# ---------------------------------------------------------------------------
# Server info
# ---------------------------------------------------------------------------

SERVER_INFO = Info(
    "synthccd",
    "SynthCCD server build and version information",
)


def expose_metrics() -> bytes:
    """Return the Prometheus text exposition payload for all registered metrics."""
    return generate_latest(REGISTRY)


def init_server_info(version: str, python_version: str) -> None:
    """Populate the ``synthccd_info`` metric with static build metadata."""
    SERVER_INFO.info({"version": version, "python_version": python_version})
