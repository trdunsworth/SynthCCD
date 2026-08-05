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
