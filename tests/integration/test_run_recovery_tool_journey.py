from __future__ import annotations

from contextlib import contextmanager
import asyncio
import json
import os
from pathlib import Path, PurePosixPath
import socket
import subprocess
import sys
import threading
import time

import pytest
import uvicorn

from agent.harness_contracts import ReportCandidate
from agent.run_result import AgentRunResult
from api.database import prepare_application_db_parent
from api.run_dispatch_repository import claim_run_dispatch, start_run_dispatch
from api.run_execution_models import new_boot_id
from api.run_execution_repository import activate_run_execution_boot
from api.run_repository import create_run


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL = PROJECT_ROOT / "tools" / "decision_research_agent_tool.py"
SECRET = "local-recovery-journey-secret"
KEY = "recovery-journey-key-0123456789abcdef"


def _seed_interrupted_source(db_path: str) -> dict:
    prepare_application_db_parent(Path(db_path))
    created = create_run(
        db_path=db_path,
        thread_id="provider-free-recovery-thread",
        query="provider-free recovery query",
    )
    boot_id = new_boot_id()
    activate_run_execution_boot(db_path=db_path, boot_id=boot_id)
    claim = claim_run_dispatch(
        db_path=db_path,
        worker_id="dispatch_worker_" + "e" * 32,
        boot_id=boot_id,
        lease_seconds=30,
        run_id=created["run_id"],
    )
    assert claim is not None
    assert start_run_dispatch(db_path=db_path, claim=claim) is not None
    return created


class _IdleWorker:
    def __init__(self) -> None:
        self._stopped = asyncio.Event()

    async def run_forever(self) -> None:
        await self._stopped.wait()

    def stop(self) -> None:
        self._stopped.set()

    async def dispatch_run(self, run_id: str) -> bool:
        del run_id
        return False

    def wake(self) -> None:
        return None


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@contextmanager
def _local_service(
    tmp_path,
    monkeypatch,
    *,
    execute_replacement: bool,
):
    import api.server as server

    db_path = str(tmp_path / "application" / "runs.db")
    source = _seed_interrupted_source(db_path)
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", db_path)
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "false")
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION",
        "false",
    )
    monkeypatch.setattr(server, "output_dir", tmp_path / "output")
    monkeypatch.setattr(
        server.app.state,
        "runtime_access_policy",
        server.load_runtime_access_policy({"API_SECRET": SECRET}),
    )
    if not execute_replacement:
        monkeypatch.setattr(
            server,
            "create_run_dispatch_worker",
            lambda *args, **kwargs: _IdleWorker(),
        )
    else:
        async def provider_free_agent(
            query,
            thread_id,
            *,
            run_id,
            segment_id,
            **kwargs,
        ):
            del kwargs
            return AgentRunResult(
                thread_id=thread_id,
                query=query,
                session_dir=tmp_path,
                run_id=run_id,
                segment_id=segment_id,
                report_candidate=ReportCandidate(
                    path=PurePosixPath("/workspace/research-report.md"),
                    content="# Provider-free recovery result",
                ),
            )

        monkeypatch.setattr(server, "run_deep_agent", provider_free_agent)

    port = _free_loopback_port()
    instance = uvicorn.Server(
        uvicorn.Config(
            server.app,
            host="127.0.0.1",
            port=port,
            log_level="critical",
            access_log=False,
        )
    )
    thread = threading.Thread(target=instance.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not instance.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    if not instance.started:
        instance.should_exit = True
        thread.join(timeout=10)
        raise AssertionError("local recovery service did not start")
    try:
        yield source, f"http://127.0.0.1:{port}"
    finally:
        instance.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


def _run_tool(base_url: str, args: list[str], *, timeout: int):
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHON_DOTENV_DISABLED": "1",
            "DECISION_RESEARCH_AGENT_API_KEY": SECRET,
        }
    )
    return subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--base-url",
            base_url,
            "--timeout",
            "5",
            *args,
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _diagnostic(*, case_id: str, seconds: float, budget_seconds: int) -> dict:
    field = (
        "acceptance_seconds"
        if case_id == "durable_acceptance"
        else "completion_seconds"
    )
    return {
        "case_id": case_id,
        "scope": "provider_free_local_fixture",
        "status": "observed",
        field: round(max(0.0, seconds), 3),
        "budget_seconds": budget_seconds,
    }


def _emit_diagnostic(payload: dict) -> None:
    print(
        "DRA_RECOVERY_TTHW_OBSERVATION "
        + json.dumps(payload, sort_keys=True, separators=(",", ":"))
    )


def test_documented_retry_command_reaches_durable_acceptance_within_90_second_test_budget(
    tmp_path,
    monkeypatch,
):
    with _local_service(
        tmp_path,
        monkeypatch,
        execute_replacement=False,
    ) as (source, base_url):
        started = time.monotonic()
        completed = _run_tool(
            base_url,
            [
                "retry",
                "--run-id",
                source["run_id"],
                "--idempotency-key",
                KEY,
            ],
            timeout=90,
        )
        elapsed = time.monotonic() - started
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "accepted"
    assert payload["source_run_id"] == source["run_id"]
    assert payload["run_id"] != source["run_id"]
    assert payload["idempotency_key"] == KEY
    assert elapsed <= 90
    _emit_diagnostic(
        _diagnostic(
            case_id="durable_acceptance",
            seconds=elapsed,
            budget_seconds=90,
        )
    )


def test_documented_retry_wait_result_targets_replacement_within_120_second_test_budget(
    tmp_path,
    monkeypatch,
):
    with _local_service(
        tmp_path,
        monkeypatch,
        execute_replacement=True,
    ) as (source, base_url):
        started = time.monotonic()
        completed = _run_tool(
            base_url,
            [
                "retry",
                "--run-id",
                source["run_id"],
                "--idempotency-key",
                KEY,
                "--wait",
                "--result",
                "--poll-seconds",
                "0.01",
                "--wait-timeout-seconds",
                "30",
            ],
            timeout=120,
        )
        elapsed = time.monotonic() - started
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["run_id"] != source["run_id"]
    assert payload["artifact"]["artifact_id"] == "research-report.md"
    assert payload["artifact"]["content"] == "# Provider-free recovery result"
    assert elapsed <= 120
    _emit_diagnostic(
        _diagnostic(
            case_id="wait_result",
            seconds=elapsed,
            budget_seconds=120,
        )
    )


@pytest.mark.parametrize(
    ("case_id", "duration_field", "budget"),
    [
        ("durable_acceptance", "acceptance_seconds", 90),
        ("wait_result", "completion_seconds", 120),
    ],
)
def test_provider_free_timing_diagnostics_have_exact_private_neutral_schema(
    case_id,
    duration_field,
    budget,
):
    payload = _diagnostic(
        case_id=case_id,
        seconds=0.125,
        budget_seconds=budget,
    )
    assert set(payload) == {
        "case_id",
        "scope",
        "status",
        duration_field,
        "budget_seconds",
    }
    assert payload["case_id"] == case_id
    assert payload["scope"] == "provider_free_local_fixture"
    assert payload["status"] == "observed"
    assert isinstance(payload[duration_field], float)
    assert 0 <= payload[duration_field] <= budget
    assert payload["budget_seconds"] == budget
    encoded = json.dumps(payload)
    for forbidden in (
        "port",
        "path",
        "run_id",
        "thread_id",
        "segment_id",
        "idempotency_key",
        "api_secret",
        "query",
        "pid",
    ):
        assert forbidden not in encoded
