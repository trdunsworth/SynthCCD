"""Dependency security audit wrapper.

Runs ``pip-audit`` against the current environment. On networks with a
TLS-inspecting proxy, set ``SYNTHCCD_SYSTEM_TRUST=1`` so HTTPS verification
uses the operating system trust store instead of Python's bundled CA list
(verification stays on).

Usage:
    uv run scripts/audit_deps.py
"""

from __future__ import annotations

import os


def main() -> None:
    if os.environ.get("SYNTHCCD_SYSTEM_TRUST") == "1":
        try:
            import truststore
        except ImportError:
            pass
        else:
            truststore.inject_into_ssl()

    from pip_audit._cli import audit

    audit()


if __name__ == "__main__":
    main()
