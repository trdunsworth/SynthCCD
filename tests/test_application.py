from uuid import UUID

from synth911gen3.addresses import StaticAddressProvider
from synth911gen3.app import Synth911Application
from synth911gen3.config import DatasetKind, GenerationRequest, IdFormat, OutputFormat
from synth911gen3.domain import Address
from synth911gen3.generators.incidents import _DAY_ABBREVIATIONS
from synth911gen3.realism_config import RealismConfig


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
        "prefix_directional",
        "street_number",
        "street_name",
        "street_type",
        "postfix_directional",
        "street_address",
        "city",
        "state",
        "postal_code",
        "location",
        "call_start_time",
        "hour",
        "dow",
        "week_no",
        "incident_start_time",
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
    assert len(result.hourly_call_counts.columns) == 15


def test_application_guid_id_format_emits_unique_uuids() -> None:
    provider = StaticAddressProvider(
        [
            Address("101 N Main St", "Kansas City", "Missouri"),
            Address("204 E 12th St", "Kansas City", "Missouri"),
            Address("55 W 39th St", "Kansas City", "Missouri"),
        ]
    )
    request = GenerationRequest(
        rows=10,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        id_format=IdFormat.GUID,
        seed=99,
    )

    result = Synth911Application(address_provider=provider).generate(request)

    assert result.incidents is not None
    ids = result.incidents["id_number"].tolist()
    assert len(ids) == len(set(ids)) == 10
    for value in ids:
        parsed = UUID(str(value))
        assert parsed.version == 4


def test_application_guid_ids_reproducible_with_seed() -> None:
    provider = StaticAddressProvider(
        [
            Address("101 N Main St", "Kansas City", "Missouri"),
            Address("204 E 12th St", "Kansas City", "Missouri"),
        ]
    )
    request = GenerationRequest(
        rows=8,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        id_format=IdFormat.GUID,
        seed=7,
    )
    app = Synth911Application(address_provider=provider)

    first_result = app.generate(request)
    second_result = app.generate(request)
    assert first_result.incidents is not None
    assert second_result.incidents is not None
    first = first_result.incidents["id_number"].tolist()
    second = second_result.incidents["id_number"].tolist()

    assert first == second


def test_application_address_components_match_street_address() -> None:
    provider = StaticAddressProvider(
        [
            Address("101 N Main St", "Kansas City", "Missouri"),
            Address("204 E 12th St", "Kansas City", "Missouri"),
            Address("890 N Oak Trafficway NW", "Kansas City", "Missouri"),
        ]
    )
    request = GenerationRequest(
        rows=12,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        seed=2,
    )

    result = Synth911Application(address_provider=provider).generate(request)

    assert result.incidents is not None
    expected = {
        ("101", "Main", "St", "N", ""),
        ("204", "12th", "St", "E", ""),
        ("890", "Oak", "Trafficway", "N", "NW"),
    }
    produced = {
        (
            row["street_number"],
            row["street_name"],
            row["street_type"],
            row["prefix_directional"],
            row["postfix_directional"],
        )
        for _, row in result.incidents.iterrows()
    }
    assert produced == expected
    for _, row in result.incidents.iterrows():
        rebuilt = " ".join(
            token
            for token in (
                row["street_number"],
                row["prefix_directional"],
                row["street_name"],
                row["street_type"],
                row["postfix_directional"],
            )
            if token
        )
        assert rebuilt == row["street_address"]


def test_application_hour_dow_week_no_derive_from_call_start_time() -> None:
    provider = StaticAddressProvider(
        [
            Address("101 N Main St", "Kansas City", "Missouri"),
            Address("204 E 12th St", "Kansas City", "Missouri"),
        ]
    )
    request = GenerationRequest(
        rows=15,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        seed=8,
    )

    result = Synth911Application(address_provider=provider).generate(request)

    assert result.incidents is not None
    for _, row in result.incidents.iterrows():
        ts = row["call_start_time"]
        assert row["hour"] == ts.hour
        assert row["dow"] == _DAY_ABBREVIATIONS[ts.weekday()]
        assert row["week_no"] == ts.isocalendar().week


def test_application_integer_id_format_is_sequential() -> None:
    provider = StaticAddressProvider(
        [
            Address("101 N Main St", "Kansas City", "Missouri"),
            Address("204 E 12th St", "Kansas City", "Missouri"),
            Address("55 W 39th St", "Kansas City", "Missouri"),
        ]
    )
    request = GenerationRequest(
        rows=5,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        id_format=IdFormat.INTEGER,
        seed=99,
    )

    result = Synth911Application(address_provider=provider).generate(request)

    assert result.incidents is not None
    assert result.incidents["id_number"].tolist() == [1, 2, 3, 4, 5]


def test_application_incident_start_time_within_three_seconds_of_call_start() -> None:
    provider = StaticAddressProvider(
        [
            Address("101 N Main St", "Kansas City", "Missouri"),
            Address("204 E 12th St", "Kansas City", "Missouri"),
        ]
    )
    request = GenerationRequest(
        rows=40,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        seed=5,
    )

    result = Synth911Application(address_provider=provider).generate(request)

    assert result.incidents is not None
    offsets = (
        result.incidents["incident_start_time"] - result.incidents["call_start_time"]
    ).dt.total_seconds()
    assert offsets.between(0, 3).all()
    assert (
        result.incidents["pre_cad_offset_seconds"].tolist() == offsets.astype(int).tolist()
    )


def test_application_incident_start_time_on_or_before_answer_when_pickup_at_least_three_seconds() -> None:
    provider = StaticAddressProvider(
        [
            Address("101 N Main St", "Kansas City", "Missouri"),
            Address("204 E 12th St", "Kansas City", "Missouri"),
        ]
    )
    request = GenerationRequest(
        rows=25,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        seed=11,
    )

    result = Synth911Application(address_provider=provider).generate(request)

    assert result.incidents is not None
    rows = result.incidents[result.incidents["pickup_delay_seconds"] >= 3]
    deltas = (
        rows["time_phone_pickup"] - rows["incident_start_time"]
    ).dt.total_seconds()
    assert (deltas >= 0).all()


def test_application_problem_nature_matches_selected_priority() -> None:
    provider = StaticAddressProvider(
        [
            Address("101 N Main St", "Kansas City", "Missouri"),
            Address("204 E 12th St", "Kansas City", "Missouri"),
        ]
    )
    request = GenerationRequest(
        rows=500,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        seed=21,
    )
    config = RealismConfig()

    result = Synth911Application(address_provider=provider).generate(request)

    assert result.incidents is not None
    for _, row in result.incidents.iterrows():
        agency = row["agency"]
        priority = row["priority"]
        pool = config.problem_profiles[agency][priority]
        names = {name for name, _ in pool}
        assert row["problem_nature"] in names, (
            f"{row['problem_nature']} not valid for {agency} priority {priority}"
        )


def test_application_high_priority_dispatched_during_call() -> None:
    provider = StaticAddressProvider(
        [
            Address("101 N Main St", "Kansas City", "Missouri"),
            Address("204 E 12th St", "Kansas City", "Missouri"),
        ]
    )
    request = GenerationRequest(
        rows=1500,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        seed=33,
    )

    result = Synth911Application(address_provider=provider).generate(request)

    assert result.incidents is not None
    df = result.incidents
    during_call = df[df["priority"] == 1]
    assigned_before_disconnect = (
        during_call["time_first_unit_assigned"] < during_call["time_phone_disconnect"]
    )
    assert assigned_before_disconnect.any(), (
        "No priority-1 incident was dispatched before the caller hung up"
    )
    for _, row in df.iterrows():
        assert row["time_first_unit_assigned"] >= row["time_phone_pickup"]


def test_application_low_priority_dispatch_deferred_after_call() -> None:
    provider = StaticAddressProvider(
        [
            Address("101 N Main St", "Kansas City", "Missouri"),
            Address("204 E 12th St", "Kansas City", "Missouri"),
        ]
    )
    request = GenerationRequest(
        rows=1500,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        seed=44,
    )

    result = Synth911Application(address_provider=provider).generate(request)

    assert result.incidents is not None
    df = result.incidents
    deferred = df[df["priority"] == 5]
    assert len(deferred) > 0
    assigned_after_disconnect = (
        deferred["time_first_unit_assigned"] >= deferred["time_phone_disconnect"]
    )
    assert assigned_after_disconnect.all(), (
        "Priority-5 incidents should be dispatched after the call ends"
    )


def test_application_phone_metrics_config_changes_abandonment() -> None:
    from synth911gen3.generators.phone_metrics import HourlyCallCountGenerator

    low = GenerationRequest(
        rows=100_000,
        dataset=DatasetKind.PHONE,
        output_format=OutputFormat.PANDAS,
        seed=60,
    )
    realism = RealismConfig()
    realism.phone_metrics["nine_one_one_abandonment_rate"] = 0.5
    realism.phone_metrics["night_abandonment_increment"] = 0.0
    high = GenerationRequest(
        rows=100_000,
        dataset=DatasetKind.PHONE,
        output_format=OutputFormat.PANDAS,
        seed=60,
        realism_config=realism,
    )

    gen = HourlyCallCountGenerator()
    low_df = gen.generate(low)
    high_df = gen.generate(high)

    low_rate = low_df["nine_one_one_calls_abandoned"].sum() / low_df[
        "nine_one_one_calls_received"
    ].sum()
    high_rate = high_df["nine_one_one_calls_abandoned"].sum() / high_df[
        "nine_one_one_calls_received"
    ].sum()
    assert high_rate > low_rate * 2, (high_rate, low_rate)
