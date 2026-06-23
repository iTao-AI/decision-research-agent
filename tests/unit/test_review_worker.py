import asyncio
from datetime import datetime, timezone
import logging
import sqlite3

import pytest

import api.review_worker as review_worker_module
from api.review_gate import ReviewGate
from api.review_models import ReviewDecisionRequest
from api.review_repository import (
    ReviewConflict,
    _connect,
    accept_review_decision,
    get_decision,
    get_review_projection,
)
from api.review_worker import ReviewWorker
from api.review_worker import reconcile_review_workflows
from api.run_repository import get_run
from tests.unit.test_review_repository import _required_review_run


class WorkerRun:
    def __init__(self, *, required, checkpoint_path):
        self.required = required
        self.db_path = required.db_path
        self.checkpoint_path = checkpoint_path
        self.run_id = required.run_id

    def projection(self):
        return get_review_projection(db_path=self.db_path, run_id=self.run_id)

    def get_run(self):
        return get_run(db_path=self.db_path, run_id=self.run_id)

    def worker(self, *, worker_id: str):
        return ReviewWorker(
            db_path=self.db_path,
            checkpoint_path=self.checkpoint_path,
            worker_id=worker_id,
        )

    def count_resolutions(self) -> int:
        connection = _connect(self.db_path)
        try:
            return connection.execute(
                "SELECT COUNT(*) FROM review_resolutions_v2 WHERE run_id = ?",
                (self.run_id,),
            ).fetchone()[0]
        finally:
            connection.close()

    def count_reviewed_json_artifacts(self) -> int:
        connection = _connect(self.db_path)
        try:
            return connection.execute(
                """
                SELECT COUNT(*) FROM run_artifacts_v2
                WHERE run_id = ?
                  AND artifact_id = 'decision-brief.reviewed.json'
                """,
                (self.run_id,),
            ).fetchone()[0]
        finally:
            connection.close()


def _accept_approval(worker_run: WorkerRun) -> None:
    accept_review_decision(
        db_path=worker_run.db_path,
        run_id=worker_run.run_id,
        review_id=worker_run.required.review_id,
        request=ReviewDecisionRequest(
            decision_id="decision_approve",
            review_revision=1,
            action="approve",
            expected_state_version=2,
        ),
        actor_fingerprint="actor_hash",
    )


def _create_checkpoint(worker_run: WorkerRun, *, review_id: str) -> None:
    gate = ReviewGate(
        worker_run.checkpoint_path,
        lambda decision_id: get_decision(
            db_path=worker_run.db_path,
            decision_id=decision_id,
        ),
    )
    gate.ensure_waiting(
        workflow_id=worker_run.required.workflow_id,
        checkpoint_thread_id=f"review_{worker_run.required.workflow_id}",
        run_id=worker_run.run_id,
        review_id=review_id,
        review_revision=1,
    )


@pytest.fixture
def checkpoint_pending_run(tmp_path):
    required = _required_review_run(tmp_path, suffix="checkpoint-pending")
    connection = _connect(required.db_path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE review_workflows_v2
                SET status = 'checkpoint_pending'
                WHERE workflow_id = ?
                """,
                (required.workflow_id,),
            )
    finally:
        connection.close()
    return WorkerRun(
        required=required,
        checkpoint_path=str(tmp_path / "checkpoint-pending.db"),
    )


@pytest.fixture
def resume_pending_run(tmp_path):
    required = _required_review_run(tmp_path, suffix="resume-pending")
    worker_run = WorkerRun(
        required=required,
        checkpoint_path=str(tmp_path / "resume-pending.db"),
    )
    _create_checkpoint(worker_run, review_id=required.review_id)
    _accept_approval(worker_run)
    return worker_run


@pytest.fixture
def mismatched_checkpoint_run(tmp_path):
    required = _required_review_run(tmp_path, suffix="mismatched")
    worker_run = WorkerRun(
        required=required,
        checkpoint_path=str(tmp_path / "mismatched.db"),
    )
    _create_checkpoint(worker_run, review_id="review_other")
    _accept_approval(worker_run)
    return worker_run


@pytest.mark.asyncio
async def test_worker_creates_missing_checkpoint_and_marks_waiting(
    checkpoint_pending_run,
):
    worker = checkpoint_pending_run.worker(worker_id="worker_a")

    assert await worker.run_once() is True
    assert checkpoint_pending_run.projection()["workflow"]["status"] == (
        "waiting_decision"
    )


@pytest.mark.asyncio
async def test_worker_resumes_decision_and_resolves_approval(resume_pending_run):
    worker = resume_pending_run.worker(worker_id="worker_a")

    assert await worker.run_once() is True
    run = resume_pending_run.get_run()
    assert run["review_status"] == "resolved"
    assert run["delivery_status"] == "ready"


@pytest.mark.asyncio
async def test_worker_marks_manual_recovery_on_mismatched_checkpoint(
    mismatched_checkpoint_run,
):
    worker = mismatched_checkpoint_run.worker(worker_id="worker_a")

    assert await worker.run_once() is True
    projection = mismatched_checkpoint_run.projection()
    assert projection["workflow"]["status"] == "manual_recovery"
    assert projection["workflow"]["last_error_code"] == (
        "checkpoint_decision_mismatch"
    )


def test_reconcile_does_not_overwrite_concurrently_superseded_workflow(
    checkpoint_pending_run,
):
    class SupersedingGate:
        def inspect(self, checkpoint_thread_id):
            connection = _connect(checkpoint_pending_run.db_path)
            try:
                with connection:
                    connection.execute(
                        """
                        UPDATE review_workflows_v2
                        SET status = 'superseded',
                            lease_owner = NULL,
                            lease_expires_at = NULL
                        WHERE workflow_id = ?
                        """,
                        (checkpoint_pending_run.required.workflow_id,),
                    )
            finally:
                connection.close()
            raise sqlite3.OperationalError("checkpoint unavailable")

    reconciled = reconcile_review_workflows(
        db_path=checkpoint_pending_run.db_path,
        gate=SupersedingGate(),
        now=datetime.now(timezone.utc),
    )

    assert reconciled == 0
    assert checkpoint_pending_run.projection()["workflow"]["status"] == (
        "superseded"
    )


@pytest.mark.asyncio
async def test_two_workers_do_not_resolve_the_same_workflow_twice(
    resume_pending_run,
):
    worker_a = resume_pending_run.worker(worker_id="worker_a")
    worker_b = resume_pending_run.worker(worker_id="worker_b")

    await asyncio.gather(worker_a.run_once(), worker_b.run_once())

    assert resume_pending_run.count_resolutions() == 1
    assert resume_pending_run.count_reviewed_json_artifacts() == 1


@pytest.mark.asyncio
async def test_permanent_failure_stops_after_three_attempts(
    resume_pending_run,
    monkeypatch,
):
    def fail_resume(self, *, checkpoint_thread_id, decision_id):
        raise sqlite3.OperationalError("checkpoint unavailable")

    monkeypatch.setattr(ReviewGate, "resume", fail_resume)
    worker = resume_pending_run.worker(worker_id="worker_a")

    for _ in range(3):
        assert await worker.run_once() is True

    projection = resume_pending_run.projection()
    assert projection["workflow"]["status"] == "manual_recovery"
    assert projection["workflow"]["last_error_code"] == "checkpoint_unavailable"
    assert await worker.run_once() is False


@pytest.mark.asyncio
async def test_expired_lease_after_graph_resume_reconciles_without_worker_exit(
    resume_pending_run,
    monkeypatch,
):
    original = review_worker_module.mark_resolution_pending

    def expire_lease_then_fail(*, db_path, workflow_id, worker_id, decision_id):
        connection = _connect(db_path)
        try:
            with connection:
                connection.execute(
                    """
                    UPDATE review_workflows_v2
                    SET lease_expires_at = '2000-01-01T00:00:00+00:00'
                    WHERE workflow_id = ?
                    """,
                    (workflow_id,),
                )
        finally:
            connection.close()
        raise ReviewConflict("lease_not_owned")

    monkeypatch.setattr(
        review_worker_module,
        "mark_resolution_pending",
        expire_lease_then_fail,
    )
    worker = resume_pending_run.worker(worker_id="worker_a")

    assert await worker.run_once() is True

    monkeypatch.setattr(
        review_worker_module,
        "mark_resolution_pending",
        original,
    )
    assert await worker.run_once() is True
    assert resume_pending_run.get_run()["delivery_status"] == "ready"


@pytest.mark.asyncio
async def test_worker_loop_continues_after_transient_run_once_failure(
    tmp_path,
    monkeypatch,
):
    worker = ReviewWorker(
        db_path=str(tmp_path / "tasks.db"),
        checkpoint_path=str(tmp_path / "checkpoints.db"),
        poll_seconds=0.01,
    )
    calls = 0

    async def flaky_run_once():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise sqlite3.OperationalError("database is locked")
        worker.stop()
        return False

    monkeypatch.setattr(worker, "run_once", flaky_run_once)

    await asyncio.wait_for(worker.run_forever(), timeout=1)

    assert calls == 2


@pytest.mark.asyncio
async def test_worker_logs_bounded_error_code_without_sensitive_exception_text(
    resume_pending_run,
    monkeypatch,
    caplog,
):
    def fail_artifact_build(*, original_brief_json, decision, revision):
        raise ValueError("sensitive claim text")

    monkeypatch.setattr(
        review_worker_module,
        "build_reviewed_artifacts",
        fail_artifact_build,
    )
    worker = resume_pending_run.worker(worker_id="worker_a")

    with caplog.at_level(logging.ERROR):
        assert await worker.run_once() is True

    assert "review_payload_invalid" in caplog.text
    assert "sensitive claim text" not in caplog.text


@pytest.mark.asyncio
async def test_worker_loads_brief_and_builds_artifacts_for_claimed_revision(
    resume_pending_run,
    monkeypatch,
):
    loaded = {}
    original_loader = review_worker_module.get_original_decision_brief
    original_builder = review_worker_module.build_reviewed_artifacts

    def recording_loader(*, db_path, run_id, review_id):
        loaded["review_id"] = review_id
        return original_loader(
            db_path=db_path,
            run_id=run_id,
            review_id=review_id,
        )

    def recording_builder(*, original_brief_json, decision, revision):
        loaded["revision"] = revision
        return original_builder(
            original_brief_json=original_brief_json,
            decision=decision,
            revision=revision,
        )

    monkeypatch.setattr(
        review_worker_module,
        "get_original_decision_brief",
        recording_loader,
    )
    monkeypatch.setattr(
        review_worker_module,
        "build_reviewed_artifacts",
        recording_builder,
    )

    assert await resume_pending_run.worker(worker_id="worker_a").run_once()
    assert loaded == {
        "review_id": resume_pending_run.required.review_id,
        "revision": 1,
    }
