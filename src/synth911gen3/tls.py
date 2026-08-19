"""TLS trust-store workaround for TLS-inspecting corporate proxies.

Python's bundled CA list (and uv's default roots) do not trust the
certificate issuer used by such proxies, so outbound HTTPS fails with
``invalid peer certificate: UnknownIssuer``. The entry point
:func:`maybe_inject_system_trust` switches the current process to the
operating system's trust store when the operator opts in via the
``SYNTHCCD_SYSTEM_TRUST`` environment variable.

Call this once at process startup (CLI, TUI, server) before any
networked work; it is a no-op when the environment variable is unset.
The injection is guarded by a module-level flag, so repeated calls (for
example in tests or shared entry points) never re-patch the global
``ssl`` module more than once per process.
"""

from __future__ import annotations

import os

_ACTIVE_ENV_VAR = "SYNTHCCD_SYSTEM_TRUST"

# Process-level re-entry guard: ``truststore.inject_into_ssl()`` patches the
# global ``ssl`` module and must run at most once per process, so once injected
# (or skipped) the flag stays set for the lifetime of the process.
_TRUST_INJECTED = False


def maybe_inject_system_trust() -> None:
    """Use the OS certificate store when SYNTHCCD_SYSTEM_TRUST=1.

    On networks with TLS-inspecting proxies, Python's bundled CA list may not
    include the proxy's issuer. Enabling this makes the current process verify
    HTTPS connections against the operating system's trust store instead.

    Safe to call any number of times: the global ``ssl`` module is patched at
    most once per process. Must run before networked work — call it once at
    startup, not per request. This is a no-op unless the environment variable
    is set, so production behavior is unchanged.
    """
    global _TRUST_INJECTED
    if _TRUST_INJECTED:
        return
    if os.environ.get(_ACTIVE_ENV_VAR) != "1":
        return
    try:
        import truststore
    except ImportError:
        return
    truststore.inject_into_ssl()
    _TRUST_INJECTED = True
