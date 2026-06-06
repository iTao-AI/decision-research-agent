"""Integration tests for API endpoints.

Uses FastAPI TestClient with real conftest fixtures.
Validates telemetry API, upload security, and task endpoint.

Note: agent.main_agent is stubbed in conftest.py to prevent LLM init.
"""
import os
from fastapi.testclient import TestClient

import pytest

from agent.telemetry import collector, TelemetryRecord
from api.server import app

AUTH_HEADERS = {"X-API-Key": "test-integration-key"}


@pytest.fixture(autouse=True)
def _auth_env():
    """Set API_SECRET for all integration tests."""
    os.environ["API_SECRET"] = "test-integration-key"
    yield


@pytest.fixture
def client():
    """FastAPI TestClient for endpoints."""
    return TestClient(app)


@pytest.fixture
def seeded_collector():
    """Seed the collector with test data, then clean up."""
    test_threads = ["test-thread-1", "test-thread-2"]
    for tid in test_threads:
        collector.clear_thread(tid)

    collector.record(TelemetryRecord(
        thread_id="test-thread-1",
        agent_name="main",
        tool_name="tavily_search",
        duration_ms=42.5,
        status="success",
    ))
    collector.record(TelemetryRecord(
        thread_id="test-thread-1",
        agent_name="db_agent",
        tool_name="mysql_query",
        duration_ms=100.0,
        status="success",
    ))
    collector.record(TelemetryRecord(
        thread_id="test-thread-2",
        agent_name="main",
        tool_name="publish_fact",
        duration_ms=10.0,
        status="success",
    ))

    yield collector

    for tid in test_threads:
        collector.clear_thread(tid)


class TestTelemetryEndpoint:
    """GET /api/telemetry/{thread_id} integration tests."""

    def test_existing_thread_returns_records(self, client, seeded_collector):
        """GET /api/telemetry/test-thread-1 returns list of records."""
        response = client.get("/api/telemetry/test-thread-1", headers=AUTH_HEADERS)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_nonexistent_thread_returns_empty(self, client):
        """GET /api/telemetry/nonexistent returns empty list."""
        response = client.get("/api/telemetry/nonexistent-thread", headers=AUTH_HEADERS)

        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_record_has_all_expected_fields(self, client, seeded_collector):
        """Each record contains thread_id, agent_name, tool_name, duration_ms, status."""
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
        assert record["agent_name"] in ("main", "db_agent")
        assert record["status"] == "success"
        assert record["error"] is None
        assert isinstance(record["timestamp"], str)

    def test_error_records_include_error_string(self, client):
        """Error records include the error field."""
        collector.record(TelemetryRecord(
            thread_id="test-thread-2",
            agent_name="db_agent",
            tool_name="mysql_query",
            duration_ms=5000.0,
            status="error",
            error="Connection timeout",
        ))

        response = client.get("/api/telemetry/test-thread-2", headers=AUTH_HEADERS)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "error"
        assert data[0]["error"] == "Connection timeout"

        collector.clear_thread("test-thread-2")


class TestUploadEndpoint:
    """POST /api/upload integration tests — security boundaries."""

    def test_rejects_empty_filename(self, client):
        """Upload with empty filename is rejected."""
        response = client.post(
            "/api/upload",
            files={"files": ("", b"test content")},
            data={"thread_id": "test-thread-1"},
            headers=AUTH_HEADERS,
        )
        assert response.status_code in (400, 422)

    def test_rejects_path_traversal_filename(self, client):
        """Upload with ../../etc/passwd filename is rejected or sanitized."""
        response = client.post(
            "/api/upload",
            files={"files": ("../../../etc/passwd", b"test content")},
            data={"thread_id": "test-thread-1"},
            headers=AUTH_HEADERS,
        )
        # Must either reject or sanitize — never accept original traversal path
        assert response.status_code in (200, 400, 422)
        if response.status_code == 200:
            data = response.json()
            assert "../../../etc/passwd" not in str(data)
            filenames = data.get("files", [])
            for fn in filenames:
                assert isinstance(fn, str), f"Expected string, got {type(fn)}"
                assert ".." not in fn
                assert "/" not in fn
        else:
            # Rejected — that's the safe path
            pass

    def test_rejects_path_traversal_thread_id(self, client):
        response = client.post(
            "/api/upload",
            files={"files": ("notes.txt", b"test content")},
            data={"thread_id": "../../../../../../tmp/escape"},
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 400


class TestTaskEndpoint:
    """POST /api/task integration tests."""

    def test_run_task_returns_thread_id(self, client):
        """POST /api/task with a query returns thread_id."""
        # The run_deep_agent is stubbed via sys.modules above
        response = client.post(
            "/api/task",
            json={"query": "Test query"},
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert "thread_id" in data

    def test_rejects_path_traversal_thread_id(self, client):
        response = client.post(
            "/api/task",
            json={"query": "Test query", "thread_id": "../../../../../../tmp/escape"},
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 422
