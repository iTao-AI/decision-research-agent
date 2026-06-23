from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import sqlite3
import uuid

from api.review_artifacts import build_reviewed_artifacts
from api.review_gate import ReviewGate, ReviewGateMismatch
from api.review_repository import (
    ReviewConflict,
    claim_review_workflow,
    complete_checkpoint_creation,
    get_decision,
    get_original_decision_brief,
    list_reconcilable_workflows,
    mark_manual_recovery,
    mark_resolution_pending,
    mark_waiting_decision,
    release_expired_lease,
    release_workflow_for_retry,
    resolve_review,
)


_PASSTHROUGH_ERROR_CODES = {
    "checkpoint_decision_mismatch",
    "decision_brief_not_found",
    "lease_not_owned",
    "resolution_result_mismatch",
    "resume_attempt_not_found",
    "review_decision_missing",
    "review_not_found",
    "review_superseded",
    "stale_state_version",
}


def bounded_worker_error_code(exc: Exception) -> str:
    """Map failures to stable codes without persisting exception text."""
    if isinstance(exc, (sqlite3.Error, OSError)):
        return "checkpoint_unavailable"
    if isinstance(exc, ReviewConflict) and exc.code in _PASSTHROUGH_ERROR_CODES:
        return exc.code
    if isinstance(exc, ValueError):
        return "review_payload_invalid"
    return "review_worker_failed"


def reconcile_review_workflows(
    *,
    db_path: str | None,
    gate: ReviewGate,
    now: datetime,
) -> int:
    """Reconcile application workflow state against opaque checkpoint position."""
    reconciled = 0
    for workflow in list_reconcilable_workflows(db_path=db_path, now=now):
        try:
            checkpoint = gate.inspect(workflow.checkpoint_thread_id)
        except Exception:
            try:
                mark_manual_recovery(
                    db_path=db_path,
                    workflow_id=workflow.workflow_id,
                    worker_id=None,
                    error_code="checkpoint_corrupt",
                )
            except ReviewConflict as exc:
                if exc.code == "review_superseded":
                    continue
                raise
            reconciled += 1
            continue

        if workflow.status == "checkpoint_pending":
            if checkpoint.status == "interrupted":
                mark_waiting_decision(
                    db_path=db_path,
                    workflow_id=workflow.workflow_id,
                )
                reconciled += 1
            continue

        if workflow.status == "resuming" and workflow.lease_expired(now):
            if (
                checkpoint.status == "completed"
                and workflow.decision_id is not None
                and checkpoint.decision_id == workflow.decision_id
            ):
                mark_resolution_pending(
                    db_path=db_path,
                    workflow_id=workflow.workflow_id,
                    worker_id=None,
                    decision_id=workflow.decision_id,
                )
            elif checkpoint.status == "interrupted":
                release_expired_lease(
                    db_path=db_path,
                    workflow_id=workflow.workflow_id,
                )
            else:
                try:
                    mark_manual_recovery(
                        db_path=db_path,
                        workflow_id=workflow.workflow_id,
                        worker_id=None,
                        error_code="checkpoint_decision_mismatch",
                    )
                except ReviewConflict as exc:
                    if exc.code == "review_superseded":
                        continue
                    raise
            reconciled += 1
    return reconciled


class ReviewWorker:
    def __init__(
        self,
        *,
        db_path: str | None,
        checkpoint_path: str,
        worker_id: str | None = None,
        lease_seconds: int = 30,
        poll_seconds: float = 1.0,
        stage_hook=None,
    ):
        self.db_path = db_path
        self.checkpoint_path = checkpoint_path
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex}"
        self.lease_seconds = lease_seconds
        self.poll_seconds = poll_seconds
        self.stage_hook = stage_hook or (lambda stage, workflow: None)
        self._stop = asyncio.Event()
        self._reconciled = False

    async def run_once(self) -> bool:
        gate = ReviewGate(
            self.checkpoint_path,
            lambda decision_id: get_decision(
                db_path=self.db_path,
                decision_id=decision_id,
            ),
        )
        if not self._reconciled:
            await asyncio.to_thread(
                reconcile_review_workflows,
                db_path=self.db_path,
                gate=gate,
                now=datetime.now(timezone.utc),
            )
            self._reconciled = True
        claim = await asyncio.to_thread(
            claim_review_workflow,
            db_path=self.db_path,
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        if claim is None:
            return False
        if claim.original_status != "checkpoint_pending":
            self.stage_hook("lease_acquired", claim)
        try:
            if claim.original_status == "checkpoint_pending":
                await asyncio.to_thread(
                    gate.ensure_waiting,
                    workflow_id=claim.workflow_id,
                    checkpoint_thread_id=claim.checkpoint_thread_id,
                    run_id=claim.run_id,
                    review_id=claim.review_id,
                    review_revision=claim.review_revision,
                )
                self.stage_hook("checkpoint_interrupted", claim)
                await asyncio.to_thread(
                    complete_checkpoint_creation,
                    db_path=self.db_path,
                    workflow_id=claim.workflow_id,
                    worker_id=self.worker_id,
                )
                return True

            if claim.decision_id is None:
                raise ReviewConflict("review_decision_missing")
            if claim.original_status != "resolution_pending":
                result = await asyncio.to_thread(
                    gate.resume,
                    checkpoint_thread_id=claim.checkpoint_thread_id,
                    decision_id=claim.decision_id,
                )
                self.stage_hook("graph_resumed", claim)
                await asyncio.to_thread(
                    mark_resolution_pending,
                    db_path=self.db_path,
                    workflow_id=claim.workflow_id,
                    worker_id=self.worker_id,
                    decision_id=result["decision_id"],
                )
            decision = await asyncio.to_thread(
                get_decision,
                db_path=self.db_path,
                decision_id=claim.decision_id,
            )
            if decision is None:
                raise ReviewConflict("review_decision_missing")
            original_brief_json = await asyncio.to_thread(
                get_original_decision_brief,
                db_path=self.db_path,
                run_id=claim.run_id,
                review_id=claim.review_id,
            )
            artifacts = build_reviewed_artifacts(
                original_brief_json=original_brief_json,
                decision=decision,
                revision=claim.review_revision,
            )
            await asyncio.to_thread(
                resolve_review,
                db_path=self.db_path,
                workflow_id=claim.workflow_id,
                worker_id=self.worker_id,
                expected_run_state_version=decision.accepted_state_version,
                result=artifacts,
            )
            return True
        except ReviewGateMismatch as exc:
            await asyncio.to_thread(
                mark_manual_recovery,
                db_path=self.db_path,
                workflow_id=claim.workflow_id,
                worker_id=self.worker_id,
                error_code=str(exc),
            )
            return True
        except Exception as exc:
            error_code = bounded_worker_error_code(exc)
            logging.error(
                "Durable review worker failed for %s: %s",
                claim.workflow_id,
                error_code,
            )
            try:
                await asyncio.to_thread(
                    release_workflow_for_retry,
                    db_path=self.db_path,
                    workflow_id=claim.workflow_id,
                    worker_id=self.worker_id,
                    error_code=error_code,
                    max_attempts=3,
                )
            except ReviewConflict as release_error:
                if release_error.code != "lease_not_owned":
                    raise
                self._reconciled = False
            return True

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                did_work = await self.run_once()
            except Exception as exc:
                logging.error(
                    "Durable review worker loop failed: %s",
                    bounded_worker_error_code(exc),
                )
                did_work = False
            if not did_work:
                try:
                    await asyncio.wait_for(
                        self._stop.wait(),
                        timeout=self.poll_seconds,
                    )
                except asyncio.TimeoutError:
                    pass

    def stop(self) -> None:
        self._stop.set()
