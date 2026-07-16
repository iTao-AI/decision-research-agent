import asyncio
from datetime import datetime, timedelta, timezone
import sqlite3

from fastapi.testclient import TestClient
import pytest

from api.run_dispatch_repository import (
    claim_run_dispatch,
    get_run_dispatch,
    start_run_dispatch,
)
from api.run_dispatch_worker import RunDispatchWorker
from api.run_repository import create_run, get_run
from api.server import app


AUTH_HEADERS = {"X-API-Key": "test-integration-key"}
WORKER_1 = "dispatch_worker_00000000000000000000000000000001"
WORKER_2 = "dispatch_worker_00000000000000000000000000000002"


def _dispatch_failure_snapshot(db_path, *, run_id, segment_id):
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        dispatch = connection.execute(
            """
            SELECT status, attempt_count, last_error_code, updated_at
            FROM run_dispatches_v1 WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        run = connection.execute(
            """
            SELECT execution_status, state_version, updated_at
            FROM research_runs_v2 WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        segment = connection.execute(
            "SELECT status, updated_at FROM run_segments WHERE segment_id = ?",
            (segment_id,),
        ).fetchone()
        cause = connection.execute(
            """
            SELECT observation_status, terminal_state_version, phase, code,
                   recorded_at
            FROM run_failure_causes_v1 WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
    finally:
        connection.close()
    return {
        "dispatch": dict(dispatch),
        "run": dict(run),
        "segment": dict(segment),
        "cause": dict(cause) if cause is not None else None,
    }


def _assert_dispatch_failure(snapshot, *, code):
    assert snapshot["dispatch"]["status"] == "failed"
    assert snapshot["dispatch"]["attempt_count"] == 3
    assert snapshot["dispatch"]["last_error_code"] == code
    assert snapshot["run"]["execution_status"] == "failed"
    assert snapshot["run"]["state_version"] == 1
    assert snapshot["segment"]["status"] == "failed"
    assert snapshot["cause"] is not None
    assert snapshot["cause"]["observation_status"] == "observed"
    assert snapshot["cause"]["terminal_state_version"] == 1
    assert snapshot["cause"]["phase"] == "dispatch"
    assert snapshot["cause"]["code"] == code
    assert {
        snapshot["dispatch"]["updated_at"],
        snapshot["run"]["updated_at"],
        snapshot["segment"]["updated_at"],
        snapshot["cause"]["recorded_at"],
    } == {snapshot["cause"]["recorded_at"]}


@pytest.mark.asyncio
async def test_lifespan_unconditionally_starts_and_stops_dispatch_worker(
    tmp_path,
    monkeypatch,
):
    import api.server as server

    db_path = str(tmp_path / "tasks.db")
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", db_path)
    migrations = []

    class FakeWorker:
        def __init__(self):
            self.started = asyncio.Event()
            self.stopped = False
            self.stop_event = asyncio.Event()

        async def run_forever(self):
            self.started.set()
            await self.stop_event.wait()

        def stop(self):
            self.stopped = True
            self.stop_event.set()

    worker = FakeWorker()
    monkeypatch.setattr(
        server,
        "migrate_with_backup",
        lambda **kwargs: migrations.append(kwargs) or {},
    )
    monkeypatch.setattr(
        server,
        "create_run_dispatch_worker",
        lambda application_db_path: worker,
        raising=False,
    )

    async with server.lifespan(server.app):
        await asyncio.wait_for(worker.started.wait(), timeout=1)
        assert server.app.state.run_dispatch_worker is worker
        assert server.app.state.run_dispatch_worker_task is not None

    assert worker.stopped is True
    assert migrations == [
        {
            "db_path": db_path,
            "backup_path": f"{db_path}.pre-run-dispatch.bak",
        }
    ]


@pytest.mark.asyncio
async def test_dispatched_wrapper_crosses_real_start_fence_before_agent_boundary(
    tmp_path,
    monkeypatch,
):
    import api.server as server

    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")
    claim = claim_run_dispatch(
        db_path=db_path,
        worker_id=WORKER_1,
        lease_seconds=30,
        run_id=created["run_id"],
    )
    entries = []

    async def fake_started(**kwargs):
        entries.append(kwargs["run_id"])

    monkeypatch.setattr(
        server,
        "_run_started_v2_with_persistence",
        fake_started,
        raising=False,
    )

    await server._run_dispatched_with_persistence(
        claim,
        db_path=db_path,
        outcome_box=server.OutcomeBox(),
    )

    assert entries == [created["run_id"]]
    assert get_run_dispatch(db_path=db_path, run_id=created["run_id"])["status"] == "started"
    assert get_run(db_path=db_path, run_id=created["run_id"])["execution_status"] == "running"


@pytest.mark.asyncio
async def test_same_owner_stale_attempt_stops_before_agent_boundary(
    tmp_path,
    monkeypatch,
):
    import api.server as server

    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")
    now = datetime(2026, 7, 14, tzinfo=timezone.utc)
    first = claim_run_dispatch(
        db_path=db_path,
        worker_id=WORKER_1,
        lease_seconds=30,
        run_id=created["run_id"],
        now=now,
    )
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                "UPDATE run_dispatches_v1 SET lease_expires_at = ? WHERE run_id = ?",
                ((now - timedelta(seconds=1)).isoformat(), created["run_id"]),
            )
    finally:
        connection.close()
    second = claim_run_dispatch(
        db_path=db_path,
        worker_id=WORKER_1,
        lease_seconds=30,
        run_id=created["run_id"],
        now=now + timedelta(minutes=1),
    )
    entries = []

    async def fake_started(**kwargs):
        entries.append(kwargs["run_id"])

    monkeypatch.setattr(server, "_run_started_v2_with_persistence", fake_started, raising=False)
    await server._run_dispatched_with_persistence(
        first,
        db_path=db_path,
        outcome_box=server.OutcomeBox(),
    )
    await server._run_dispatched_with_persistence(
        second,
        db_path=db_path,
        outcome_box=server.OutcomeBox(),
    )

    assert entries == [created["run_id"]]


@pytest.mark.asyncio
async def test_concurrent_workers_produce_one_fenced_agent_entry(tmp_path, monkeypatch):
    import api.server as server

    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")
    claims = []
    first = RunDispatchWorker(
        db_path=db_path,
        scheduler=claims.append,
        worker_id=WORKER_1,
    )
    second = RunDispatchWorker(
        db_path=db_path,
        scheduler=claims.append,
        worker_id=WORKER_2,
    )
    await asyncio.gather(
        first.dispatch_run(created["run_id"]),
        second.dispatch_run(created["run_id"]),
    )
    entries = []

    async def fake_started(**kwargs):
        entries.append(kwargs["run_id"])

    monkeypatch.setattr(server, "_run_started_v2_with_persistence", fake_started, raising=False)
    await asyncio.gather(
        *[
            server._run_dispatched_with_persistence(
                claim,
                db_path=db_path,
                outcome_box=server.OutcomeBox(),
            )
            for claim in claims
        ]
    )

    assert len(claims) == 1
    assert entries == [created["run_id"]]


@pytest.mark.asyncio
async def test_stale_timeout_does_not_change_newer_started_attempt(tmp_path, monkeypatch):
    import api.server as server

    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")
    now = datetime(2026, 7, 14, tzinfo=timezone.utc)
    first = claim_run_dispatch(
        db_path=db_path,
        worker_id=WORKER_1,
        lease_seconds=30,
        run_id=created["run_id"],
        now=now,
    )
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                "UPDATE run_dispatches_v1 SET lease_expires_at = ? WHERE run_id = ?",
                ((now - timedelta(seconds=1)).isoformat(), created["run_id"]),
            )
    finally:
        connection.close()
    second = claim_run_dispatch(
        db_path=db_path,
        worker_id=WORKER_2,
        lease_seconds=30,
        run_id=created["run_id"],
        now=now + timedelta(minutes=1),
    )
    assert start_run_dispatch(db_path=db_path, claim=second) is True
    monkeypatch.setattr(
        server,
        "_mark_run_timeout",
        lambda *args, **kwargs: pytest.fail("stale timeout must not mark run"),
    )

    await server._mark_dispatched_timeout(
        first,
        db_path=db_path,
        outcome_box=server.OutcomeBox(),
        timeout_seconds=1,
    )

    assert get_run_dispatch(db_path=db_path, run_id=created["run_id"])["status"] == "started"
    assert get_run(db_path=db_path, run_id=created["run_id"])["execution_status"] == "running"


@pytest.mark.asyncio
async def test_same_attempt_start_between_timeout_read_and_release_is_not_orphaned(
    tmp_path,
    monkeypatch,
):
    import api.server as server
    from api.run_dispatch_repository import (
        reconcile_run_dispatch_timeout as real_timeout_reconciliation,
    )

    db_path = str(tmp_path / "tasks.db")
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", db_path)
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")
    claim = claim_run_dispatch(
        db_path=db_path,
        worker_id=WORKER_1,
        lease_seconds=30,
        run_id=created["run_id"],
    )

    def start_before_timeout_reconciliation(**kwargs):
        assert start_run_dispatch(db_path=db_path, claim=claim) is True
        return real_timeout_reconciliation(**kwargs)

    monkeypatch.setattr(
        server,
        "reconcile_run_dispatch_timeout",
        start_before_timeout_reconciliation,
    )

    await server._mark_dispatched_timeout(
        claim,
        db_path=db_path,
        outcome_box=server.OutcomeBox(),
        timeout_seconds=1,
    )

    snapshot = _dispatch_failure_snapshot(
        db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
    )
    assert snapshot["dispatch"]["status"] == "started"
    assert snapshot["run"]["execution_status"] == "failed"
    assert snapshot["cause"] is None or snapshot["cause"]["phase"] != "dispatch"


@pytest.mark.asyncio
async def test_third_pre_start_timeout_records_dispatch_cause(tmp_path):
    import api.server as server

    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")

    for attempt in (1, 2, 3):
        claim = claim_run_dispatch(
            db_path=db_path,
            worker_id=WORKER_1,
            lease_seconds=30,
            run_id=created["run_id"],
            now=datetime(2026, 7, 14, attempt, tzinfo=timezone.utc),
        )
        await server._mark_dispatched_timeout(
            claim,
            db_path=db_path,
            outcome_box=server.OutcomeBox(),
            timeout_seconds=1,
        )

    snapshot = _dispatch_failure_snapshot(
        db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
    )
    _assert_dispatch_failure(snapshot, code="run_dispatch_start_timeout")


@pytest.mark.asyncio
async def test_third_start_failure_records_dispatch_cause(tmp_path, monkeypatch):
    import api.server as server

    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")

    def fail_start(**_kwargs):
        raise RuntimeError("start fence unavailable")

    monkeypatch.setattr(server, "start_run_dispatch", fail_start)
    monkeypatch.setattr(
        server,
        "_run_started_v2_with_persistence",
        lambda **_kwargs: pytest.fail("failed start must not enter the agent"),
    )
    for attempt in (1, 2, 3):
        claim = claim_run_dispatch(
            db_path=db_path,
            worker_id=WORKER_1,
            lease_seconds=30,
            run_id=created["run_id"],
            now=datetime(2026, 7, 14, attempt, tzinfo=timezone.utc),
        )
        await server._run_dispatched_with_persistence(
            claim,
            db_path=db_path,
            outcome_box=server.OutcomeBox(),
        )

    snapshot = _dispatch_failure_snapshot(
        db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
    )
    _assert_dispatch_failure(snapshot, code="run_dispatch_start_failed")


def test_route_post_commit_dispatch_failure_still_returns_ack(tmp_path, monkeypatch):
    import api.server as server

    db_path = str(tmp_path / "tasks.db")
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", db_path)
    monkeypatch.setenv("API_SECRET", "test-integration-key")

    class NonSchedulingWorker:
        def __init__(self):
            self.stop_event = asyncio.Event()

        async def run_forever(self):
            await self.stop_event.wait()

        async def dispatch_run(self, _run_id):
            return False

        def wake(self):
            pass

        def stop(self):
            self.stop_event.set()

    worker = NonSchedulingWorker()
    monkeypatch.setattr(server, "create_run_dispatch_worker", lambda _path: worker, raising=False)

    with TestClient(app) as client:
        response = client.post(
            "/api/runs",
            json={"query": "research", "thread_id": "thread-1"},
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    assert set(response.json()) == {"status", "thread_id", "run_id", "segment_id"}
    assert response.json()["status"] == "started"
    assert get_run_dispatch(db_path=db_path, run_id=response.json()["run_id"])["status"] == "pending"


def test_schedule_uses_attempt_qualified_task_id(tmp_path, monkeypatch):
    import api.server as server

    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")
    claim = claim_run_dispatch(
        db_path=db_path,
        worker_id=WORKER_1,
        lease_seconds=30,
        run_id=created["run_id"],
    )
    captured = []

    def capture(coroutine, task_id, **kwargs):
        captured.append((coroutine, task_id, kwargs))

    monkeypatch.setattr(server, "create_tracked_task", capture)
    server._schedule_run_dispatch(claim, db_path=db_path)
    coroutine, task_id, kwargs = captured[0]
    try:
        assert task_id == f"{claim.run_id}:dispatch:{claim.attempt_count}"
        assert callable(kwargs["on_timeout"])
    finally:
        coroutine.close()


@pytest.mark.asyncio
async def test_completed_stale_attempt_cannot_remove_newer_tracked_attempt(
    tmp_path,
    monkeypatch,
):
    import api.server as server
    from api.task_tracker import clear_active_tasks, get_active_task

    clear_active_tasks()
    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")
    now = datetime(2026, 7, 14, tzinfo=timezone.utc)
    first = claim_run_dispatch(
        db_path=db_path,
        worker_id=WORKER_1,
        lease_seconds=30,
        run_id=created["run_id"],
        now=now,
    )
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                "UPDATE run_dispatches_v1 SET lease_expires_at = ? WHERE run_id = ?",
                ((now - timedelta(seconds=1)).isoformat(), created["run_id"]),
            )
    finally:
        connection.close()
    second = claim_run_dispatch(
        db_path=db_path,
        worker_id=WORKER_2,
        lease_seconds=30,
        run_id=created["run_id"],
        now=now + timedelta(minutes=1),
    )
    releases = {1: asyncio.Event(), 2: asyncio.Event()}

    async def hold_attempt(claim, **_kwargs):
        await releases[claim.attempt_count].wait()

    monkeypatch.setattr(server, "_run_dispatched_with_persistence", hold_attempt)
    server._schedule_run_dispatch(first, db_path=db_path)
    server._schedule_run_dispatch(second, db_path=db_path)
    first_id = f"{created['run_id']}:dispatch:1"
    second_id = f"{created['run_id']}:dispatch:2"
    assert get_active_task(first_id) is not None
    assert get_active_task(second_id) is not None

    releases[1].set()
    await get_active_task(first_id)
    await asyncio.sleep(0)
    assert get_active_task(first_id) is None
    assert get_active_task(second_id) is not None

    releases[2].set()
    await get_active_task(second_id)
    await asyncio.sleep(0)
    assert get_active_task(second_id) is None
