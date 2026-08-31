"""Tests for the Prometheus metrics module and /metrics endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from synth911gen3.metrics import (
    GENERATION_COUNT,
    GENERATION_DURATION,
    GENERATION_ERRORS,
    GENERATION_ROWS,
    SERVER_INFO,
    expose_metrics,
    init_server_info,
)
from synth911gen3.serve import _MetricsMiddleware, app


@pytest.fixture()
def client() -> TestClient:
    """Return a TestClient bound to the app."""
    return TestClient(app, raise_server_exceptions=False)


class TestExposeMetrics:
    """Verify the text exposition format returns valid Prometheus output."""

    def test_returns_bytes(self) -> None:
        payload = expose_metrics()
        assert isinstance(payload, bytes)

    def test_contains_help_comments(self) -> None:
        payload = expose_metrics().decode("utf-8")
        assert "synthccd_requests_total" in payload
        assert "synthccd_request_duration_seconds" in payload
        assert "synthccd_active_requests" in payload
        assert "synthccd_generations_total" in payload
        assert "synthccd_generation_rows_total" in payload
        assert "synthccd_generation_duration_seconds" in payload
        assert "synthccd_generation_errors_total" in payload
        assert "synthccd_info" in payload

    def test_prometheus_format_structure(self) -> None:
        """Each metric family should have a # HELP and # TYPE line."""
        payload = expose_metrics().decode("utf-8")
        lines = payload.strip().split("\n")
        metric_names = set()
        for line in lines:
            if line.startswith("# HELP synthccd_"):
                name = line.split()[2]
                metric_names.add(name)
            if line.startswith("# TYPE synthccd_"):
                parts = line.split()
                name = parts[2]
                assert parts[3] in (
                    "counter",
                    "gauge",
                    "histogram",
                    "info",
                ), f"Unexpected type for {name}: {parts[3]}"
        # At minimum these core metrics should be present
        assert "synthccd_requests_total" in metric_names
        assert "synthccd_active_requests" in metric_names


class TestInitServerInfo:
    """Verify the server info metric can be populated."""

    def test_init_sets_version(self) -> None:
        init_server_info(version="0.9.5", python_version="3.12.0")
        # After init, the info metric should have the version label
        # prometheus_client.Info stores its payload in _value dict
        info_dict = SERVER_INFO._value
        assert info_dict.get("version") == "0.9.5"
        assert info_dict.get("python_version") == "3.12.0"


class TestMetricsEndpoint:
    """Verify the /metrics HTTP endpoint serves valid Prometheus output."""

    def test_metrics_returns_200(self, client: TestClient) -> None:
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_metrics_content_type(self, client: TestClient) -> None:
        resp = client.get("/metrics")
        assert "text/plain" in resp.headers["content-type"]

    def test_metrics_body_is_prometheus_format(self, client: TestClient) -> None:
        resp = client.get("/metrics")
        body = resp.text
        # Should have HELP and TYPE lines
        assert "# HELP" in body
        assert "# TYPE" in body
        # Should contain the core metrics
        assert "synthccd_requests_total" in body

    def test_metrics_endpoint_not_tracked_by_metrics_middleware(
        self, client: TestClient
    ) -> None:
        """The /metrics endpoint itself should not increment request counters."""
        # Hit /metrics a few times
        for _ in range(3):
            resp = client.get("/metrics")
            assert resp.status_code == 200

        # The metrics payload should show 0 for /metrics endpoint
        resp = client.get("/metrics")
        body = resp.text
        # There should be no line with endpoint="/metrics" in the active counters
        assert 'endpoint="/metrics"' not in body


class TestMetricsMiddleware:
    """Verify the metrics middleware tracks request counts and durations."""

    def test_middleware_is_wired(self) -> None:
        """Verify the metrics middleware is registered on the app."""
        assert any(
            mw.cls is _MetricsMiddleware
            for mw in app.user_middleware
        )

    def test_health_request_tracked(self, client: TestClient) -> None:
        """A GET /health request should increment the request counter."""
        resp = client.get("/health")
        assert resp.status_code == 200

        # Check the metrics payload for the health endpoint
        metrics_resp = client.get("/metrics")
        body = metrics_resp.text
        assert 'endpoint="/health"' in body
        assert 'method="GET"' in body

    def test_health_request_duration_recorded(self, client: TestClient) -> None:
        """A GET /health request should have a duration observation."""
        resp = client.get("/health")
        assert resp.status_code == 200

        metrics_resp = client.get("/metrics")
        body = metrics_resp.text
        # The histogram should have at least one observation
        assert "synthccd_request_duration_seconds_count" in body

    def test_404_response_tracked(self, client: TestClient) -> None:
        """A request to a non-existent endpoint should track status_code=404."""
        resp = client.get("/nonexistent")
        assert resp.status_code == 404

        metrics_resp = client.get("/metrics")
        body = metrics_resp.text
        assert 'status_code="404"' in body


class TestGenerationMetrics:
    """Verify generation counters are available and functional."""

    def test_generation_count_has_labels(self) -> None:
        """GENERATION_COUNT counter should accept dataset and output_format labels."""
        GENERATION_COUNT.labels(dataset="incidents", output_format="csv").inc()
        # Verify the metric was incremented (no exception = success)

    def test_generation_rows_has_labels(self) -> None:
        """GENERATION_ROWS counter should accept a dataset label."""
        GENERATION_ROWS.labels(dataset="incidents").inc(100)

    def test_generation_duration_has_labels(self) -> None:
        """GENERATION_DURATION histogram should accept dataset and output_format labels."""
        GENERATION_DURATION.labels(dataset="incidents", output_format="csv").observe(1.5)

    def test_generation_errors_has_labels(self) -> None:
        """GENERATION_ERRORS counter should accept dataset and error_type labels."""
        GENERATION_ERRORS.labels(dataset="incidents", error_type="AddressLookupError").inc()
