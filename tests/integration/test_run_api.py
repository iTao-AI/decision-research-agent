import os
import asyncio
import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient

from api.server import app


AUTH_HEADERS = {"X-API-Key": "test-integration-key"}
pytestmark = pytest.mark.usefixtures("authenticated_runtime_access")
TEST_WORKER_ID = "dispatch_worker_0000000000000000000000000000000a"


@pytest.fixture(autouse=True)
def route_dispatch_worker(monkeypatch):
    import api.server as server
    from api.database import sqlite_db_path

    class RouteWorker:
        async def dispatch_run(self, run_id):
            return await server.create_run_dispatch_worker(
                sqlite_db_path()
            ).dispatch_run(run_id)

        def wake(self):
            pass

    monkeypatch.setattr(
        server.app.state,
        "run_dispatch_worker",
        RouteWorker(),
        raising=False,
    )


async def _start_run_v2_with_dispatch(
    server,
    *,
    timeout_seconds=30,
    on_timeout=None,
    on_cancel=None,
    **kwargs,
):
    from api.database import sqlite_db_path
    from api.run_dispatch_repository import claim_run_dispatch

    claim = claim_run_dispatch(
        db_path=sqlite_db_path(),
        worker_id=TEST_WORKER_ID,
        lease_seconds=30,
        run_id=kwargs["run_id"],
    )
    assert claim is not None
    stage = server._RunStage()
    origin = server.TerminationOrigin()
    checkpoint = server.FinalizationCheckpoint()
    coroutine = server._run_dispatched_with_persistence(
        claim,
        db_path=sqlite_db_path(),
        outcome_box=kwargs["outcome_box"],
        stage=stage,
        termination_origin=origin,
        finalization_checkpoint=checkpoint,
    )
    task = server.create_tracked_task(
        coroutine,
        f"{claim.run_id}:test:{claim.attempt_count}",
        timeout_seconds=timeout_seconds,
        on_timeout=on_timeout,
        on_cancel=on_cancel,
        termination_origin=origin,
        finalization_checkpoint=checkpoint,
    )
    return task, stage, origin, checkpoint


async def _run_v2_with_dispatch(server, **kwargs):
    from api.task_tracker import get_active_task

    task, _, _, _ = await _start_run_v2_with_dispatch(server, **kwargs)
    task_id = f"{kwargs['run_id']}:test:1"
    try:
        return await task
    finally:
        await asyncio.sleep(0)
        assert get_active_task(task_id) is None


def test_create_and_get_run_returns_distinct_thread_and_run_identity(
    tmp_path, monkeypatch
):
    import api.server as server

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    scheduled = []

    def capture_task(coroutine, task_id, **kwargs):
        scheduled.append((coroutine, task_id))
        coroutine.close()

    monkeypatch.setattr(server, "create_tracked_task", capture_task)
    client = TestClient(app)

    response = client.post(
        "/api/runs",
        json={"query": "research", "thread_id": "thread-1"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    created = response.json()
    assert created["thread_id"] == "thread-1"
    assert created["run_id"].startswith("run_")
    assert created["segment_id"].endswith("_seg_000")
    assert scheduled[0][1] == f"{created['run_id']}:dispatch:1"
    assert set(created) == {"status", "thread_id", "run_id", "segment_id"}

    fetched = client.get(f"/api/runs/{created['run_id']}", headers=AUTH_HEADERS)
    assert fetched.status_code == 200
    assert fetched.json()["run_id"] == created["run_id"]


def test_get_run_status_exposes_observed_failure_cause(tmp_path, monkeypatch):
    import api.run_repository as repository
    from api.run_failure_cause_models import RunFailureCauseWrite

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("API_SECRET", "test-integration-key")
    monkeypatch.setattr(
        repository,
        "_now",
        lambda: "2026-07-16T00:00:00+00:00",
    )
    created = repository.create_run(thread_id="thread-1", query="query")
    assert repository.finalize_run_transaction(
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="failed",
        delivery_status="failed",
        evidence_entries=[],
        failure_cause=RunFailureCauseWrite(
            phase="execution",
            code="execution_error",
        ),
    )

    response = TestClient(app).get(
        f"/api/runs/{created['run_id']}",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["failure_cause"] == {
        "schema_version": "dra.run-failure-cause.v1",
        "observation_status": "observed",
        "phase": "execution",
        "code": "execution_error",
        "recorded_at": "2026-07-16T00:00:00Z",
    }
    assert "terminal_state_version" not in response.text


def test_get_run_status_exposes_historical_not_observed_failure_cause(
    tmp_path,
    monkeypatch,
):
    from tests.unit.test_run_migrations import _apply_009, _seed_pre_009_runs

    db_path = str(tmp_path / "tasks.db")
    _seed_pre_009_runs(db_path, statuses=("failed",))
    _apply_009(db_path)
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", db_path)
    monkeypatch.setenv("API_SECRET", "test-integration-key")

    response = TestClient(app).get(
        "/api/runs/run_failed_0",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["failure_cause"] == {
        "schema_version": "dra.run-failure-cause.v1",
        "observation_status": "not_observed",
    }


def test_get_run_status_exposes_null_failure_cause_for_nonfailed_run(
    tmp_path,
    monkeypatch,
):
    from api.run_repository import create_run

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("API_SECRET", "test-integration-key")
    created = create_run(thread_id="thread-1", query="query")

    response = TestClient(app).get(
        f"/api/runs/{created['run_id']}",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["failure_cause"] is None


def test_run_status_openapi_documents_only_additive_failure_cause():
    schema = app.openapi()
    status_operation = schema["paths"]["/api/runs/{run_id}"]["get"]
    status_response_schema = status_operation["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert status_response_schema == {
        "$ref": "#/components/schemas/RunStatusFailureCauseOpenAPI"
    }

    envelope = schema["components"]["schemas"]["RunStatusFailureCauseOpenAPI"]
    assert envelope["required"] == ["failure_cause"]
    assert set(envelope["properties"]) == {"failure_cause"}
    assert envelope["additionalProperties"] is True
    assert "terminal_state_version" not in str(envelope)

    result_operation = schema["paths"]["/api/runs/{run_id}/result"]["get"]
    assert "failure_cause" not in str(result_operation)


@pytest.mark.parametrize("detection_point", ["schema_verifier", "joined_projector"])
def test_run_status_bounds_corrupt_failure_cause(
    tmp_path,
    monkeypatch,
    detection_point,
):
    import api.review_repository as review_repository
    import api.run_repository as repository
    from api.run_failure_cause_models import RunFailureCauseWrite

    db_path = str(tmp_path / "tasks.db")
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", db_path)
    monkeypatch.setenv("API_SECRET", "test-integration-key")
    created = repository.create_run(
        db_path=db_path,
        thread_id="corrupt-cause-thread",
        query="query",
    )
    assert repository.finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="failed",
        delivery_status="failed",
        evidence_entries=[],
        failure_cause=RunFailureCauseWrite(
            phase="execution",
            code="execution_error",
        ),
    )
    if detection_point == "joined_projector":
        assert repository.get_run(db_path=db_path, run_id=created["run_id"])
        monkeypatch.setattr(
            review_repository,
            "init_review_schema",
            lambda _db_path=None: None,
        )

    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE run_failure_causes_v1
                SET terminal_state_version = 99
                WHERE run_id = ?
                """,
                (created["run_id"],),
            )
    finally:
        connection.close()

    response = TestClient(app, raise_server_exceptions=False).get(
        f"/api/runs/{created['run_id']}",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "ResearchRun state is unavailable"}


def test_keyed_create_replays_identity_and_schedules_once(tmp_path, monkeypatch):
    import api.server as server

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("API_SECRET", "test-integration-key")
    scheduled = []

    def capture_task(coroutine, task_id, **kwargs):
        scheduled.append(task_id)
        coroutine.close()

    monkeypatch.setattr(server, "create_tracked_task", capture_task)
    client = TestClient(app)
    headers = {**AUTH_HEADERS, "Idempotency-Key": "run-key-api-0001"}
    body = {"query": "research", "profile_id": "generic", "scope": {}}
    first = client.post("/api/runs", json=body, headers=headers)
    second = client.post("/api/runs", json=body, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["idempotent_replay"] is False
    assert second.json()["idempotent_replay"] is True
    assert {key: first.json()[key] for key in ("run_id", "thread_id", "segment_id")} == {
        key: second.json()[key] for key in ("run_id", "thread_id", "segment_id")
    }
    assert scheduled == [f"{first.json()['run_id']}:dispatch:1"]


def test_keyed_replay_cannot_enter_agent_twice(tmp_path, monkeypatch):
    import api.server as server

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("API_SECRET", "test-integration-key")
    scheduled = []

    def capture_task(coroutine, task_id, **kwargs):
        scheduled.append(task_id)
        coroutine.close()

    monkeypatch.setattr(server, "create_tracked_task", capture_task)
    client = TestClient(app)
    headers = {**AUTH_HEADERS, "Idempotency-Key": "run-key-api-fence-0001"}
    body = {"query": "research"}
    first = client.post("/api/runs", json=body, headers=headers)
    second = client.post("/api/runs", json=body, headers=headers)
    assert first.status_code == second.status_code == 200
    assert scheduled == [f"{first.json()['run_id']}:dispatch:1"]


def test_keyed_create_conflict_is_stable_and_schedules_nothing_new(tmp_path, monkeypatch):
    import api.server as server

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("API_SECRET", "test-integration-key")
    scheduled = []

    def capture_task(coroutine, task_id, **kwargs):
        scheduled.append(task_id)
        coroutine.close()

    monkeypatch.setattr(server, "create_tracked_task", capture_task)
    client = TestClient(app)
    raw_key = "run-key-api-0002"
    headers = {**AUTH_HEADERS, "Idempotency-Key": raw_key}
    assert client.post("/api/runs", json={"query": "first"}, headers=headers).status_code == 200
    conflict = client.post("/api/runs", json={"query": "second"}, headers=headers)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "run_idempotency_conflict"
    assert conflict.json()["retryable"] is False
    assert conflict.json()["run_id"] is None
    assert raw_key not in conflict.text
    assert len(scheduled) == 1


def test_invalid_idempotency_key_is_stable_and_does_not_touch_repository(monkeypatch):
    import api.server as server

    monkeypatch.setenv("API_SECRET", "test-integration-key")
    monkeypatch.setattr(
        server,
        "create_or_replay_run",
        lambda **kwargs: pytest.fail("invalid key must fail before persistence"),
        raising=False,
    )
    response = TestClient(app).post(
        "/api/runs",
        json={"query": "research"},
        headers={**AUTH_HEADERS, "Idempotency-Key": "short"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "run_idempotency_key_invalid"


def test_keyed_persistence_failure_is_503_without_unkeyed_fallback(monkeypatch):
    import api.server as server
    from api.run_repository import RunCreationConflict

    monkeypatch.setenv("API_SECRET", "test-integration-key")
    monkeypatch.setattr(
        server,
        "create_or_replay_run",
        lambda **kwargs: (_ for _ in ()).throw(
            RunCreationConflict("run_idempotency_unavailable")
        ),
        raising=False,
    )
    monkeypatch.setattr(
        server,
        "create_run",
        lambda **kwargs: pytest.fail("must not fall back to unkeyed create"),
    )
    raw_key = "run-key-api-0003"
    response = TestClient(app).post(
        "/api/runs",
        json={"query": "research"},
        headers={**AUTH_HEADERS, "Idempotency-Key": raw_key},
    )
    assert response.status_code == 503
    assert response.json()["code"] == "run_idempotency_unavailable"
    assert response.json()["retryable"] is True
    assert raw_key not in response.text


def test_unknown_run_creation_conflict_maps_to_safe_unavailable(monkeypatch):
    import api.server as server
    from api.run_repository import RunCreationConflict

    monkeypatch.setenv("API_SECRET", "test-integration-key")
    monkeypatch.setattr(
        server,
        "create_or_replay_run",
        lambda **kwargs: (_ for _ in ()).throw(
            RunCreationConflict("unexpected_internal_code")
        ),
    )
    response = TestClient(app).post(
        "/api/runs",
        json={"query": "research"},
        headers={**AUTH_HEADERS, "Idempotency-Key": "run-key-api-unknown-0001"},
    )
    assert response.status_code == 503
    assert response.json()["code"] == "run_idempotency_unavailable"
    assert "unexpected_internal_code" not in response.text


def test_keyed_scheduler_failure_returns_ack_and_exhausts_durable_retries(
    tmp_path,
    monkeypatch,
):
    import api.server as server

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("API_SECRET", "test-integration-key")

    def fail_to_schedule(*args, **kwargs):
        raise RuntimeError("scheduler unavailable")

    monkeypatch.setattr(server, "create_tracked_task", fail_to_schedule)
    client = TestClient(app, raise_server_exceptions=False)
    headers = {**AUTH_HEADERS, "Idempotency-Key": "run-key-api-schedule-0001"}
    body = {"query": "research"}
    responses = [client.post("/api/runs", json=body, headers=headers) for _ in range(3)]
    assert [response.status_code for response in responses] == [200, 200, 200]
    assert [response.json()["idempotent_replay"] for response in responses] == [
        False,
        True,
        True,
    ]
    replay = responses[-1]
    fetched = client.get(
        f"/api/runs/{replay.json()['run_id']}",
        headers=AUTH_HEADERS,
    )
    assert fetched.status_code == 200
    assert fetched.json()["execution_status"] == "failed"


def test_create_run_registers_run_scoped_timeout_callback(tmp_path, monkeypatch):
    import api.server as server

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    scheduled = []

    def capture_task(coroutine, task_id, **kwargs):
        scheduled.append((coroutine, task_id, kwargs))

    monkeypatch.setattr(server, "create_tracked_task", capture_task)
    client = TestClient(app)

    response = client.post(
        "/api/runs",
        json={"query": "research", "thread_id": "timeout-thread"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    coroutine, task_id, kwargs = scheduled[0]
    try:
        assert task_id == f"{response.json()['run_id']}:dispatch:1"
        assert callable(kwargs["on_timeout"])
    finally:
        coroutine.close()


def test_create_run_allows_same_thread_without_legacy_guard(tmp_path, monkeypatch):
    import api.server as server

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    scheduled = []

    def capture_task(coroutine, task_id, **kwargs):
        scheduled.append(coroutine)

    monkeypatch.setattr(server, "create_tracked_task", capture_task)
    client = TestClient(app)

    response = client.post(
        "/api/runs",
        json={"query": "research", "thread_id": "shared-thread"},
        headers=AUTH_HEADERS,
    )
    second = client.post(
        "/api/runs",
        json={"query": "research again", "thread_id": "shared-thread"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert second.status_code == 200
    assert response.json()["thread_id"] == "shared-thread"
    assert second.json()["thread_id"] == "shared-thread"
    assert response.json()["run_id"] != second.json()["run_id"]
    for coroutine in scheduled:
        coroutine.close()


def test_create_run_rejects_unknown_profile_fail_closed(tmp_path, monkeypatch):
    import api.server as server

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    client = TestClient(app)

    response = client.post(
        "/api/runs",
        json={"query": "research", "profile_id": "unknown"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unknown_profile"


def test_create_talent_run_rejects_invalid_scope_before_scheduling(
    tmp_path, monkeypatch
):
    import api.server as server

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    scheduled = []
    monkeypatch.setattr(server, "create_tracked_task", scheduled.append)
    client = TestClient(app)

    response = client.post(
        "/api/runs",
        json={
            "query": "research",
            "profile_id": "talent-hiring-signal",
            "scope": {"target_roles": ["AI Agent Engineer"]},
        },
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_research_scope"
    assert scheduled == []


def test_profile_manifest_exposes_policy_without_runtime_secrets():
    os.environ["API_SECRET"] = "test-integration-key"
    client = TestClient(app)

    response = client.get("/api/profiles/talent-hiring-signal", headers=AUTH_HEADERS)

    assert response.status_code == 200
    manifest = response.json()
    assert manifest["profile"]["profile_id"] == "talent-hiring-signal"
    assert manifest["harness_policy"]["allowed_tools"] == []
    assert "api_key" not in str(manifest).lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_kind", "expected_code"),
    [
        ("call_budget_exceeded", "call_budget_exceeded"),
        ("recursion_limit_exceeded", "recursion_limit_exceeded"),
        ("unknown_harness_value", "execution_error"),
        ("run_timeout", "execution_error"),
        ("cancelled", "execution_error"),
    ],
)
async def test_run_v2_maps_only_bounded_execution_failure_kinds(
    tmp_path,
    monkeypatch,
    failure_kind,
    expected_code,
):
    import api.server as server
    from agent.run_result import AgentRunResult
    from api.run_repository import create_run, get_run

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    created = create_run(
        thread_id=f"mapper-{expected_code}-{failure_kind}",
        query="query containing /private/path and sk-not-a-real-secret",
    )

    async def bounded_failure(*_args, **_kwargs):
        return AgentRunResult(
            thread_id=created["thread_id"],
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            query="query",
            session_dir=tmp_path,
            failure_kind=failure_kind,
            error_message="provider traceback /private/path sk-not-a-real-secret",
        )

    monkeypatch.setattr(server, "run_deep_agent", bounded_failure)
    await _run_v2_with_dispatch(
        server,
        query="query",
        thread_id=created["thread_id"],
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        outcome_box=server.OutcomeBox(),
    )

    run = get_run(run_id=created["run_id"])
    assert run["execution_status"] == "failed"
    assert run["state_version"] == 2
    assert run["segments"][0]["status"] == "failed"
    assert run["failure_cause"]["phase"] == "execution"
    assert run["failure_cause"]["code"] == expected_code
    assert "private" not in str(run["failure_cause"]).lower()
    assert "secret" not in str(run["failure_cause"]).lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("packet_content", "expected_code"),
    [
        ('{"packet_id":"malformed-private-diagnostic"}', "invalid_research_packet"),
        (None, "missing_research_packet"),
    ],
)
async def test_talent_packet_resolution_reaches_durable_server_cause(
    tmp_path,
    monkeypatch,
    packet_content,
    expected_code,
):
    import api.server as server
    from api.research_execution_service import ResearchExecutionService
    from api.run_repository import create_run, get_run
    from langchain_core.messages import ToolMessage

    db_path = str(tmp_path / "tasks.db")
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", db_path)

    class TalentPacketHarness:
        async def execute(self, request, *, runtime_context, observer):
            del request, runtime_context
            if packet_content is not None:
                observer.on_stream_chunk(
                    {
                        "tools": {
                            "messages": [
                                ToolMessage(
                                    content=packet_content,
                                    tool_call_id="call-task",
                                    name="task",
                                )
                            ]
                        }
                    }
                )
            return observer.snapshot_outcome()

    service = ResearchExecutionService(
        harness=TalentPacketHarness(),
        project_root=tmp_path,
        clear_run_cache=lambda _run_id: None,
    )

    async def run_talent_packet_chain(query, thread_id, **kwargs):
        return await service.execute(query, thread_id, **kwargs)

    created = create_run(
        db_path=db_path,
        thread_id=f"talent-{expected_code}",
        query="query",
        profile_id="talent-hiring-signal",
        scope={},
    )
    outcome_box = server.OutcomeBox()
    monkeypatch.setattr(server, "run_deep_agent", run_talent_packet_chain)

    await _run_v2_with_dispatch(
        server,
        query="query",
        thread_id=created["thread_id"],
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        outcome_box=outcome_box,
    )

    outcome = outcome_box.latest()
    assert outcome is not None
    assert outcome.failure_kind == expected_code
    invalid_diagnostics = [
        item
        for item in outcome.diagnostics
        if item.startswith("invalid_research_packet:")
    ]
    assert bool(invalid_diagnostics) is (expected_code == "invalid_research_packet")

    run = get_run(db_path=db_path, run_id=created["run_id"])
    assert run["execution_status"] == "failed"
    assert run["state_version"] == 2
    assert run["segments"][0]["status"] == "failed"
    assert run["failure_cause"]["phase"] == "execution"
    assert run["failure_cause"]["code"] == expected_code
    assert "malformed-private-diagnostic" not in str(run["failure_cause"])

    connection = sqlite3.connect(db_path)
    try:
        cause_rows = connection.execute(
            """
            SELECT observation_status, terminal_state_version, phase, code
            FROM run_failure_causes_v1
            WHERE run_id = ?
            """,
            (created["run_id"],),
        ).fetchall()
    finally:
        connection.close()
    assert cause_rows == [("observed", 2, "execution", expected_code)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("native_kind", "expected_code"),
    [
        ("model_call_limit", "call_budget_exceeded"),
        ("tool_call_limit", "call_budget_exceeded"),
        ("graph_recursion", "recursion_limit_exceeded"),
    ],
)
async def test_installed_native_signal_reaches_durable_server_cause(
    tmp_path,
    monkeypatch,
    native_kind,
    expected_code,
):
    import api.server as server
    from agent.deepagents_harness import DeepAgentsHarness
    from api.research_execution_service import ResearchExecutionService
    from api.run_repository import create_run, get_run
    from langchain.agents.middleware.model_call_limit import (
        ModelCallLimitExceededError,
    )
    from langchain.agents.middleware.tool_call_limit import (
        ToolCallLimitExceededError,
    )
    from langgraph.errors import GraphRecursionError

    native_exception = {
        "model_call_limit": ModelCallLimitExceededError(1, 1, 1, 1),
        "tool_call_limit": ToolCallLimitExceededError(
            1,
            1,
            1,
            1,
            tool_name="search",
        ),
        "graph_recursion": GraphRecursionError("bounded recursion"),
    }[native_kind]

    class RaisingGraph:
        async def astream(self, _input, *, config, context):
            del config, context
            if False:
                yield {}
            raise native_exception

    graph = RaisingGraph()
    harness = DeepAgentsHarness(
        graph=graph,
        backend=object(),
        permissions=(),
        skills=(),
        profile_graphs={"generic": graph},
    )
    service = ResearchExecutionService(
        harness=harness,
        project_root=tmp_path,
        clear_run_cache=lambda _run_id: None,
    )

    async def run_native_chain(query, thread_id, **kwargs):
        return await service.execute(query, thread_id, **kwargs)

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    created = create_run(
        thread_id=f"native-{native_kind}",
        query="query",
    )
    monkeypatch.setattr(server, "run_deep_agent", run_native_chain)

    await _run_v2_with_dispatch(
        server,
        query="query",
        thread_id=created["thread_id"],
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        outcome_box=server.OutcomeBox(),
    )

    run = get_run(run_id=created["run_id"])
    assert run["failure_cause"]["phase"] == "execution"
    assert run["failure_cause"]["code"] == expected_code
    assert str(native_exception) not in str(run["failure_cause"])


@pytest.mark.asyncio
async def test_run_v2_cancellation_without_outcome_still_finalizes_failed(
    tmp_path, monkeypatch
):
    import api.server as server
    from api.run_repository import create_run, get_run

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    created = create_run(thread_id="cancel-thread", query="query")

    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(server, "run_deep_agent", cancelled)

    with pytest.raises(asyncio.CancelledError):
        await _run_v2_with_dispatch(server,
            query="query",
            thread_id="cancel-thread",
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            outcome_box=server.OutcomeBox(),
        )

    run = get_run(run_id=created["run_id"])
    assert run["execution_status"] == "failed"
    assert run["delivery_status"] == "failed"
    assert run["state_version"] == 2
    assert run["failure_cause"]["phase"] == "execution"
    assert run["failure_cause"]["code"] == "execution_error"


@pytest.mark.asyncio
async def test_run_v2_exception_freezes_partial_evidence_with_bounded_cause(
    tmp_path,
    monkeypatch,
):
    import api.server as server
    from agent.research import EvidenceEntry
    from agent.run_result import AgentRunResult
    from api.run_repository import create_run, get_run

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    created = create_run(thread_id="exception-thread", query="query")
    evidence = EvidenceEntry(
        thread_id=created["thread_id"],
        query_text="query",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url="https://example.com/source",
        source_identity="https://example.com/source",
        snippet="partial evidence",
        evidence_fingerprint="partial-exception-evidence",
    )

    async def explode(*_args, **kwargs):
        kwargs["outcome_box"].publish(
            AgentRunResult(
                thread_id=created["thread_id"],
                run_id=created["run_id"],
                segment_id=created["segment_id"],
                query="query",
                session_dir=tmp_path,
                evidence_entries=[evidence],
                failure_kind="execution_error",
            )
        )
        raise RuntimeError("provider traceback /private/path credential-value")

    monkeypatch.setattr(server, "run_deep_agent", explode)
    with pytest.raises(RuntimeError, match="provider traceback"):
        await _run_v2_with_dispatch(
            server,
            query="query",
            thread_id=created["thread_id"],
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            outcome_box=server.OutcomeBox(),
        )

    run = get_run(run_id=created["run_id"])
    assert [item["evidence_fingerprint"] for item in run["evidence"]] == [
        "partial-exception-evidence"
    ]
    assert run["failure_cause"]["phase"] == "execution"
    assert run["failure_cause"]["code"] == "execution_error"
    assert "private" not in str(run["failure_cause"]).lower()
    assert "credential" not in str(run["failure_cause"]).lower()


@pytest.mark.asyncio
async def test_late_outer_cancel_during_failed_finalizer_preserves_committed_cause(
    tmp_path,
    monkeypatch,
):
    import api.server as server
    from api.run_dispatch_repository import claim_run_dispatch
    from api.run_repository import create_run, get_run

    db_path = str(tmp_path / "tasks.db")
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", db_path)
    created = create_run(thread_id="failed-finalizer-cancel", query="query")
    committed = threading.Event()
    release = threading.Event()

    async def explode(*_args, **_kwargs):
        raise RuntimeError("ordinary agent failure")

    real_finalize = server.finalize_run_transaction

    def commit_failed_then_hold(**kwargs):
        assert kwargs["failure_cause"].phase == "execution"
        assert kwargs["failure_cause"].code == "execution_error"
        result = real_finalize(**kwargs)
        committed.set()
        assert release.wait(timeout=3)
        return result

    monkeypatch.setattr(server, "run_deep_agent", explode)
    monkeypatch.setattr(server, "finalize_run_transaction", commit_failed_then_hold)
    claim = claim_run_dispatch(
        db_path=db_path,
        worker_id=TEST_WORKER_ID,
        lease_seconds=30,
        run_id=created["run_id"],
    )
    assert claim is not None
    task = asyncio.create_task(
        server._run_dispatched_with_persistence(
            claim,
            db_path=db_path,
            outcome_box=server.OutcomeBox(),
            stage=server._RunStage(),
            termination_origin=server.TerminationOrigin(),
            finalization_checkpoint=server.FinalizationCheckpoint(),
        )
    )

    try:
        assert await asyncio.to_thread(committed.wait, 1)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        if not task.done():
            task.cancel()
        try:
            await task
        except BaseException:
            pass

    assert task.cancelled()
    run = get_run(db_path=db_path, run_id=created["run_id"])
    assert run["execution_status"] == "failed"
    assert run["failure_cause"]["phase"] == "execution"
    assert run["failure_cause"]["code"] == "execution_error"


@pytest.mark.asyncio
async def test_external_cancellation_during_execution_freezes_partial_evidence(
    tmp_path,
    monkeypatch,
):
    import api.server as server
    from agent.research import EvidenceEntry
    from agent.run_result import AgentRunResult
    from api.run_repository import create_run, get_run

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    created = create_run(thread_id="execution-cancel", query="query")
    entered = asyncio.Event()
    evidence = EvidenceEntry(
        thread_id=created["thread_id"],
        query_text="query",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url="https://example.com/cancel",
        source_identity="https://example.com/cancel",
        snippet="partial before cancellation",
        evidence_fingerprint="partial-cancel-evidence",
    )

    async def wait_for_cancel(*_args, **kwargs):
        kwargs["outcome_box"].publish(
            AgentRunResult(
                thread_id=created["thread_id"],
                run_id=created["run_id"],
                segment_id=created["segment_id"],
                query="query",
                session_dir=tmp_path,
                evidence_entries=[evidence],
            )
        )
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(server, "run_deep_agent", wait_for_cancel)
    task, stage, origin, _ = await _start_run_v2_with_dispatch(
        server,
        query="query",
        thread_id=created["thread_id"],
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        outcome_box=server.OutcomeBox(),
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    run = get_run(run_id=created["run_id"])
    assert stage.value == "execution"
    assert origin.value == "cancelled"
    assert run["failure_cause"]["phase"] == "execution"
    assert run["failure_cause"]["code"] == "cancelled"
    assert [item["evidence_fingerprint"] for item in run["evidence"]] == [
        "partial-cancel-evidence"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first_origin", "expected_code"),
    [
        ("timeout", "run_timeout"),
        ("cancelled", "cancelled"),
    ],
)
async def test_timeout_and_cancel_first_winner_owns_one_durable_cause(
    tmp_path,
    monkeypatch,
    first_origin,
    expected_code,
):
    import api.server as server
    from api.run_dispatch_repository import claim_run_dispatch
    from api.run_repository import create_run, get_run
    from api.task_tracker import get_active_task

    db_path = str(tmp_path / "tasks.db")
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", db_path)
    created = create_run(
        db_path=db_path,
        thread_id=f"first-wins-{first_origin}",
        query="query",
    )
    claim = claim_run_dispatch(
        db_path=db_path,
        worker_id=TEST_WORKER_ID,
        lease_seconds=30,
        run_id=created["run_id"],
    )
    assert claim is not None

    entered = asyncio.Event()
    callback_entered = asyncio.Event()
    release_callback = asyncio.Event()
    callbacks = []
    terminal_writes = []
    loop = asyncio.get_running_loop()
    real_loop_time = loop.time
    offset = [0.0]
    monkeypatch.setattr(loop, "time", lambda: real_loop_time() + offset[0])

    async def hangs(*_args, **_kwargs):
        entered.set()
        await asyncio.Event().wait()

    real_finalize = server.finalize_run_transaction

    def record_terminal_write(**kwargs):
        terminal_writes.append(kwargs["failure_cause"].code)
        return real_finalize(**kwargs)

    stage = server._RunStage()
    origin = server.TerminationOrigin()
    checkpoint = server.FinalizationCheckpoint()
    outcome_box = server.OutcomeBox()

    async def on_timeout(_task_id, timeout_seconds):
        callbacks.append("timeout")
        callback_entered.set()
        await release_callback.wait()
        await server._mark_dispatched_timeout(
            claim,
            db_path=db_path,
            outcome_box=outcome_box,
            timeout_seconds=timeout_seconds,
            stage=stage,
            termination_origin=origin,
        )

    async def on_cancel(_task_id):
        callbacks.append("cancelled")
        callback_entered.set()
        await release_callback.wait()
        await server._mark_dispatched_cancellation(
            claim,
            db_path=db_path,
            outcome_box=outcome_box,
            stage=stage,
            termination_origin=origin,
        )

    monkeypatch.setattr(server, "run_deep_agent", hangs)
    monkeypatch.setattr(server, "finalize_run_transaction", record_terminal_write)
    task_id = f"{claim.run_id}:first-wins:{claim.attempt_count}"
    task = server.create_tracked_task(
        server._run_dispatched_with_persistence(
            claim,
            db_path=db_path,
            outcome_box=outcome_box,
            stage=stage,
            termination_origin=origin,
            finalization_checkpoint=checkpoint,
        ),
        task_id,
        timeout_seconds=10,
        on_timeout=on_timeout,
        on_cancel=on_cancel,
        termination_origin=origin,
        finalization_checkpoint=checkpoint,
    )

    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        if first_origin == "timeout":
            offset[0] = 100.0
        else:
            task.cancel()
        await asyncio.wait_for(callback_entered.wait(), timeout=1)
        assert origin.value == first_origin

        if first_origin == "timeout":
            task.cancel()
        else:
            offset[0] = 100.0
            await asyncio.sleep(0)
        release_callback.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release_callback.set()
        if not task.done():
            task.cancel()
        try:
            await task
        except BaseException:
            pass
    await asyncio.sleep(0)

    assert callbacks == [first_origin]
    assert terminal_writes == [expected_code]
    assert stage.value == "execution"
    assert get_active_task(task_id) is None
    run = get_run(db_path=db_path, run_id=created["run_id"])
    assert run["execution_status"] == "failed"
    assert run["state_version"] == 2
    assert run["segments"][0]["status"] == "failed"
    assert run["failure_cause"]["phase"] == "execution"
    assert run["failure_cause"]["code"] == expected_code

    connection = sqlite3.connect(db_path)
    try:
        cause_rows = connection.execute(
            """
            SELECT observation_status, terminal_state_version, phase, code
            FROM run_failure_causes_v1
            WHERE run_id = ?
            """,
            (created["run_id"],),
        ).fetchall()
    finally:
        connection.close()
    assert cause_rows == [("observed", 2, "execution", expected_code)]


@pytest.mark.asyncio
async def test_artifact_construction_failure_is_finalization_failure(
    tmp_path,
    monkeypatch,
):
    import api.server as server
    from agent.run_result import AgentRunResult
    from api.run_repository import create_run, get_run

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    created = create_run(thread_id="artifact-failure", query="query")

    async def completed(*_args, **_kwargs):
        return AgentRunResult(
            thread_id=created["thread_id"],
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            query="query",
            session_dir=tmp_path,
        )

    monkeypatch.setattr(server, "run_deep_agent", completed)
    monkeypatch.setattr(
        server,
        "build_generic_result_artifact",
        lambda _result: (_ for _ in ()).throw(RuntimeError("artifact failed")),
    )

    with pytest.raises(RuntimeError, match="artifact failed"):
        await _run_v2_with_dispatch(
            server,
            query="query",
            thread_id=created["thread_id"],
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            outcome_box=server.OutcomeBox(),
        )

    run = get_run(run_id=created["run_id"])
    assert run["failure_cause"]["phase"] == "finalization"
    assert run["failure_cause"]["code"] == "run_finalization_failed"
    assert run["artifacts"] == []


@pytest.mark.asyncio
async def test_terminal_rollback_permits_finalization_failure_fallback(
    tmp_path,
    monkeypatch,
):
    import api.server as server
    from agent.harness_contracts import ReportCandidate
    from agent.run_result import AgentRunResult
    from api.run_repository import create_run, get_run
    from pathlib import PurePosixPath

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    created = create_run(thread_id="terminal-rollback", query="query")

    async def completed(*_args, **_kwargs):
        return AgentRunResult(
            thread_id=created["thread_id"],
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            query="query",
            session_dir=tmp_path,
            report_candidate=ReportCandidate(
                path=PurePosixPath("/workspace/research-report.md"),
                content="# Result",
            ),
        )

    real_finalize = server.finalize_run_transaction
    calls = []

    def fail_first_terminal(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("terminal transaction rolled back")
        return real_finalize(**kwargs)

    monkeypatch.setattr(server, "run_deep_agent", completed)
    monkeypatch.setattr(server, "finalize_run_transaction", fail_first_terminal)

    with pytest.raises(RuntimeError, match="terminal transaction rolled back"):
        await _run_v2_with_dispatch(
            server,
            query="query",
            thread_id=created["thread_id"],
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            outcome_box=server.OutcomeBox(),
        )

    assert len(calls) == 2
    run = get_run(run_id=created["run_id"])
    assert run["failure_cause"]["phase"] == "finalization"
    assert run["failure_cause"]["code"] == "run_finalization_failed"
    assert run["artifacts"] == []


@pytest.mark.asyncio
async def test_committed_terminal_transaction_wins_over_late_cancellation(
    tmp_path,
    monkeypatch,
):
    import api.server as server
    from agent.harness_contracts import ReportCandidate
    from agent.run_result import AgentRunResult
    from api.run_repository import create_run, get_run
    from pathlib import PurePosixPath

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    created = create_run(thread_id="terminal-commit", query="query")
    committed = threading.Event()
    release = threading.Event()

    async def completed(*_args, **_kwargs):
        return AgentRunResult(
            thread_id=created["thread_id"],
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            query="query",
            session_dir=tmp_path,
            report_candidate=ReportCandidate(
                path=PurePosixPath("/workspace/research-report.md"),
                content="# Result",
            ),
        )

    real_finalize = server.finalize_run_transaction

    def commit_then_hold(**kwargs):
        result = real_finalize(**kwargs)
        committed.set()
        assert release.wait(timeout=3)
        return result

    monkeypatch.setattr(server, "run_deep_agent", completed)
    monkeypatch.setattr(server, "finalize_run_transaction", commit_then_hold)
    task, _, _, _ = await _start_run_v2_with_dispatch(
        server,
        query="query",
        thread_id=created["thread_id"],
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        outcome_box=server.OutcomeBox(),
    )
    assert await asyncio.to_thread(committed.wait, 1)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    run = get_run(run_id=created["run_id"])
    assert run["execution_status"] == "completed"
    assert run["failure_cause"] is None
    assert [artifact["artifact_id"] for artifact in run["artifacts"]] == [
        "research-report.md"
    ]


@pytest.mark.asyncio
async def test_committed_terminal_transaction_wins_over_late_timeout(
    tmp_path,
    monkeypatch,
):
    import api.server as server
    from agent.harness_contracts import ReportCandidate
    from agent.run_result import AgentRunResult
    from api.run_repository import create_run, get_run
    from pathlib import PurePosixPath

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    created = create_run(thread_id="terminal-timeout", query="query")
    loop = asyncio.get_running_loop()
    real_loop_time = loop.time
    offset = [0.0]
    monkeypatch.setattr(loop, "time", lambda: real_loop_time() + offset[0])
    committed = threading.Event()
    release = threading.Event()

    async def completed(*_args, **_kwargs):
        return AgentRunResult(
            thread_id=created["thread_id"],
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            query="query",
            session_dir=tmp_path,
            report_candidate=ReportCandidate(
                path=PurePosixPath("/workspace/research-report.md"),
                content="# Result",
            ),
        )

    real_finalize = server.finalize_run_transaction

    def commit_then_expire_deadline(**kwargs):
        result = real_finalize(**kwargs)
        offset[0] = 100.0
        committed.set()
        assert release.wait(timeout=3)
        return result

    monkeypatch.setattr(server, "run_deep_agent", completed)
    monkeypatch.setattr(
        server,
        "finalize_run_transaction",
        commit_then_expire_deadline,
    )
    task, _, origin, _ = await _start_run_v2_with_dispatch(
        server,
        query="query",
        thread_id=created["thread_id"],
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        outcome_box=server.OutcomeBox(),
        timeout_seconds=10,
    )
    assert await asyncio.to_thread(committed.wait, 1)
    try:
        for _ in range(10):
            if origin.value == "timeout":
                break
            await asyncio.sleep(0)
        assert origin.value == "timeout"
        assert not task.done()
    finally:
        release.set()
    assert await task is None

    run = get_run(run_id=created["run_id"])
    assert run["execution_status"] == "completed"
    assert run["failure_cause"] is None
    assert [artifact["artifact_id"] for artifact in run["artifacts"]] == [
        "research-report.md"
    ]


@pytest.mark.asyncio
async def test_stale_terminal_result_creates_no_fallback_cause(
    tmp_path,
    monkeypatch,
):
    import api.server as server
    from agent.harness_contracts import ReportCandidate
    from agent.run_result import AgentRunResult
    from api.run_failure_cause_models import RunFailureCauseWrite
    from api.run_repository import create_run, get_run
    from pathlib import PurePosixPath

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    created = create_run(thread_id="terminal-stale", query="query")

    async def completed(*_args, **_kwargs):
        return AgentRunResult(
            thread_id=created["thread_id"],
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            query="query",
            session_dir=tmp_path,
            report_candidate=ReportCandidate(
                path=PurePosixPath("/workspace/research-report.md"),
                content="# Result",
            ),
        )

    real_finalize = server.finalize_run_transaction
    calls = []

    def install_winner_then_return_real_stale(**kwargs):
        calls.append(kwargs)
        assert real_finalize(
            run_id=kwargs["run_id"],
            segment_id=kwargs["segment_id"],
            expected_state_version=kwargs["expected_state_version"],
            allowed_previous_statuses=kwargs["allowed_previous_statuses"],
            execution_status="failed",
            delivery_status="failed",
            evidence_entries=[],
            failure_cause=RunFailureCauseWrite(
                phase="execution",
                code="execution_error",
            ),
            db_path=kwargs.get("db_path"),
        )
        return real_finalize(**kwargs)

    monkeypatch.setattr(server, "run_deep_agent", completed)
    monkeypatch.setattr(
        server,
        "finalize_run_transaction",
        install_winner_then_return_real_stale,
    )
    await _run_v2_with_dispatch(
        server,
        query="query",
        thread_id=created["thread_id"],
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        outcome_box=server.OutcomeBox(),
    )

    assert len(calls) == 1
    run = get_run(run_id=created["run_id"])
    assert run["failure_cause"]["phase"] == "execution"
    assert run["failure_cause"]["code"] == "execution_error"
    assert run["artifacts"] == []


@pytest.mark.asyncio
async def test_checkpoint_expired_deadline_blocks_success_terminal_launch(
    tmp_path,
    monkeypatch,
):
    import api.server as server
    from agent.harness_contracts import ReportCandidate
    from agent.run_result import AgentRunResult
    from api.run_repository import create_run, get_run
    from pathlib import PurePosixPath

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    created = create_run(thread_id="checkpoint-timeout", query="query")
    loop = asyncio.get_running_loop()
    real_loop_time = loop.time
    offset = [0.0]
    monkeypatch.setattr(loop, "time", lambda: real_loop_time() + offset[0])

    async def completed(*_args, **_kwargs):
        return AgentRunResult(
            thread_id=created["thread_id"],
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            query="query",
            session_dir=tmp_path,
            report_candidate=ReportCandidate(
                path=PurePosixPath("/workspace/research-report.md"),
                content="# Result",
            ),
        )

    real_builder = server.build_generic_result_artifact

    def advance_deadline(result):
        artifact = real_builder(result)
        offset[0] = 100.0
        return artifact

    monkeypatch.setattr(server, "run_deep_agent", completed)
    monkeypatch.setattr(server, "build_generic_result_artifact", advance_deadline)
    await _run_v2_with_dispatch(
        server,
        query="query",
        thread_id=created["thread_id"],
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        outcome_box=server.OutcomeBox(),
        timeout_seconds=10,
    )

    run = get_run(run_id=created["run_id"])
    assert run["failure_cause"]["phase"] == "finalization"
    assert run["failure_cause"]["code"] == "run_timeout"
    assert run["artifacts"] == []


@pytest.mark.asyncio
async def test_checkpoint_explicit_cancellation_blocks_success_terminal_launch(
    tmp_path,
    monkeypatch,
):
    import api.server as server
    from agent.harness_contracts import ReportCandidate
    from agent.run_result import AgentRunResult
    from api.run_repository import create_run, get_run
    from pathlib import PurePosixPath

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    created = create_run(thread_id="checkpoint-cancel", query="query")

    async def completed(*_args, **_kwargs):
        return AgentRunResult(
            thread_id=created["thread_id"],
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            query="query",
            session_dir=tmp_path,
            report_candidate=ReportCandidate(
                path=PurePosixPath("/workspace/research-report.md"),
                content="# Result",
            ),
        )

    monkeypatch.setattr(server, "run_deep_agent", completed)
    task, _, _, checkpoint = await _start_run_v2_with_dispatch(
        server,
        query="query",
        thread_id=created["thread_id"],
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        outcome_box=server.OutcomeBox(),
    )
    await asyncio.wait_for(checkpoint.wait_requested(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    run = get_run(run_id=created["run_id"])
    assert run["failure_cause"]["phase"] == "finalization"
    assert run["failure_cause"]["code"] == "cancelled"
    assert run["artifacts"] == []


@pytest.mark.asyncio
async def test_run_v2_routes_profile_id_to_agent_execution(tmp_path, monkeypatch):
    import api.server as server
    from agent.run_result import AgentRunResult
    from agent.talent_contracts import ResearchPacket
    from api.run_repository import create_run

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    captured = {}
    scope = {
        "target_roles": ["AI Agent Engineer"],
        "target_companies": [],
        "time_window": {"start": "2026-01-01", "end": "2026-06-12"},
        "declared_samples": [],
        "allowed_source_types": ["public_job_posting"],
        "research_questions": ["question-1"],
        "requested_outputs": ["decision_brief"],
    }
    created = create_run(
        thread_id="talent-thread",
        query="query",
        profile_id="talent-hiring-signal",
        scope=scope,
    )

    async def capture_agent(*args, **kwargs):
        captured.update(kwargs)
        return AgentRunResult(
            thread_id="talent-thread",
            query="query",
            session_dir=tmp_path,
            profile_id="talent-hiring-signal",
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            research_packets=[
                ResearchPacket(
                    packet_id="packet-1",
                    scope_id="scope-1",
                    findings=[],
                    candidate_claims=[],
                )
            ],
        )

    monkeypatch.setattr(server, "run_deep_agent", capture_agent)

    await _run_v2_with_dispatch(server,
        query="query",
        thread_id="talent-thread",
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        profile_id="talent-hiring-signal",
        scope=scope,
        outcome_box=server.OutcomeBox(),
    )

    assert captured["profile_id"] == "talent-hiring-signal"


@pytest.mark.asyncio
async def test_talent_run_persists_review_and_canonical_artifacts(tmp_path, monkeypatch):
    import api.server as server
    from agent.run_result import AgentRunResult
    from agent.talent_contracts import ResearchPacket
    from api.run_repository import create_run, get_run

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "false")
    scope = {
        "target_roles": ["AI Agent Engineer"],
        "target_companies": [],
        "time_window": {"start": "2026-01-01", "end": "2026-06-12"},
        "declared_samples": [],
        "allowed_source_types": ["public_job_posting"],
        "research_questions": ["question-1"],
        "requested_outputs": ["decision_brief"],
    }
    created = create_run(
        thread_id="talent-thread", query="query", profile_id="talent-hiring-signal",
        scope=scope,
    )
    packet = ResearchPacket(
        packet_id="packet-1",
        scope_id="scope-1",
        findings=[{
            "finding_id": "finding-1",
            "research_question_id": "question-1",
            "statement": "Signal",
            "evidence_refs": ["ev_missing"],
            "sample_scope": "declared",
            "confidence": 0.8,
        }],
        candidate_claims=[{
            "claim_id": "claim-1",
            "text": "Claim requiring review",
            "claim_type": "signal",
            "finding_refs": ["finding-1"],
            "evidence_refs": ["ev_missing"],
            "confidence": 0.8,
            "citation_status": "cited",
            "verification_status": "unverified",
            "review_status": "pending",
            "conflict_status": "none",
        }],
    )

    async def capture_agent(*args, **kwargs):
        return AgentRunResult(
            thread_id="talent-thread", query="query", session_dir=tmp_path,
            profile_id="talent-hiring-signal", run_id=created["run_id"],
            segment_id=created["segment_id"], research_packets=[packet],
        )

    monkeypatch.setattr(server, "run_deep_agent", capture_agent)
    await _run_v2_with_dispatch(server,
        query="query", thread_id="talent-thread", run_id=created["run_id"],
        segment_id=created["segment_id"], profile_id="talent-hiring-signal",
        scope=scope, outcome_box=server.OutcomeBox(),
    )

    run = get_run(run_id=created["run_id"])
    assert run["research_packets"][0]["packet_id"] == "packet-1"
    assert run["review_status"] == "required"
    assert run["delivery_status"] == "review_required"
    assert {item["artifact_id"] for item in run["artifacts"]} == {
        "decision-brief.json", "decision-brief.md",
    }
    assert run["review_workflow"] is None


@pytest.mark.asyncio
async def test_generic_run_persists_canonical_result_artifact(tmp_path, monkeypatch):
    import api.server as server
    from agent.harness_contracts import ReportCandidate
    from agent.run_result import AgentRunResult
    from api.run_repository import create_run, get_artifact, get_run
    from pathlib import PurePosixPath

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    created = create_run(
        thread_id="generic-thread",
        query="query",
        profile_id="generic",
    )

    async def capture_agent(*args, **kwargs):
        return AgentRunResult(
            thread_id="generic-thread",
            query="query",
            session_dir=tmp_path,
            profile_id="generic",
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            report_candidate=ReportCandidate(
                path=PurePosixPath("/workspace/research-report.md"),
                content="# Generic Report",
            ),
        )

    monkeypatch.setattr(server, "run_deep_agent", capture_agent)

    await _run_v2_with_dispatch(server,
        query="query",
        thread_id="generic-thread",
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        profile_id="generic",
        scope={},
        outcome_box=server.OutcomeBox(),
    )

    run = get_run(run_id=created["run_id"])
    assert run["execution_status"] == "completed"
    assert run["delivery_status"] == "ready"
    assert run["review_status"] == "not_required"
    assert [item["artifact_id"] for item in run["artifacts"]] == [
        "research-report.md"
    ]
    artifact = get_artifact(
        run_id=created["run_id"],
        artifact_id="research-report.md",
    )
    assert artifact["kind"] == "research_report_markdown"
    assert artifact["media_type"] == "text/markdown"
    assert artifact["content"] == "# Generic Report"


def test_run_artifact_api_resolves_by_run_and_artifact_id(tmp_path, monkeypatch):
    from api.run_repository import create_run, finalize_run_transaction

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    created = create_run(thread_id="thread-1", query="query")
    finalize_run_transaction(
        run_id=created["run_id"], segment_id=created["segment_id"],
        expected_state_version=0, allowed_previous_statuses={"pending"},
        execution_status="completed", delivery_status="ready", evidence_entries=[],
        artifacts=[{
            "artifact_id": "brief.md", "kind": "markdown", "media_type": "text/markdown",
            "content": "# Brief", "content_hash": "hash",
        }],
    )
    client = TestClient(app)

    response = client.get(
        f"/api/runs/{created['run_id']}/artifacts/brief.md", headers=AUTH_HEADERS
    )

    assert response.status_code == 200
    assert response.text == "# Brief"


def test_run_projection_exposes_current_publication_and_artifacts(
    tmp_path,
    monkeypatch,
):
    from tests.unit.test_publication_repository import (
        _accept_verification,
        _seed_talent_run,
    )
    from api.publication_repository import finalize_verification_publication
    from api.run_repository import get_run

    seeded = _seed_talent_run(tmp_path, migrate=True)
    _accept_verification(seeded)
    finalize_verification_publication(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        expected_state_version=get_run(
            db_path=seeded.db_path,
            run_id=seeded.run_id,
        )["state_version"],
    )
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", seeded.db_path)
    monkeypatch.setenv("API_SECRET", "test-integration-key")

    response = TestClient(app).get(
        f"/api/runs/{seeded.run_id}",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_publication"]["revision"] == 2
    assert {
        item["artifact_id"]
        for item in body["current_artifacts"]
    } == {
        "decision-brief.r2.json",
        "decision-brief.r2.md",
    }
    assert body["verification_summary"]["state_counts"] == {
        "verified": 1
    }


@pytest.mark.asyncio
async def test_mark_run_timeout_finalizes_nonterminal_run_with_frozen_evidence(
    tmp_path, monkeypatch
):
    import api.server as server
    from agent.research import EvidenceEntry
    from agent.run_result import AgentRunResult
    from api.run_repository import create_run, get_run, transition_run

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    events = []
    monkeypatch.setattr(
        server.monitor,
        "_emit",
        lambda *args, **kwargs: events.append((args, kwargs)),
    )
    created = create_run(thread_id="timeout-thread", query="query")
    assert transition_run(
        run_id=created["run_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="running",
    )
    evidence = EvidenceEntry(
        thread_id="timeout-thread",
        query_text="query",
        subagent_name="network_search",
        tool_name="tavily_search",
        source_url="https://example.com/source",
        source_identity="https://example.com/source",
        snippet="partial evidence",
        evidence_fingerprint="timeout-evidence",
    )
    outcome_box = server.OutcomeBox()
    outcome_box.publish(
        AgentRunResult(
            thread_id="timeout-thread",
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            query="query",
            session_dir=tmp_path,
            evidence_entries=[evidence],
        )
    )

    await server._mark_run_timeout(
        created["run_id"],
        7,
        segment_id=created["segment_id"],
        outcome_box=outcome_box,
    )

    run = get_run(run_id=created["run_id"])
    assert run["execution_status"] == "failed"
    assert run["delivery_status"] == "failed"
    assert [item["evidence_fingerprint"] for item in run["evidence"]] == [
        "timeout-evidence"
    ]
    assert run["artifacts"] == []
    assert events[0][0][0] == "run_timeout"
    assert events[0][1]["thread_id"] == "timeout-thread"
    assert events[0][1]["run_id"] == created["run_id"]
    assert events[0][1]["segment_id"] == created["segment_id"]


@pytest.mark.asyncio
async def test_tracked_run_timeout_reaches_persisted_failed_state(tmp_path, monkeypatch):
    import api.server as server
    from agent.research import EvidenceEntry
    from agent.run_result import AgentRunResult
    from api.run_repository import create_run, get_run

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    created = create_run(thread_id="timeout-thread", query="query")

    evidence = EvidenceEntry(
        thread_id=created["thread_id"],
        query_text="query",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url="https://example.com/timeout",
        source_identity="https://example.com/timeout",
        snippet="partial before timeout",
        evidence_fingerprint="partial-timeout-evidence",
    )

    async def hangs(*args, **kwargs):
        kwargs["outcome_box"].publish(
            AgentRunResult(
                thread_id=created["thread_id"],
                run_id=created["run_id"],
                segment_id=created["segment_id"],
                query="query",
                session_dir=tmp_path,
                evidence_entries=[evidence],
            )
        )
        await asyncio.Event().wait()

    monkeypatch.setattr(server, "run_deep_agent", hangs)
    outcome_box = server.OutcomeBox()
    await _run_v2_with_dispatch(server,
        query="query",
        thread_id="timeout-thread",
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        outcome_box=outcome_box,
        timeout_seconds=0.01,
        on_timeout=lambda run_id, timeout_seconds: server._mark_run_timeout(
            created["run_id"],
            timeout_seconds,
            segment_id=created["segment_id"],
            outcome_box=outcome_box,
        ),
    )

    run = get_run(run_id=created["run_id"])
    assert run["execution_status"] == "failed"
    assert run["delivery_status"] == "failed"
    assert run["failure_cause"]["phase"] == "execution"
    assert run["failure_cause"]["code"] == "run_timeout"
    assert [item["evidence_fingerprint"] for item in run["evidence"]] == [
        "partial-timeout-evidence"
    ]


def test_create_run_scheduler_failure_returns_ack_and_releases_for_retry(
    tmp_path, monkeypatch
):
    import api.server as server
    from api.run_repository import create_run as real_create_run, get_run

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    created_runs = []

    def capture_create_run(**kwargs):
        created = real_create_run(**kwargs)
        created_runs.append(created)
        return created

    def fail_to_schedule(*args, **kwargs):
        raise RuntimeError("scheduler unavailable")

    monkeypatch.setattr(server, "create_run", capture_create_run)
    monkeypatch.setattr(server, "create_tracked_task", fail_to_schedule)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/runs",
        json={"query": "research", "thread_id": "schedule-failure"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    runs = get_run(run_id=created_runs[0]["run_id"])
    assert runs["execution_status"] == "pending"
