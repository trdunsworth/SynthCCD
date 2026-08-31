"""Load-testing benchmarks for the generation pipeline.

Measures throughput (rows/sec) and latency at four scale tiers:
10K, 100K, 1M, and 10M rows.  Run with::

    uv run pytest tests/test_benchmarks.py -v --benchmark-only

To compare against a saved baseline::

    uv run pytest tests/test_benchmarks.py --benchmark-compare=0001

To save a new baseline after intentional performance improvements::

    uv run pytest tests/test_benchmarks.py --benchmark-save=baseline

The 10M tier is excluded by default (slow); run explicitly with
``--benchmark-enable`` or by selecting the tier directly::

    uv run pytest tests/test_benchmarks.py -k "10m" --benchmark-only
"""

from __future__ import annotations

import tracemalloc

import pytest

from synth911gen3.addresses import StaticAddressProvider
from synth911gen3.config import DatasetKind, GenerationRequest, IdFormat, OutputFormat
from synth911gen3.domain import Address
from synth911gen3.generators import IncidentGenerator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ROWS = [10_000, 100_000, 1_000_000, 10_000_000]
_ROW_LABELS = ["10k", "100k", "1m", "10m"]

_ADDRESSES = [
    Address("101 N Main St", "Kansas City", "Missouri"),
    Address("204 E 12th St", "Kansas City", "Missouri"),
    Address("55 W 39th St", "Kansas City", "Missouri"),
    Address("777 S Broadway Blvd", "Kansas City", "Missouri"),
    Address("890 N Oak Trafficway", "Kansas City", "Missouri"),
]


def _make_request(rows: int) -> GenerationRequest:
    """Build a minimal GenerationRequest for benchmarking."""
    return GenerationRequest(
        rows=rows,
        area_query="Kansas City, MO",
        output_format=OutputFormat.PANDAS,
        dataset=DatasetKind.INCIDENTS,
        id_format=IdFormat.INTEGER,
        output_stem="bench",
        seed=42,
        calltaker_pool_size=20,
        dispatcher_pool_size=20,
    )


def _generate_incidents(rows: int) -> None:
    """Generate *rows* incident records using a static address pool."""
    request = _make_request(rows)
    provider = StaticAddressProvider(_ADDRESSES)
    gen = IncidentGenerator(address_provider=provider)
    gen.generate(request)


# ---------------------------------------------------------------------------
# Benchmark tests
# ---------------------------------------------------------------------------


class TestIncidentGenerationThroughput:
    """Benchmark incident generation at increasing scale tiers."""

    @pytest.mark.parametrize(
        "rows,label",
        list(zip(_ROWS, _ROW_LABELS)),
        ids=_ROW_LABELS,
    )
    def test_generation_throughput(
        self, benchmark, rows: int, label: str
    ) -> None:
        """Measure rows/sec for incident generation at *rows* scale."""
        benchmark.pedantic(
            _generate_incidents,
            args=(rows,),
            rounds=3 if rows <= 100_000 else 1,
            warmup_rounds=1 if rows <= 100_000 else 0,
        )


class TestMemoryUsage:
    """Track peak memory at each scale tier."""

    @pytest.mark.parametrize(
        "rows,label",
        list(zip(_ROWS, _ROW_LABELS)),
        ids=_ROW_LABELS,
    )
    def test_peak_memory(self, rows: int, label: str) -> None:
        """Measure peak memory for *rows* incident records."""
        tracemalloc.start()
        try:
            _generate_incidents(rows)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        peak_mb = peak / (1024 * 1024)
        # Soft assertion: peak memory should not exceed 2 GiB for any tier
        assert peak_mb < 2048, f"Peak memory {peak_mb:.0f} MiB exceeds 2 GiB at {label}"
