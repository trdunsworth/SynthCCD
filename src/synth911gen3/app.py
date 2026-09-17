"""Application-level orchestration of a generation run.

:class:`Synth911Application` is the single entry point shared by the CLI,
TUI, and server: it validates the request, builds the requested datasets
(streaming incidents in chunks for very large CSV/Parquet runs), routes
to the file/database exporters, and assembles the final
:class:`~synth911gen3.domain.GenerationResult` with the governance
manifest.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from .addresses import AddressProvider, OpenStreetMapAddressProvider
from .config import DatasetKind, GenerationRequest, OutputFormat
from .db_exporter import export_to_database
from .domain import GenerationResult
from .exporters import export_chunked_generator, export_generated_data, export_manifest
from .generators import HourlyCallCountGenerator, IncidentGenerator
from .logging_conf import get_logger
from .manifest import Manifest
from .metrics import GENERATION_ROWS

logger = get_logger("app")


class Synth911Application:
    """Orchestrates dataset generation and export for a single request."""

    def __init__(self, address_provider: AddressProvider | None = None) -> None:
        """Use the given provider (tests) or the default OpenStreetMap-backed one."""
        self._address_provider = address_provider or OpenStreetMapAddressProvider()

    def generate(
        self,
        request: GenerationRequest,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> GenerationResult:
        """Generate and export the datasets requested by ``request``.

        Args:
            request: Validated run configuration.
            on_progress: Optional ``(dataset, done, total)`` callback for
                progress reporting during incident generation.

        Returns:
            The generated frames (when materialized) plus exported artifact
            paths. CSV/Parquet runs that exceed the memory budget return
            streamed artifacts instead of frames.
        """
        request.validate()
        # Auto-resolve population from the address provider when the user
        # did not supply --population.  The provider extracts it from the
        # Nominatim extratags.population field during geocoding, so we
        # trigger address loading here (cache hit is cheap on repeat runs).
        if request.population is None and hasattr(self._address_provider, "resolved_population"):
            try:
                self._address_provider.load_addresses(request.area_query)
            except Exception:
                logger.debug("Address preload for population lookup failed; continuing")
            resolved_pop = self._address_provider.resolved_population()
            if resolved_pop is not None and resolved_pop > 0:
                request.population = resolved_pop
                request.population_source = "nominatim"
                logger.info(
                    "Auto-resolved population from Nominatim: %d (area: %s)",
                    resolved_pop,
                    request.area_query,
                )
            else:
                logger.info(
                    "No population available from Nominatim for '%s'", request.area_query
                )
        # Resolve the rows/population precedence once up front so every
        # downstream consumer (chunking, generators, manifest, logging) sees
        # a concrete count. Explicit rows always win; population derivation
        # only fills the gap (see GenerationRequest.resolved_rows).
        if request.rows is None:
            request.rows = request.resolved_rows()
            if request.population is not None:
                logger.info(
                    "Derived incident rows from population %d: %d rows",
                    request.population,
                    request.rows,
                )
        assert request.rows is not None  # narrowed: resolved above

        # Resolve the effective output format (may auto-switch to Parquet)
        effective_format = request.resolved_output_format()
        if effective_format != request.output_format:
            logger.info(
                "Auto-switched format: %s -> %s (threshold: %s rows)",
                request.output_format.value,
                effective_format.value,
                request.auto_parquet_threshold if request.auto_parquet_threshold is not None else 100000,
            )

        datasets = {}
        incidents = None
        hourly_call_counts = None
        hourly_event_counts: dict[pd.Timestamp, int] | None = None
        streamed_artifacts: dict[str, object] = {}

        if request.dataset in (DatasetKind.INCIDENTS, DatasetKind.ALL):
            logger.info("Building incident dataset (%d rows)", request.rows)
            incident_generator = IncidentGenerator(self._address_provider)
            incident_progress = (
                (lambda done, total: on_progress("incidents", done, total))
                if on_progress is not None
                else None
            )
            if effective_format in (OutputFormat.CSV, OutputFormat.PARQUET):
                chunk_frames = incident_generator.generate_chunks(
                    request, on_progress=incident_progress
                )
                first_chunk = next(chunk_frames)
                if len(first_chunk) < request.rows:
                    # Embed request provenance (seed, config hash, schema version,
                    # …) in the Parquet footer; the first chunk's columns give an
                    # accurate schema hash for the whole incident dataset.
                    chunk_metadata: dict[str, str] | None = None
                    if effective_format is OutputFormat.PARQUET:
                        chunk_metadata = Manifest.from_request(
                            request, {"incidents": first_chunk}
                        ).to_kv_metadata()
                    # Accumulate event counts per hour when requested, then
                    # chain all chunks (including the first) for export.
                    hourly_event_counts: dict[pd.Timestamp, int] | None = None
                    all_chunks: list[pd.DataFrame] = [first_chunk]
                    if request.include_event_counts:
                        hourly_event_counts = {}
                        all_chunks = [first_chunk, *chunk_frames]
                        for chunk in all_chunks:
                            hours = chunk["call_start_time"].dt.floor("h")
                            for hour, count in hours.value_counts().items():
                                hourly_event_counts[hour] = (
                                    hourly_event_counts.get(hour, 0) + int(count)
                                )
                    else:
                        all_chunks.extend(chunk_frames)
                    path = export_chunked_generator(
                        iter(all_chunks),
                        output_format=effective_format,
                        output_dir=request.output_dir,
                        output_stem=request.output_stem,
                        dataset_name="incidents",
                        parquet_metadata=chunk_metadata,
                    )
                    streamed_artifacts["incidents"] = path
                    logger.info(
                        "Incidents streamed to %s in chunks (budget: %s bytes)",
                        path,
                        request.max_memory_bytes
                        if request.max_memory_bytes is not None
                        else "default",
                    )
                else:
                    incidents = first_chunk
                    datasets["incidents"] = incidents
            else:
                incidents = incident_generator.generate(request, on_progress=incident_progress)
                datasets["incidents"] = incidents
            if incidents is not None:
                logger.info(
                    "Incidents built: %d rows x %d columns", len(incidents), len(incidents.columns)
                )
                GENERATION_ROWS.labels(dataset="incidents").inc(len(incidents))
                if request.include_event_counts:
                    hourly_event_counts = {}
                    hours = incidents["call_start_time"].dt.floor("h")
                    for hour, count in hours.value_counts().items():
                        hourly_event_counts[hour] = int(count)

        if request.dataset in (DatasetKind.PHONE, DatasetKind.ALL):
            logger.info("Building hourly phone-metrics dataset")
            hourly_call_counts = HourlyCallCountGenerator().generate(request)
            if hourly_event_counts is not None:
                event_series = pd.Series(hourly_event_counts, dtype="int64")
                hour_key = hourly_call_counts["hour_start"].dt.floor("h")
                hourly_call_counts["events_created"] = (
                    hour_key.map(event_series).fillna(0).astype(int)
                )
                logger.info(
                    "Added events_created column (total events: %d)",
                    hourly_call_counts["events_created"].sum(),
                )
            datasets["hourly_call_counts"] = hourly_call_counts
            logger.info(
                "Hourly phone metrics built: %d rows x %d columns",
                len(hourly_call_counts),
                len(hourly_call_counts.columns),
            )
            GENERATION_ROWS.labels(dataset="phone").inc(len(hourly_call_counts))

        logger.debug("Exporting datasets (%s)", effective_format.value)
        artifacts: dict[str, object] = dict(streamed_artifacts)

        # Handle database exports separately
        # Note: Database formats are explicit and should NOT auto-switch to Parquet
        db_formats = (
            OutputFormat.POSTGRESQL,
            OutputFormat.SQLSERVER,
            OutputFormat.MARIADB,
            OutputFormat.DUCKDB,
            OutputFormat.SQLITE,
        )
        if datasets and request.output_format in db_formats:
            db_results = export_to_database(datasets, request)
            artifacts["database"] = db_results
            logger.info("Database export complete: %s", db_results)
        elif datasets:
            # Build the manifest before export so Parquet files can embed it in
            # their footer metadata; the sidecar is written afterwards.
            manifest = None
            if (
                effective_format != OutputFormat.PANDAS
                and effective_format != OutputFormat.POLARS
            ):
                manifest = Manifest.from_request(request, datasets)

            artifacts = {
                **export_generated_data(
                    datasets=datasets,
                    output_format=effective_format,
                    output_dir=request.output_dir,
                    output_stem=request.output_stem,
                    parquet_metadata=manifest.to_kv_metadata() if manifest is not None else None,
                ),
                **streamed_artifacts,
            }

            # Generate and export data governance manifest
            if manifest is not None:
                manifest_path = export_manifest(
                    manifest=manifest,
                    output_dir=request.output_dir,
                    output_stem=request.output_stem,
                    output_format=effective_format,
                )
                artifacts["manifest"] = manifest_path
                logger.info("Wrote manifest: %s", manifest_path)

        return GenerationResult(
            incidents=incidents,
            hourly_call_counts=hourly_call_counts,
            exported_artifacts=artifacts,
        )
