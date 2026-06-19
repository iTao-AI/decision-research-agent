from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from agent.talent_contracts import ResearchPacket
from api.review_models import (
    ReviewDecisionRequest,
    checkpoint_thread_id,
    post_review_segment_id,
    review_workflow_id,
)
from api.review_repository import (
    _connect,
    accept_review_decision,
    claim_review_workflow,
)
from api.review_worker import ReviewWorker
from api.run_repository import (
    create_run,
    finalize_run_transaction,
    get_run,
    transition_run,
)
from api.talent_artifacts import build_talent_artifacts


@dataclass(frozen=True)
class DurableReviewFixture:
    db_path: str
    checkpoint_path: str
    run_id: str
    review_id: str
    workflow_id: str
    approve_request: ReviewDecisionRequest
    worker: ReviewWorker

    def get_run(self):
        return get_run(db_path=self.db_path, run_id=self.run_id)


def create_required_review_fixture(
    *,
    db_path: str,
    checkpoint_path: str,
    stage_hook=None,
) -> DurableReviewFixture:
    scope = {
        "target_roles": ["AI Agent Engineer"],
        "target_companies": [],
        "time_window": {"start": "2026-01-01", "end": "2026-06-19"},
        "declared_samples": [],
        "allowed_source_types": ["public_job_posting"],
        "research_questions": ["question-1"],
        "requested_outputs": ["decision_brief"],
    }
    created = create_run(
        db_path=db_path,
        thread_id="durable-review-fixture",
        query="fixture query",
        profile_id="talent-hiring-signal",
        scope=scope,
    )
    assert transition_run(
        db_path=db_path,
        run_id=created["run_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="running",
    )
    packet = ResearchPacket.model_validate(
        {
            "packet_id": "packet-fixture",
            "scope_id": "scope-fixture",
            "findings": [
                {
                    "finding_id": "finding-1",
                    "research_question_id": "question-1",
                    "statement": "Fixture signal",
                    "evidence_refs": ["ev_missing"],
                    "sample_scope": "declared fixture",
                    "confidence": 0.8,
                }
            ],
            "candidate_claims": [
                {
                    "claim_id": "claim-1",
                    "text": "Fixture claim",
                    "claim_type": "signal",
                    "finding_refs": ["finding-1"],
                    "evidence_refs": ["ev_missing"],
                    "confidence": 0.8,
                    "citation_status": "cited",
                    "verification_status": "unverified",
                    "review_status": "required",
                    "conflict_status": "none",
                }
            ],
        }
    )
    review, _, artifacts = build_talent_artifacts(
        run_id=created["run_id"],
        scope=scope,
        packets=[packet],
        evidence_entries=[],
        generated_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
    )
    workflow_id = review_workflow_id(
        created["run_id"],
        review.review_id,
        review.revision,
    )
    assert finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=1,
        allowed_previous_statuses={"running"},
        execution_status="completed",
        review_status="required",
        delivery_status="review_required",
        evidence_entries=[],
        research_packets=[packet],
        review_bundle=review,
        artifacts=artifacts,
        review_workflow={
            "workflow_id": workflow_id,
            "checkpoint_thread_id": checkpoint_thread_id(workflow_id),
            "post_review_segment_id": post_review_segment_id(
                created["run_id"],
                review.review_id,
                review.revision,
            ),
        },
    )
    request = ReviewDecisionRequest(
        decision_id="decision_fixture_001",
        review_revision=review.revision,
        action="approve",
        expected_state_version=2,
    )
    return DurableReviewFixture(
        db_path=db_path,
        checkpoint_path=checkpoint_path,
        run_id=created["run_id"],
        review_id=review.review_id,
        workflow_id=workflow_id,
        approve_request=request,
        worker=ReviewWorker(
            db_path=db_path,
            checkpoint_path=checkpoint_path,
            worker_id="worker_fixture",
            stage_hook=stage_hook,
        ),
    )


def seed_checkpoint_pending(root: Path) -> DurableReviewFixture:
    return create_required_review_fixture(
        db_path=str(root / "tasks.db"),
        checkpoint_path=str(root / "review_checkpoints.db"),
    )


def seed_resume_pending(
    root: Path,
    *,
    action: str = "approve",
) -> DurableReviewFixture:
    fixture = seed_checkpoint_pending(root)
    asyncio.run(fixture.worker.run_once())
    request = fixture.approve_request.model_copy(
        update={
            "action": action,
            "reason": "Rejected by fixture" if action == "reject" else None,
        }
    )
    accept_review_decision(
        db_path=fixture.db_path,
        run_id=fixture.run_id,
        review_id=fixture.review_id,
        request=request,
        actor_fingerprint="fixture_actor",
    )
    return fixture


def seed_resuming_with_corrupt_checkpoint(root: Path) -> DurableReviewFixture:
    fixture = seed_resume_pending(root)
    claim = claim_review_workflow(
        db_path=fixture.db_path,
        worker_id="crashed_worker",
        lease_seconds=30,
    )
    assert claim is not None
    Path(fixture.checkpoint_path).write_bytes(b"not-a-sqlite-database")
    return fixture


def expire_active_leases(db_path: str) -> None:
    connection = _connect(db_path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE review_workflows_v2
                SET lease_expires_at = '1970-01-01T00:00:00+00:00'
                WHERE lease_owner IS NOT NULL
                """
            )
    finally:
        connection.close()


def run_recovery(root: Path) -> None:
    db_path = str(root / "tasks.db")
    checkpoint_path = str(root / "review_checkpoints.db")
    expire_active_leases(db_path)
    worker = ReviewWorker(
        db_path=db_path,
        checkpoint_path=checkpoint_path,
        worker_id="worker_recovery",
    )

    async def recover():
        for _ in range(5):
            if not await worker.run_once():
                break

    asyncio.run(recover())


def run_stage(root: Path, stage: str, stage_hook) -> None:
    fixture = create_required_review_fixture(
        db_path=str(root / "tasks.db"),
        checkpoint_path=str(root / "review_checkpoints.db"),
        stage_hook=stage_hook,
    )
    if stage == "application_finalized":
        stage_hook(stage, fixture)
        return
    asyncio.run(fixture.worker.run_once())
    if stage == "checkpoint_interrupted":
        return
    accept_review_decision(
        db_path=fixture.db_path,
        run_id=fixture.run_id,
        review_id=fixture.review_id,
        request=fixture.approve_request,
        actor_fingerprint="fixture_actor",
    )
    if stage == "decision_committed":
        stage_hook(stage, fixture)
        return
    asyncio.run(fixture.worker.run_once())


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["recover"])
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    if args.command == "recover":
        run_recovery(Path(args.root))
        print(json.dumps({"status": "recovered"}, sort_keys=True))


if __name__ == "__main__":
    _main()
