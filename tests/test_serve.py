"""Tests for the API server middleware and security features."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from synth911gen3.serve import _DEFAULT_RATE_LIMIT, _RateLimitMiddleware, app


def _reset_rate_limiter() -> None:
    """Walk the ASGI app chain and reset the rate limiter's hit counters."""
    current = app.middleware_stack
    while hasattr(current, "app"):
        if isinstance(current, _RateLimitMiddleware):
            current.reset()
            return
        current = current.app


@pytest.fixture(autouse=True)
def _clean_rate_limiter() -> None:  # type: ignore[misc]
    """Clear rate limiter state between tests."""
    yield
    _reset_rate_limiter()


@pytest.fixture()
def client() -> TestClient:
    """Return a TestClient bound to the app."""
    return TestClient(app, raise_server_exceptions=False)


class TestRateLimiter:
    """Verify the sliding-window rate limiter returns 429 when exhausted."""

    def test_health_endpoint_works(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_429_after_rate_limit_exceeded(self, client: TestClient) -> None:
        """Fire *max_requests + 1* requests; the last should get 429."""
        for _ in range(_DEFAULT_RATE_LIMIT):
            resp = client.get("/health")
            assert resp.status_code == 200

        resp = client.get("/health")
        assert resp.status_code == 429
        body = resp.json()
        assert "Rate limit" in body["detail"]
        assert "Retry-After" in resp.headers

    def test_middleware_is_wired(self) -> None:
        """Verify the rate limiter middleware is registered on the app."""
        assert any(
            mw.cls is _RateLimitMiddleware
            for mw in app.user_middleware
        )
