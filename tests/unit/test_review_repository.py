from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json

import pytest

from agent.talent_contracts import (
    DecisionBrief,
    EvidenceSnapshot,
    ResearchScope,
    ReviewBundle,
)
from api.decision_brief import with_content_hash
from api.review_artifacts import ReviewedArtifactResult, build_reviewed_artifacts
from api.review_models import (
    ReviewDecisionRequest,
    checkpoint_thread_id,
    decode_review_cursor,
    post_review_segment_id,
    review_workflow_id,
)
from api.review_repository import (
    ReviewConflict,
    _connect,
    accept_review_decision,
    claim_review_workflow,
    complete_checkpoint_creation,
    get_review_detail,
    get_review_projection,
    list_review_workflows,
    mark_manual_recovery,
    release_workflow_for_retry,
    resolve_review,
)
from api.run_repository import (
    create_run,
    finalize_run_transaction,
    get_run,
    transition_run,
)


@dataclass(frozen=True)
class RequiredReviewRun:
    db_path: str
    run_id: str
    review_id: str
    review: ReviewBundle
    workflow_id: str
    brief_json: str


def _required_review_run(
    tmp_path,
    *,
    suffix: str,
    db_path: str | None = None,
) -> RequiredReviewRun:
    db_path = db_path or str(tmp_path / f"runs-{suffix}.db")
    created = create_run(
        db_path=db_path,
        thread_id=f"thread-{suffix}",
        query="query",
        profile_id="talent-hiring-signal",
    )
    assert transition_run(
        db_path=db_path,
        run_id=created["run_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="running",
    )
    evidence = EvidenceSnapshot(
        evidence_id="ev_1",
        source_url="https://example.com",
        snippet="Evidence",
        verification_status="unverified",
    )
    review = ReviewBundle(
        review_id=f"review_{suffix}",
        run_id=created["run_id"],
        revision=1,
        status="required",
        claim_snapshots=[],
        evidence_snapshots=[evidence],
        triggers=["manual_review_required"],
        recommended_actions=["Review the bundle."],
        required_before_delivery=True,
    )
    scope = ResearchScope.model_validate(
        {
            "target_roles": ["AI Agent Engineer"],
            "target_companies": [],
            "time_window": {"start": "2026-01-01", "end": "2026-06-12"},
            "declared_samples": [],
            "allowed_source_types": ["public_job_posting"],
            "research_questions": ["Which skills recur?"],
            "requested_outputs": ["decision_brief"],
        }
    )
    brief = with_content_hash(
        DecisionBrief(
            schema_version="1",
            run_id=created["run_id"],
            profile_id="talent-hiring-signal",
            profile_version="1",
            input_snapshot_hash="input_hash",
            renderer_version="2",
            canonicalization_version="1",
            scope=scope,
            executive_summary="Summary",
            findings=[],
            claims=[],
            evidence_summary=[evidence.model_dump(mode="json")],
            conflicts=[],
            limitations=[],
            recommendations=[],
            review_summary=review.model_dump(mode="json"),
            quality_summary={"status": "passed"},
            generated_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
        )
    )
    brief_json = json.dumps(
        brief.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
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
        review_bundle=review,
        artifacts=[
            {
                "artifact_id": "decision-brief.json",
                "kind": "decision_brief_json",
                "media_type": "application/json",
                "content": brief_json,
                "content_hash": brief.content_hash,
            }
        ],
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
    connection = _connect(db_path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE review_workflows_v2
                SET status = 'waiting_decision'
                WHERE workflow_id = ?
                """,
                (workflow_id,),
            )
    finally:
        connection.close()
    assert get_run(db_path=db_path, run_id=created["run_id"])["state_version"] == 2
    return RequiredReviewRun(
        db_path=db_path,
        run_id=created["run_id"],
        review_id=review.review_id,
        review=review,
        workflow_id=workflow_id,
        brief_json=brief_json,
    )


@pytest.fixture
def required_review_run(tmp_path) -> RequiredReviewRun:
    return _required_review_run(tmp_path, suffix="required")


@dataclass(frozen=True)
class ResumableReviewRun:
    required: RequiredReviewRun
    artifacts: ReviewedArtifactResult


@dataclass
class MutableClock:
    value: datetime

    def now(self) -> datetime:
        return self.value

    def advance(self, *, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock(datetime(2026, 6, 19, tzinfo=timezone.utc))


@pytest.fixture
def claimable_review_run(required_review_run) -> RequiredReviewRun:
    accept_review_decision(
        db_path=required_review_run.db_path,
        run_id=required_review_run.run_id,
        review_id=required_review_run.review_id,
        request=ReviewDecisionRequest(
            decision_id="decision_claim",
            review_revision=1,
            action="approve",
            expected_state_version=2,
        ),
        actor_fingerprint="actor_hash",
    )
    return required_review_run


def _make_resumable_review_run(
    required: RequiredReviewRun,
    *,
    action: str,
) -> ResumableReviewRun:
    request = ReviewDecisionRequest(
        decision_id=f"decision_{action}",
        review_revision=1,
        action=action,
        reason="Rejected" if action == "reject" else None,
        expected_state_version=2,
    )
    accepted = accept_review_decision(
        db_path=required.db_path,
        run_id=required.run_id,
        review_id=required.review_id,
        request=request,
        actor_fingerprint="actor_hash",
    )
    artifacts = build_reviewed_artifacts(
        original_brief_json=required.brief_json,
        decision=accepted.decision,
    )
    now = datetime.now(timezone.utc)
    connection = _connect(required.db_path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE review_workflows_v2
                SET status = 'resolution_pending',
                    lease_owner = 'worker_a',
                    lease_expires_at = ?,
                    attempt_count = 1
                WHERE workflow_id = ?
                """,
                (
                    (now + timedelta(minutes=5)).isoformat(),
                    required.workflow_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO review_resume_attempts_v2 (
                    workflow_id, attempt, worker_id, started_at
                ) VALUES (?, 1, 'worker_a', ?)
                """,
                (required.workflow_id, now.isoformat()),
            )
    finally:
        connection.close()
    return ResumableReviewRun(required=required, artifacts=artifacts)


@pytest.fixture
def resumable_approved_review_run(tmp_path) -> ResumableReviewRun:
    required = _required_review_run(tmp_path, suffix="approved")
    return _make_resumable_review_run(required, action="approve")


@pytest.fixture
def resumable_rejected_review_run(tmp_path) -> ResumableReviewRun:
    required = _required_review_run(tmp_path, suffix="rejected")
    return _make_resumable_review_run(required, action="reject")


def test_same_decision_request_is_idempotent(required_review_run):
    request = ReviewDecisionRequest(
        decision_id="decision_001",
        review_revision=1,
        action="approve",
        expected_state_version=2,
    )
    first = accept_review_decision(
        db_path=required_review_run.db_path,
        run_id=required_review_run.run_id,
        review_id=required_review_run.review_id,
        request=request,
        actor_fingerprint="actor_hash",
    )
    second = accept_review_decision(
        db_path=required_review_run.db_path,
        run_id=required_review_run.run_id,
        review_id=required_review_run.review_id,
        request=request,
        actor_fingerprint="actor_hash",
    )

    assert first.decision == second.decision
    assert first.idempotent_replay is False
    assert second.idempotent_replay is True
    assert get_review_projection(
        db_path=required_review_run.db_path,
        run_id=required_review_run.run_id,
    )["workflow"]["status"] == "resume_pending"


def test_reused_decision_id_with_different_action_conflicts(required_review_run):
    approve = ReviewDecisionRequest(
        decision_id="decision_001",
        review_revision=1,
        action="approve",
        expected_state_version=2,
    )
    reject = approve.model_copy(update={"action": "reject", "reason": "Not accepted"})
    accept_review_decision(
        db_path=required_review_run.db_path,
        run_id=required_review_run.run_id,
        review_id=required_review_run.review_id,
        request=approve,
        actor_fingerprint="actor_hash",
    )

    with pytest.raises(ReviewConflict, match="decision_id_conflict"):
        accept_review_decision(
            db_path=required_review_run.db_path,
            run_id=required_review_run.run_id,
            review_id=required_review_run.review_id,
            request=reject,
            actor_fingerprint="actor_hash",
        )


def test_different_decision_for_same_review_conflicts(required_review_run):
    first = ReviewDecisionRequest(
        decision_id="decision_001",
        review_revision=1,
        action="approve",
        expected_state_version=2,
    )
    second = ReviewDecisionRequest(
        decision_id="decision_002",
        review_revision=1,
        action="reject",
        reason="Rejected",
        expected_state_version=2,
    )
    accept_review_decision(
        db_path=required_review_run.db_path,
        run_id=required_review_run.run_id,
        review_id=required_review_run.review_id,
        request=first,
        actor_fingerprint="actor_hash",
    )

    with pytest.raises(ReviewConflict, match="review_already_decided"):
        accept_review_decision(
            db_path=required_review_run.db_path,
            run_id=required_review_run.run_id,
            review_id=required_review_run.review_id,
            request=second,
            actor_fingerprint="actor_hash",
        )


def test_stale_run_version_conflicts(required_review_run):
    request = ReviewDecisionRequest(
        decision_id="decision_001",
        review_revision=1,
        action="approve",
        expected_state_version=1,
    )

    with pytest.raises(ReviewConflict, match="stale_state_version"):
        accept_review_decision(
            db_path=required_review_run.db_path,
            run_id=required_review_run.run_id,
            review_id=required_review_run.review_id,
            request=request,
            actor_fingerprint="actor_hash",
        )


def test_run_projection_does_not_expose_sensitive_decision_fields(
    required_review_run,
):
    request = ReviewDecisionRequest(
        decision_id="decision_001",
        review_revision=1,
        action="reject",
        reason="Internal audit detail",
        expected_state_version=2,
    )
    accept_review_decision(
        db_path=required_review_run.db_path,
        run_id=required_review_run.run_id,
        review_id=required_review_run.review_id,
        request=request,
        actor_fingerprint="actor_hash",
    )

    projection = get_review_projection(
        db_path=required_review_run.db_path,
        run_id=required_review_run.run_id,
    )

    assert projection["decision"]["reason_recorded"] is True
    assert "reason" not in projection["decision"]
    assert "actor_fingerprint" not in projection["decision"]
    assert "lease_owner" not in projection["workflow"]


def test_review_queue_defaults_to_waiting_and_uses_stable_cursor(tmp_path):
    db_path = str(tmp_path / "queue.db")
    _required_review_run(
        tmp_path,
        suffix="queue-a",
        db_path=db_path,
    )
    _required_review_run(
        tmp_path,
        suffix="queue-b",
        db_path=db_path,
    )
    page = list_review_workflows(
        db_path=db_path,
        status="waiting_decision",
        limit=1,
        cursor=None,
    )

    assert len(page["reviews"]) == 1
    assert page["reviews"][0]["workflow_status"] == "waiting_decision"
    assert page["next_cursor"] is not None
    assert "lease_owner" not in page["reviews"][0]
    second_page = list_review_workflows(
        db_path=db_path,
        status="waiting_decision",
        limit=1,
        cursor=decode_review_cursor(page["next_cursor"]),
    )
    assert len(second_page["reviews"]) == 1
    assert (
        second_page["reviews"][0]["workflow_id"]
        != page["reviews"][0]["workflow_id"]
    )


def test_review_detail_includes_bundle_and_reason_but_excludes_audit_secrets(
    required_review_run,
):
    request = ReviewDecisionRequest(
        decision_id="decision_reject",
        review_revision=1,
        action="reject",
        reason="Evidence boundary was not accepted.",
        expected_state_version=2,
    )
    accept_review_decision(
        db_path=required_review_run.db_path,
        run_id=required_review_run.run_id,
        review_id=required_review_run.review_id,
        request=request,
        actor_fingerprint="actor_hash",
    )

    detail = get_review_detail(
        db_path=required_review_run.db_path,
        run_id=required_review_run.run_id,
        review_id=required_review_run.review_id,
    )

    assert detail["review_bundle"]["review_id"] == required_review_run.review_id
    assert detail["decision"]["reason"] == "Evidence boundary was not accepted."
    encoded = json.dumps(detail)
    assert "actor_hash" not in encoded
    assert "checkpoint_thread_id" not in encoded
    assert "lease_owner" not in encoded


def test_approval_resolution_is_exactly_once(resumable_approved_review_run):
    fixture = resumable_approved_review_run
    resolution = resolve_review(
        db_path=fixture.required.db_path,
        workflow_id=fixture.required.workflow_id,
        worker_id="worker_a",
        expected_run_state_version=3,
        result=fixture.artifacts,
    )
    replay = resolve_review(
        db_path=fixture.required.db_path,
        workflow_id=fixture.required.workflow_id,
        worker_id="worker_a",
        expected_run_state_version=3,
        result=fixture.artifacts,
    )

    assert replay == resolution
    run = get_run(
        db_path=fixture.required.db_path,
        run_id=fixture.required.run_id,
    )
    assert run["review_status"] == "resolved"
    assert run["delivery_status"] == "ready"
    assert run["state_version"] == 4
    assert [item["artifact_id"] for item in run["artifacts"]].count(
        "decision-brief.reviewed.json"
    ) == 1


def test_approval_rejects_mismatched_reviewed_artifact_hash(
    resumable_approved_review_run,
):
    fixture = resumable_approved_review_run
    mismatched = ReviewedArtifactResult(
        brief=fixture.artifacts.brief,
        resolved_review=fixture.artifacts.resolved_review,
        artifacts=[
            (
                {**artifact, "content_hash": "f" * 64}
                if artifact["media_type"] == "text/markdown"
                else artifact
            )
            for artifact in fixture.artifacts.artifacts
        ],
    )

    with pytest.raises(ReviewConflict, match="resolution_result_mismatch"):
        resolve_review(
            db_path=fixture.required.db_path,
            workflow_id=fixture.required.workflow_id,
            worker_id="worker_a",
            expected_run_state_version=3,
            result=mismatched,
        )


def test_manual_recovery_cannot_overwrite_superseded_workflow(
    required_review_run,
):
    connection = _connect(required_review_run.db_path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE review_workflows_v2
                SET status = 'superseded'
                WHERE workflow_id = ?
                """,
                (required_review_run.workflow_id,),
            )
    finally:
        connection.close()

    with pytest.raises(ReviewConflict, match="review_superseded"):
        mark_manual_recovery(
            db_path=required_review_run.db_path,
            workflow_id=required_review_run.workflow_id,
            worker_id=None,
            error_code="checkpoint_corrupt",
        )

    assert get_review_projection(
        db_path=required_review_run.db_path,
        run_id=required_review_run.run_id,
    )["workflow"]["status"] == "superseded"


def test_rejection_resolution_blocks_delivery(resumable_rejected_review_run):
    fixture = resumable_rejected_review_run
    resolution = resolve_review(
        db_path=fixture.required.db_path,
        workflow_id=fixture.required.workflow_id,
        worker_id="worker_a",
        expected_run_state_version=3,
        result=fixture.artifacts,
    )

    run = get_run(
        db_path=fixture.required.db_path,
        run_id=fixture.required.run_id,
    )
    assert resolution.action == "reject"
    assert run["review_status"] == "resolved"
    assert run["delivery_status"] == "blocked"
    assert not any(
        item["artifact_id"].startswith("decision-brief.reviewed")
        for item in run["artifacts"]
    )


def test_stale_worker_cannot_resolve_after_another_worker(
    resumable_approved_review_run,
):
    fixture = resumable_approved_review_run

    with pytest.raises(ReviewConflict, match="lease_not_owned"):
        resolve_review(
            db_path=fixture.required.db_path,
            workflow_id=fixture.required.workflow_id,
            worker_id="stale_worker",
            expected_run_state_version=3,
            result=fixture.artifacts,
        )


def test_expired_lease_is_reclaimed_without_new_segment(
    claimable_review_run,
    clock,
):
    first = claim_review_workflow(
        db_path=claimable_review_run.db_path,
        worker_id="worker_a",
        lease_seconds=10,
        now=clock.now(),
    )
    clock.advance(seconds=11)
    second = claim_review_workflow(
        db_path=claimable_review_run.db_path,
        worker_id="worker_b",
        lease_seconds=10,
        now=clock.now(),
    )

    assert first is not None
    assert second is not None
    assert second.workflow_id == first.workflow_id
    assert second.post_review_segment_id == first.post_review_segment_id
    assert second.attempt == first.attempt + 1
    run = get_run(
        db_path=claimable_review_run.db_path,
        run_id=claimable_review_run.run_id,
    )
    assert run["state_version"] == 3
    assert [
        segment["kind"] for segment in run["segments"]
    ].count("post_review") == 1


def test_stale_worker_cannot_complete_reclaimed_attempt(
    claimable_review_run,
    clock,
):
    first = claim_review_workflow(
        db_path=claimable_review_run.db_path,
        worker_id="worker_a",
        lease_seconds=10,
        now=clock.now(),
    )
    clock.advance(seconds=11)
    second = claim_review_workflow(
        db_path=claimable_review_run.db_path,
        worker_id="worker_b",
        lease_seconds=10,
        now=clock.now(),
    )

    assert first is not None
    assert second is not None
    assert second.attempt == first.attempt + 1
    with pytest.raises(ReviewConflict, match="lease_not_owned"):
        complete_checkpoint_creation(
            db_path=claimable_review_run.db_path,
            workflow_id=first.workflow_id,
            worker_id="worker_a",
        )


def test_resolution_pending_retry_never_returns_to_resume_pending(
    resumable_approved_review_run,
):
    fixture = resumable_approved_review_run

    release_workflow_for_retry(
        db_path=fixture.required.db_path,
        workflow_id=fixture.required.workflow_id,
        worker_id="worker_a",
        error_code="review_worker_failed",
        max_attempts=3,
    )

    workflow = get_review_projection(
        db_path=fixture.required.db_path,
        run_id=fixture.required.run_id,
    )["workflow"]
    assert workflow["status"] == "resolution_pending"
    assert workflow["last_error_code"] == "review_worker_failed"
