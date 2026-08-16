"""TLS trust-store workaround for TLS-inspecting corporate proxies.

Python's bundled CA list (and uv's default roots) do not trust the
certificate issuer used by such proxies, so outbound HTTPS fails with
``invalid peer certificate: UnknownIssuer``. The entry point
:func:`maybe_inject_system_trust` switches the current process to the
operating system's trust store when the operator opts in via the
``SYNTH911_SYSTEM_TRUST`` environment variable.

Call this once at process startup (CLI, TUI, server) before any
networked work; it is a no-op when the environment variable is unset.
"""

from __future__ import annotations

import os

_ACTIVE_ENV_VAR = "SYNTH911_SYSTEM_TRUST"


def maybe_inject_system_trust() -> None:
    """Use the OS certificate store when SYNTH911_SYSTEM_TRUST=1.

    On networks with TLS-inspecting proxies, Python's bundled CA list may not
    include the proxy's issuer. Enabling this makes the current process verify
    HTTPS connections against the operating system's trust store instead.

    This is a no-op unless the environment variable is set, so production
    behavior is unchanged.
    """
    if os.environ.get(_ACTIVE_ENV_VAR) != "1":
        return
    try:
        import truststore
    except ImportError:
        return
    truststore.inject_into_ssl()
