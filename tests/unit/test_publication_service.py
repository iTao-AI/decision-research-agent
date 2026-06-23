from __future__ import annotations

from dataclasses import dataclass

import pytest

from agent.research import EvidenceEntry
from agent.talent_contracts import ResearchPacket
from api.evidence_verification_repository import (
    finalize_verification_snapshot,
    init_evidence_verification_schema,
)
from api.publication_service import (
    PublicationBuildConflict,
    build_publication_artifacts,
)
from api.run_repository import (
    _connect,
    create_run,
    finalize_run_transaction,
    transition_run,
)


@dataclass
class PersistedPublicationInputs:
    connection: object
    db_path: str
    run_id: str
    snapshot_id: str


def _seed_publication_inputs(tmp_path) -> PersistedPublicationInputs:
    db_path = str(tmp_path / "tasks.db")
    scope = {
        "target_roles": ["AI Agent Engineer"],
        "target_companies": [],
        "time_window": {"start": "2026-01-01", "end": "2026-06-23"},
        "declared_samples": [],
        "allowed_source_types": ["public_job_posting"],
        "research_questions": ["question-1"],
        "requested_outputs": ["decision_brief"],
    }
    created = create_run(
        db_path=db_path,
        thread_id="thread-publication-service",
        query="query",
        profile_id="talent-hiring-signal",
        profile_version="1",
        scope=scope,
    )
    assert transition_run(
        db_path=db_path,
        run_id=created["run_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="running",
    )
    evidence = EvidenceEntry(
        thread_id="thread-publication-service",
        query_text="query",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url="https://example.com/job",
        snippet="Evidence",
        retrieved_at="2026-06-22T00:00:00+00:00",
        created_at="2026-06-22T00:00:00+00:00",
    )
    evidence_id = f"ev_{created['run_id']}_{evidence.evidence_fingerprint}"
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
    assert finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=1,
        allowed_previous_statuses={"running"},
        execution_status="completed",
        delivery_status="ready",
        evidence_entries=[evidence],
        research_packets=[packet],
    )
    init_evidence_verification_schema(db_path)
    snapshot = finalize_verification_snapshot(
        db_path=db_path,
        run_id=created["run_id"],
    ).snapshot
    return PersistedPublicationInputs(
        connection=_connect(db_path),
        db_path=db_path,
        run_id=created["run_id"],
        snapshot_id=snapshot.snapshot_id,
    )


def test_revisioned_artifacts_are_byte_stable_for_same_snapshot(tmp_path):
    persisted = _seed_publication_inputs(tmp_path)
    try:
        first = build_publication_artifacts(
            connection=persisted.connection,
            run_id=persisted.run_id,
            snapshot_id=persisted.snapshot_id,
            revision=2,
        )
        second = build_publication_artifacts(
            connection=persisted.connection,
            run_id=persisted.run_id,
            snapshot_id=persisted.snapshot_id,
            revision=2,
        )
    finally:
        persisted.connection.close()

    assert first.brief_json == second.brief_json
    assert first.brief_markdown == second.brief_markdown
    assert first.review == second.review


def test_revision_two_uses_new_ids_and_keeps_revision_one(tmp_path):
    persisted = _seed_publication_inputs(tmp_path)
    try:
        result = build_publication_artifacts(
            connection=persisted.connection,
            run_id=persisted.run_id,
            snapshot_id=persisted.snapshot_id,
            revision=2,
        )
    finally:
        persisted.connection.close()

    assert result.artifact_ids == (
        "decision-brief.r2.json",
        "decision-brief.r2.md",
    )


def test_publication_build_rejects_snapshot_evidence_fingerprint_mismatch(
    tmp_path,
):
    persisted = _seed_publication_inputs(tmp_path)
    try:
        persisted.connection.execute(
            """
            UPDATE evidence_entries_v2
            SET evidence_fingerprint = ?
            WHERE run_id = ?
            """,
            ("f" * 64, persisted.run_id),
        )
        with pytest.raises(
            PublicationBuildConflict,
            match="verification_snapshot_evidence_mismatch",
        ):
            build_publication_artifacts(
                connection=persisted.connection,
                run_id=persisted.run_id,
                snapshot_id=persisted.snapshot_id,
                revision=2,
            )
    finally:
        persisted.connection.rollback()
        persisted.connection.close()
