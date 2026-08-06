from __future__ import annotations

from collections.abc import Callable

from .addresses import AddressProvider, OpenStreetMapAddressProvider
from .config import DatasetKind, GenerationRequest
from .domain import GenerationResult
from .exporters import export_generated_data
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

        if request.dataset in (DatasetKind.INCIDENTS, DatasetKind.ALL):
            logger.info("Building incident dataset (%d rows)", request.rows)
            incidents = IncidentGenerator(self._address_provider).generate(
                request,
                on_progress=(
                    (lambda done, total: on_progress("incidents", done, total))
                    if on_progress is not None
                    else None
                ),
            )
            datasets["incidents"] = incidents
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
        artifacts = export_generated_data(
            datasets=datasets,
            output_format=request.output_format,
            output_dir=request.output_dir,
            output_stem=request.output_stem,
        )
        return GenerationResult(
            incidents=incidents,
            hourly_call_counts=hourly_call_counts,
            exported_artifacts=artifacts,
        )
