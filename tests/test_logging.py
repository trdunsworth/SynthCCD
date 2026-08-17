"""Tests for logging configuration, loggers, and the ProgressReporter."""
import logging
from collections.abc import Iterator

import pytest

from synth911gen3.addresses import StaticAddressProvider
from synth911gen3.app import Synth911Application
from synth911gen3.config import DatasetKind, GenerationRequest, OutputFormat
from synth911gen3.domain import Address
from synth911gen3.logging_conf import (
    _ROOT_LOGGER,
    ProgressReporter,
    configure_logging,
    get_logger,
)


class _RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _quiet_logger(name: str) -> tuple[logging.Logger, _RecordingHandler]:
    logger = get_logger(name)
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = _RecordingHandler()
    logger.addHandler(handler)
    return logger, handler


@pytest.fixture(autouse=True)
def _reset_package_logger() -> Iterator[None]:
    _ROOT_LOGGER.handlers.clear()
    _ROOT_LOGGER.setLevel(logging.NOTSET)
    _ROOT_LOGGER.propagate = True
    yield
    _ROOT_LOGGER.handlers.clear()
    _ROOT_LOGGER.setLevel(logging.NOTSET)
    _ROOT_LOGGER.propagate = True


def test_configure_logging_attaches_exactly_one_handler() -> None:
    configure_logging(verbose=True)
    configure_logging(quiet=True)
    configure_logging()
    assert len(_ROOT_LOGGER.handlers) == 1


def test_configure_logging_quiet_sets_error_level() -> None:
    configure_logging(quiet=True)
    assert _ROOT_LOGGER.level == logging.ERROR


def test_configure_logging_verbose_sets_debug_level() -> None:
    configure_logging(verbose=True)
    assert _ROOT_LOGGER.level == logging.DEBUG


def test_get_logger_is_package_scoped() -> None:
    assert get_logger("incidents").name == "SynthCCD.incidents"
    assert get_logger().name == "SynthCCD"


def test_progress_reporter_emits_only_finish_for_small_totals() -> None:
    logger, handler = _quiet_logger("test_progress_small")
    reporter = ProgressReporter(5, logger, min_total=10)
    reporter.update(2)
    reporter.update(5)
    reporter.finish()
    assert handler.messages == ["done (5/5)"]


def test_progress_reporter_emits_intermediates_for_large_totals() -> None:
    logger, handler = _quiet_logger("test_progress_large")
    reporter = ProgressReporter(100, logger, min_total=50)
    reporter.update(25)
    reporter.update(60)
    reporter.finish()
    assert handler.messages == [
        "25% complete (25/100)",
        "60% complete (60/100)",
        "done (100/100)",
    ]


def test_application_logs_build_status(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="SynthCCD")
    provider = StaticAddressProvider(
        [
            Address("101 N Main St", "Kansas City", "Missouri"),
            Address("204 E 12th St", "Kansas City", "Missouri"),
        ]
    )
    request = GenerationRequest(
        rows=10,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        seed=1,
    )

    Synth911Application(address_provider=provider).generate(request)

    messages = " | ".join(record.message for record in caplog.records)
    assert "Incidents built: 10 rows x " in messages


def test_incident_generator_logs_progress_for_large_run(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="SynthCCD")
    provider = StaticAddressProvider(
        [
            Address("101 N Main St", "Kansas City", "Missouri"),
            Address("204 E 12th St", "Kansas City", "Missouri"),
        ]
    )
    request = GenerationRequest(
        rows=10_000,
        dataset=DatasetKind.INCIDENTS,
        output_format=OutputFormat.PANDAS,
        seed=1,
    )

    Synth911Application(address_provider=provider).generate(request)

    messages = [record.message for record in caplog.records]
    assert any("complete" in message for message in messages), messages[:5]
