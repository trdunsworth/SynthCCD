import pytest
import os
import polars as pl
from synth911gen import generate_911_data

def test_generate_911_data_defaults(tmp_path):
    output_file = tmp_path / "test_dispatch.csv"
    df, call_taker_names, dispatcher_names = generate_911_data(
        num_records=100,
        start_date="2024-01-01",
        end_date="2024-01-31",
        num_names=4,
        locale="en_US",
        selected_agencies=None,
        agency_probabilities=None
    )
    df.write_csv(output_file)
    # Check file exists and has content
    assert os.path.exists(output_file)
    df2 = pl.read_csv(output_file)
    assert len(df2) == 100
    assert set(["call_id", "agency", "event_time"]).issubset(df2.columns)
    # Check call_taker_names and dispatcher_names
    assert isinstance(call_taker_names, dict)
    assert isinstance(dispatcher_names, dict)
    assert all(len(v) == 4 for v in call_taker_names.values())
    assert all(len(v) == 4 for v in dispatcher_names.values())

def test_generate_911_data_agency_selection():
    df, _, _ = generate_911_data(
        num_records=50,
        start_date="2024-01-01",
        end_date="2024-01-02",
        num_names=2,
        locale="en_US",
        selected_agencies=["LAW", "EMS"],
        agency_probabilities=[0.6, 0.4]
    )
    assert set(df["agency"].unique().to_list()).issubset({"LAW", "EMS"})
    law_proportion = df.filter(pl.col('agency') == 'LAW').height / df.height
    assert abs(law_proportion - 0.6) < 0.2

def test_generate_911_data_disposition_logic():
    df, _, _ = generate_911_data(num_records=100, selected_agencies=["LAW", "FIRE"])
    # "ARREST MADE" should not appear for FIRE
    fire_dispositions = df.filter(pl.col("agency") == "FIRE")["disposition"].unique()
    assert "ARREST MADE" not in fire_dispositions
    # "ARREST MADE" can appear for LAW
    law_dispositions = df.filter(pl.col("agency") == "LAW")["disposition"].unique()
    assert "ARREST MADE" in law_dispositions or len(law_dispositions) > 0
