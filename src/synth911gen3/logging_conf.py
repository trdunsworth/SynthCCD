"""Package logging configuration and progress reporting.

All modules log through :func:`get_logger`, which scopes loggers under
the ``SynthCCD`` package name. The effective level is configured once
by :func:`configure_logging` using, in order of precedence: the ``--quiet``
flag, the ``--verbose`` flag, the ``SYNTHCCD_LOG_LEVEL`` environment
variable, then INFO. :class:`ProgressReporter` provides coarse completion
percentages for long-running loops without spamming small runs.
"""

from __future__ import annotations

import logging
import os

PACKAGE_LOGGER = "SynthCCD"
_LOG_LEVEL_ENV = "SYNTHCCD_LOG_LEVEL"
_PROGRESS_MIN_TOTAL = 10_000
_PROGRESS_PERCENT_STEP = 0.05

_ROOT_LOGGER = logging.getLogger(PACKAGE_LOGGER)


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a package-scoped logger, e.g. ``SynthCCD.incidents``."""
    if name is None:
        return _ROOT_LOGGER
    return logging.getLogger(f"{PACKAGE_LOGGER}.{name}")


def _env_level() -> int | None:
    """Resolve the SYNTHCCD_LOG_LEVEL variable to a logging level.

    Returns ``None`` when the variable is unset, empty, or names an
    unknown level, so the caller can fall back to the INFO default.
    """
    value = os.environ.get(_LOG_LEVEL_ENV, "").strip().upper()
    if not value:
        return None
    level = getattr(logging, value, None)
    if not isinstance(level, int):
        return None
    return level


def configure_logging(*, verbose: bool = False, quiet: bool = False) -> None:
    """Set up the package logger on first use.

    Level precedence: ``--quiet`` > ``--verbose`` > ``SYNTHCCD_LOG_LEVEL`` > INFO.
    Handlers are attached once; later calls only adjust the effective level so
    repeated invocation (e.g. from tests or the TUI) is idempotent.
    """
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = _env_level() or logging.INFO

    _ROOT_LOGGER.setLevel(level)
    if not _ROOT_LOGGER.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s\t%(name)s: %(message)s"))
        _ROOT_LOGGER.addHandler(handler)
    _ROOT_LOGGER.propagate = False


class ProgressReporter:
    """Coarse-grained completion reporter for progressive loops.

    Intermediate updates are only emitted (at INFO) once the total crosses a
    threshold so small runs stay quiet while large generations surface progress.
    A final completion line is always logged via ``finish``.
    """

    def __init__(
        self,
        total: int,
        logger: logging.Logger,
        *,
        min_total: int = _PROGRESS_MIN_TOTAL,
        percent_step: float = _PROGRESS_PERCENT_STEP,
    ) -> None:
        self._total = max(total, 1)
        self._logger = logger
        self._increment = max(1, int(self._total * percent_step))
        self._next = self._increment
        self._intermediate = total >= min_total

    def update(self, done: int) -> None:
        """Report progress once ``done`` crosses the next percentage step.

        Silent for runs below the configured total threshold, so small
        generations produce no intermediate chatter.
        """
        if not self._intermediate:
            return
        if done >= self._next:
            percent = 100.0 * done / self._total
            self._logger.info("%.0f%% complete (%d/%d)", percent, done, self._total)
            self._next += self._increment

    def finish(self) -> None:
        """Log the final completion line at the full total."""
        self._logger.info("done (%d/%d)", self._total, self._total)
