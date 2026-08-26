"""Round-trip validation for the bundled CLI samples in ``config/samples/``.

Every sample must load through the real params pipeline
(:func:`load_params_file` + :func:`build_request_from_params`) into a valid
:class:`~synth911gen3.config.GenerationRequest`, so the bundled examples can
never drift from the schema the CLI accepts.
"""

from pathlib import Path

import pytest

from synth911gen3.config import OutputFormat
from synth911gen3.params import build_request_from_params, load_params_file
from synth911gen3.realism_config import RealismConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = REPO_ROOT / "config" / "samples"
EXPECTED_FILES = {
    "small_centre.json",
    "midsize_centre.yaml",
    "large_centre.toml",
    "realism_disciplines.yaml",  # a realism config, validated via RealismConfig
}
# Params samples only: the realism companion is exercised separately below.
PARAMS_SAMPLES = [
    SAMPLES_DIR / "small_centre.json",
    SAMPLES_DIR / "midsize_centre.yaml",
    SAMPLES_DIR / "large_centre.toml",
]


def test_samples_directory_contains_expected_files() -> None:
    """Guard against silent sample loss (a missing file would skip quietly)."""
    names = {path.name for path in SAMPLES_DIR.iterdir()}
    assert EXPECTED_FILES <= names


@pytest.mark.parametrize("path", PARAMS_SAMPLES, ids=lambda path: path.name)
def test_sample_loads_into_valid_request(path: Path) -> None:
    """Every params sample round-trips into a validated GenerationRequest."""
    request = build_request_from_params(load_params_file(path), {})
    request.validate()
    assert request.rows >= 1


def test_small_centre_sample_stays_combined() -> None:
    """Small-centre persona: modest pools, csv output, no realism file."""
    request = build_request_from_params(
        load_params_file(SAMPLES_DIR / "small_centre.json"), {}
    )
    assert request.area_query == "Manhattan, KS"
    assert request.output_format is OutputFormat.CSV
    assert request.calltaker_pool_size == 6
    assert request.dispatcher_pool_size == 5
    # 5 dispatchers over the default 4 shifts is at most 2 per shift, below
    # the split threshold: a small centre keeps one combined console.
    assert request.realism_config_path is None
    assert request.realism_config is None


def test_midsize_sample_references_disciplines_realism_file() -> None:
    """Mid-size persona references the companion realism YAML and stays valid."""
    request = build_request_from_params(
        load_params_file(SAMPLES_DIR / "midsize_centre.yaml"), {}
    )
    assert request.realism_config_path == Path("config/samples/realism_disciplines.yaml")
    assert request.realism_config_path is not None

    realism = RealismConfig.from_yaml(request.realism_config_path)
    assert realism.dispatcher_disciplines["mode"] == "two_way"
    assert realism.dispatcher_disciplines["min_dispatchers_for_split"] == 4
    # Alexandria staffing: every shift carries 4 calltakers + 4 dispatchers,
    # which two-way mode splits 2 LAW + 2 FIRE/EMS.
    shifts = realism.shift_config.shifts
    assert shifts
    assert all(shift.calltakers == 4 and shift.dispatchers == 4 for shift in shifts)


def test_large_sample_demonstrates_population_sqlite_and_budget() -> None:
    """Large persona: sqlite target, population-based volume, chunk budget."""
    request = build_request_from_params(
        load_params_file(SAMPLES_DIR / "large_centre.toml"), {}
    )
    assert request.output_format is OutputFormat.SQLITE
    assert request.population == 2_300_000
    assert request.max_memory_bytes == 1_073_741_824
    assert request.dispatcher_pool_size == 40
    assert request.id_format.value == "guid"
