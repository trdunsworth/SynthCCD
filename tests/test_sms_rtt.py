"""Tests for the SMS/RTT (text-to-911) channel in the hourly phone metrics.

SMS/RTT is modelled as its own session-counted line rather than a share of the
voice 9-1-1 queue: centres log text contacts as discrete sessions and measure
them separately, and the interaction happens inside and between calls. Its
engagement thresholds are minute-scale because a text reply is not a voice
answer-time distribution.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from synth911gen3.config import DatasetKind, GenerationRequest, OutputFormat
from synth911gen3.generators.phone_metrics import (
    HourlyCallCountGenerator,
    _sms_rtt_thresholds,
    phone_metrics_columns,
)
from synth911gen3.realism_config import RealismConfig


def _request(**overrides) -> GenerationRequest:
    params = {
        "rows": 5_000,
        "dataset": DatasetKind.PHONE,
        "output_format": OutputFormat.PANDAS,
        "seed": 21,
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 1, 7),
    }
    params.update(overrides)
    return GenerationRequest(**params)


@pytest.fixture
def frame() -> pd.DataFrame:
    return HourlyCallCountGenerator().generate(_request())


class TestSchema:
    """The channel emits the full per-line column family."""

    def test_emits_all_line_columns(self, frame: pd.DataFrame) -> None:
        for column in (
            "sms_rtt_calls_received",
            "sms_rtt_calls_abandoned",
            "sms_rtt_mean_duration",
        ):
            assert column in frame.columns, column

    def test_engagement_uses_minute_scale_thresholds(self, frame: pd.DataFrame) -> None:
        """Text engagement is measured in minutes, not the voice 10/15/20/40 s."""
        engagement = [c for c in frame.columns if c.startswith("sms_rtt_answered_")]
        assert engagement
        assert [c for c in engagement if c.endswith("s_pct")]
        # No voice-scale thresholds leak into the text channel.
        assert "sms_rtt_answered_10s_pct" not in frame.columns
        assert "sms_rtt_answered_15s_pct" not in frame.columns

    def test_columns_helper_matches_generated_frame(self) -> None:
        request = _request()
        declared = set(phone_metrics_columns(request, RealismConfig()))
        generated = set(HourlyCallCountGenerator().generate(request).columns)
        assert declared == generated


class TestInvariants:
    def test_counts_are_non_negative(self, frame: pd.DataFrame) -> None:
        assert (frame["sms_rtt_calls_received"] >= 0).all()
        assert (frame["sms_rtt_calls_abandoned"] >= 0).all()

    def test_abandoned_never_exceeds_received(self, frame: pd.DataFrame) -> None:
        assert (
            frame["sms_rtt_calls_abandoned"] <= frame["sms_rtt_calls_received"]
        ).all()

    def test_engagement_bounded_and_monotonic(self, frame: pd.DataFrame) -> None:
        """Percentages stay in [0, 100] and never decrease as the threshold grows."""
        columns = sorted(
            (c for c in frame.columns if c.startswith("sms_rtt_answered_")),
            key=lambda c: int(c.split("_answered_")[1].rstrip("s_pct")),
        )
        values = frame[columns].to_numpy(dtype=float)
        assert (values >= 0.0).all() and (values <= 100.0).all()
        assert (np.diff(values, axis=1) >= -1e-9).all()

    def test_duration_zero_when_no_answered_sessions(self) -> None:
        """Zero sessions yields a zero mean; the 0.5 Poisson floor keeps some."""
        realism = RealismConfig()
        realism.phone_metrics["sms_rtt_abandonment_rate"] = 1.0
        realism.phone_metrics["max_abandonment_rate"] = 1.0
        frame = HourlyCallCountGenerator().generate(_request(realism_config=realism))
        assert (frame["sms_rtt_calls_abandoned"] == frame["sms_rtt_calls_received"]).all()
        assert (frame["sms_rtt_mean_duration"] == 0.0).all()


class TestTotals:
    """SMS/RTT is a separate line and must not inflate reported 9-1-1 volume."""

    def test_excluded_from_total_emergency_calls(self, frame: pd.DataFrame) -> None:
        """Text is not a voice emergency call, so 911 volume stays uncorrupted."""
        assert (
            frame["total_emergency_calls"] == frame["nine_one_one_calls_received"]
        ).all()

    def test_included_in_total_calls(self, frame: pd.DataFrame) -> None:
        expected = (
            frame["total_emergency_calls"]
            + frame["total_nonemergency_calls"]
            + frame["outbound_calls_placed"]
            + frame["sms_rtt_calls_received"]
        )
        pd.testing.assert_series_equal(
            frame["total_calls"], expected, check_names=False
        )

    def test_does_not_disturb_non_emergency_floor(self, frame: pd.DataFrame) -> None:
        """The floor is computed against voice emergency volume only."""
        floor = np.ceil(
            frame["total_emergency_calls"]
            * float(RealismConfig().phone_metrics["non_emergency_floor_ratio"])
        ).astype(int)
        assert (frame["non_emergency_calls_received"] >= floor).all()


class TestConfiguration:
    def test_fraction_scales_volume(self) -> None:
        low = RealismConfig()
        low.phone_metrics["sms_rtt_received_fraction"] = 0.01
        high = RealismConfig()
        high.phone_metrics["sms_rtt_received_fraction"] = 0.20

        low_total = int(
            HourlyCallCountGenerator()
            .generate(_request(realism_config=low))["sms_rtt_calls_received"]
            .sum()
        )
        high_total = int(
            HourlyCallCountGenerator()
            .generate(_request(realism_config=high))["sms_rtt_calls_received"]
            .sum()
        )
        assert high_total > low_total

    def test_abandonment_rate_is_respected(self) -> None:
        realism = RealismConfig()
        realism.phone_metrics["sms_rtt_abandonment_rate"] = 0.15
        realism.phone_metrics["night_abandonment_increment"] = 0.0
        realism.phone_metrics["max_abandonment_rate"] = 1.0
        frame = HourlyCallCountGenerator().generate(_request(realism_config=realism))
        received = frame["sms_rtt_calls_received"].sum()
        abandoned = frame["sms_rtt_calls_abandoned"].sum()
        assert 0.12 < abandoned / received < 0.18

    def test_custom_thresholds_change_columns(self) -> None:
        realism = RealismConfig()
        realism.phone_metrics["sms_rtt_answer_time_thresholds"] = [30.0, 90.0]
        frame = HourlyCallCountGenerator().generate(_request(realism_config=realism))
        assert "sms_rtt_answered_30s_pct" in frame.columns
        assert "sms_rtt_answered_90s_pct" in frame.columns
        assert "sms_rtt_answered_600s_pct" not in frame.columns

    def test_config_without_sms_keys_uses_defaults(self) -> None:
        """A config predating the channel still generates it from defaults."""
        realism = RealismConfig()
        for key in [k for k in realism.phone_metrics if k.startswith("sms_rtt")]:
            del realism.phone_metrics[key]
        frame = HourlyCallCountGenerator().generate(_request(realism_config=realism))
        assert (frame["sms_rtt_calls_received"] >= 0).all()
        assert "sms_rtt_answered_60s_pct" in frame.columns

    def test_default_thresholds_helper(self) -> None:
        assert _sms_rtt_thresholds(RealismConfig()) == [60.0, 120.0, 300.0, 600.0]


class TestReproducibility:
    def test_same_seed_same_output(self) -> None:
        first = HourlyCallCountGenerator().generate(_request())
        second = HourlyCallCountGenerator().generate(_request())
        pd.testing.assert_series_equal(
            first["sms_rtt_calls_received"], second["sms_rtt_calls_received"]
        )

    def test_voice_columns_unaffected_by_channel(self) -> None:
        """Adding the channel must not perturb existing voice series.

        The regression baseline independently confirms this at suite level; this
        pins the local guarantee that voice draws keep their stream position.
        """
        baseline = RealismConfig()
        baseline.phone_metrics["sms_rtt_received_fraction"] = 0.0
        with_text = RealismConfig()

        zero = HourlyCallCountGenerator().generate(_request(realism_config=baseline))
        text = HourlyCallCountGenerator().generate(_request(realism_config=with_text))
        for column in ("nine_one_one_calls_received", "non_emergency_calls_received"):
            pd.testing.assert_series_equal(zero[column], text[column])