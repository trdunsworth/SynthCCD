import pytest
from datetime import date
from pathlib import Path

from synth911gen3.schema import (
    DispatchInitFraction,
    GenerationRequest,
    IfExistsMode,
    OutputFormat,
    OutputSchema,
    PhoneMetrics,
    RealismConfig,
    SchemaVersion,
    Shift,
    ShiftConfig,
    TimeProfileIntervals,
)


class TestTimeProfileIntervals:
    def test_valid_intervals(self):
        intervals = TimeProfileIntervals(
            interview_mean=12,
            dispatch_mean=4,
            turnout_mean=10,
            travel_mean=220,
            scene_mean=1500,
            closeout_mean=240,
            phone_mean=170,
        )
        assert intervals.interview_mean == 12

    def test_negative_interval_rejected(self):
        with pytest.raises(Exception):
            TimeProfileIntervals(
                interview_mean=-1,
                dispatch_mean=4,
                turnout_mean=10,
                travel_mean=220,
                scene_mean=1500,
                closeout_mean=240,
                phone_mean=170,
            )


class TestDispatchInitFraction:
    def test_valid_fraction(self):
        frac = DispatchInitFraction(lo=0.1, hi=0.5)
        assert frac.lo == 0.1
        assert frac.hi == 0.5

    def test_invalid_bounds_rejected(self):
        with pytest.raises(Exception):
            DispatchInitFraction(lo=0.5, hi=0.1)

    def test_equal_bounds_allowed(self):
        frac = DispatchInitFraction(lo=1.0, hi=1.0)
        assert frac.lo == 1.0
        assert frac.hi == 1.0


class TestPhoneMetrics:
    def test_valid_metrics(self):
        metrics = PhoneMetrics(
            min_hourly_volume=2.0,
            nine_one_one_received_fraction=0.48,
            non_emergency_received_fraction=0.58,
            outbound_calls_fraction=0.26,
            nine_one_one_abandonment_rate=0.02,
            night_abandonment_increment=0.03,
            non_emergency_abandonment_rate=0.05,
            max_abandonment_rate=0.12,
            weekend_multiplier=1.12,
            nine_one_one_answer_time_mu=1.80,
            nine_one_one_answer_time_sigma=0.80,
            non_emergency_answer_time_mu=1.70,
            non_emergency_answer_time_sigma=0.80,
            answer_time_thresholds=[10.0, 15.0, 20.0, 40.0],
        )
        assert metrics.nine_one_one_received_fraction == 0.48

    def test_invalid_fraction_rejected(self):
        with pytest.raises(Exception):
            PhoneMetrics(
                min_hourly_volume=2.0,
                nine_one_one_received_fraction=1.5,
                non_emergency_received_fraction=0.58,
                outbound_calls_fraction=0.26,
                nine_one_one_abandonment_rate=0.02,
                night_abandonment_increment=0.03,
                non_emergency_abandonment_rate=0.05,
                max_abandonment_rate=0.12,
                weekend_multiplier=1.12,
                nine_one_one_answer_time_mu=1.80,
                nine_one_one_answer_time_sigma=0.80,
                non_emergency_answer_time_mu=1.70,
                non_emergency_answer_time_sigma=0.80,
                answer_time_thresholds=[10.0],
            )


class TestShift:
    def test_valid_shift(self):
        shift = Shift(
            name="A",
            label="DAY",
            start_hour=6,
            start_minute=0,
            end_hour=18,
            end_minute=0,
            rotation=1,
            calltakers=3,
            dispatchers=2,
        )
        assert shift.name == "A"

    def test_overnight_shift(self):
        shift = Shift(
            name="C",
            label="NIGHT",
            start_hour=18,
            start_minute=0,
            end_hour=6,
            end_minute=0,
            rotation=1,
        )
        assert shift.start_hour == 18
        assert shift.end_hour == 6


class TestShiftConfig:
    def test_valid_config(self):
        config = ShiftConfig(
            name="test",
            cycle_start_weekday=0,
            rotation=[1, 2],
            shifts=[
                Shift(name="A", label="DAY", start_hour=6, start_minute=0, end_hour=18, end_minute=0, rotation=1),
                Shift(name="B", label="NIGHT", start_hour=18, start_minute=0, end_hour=6, end_minute=0, rotation=2),
            ],
        )
        assert len(config.shifts) == 2


class TestRealismConfig:
    def test_valid_config(self):
        config = RealismConfig(
            agency_weights={"LAW": 0.52, "FIRE": 0.20, "EMS": 0.28},
            priority_weights={
                "LAW": {1: 0.12, 2: 0.18, 3: 0.28, 4: 0.26, 5: 0.16},
                "FIRE": {1: 0.18, 2: 0.24, 3: 0.24, 4: 0.20, 5: 0.14},
                "EMS": {1: 0.16, 2: 0.26, 3: 0.28, 4: 0.18, 5: 0.12},
            },
            call_reception_weights={
                "E-911": 0.33,
                "Phone": 0.38,
                "OFFICER": 0.14,
                "Radio": 0.06,
                "C2C": 0.05,
                "NOT CAPTURED": 0.02,
                "Text": 0.01,
                "CAD2CAD": 0.01,
            },
            hourly_weights=[0.03] * 24,
        )
        assert config.agency_weights["LAW"] == 0.52

    def test_invalid_agency_weights_rejected(self):
        with pytest.raises(Exception):
            RealismConfig(agency_weights={"LAW": 0.5, "FIRE": 0.3})  # sums to 0.8

    def test_invalid_priority_weights_rejected(self):
        with pytest.raises(Exception):
            RealismConfig(
                agency_weights={"LAW": 1.0},
                priority_weights={"LAW": {1: 0.5, 2: 0.3}},  # sums to 0.8
            )

    def test_invalid_call_reception_rejected(self):
        with pytest.raises(Exception):
            RealismConfig(
                agency_weights={"LAW": 1.0},
                call_reception_weights={"E-911": 0.5, "Phone": 0.3},
            )

    def test_invalid_hourly_weights_rejected(self):
        with pytest.raises(Exception):
            RealismConfig(
                agency_weights={"LAW": 1.0},
                hourly_weights=[0.1] * 12,  # wrong length
            )

    def test_seasonal_multipliers_valid(self):
        config = RealismConfig(
            agency_weights={"LAW": 1.0},
            seasonal_multipliers={"Heat/Cold Exposure": [1.5, 0.8, 2.0, 0.8]},
        )
        assert config.seasonal_multipliers["Heat/Cold Exposure"] == [1.5, 0.8, 2.0, 0.8]

    def test_seasonal_multipliers_invalid_length(self):
        with pytest.raises(Exception):
            RealismConfig(
                agency_weights={"LAW": 1.0},
                seasonal_multipliers={"Test": [1.0, 1.0, 1.0]},
            )


class TestGenerationRequest:
    def test_defaults(self):
        req = GenerationRequest()
        assert req.rows == 10000
        assert req.area_query == "Kansas City, MO"
        assert req.output_format == OutputFormat.CSV
        assert req.seed == 911

    def test_custom_values(self):
        req = GenerationRequest(
            rows=5000,
            area_query="Seattle, WA",
            output_format=OutputFormat.PARQUET,
            seed=42,
            calltaker_pool_size=20,
            dispatcher_pool_size=15,
        )
        assert req.rows == 5000
        assert req.area_query == "Seattle, WA"
        assert req.output_format == OutputFormat.PARQUET
        assert req.seed == 42

    def test_invalid_rows_rejected(self):
        with pytest.raises(Exception):
            GenerationRequest(rows=0)

    def test_invalid_output_stem_rejected(self):
        with pytest.raises(Exception):
            GenerationRequest(output_stem=".")

    def test_invalid_output_stem_reserved(self):
        with pytest.raises(Exception):
            GenerationRequest(output_stem="CON")

    def test_invalid_output_dir_rejected(self):
        with pytest.raises(Exception):
            GenerationRequest(output_dir=Path("../outside"))

    def test_date_validation(self):
        with pytest.raises(Exception):
            GenerationRequest(start_date=date(2024, 12, 31), end_date=date(2024, 1, 1))

    def test_database_postgresql_requires_host(self):
        with pytest.raises(Exception):
            GenerationRequest(
                output_format=OutputFormat.POSTGRESQL,
                db_name="test",
                db_user="user",
                db_password="pass",
            )

    def test_database_postgresql_default_port(self):
        req = GenerationRequest(
            output_format=OutputFormat.POSTGRESQL,
            db_host="localhost",
            db_name="test",
            db_user="user",
            db_password="pass",
        )
        assert req.db_port == 5432

    def test_database_sqlserver_default_port(self):
        req = GenerationRequest(
            output_format=OutputFormat.SQLSERVER,
            db_host="localhost",
            db_name="test",
            db_user="user",
            db_password="pass",
        )
        assert req.db_port == 1433

    def test_database_mariadb_default_port(self):
        req = GenerationRequest(
            output_format=OutputFormat.MARIADB,
            db_host="localhost",
            db_name="test",
            db_user="user",
            db_password="pass",
        )
        assert req.db_port == 3306

    def test_database_duckdb_default_name(self):
        req = GenerationRequest(
            output_format=OutputFormat.DUCKDB,
            output_stem="test_run",
        )
        assert req.db_name == "test_run.duckdb"

    def test_database_if_exists_validation(self):
        with pytest.raises(Exception):
            GenerationRequest(
                output_format=OutputFormat.POSTGRESQL,
                db_host="localhost",
                db_name="test",
                db_user="user",
                db_password="pass",
                db_if_exists=IfExistsMode("invalid"),
            )

    def test_database_batch_size_validation(self):
        with pytest.raises(Exception):
            GenerationRequest(
                output_format=OutputFormat.POSTGRESQL,
                db_host="localhost",
                db_name="test",
                db_user="user",
                db_password="pass",
                db_batch_size=0,
            )


class TestOutputSchema:
    def test_valid_schema(self):
        schema = OutputSchema(
            version="1.0",
            schema_hash="abc123",
            incidents_columns={"id_number": "int64", "agency": "object"},
            phone_columns={"hour_start": "datetime64[ns]"},
        )
        assert schema.version == "1.0"


class TestSchemaVersion:
    def test_valid_version(self):
        version = SchemaVersion(
            generated_at="2024-01-01T00:00:00Z",
            package_version="0.1.0",
            python_version="3.12.0",
            platform="linux",
        )
        assert version.version == "1.0"
        assert version.package == "synth911gen3"