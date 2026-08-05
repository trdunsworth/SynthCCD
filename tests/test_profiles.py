from synth911gen3.constants import AGENCY_WEIGHTS, PROBLEM_PROFILES
from synth911gen3.generators.incidents import _weighted_choice_from_pairs
from synth911gen3.realism_config import RealismConfig


def test_problem_profiles_have_enough_variety() -> None:
    assert len(PROBLEM_PROFILES["LAW"]) >= 20
    assert len(PROBLEM_PROFILES["FIRE"]) >= 15
    assert len(PROBLEM_PROFILES["EMS"]) >= 15


def test_problem_profile_weights_sum_to_one() -> None:
    for agency, profiles in PROBLEM_PROFILES.items():
        total = sum(weight for _, weight in profiles)
        assert abs(total - 1.0) < 1e-9, f"{agency} weights sum to {total}"


def test_problem_profile_weights_are_positive() -> None:
    for agency, profiles in PROBLEM_PROFILES.items():
        for name, weight in profiles:
            assert weight > 0, f"{agency} profile {name} has non-positive weight"
            assert name.strip(), f"{agency} has an empty problem name"


def test_problem_profile_names_are_unique_per_agency() -> None:
    for agency, profiles in PROBLEM_PROFILES.items():
        names = [name for name, _ in profiles]
        assert len(names) == len(set(names)), f"{agency} contains duplicate names"


def test_problem_profiles_load_into_realism_config() -> None:
    config = RealismConfig()
    for agency in AGENCY_WEIGHTS:
        assert agency in config.problem_profiles
        total = sum(w for _, w in config.problem_profiles[agency])
        assert abs(total - 1.0) < 1e-9


def test_weighted_choice_from_pairs_returns_valid_problem() -> None:
    import numpy as np

    rng = np.random.default_rng(seed=7)
    for agency, profiles in PROBLEM_PROFILES.items():
        for _ in range(100):
            problem = _weighted_choice_from_pairs(rng, profiles)
            names = {name for name, _ in profiles}
            assert problem in names
