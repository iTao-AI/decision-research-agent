from datetime import datetime, timezone

from agent.token_tracking import TokenUsageData


class TestTelemetryRecord:
    def test_create_success_record(self):
        from agent.telemetry import TelemetryRecord

        record = TelemetryRecord(
            thread_id="thread-1",
            agent_name="main",
            tool_name="tavily_search",
            duration_ms=120.5,
            status="success",
        )

        assert record.thread_id == "thread-1"
        assert record.agent_name == "main"
        assert record.tool_name == "tavily_search"
        assert record.duration_ms == 120.5
        assert record.status == "success"
        assert record.error is None
        assert isinstance(record.timestamp, datetime)

    def test_create_error_record(self):
        from agent.telemetry import TelemetryRecord

        record = TelemetryRecord(
            thread_id="thread-2",
            agent_name="main",
            tool_name="mysql_query",
            duration_ms=5000.0,
            status="error",
            error="Connection timeout after 5s",
        )

        assert record.thread_id == "thread-2"
        assert record.status == "error"
        assert record.error == "execution_failed"

    def test_record_discards_raw_error_at_construction(self):
        from agent.telemetry import TelemetryRecord

        record = TelemetryRecord(
            thread_id="thread-a",
            run_id="run-a",
            segment_id="run-a-seg-000",
            agent_name="raw agent OBS_MARKER",
            tool_name="raw tool OBS_MARKER",
            duration_ms=1.0,
            status="error",
            error="SELECT secret FROM private_table OBS_MARKER",
            error_type="RuntimeError",
        )
        assert record.schema == "dra.telemetry-record.v1"
        assert record.agent_name == "unknown_agent"
        assert record.tool_name == "unknown_tool"
        assert record.error == "execution_failed"
        assert record.error_type == "RuntimeError"
        assert "OBS_MARKER" not in vars(record).values()

    def test_record_preserves_exact_timestamp_and_valid_token_usage(self):
        from agent.telemetry import TelemetryRecord

        timestamp = datetime(2026, 7, 26, 1, 2, 3, tzinfo=timezone.utc)
        usage = TokenUsageData(
            prompt_tokens=2,
            completion_tokens=3,
            model="fixture",
            cost=0.0,
        )
        record = TelemetryRecord(
            thread_id="thread-a",
            run_id="run-a",
            segment_id="run-a-seg-000",
            agent_name="main",
            tool_name="tavily_search",
            duration_ms=1.0,
            status="success",
            token_usage=usage,
            timestamp=timestamp,
        )
        assert record.timestamp is timestamp
        assert record.token_usage is usage

    def test_invalid_direct_timestamp_and_token_usage_use_sentinels(self):
        from agent.telemetry import TelemetryRecord

        record = TelemetryRecord(
            thread_id=object(),
            agent_name="main",
            tool_name="tavily_search",
            duration_ms=10**100_000,
            status="error",
            error=None,
            error_type="RuntimeError",
            token_usage=object(),
            timestamp=object(),
        )
        assert record.thread_id is None
        assert record.timestamp == datetime(1970, 1, 1, tzinfo=timezone.utc)
        assert record.token_usage is None
        assert (record.status, record.error, record.error_type) == (
            "error",
            "execution_failed",
            None,
        )


class TestTelemetryCollector:
    def _get_collector(self):
        from agent.telemetry import TelemetryCollector
        return TelemetryCollector()

    def test_record_and_query(self):
        collector = self._get_collector()
        from agent.telemetry import TelemetryRecord

        collector.record(TelemetryRecord(
            thread_id="t1", agent_name="main", tool_name="tavily_search",
            duration_ms=10.0, status="success",
        ))
        collector.record(TelemetryRecord(
            thread_id="t1", agent_name="main", tool_name="mysql_query",
            duration_ms=20.0, status="success",
        ))

        results = collector.get_by_thread("t1")
        assert len(results) == 2
        assert results[0].tool_name == "tavily_search"
        assert results[1].tool_name == "mysql_query"

    def test_collector_rejects_telemetry_record_subclass(self):
        from agent.telemetry import TelemetryCollector, TelemetryRecord

        class BypassRecord(TelemetryRecord):
            pass

        collector = TelemetryCollector()
        collector.record(
            BypassRecord(
                thread_id="thread-a",
                agent_name="main",
                tool_name="tavily_search",
                duration_ms=1.0,
                status="success",
            )
        )
        assert collector.get_by_thread("thread-a") == []

    def test_collector_reprojects_mutation_without_refreshing_timestamp(self):
        from agent.telemetry import TelemetryCollector, TelemetryRecord

        original_timestamp = datetime(2026, 7, 26, tzinfo=timezone.utc)
        record = TelemetryRecord(
            thread_id="thread-a",
            run_id="run-a",
            agent_name="main",
            tool_name="tavily_search",
            duration_ms=1.0,
            status="success",
            timestamp=original_timestamp,
        )
        object.__setattr__(record, "error", "OBS_MARKER")
        object.__setattr__(record, "error_type", "RuntimeError")
        collector = TelemetryCollector()
        collector.record(record)
        stored = collector.get_by_run("run-a")[0]
        assert stored is not record
        assert stored.timestamp is original_timestamp
        assert (stored.status, stored.error, stored.error_type) == (
            "error",
            "execution_failed",
            "RuntimeError",
        )
        assert "OBS_MARKER" not in repr(vars(stored))

    def test_query_nonexistent_thread(self):
        collector = self._get_collector()
        results = collector.get_by_thread("nonexistent")
        assert results == []

    def test_clear_thread(self):
        collector = self._get_collector()
        from agent.telemetry import TelemetryRecord

        collector.record(TelemetryRecord(
            thread_id="t1", agent_name="main", tool_name="tavily_search",
            duration_ms=5.0, status="success",
        ))
        assert len(collector.get_by_thread("t1")) == 1

        collector.clear_thread("t1")
        assert collector.get_by_thread("t1") == []

    def test_clear_nonexistent_thread(self):
        collector = self._get_collector()
        # Should not raise
        collector.clear_thread("does-not-exist")
        assert collector.get_by_thread("does-not-exist") == []

    def test_clear_doesnt_affect_other_threads(self):
        collector = self._get_collector()
        from agent.telemetry import TelemetryRecord

        collector.record(TelemetryRecord(
            thread_id="t1", agent_name="main", tool_name="tavily_search",
            duration_ms=1.0, status="success",
        ))
        collector.record(TelemetryRecord(
            thread_id="t2", agent_name="main", tool_name="mysql_query",
            duration_ms=2.0, status="success",
        ))

        collector.clear_thread("t1")

        assert collector.get_by_thread("t1") == []
        assert len(collector.get_by_thread("t2")) == 1
        assert collector.get_by_thread("t2")[0].tool_name == "mysql_query"


class TestCapacityControl:
    def test_eviction_at_500_limit(self):
        from agent.telemetry import TelemetryCollector, TelemetryRecord

        collector = TelemetryCollector()

        first_timestamp = datetime(2026, 7, 26, tzinfo=timezone.utc)
        for i in range(501):
            collector.record(TelemetryRecord(
                thread_id="cap-test",
                agent_name="main",
                tool_name="tavily_search",
                duration_ms=float(i),
                status="success",
                timestamp=first_timestamp.replace(microsecond=i),
            ))

        results = collector.get_by_thread("cap-test")
        assert len(results) == 500
        assert results[0].timestamp == first_timestamp.replace(microsecond=1)
        assert results[-1].timestamp == first_timestamp.replace(microsecond=500)


class TestGlobalCollector:
    def test_global_collector_exists(self):
        from agent.telemetry import collector
        assert collector is not None

    def test_global_collector_has_methods(self):
        from agent.telemetry import collector
        assert hasattr(collector, "record")
        assert hasattr(collector, "get_by_thread")
