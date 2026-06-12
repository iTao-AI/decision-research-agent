import asyncio
import os
from pathlib import Path
import subprocess
import sys
import textwrap

from fastapi.testclient import TestClient
import pytest

from api.server import app


AUTH_HEADERS = {"X-API-Key": "test-integration-key"}


def test_same_thread_can_schedule_two_run_scoped_requests(tmp_path, monkeypatch):
    import api.server as server

    monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    scheduled = []

    def capture_task(coroutine, task_id, **kwargs):
        scheduled.append((coroutine, task_id))

    monkeypatch.setattr(server, "create_tracked_task", capture_task)
    client = TestClient(app)

    first = client.post(
        "/api/runs",
        json={"query": "first", "thread_id": "shared-thread"},
        headers=AUTH_HEADERS,
    )
    second = client.post(
        "/api/runs",
        json={"query": "second", "thread_id": "shared-thread"},
        headers=AUTH_HEADERS,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["run_id"] != second.json()["run_id"]
    assert [task_id for _, task_id in scheduled] == [
        first.json()["run_id"],
        second.json()["run_id"],
    ]

    for coroutine, _ in scheduled:
        coroutine.close()


def test_telemetry_api_isolates_two_runs_in_same_thread():
    from agent.telemetry import TelemetryRecord, collector

    os.environ["API_SECRET"] = "test-integration-key"
    collector.record(
        TelemetryRecord(
            thread_id="shared-thread",
            run_id="run-a",
            segment_id="run-a-seg-000",
            agent_name="main",
            tool_name="search-a",
            duration_ms=1,
            status="success",
        )
    )
    collector.record(
        TelemetryRecord(
            thread_id="shared-thread",
            run_id="run-b",
            segment_id="run-b-seg-000",
            agent_name="main",
            tool_name="search-b",
            duration_ms=2,
            status="success",
        )
    )
    client = TestClient(app)

    run_a = client.get("/api/telemetry/runs/run-a", headers=AUTH_HEADERS)
    run_b = client.get("/api/telemetry/runs/run-b", headers=AUTH_HEADERS)

    assert [item["tool_name"] for item in run_a.json()] == ["search-a"]
    assert [item["tool_name"] for item in run_b.json()] == ["search-b"]
    assert run_a.json()[0]["thread_id"] == run_b.json()[0]["thread_id"]
    assert run_a.json()[0]["run_id"] != run_b.json()[0]["run_id"]

    collector.clear_run("run-a")
    collector.clear_run("run-b")


def test_token_usage_api_isolates_two_runs_in_same_thread():
    from agent.token_tracking import TokenUsageData, token_collector

    os.environ["API_SECRET"] = "test-integration-key"
    token_collector.record("run-a", TokenUsageData(prompt_tokens=10, completion_tokens=1))
    token_collector.record("run-b", TokenUsageData(prompt_tokens=20, completion_tokens=2))
    client = TestClient(app)

    run_a = client.get("/api/token-usage/runs/run-a", headers=AUTH_HEADERS)
    run_b = client.get("/api/token-usage/runs/run-b", headers=AUTH_HEADERS)

    assert run_a.json()["total_tokens"] == 11
    assert run_b.json()["total_tokens"] == 22
    token_collector.clear_thread("run-a")
    token_collector.clear_thread("run-b")


@pytest.mark.asyncio
async def test_monitor_isolates_same_tool_timing_and_routes_by_run(monkeypatch):
    import api.monitor as monitor_module
    from agent.telemetry import collector
    from api.context import (
        reset_execution_context,
        set_run_context,
        set_segment_context,
        set_thread_context,
    )

    routed = []

    class FakeManager:
        def get_loop(self):
            return asyncio.get_running_loop()

        async def send_to_run(self, payload, run_id):
            routed.append((run_id, payload))

    monkeypatch.setattr(monitor_module.monitor, "websocket_manager", FakeManager())

    async def emit(run_id: str, segment_id: str):
        thread_token = set_thread_context("shared-thread")
        run_token = set_run_context(run_id)
        segment_token = set_segment_context(segment_id)
        try:
            monitor_module.monitor.report_start("same-tool")
            await asyncio.sleep(0)
            monitor_module.monitor.report_end("same-tool")
        finally:
            reset_execution_context(run_token, thread_token, segment_token)

    await asyncio.gather(
        emit("run-a", "run-a-seg-000"),
        emit("run-b", "run-b-seg-000"),
    )
    await asyncio.sleep(0)

    assert len(collector.get_by_run("run-a")) == 1
    assert len(collector.get_by_run("run-b")) == 1
    assert {run_id for run_id, _ in routed} == {"run-a", "run-b"}
    for run_id, payload in routed:
        assert payload["thread_id"] == "shared-thread"
        assert payload["run_id"] == run_id
        assert payload["segment_id"] == f"{run_id}-seg-000"

    collector.clear_run("run-a")
    collector.clear_run("run-b")


@pytest.mark.asyncio
async def test_connection_manager_keeps_two_run_channels_for_same_thread():
    from api.monitor import ConnectionManager

    class FakeWebSocket:
        def __init__(self):
            self.accepted = False
            self.payloads = []

        async def accept(self):
            self.accepted = True

        async def send_json(self, payload):
            self.payloads.append(payload)

    manager = ConnectionManager()
    run_a = FakeWebSocket()
    run_b = FakeWebSocket()

    await manager.connect_run(run_a, run_id="run-a", thread_id="shared-thread")
    await manager.connect_run(run_b, run_id="run-b", thread_id="shared-thread")
    await manager.send_to_run({"run_id": "run-a"}, "run-a")
    await manager.send_to_run({"run_id": "run-b"}, "run-b")

    assert run_a.payloads == [{"run_id": "run-a"}]
    assert run_b.payloads == [{"run_id": "run-b"}]


def test_run_websocket_resolves_run_identity(tmp_path, monkeypatch):
    from api.run_repository import create_run

    monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    created = create_run(thread_id="shared-thread", query="query")
    client = TestClient(app)

    with client.websocket_connect(
        f"/ws/runs/{created['run_id']}?api_key=test-integration-key"
    ) as websocket:
        websocket.send_text("ping")
        payload = websocket.receive_json()

    assert payload["type"] == "pong"
    assert payload["run_id"] == created["run_id"]


def test_three_concurrent_runs_isolate_runtime_state_and_workspace(tmp_path):
    script = textwrap.dedent(
        f"""
        import asyncio
        import os
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        os.environ["OPENAI_API_KEY"] = "test"
        os.environ["OPENAI_BASE_URL"] = "http://test"
        os.environ["LLM_QWEN_MAX"] = "test"

        with patch("deepagents.create_deep_agent", return_value=MagicMock()):
            import agent.main_agent as main_agent

        from agent.token_tracking import TokenUsageData, token_collector
        from api.context import get_run_context, get_session_context, get_thread_context
        from tools.tavily_tools import _search_cache, search_with_dedup

        main_agent.project_root = Path({str(tmp_path)!r})
        entered = asyncio.Event()
        release = asyncio.Event()
        snapshots = {{}}

        class FakeAgent:
            async def astream(self, *args, **kwargs):
                run_id = get_run_context()
                main_agent.shared_context.publish_fact(
                    run_id, f"fact:{{run_id}}", "test", "runtime"
                )
                search_with_dedup(
                    "same-query",
                    search_fn=lambda query: f"result:{{run_id}}",
                    thread_id=run_id,
                )
                token_collector.record(
                    run_id, TokenUsageData(prompt_tokens=len(run_id), completion_tokens=1)
                )
                snapshots[run_id] = {{
                    "thread_id": get_thread_context(),
                    "session_dir": get_session_context(),
                    "facts": main_agent.shared_context.snapshot_facts(run_id),
                    "cache": dict(_search_cache[run_id]),
                }}
                if len(snapshots) == 3:
                    entered.set()
                await release.wait()
                if False:
                    yield {{}}

        main_agent.main_agent = FakeAgent()
        runs = [
            ("shared-thread", "run-a", "run-a-seg-000"),
            ("shared-thread", "run-b", "run-b-seg-000"),
            ("other-thread", "run-c", "run-c-seg-000"),
        ]

        async def verify():
            tasks = [
                asyncio.create_task(
                    main_agent.run_deep_agent(
                        "query", thread_id, run_id=run_id, segment_id=segment_id
                    )
                )
                for thread_id, run_id, segment_id in runs
            ]
            await asyncio.wait_for(entered.wait(), timeout=2)
            assert snapshots["run-a"]["thread_id"] == snapshots["run-b"]["thread_id"]
            assert len({{item["session_dir"] for item in snapshots.values()}}) == 3
            for _, run_id, _ in runs:
                assert snapshots[run_id]["facts"][0]["fact"] == f"fact:{{run_id}}"
                assert list(snapshots[run_id]["cache"].values()) == [f"result:{{run_id}}"]
                assert token_collector.get_summary(run_id)["call_count"] == 1
            release.set()
            await asyncio.gather(*tasks)
            for _, run_id, _ in runs:
                assert main_agent.shared_context.snapshot_facts(run_id) == []
                assert run_id not in _search_cache

        asyncio.run(verify())
        print("OK")
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parents[2],
    )

    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
