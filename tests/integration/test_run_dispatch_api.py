import asyncio
from datetime import datetime, timedelta, timezone
import sqlite3
import threading

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
pytestmark = pytest.mark.usefixtures("authenticated_runtime_access")
WORKER_1 = "dispatch_worker_00000000000000000000000000000001"
WORKER_2 = "dispatch_worker_00000000000000000000000000000002"


def _runtime_owners(server):
    return (
        server._RunStage(),
        server.TerminationOrigin(),
        server.FinalizationCheckpoint(),
    )


async def _run_dispatched(server, claim, *, db_path, outcome_box=None):
    stage, origin, checkpoint = _runtime_owners(server)
    await server._run_dispatched_with_persistence(
        claim,
        db_path=db_path,
        outcome_box=outcome_box or server.OutcomeBox(),
        stage=stage,
        termination_origin=origin,
        finalization_checkpoint=checkpoint,
    )


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

    await _run_dispatched(
        server,
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
    await _run_dispatched(
        server,
        first,
        db_path=db_path,
        outcome_box=server.OutcomeBox(),
    )
    await _run_dispatched(
        server,
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
            _run_dispatched(
                server,
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
        await _run_dispatched(
            server,
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
    inner = {}

    async def placeholder():
        return None

    def capture_inner(_claim, **kwargs):
        inner.update(kwargs)
        return placeholder()

    def capture(coroutine, task_id, **kwargs):
        captured.append((coroutine, task_id, kwargs))

    monkeypatch.setattr(server, "_run_dispatched_with_persistence", capture_inner)
    monkeypatch.setattr(server, "create_tracked_task", capture)
    server._schedule_run_dispatch(claim, db_path=db_path)
    coroutine, task_id, kwargs = captured[0]
    try:
        assert task_id == f"{claim.run_id}:dispatch:{claim.attempt_count}"
        assert callable(kwargs["on_timeout"])
        assert callable(kwargs["on_cancel"])
        assert kwargs["termination_origin"] is inner["termination_origin"]
        assert kwargs["finalization_checkpoint"] is inner["finalization_checkpoint"]
        assert inner["stage"].value == "dispatch"
        assert inner["outcome_box"] is not None
    finally:
        coroutine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("termination_kind", "expected_code"),
    [
        ("timeout", "run_timeout"),
        ("cancelled", "cancelled"),
    ],
)
async def test_scheduler_created_task_reaches_real_finalization_checkpoint(
    tmp_path,
    monkeypatch,
    termination_kind,
    expected_code,
):
    import api.server as server
    from agent.harness_contracts import ReportCandidate
    from agent.run_result import AgentRunResult
    from api.task_tracker import DEFAULT_TASK_TIMEOUT, get_active_task
    from pathlib import PurePosixPath

    db_path = str(tmp_path / "tasks.db")
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", db_path)
    created = create_run(
        db_path=db_path,
        thread_id=f"scheduler-checkpoint-{termination_kind}",
        query="query",
    )
    claim = claim_run_dispatch(
        db_path=db_path,
        worker_id=WORKER_1,
        lease_seconds=30,
        run_id=created["run_id"],
    )
    assert claim is not None

    checkpoints = []
    origins = []
    callbacks = []
    terminal_writes = []
    real_checkpoint_type = server.FinalizationCheckpoint
    real_origin_type = server.TerminationOrigin

    class GatedTrackerCheckpoint(real_checkpoint_type):
        def __init__(self):
            super().__init__()
            self.tracker_waiting = asyncio.Event()
            self.release_tracker = asyncio.Event()
            checkpoints.append(self)

        async def wait_requested(self):
            await super().wait_requested()
            self.tracker_waiting.set()
            await self.release_tracker.wait()

    class ObservableOrigin(real_origin_type):
        def __init__(self):
            super().__init__()
            origins.append(self)

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

    real_timeout_callback = server._mark_dispatched_timeout
    real_cancel_callback = server._mark_dispatched_cancellation
    real_finalize = server.finalize_run_transaction

    async def record_timeout_callback(*args, **kwargs):
        callbacks.append("timeout")
        return await real_timeout_callback(*args, **kwargs)

    async def record_cancel_callback(*args, **kwargs):
        callbacks.append("cancelled")
        return await real_cancel_callback(*args, **kwargs)

    def record_terminal_write(**kwargs):
        cause = kwargs["failure_cause"]
        terminal_writes.append(
            (
                kwargs["execution_status"],
                cause.phase if cause is not None else None,
                cause.code if cause is not None else None,
            )
        )
        return real_finalize(**kwargs)

    loop = asyncio.get_running_loop()
    real_loop_time = loop.time
    offset = [0.0]
    monkeypatch.setattr(loop, "time", lambda: real_loop_time() + offset[0])
    monkeypatch.setattr(server, "FinalizationCheckpoint", GatedTrackerCheckpoint)
    monkeypatch.setattr(server, "TerminationOrigin", ObservableOrigin)
    monkeypatch.setattr(server, "run_deep_agent", completed)
    monkeypatch.setattr(server, "_mark_dispatched_timeout", record_timeout_callback)
    monkeypatch.setattr(
        server,
        "_mark_dispatched_cancellation",
        record_cancel_callback,
    )
    monkeypatch.setattr(server, "finalize_run_transaction", record_terminal_write)

    task_id = f"{claim.run_id}:dispatch:{claim.attempt_count}"
    server._schedule_run_dispatch(claim, db_path=db_path)
    task = get_active_task(task_id)
    assert task is not None
    checkpoint = checkpoints[0] if checkpoints else None
    origin = origins[0] if origins else None

    try:
        assert len(checkpoints) == len(origins) == 1
        assert checkpoint is not None
        assert origin is not None
        await asyncio.wait_for(checkpoint.tracker_waiting.wait(), timeout=1)
        if termination_kind == "timeout":
            offset[0] = float(DEFAULT_TASK_TIMEOUT + 1)
            checkpoint.release_tracker.set()
            assert await asyncio.wait_for(asyncio.shield(task), timeout=2) is None
        else:
            task.cancel()
            for _ in range(100):
                if origin.value == "cancelled":
                    break
                await asyncio.sleep(0)
            assert origin.value == "cancelled"
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(task), timeout=2)
    finally:
        for item in checkpoints:
            item.release_tracker.set()
        if not task.done():
            task.cancel()
        try:
            await task
        except BaseException:
            pass
    await asyncio.sleep(0)

    assert origin is not None
    assert origin.value == termination_kind
    assert callbacks == [termination_kind]
    assert terminal_writes == [("failed", "finalization", expected_code)]
    assert get_active_task(task_id) is None
    run = get_run(db_path=db_path, run_id=created["run_id"])
    assert run["execution_status"] == "failed"
    assert run["state_version"] == 2
    assert run["segments"][0]["status"] == "failed"
    assert run["failure_cause"]["phase"] == "finalization"
    assert run["failure_cause"]["code"] == expected_code
    assert run["artifacts"] == []


@pytest.mark.asyncio
async def test_late_committed_start_uses_post_start_cancellation_semantics(
    tmp_path,
    monkeypatch,
):
    import api.server as server
    from api.task_tracker import create_tracked_task, get_active_task

    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="late-start", query="query")
    claim = claim_run_dispatch(
        db_path=db_path,
        worker_id=WORKER_1,
        lease_seconds=30,
        run_id=created["run_id"],
    )
    start_committed = threading.Event()
    release_start = threading.Event()
    real_start = server.start_run_dispatch

    def commit_then_hold(**kwargs):
        assert real_start(**kwargs) is True
        start_committed.set()
        assert release_start.wait(timeout=3)
        return True

    monkeypatch.setattr(server, "start_run_dispatch", commit_then_hold)
    monkeypatch.setattr(
        server,
        "_run_started_v2_with_persistence",
        lambda **_kwargs: pytest.fail("cancelled late start must not enter Agent"),
    )
    stage, origin, checkpoint = _runtime_owners(server)
    outcome_box = server.OutcomeBox()
    task_id = f"{claim.run_id}:dispatch:{claim.attempt_count}"
    task = create_tracked_task(
        server._run_dispatched_with_persistence(
            claim,
            db_path=db_path,
            outcome_box=outcome_box,
            stage=stage,
            termination_origin=origin,
            finalization_checkpoint=checkpoint,
        ),
        task_id,
        on_cancel=lambda _task_id: server._mark_dispatched_cancellation(
            claim,
            db_path=db_path,
            outcome_box=outcome_box,
            stage=stage,
            termination_origin=origin,
        ),
        termination_origin=origin,
        finalization_checkpoint=checkpoint,
    )

    assert await asyncio.to_thread(start_committed.wait, 1)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release_start.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)

    snapshot = _dispatch_failure_snapshot(
        db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
    )
    assert snapshot["dispatch"]["status"] == "started"
    assert snapshot["run"]["execution_status"] == "failed"
    assert snapshot["run"]["state_version"] == 2
    assert snapshot["cause"]["phase"] == "execution"
    assert snapshot["cause"]["code"] == "cancelled"
    assert stage.value == "execution"
    assert origin.value == "cancelled"
    assert get_active_task(task_id) is None


@pytest.mark.asyncio
async def test_late_committed_start_uses_post_start_timeout_semantics(
    tmp_path,
    monkeypatch,
):
    import api.server as server
    from api.task_tracker import create_tracked_task

    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="late-start-timeout", query="query")
    claim = claim_run_dispatch(
        db_path=db_path,
        worker_id=WORKER_1,
        lease_seconds=30,
        run_id=created["run_id"],
    )
    loop = asyncio.get_running_loop()
    real_loop_time = loop.time
    offset = [0.0]
    monkeypatch.setattr(loop, "time", lambda: real_loop_time() + offset[0])
    start_committed = threading.Event()
    release_start = threading.Event()
    real_start = server.start_run_dispatch

    def commit_then_expire_deadline(**kwargs):
        assert real_start(**kwargs) is True
        offset[0] = 100.0
        start_committed.set()
        assert release_start.wait(timeout=3)
        return True

    monkeypatch.setattr(server, "start_run_dispatch", commit_then_expire_deadline)
    monkeypatch.setattr(
        server,
        "_run_started_v2_with_persistence",
        lambda **_kwargs: pytest.fail("timed-out late start must not enter Agent"),
    )
    stage, origin, checkpoint = _runtime_owners(server)
    outcome_box = server.OutcomeBox()
    task = create_tracked_task(
        server._run_dispatched_with_persistence(
            claim,
            db_path=db_path,
            outcome_box=outcome_box,
            stage=stage,
            termination_origin=origin,
            finalization_checkpoint=checkpoint,
        ),
        f"{claim.run_id}:dispatch:{claim.attempt_count}",
        timeout_seconds=10,
        on_timeout=lambda _task_id, timeout_seconds: server._mark_dispatched_timeout(
            claim,
            db_path=db_path,
            outcome_box=outcome_box,
            timeout_seconds=timeout_seconds,
            stage=stage,
            termination_origin=origin,
        ),
        termination_origin=origin,
        finalization_checkpoint=checkpoint,
    )

    assert await asyncio.to_thread(start_committed.wait, 1)
    try:
        for _ in range(10):
            if origin.value == "timeout":
                break
            await asyncio.sleep(0)
        assert origin.value == "timeout"
        assert not task.done()
    finally:
        release_start.set()
    assert await task is None

    snapshot = _dispatch_failure_snapshot(
        db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
    )
    assert snapshot["dispatch"]["status"] == "started"
    assert snapshot["run"]["execution_status"] == "failed"
    assert snapshot["run"]["state_version"] == 2
    assert snapshot["cause"]["phase"] == "execution"
    assert snapshot["cause"]["code"] == "run_timeout"
    assert stage.value == "execution"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("attempt_count", "expected_dispatch_status"),
    [(1, "pending"), (2, "pending"), (3, "leased")],
)
async def test_pre_start_cancellation_retries_or_defers_without_public_cause(
    tmp_path,
    monkeypatch,
    attempt_count,
    expected_dispatch_status,
):
    import api.server as server
    from api.run_dispatch_repository import reconcile_run_dispatch_timeout
    from api.task_tracker import create_tracked_task

    db_path = str(tmp_path / "tasks.db")
    created = create_run(
        db_path=db_path,
        thread_id=f"pre-start-cancel-{attempt_count}",
        query="query",
    )
    claim = None
    for attempt in range(1, attempt_count + 1):
        claim = claim_run_dispatch(
            db_path=db_path,
            worker_id=WORKER_1,
            lease_seconds=30,
            run_id=created["run_id"],
            now=datetime(2026, 7, 14, attempt, tzinfo=timezone.utc),
        )
        assert claim is not None
        if attempt < attempt_count:
            assert reconcile_run_dispatch_timeout(
                db_path=db_path,
                claim=claim,
            ) == "retry"

    start_entered = threading.Event()
    release_start = threading.Event()

    def held_uncommitted_start(**_kwargs):
        start_entered.set()
        assert release_start.wait(timeout=3)
        return False

    monkeypatch.setattr(server, "start_run_dispatch", held_uncommitted_start)
    stage, origin, checkpoint = _runtime_owners(server)
    outcome_box = server.OutcomeBox()
    task = create_tracked_task(
        server._run_dispatched_with_persistence(
            claim,
            db_path=db_path,
            outcome_box=outcome_box,
            stage=stage,
            termination_origin=origin,
            finalization_checkpoint=checkpoint,
        ),
        f"{claim.run_id}:dispatch:{claim.attempt_count}",
        on_cancel=lambda _task_id: server._mark_dispatched_cancellation(
            claim,
            db_path=db_path,
            outcome_box=outcome_box,
            stage=stage,
            termination_origin=origin,
        ),
        termination_origin=origin,
        finalization_checkpoint=checkpoint,
    )

    assert await asyncio.to_thread(start_entered.wait, 1)
    task.cancel()
    release_start.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    snapshot = _dispatch_failure_snapshot(
        db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
    )
    assert snapshot["dispatch"]["status"] == expected_dispatch_status
    assert snapshot["dispatch"]["attempt_count"] == attempt_count
    assert snapshot["run"]["execution_status"] == "pending"
    assert snapshot["run"]["state_version"] == 0
    assert snapshot["segment"]["status"] == "pending"
    assert snapshot["cause"] is None


@pytest.mark.asyncio
async def test_cancelled_callback_waits_for_reconciliation_thread_settlement(
    tmp_path,
    monkeypatch,
):
    import api.server as server
    from api.run_dispatch_repository import (
        reconcile_run_dispatch_cancellation as real_reconcile,
    )
    from api.task_tracker import create_tracked_task

    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="callback-settle", query="query")
    claim = claim_run_dispatch(
        db_path=db_path,
        worker_id=WORKER_1,
        lease_seconds=30,
        run_id=created["run_id"],
    )
    start_entered = threading.Event()
    release_start = threading.Event()
    reconciliation_committed = threading.Event()
    release_reconciliation = threading.Event()

    def held_uncommitted_start(**_kwargs):
        start_entered.set()
        assert release_start.wait(timeout=3)
        return False

    def reconcile_then_hold(**kwargs):
        result = real_reconcile(**kwargs)
        reconciliation_committed.set()
        assert release_reconciliation.wait(timeout=3)
        return result

    monkeypatch.setattr(server, "start_run_dispatch", held_uncommitted_start)
    monkeypatch.setattr(
        server,
        "reconcile_run_dispatch_cancellation",
        reconcile_then_hold,
    )
    stage, origin, checkpoint = _runtime_owners(server)
    outcome_box = server.OutcomeBox()
    task = create_tracked_task(
        server._run_dispatched_with_persistence(
            claim,
            db_path=db_path,
            outcome_box=outcome_box,
            stage=stage,
            termination_origin=origin,
            finalization_checkpoint=checkpoint,
        ),
        f"{claim.run_id}:dispatch:{claim.attempt_count}",
        on_cancel=lambda _task_id: server._mark_dispatched_cancellation(
            claim,
            db_path=db_path,
            outcome_box=outcome_box,
            stage=stage,
            termination_origin=origin,
        ),
        termination_origin=origin,
        finalization_checkpoint=checkpoint,
    )

    assert await asyncio.to_thread(start_entered.wait, 1)
    task.cancel()
    release_start.set()
    assert await asyncio.to_thread(reconciliation_committed.wait, 1)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release_reconciliation.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    snapshot = _dispatch_failure_snapshot(
        db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
    )
    assert snapshot["dispatch"]["status"] == "pending"
    assert snapshot["cause"] is None


@pytest.mark.asyncio
async def test_stale_cancellation_callback_cannot_replace_terminal_winner(
    tmp_path,
):
    import api.server as server
    from api.run_failure_cause_models import RunFailureCauseWrite
    from api.run_repository import finalize_run_transaction

    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="stale-cancel", query="query")
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
    assert finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=1,
        allowed_previous_statuses={"running"},
        execution_status="failed",
        delivery_status="failed",
        evidence_entries=[],
        failure_cause=RunFailureCauseWrite(
            phase="execution",
            code="execution_error",
        ),
    )
    before = _dispatch_failure_snapshot(
        db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
    )
    stage, origin, _ = _runtime_owners(server)
    stage.advance_to_execution()
    assert origin.claim_cancelled()

    await server._mark_dispatched_cancellation(
        first,
        db_path=db_path,
        outcome_box=server.OutcomeBox(),
        stage=stage,
        termination_origin=origin,
    )

    assert _dispatch_failure_snapshot(
        db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
    ) == before


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
