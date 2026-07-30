from __future__ import annotations

import asyncio
import builtins
import json
import logging

from fastapi.testclient import TestClient
from langchain_core.messages import ToolMessage
import pytest

from api.server import app
from tools.error_projection import RUNTIME_ERROR_CODES, classify_exception, projection_for, safe_log


MARKER = "DRA_ERROR_EGRESS_SENTINEL"
AUTH_HEADERS = {"X-API-Key": "test-integration-key"}
pytestmark = pytest.mark.usefixtures("authenticated_runtime_access")


class HostileFailure(RuntimeError):
    def __str__(self) -> str:
        raise AssertionError("raw exception conversion attempted")

    def __repr__(self) -> str:
        raise AssertionError("raw exception representation attempted")


async def _settle(monitor):
    tasks, futures = monitor._pending_snapshot()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    if futures:
        await asyncio.gather(
            *(asyncio.wrap_future(future) for future in futures),
            return_exceptions=True,
        )


@pytest.mark.asyncio
async def test_closed_codes_and_marker_use_production_projection_delivery_and_rest(
    monkeypatch,
    caplog,
) -> None:
    import api.monitor as monitor_module
    from agent.telemetry import collector
    from api.context import reset_execution_context, set_run_context, set_segment_context, set_thread_context

    websocket_payloads = []
    stream_payloads = []

    class FakeManager:
        def get_loop(self):
            return asyncio.get_running_loop()

        async def send_to_run(self, payload, run_id):
            websocket_payloads.append(payload)

    class Runtime:
        def stream_writer(self, payload):
            stream_payloads.append(payload)

    monitor = monitor_module.monitor
    await _settle(monitor)
    monkeypatch.setattr(monitor, "websocket_manager", FakeManager())
    monkeypatch.setattr(builtins, "runtime", Runtime(), raising=False)
    thread_token = set_thread_context("runtime-projection-thread")
    run_token = set_run_context("runtime-projection-run")
    segment_token = set_segment_context("runtime-projection-run-seg-000")
    logger = logging.getLogger("runtime-error-projection-test")
    messages = []
    try:
        with caplog.at_level(logging.ERROR, logger=logger.name):
            for code in sorted(RUNTIME_ERROR_CODES):
                projection = projection_for(
                    operation="harness",
                    code=code,
                    error_type="HostileFailure",
                )
                safe_log(logger, logging.ERROR, event="harness_failed", projection=projection)
                messages.append(ToolMessage(content=projection.message, tool_call_id=f"call-{code}"))
                monitor.report_tool("mysql_query", {"query": MARKER, "path": f"/private/{MARKER}"})
                monitor.report_end(
                    "mysql_query",
                    result={"secret": MARKER},
                    error=projection.code,
                    error_type=projection.error_type,
                )
        await _settle(monitor)
        response = TestClient(app).get(
            "/api/telemetry/runs/runtime-projection-run",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200
        records = response.json()
        expected = set(RUNTIME_ERROR_CODES)
        assert {record["error"] for record in records} == expected
        assert {payload["data"].get("error") for payload in websocket_payloads if payload["event"] == "tool_end"} == expected
        assert {payload["data"].get("error") for payload in stream_payloads if payload["event"] == "tool_end"} == expected
        serialized = json.dumps(
            {
                "logs": [record.getMessage() for record in caplog.records],
                "model": [message.content for message in messages],
                "websocket": websocket_payloads,
                "stream": stream_payloads,
                "rest": records,
            },
            sort_keys=True,
        )
        assert MARKER not in serialized
        assert all(record.exc_info is None for record in caplog.records)
        failure_projection = classify_exception(HostileFailure(MARKER), operation="harness")
        assert failure_projection.code == "execution_failed"
    finally:
        reset_execution_context(run_token, thread_token, segment_token)
        collector.clear_run("runtime-projection-run")
        await _settle(monitor)
