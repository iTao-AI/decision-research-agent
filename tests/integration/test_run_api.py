import os
import asyncio

import pytest
from fastapi.testclient import TestClient

from api.server import app


AUTH_HEADERS = {"X-API-Key": "test-integration-key"}


def test_create_and_get_run_returns_distinct_thread_and_run_identity(
    tmp_path, monkeypatch
):
    import api.server as server

    monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "tasks.db"))
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
    assert scheduled[0][1] == created["run_id"]

    fetched = client.get(f"/api/runs/{created['run_id']}", headers=AUTH_HEADERS)
    assert fetched.status_code == 200
    assert fetched.json()["run_id"] == created["run_id"]
    server.active_run_threads.clear()


def test_create_run_does_not_depend_on_legacy_thread_guard(tmp_path, monkeypatch):
    import api.server as server

    monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    server.active_run_threads.add("thread-active")
    scheduled = []

    def capture_task(coroutine, task_id, **kwargs):
        scheduled.append(coroutine)

    monkeypatch.setattr(server, "create_tracked_task", capture_task)
    client = TestClient(app)

    response = client.post(
        "/api/runs",
        json={"query": "research", "thread_id": "thread-active"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["thread_id"] == "thread-active"
    assert "thread-active" in server.active_run_threads
    scheduled[0].close()
    server.active_run_threads.clear()


def test_create_run_rejects_unknown_profile_fail_closed(tmp_path, monkeypatch):
    import api.server as server

    monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    client = TestClient(app)

    response = client.post(
        "/api/runs",
        json={"query": "research", "profile_id": "unknown"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unknown_profile"
    server.active_run_threads.clear()


def test_create_talent_run_rejects_invalid_scope_before_scheduling(
    tmp_path, monkeypatch
):
    import api.server as server

    monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "tasks.db"))
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
    server.active_run_threads.clear()


def test_profile_manifest_exposes_policy_without_runtime_secrets():
    os.environ["API_SECRET"] = "test-integration-key"
    client = TestClient(app)

    response = client.get("/api/profiles/talent-hiring-signal", headers=AUTH_HEADERS)

    assert response.status_code == 200
    manifest = response.json()
    assert manifest["profile"]["profile_id"] == "talent-hiring-signal"
    assert manifest["harness_policy"]["allowed_tools"] == ["internet_search"]
    assert "api_key" not in str(manifest).lower()


@pytest.mark.asyncio
async def test_run_v2_cancellation_without_outcome_still_finalizes_failed(
    tmp_path, monkeypatch
):
    import api.server as server
    from api.run_repository import create_run, get_run

    monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "tasks.db"))
    created = create_run(thread_id="cancel-thread", query="query")
    server.active_run_threads.add("cancel-thread")

    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(server, "run_deep_agent", cancelled)

    with pytest.raises(asyncio.CancelledError):
        await server._run_v2_with_persistence(
            query="query",
            thread_id="cancel-thread",
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            outcome_box=server.OutcomeBox(),
        )

    run = get_run(run_id=created["run_id"])
    assert run["execution_status"] == "failed"
    assert run["delivery_status"] == "failed"
    assert "cancel-thread" in server.active_run_threads
    server.active_run_threads.clear()


def test_create_run_scheduler_failure_releases_guard_and_marks_run_failed(
    tmp_path, monkeypatch
):
    import api.server as server
    from api.run_repository import create_run as real_create_run, get_run

    monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    server.active_run_threads.clear()
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

    assert response.status_code == 500
    assert "schedule-failure" not in server.active_run_threads
    runs = get_run(run_id=created_runs[0]["run_id"])
    assert runs["execution_status"] == "failed"
