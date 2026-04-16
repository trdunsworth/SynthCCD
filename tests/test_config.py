from synth911gen3.config import DatasetKind, GenerationRequest, OutputFormat


def test_generation_request_defaults() -> None:
    request = GenerationRequest()

    assert request.rows == 10_000
    assert request.area_query == "Kansas City, MO"
    assert request.output_format is OutputFormat.CSV
    assert request.dataset is DatasetKind.ALL
    assert request.output_stem == "synthetic_911"
