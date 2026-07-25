import asyncio
import builtins
import gc
import json
from pathlib import Path
import threading
import uuid
import warnings

from langchain_core.messages import AIMessage
import pytest


async def _settle_monitor_pending(monitor):
    tasks, futures = monitor._pending_snapshot()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    if futures:
        await asyncio.gather(
            *(asyncio.wrap_future(future) for future in futures),
            return_exceptions=True,
        )
    assert monitor._pending_snapshot() == ((), ())


class HostileIdentity:
    def __bool__(self):
        raise AssertionError("hostile bool called")

    def __str__(self):
        raise AssertionError("hostile str called")

    def __repr__(self):
        raise AssertionError("hostile repr called")


@pytest.mark.asyncio
async def test_same_marker_is_absent_from_every_observation_sink(
    monkeypatch,
    capsys,
):
    import api.monitor as monitor_module
    from agent.telemetry import collector
    from api.context import (
        reset_execution_context,
        set_run_context,
        set_segment_context,
        set_thread_context,
    )

    marker = "OBS_MARKER_SQL_RAGFLOW_PATH_" + "x" * 4096
    websocket_snapshots = []
    websocket_ids = []
    stream_payloads = []
    stream_ids = []
    loop_errors = []
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(
        lambda _loop, context: loop_errors.append(context)
    )

    class FakeManager:
        def get_loop(self):
            return asyncio.get_running_loop()

        async def send_to_run(self, payload, run_id):
            websocket_ids.append((id(payload), id(payload["data"])))
            websocket_snapshots.append(
                json.loads(json.dumps(payload, allow_nan=False))
            )
            payload["data"]["tool_name"] = "mutated_by_websocket"

    class Runtime:
        def stream_writer(self, payload):
            stream_payloads.append(payload)
            stream_ids.append((id(payload), id(payload["data"])))

    monitor = monitor_module.monitor
    await _settle_monitor_pending(monitor)
    monkeypatch.setattr(monitor, "websocket_manager", FakeManager())
    monkeypatch.setattr(builtins, "runtime", Runtime(), raising=False)
    thread_token = set_thread_context("shared-thread")
    run_token = set_run_context("run-marker")
    segment_token = set_segment_context("run-marker-seg-000")
    try:
        for _ in range(2):
            value = {
                "query": marker,
                "nested": {"secret": marker},
                "rows": [marker],
                "answer": marker,
                "output_path": "/private/" + marker,
            }
            monitor.report_start("tavily_search", value)
            monitor.report_end(
                "tavily_search",
                result=value,
                error=marker,
                error_type="RuntimeError",
            )
            assert value["query"] == marker
        await _settle_monitor_pending(monitor)
        records = collector.get_by_run("run-marker")
        captured = capsys.readouterr()
        serialized = json.dumps(
            {
                "websocket": websocket_snapshots,
                "stream": stream_payloads,
                "telemetry": [vars(record) for record in records],
                "stdout": captured.out,
                "stderr": captured.err,
            },
            default=lambda _value: "<opaque>",
            allow_nan=False,
        )
        assert marker not in serialized
        assert websocket_snapshots == stream_payloads
        assert websocket_ids != stream_ids
        assert all(
            web_outer != stream_outer and web_data != stream_data
            for (web_outer, web_data), (stream_outer, stream_data) in zip(
                websocket_ids,
                stream_ids,
                strict=True,
            )
        )
        assert all(
            item["data"].get("tool_name") != "mutated_by_websocket"
            for item in stream_payloads
        )
        assert not loop_errors
    finally:
        reset_execution_context(run_token, thread_token, segment_token)
        collector.clear_run("run-marker")
        await _settle_monitor_pending(monitor)
        loop.set_exception_handler(previous_handler)


@pytest.mark.asyncio
async def test_current_loop_websocket_failure_is_consumed(
    monkeypatch,
    capsys,
):
    import api.monitor as monitor_module

    gate = asyncio.Event()
    started = asyncio.Event()
    stream_payloads = []
    loop_errors = []
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(
        lambda _loop, context: loop_errors.append(context)
    )

    class FakeManager:
        def get_loop(self):
            return loop

        async def send_to_run(self, payload, run_id):
            started.set()
            await gate.wait()
            raise RuntimeError("OBS_MARKER")

    class Runtime:
        def stream_writer(self, payload):
            stream_payloads.append(payload)

    monitor = monitor_module.monitor
    await _settle_monitor_pending(monitor)
    monkeypatch.setattr(monitor, "websocket_manager", FakeManager())
    monkeypatch.setattr(builtins, "runtime", Runtime(), raising=False)
    try:
        monitor._emit(
            "error",
            "raw OBS_MARKER",
            {"error": "OBS_MARKER"},
            thread_id="thread-a",
            run_id="run-a",
            segment_id="run-a-seg-000",
        )
        await started.wait()
        tasks, futures = monitor._pending_snapshot()
        assert len(tasks) == 1
        assert futures == ()
        gate.set()
        await _settle_monitor_pending(monitor)
        captured = capsys.readouterr()
        assert stream_payloads
        assert "OBS_MARKER" not in captured.out + captured.err
        assert not loop_errors
    finally:
        gate.set()
        await _settle_monitor_pending(monitor)
        loop.set_exception_handler(previous_handler)


@pytest.mark.asyncio
async def test_manager_loop_websocket_future_is_consumed(
    monkeypatch,
    capsys,
):
    import api.monitor as monitor_module

    manager_loop = asyncio.new_event_loop()
    loop_ready = threading.Event()
    release = threading.Event()
    started = threading.Event()
    loop_errors = []

    def run_loop():
        asyncio.set_event_loop(manager_loop)
        manager_loop.set_exception_handler(
            lambda _loop, context: loop_errors.append(context)
        )
        loop_ready.set()
        manager_loop.run_forever()

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    loop_ready.wait(timeout=2)

    class FakeManager:
        def get_loop(self):
            return manager_loop

        async def send_to_run(self, payload, run_id):
            started.set()
            while not release.is_set():
                await asyncio.sleep(0.001)
            raise RuntimeError("OBS_MARKER")

    monitor = monitor_module.monitor
    await _settle_monitor_pending(monitor)
    monkeypatch.setattr(monitor, "websocket_manager", FakeManager())
    try:
        monitor._emit(
            "error",
            "raw OBS_MARKER",
            {"error": "OBS_MARKER"},
            thread_id="thread-a",
            run_id="run-a",
            segment_id="run-a-seg-000",
        )
        assert started.wait(timeout=2)
        tasks, futures = monitor._pending_snapshot()
        assert tasks == ()
        assert len(futures) == 1
        release.set()
        await _settle_monitor_pending(monitor)
        captured = capsys.readouterr()
        assert "OBS_MARKER" not in captured.out + captured.err
        assert not loop_errors
    finally:
        release.set()
        await _settle_monitor_pending(monitor)
        manager_loop.call_soon_threadsafe(manager_loop.stop)
        thread.join(timeout=2)
        manager_loop.close()


@pytest.mark.asyncio
async def test_emit_never_uses_hostile_truthiness_or_raw_route_ids(
    monkeypatch,
):
    import api.monitor as monitor_module

    routed = []

    class FakeManager:
        def get_loop(self):
            return asyncio.get_running_loop()

        async def send_to_run(self, payload, run_id):
            routed.append(("run", run_id))

        async def send_to_thread(self, payload, thread_id):
            routed.append(("thread", thread_id))

    monitor = monitor_module.monitor
    await _settle_monitor_pending(monitor)
    monkeypatch.setattr(monitor, "websocket_manager", FakeManager())
    monitor._emit(
        "error",
        "ignored",
        {"error": "execution_failed"},
        thread_id=HostileIdentity(),
        run_id=HostileIdentity(),
        segment_id=HostileIdentity(),
    )
    monitor._emit(
        "error",
        "ignored",
        {"error": "execution_failed"},
        thread_id="thread-valid",
        run_id="illegal/run",
        segment_id="illegal segment",
    )
    await _settle_monitor_pending(monitor)
    assert routed == [("thread", "thread-valid")]


@pytest.mark.asyncio
async def test_valid_generated_identities_route_exactly(monkeypatch):
    import api.monitor as monitor_module

    routed = []
    run_id = f"run_{uuid.uuid4().hex}"
    segment_id = f"{run_id}_seg_000"

    class FakeManager:
        def get_loop(self):
            return asyncio.get_running_loop()

        async def send_to_run(self, payload, routed_run_id):
            routed.append((routed_run_id, payload))

    monitor = monitor_module.monitor
    await _settle_monitor_pending(monitor)
    monkeypatch.setattr(monitor, "websocket_manager", FakeManager())
    monitor._emit(
        "error",
        "ignored",
        {"error": "execution_failed"},
        thread_id="thread-valid",
        run_id=run_id,
        segment_id=segment_id,
    )
    await _settle_monitor_pending(monitor)
    assert routed[0][0] == run_id
    assert routed[0][1]["thread_id"] == "thread-valid"
    assert routed[0][1]["run_id"] == run_id
    assert routed[0][1]["segment_id"] == segment_id


@pytest.mark.asyncio
async def test_current_loop_scheduling_failure_closes_protected_coroutine(
    monkeypatch,
    capsys,
):
    import api.monitor as monitor_module

    loop = asyncio.get_running_loop()

    class FakeManager:
        def get_loop(self):
            return loop

        async def send_to_run(self, payload, run_id):
            raise AssertionError("send must not start")

    monitor = monitor_module.monitor
    await _settle_monitor_pending(monitor)
    monkeypatch.setattr(monitor, "websocket_manager", FakeManager())
    original_create_task = loop.create_task

    def fail_create_task(_coroutine):
        raise RuntimeError("OBS_MARKER")

    with warnings.catch_warnings(record=True) as captured_warnings:
        warnings.simplefilter("always")
        monkeypatch.setattr(loop, "create_task", fail_create_task)
        monitor._emit(
            "error",
            "ignored",
            {"error": "execution_failed"},
            thread_id="thread-a",
            run_id="run-a",
        )
        monkeypatch.setattr(loop, "create_task", original_create_task)
        gc.collect()
    assert monitor._pending_snapshot() == ((), ())
    output = capsys.readouterr()
    assert "OBS_MARKER" not in output.out + output.err
    assert not any(
        "was never awaited" in str(item.message)
        for item in captured_warnings
    )


@pytest.mark.asyncio
async def test_manager_loop_scheduling_failure_closes_protected_coroutine(
    monkeypatch,
    capsys,
):
    import api.monitor as monitor_module

    loop = asyncio.get_running_loop()

    class FakeManager:
        def get_loop(self):
            return loop

        async def send_to_run(self, payload, run_id):
            raise AssertionError("send must not start")

    monitor = monitor_module.monitor
    await _settle_monitor_pending(monitor)
    monkeypatch.setattr(monitor, "websocket_manager", FakeManager())
    original_get_running_loop = asyncio.get_running_loop
    original_schedule = asyncio.run_coroutine_threadsafe

    def no_current_loop():
        raise RuntimeError

    def fail_schedule(_coroutine, _loop):
        raise RuntimeError("OBS_MARKER")

    with warnings.catch_warnings(record=True) as captured_warnings:
        warnings.simplefilter("always")
        monkeypatch.setattr(asyncio, "get_running_loop", no_current_loop)
        monkeypatch.setattr(
            asyncio,
            "run_coroutine_threadsafe",
            fail_schedule,
        )
        monitor._emit(
            "error",
            "ignored",
            {"error": "execution_failed"},
            thread_id="thread-a",
            run_id="run-a",
        )
        monkeypatch.setattr(
            asyncio,
            "get_running_loop",
            original_get_running_loop,
        )
        monkeypatch.setattr(
            asyncio,
            "run_coroutine_threadsafe",
            original_schedule,
        )
        gc.collect()
    assert monitor._pending_snapshot() == ((), ())
    output = capsys.readouterr()
    assert "OBS_MARKER" not in output.out + output.err
    assert not any(
        "was never awaited" in str(item.message)
        for item in captured_warnings
    )


@pytest.mark.asyncio
async def test_observation_failures_do_not_change_exact_returns_or_canonical_result(
    monkeypatch,
    tmp_path,
):
    import api.monitor as monitor_module
    from agent.run_result import AgentRunAccumulator, process_stream_chunk

    monitor = monitor_module.monitor
    await _settle_monitor_pending(monitor)
    monkeypatch.setattr(monitor, "websocket_manager", None)
    for value in ("text", {"key": "value"}, b"raw-bytes"):
        original = value.copy() if type(value) is dict else value
        monitor.report_end("tavily_search", result=value)
        assert value == original

    accumulator = AgentRunAccumulator(
        thread_id="thread-result",
        query="query",
        session_dir=Path(tmp_path),
    )
    process_stream_chunk(
        {"agent": {"messages": [AIMessage(content="canonical result")]}},
        accumulator,
        monitor,
    )
    outcome = accumulator.to_outcome()
    assert outcome.last_agent_text == "canonical result"
    assert outcome.evidence_entries == []
