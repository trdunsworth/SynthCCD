"""SynthCCD — synthetic CAD dispatch and phone-equipment data.

Emulates dispatch archival records (incident lifecycle, personnel,
addresses) and hourly call-center phone metrics, seeded and configurable
through a realism YAML. The package entry point is :func:`main` (the
Typer CLI); the same machinery is reachable via the TUI, the HTTP server,
and the Python API (``Synth911Application``).
"""

from importlib.metadata import version as _pkg_version

from .cli import main
from .realism_config import RealismConfig
from .shifts import Shift, ShiftConfig

__version__ = _pkg_version("SynthCCD")
__all__ = ["RealismConfig", "Shift", "ShiftConfig", "__version__", "main"]
