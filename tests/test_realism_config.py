"""Tests for RealismConfig: validation, normalization, and YAML round-trips."""
from pathlib import Path

import numpy as np
import pytest
import yaml

from synth911gen3.exceptions import ValidationError
from synth911gen3.realism_config import RealismConfig
from synth911gen3.shifts import get_default_shift_config


class TestRealismConfigRoundTrip:
    """Tests for YAML serialization round-trip."""

    def test_default_config_roundtrip(self, tmp_path: Path) -> None:
        """Default config should survive to_yaml/from_yaml unchanged."""
        config = RealismConfig()
        path = tmp_path / "config.yaml"
        config.to_yaml(path)
        loaded = RealismConfig.from_yaml(path)

        assert loaded.agency_weights == config.agency_weights
        assert loaded.priority_weights == config.priority_weights
        assert loaded.problem_profiles == config.problem_profiles
        assert loaded.call_reception_weights == config.call_reception_weights
        assert loaded.disposition_profiles == config.disposition_profiles
        assert loaded.time_profiles == config.time_profiles
        assert loaded.dispatch_init_fraction == config.dispatch_init_fraction
        assert loaded.phone_metrics == config.phone_metrics
        assert np.allclose(loaded.hourly_weights, config.hourly_weights)
        assert loaded.agency_names == config.agency_names
        assert loaded.shift_config.to_dict() == config.shift_config.to_dict()

    def test_custom_config_roundtrip(self, tmp_path: Path) -> None:
        """Custom config with overrides should round-trip correctly."""
        config = RealismConfig()
        config.agency_weights = {"LAW": 0.6, "FIRE": 0.2, "EMS": 0.2}
        config.agency_names = {"LAW": "POLICE", "FIRE": "FIRE", "EMS": "EMS"}
        config.phone_metrics["min_hourly_volume"] = 5.0

        path = tmp_path / "custom.yaml"
        config.to_yaml(path)
        loaded = RealismConfig.from_yaml(path)

        assert loaded.agency_weights == {"LAW": 0.6, "FIRE": 0.2, "EMS": 0.2}
        assert loaded.agency_names == {"LAW": "POLICE", "FIRE": "FIRE", "EMS": "EMS"}
        assert loaded.phone_metrics["min_hourly_volume"] == 5.0

    def test_shift_config_roundtrip(self, tmp_path: Path) -> None:
        """ShiftConfig should survive round-trip via RealismConfig."""
        config = RealismConfig()
        config.shift_config = get_default_shift_config()

        path = tmp_path / "shifts.yaml"
        config.to_yaml(path)
        loaded = RealismConfig.from_yaml(path)

        assert loaded.shift_config.to_dict() == config.shift_config.to_dict()

    def test_yaml_file_not_found(self) -> None:
        """from_yaml should raise for missing file."""
        with pytest.raises(FileNotFoundError):
            RealismConfig.from_yaml(Path("/nonexistent/path.yaml"))

    def test_invalid_yaml_syntax(self, tmp_path: Path) -> None:
        """from_yaml should raise for invalid YAML."""
        bad = tmp_path / "bad.yaml"
        bad.write_text("[invalid yaml")
        with pytest.raises(yaml.YAMLError):
            RealismConfig.from_yaml(bad)

    def test_empty_yaml_uses_defaults(self, tmp_path: Path) -> None:
        """Empty YAML should fall back to defaults."""
        empty = tmp_path / "empty.yaml"
        empty.write_text("")
        loaded = RealismConfig.from_yaml(empty)

        assert loaded.agency_weights == {"LAW": 0.52, "FIRE": 0.20, "EMS": 0.28}
        assert loaded.agency_names == {"LAW": "LAW", "FIRE": "FIRE", "EMS": "EMS"}


class TestRealismConfigWeightValidation:
    """Tests for weight validation in _validate()."""

    def test_valid_default_config_passes(self) -> None:
        """Default config should pass validation."""
        config = RealismConfig()
        config._validate()

    def test_priority_weights_must_sum_to_one(self) -> None:
        """Priority weights per agency must sum to 1.0."""
        config = RealismConfig()
        config.priority_weights = {
            "LAW": {1: 0.5, 2: 0.5, 3: 0.0, 4: 0.0, 5: 0.0},
            "FIRE": {1: 0.2, 2: 0.2, 3: 0.2, 4: 0.2, 5: 0.2},
            "EMS": {1: 0.2, 2: 0.2, 3: 0.2, 4: 0.2, 5: 0.2},
        }
        config._validate()

        config.priority_weights["LAW"] = {1: 0.6, 2: 0.6, 3: 0.0, 4: 0.0, 5: 0.0}
        with pytest.raises(ValidationError, match="Priority weights for LAW must sum to 1.0"):
            config._validate()

    def test_priority_weights_unknown_agency_rejected(self) -> None:
        """Priority weights for unknown agency should be rejected."""
        config = RealismConfig()
        config.priority_weights = {
            "LAW": {1: 0.2, 2: 0.2, 3: 0.2, 4: 0.2, 5: 0.2},
            "UNKNOWN": {1: 0.2, 2: 0.2, 3: 0.2, 4: 0.2, 5: 0.2},
        }
        with pytest.raises(
            ValidationError, match="Priority weights defined for unknown agency: UNKNOWN"
        ):
            config._validate()

    def test_problem_profiles_must_sum_to_one_per_priority(self) -> None:
        """Problem profiles per agency/priority must sum to 1.0."""
        config = RealismConfig()
        config._validate()

        config.problem_profiles["LAW"][1] = [("Test", 0.5), ("Test2", 0.3)]
        with pytest.raises(
            ValidationError, match="Problem profiles for LAW priority 1 must sum to 1.0"
        ):
            config._validate()

    def test_problem_profiles_missing_priority_rejected(self) -> None:
        """Missing priority in problem profiles should be rejected."""
        config = RealismConfig()
        del config.problem_profiles["LAW"][3]
        with pytest.raises(ValidationError, match="Problem profiles missing for LAW priority 3"):
            config._validate()

    def test_problem_profiles_unknown_agency_rejected(self) -> None:
        """Problem profiles for unknown agency should be rejected."""
        config = RealismConfig()
        config.problem_profiles = {"UNKNOWN": {1: [("Test", 1.0)]}}
        with pytest.raises(
            ValidationError, match="Problem profiles defined for unknown agency: UNKNOWN"
        ):
            config._validate()

    def test_disposition_profiles_must_sum_to_one(self) -> None:
        """Disposition profiles per agency must sum to 1.0."""
        config = RealismConfig()
        config._validate()

        config.disposition_profiles["LAW"] = [("NR", 0.5), ("RE", 0.3)]
        with pytest.raises(ValidationError, match="Disposition profiles for LAW must sum to 1.0"):
            config._validate()

    def test_disposition_profiles_unknown_agency_rejected(self) -> None:
        """Disposition profiles for unknown agency should be rejected."""
        config = RealismConfig()
        config.disposition_profiles = {"UNKNOWN": [("NR", 1.0)]}
        with pytest.raises(
            ValidationError, match="Disposition profiles defined for unknown agency: UNKNOWN"
        ):
            config._validate()

    def test_time_profiles_missing_agency_rejected(self) -> None:
        """Missing time profiles for agency should be rejected."""
        config = RealismConfig()
        del config.time_profiles["FIRE"]
        with pytest.raises(ValidationError, match="Time profiles missing for agency: FIRE"):
            config._validate()

    def test_time_profiles_missing_priority_rejected(self) -> None:
        """Missing priority in time profiles should be rejected."""
        config = RealismConfig()
        del config.time_profiles["LAW"][3]
        with pytest.raises(ValidationError, match="Time profiles missing for LAW priority 3"):
            config._validate()

    def test_time_profiles_missing_required_keys_rejected(self) -> None:
        """Missing required keys in time profiles should be rejected."""
        config = RealismConfig()
        config.time_profiles["LAW"][1] = {"interview_mean": 10}
        with pytest.raises(ValidationError, match="Time profiles for LAW priority 1 missing keys"):
            config._validate()

    def test_dispatch_init_fraction_bounds_validated(self) -> None:
        """dispatch_init_fraction bounds must satisfy 0 <= lo <= hi."""
        config = RealismConfig()
        config._validate()

        config.dispatch_init_fraction[1] = (0.5, 0.3)
        with pytest.raises(
            ValidationError,
            match="dispatch_init_fraction for priority 1 must satisfy 0 <= lo <= hi",
        ):
            config._validate()

        config.dispatch_init_fraction[1] = (-0.1, 0.5)
        with pytest.raises(
            ValidationError,
            match="dispatch_init_fraction for priority 1 must satisfy 0 <= lo <= hi",
        ):
            config._validate()

    def test_dispatch_init_fraction_missing_priority_rejected(self) -> None:
        """Missing priority in dispatch_init_fraction should be rejected."""
        config = RealismConfig()
        del config.dispatch_init_fraction[3]
        with pytest.raises(ValidationError, match="dispatch_init_fraction missing for priority 3"):
            config._validate()

    def test_phone_metrics_required_keys(self) -> None:
        """phone_metrics must contain all required keys."""
        config = RealismConfig()
        config._validate()

        config.phone_metrics = {"min_hourly_volume": 1.0}
        with pytest.raises(ValidationError, match="phone_metrics missing keys"):
            config._validate()

    def test_phone_metrics_max_abandonment_rate_bounds(self) -> None:
        """phone_metrics.max_abandonment_rate must be in [0, 1]."""
        config = RealismConfig()
        config.phone_metrics["max_abandonment_rate"] = 1.5
        with pytest.raises(
            ValidationError, match="phone_metrics.max_abandonment_rate must be between 0 and 1"
        ):
            config._validate()

        config.phone_metrics["max_abandonment_rate"] = -0.1
        with pytest.raises(
            ValidationError, match="phone_metrics.max_abandonment_rate must be between 0 and 1"
        ):
            config._validate()

    def test_phone_metrics_min_hourly_volume_non_negative(self) -> None:
        """phone_metrics.min_hourly_volume must be non-negative."""
        config = RealismConfig()
        config.phone_metrics["min_hourly_volume"] = -1
        with pytest.raises(
            ValidationError, match="phone_metrics.min_hourly_volume must be non-negative"
        ):
            config._validate()

    def test_agency_names_mapping_required(self) -> None:
        """Every agency in agency_weights must have a display name."""
        config = RealismConfig()
        config.agency_weights["NEW"] = 0.1
        # Provide minimal valid time_profiles for NEW agency to reach agency_names check
        config.time_profiles["NEW"] = {
            p: {
                "interview_mean": 10,
                "dispatch_mean": 5,
                "turnout_mean": 10,
                "travel_mean": 100,
                "scene_mean": 1000,
                "closeout_mean": 100,
                "phone_mean": 100,
            }
            for p in range(1, 6)
        }
        # Also need problem_profiles and disposition_profiles
        config.problem_profiles["NEW"] = {p: [("Test", 1.0)] for p in range(1, 6)}
        config.disposition_profiles["NEW"] = [("NR", 1.0)]
        config.priority_weights["NEW"] = {1: 0.2, 2: 0.2, 3: 0.2, 4: 0.2, 5: 0.2}

        with pytest.raises(ValidationError, match="Agency name mapping missing for: NEW"):
            config._validate()

    def test_agency_weights_normalized_in_from_yaml(self, tmp_path: Path) -> None:
        """from_yaml should normalize agency weights to sum to 1.0."""
        yaml_content = """
agency_weights:
  LAW: 52
  FIRE: 20
  EMS: 28
"""
        path = tmp_path / "norm.yaml"
        path.write_text(yaml_content)
        loaded = RealismConfig.from_yaml(path)

        assert abs(sum(loaded.agency_weights.values()) - 1.0) < 0.001
        assert loaded.agency_weights["LAW"] == pytest.approx(0.52)
        assert loaded.agency_weights["FIRE"] == pytest.approx(0.20)
        assert loaded.agency_weights["EMS"] == pytest.approx(0.28)

    def test_priority_weights_normalized_in_from_yaml(self, tmp_path: Path) -> None:
        """from_yaml should normalize priority weights per agency."""
        yaml_content = """
agency_weights:
  LAW: 1
  FIRE: 1
  EMS: 1
priority_weights:
  LAW:
    1: 10
    2: 20
    3: 30
    4: 20
    5: 20
"""
        path = tmp_path / "norm.yaml"
        path.write_text(yaml_content)
        loaded = RealismConfig.from_yaml(path)

        total = sum(loaded.priority_weights["LAW"].values())
        assert abs(total - 1.0) < 0.001

    def test_hourly_weights_must_have_24_values(self, tmp_path: Path) -> None:
        """hourly_weights must have exactly 24 values."""
        yaml_content = "hourly_weights: [0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04]\n"
        path = tmp_path / "bad_hourly.yaml"
        path.write_text(yaml_content)
        with pytest.raises(ValidationError, match="hourly_weights must have exactly 24 values"):
            RealismConfig.from_yaml(path)

    def test_hourly_weights_normalized_in_from_yaml(self, tmp_path: Path) -> None:
        """from_yaml should normalize hourly_weights to sum to 1.0."""
        yaml_content = "hourly_weights: [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]\n"
        path = tmp_path / "norm.yaml"
        path.write_text(yaml_content)
        loaded = RealismConfig.from_yaml(path)

        assert abs(sum(loaded.hourly_weights) - 1.0) < 0.001

    def test_shift_config_validation_called(self, tmp_path: Path) -> None:
        """ShiftConfig validation should be invoked during _validate."""
        config = RealismConfig()
        config.shift_config = config.shift_config  # default is valid

        config.shift_config.shifts = []
        with pytest.raises(
            ValidationError, match="shift_config.shifts must define at least one shift"
        ):
            config._validate()

    def test_call_reception_weights_normalized(self, tmp_path: Path) -> None:
        """call_reception_weights should be normalized in from_yaml."""
        yaml_content = """
agency_weights:
  LAW: 1
  FIRE: 1
  EMS: 1
call_reception_weights:
  E-911: 33
  Phone: 38
  OFFICER: 14
"""
        path = tmp_path / "norm.yaml"
        path.write_text(yaml_content)
        loaded = RealismConfig.from_yaml(path)

        total = sum(loaded.call_reception_weights.values())
        assert abs(total - 1.0) < 0.001

    def test_normalize_weights_rejects_zero_sum(self) -> None:
        """_normalize_weights should reject zero or negative sum."""
        with pytest.raises(ValidationError, match="Weights must sum to a positive value"):
            RealismConfig._normalize_weights({"A": 0, "B": 0})

        with pytest.raises(ValidationError, match="Weights must sum to a positive value"):
            RealismConfig._normalize_weights({"A": -1, "B": 1})


class TestRealismConfigEdgeCases:
    """Additional edge case tests."""

    def test_agency_display_name_getter(self) -> None:
        """get_agency_display_name should return mapping or fallback."""
        config = RealismConfig()
        config.agency_names = {"LAW": "POLICE", "FIRE": "FIRE"}

        assert config.get_agency_display_name("LAW") == "POLICE"
        assert config.get_agency_display_name("FIRE") == "FIRE"
        assert config.get_agency_display_name("EMS") == "EMS"
        assert config.get_agency_display_name("UNKNOWN") == "UNKNOWN"

    def test_partial_yaml_overrides_only_specified_fields(self, tmp_path: Path) -> None:
        """Partial YAML should only override specified fields, keep defaults for rest."""
        yaml_content = """
agency_weights:
  LAW: 0.7
  FIRE: 0.2
  EMS: 0.1
"""
        path = tmp_path / "partial.yaml"
        path.write_text(yaml_content)
        loaded = RealismConfig.from_yaml(path)

        assert loaded.agency_weights["LAW"] == 0.7
        assert loaded.priority_weights == RealismConfig().priority_weights
        assert loaded.problem_profiles == RealismConfig().problem_profiles

    def test_to_yaml_creates_valid_yaml(self, tmp_path: Path) -> None:
        """to_yaml should produce valid YAML that can be loaded."""
        config = RealismConfig()
        path = tmp_path / "output.yaml"
        config.to_yaml(path)

        content = path.read_text()
        assert "agency_weights:" in content
        assert "priority_weights:" in content
        assert "hourly_weights:" in content

        loaded = RealismConfig.from_yaml(path)
        assert loaded.agency_weights == config.agency_weights


class TestNameLocalesConfig:
    """Tests for the ``name_locales`` realism-config section."""

    def test_default_config_has_no_name_locales(self) -> None:
        config = RealismConfig()
        assert config.name_locales == {}

    def test_yaml_list_form_roundtrip(self, tmp_path: Path) -> None:
        config = RealismConfig()
        config.name_locales = {"IE": [("en_IE", 1.0), ("ga_IE", 1.0)]}
        path = tmp_path / "names.yaml"
        config.to_yaml(path)
        loaded = RealismConfig.from_yaml(path)

        assert loaded.name_locales == {"IE": [("en_IE", 1.0), ("ga_IE", 1.0)]}
        # Equal weights emit as a plain list in YAML
        assert "IE: [en_IE, ga_IE]" in path.read_text()

    def test_yaml_mapping_form_roundtrip(self, tmp_path: Path) -> None:
        config = RealismConfig()
        config.name_locales = {"US": [("en_US", 0.64), ("es_MX", 0.16), ("en_NG", 0.07)]}
        path = tmp_path / "names.yaml"
        config.to_yaml(path)
        loaded = RealismConfig.from_yaml(path)

        assert loaded.name_locales == config.name_locales
        # Unequal weights emit as a locale -> weight mapping
        content = path.read_text()
        assert "en_US: 0.64" in content
        assert "es_MX: 0.16" in content

    def test_yaml_accepts_country_aliases(self, tmp_path: Path) -> None:
        path = tmp_path / "aliases.yaml"
        path.write_text("name_locales:\n  UK:\n    - en_GB\n")
        loaded = RealismConfig.from_yaml(path)
        assert loaded.name_locales == {"GB": [("en_GB", 1.0)]}

    def test_yaml_rejects_unknown_locale(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("name_locales:\n  US:\n    - xx_XX\n")
        with pytest.raises(ValidationError, match="Unknown Faker locale"):
            RealismConfig.from_yaml(path)

    def test_yaml_rejects_empty_spec(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("name_locales:\n  US: []\n")
        with pytest.raises(ValidationError, match="must not be empty"):
            RealismConfig.from_yaml(path)

    def test_yaml_rejects_non_positive_weight(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("name_locales:\n  US:\n    en_US: 0\n")
        with pytest.raises(ValidationError, match="must be positive"):
            RealismConfig.from_yaml(path)

    def test_programmatic_validation(self) -> None:
        config = RealismConfig()
        config.name_locales = {"us": [("en_US", 1.0)]}
        with pytest.raises(ValidationError, match="uppercase ISO"):
            config._validate()

    def test_programmatic_validation_unknown_locale(self) -> None:
        config = RealismConfig()
        config.name_locales = {"US": [("xx_XX", 1.0)]}
        with pytest.raises(ValidationError, match="Unknown Faker locale"):
            config._validate()

    def test_to_yaml_emits_name_locales_section(self, tmp_path: Path) -> None:
        config = RealismConfig()
        config.name_locales = {"CA": [("en_CA", 1.0), ("fr_CA", 1.0)]}
        path = tmp_path / "out.yaml"
        config.to_yaml(path)
        assert "name_locales:" in path.read_text()


class TestDispatcherDisciplinesConfig:
    """Tests for the dispatcher_disciplines realism section."""

    def test_default_section_populated(self) -> None:
        config = RealismConfig()
        assert config.dispatcher_disciplines == {
            "mode": "auto",
            "min_dispatchers_for_split": 4,
        }

    def test_yaml_override_parses(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text(
            "dispatcher_disciplines:\n"
            "  mode: three_way\n"
            "  min_dispatchers_for_split: 4\n"
        )
        loaded = RealismConfig.from_yaml(path)
        assert loaded.dispatcher_disciplines["mode"] == "three_way"
        assert loaded.dispatcher_disciplines["min_dispatchers_for_split"] == 4

    def test_yaml_rejects_unknown_mode(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("dispatcher_disciplines:\n  mode: four_way\n")
        with pytest.raises(ValidationError, match="mode must be one of"):
            RealismConfig.from_yaml(path)

    def test_yaml_rejects_unknown_key(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("dispatcher_disciplines:\n  allocation:\n    law: 2\n")
        with pytest.raises(ValidationError, match="unknown key"):
            RealismConfig.from_yaml(path)

    def test_yaml_rejects_non_positive_threshold(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("dispatcher_disciplines:\n  min_dispatchers_for_split: 0\n")
        with pytest.raises(ValidationError, match="at least 1"):
            RealismConfig.from_yaml(path)

    def test_yaml_rejects_non_mapping_section(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("dispatcher_disciplines:\n  - auto\n")
        with pytest.raises(ValidationError, match="must be a mapping"):
            RealismConfig.from_yaml(path)

    def test_roundtrip_preserves_values(self, tmp_path: Path) -> None:
        config = RealismConfig()
        config.dispatcher_disciplines = {
            "mode": "two_way",
            "min_dispatchers_for_split": 6,
        }
        path = tmp_path / "out.yaml"
        config.to_yaml(path)
        loaded = RealismConfig.from_yaml(path)
        assert loaded.dispatcher_disciplines == {
            "mode": "two_way",
            "min_dispatchers_for_split": 6,
        }

    def test_to_yaml_emits_section(self, tmp_path: Path) -> None:
        path = tmp_path / "out.yaml"
        RealismConfig().to_yaml(path)
        text = path.read_text()
        assert "dispatcher_disciplines:" in text
        assert "mode: auto" in text
