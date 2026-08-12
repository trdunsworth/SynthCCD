class Synth911GenError(Exception):
    """Base exception for synth911gen3."""


class ValidationError(Synth911GenError):
    """Raised when a generation request is invalid."""


class AddressLookupError(Synth911GenError):
    """Raised when addresses cannot be loaded from the configured provider."""


class AddressConnectionError(AddressLookupError):
    """Raised when an address provider cannot be reached over the network.

    Distinct from :class:`AddressLookupError` so callers can tell an
    unreachable service (TLS failure, proxy issue, DNS, etc.) apart from an
    area that simply has too few usable addresses.
    """


class ExportError(Synth911GenError):
    """Raised when generated data cannot be exported."""
