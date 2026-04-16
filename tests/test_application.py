from synth911gen3.addresses import StaticAddressProvider
from synth911gen3.app import Synth911Application
from synth911gen3.config import DatasetKind, GenerationRequest, OutputFormat
from synth911gen3.domain import Address


def test_application_generates_incidents_and_hourly_counts() -> None:
    provider = StaticAddressProvider(
        [
            Address("101 N Main St", "Kansas City", "Missouri"),
            Address("204 E 12th St", "Kansas City", "Missouri"),
            Address("55 W 39th St", "Kansas City", "Missouri"),
            Address("777 S Broadway Blvd", "Kansas City", "Missouri"),
            Address("890 N Oak Trafficway", "Kansas City", "Missouri"),
        ]
    )
    request = GenerationRequest(
        rows=25,
        dataset=DatasetKind.ALL,
        output_format=OutputFormat.PANDAS,
        seed=1234,
    )

    result = Synth911Application(address_provider=provider).generate(request)

    assert result.incidents is not None
    assert result.hourly_call_counts is not None
    assert len(result.incidents) == 25
    assert {
        "id_number",
        "internal_reference_number",
        "agency",
        "problem_nature",
        "priority",
        "location",
        "call_start_time",
        "time_phone_pickup",
        "time_call_enters_queue",
        "time_first_unit_assigned",
        "time_unit_enroute",
        "time_unit_arrived",
        "time_last_unit_cleared",
        "time_call_closed",
        "calltaker",
        "dispatcher",
        "method_of_call_reception",
        "call_disposition",
        "total_elapsed_seconds",
    }.issubset(result.incidents.columns)
    assert len(result.hourly_call_counts.columns) == 7
