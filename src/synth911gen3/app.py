from __future__ import annotations

from .addresses import AddressProvider, OpenStreetMapAddressProvider
from .config import DatasetKind, GenerationRequest
from .domain import GenerationResult
from .exporters import export_generated_data
from .generators import HourlyCallCountGenerator, IncidentGenerator


class Synth911Application:
    def __init__(self, address_provider: AddressProvider | None = None) -> None:
        self._address_provider = address_provider or OpenStreetMapAddressProvider()

    def generate(self, request: GenerationRequest) -> GenerationResult:
        request.validate()

        datasets = {}
        incidents = None
        hourly_call_counts = None

        if request.dataset in (DatasetKind.INCIDENTS, DatasetKind.ALL):
            incidents = IncidentGenerator(self._address_provider).generate(request)
            datasets["incidents"] = incidents

        if request.dataset in (DatasetKind.PHONE, DatasetKind.ALL):
            hourly_call_counts = HourlyCallCountGenerator().generate(request)
            datasets["hourly_call_counts"] = hourly_call_counts

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
