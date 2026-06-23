from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sqlite3

import pytest

from agent.research import EvidenceEntry
from agent.talent_contracts import ResearchPacket
from api.evidence_verification_models import VerificationDecisionRequest
from api.evidence_verification_repository import accept_verification_decision
from api.publication_repository import (
    PublicationConflict,
    count_current_publications,
    finalize_verification_publication,
    get_current_publication,
    get_publication,
    get_publication_by_revision,
    migrate_publication_with_backup,
)
from api.review_artifacts import ReviewedArtifactResult, build_reviewed_artifacts
from api.review_models import (
    ReviewDecisionRequest,
    checkpoint_thread_id,
    post_review_segment_id,
    review_workflow_id,
)
from api.review_repository import (
    ReviewConflict,
    accept_review_decision,
    get_original_decision_brief,
    get_review_detail,
    resolve_review,
)
from api.run_repository import (
    _connect,
    create_run,
    finalize_run_transaction,
    get_run,
)
from api.talent_artifacts import build_talent_artifacts


@dataclass(frozen=True)
class SeededPublicationRun:
    db_path: str
    run_id: str
    evidence_id: str
    evidence_fingerprint: str
    review_id: str
    workflow_id: str
    publication_id: str | None


def _scope() -> dict:
    return {
        "target_roles": ["AI Agent Engineer"],
        "target_companies": [],
        "time_window": {"start": "2026-01-01", "end": "2026-06-23"},
        "declared_samples": [{
            "sample_id": "job-1",
            "source_type": "public_job_posting",
            "reference": "https://example.com/job",
        }],
        "allowed_source_types": ["public_job_posting"],
        "research_questions": ["question-1"],
        "requested_outputs": ["decision_brief"],
    }


def _seed_talent_run(
    tmp_path,
    *,
    migrate: bool,
) -> SeededPublicationRun:
    db_path = str(tmp_path / "tasks.db")
    created = create_run(
        db_path=db_path,
        thread_id="thread-publication",
        query="query",
        profile_id="talent-hiring-signal",
        profile_version="1",
        scope=_scope(),
    )
    entry = EvidenceEntry(
        thread_id="thread-publication",
        query_text="query",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url="https://example.com/job",
        snippet="Persisted evidence",
        citation_status="cited",
        created_at="2026-06-22T00:00:00+00:00",
    )
    evidence_id = f"ev_{created['run_id']}_{entry.evidence_fingerprint}"
    packet = ResearchPacket.model_validate(
        {
            "packet_id": "packet-1",
            "scope_id": "scope-1",
            "findings": [{
                "finding_id": "finding-1",
                "research_question_id": "question-1",
                "statement": "Signal",
                "evidence_refs": [evidence_id],
                "sample_scope": "declared",
                "confidence": 0.8,
            }],
            "candidate_claims": [{
                "claim_id": "claim-1",
                "text": "Claim",
                "claim_type": "signal",
                "finding_refs": ["finding-1"],
                "evidence_refs": [evidence_id],
                "confidence": 0.8,
                "citation_status": "cited",
                "verification_status": "unverified",
                "review_status": "pending",
                "conflict_status": "none",
            }],
        }
    )
    review, _, artifacts = build_talent_artifacts(
        run_id=created["run_id"],
        scope=_scope(),
        packets=[packet],
        evidence_entries=[entry],
        generated_at=datetime(2026, 6, 22, tzinfo=timezone.utc),
    )
    workflow_id = review_workflow_id(
        created["run_id"],
        review.review_id,
        review.revision,
    )
    if not migrate:
        migrate_publication_with_backup(
            db_path=db_path,
            backup_path=str(tmp_path / "pre-finalization-backup.db"),
        )
    assert finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        review_status="required",
        delivery_status="review_required",
        evidence_entries=[entry],
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
    if migrate:
        migrate_publication_with_backup(
            db_path=db_path,
            backup_path=str(tmp_path / "backup.db"),
        )
    publication = get_current_publication(
        db_path=db_path,
        run_id=created["run_id"],
    ) if migrate else None
    return SeededPublicationRun(
        db_path=db_path,
        run_id=created["run_id"],
        evidence_id=evidence_id,
        evidence_fingerprint=entry.evidence_fingerprint,
        review_id=review.review_id,
        workflow_id=workflow_id,
        publication_id=(
            publication.publication_id
            if publication is not None
            else None
        ),
    )


def _verify_request(
    seeded: SeededPublicationRun,
    *,
    verification_id: str = "verification-1",
) -> VerificationDecisionRequest:
    return VerificationDecisionRequest(
        verification_id=verification_id,
        evidence_fingerprint=seeded.evidence_fingerprint,
        expected_revision=0,
        action="verify",
        confirm_source_match=True,
    )


def _accept_verification(
    seeded: SeededPublicationRun,
    *,
    verification_id: str = "verification-1",
):
    return accept_verification_decision(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        evidence_id=seeded.evidence_id,
        request=_verify_request(
            seeded,
            verification_id=verification_id,
        ),
        actor_fingerprint="actor",
    )


def _publication_tables(db_path: str) -> dict[str, list[tuple]]:
    connection = sqlite3.connect(db_path)
    try:
        return {
            table: list(
                connection.execute(
                    f"SELECT * FROM {table} ORDER BY 1"
                )
            )
            for table in (
                "evidence_verification_snapshots_v2",
                "run_artifacts_v2",
                "review_bundles_v2",
                "review_workflows_v2",
                "run_publications_v2",
                "research_runs_v2",
            )
        }
    finally:
        connection.close()


def test_new_decision_atomically_stales_current_publication(tmp_path):
    seeded = _seed_talent_run(tmp_path, migrate=True)

    accepted = _accept_verification(seeded)

    publication = get_publication(
        db_path=seeded.db_path,
        publication_id=seeded.publication_id,
    )
    run = get_run(db_path=seeded.db_path, run_id=seeded.run_id)
    workflow = get_review_detail(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        review_id=seeded.review_id,
    )
    assert accepted.idempotent_replay is False
    assert publication.status == "stale"
    assert publication.is_current is False
    assert workflow["workflow"]["status"] == "superseded"
    assert run["delivery_status"] == "review_required"


def test_first_decision_adopts_then_stales_missing_baseline(tmp_path):
    seeded = _seed_talent_run(tmp_path, migrate=True)
    connection = _connect(seeded.db_path)
    try:
        with connection:
            connection.execute(
                "DELETE FROM run_publications_v2 WHERE run_id = ?",
                (seeded.run_id,),
            )
    finally:
        connection.close()

    _accept_verification(seeded)

    revision_one = get_publication_by_revision(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        revision=1,
    )
    assert revision_one.status == "stale"
    assert "decision-brief.json" in revision_one.artifact_ids


def test_enabled_initial_run_seeds_baseline_publication(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION",
        "true",
    )

    seeded = _seed_talent_run(tmp_path, migrate=False)

    publication = get_current_publication(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
    )
    assert publication.revision == 1
    assert publication.artifact_ids[0] == "decision-brief.json"


def test_idempotent_decision_replay_does_not_increment_run_twice(tmp_path):
    seeded = _seed_talent_run(tmp_path, migrate=True)
    request = _verify_request(seeded)
    first = accept_verification_decision(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        evidence_id=seeded.evidence_id,
        request=request,
        actor_fingerprint="actor",
    )
    version = get_run(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
    )["state_version"]

    second = accept_verification_decision(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        evidence_id=seeded.evidence_id,
        request=request,
        actor_fingerprint="actor",
    )

    assert first.idempotent_replay is False
    assert second.idempotent_replay is True
    assert get_run(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
    )["state_version"] == version


def test_changed_snapshot_creates_one_current_publication(tmp_path):
    seeded = _seed_talent_run(tmp_path, migrate=True)
    _accept_verification(seeded)
    state_version = get_run(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
    )["state_version"]

    result = finalize_verification_publication(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        expected_state_version=state_version,
    )

    assert result.publication.revision == 2
    assert result.publication.status == "review_required"
    assert result.idempotent_replay is False
    assert count_current_publications(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
    ) == 1


def test_stale_state_finalization_writes_nothing(tmp_path):
    seeded = _seed_talent_run(tmp_path, migrate=True)
    _accept_verification(seeded)
    state_version = get_run(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
    )["state_version"]
    before = _publication_tables(seeded.db_path)

    with pytest.raises(PublicationConflict, match="stale_state_version"):
        finalize_verification_publication(
            db_path=seeded.db_path,
            run_id=seeded.run_id,
            expected_state_version=state_version - 1,
        )

    assert _publication_tables(seeded.db_path) == before


def test_same_snapshot_returns_existing_current_publication(tmp_path):
    seeded = _seed_talent_run(tmp_path, migrate=True)
    _accept_verification(seeded)
    first = finalize_verification_publication(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        expected_state_version=get_run(
            db_path=seeded.db_path,
            run_id=seeded.run_id,
        )["state_version"],
    )

    second = finalize_verification_publication(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        expected_state_version=get_run(
            db_path=seeded.db_path,
            run_id=seeded.run_id,
        )["state_version"],
    )

    assert second.idempotent_replay is True
    assert second.publication == first.publication


def test_fresh_approval_marks_only_current_publication_ready(tmp_path):
    seeded = _seed_talent_run(tmp_path, migrate=True)
    _accept_verification(seeded)
    finalized = finalize_verification_publication(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        expected_state_version=get_run(
            db_path=seeded.db_path,
            run_id=seeded.run_id,
        )["state_version"],
    )
    connection = _connect(seeded.db_path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE review_workflows_v2
                SET status = 'waiting_decision'
                WHERE review_id = ?
                """,
                (finalized.publication.review_id,),
            )
    finally:
        connection.close()
    state_version = get_run(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
    )["state_version"]
    accepted = accept_review_decision(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        review_id=finalized.publication.review_id,
        request=ReviewDecisionRequest(
            decision_id="decision_revision_2",
            review_revision=2,
            action="approve",
            expected_state_version=state_version,
        ),
        actor_fingerprint="actor",
    )
    result = build_reviewed_artifacts(
        original_brief_json=get_original_decision_brief(
            db_path=seeded.db_path,
            run_id=seeded.run_id,
            review_id=finalized.publication.review_id,
        ),
        decision=accepted.decision,
        revision=2,
    )
    connection = _connect(seeded.db_path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE review_workflows_v2
                SET status = 'resolution_pending',
                    lease_owner = 'worker',
                    lease_expires_at = '2999-01-01T00:00:00+00:00',
                    attempt_count = 1
                WHERE review_id = ?
                """,
                (finalized.publication.review_id,),
            )
            connection.execute(
                """
                INSERT INTO review_resume_attempts_v2(
                    workflow_id, attempt, worker_id, started_at
                )
                SELECT workflow_id, 1, 'worker', '2026-06-23T00:00:00+00:00'
                FROM review_workflows_v2
                WHERE review_id = ?
                """,
                (finalized.publication.review_id,),
            )
        verification_count = connection.execute(
            """
            SELECT COUNT(*) FROM evidence_verification_decisions_v2
            WHERE run_id = ?
            """,
            (seeded.run_id,),
        ).fetchone()[0]
    finally:
        connection.close()

    resolve_review(
        db_path=seeded.db_path,
        workflow_id=finalized.workflow["workflow_id"],
        worker_id="worker",
        expected_run_state_version=accepted.decision.accepted_state_version,
        result=result,
    )

    current = get_current_publication(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
    )
    assert current.status == "ready"
    assert current.artifact_ids == (
        "decision-brief.r2.reviewed.json",
        "decision-brief.r2.reviewed.md",
    )
    assert current.content_hash == result.brief.content_hash
    assert get_publication_by_revision(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        revision=1,
    ).status == "stale"
    connection = _connect(seeded.db_path)
    try:
        assert connection.execute(
            """
            SELECT COUNT(*) FROM evidence_verification_decisions_v2
            WHERE run_id = ?
            """,
            (seeded.run_id,),
        ).fetchone()[0] == verification_count
    finally:
        connection.close()


def test_old_review_approval_cannot_resolve_new_publication(tmp_path):
    seeded = _seed_talent_run(tmp_path, migrate=True)
    _accept_verification(seeded)

    with pytest.raises(ReviewConflict, match="review_superseded"):
        resolve_review(
            db_path=seeded.db_path,
            workflow_id=seeded.workflow_id,
            worker_id="worker",
            expected_run_state_version=2,
            result=ReviewedArtifactResult(
                brief=None,
                resolved_review={},
                artifacts=[],
            ),
        )
