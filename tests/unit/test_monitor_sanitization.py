"""Tests for ToolMonitor sanitize_args and telemetry integration (Phase B)."""

import time
from unittest.mock import patch, MagicMock, call

import pytest

from api.monitor import ToolMonitor, sanitize_args
from agent.telemetry import collector, TelemetryRecord


# ── sanitize_args tests ──────────────────────────────────────────────

class TestSanitizeArgs:
    """Test the sanitize_args function."""

    def test_sensitive_api_key_redacted(self):
        """api_key field should be redacted."""
        result = sanitize_args({"api_key": "sk-12345", "query": "hello"})
        assert result["api_key"] == "***REDACTED***"
        assert result["query"] == "hello"

    def test_sensitive_password_redacted(self):
        """password field should be redacted."""
        result = sanitize_args({"password": "supersecret", "user": "alice"})
        assert result["password"] == "***REDACTED***"
        assert result["user"] == "alice"

    def test_sensitive_token_redacted(self):
        """token field should be redacted."""
        result = sanitize_args({"token": "abc-token", "id": 42})
        assert result["token"] == "***REDACTED***"
        assert result["id"] == 42

    def test_sensitive_secret_redacted(self):
        """secret field should be redacted."""
        result = sanitize_args({"secret": "my-secret-value"})
        assert result["secret"] == "***REDACTED***"

    def test_sensitive_pattern_matching_exact_and_suffix(self):
        """Fields that exactly match or end with sensitive suffixes should be redacted."""
        result = sanitize_args({
            "my_api_key": "key1",       # ends with _key
            "auth_token": "tok1",       # exact match
            "client_secret": "sec1",    # exact match
            "db_password_hash": "hash1", # does NOT match (no _hash suffix, no exact match)
        })
        assert result["my_api_key"] == "***REDACTED***"
        assert result["auth_token"] == "***REDACTED***"
        assert result["client_secret"] == "***REDACTED***"
        # db_password_hash is intentionally NOT redacted — the new pattern
        # list avoids false positives like "bucket_key", "monkey", etc.
        assert result["db_password_hash"] == "hash1"

    def test_sensitive_key_pattern_case_insensitive(self):
        """Pattern matching should be case-insensitive."""
        result = sanitize_args({"API_KEY": "val", "Password": "val", "Token": "val"})
        assert result["API_KEY"] == "***REDACTED***"
        assert result["Password"] == "***REDACTED***"
        assert result["Token"] == "***REDACTED***"

    def test_long_string_truncated(self):
        """Strings longer than 200 chars should be truncated."""
        long_val = "x" * 500
        result = sanitize_args({"description": long_val})
        assert len(result["description"]) < 500
        assert result["description"].startswith("x" * 200)
        assert "... (truncated, 500 chars total)" in result["description"]

    def test_non_string_values_not_truncated(self):
        """Non-string values (int, bool) should pass through unchanged."""
        result = sanitize_args({"count": 999, "flag": True, "value": 3.14})
        assert result["count"] == 999
        assert result["flag"] is True
        assert result["value"] == 3.14

    def test_none_returns_none(self):
        """sanitize_args(None) should return None."""
        assert sanitize_args(None) is None

    def test_empty_dict_returns_empty_dict(self):
        """sanitize_args({}) should return {}."""
        assert sanitize_args({}) == {}


# ── ToolMonitor integration tests ────────────────────────────────────

class TestToolMonitorSanitization:
    """Test that ToolMonitor methods apply sanitize_args before emitting."""

    def _make_monitor_with_captured_emit(self):
        """Create a ToolMonitor subclass that captures _emit calls."""
        captured = []

        class CapturingMonitor(ToolMonitor):
            def _emit(self, event_type, message, data=None, thread_id=None):
                captured.append((event_type, message, data, thread_id))

        mon = CapturingMonitor()
        return mon, captured

    def test_report_start_emits_sanitized_args(self):
        """report_start should emit sanitized args (sensitive fields redacted)."""
        mon, captured = self._make_monitor_with_captured_emit()
        mon.report_start("search_tool", {"api_key": "sk-secret", "query": "hello world"})

        assert len(captured) == 1
        event_type, message, data, _ = captured[0]
        assert event_type == "tool_start"
        assert data["args"]["api_key"] == "***REDACTED***"
        assert data["args"]["query"] == "hello world"

    def test_report_assistant_emits_sanitized_args(self):
        """report_assistant should emit sanitized args."""
        mon, captured = self._make_monitor_with_captured_emit()
        mon.report_assistant("db_agent", {"password": "secret123", "database": "main"})

        assert len(captured) == 1
        data = captured[0][2]
        assert data["args"]["password"] == "***REDACTED***"
        assert data["args"]["database"] == "main"

    def test_report_task_result_emits_sanitized_args(self):
        """report_task_result should sanitize its result field."""
        mon, captured = self._make_monitor_with_captured_emit()
        # result is a dict with a "result" key containing a long string
        long_result = "x" * 500
        mon.report_task_result(long_result)

        assert len(captured) == 1
        data = captured[0][2]
        # The result value should be truncated since it's a long string
        emitted_result = data["result"]
        assert len(emitted_result) < 500
        assert "... (truncated, 500 chars total)" in emitted_result

    def test_report_end_generates_telemetry_record(self):
        """report_end should record a TelemetryRecord in the collector."""
        mon, captured = self._make_monitor_with_captured_emit()

        # Simulate a tool lifecycle
        mon.report_start("search_tool", {"query": "test"})
        time.sleep(0.05)  # Small delay to ensure non-zero duration
        mon.report_end("search_tool", result={"hits": 10})

        # Check that _emit was called for both start and end
        assert len(captured) == 2
        assert captured[0][0] == "tool_start"
        assert captured[1][0] == "tool_end"

        # Check telemetry record was recorded
        thread_id = "default"  # fallback when no context is set
        records = collector.get_by_thread(thread_id)
        # Find the record for this tool
        matching = [r for r in records if r.tool_name == "search_tool"]
        assert len(matching) >= 1
        record = matching[-1]
        assert record.status == "success"
        assert record.duration_ms >= 0
        assert record.agent_name == "main"

    def test_report_end_with_error_generates_failure_record(self):
        """report_end with error should record a TelemetryRecord with status='error'."""
        mon, captured = self._make_monitor_with_captured_emit()

        mon.report_start("db_tool", {"query": "SELECT 1"})
        time.sleep(0.02)
        mon.report_end("db_tool", error="connection refused")

        thread_id = "default"
        records = collector.get_by_thread(thread_id)
        matching = [r for r in records if r.tool_name == "db_tool"]
        assert len(matching) >= 1
        record = matching[-1]
        assert record.status == "error"
        assert record.error == "connection refused"

    def test_report_tool_backward_compatible_alias(self):
        """report_tool should still work as an alias for report_start."""
        mon, captured = self._make_monitor_with_captured_emit()
        # Old API: report_tool(tool_name, args)
        mon.report_tool("search_tool", {"api_key": "secret", "query": "test"})

        assert len(captured) == 1
        event_type, message, data, _ = captured[0]
        assert event_type == "tool_start"
        assert data["args"]["api_key"] == "***REDACTED***"

    def test_report_task_finalized_emits_terminal_payload(self):
        """task_finalized includes status and fallback metadata."""
        mon, captured = self._make_monitor_with_captured_emit()

        mon.report_task_finalized(
            thread_id="thread-001",
            status="completed_with_fallback",
            fallback_used=True,
            output_path="/tmp/output/session_thread-001/fallback_report.md",
            error_message=None,
        )

        assert len(captured) == 1
        event_type, message, data, routed_thread_id = captured[0]
        assert event_type == "task_finalized"
        assert message == "任务状态已完成: completed_with_fallback"
        assert routed_thread_id == "thread-001"
        assert data == {
            "thread_id": "thread-001",
            "status": "completed_with_fallback",
            "fallback_used": True,
            "output_path": "/tmp/output/session_thread-001/fallback_report.md",
            "error_message": None,
        }
