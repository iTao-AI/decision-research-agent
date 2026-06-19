from dataclasses import dataclass

import pytest

from agent.talent_contracts import ReviewBundle
from api.review_models import (
    ReviewDecisionRequest,
    checkpoint_thread_id,
    post_review_segment_id,
    review_workflow_id,
)
from api.review_repository import (
    ReviewConflict,
    _connect,
    accept_review_decision,
    get_review_projection,
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


@pytest.fixture
def required_review_run(tmp_path) -> RequiredReviewRun:
    db_path = str(tmp_path / "runs.db")
    created = create_run(
        db_path=db_path,
        thread_id="thread-1",
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
    review = ReviewBundle(
        review_id="review_1",
        run_id=created["run_id"],
        revision=1,
        status="required",
        claim_snapshots=[],
        evidence_snapshots=[],
        triggers=["manual_review_required"],
        recommended_actions=["Review the bundle."],
        required_before_delivery=True,
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
    )


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
