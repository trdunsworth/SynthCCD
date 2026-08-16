"""synth911gen3 — synthetic CAD dispatch and phone-equipment data.

Emulates dispatch archival records (incident lifecycle, personnel,
addresses) and hourly call-center phone metrics, seeded and configurable
through a realism YAML. The package entry point is :func:`main` (the
Typer CLI); the same machinery is reachable via the TUI, the HTTP server,
and the Python API (``Synth911Application``).
"""

from .cli import main
from .realism_config import RealismConfig
from .shifts import Shift, ShiftConfig

__all__ = ["RealismConfig", "Shift", "ShiftConfig", "main"]
