class Synth911GenError(Exception):
    """Base exception for synth911gen3."""


class ValidationError(Synth911GenError):
    """Raised when a generation request is invalid."""


class AddressLookupError(Synth911GenError):
    """Raised when addresses cannot be loaded from the configured provider."""


class ExportError(Synth911GenError):
    """Raised when generated data cannot be exported."""
