"""Integration tests: monitor.report_start + report_end -> TelemetryRecord in collector."""
import time
from unittest.mock import patch

import pytest

from api.monitor import ToolMonitor
from agent.telemetry import collector, TelemetryRecord
from api.context import _thread_id_ctx, set_thread_context


class TestMonitorToCollectorIntegration:
    """Test that monitor report_start/report_end stores TelemetryRecord."""

    def setup_method(self):
        """Clear collector and reset monitor state before each test."""
        collector.clear_thread("integration-thread-1")
        collector.clear_thread("integration-thread-2")

    def teardown_method(self):
        """Clean up after each test."""
        collector.clear_thread("integration-thread-1")
        collector.clear_thread("integration-thread-2")
        _thread_id_ctx.set(None)

    def _create_monitor_with_no_websocket(self):
        """Create a fresh ToolMonitor with no websocket_manager."""
        m = ToolMonitor()
        m.websocket_manager = None
        m._start_times = {}
        return m

    def test_report_start_end_creates_telemetry_record(self):
        """Calling report_start + report_end results in a TelemetryRecord in collector."""
        monitor = self._create_monitor_with_no_websocket()

        # Set thread context
        set_thread_context("integration-thread-1")

        # Suppress _emit console output
        with patch.object(monitor, '_emit'):
            monitor.report_start("tavily_search", {"query": "test"})
            time.sleep(0.01)  # Ensure non-zero duration
            monitor.report_end("tavily_search", result={"hits": []})

        records = collector.get_by_thread("integration-thread-1")
        assert len(records) == 1
        record = records[0]

        assert isinstance(record, TelemetryRecord)
        assert record.thread_id == "integration-thread-1"
        assert record.tool_name == "tavily_search"
        assert record.status == "success"
        assert record.error is None
        assert record.duration_ms >= 0.0

    def test_record_has_correct_duration(self):
        """Verify duration_ms reflects actual elapsed time."""
        monitor = self._create_monitor_with_no_websocket()
        set_thread_context("integration-thread-1")

        with patch.object(monitor, '_emit'):
            monitor.report_start("slow_tool")
            time.sleep(0.05)  # Sleep 50ms
            monitor.report_end("slow_tool")

        records = collector.get_by_thread("integration-thread-1")
        assert len(records) == 1
        # Should be approximately 50ms, allow some tolerance
        assert records[0].duration_ms >= 40.0
        assert records[0].duration_ms < 200.0

    def test_record_has_error_status_on_error(self):
        """When report_end receives an error, status should be 'error'."""
        monitor = self._create_monitor_with_no_websocket()
        set_thread_context("integration-thread-1")

        with patch.object(monitor, '_emit'):
            monitor.report_start("failing_tool")
            monitor.report_end("failing_tool", error="Something went wrong")

        records = collector.get_by_thread("integration-thread-1")
        assert len(records) == 1
        assert records[0].status == "error"
        assert records[0].error == "Something went wrong"

    def test_thread_id_isolation(self):
        """Two different thread_ids don't mix their telemetry records."""
        monitor = self._create_monitor_with_no_websocket()

        # Thread 1
        set_thread_context("integration-thread-1")
        with patch.object(monitor, '_emit'):
            monitor.report_start("tool_a")
            monitor.report_end("tool_a")

        # Thread 2
        set_thread_context("integration-thread-2")
        with patch.object(monitor, '_emit'):
            monitor.report_start("tool_b")
            monitor.report_end("tool_b")

        records_t1 = collector.get_by_thread("integration-thread-1")
        records_t2 = collector.get_by_thread("integration-thread-2")

        assert len(records_t1) == 1
        assert records_t1[0].tool_name == "tool_a"
        assert records_t1[0].thread_id == "integration-thread-1"

        assert len(records_t2) == 1
        assert records_t2[0].tool_name == "tool_b"
        assert records_t2[0].thread_id == "integration-thread-2"

        # Verify no cross-contamination
        t1_tool_names = {r.tool_name for r in records_t1}
        t2_tool_names = {r.tool_name for r in records_t2}
        assert t1_tool_names.isdisjoint(t2_tool_names)


class TestCollectorClearIntegration:
    """Test that clearing a thread works correctly with integration flow."""

    def setup_method(self):
        collector.clear_thread("clear-test-thread")

    def teardown_method(self):
        collector.clear_thread("clear-test-thread")
        _thread_id_ctx.set(None)

    def test_clear_thread_removes_records(self):
        """After clear_thread, get_by_thread returns empty."""
        monitor = ToolMonitor()
        monitor.websocket_manager = None
        monitor._start_times = {}

        set_thread_context("clear-test-thread")
        with patch.object(monitor, '_emit'):
            monitor.report_start("test_tool")
            monitor.report_end("test_tool")

        assert len(collector.get_by_thread("clear-test-thread")) == 1

        collector.clear_thread("clear-test-thread")
        assert collector.get_by_thread("clear-test-thread") == []
