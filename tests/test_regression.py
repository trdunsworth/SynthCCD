"""Regression suite: generated statistics vs the committed realism baseline.

The generators are deterministic for a given seed, so the key statistics of a
reference run (agency/priority/reception/disposition fractions, per-cell
timing means, hourly call-shape, phone-metrics rates) can be frozen in
``tests/regression_baseline.json``. If the realism defaults drift -- weights,
time profiles, phone metrics -- the freshly generated signature no longer
matches and these tests fail, pointing the developer at
``scripts/update_regression_baseline.py`` (for intentional changes) or at the
regression itself.

The baseline was produced from the current package defaults; see REALISMGUIDE
for the refresh workflow.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from synth911gen3.constants import DATA_SCHEMA_VERSION
from synth911gen3.manifest import _hash_realism_config
from synth911gen3.realism_config import RealismConfig
from synth911gen3.regression import (
    RegressionTolerances,
    build_baseline,
    build_signature,
    compare,
    load_baseline,
)

_BASELINE_PATH = Path(__file__).parent / "regression_baseline.json"


def _baseline() -> dict:
    return load_baseline(_BASELINE_PATH)


@pytest.fixture(scope="session")
def generated() -> tuple[dict[str, float], dict[str, float]]:
    """Deterministic signatures from the fixed reference seed, generated once.

    Generation is deterministic, so sharing one run across the session is
    safe and keeps the suite fast.
    """
    return build_signature()


# ---------------------------------------------------------------------------
# Baseline fixture integrity
# ---------------------------------------------------------------------------


def test_baseline_file_exists_and_is_current_schema() -> None:
    baseline = _baseline()
    assert baseline["meta"]["schema_version"] == DATA_SCHEMA_VERSION
    assert baseline["meta"]["realism_config_hash"] == _hash_realism_config(
        RealismConfig()
    ), "baseline realism hash changed; run scripts/update_regression_baseline.py"


def test_baseline_incident_signature_has_expected_sections() -> None:
    signature = _baseline()["incidents"]
    agency_keys = sorted(k for k in signature if k.startswith("agency."))
    assert agency_keys == ["agency.EMS", "agency.FIRE", "agency.LAW"]
    assert abs(sum(signature[k] for k in agency_keys) - 1.0) < 1e-6

    # All three agencies x five priorities produce timing cells.
    timing_keys = [k for k in signature if k.startswith("timing.")]
    assert len(timing_keys) == 3 * 5 * 7  # agencies x priorities x timing fields

    hour_keys = [k for k in signature if k.startswith("hour.")]
    assert len(hour_keys) == 24
    assert abs(sum(signature[k] for k in hour_keys) - 1.0) < 1e-6


def test_baseline_phone_signature_has_expected_sections() -> None:
    signature = _baseline()["phone"]
    assert set(signature) == {
        "phone.received_911_per_hour",
        "phone.received_non_emergency_per_hour",
        "phone.outbound_per_hour",
        "phone.911_abandonment_rate",
        "phone.non_emergency_abandonment_rate",
        "phone.911_answered_10s_mean",
        "phone.911_answered_40s_mean",
    }
    assert 0.0 <= signature["phone.911_abandonment_rate"] <= 0.5
    assert 0.0 <= signature["phone.non_emergency_abandonment_rate"] <= 0.5


# ---------------------------------------------------------------------------
# The regression gate: fresh generation must match the committed baseline
# ---------------------------------------------------------------------------


def test_incident_signature_matches_baseline(generated) -> None:
    signature, _ = generated
    issues = compare(signature, _baseline()["incidents"])
    assert issues == [], "\n".join(issues)


def test_phone_signature_matches_baseline(generated) -> None:
    _, signature = generated
    issues = compare(signature, _baseline()["phone"])
    assert issues == [], "\n".join(issues)


def test_baseline_is_deterministic_for_same_seed() -> None:
    first, first_phone = build_signature()
    second, second_phone = build_signature()
    assert first == second
    assert first_phone == second_phone


# ---------------------------------------------------------------------------
# Signature computation units
# ---------------------------------------------------------------------------


def test_incident_signature_counts_fractions_across_categories(generated) -> None:
    """Each fraction family sums to one and timing cells are per agency/priority."""
    signature = generated[0]

    for prefix in ("agency", "reception"):
        family = [v for k, v in signature.items() if k.startswith(f"{prefix}.")]
        assert abs(sum(family) - 1.0) < 1e-6, prefix

    agencies = [k for k in signature if k.startswith("agency.")]
    for agency_key in agencies:
        agency = agency_key.split(".")[1]
        dispositions = [v for k, v in signature.items() if k.startswith(f"disposition.{agency}.")]
        assert abs(sum(dispositions) - 1.0) < 1e-6, agency
        problems = [v for k, v in signature.items() if k.startswith(f"problem.{agency}.")]
        assert abs(sum(problems) - 1.0) < 1e-6, agency

    # Timing means must exist for every (agency, priority) cell and stay positive.
    timing = {k: v for k, v in signature.items() if k.startswith("timing.")}
    assert timing
    assert all(v > 0 for v in timing.values())


def test_phone_signature_is_small_and_typed(generated) -> None:
    _, signature = generated
    assert isinstance(signature, dict)
    for value in signature.values():
        assert isinstance(value, float)


# ---------------------------------------------------------------------------
# Comparator behavior
# ---------------------------------------------------------------------------


def test_compare_returns_empty_for_identical_signatures(generated) -> None:
    signature, _ = generated
    assert compare(signature, signature) == []


def test_compare_detects_fraction_drift() -> None:
    baseline = {"agency.LAW": 0.52, "reception.E-911": 0.33}
    current = {"agency.LAW": 0.60, "reception.E-911": 0.33}
    issues = compare(current, baseline)
    assert len(issues) == 1
    assert "agency.LAW" in issues[0]
    assert "baseline 0.52" in issues[0]
    assert "current 0.6" in issues[0]


def test_compare_detects_timing_mean_drift() -> None:
    baseline = {"timing.LAW.1.travel_seconds": 220.0}
    current = {"timing.LAW.1.travel_seconds": 300.0}
    issues = compare(current, baseline)
    assert len(issues) == 1
    assert "timing.LAW.1.travel_seconds" in issues[0]


def test_compare_tolerates_means_within_relative_bound() -> None:
    baseline = {"timing.LAW.1.travel_seconds": 220.0}
    current = {"timing.LAW.1.travel_seconds": 235.0}  # 6.8% < 10%
    assert compare(current, baseline) == []


def test_compare_uses_absolute_floor_for_small_means() -> None:
    # 4s dispatch mean with a 3.9s current value: 2.5% relative, well under
    # 10%, but the absolute floor of 2s is not exceeded either -- no failure.
    baseline = {"timing.EMS.1.dispatch_queue_seconds": 4.0}
    current = {"timing.EMS.1.dispatch_queue_seconds": 4.1}
    assert compare(current, baseline) == []

    # A shift of 2.5s on a 4s baseline exceeds the 2s floor -> flagged.
    current_big = {"timing.EMS.1.dispatch_queue_seconds": 6.5}
    issues = compare(current_big, baseline)
    assert len(issues) == 1


def test_compare_detects_phone_rate_drift() -> None:
    baseline = {"phone.911_abandonment_rate": 0.02}
    current = {"phone.911_abandonment_rate": 0.05}
    issues = compare(current, baseline)
    assert len(issues) == 1
    assert "phone.911_abandonment_rate" in issues[0]


def test_compare_reports_missing_and_new_keys() -> None:
    issues = compare({"agency.LAW": 0.52}, {"agency.LAW": 0.52, "agency.FIRE": 0.20})
    assert len(issues) == 1
    assert "agency.FIRE" in issues[0]
    assert "not in current" in issues[0]

    issues = compare({"agency.LAW": 0.52, "agency.EMS": 0.28}, {"agency.LAW": 0.52})
    assert len(issues) == 1
    assert "agency.EMS" in issues[0]
    assert "not in baseline" in issues[0]


def test_compare_respects_custom_tolerances() -> None:
    tight = RegressionTolerances(fraction_abs=0.01)
    baseline = {"agency.LAW": 0.52}
    current = {"agency.LAW": 0.53}
    assert compare(current, baseline, tight) != []
    assert compare(current, baseline, RegressionTolerances(fraction_abs=0.02)) == []


def test_compare_is_deterministic_order() -> None:
    baseline = {"agency.LAW": 0.52, "agency.FIRE": 0.20, "agency.EMS": 0.28}
    current = {k: v + 0.1 for k, v in baseline.items()}
    issues = compare(current, baseline)
    assert issues == sorted(issues)


# ---------------------------------------------------------------------------
# Baseline document round-trip
# ---------------------------------------------------------------------------


def test_build_baseline_roundtrips_through_json(tmp_path) -> None:
    from synth911gen3.regression import save_baseline

    baseline = build_baseline()
    path = tmp_path / "baseline.json"
    save_baseline(baseline, path)
    restored = load_baseline(path)

    assert restored["meta"]["schema_version"] == baseline["meta"]["schema_version"]
    assert restored["incidents"] == baseline["incidents"]
    assert restored["phone"] == baseline["phone"]


def test_baseline_document_is_serializable_json(tmp_path) -> None:
    from synth911gen3.regression import save_baseline

    baseline = build_baseline()
    path = tmp_path / "baseline.json"
    save_baseline(baseline, path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert set(raw) == {"meta", "incidents", "phone"}


def test_compare_ignores_float_noise_from_serialization() -> None:
    """Values round-tripped through JSON must not trip the comparator."""
    baseline = _baseline()
    for section in ("incidents", "phone"):
        current = copy.deepcopy(baseline[section])
        assert compare(current, baseline[section]) == []
