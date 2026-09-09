"""Tests for population-based volume scaling: tiered 911 rates, row precedence.

Covers the tiered ``population_rates`` realism section (Reading-B anchored),
the rows/population precedence matrix on ``GenerationRequest.resolved_rows``,
the 911-anchored phone-volume derivation, the configurable non-emergency
floor, and the per-center calibration YAML library in config/calibrations/.
"""
from datetime import date
from pathlib import Path
from typing import ClassVar

import pytest

from synth911gen3.addresses import StaticAddressProvider
from synth911gen3.app import Synth911Application
from synth911gen3.config import DatasetKind, GenerationRequest, OutputFormat
from synth911gen3.domain import Address
from synth911gen3.exceptions import ValidationError
from synth911gen3.realism_config import RealismConfig

CALIBRATIONS_DIR = Path(__file__).resolve().parent.parent / "config" / "calibrations"
WEEK_START = date(2026, 1, 1)
WEEK_END = date(2026, 1, 7)


def _provider() -> StaticAddressProvider:
    """Two-address static pool so generation never touches the network."""
    return StaticAddressProvider(
        [
            Address("101 N Main St", "Kansas City", "Missouri"),
            Address("204 E 12th St", "Kansas City", "Missouri"),
        ]
    )


# ---------------------------------------------------------------------------
# Tier lookup
# ---------------------------------------------------------------------------


class TestEmergencyTiers:
    """National tier defaults follow the open-data anchors (rural -> major)."""

    def test_tier_boundaries(self) -> None:
        realism = RealismConfig()
        assert realism.emergency_rate_for_population(50_000) == 400.0
        assert realism.emergency_rate_for_population(99_999) == 400.0
        assert realism.emergency_rate_for_population(100_000) == 650.0
        assert realism.emergency_rate_for_population(230_000) == 650.0
        assert realism.emergency_rate_for_population(500_000) == 1_000.0
        assert realism.emergency_rate_for_population(521_250) == 1_000.0
        assert realism.emergency_rate_for_population(1_000_000) == 1_100.0
        assert realism.emergency_rate_for_population(10_000_000) == 1_100.0

    def test_default_incidents_rate(self) -> None:
        assert RealismConfig().incidents_per_1000_yearly() == 2_200.0

    def test_yaml_override_round_trip(self, tmp_path: Path) -> None:
        realism = RealismConfig()
        realism.population_rates = {
            "emergency_tiers": [[100_000.0, 400.0], [float("inf"), 1_148.0]],
            "incidents_per_1000_yearly": 2_394.0,
        }
        path = tmp_path / "rates.yaml"
        realism.to_yaml(path)
        reloaded = RealismConfig.from_yaml(path)
        assert reloaded.emergency_rate_for_population(50_000) == 400.0
        assert reloaded.emergency_rate_for_population(9_000_000) == 1_148.0
        assert reloaded.incidents_per_1000_yearly() == 2_394.0

    def test_partial_section_merges_over_defaults(self, tmp_path: Path) -> None:
        path = tmp_path / "partial.yaml"
        path.write_text(
            "population_rates:\n  incidents_per_1000_yearly: 3000.0\n",
            encoding="utf-8",
        )
        realism = RealismConfig.from_yaml(path)
        # Tiers untouched by the partial override.
        assert realism.emergency_rate_for_population(50_000) == 400.0
        assert realism.incidents_per_1000_yearly() == 3_000.0

    @pytest.mark.parametrize(
        "section",
        [
            {"emergency_tiers": []},
            {"emergency_tiers": [[500_000.0, 650.0], [100_000.0, 400.0]]},
            {"emergency_tiers": [[100_000.0, 0.0], [float("inf"), 650.0]]},
            {"incidents_per_1000_yearly": 0.0},
            {"incidents_per_1000_yearly": -5.0},
        ],
    )
    def test_invalid_sections_rejected(
        self, tmp_path: Path, section: dict
    ) -> None:
        import yaml

        path = tmp_path / "bad.yaml"
        path.write_text(
            yaml.safe_dump({"population_rates": section}), encoding="utf-8"
        )
        with pytest.raises(ValidationError):
            RealismConfig.from_yaml(path)


# ---------------------------------------------------------------------------
# Rows / population precedence
# ---------------------------------------------------------------------------


class TestResolvedRows:
    """Precedence: explicit rows > population derivation > 10,000 default."""

    def test_neither_set_falls_back_to_default(self) -> None:
        assert GenerationRequest().resolved_rows() == 10_000

    def test_explicit_rows_win_without_population(self) -> None:
        assert GenerationRequest(rows=24_000).resolved_rows() == 24_000

    def test_population_derives_rows_for_a_week(self) -> None:
        request = GenerationRequest(
            population=521_250, start_date=WEEK_START, end_date=WEEK_END
        )
        # 521.25 x 2200 x 7/365, rounded.
        assert request.resolved_rows() == 21_992

    def test_explicit_rows_win_with_population(self) -> None:
        request = GenerationRequest(
            rows=24_000,
            population=521_250,
            start_date=WEEK_START,
            end_date=WEEK_END,
        )
        assert request.resolved_rows() == 24_000

    def test_rows_none_validates_but_zero_rejected(self) -> None:
        GenerationRequest(rows=None).validate()
        with pytest.raises(ValidationError, match="rows must be greater than zero"):
            GenerationRequest(rows=0).validate()

    def test_generate_resolves_rows_on_the_request(self) -> None:
        request = GenerationRequest(
            rows=None,
            population=521_250,
            dataset=DatasetKind.INCIDENTS,
            output_format=OutputFormat.PANDAS,
            seed=11,
            start_date=WEEK_START,
            end_date=WEEK_END,
        )
        result = Synth911Application(address_provider=_provider()).generate(request)
        assert request.rows == 21_992
        assert result.incidents is not None
        assert len(result.incidents) == 21_992


# ---------------------------------------------------------------------------
# 911-anchored phone volume + floor override
# ---------------------------------------------------------------------------


class TestPhoneVolumeAnchoring:
    """Population phone volume tracks the tiered 911 rate (Reading B)."""

    def test_kansas_city_week_phone_totals(self) -> None:
        request = GenerationRequest(
            rows=24_000,
            population=521_250,
            dataset=DatasetKind.ALL,
            output_format=OutputFormat.PANDAS,
            seed=42,
            start_date=WEEK_START,
            end_date=WEEK_END,
            include_event_counts=True,
        )
        result = Synth911Application(address_provider=_provider()).generate(request)
        assert result.hourly_call_counts is not None
        assert len(result.hourly_call_counts) == 7 * 24

        frame = result.hourly_call_counts
        received_911 = int(frame["nine_one_one_calls_received"].sum())
        abandoned_911 = int(frame["nine_one_one_calls_abandoned"].sum())
        received_non_em = int(frame["non_emergency_calls_received"].sum())

        # Tier-1000 anchor: 521.25 x 1000 / 52 ~= 10,024 expected 911/week.
        assert 7_500 <= received_911 <= 12_500
        # Default ~7% abandonment blended with the +3pp night increment.
        assert 0.05 <= abandoned_911 / received_911 <= 0.16
        # Default 1.2 floor keeps non-emergency at or above emergency.
        assert received_non_em >= received_911
        # Event counts reconcile exactly with the incident frame.
        assert result.incidents is not None
        assert int(frame["events_created"].sum()) == len(result.incidents)

    def test_kc_calibration_week_matches_reading_b(self) -> None:
        request = GenerationRequest(
            population=521_250,
            dataset=DatasetKind.ALL,
            output_format=OutputFormat.PANDAS,
            seed=42,
            start_date=WEEK_START,
            end_date=WEEK_END,
            include_event_counts=True,
            realism_config_path=CALIBRATIONS_DIR / "kansas_city_mo.yaml",
        )
        result = Synth911Application(address_provider=_provider()).generate(request)
        assert result.hourly_call_counts is not None
        assert result.incidents is not None
        frame = result.hourly_call_counts

        # KC measured 911 rate (1,148) pins ~11.5K received/week.
        received_911 = int(frame["nine_one_one_calls_received"].sum())
        assert 8_500 <= received_911 <= 14_500
        # KC incidents rate (2,394) pins ~24K rows for the week.
        assert 22_000 <= len(result.incidents) <= 26_000
        # ~51.5% 911 share of received (relaxed 0.9 floor).
        received_non_em = int(frame["non_emergency_calls_received"].sum())
        share = received_911 / (received_911 + received_non_em)
        assert 0.44 <= share <= 0.58
        assert int(frame["events_created"].sum()) == len(result.incidents)

    def test_floor_override_relaxes_below_emergency(self) -> None:
        def _non_em_total(floor: float) -> int:
            realism = RealismConfig()
            realism.phone_metrics["non_emergency_floor_ratio"] = floor
            request = GenerationRequest(
                rows=5_000,
                dataset=DatasetKind.PHONE,
                output_format=OutputFormat.PANDAS,
                seed=7,
                start_date=WEEK_START,
                end_date=WEEK_END,
                realism_config=realism,
            )
            result = Synth911Application(address_provider=_provider()).generate(request)
            assert result.hourly_call_counts is not None
            return int(result.hourly_call_counts["non_emergency_calls_received"].sum())

        assert _non_em_total(0.9) <= _non_em_total(1.2)


# ---------------------------------------------------------------------------
# Calibration library
# ---------------------------------------------------------------------------


class TestCalibrationLibrary:
    """Every shipped per-center calibration loads, validates, and round-trips."""

    EXPECTED_FILES: ClassVar[set[str]] = {
        "kansas_city_mo.yaml",
        "new_york_ny.yaml",
        "washington_dc.yaml",
        "norfolk_va.yaml",
        "king_county_wa.yaml",
        "vermont_rural.yaml",
    }

    def test_all_files_present_and_valid(self) -> None:
        found = {path.name for path in CALIBRATIONS_DIR.glob("*.yaml")}
        assert self.EXPECTED_FILES <= found
        for name in sorted(self.EXPECTED_FILES):
            realism = RealismConfig.from_yaml(CALIBRATIONS_DIR / name)
            realism._validate()

    def test_kansas_city_values(self) -> None:
        realism = RealismConfig.from_yaml(CALIBRATIONS_DIR / "kansas_city_mo.yaml")
        assert realism.phone_metrics["nine_one_one_abandonment_rate"] == 0.10
        assert realism.phone_metrics["non_emergency_floor_ratio"] == 0.9
        assert realism.emergency_rate_for_population(521_250) == 1_148.0
        assert realism.incidents_per_1000_yearly() == 2_394.0

    def test_vermont_rural_rate_below_default_tiers(self) -> None:
        realism = RealismConfig.from_yaml(CALIBRATIONS_DIR / "vermont_rural.yaml")
        assert realism.emergency_rate_for_population(648_000) == 360.0
