"""Closed observation behavior for ToolMonitor."""

from api.monitor import ToolMonitor, sanitize_args


def test_sanitize_args_is_closed_descriptor_compatibility_alias():
    marker = {"query": "OBS_MARKER", "nested": {"secret": "OBS_MARKER"}}
    assert sanitize_args(marker) == {
        "present": True,
        "kind": "mapping",
        "top_level_item_count": 2,
        "count_capped": False,
    }


def test_pending_inventory_initializes_and_snapshots_under_lock():
    monitor = ToolMonitor()
    with monitor._pending_lock:
        with monitor._pending_lock:
            assert monitor._pending_snapshot() == ((), ())
    assert isinstance(monitor._pending_tasks, set)
    assert isinstance(monitor._pending_futures, set)


def test_console_failure_isolated_and_start_state_cleaned(monkeypatch):
    import builtins
    import api.monitor as monitor_module
    from api.context import (
        reset_execution_context,
        set_run_context,
        set_segment_context,
        set_thread_context,
    )

    def broken_print(*_args, **_kwargs):
        raise RuntimeError("OBS_MARKER")

    monitor = monitor_module.monitor
    monitor.websocket_manager = None
    monkeypatch.setattr(builtins, "print", broken_print)
    thread_token = set_thread_context("thread-console")
    run_token = set_run_context("run-console")
    segment_token = set_segment_context("run-console-seg-000")
    try:
        monitor.report_start("tavily_search", {"query": "OBS_MARKER"})
        monitor.report_end("tavily_search", result="exact-result")
        assert ("run-console", "tavily_search") not in monitor._start_times
    finally:
        reset_execution_context(run_token, thread_token, segment_token)


def test_reporters_keep_raw_values_only_until_projector_boundary():
    captured = []

    class CapturingMonitor(ToolMonitor):
        def _emit(
            self,
            event_type,
            message,
            data=None,
            thread_id=None,
            run_id=None,
            segment_id=None,
        ):
            captured.append(
                (
                    event_type,
                    data,
                    thread_id,
                    run_id,
                    segment_id,
                )
            )

    monitor = CapturingMonitor()
    marker = {"query": "OBS_MARKER"}
    monitor.report_start("tavily_search", marker)
    monitor.report_end(
        "tavily_search",
        result=marker,
        error="timeout",
        error_type="TimeoutError",
    )
    monitor.report_task_finalized(
        thread_id="thread-final",
        status="failed",
        fallback_used=False,
        output_path="/private/OBS_MARKER",
        error_message="OBS_MARKER",
    )
    assert captured[0][1]["args"] is marker
    assert captured[1][1]["result"] is marker
    assert captured[1][1]["error"] == "timeout"
    assert captured[1][1]["error_type"] == "TimeoutError"
    assert captured[2][1]["error"] == "OBS_MARKER"
    assert captured[2][2] == "thread-final"


def test_monitor_docstrings_use_registered_aliases_and_descriptor_semantics():
    assert "tavily_search" in (ToolMonitor.__doc__ or "")
    assert "report_running" not in (ToolMonitor.__doc__ or "")
    assert "descriptor" in (sanitize_args.__doc__ or "").lower()


def test_reporting_does_not_mutate_model_visible_values():
    monitor = ToolMonitor()
    values = ["text", {"key": "value"}, b"raw-bytes"]
    for value in values:
        original = value.copy() if type(value) is dict else value
        monitor.report_end("tavily_search", result=value)
        assert value == original
