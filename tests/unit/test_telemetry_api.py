"""Tests for the /api/telemetry/{thread_id} endpoint."""
import os
import sys
from unittest.mock import MagicMock

# Stub heavy imports before importing api.server
sys.modules.setdefault("agent.main_agent", MagicMock(run_deep_agent=MagicMock()))

import pytest
from fastapi.testclient import TestClient

from api.server import app
from agent.telemetry import collector, TelemetryRecord


API_KEY = "test-telemetry-key"
AUTH_HEADERS = {"X-API-Key": API_KEY}


class TestTelemetryApiEndpoint:
    """Test GET /api/telemetry/{thread_id}."""

    @pytest.fixture(autouse=True)
    def _auth_env(self):
        """Set API_SECRET for all tests in this class."""
        os.environ["API_SECRET"] = API_KEY
        yield
        # Only clean up if we set it (don't disturb other tests)
        if os.environ.get("API_SECRET") == API_KEY:
            del os.environ["API_SECRET"]

    def setup_method(self):
        """Clear test threads before each test."""
        for tid in ["test-thread-1", "test-thread-2", "nonexistent-thread"]:
            collector.clear_thread(tid)

    def teardown_method(self):
        """Clean up after each test."""
        for tid in ["test-thread-1", "test-thread-2", "nonexistent-thread"]:
            collector.clear_thread(tid)

    def test_get_telemetry_existing_thread_returns_records(self):
        """GET /api/telemetry/existing_thread_id returns list of records."""
        # Arrange: seed collector with records
        collector.record(TelemetryRecord(
            thread_id="test-thread-1",
            agent_name="main",
            tool_name="tavily_search",
            duration_ms=42.5,
            status="success",
        ))
        collector.record(TelemetryRecord(
            thread_id="test-thread-1",
            agent_name="main",
            tool_name="mysql_query",
            duration_ms=100.0,
            status="success",
        ))

        # Act
        client = TestClient(app)
        response = client.get("/api/telemetry/test-thread-1", headers=AUTH_HEADERS)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_get_telemetry_nonexistent_thread_returns_empty(self):
        """GET /api/telemetry/nonexistent returns empty list."""
        client = TestClient(app)
        response = client.get("/api/telemetry/nonexistent-thread", headers=AUTH_HEADERS)

        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_record_format_has_expected_fields(self):
        """Each record in the response has all expected fields."""
        collector.record(TelemetryRecord(
            thread_id="test-thread-1",
            agent_name="main",
            tool_name="tavily_search",
            duration_ms=42.5,
            status="success",
        ))

        client = TestClient(app)
        response = client.get("/api/telemetry/test-thread-1", headers=AUTH_HEADERS)

        assert response.status_code == 200
        data = response.json()
        record = data[0]

        expected_fields = {
            "thread_id", "agent_name", "tool_name",
            "duration_ms", "status", "error", "timestamp",
        }
        assert expected_fields.issubset(set(record.keys()))
        assert record["thread_id"] == "test-thread-1"
        assert record["agent_name"] == "main"
        assert record["tool_name"] == "tavily_search"
        assert record["duration_ms"] == 42.5
        assert record["status"] == "success"
        assert record["error"] is None
        # timestamp should be an ISO-format string
        assert isinstance(record["timestamp"], str)
        # Verify it parses as ISO
        from datetime import datetime
        datetime.fromisoformat(record["timestamp"])

    def test_telemetry_error_record_has_error_field(self):
        """Error records include the error string."""
        collector.record(TelemetryRecord(
            thread_id="test-thread-2",
            agent_name="db_agent",
            tool_name="mysql_query",
            duration_ms=5000.0,
            status="error",
            error="Connection timeout",
        ))

        client = TestClient(app)
        response = client.get("/api/telemetry/test-thread-2", headers=AUTH_HEADERS)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "error"
        assert data[0]["error"] == "Connection timeout"
