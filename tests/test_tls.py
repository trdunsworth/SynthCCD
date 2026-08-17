"""Tests for system-trust injection under the SYNTHCCD_SYSTEM_TRUST env var."""
import sys
from types import SimpleNamespace

import pytest

from synth911gen3.tls import maybe_inject_system_trust


def test_noop_without_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SYNTHCCD_SYSTEM_TRUST", raising=False)
    assert maybe_inject_system_trust() is None


def test_noop_when_env_var_not_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNTHCCD_SYSTEM_TRUST", "0")
    assert maybe_inject_system_trust() is None


def test_injects_system_trust_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[bool] = []
    fake_truststore = SimpleNamespace(inject_into_ssl=lambda: calls.append(True))
    monkeypatch.setenv("SYNTHCCD_SYSTEM_TRUST", "1")
    monkeypatch.setitem(sys.modules, "truststore", fake_truststore)

    maybe_inject_system_trust()

    assert calls == [True]


def test_graceful_when_truststore_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNTHCCD_SYSTEM_TRUST", "1")
    monkeypatch.setitem(sys.modules, "truststore", None)

    assert maybe_inject_system_trust() is None
