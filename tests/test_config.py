from pathlib import Path

import pytest

from synth911gen3.config import DatasetKind, GenerationRequest, OutputFormat
from synth911gen3.exceptions import ValidationError


def test_generation_request_defaults() -> None:
    request = GenerationRequest()

    assert request.rows == 10_000
    assert request.area_query == "Kansas City, MO"
    assert request.output_format is OutputFormat.CSV
    assert request.dataset is DatasetKind.ALL
    assert request.output_stem == "synthetic_911"


@pytest.mark.parametrize("stem", [".", "..", "a/b", "a\\b", "CON", "con.csv", "NUL", "COM1", "aux", "has\x00null"])
def test_output_stem_rejects_unsafe_values(stem: str) -> None:
    with pytest.raises(ValidationError):
        GenerationRequest(output_stem=stem).validate()


@pytest.mark.parametrize("output_dir", [Path("../outside"), Path("nested/../../escape"), Path("x\x00y")])
def test_output_dir_rejects_unsafe_values(output_dir: Path) -> None:
    with pytest.raises(ValidationError):
        GenerationRequest(output_dir=output_dir).validate()


def test_output_dir_accepts_normal_paths(tmp_path: Path) -> None:
    request = GenerationRequest(output_dir=tmp_path / "exports", output_stem="kc_911")
    request.validate()
    assert request.output_dir == tmp_path / "exports"
