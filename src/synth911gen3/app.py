from __future__ import annotations

from collections.abc import Callable
from itertools import chain

from .addresses import AddressProvider, OpenStreetMapAddressProvider
from .config import DatasetKind, GenerationRequest, OutputFormat
from .domain import GenerationResult
from .exporters import export_chunked_generator, export_generated_data
from .generators import HourlyCallCountGenerator, IncidentGenerator
from .logging_conf import get_logger

logger = get_logger("app")


class Synth911Application:
    def __init__(self, address_provider: AddressProvider | None = None) -> None:
        self._address_provider = address_provider or OpenStreetMapAddressProvider()

    def generate(
        self,
        request: GenerationRequest,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> GenerationResult:
        request.validate()

        datasets = {}
        incidents = None
        hourly_call_counts = None
        streamed_artifacts: dict[str, object] = {}

        if request.dataset in (DatasetKind.INCIDENTS, DatasetKind.ALL):
            logger.info("Building incident dataset (%d rows)", request.rows)
            incident_generator = IncidentGenerator(self._address_provider)
            incident_progress = (
                (lambda done, total: on_progress("incidents", done, total))
                if on_progress is not None
                else None
            )
            if request.output_format in (OutputFormat.CSV, OutputFormat.PARQUET):
                chunk_frames = incident_generator.generate_chunks(
                    request, on_progress=incident_progress
                )
                first_chunk = next(chunk_frames)
                if len(first_chunk) < request.rows:
                    path = export_chunked_generator(
                        chain([first_chunk], chunk_frames),
                        output_format=request.output_format,
                        output_dir=request.output_dir,
                        output_stem=request.output_stem,
                        dataset_name="incidents",
                    )
                    streamed_artifacts["incidents"] = path
                    logger.info(
                        "Incidents streamed to %s in chunks (budget: %s bytes)",
                        path,
                        request.max_memory_bytes if request.max_memory_bytes is not None else "default",
                    )
                else:
                    incidents = first_chunk
                    datasets["incidents"] = incidents
            else:
                incidents = incident_generator.generate(request, on_progress=incident_progress)
                datasets["incidents"] = incidents
            if incidents is not None:
                logger.info("Incidents built: %d rows x %d columns", len(incidents), len(incidents.columns))

        if request.dataset in (DatasetKind.PHONE, DatasetKind.ALL):
            logger.info("Building hourly phone-metrics dataset")
            hourly_call_counts = HourlyCallCountGenerator().generate(request)
            datasets["hourly_call_counts"] = hourly_call_counts
            logger.info(
                "Hourly phone metrics built: %d rows x %d columns",
                len(hourly_call_counts),
                len(hourly_call_counts.columns),
            )

        logger.debug("Exporting datasets (%s)", request.output_format.value)
        artifacts: dict[str, object] = dict(streamed_artifacts)
        if datasets:
            artifacts = {**export_generated_data(
                datasets=datasets,
                output_format=request.output_format,
                output_dir=request.output_dir,
                output_stem=request.output_stem,
            ), **streamed_artifacts}
        return GenerationResult(
            incidents=incidents,
            hourly_call_counts=hourly_call_counts,
            exported_artifacts=artifacts,
        )
