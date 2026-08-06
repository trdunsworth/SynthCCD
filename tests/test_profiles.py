from synth911gen3.constants import (
    AGENCY_WEIGHTS,
    CALL_RECEPTION_WEIGHTS,
    DISPOSITION_PROFILES,
    PHONE_METRICS,
    PROBLEM_PROFILES,
)
from synth911gen3.generators.incidents import _weighted_choice_from_pairs
from synth911gen3.realism_config import RealismConfig

_PRIORITIES = (1, 2, 3, 4, 5)


def test_problem_profiles_have_enough_variety() -> None:
    for agency in AGENCY_WEIGHTS:
        for priority in _PRIORITIES:
            assert len(PROBLEM_PROFILES[agency][priority]) >= 3, (agency, priority)


def test_problem_profile_weights_sum_to_one() -> None:
    for agency, priorities in PROBLEM_PROFILES.items():
        for priority, profiles in priorities.items():
            total = sum(weight for _, weight in profiles)
            assert abs(total - 1.0) < 1e-9, f"{agency} priority {priority} weights sum to {total}"


def test_problem_profile_weights_are_positive() -> None:
    for agency, priorities in PROBLEM_PROFILES.items():
        for priority, profiles in priorities.items():
            for name, weight in profiles:
                assert weight > 0, f"{agency}/{priority} profile {name} has non-positive weight"
                assert name.strip(), f"{agency}/{priority} has an empty problem name"


def test_problem_profile_names_are_unique_per_agency() -> None:
    for agency, priorities in PROBLEM_PROFILES.items():
        for priority, profiles in priorities.items():
            names = [name for name, _ in profiles]
            assert len(names) == len(set(names)), f"{agency}/{priority} contains duplicate names"


def test_problem_profiles_load_into_realism_config() -> None:
    config = RealismConfig()
    for agency in AGENCY_WEIGHTS:
        assert agency in config.problem_profiles
        for priority in _PRIORITIES:
            total = sum(w for _, w in config.problem_profiles[agency][priority])
            assert abs(total - 1.0) < 1e-9, (agency, priority)


def test_weighted_choice_from_pairs_returns_valid_problem() -> None:
    import numpy as np

    rng = np.random.default_rng(seed=7)
    for agency in AGENCY_WEIGHTS:
        for priority in _PRIORITIES:
            profiles = PROBLEM_PROFILES[agency][priority]
            names = {name for name, _ in profiles}
            for _ in range(100):
                problem = _weighted_choice_from_pairs(rng, profiles)
                assert problem in names


def test_call_reception_uses_real_cad_vocabulary() -> None:
    assert set(CALL_RECEPTION_WEIGHTS) == {
        "E-911",
        "Phone",
        "OFFICER",
        "Radio",
        "C2C",
        "NOT CAPTURED",
        "Text",
        "CAD2CAD",
    }


def test_call_reception_weights_sum_to_one() -> None:
    total = sum(CALL_RECEPTION_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9


def test_disposition_profiles_use_code_label_pairs() -> None:
    for agency, profiles in DISPOSITION_PROFILES.items():
        for label, weight in profiles:
            assert weight > 0
            assert label == "UNDEFINED" or "-" in label, (
                f"{agency} disposition '{label}' is not a code+label pair"
            )
            if "-" in label:
                code = label.split("-")[0]
                assert code.isalnum(), f"{agency} disposition '{label}' has invalid code '{code}'"


def test_disposition_profile_weights_sum_to_one() -> None:
    for agency, profiles in DISPOSITION_PROFILES.items():
        total = sum(weight for _, weight in profiles)
        assert abs(total - 1.0) < 1e-9, f"{agency} weights sum to {total}"


def test_phone_metrics_defaults_load_into_realism_config() -> None:
    config = RealismConfig()
    assert config.phone_metrics == PHONE_METRICS
    assert config.phone_metrics["max_abandonment_rate"] <= 1.0
    assert config.phone_metrics["min_hourly_volume"] >= 0.0


def test_animal_control_disposition_has_matching_problems() -> None:
    animal_terms = ("animal", "bite")
    for agency, dispositions in DISPOSITION_PROFILES.items():
        if not any("ACOR" in label for label, _ in dispositions):
            continue
        problems = {
            name
            for pool in PROBLEM_PROFILES[agency].values()
            for name, _ in pool
        }
        assert any(term in name.lower() for name in problems for term in animal_terms), (
            f"{agency} has ACOR disposition but no animal-related problems"
        )