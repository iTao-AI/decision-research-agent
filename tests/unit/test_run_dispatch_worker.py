import asyncio
import logging
import sqlite3

import pytest

from api.run_dispatch_repository import get_run_dispatch
from api.run_dispatch_worker import RunDispatchWorker, bounded_dispatch_error_code
from api.run_repository import create_run


WORKER_ID = "dispatch_worker_00000000000000000000000000000001"


@pytest.mark.asyncio
async def test_run_once_claims_oldest_and_schedules_once(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    first = create_run(db_path=db_path, thread_id="thread-1", query="first")
    second = create_run(db_path=db_path, thread_id="thread-2", query="second")
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                "UPDATE run_dispatches_v1 SET created_at = ? WHERE run_id = ?",
                ("2026-07-14T00:00:00+00:00", first["run_id"]),
            )
            connection.execute(
                "UPDATE run_dispatches_v1 SET created_at = ? WHERE run_id = ?",
                ("2026-07-14T00:00:01+00:00", second["run_id"]),
            )
    finally:
        connection.close()
    scheduled = []
    worker = RunDispatchWorker(
        db_path=db_path,
        scheduler=scheduled.append,
        worker_id=WORKER_ID,
    )

    assert await worker.run_once() is True

    assert [claim.run_id for claim in scheduled] == [first["run_id"]]
    assert get_run_dispatch(db_path=db_path, run_id=first["run_id"])["status"] == "leased"
    assert get_run_dispatch(db_path=db_path, run_id=second["run_id"])["status"] == "pending"


@pytest.mark.asyncio
async def test_dispatch_run_targets_requested_run(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    first = create_run(db_path=db_path, thread_id="thread-1", query="first")
    second = create_run(db_path=db_path, thread_id="thread-2", query="second")
    scheduled = []
    worker = RunDispatchWorker(
        db_path=db_path,
        scheduler=scheduled.append,
        worker_id=WORKER_ID,
    )

    assert await worker.dispatch_run(second["run_id"]) is True

    assert [claim.run_id for claim in scheduled] == [second["run_id"]]
    assert get_run_dispatch(db_path=db_path, run_id=first["run_id"])["status"] == "pending"


@pytest.mark.asyncio
async def test_scheduler_failure_releases_claim_without_sensitive_text(
    tmp_path,
    caplog,
):
    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="secret")

    def fail_scheduler(_claim):
        raise RuntimeError("credential=/private/token")

    worker = RunDispatchWorker(
        db_path=db_path,
        scheduler=fail_scheduler,
        worker_id=WORKER_ID,
        lease_seconds=30,
        poll_seconds=0.01,
    )
    with caplog.at_level(logging.ERROR):
        assert await worker.dispatch_run(created["run_id"]) is True

    row = get_run_dispatch(db_path=db_path, run_id=created["run_id"])
    assert row["status"] == "pending"
    assert row["last_error_code"] == "run_dispatch_schedule_failed"
    assert "credential=/private/token" not in caplog.text
    assert "secret" not in caplog.text
    assert "run_dispatch_schedule_failed" in caplog.text


@pytest.mark.asyncio
async def test_third_scheduler_failure_terminalizes_dispatch(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")

    def fail_scheduler(_claim):
        raise RuntimeError("raw provider failure")

    worker = RunDispatchWorker(
        db_path=db_path,
        scheduler=fail_scheduler,
        worker_id=WORKER_ID,
    )

    assert await worker.dispatch_run(created["run_id"]) is True
    assert await worker.dispatch_run(created["run_id"]) is True
    assert await worker.dispatch_run(created["run_id"]) is True

    row = get_run_dispatch(db_path=db_path, run_id=created["run_id"])
    assert row["status"] == "failed"
    assert row["attempt_count"] == 3
    assert row["last_error_code"] == "run_dispatch_schedule_failed"


@pytest.mark.asyncio
async def test_wake_runs_pending_dispatch_and_stop_terminates_loop(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")
    scheduled = asyncio.Event()
    claims = []

    def scheduler(claim):
        claims.append(claim)
        scheduled.set()

    worker = RunDispatchWorker(
        db_path=db_path,
        scheduler=scheduler,
        worker_id=WORKER_ID,
        poll_seconds=60,
    )
    task = asyncio.create_task(worker.run_forever())
    worker.wake()
    await asyncio.wait_for(scheduled.wait(), timeout=1)
    worker.stop()
    await asyncio.wait_for(task, timeout=1)

    assert [claim.run_id for claim in claims] == [created["run_id"]]


@pytest.mark.asyncio
async def test_wake_between_empty_claim_and_wait_is_not_lost(tmp_path, monkeypatch):
    import api.run_dispatch_worker as worker_module

    db_path = str(tmp_path / "tasks.db")
    original_claim = worker_module.claim_run_dispatch
    first_claim_finished = asyncio.Event()
    permit_return = asyncio.Event()
    calls = 0

    async def first_none_then_real(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            first_claim_finished.set()
            await permit_return.wait()
            return None
        return await asyncio.to_thread(original_claim, **kwargs)

    async def claim_adapter(**kwargs):
        return await first_none_then_real(**kwargs)

    monkeypatch.setattr(worker_module, "_claim_in_thread", claim_adapter)
    scheduled = asyncio.Event()
    worker = RunDispatchWorker(
        db_path=db_path,
        scheduler=lambda _claim: scheduled.set(),
        worker_id=WORKER_ID,
        poll_seconds=60,
    )
    task = asyncio.create_task(worker.run_forever())
    await asyncio.wait_for(first_claim_finished.wait(), timeout=1)
    create_run(db_path=db_path, thread_id="thread-1", query="query")
    worker.wake()
    permit_return.set()
    await asyncio.wait_for(scheduled.wait(), timeout=1)
    worker.stop()
    await asyncio.wait_for(task, timeout=1)
    assert calls >= 2


@pytest.mark.asyncio
async def test_run_forever_survives_sqlite_error_with_bounded_log(
    tmp_path,
    monkeypatch,
    caplog,
):
    import api.run_dispatch_worker as worker_module

    calls = 0

    def fail_then_empty(**_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise sqlite3.OperationalError("credential=/private/db")
        return None

    monkeypatch.setattr(worker_module, "claim_run_dispatch", fail_then_empty)
    worker = RunDispatchWorker(
        db_path=str(tmp_path / "tasks.db"),
        scheduler=lambda _claim: None,
        worker_id=WORKER_ID,
        poll_seconds=0.01,
    )
    with caplog.at_level(logging.ERROR):
        task = asyncio.create_task(worker.run_forever())
        await asyncio.sleep(0.04)
        worker.stop()
        await asyncio.wait_for(task, timeout=1)

    assert calls >= 2
    assert "run_dispatch_unavailable" in caplog.text
    assert "credential=/private/db" not in caplog.text


def test_bounded_dispatch_error_code_maps_without_raw_text():
    assert bounded_dispatch_error_code(sqlite3.OperationalError("secret")) == "run_dispatch_unavailable"
    assert bounded_dispatch_error_code(OSError("private path")) == "run_dispatch_unavailable"
    assert bounded_dispatch_error_code(ValueError("query")) == "run_dispatch_invalid"
    assert bounded_dispatch_error_code(RuntimeError("provider")) == "run_dispatch_schedule_failed"
