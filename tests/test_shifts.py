from datetime import datetime

import numpy as np
import pytest

from synth911gen3.addresses import StaticAddressProvider
from synth911gen3.app import Synth911Application
from synth911gen3.config import DatasetKind, GenerationRequest, OutputFormat
from synth911gen3.domain import Address
from synth911gen3.exceptions import ValidationError
from synth911gen3.generators.incidents import _distribute, _resolve_shift_staffing, _zipf_pick
from synth911gen3.realism_config import RealismConfig
from synth911gen3.shifts import (
    DEFAULT_SHIFT_PRESET,
    SHIFT_PRESETS,
    Shift,
    ShiftConfig,
    apply_shift_preset,
    get_default_shift_config,
    get_preset,
)

# 1970-01-05 is a Monday, used to anchor the 14-day rotation cycle.
_MON = datetime(1970, 1, 5, 8, 0)
_TUE = datetime(1970, 1, 6, 8, 0)
_THU = datetime(1970, 1, 8, 8, 0)
_FRI = datetime(1970, 1, 9, 8, 0)
_MON2 = datetime(1970, 1, 12, 8, 0)
_NIGHT = datetime(1970, 1, 5, 22, 0)
_AM = datetime(1970, 1, 6, 2, 0)


def _one() -> StaticAddressProvider:
    return StaticAddressProvider([Address("100 E 12th St", "Kansas City", "Missouri")])


# ---------------------------------------------------------------------------
# Presets and the default schedule
# ---------------------------------------------------------------------------


def test_default_shift_preset_is_4shift_14day() -> None:
    assert DEFAULT_SHIFT_PRESET == "2x12h-4shift-14day"
    assert get_default_shift_config().name == "2x12h-4shift-14day"


def test_default_rotation_matches_spec_pattern() -> None:
    config = get_default_shift_config()
    assert config.rotation == [1, 1, 2, 2, 1, 1, 1, 2, 2, 1, 1, 2, 2, 2]


def test_default_rotation_has_14_days_balanced_groups() -> None:
    rotation = get_default_shift_config().rotation
    assert len(rotation) == 14
    assert rotation.count(1) == 7
    assert rotation.count(2) == 7


def test_presets_are_valid_and_cover_full_day() -> None:
    for name in SHIFT_PRESETS:
        config = get_preset(name)
        config.validate()
        assert len(config.shifts) >= 1


def test_get_preset_unknown_raises() -> None:
    with pytest.raises(ValidationError):
        get_preset("bogus")


def test_apply_shift_preset_none_returns_input() -> None:
    config = ShiftConfig(rotation=[1], shifts=[Shift("A", rotation=1)])
    assert apply_shift_preset(config, None) is config


def test_apply_shift_preset_returns_preset() -> None:
    result = apply_shift_preset(ShiftConfig(), "3x8h-3shift")
    assert result.name == "3x8h-3shift"
    assert len(result.shifts) == 3


# ---------------------------------------------------------------------------
# Active shift resolution
# ---------------------------------------------------------------------------


def test_default_active_shift_follows_rotation() -> None:
    config = get_default_shift_config()
    # Day 0 (Mon) and day 1 (Tue) are group 1 -> day A / night C.
    assert config.active_shift(_MON).name == "A"
    assert config.active_shift(_NIGHT).name == "C"
    # Day 3 (Thu) is group 2 -> day B.
    assert config.active_shift(_THU).name == "B"


def test_default_active_shift_cycles_into_week_two() -> None:
    config = get_default_shift_config()
    # Day 7 (Mon 1970-01-12) -> rotation[7] == 2 -> day B.
    assert config.active_shift(_MON2).name == "B"


def test_overnight_shift_covers_after_midnight() -> None:
    config = get_default_shift_config()
    assert config.active_shift(_AM).name == "C"


def test_shift_covers_respects_window() -> None:
    day = Shift("A", start_hour=6, end_hour=18)
    assert day.covers(_MON) is True
    assert day.covers(datetime(1970, 1, 5, 4, 0)) is False
    assert day.covers(datetime(1970, 1, 5, 18, 0)) is False


def test_overnight_shift_flags_and_covers_window() -> None:
    night = Shift("C", start_hour=18, end_hour=6)
    assert night.is_overnight is True
    assert night.covers(datetime(1970, 1, 5, 22, 0)) is True
    assert night.covers(datetime(1970, 1, 6, 2, 0)) is True
    assert night.covers(datetime(1970, 1, 5, 12, 0)) is False


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_shift_config_validate_rejects_duplicate_names() -> None:
    config = ShiftConfig(rotation=[1], shifts=[Shift("A", rotation=1), Shift("A", rotation=1)])
    with pytest.raises(ValidationError):
        config.validate()


def test_shift_config_validate_rejects_coverage_gap() -> None:
    config = ShiftConfig(rotation=[1], shifts=[Shift("A", start_hour=6, end_hour=18, rotation=1)])
    with pytest.raises(ValidationError):
        config.validate()


def test_shift_config_validate_rejects_missing_group() -> None:
    config = ShiftConfig(
        rotation=[1, 2],
        shifts=[Shift("A", rotation=1), Shift("B", start_hour=18, end_hour=6, rotation=1)],
    )
    with pytest.raises(ValidationError):
        config.validate()


def test_shift_config_validate_rejects_negative_staffing() -> None:
    config = ShiftConfig(rotation=[1], shifts=[Shift("A", rotation=1, calltakers=-1)])
    with pytest.raises(ValidationError):
        config.validate()


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_shift_config_roundtrip_via_dict() -> None:
    config = get_default_shift_config()
    rebuilt = ShiftConfig.from_dict(config.to_dict())
    assert rebuilt.name == config.name
    assert rebuilt.rotation == config.rotation
    assert len(rebuilt.shifts) == len(config.shifts)
    for a, b in zip(rebuilt.shifts, config.shifts):
        assert a.name == b.name
        assert a.label == b.label
        assert a.start_hour == b.start_hour
        assert a.end_hour == b.end_hour
        assert a.rotation == b.rotation
        assert a.calltakers == b.calltakers
        assert a.dispatchers == b.dispatchers


def test_shift_config_omits_unset_staffing_in_dict() -> None:
    data = ShiftConfig(rotation=[1], shifts=[Shift("A", rotation=1)]).to_dict()
    assert "calltakers" not in data["shifts"][0]
    assert "dispatchers" not in data["shifts"][0]


def test_realism_config_default_uses_default_shift_config() -> None:
    realism = RealismConfig()
    assert realism.shift_config.name == "2x12h-4shift-14day"
    realism.shift_config.validate()


def test_realism_config_roundtrips_shift_config(tmp_path) -> None:
    realism = RealismConfig()
    realism.shift_config = get_preset("2x12h-2shift")
    path = tmp_path / "realism.yaml"
    realism.to_yaml(path)
    reloaded = RealismConfig.from_yaml(path)
    assert reloaded.shift_config.name == "2x12h-2shift"
    assert [s.name for s in reloaded.shift_config.shifts] == ["A", "C"]


def test_realism_config_writes_shift_section(tmp_path) -> None:
    path = tmp_path / "realism.yaml"
    RealismConfig().to_yaml(path)
    assert "shift_config:" in path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Staffing helpers
# ---------------------------------------------------------------------------


def test_distribute_splits_totals() -> None:
    assert _distribute(12, 4) == [3, 3, 3, 3]
    assert _distribute(10, 4) == [3, 3, 2, 2]
    assert _distribute(0, 0) == []
    assert _distribute(1, 4) == [1, 0, 0, 0]


def test_resolve_staffing_uses_explicit_counts() -> None:
    config = get_default_shift_config()
    plan = _resolve_shift_staffing(config, GenerationRequest())
    assert {name: (ct, dsp) for name, ct, dsp in plan} == {
        "A": (3, 2),
        "B": (3, 2),
        "C": (3, 2),
        "D": (3, 2),
    }


def test_resolve_staffing_falls_back_to_global_split() -> None:
    config = ShiftConfig(
        name="custom",
        rotation=[1],
        shifts=[Shift(name, rotation=1) for name in ("A", "B", "C")],
    )
    request = GenerationRequest(calltaker_pool_size=12, dispatcher_pool_size=9)
    plan = _resolve_shift_staffing(config, request)
    assert sum(item[1] for item in plan) == 12
    assert sum(item[2] for item in plan) == 9
    assert all(ct >= 1 and dsp >= 1 for _, ct, dsp in plan)


def test_zipf_pick_returns_only_pool_names() -> None:
    rng = np.random.default_rng(seed=1)
    names = ["Alice", "Bob", "Carol"]
    picked = {_zipf_pick(rng, names) for _ in range(500)}
    assert picked <= set(names)


# ---------------------------------------------------------------------------
# End-to-end incident generation
# ---------------------------------------------------------------------------


def test_application_includes_shift_columns() -> None:
    request = GenerationRequest(
        rows=30,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        seed=3,
    )
    frame = Synth911Application(address_provider=_one()).generate(request).incidents
    assert frame is not None
    assert {"shift", "shift_label", "shift_group"}.issubset(frame.columns)
    assert set(frame["shift"]) <= {"A", "B", "C", "D"}
    assert set(frame["shift_label"]) <= {"DAY", "NIGHT"}


def test_application_assigned_shift_matches_timestamp() -> None:
    config = get_default_shift_config()
    request = GenerationRequest(
        rows=80,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        seed=4,
    )
    frame = Synth911Application(address_provider=_one()).generate(request).incidents
    assert frame is not None
    for _, row in frame.iterrows():
        expected = config.active_shift(row["call_start_time"])
        assert row["shift"] == expected.name, (row["call_start_time"], expected.name)


def test_application_shift_preset_selects_three_shift() -> None:
    request = GenerationRequest(
        rows=40,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        seed=5,
        shift_preset="3x8h-3shift",
    )
    frame = Synth911Application(address_provider=_one()).generate(request).incidents
    assert frame is not None
    assert set(frame["shift_label"]) <= {"MORNING", "SWING", "NIGHT"}


def test_application_calltakers_fit_per_shift_pool_size() -> None:
    request = GenerationRequest(
        rows=400,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        seed=6,
    )
    frame = Synth911Application(address_provider=_one()).generate(request).incidents
    assert frame is not None
    # Default preset staffs each shift with 3 calltakers and 2 dispatchers, so
    # a shift's output must never show more distinct names than its pool holds.
    for shift_name, group in frame.groupby("shift"):
        assert group["calltaker"].nunique() <= 3, shift_name
        assert group["dispatcher"].nunique() <= 2, shift_name
