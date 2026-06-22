from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from agent.research import EvidenceEntry
from api.evidence_verification_models import VerificationDecisionRequest
from api.evidence_verification_repository import (
    VerificationConflict,
    accept_verification_decision,
    get_or_create_evidence_preflight,
    get_effective_verification,
    init_evidence_verification_schema,
    list_effective_verifications,
)
from api.run_repository import create_run, finalize_run_transaction


def _persisted_evidence(
    tmp_path,
    *,
    suffix="ordinary",
    baseline_origin="none",
    source_url="https://jobs.example.com/role",
    declared_source_url=None,
):
    db_path = str(tmp_path / f"{suffix}.db")
    declared_source_url = declared_source_url or source_url
    declared_samples = (
        [
            {
                "sample_id": "aggregate-v1",
                "source_type": "provided_aggregate",
                "reference": "aggregate-v1",
            }
        ]
        if baseline_origin == "declared_fixture"
        else [
            {
                "sample_id": "job-1",
                "source_type": "public_job_posting",
                "reference": declared_source_url,
            }
        ]
    )
    created = create_run(
        db_path=db_path,
        thread_id=f"thread-{suffix}",
        query="query",
        profile_id="talent-hiring-signal",
        scope={
            "target_roles": ["AI Agent Engineer"],
            "target_companies": [],
            "time_window": {"start": "2026-01-01", "end": "2026-06-12"},
            "declared_samples": declared_samples,
            "allowed_source_types": [
                "provided_aggregate"
                if baseline_origin == "declared_fixture"
                else "public_job_posting"
            ],
            "research_questions": ["question-1"],
            "requested_outputs": ["decision_brief"],
        },
    )
    entry = EvidenceEntry(
        thread_id=f"thread-{suffix}",
        query_text="query",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url=source_url,
        snippet="Persisted evidence",
        citation_status="cited",
        verification_status=(
            "verified"
            if baseline_origin == "declared_fixture"
            else "unverified"
        ),
        baseline_verification_origin=baseline_origin,
    )
    assert finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        delivery_status="ready",
        evidence_entries=[entry],
    )
    evidence_id = f"ev_{created['run_id']}_{entry.evidence_fingerprint}"
    return db_path, created["run_id"], evidence_id, entry.evidence_fingerprint


def _verify_request(
    *,
    verification_id="verification-1",
    fingerprint,
    expected_revision=0,
):
    return VerificationDecisionRequest(
        verification_id=verification_id,
        evidence_fingerprint=fingerprint,
        expected_revision=expected_revision,
        action="verify",
        confirm_source_match=True,
    )


def _reject_request(
    *,
    verification_id="verification-2",
    fingerprint,
    expected_revision,
):
    return VerificationDecisionRequest(
        verification_id=verification_id,
        evidence_fingerprint=fingerprint,
        expected_revision=expected_revision,
        action="reject",
        reason_code="content_mismatch",
        reason_note="The persisted snippet does not match the source.",
    )


def test_first_verify_appends_revision_one_and_derives_human_verified(tmp_path):
    db_path, run_id, evidence_id, fingerprint = _persisted_evidence(tmp_path)

    accepted = accept_verification_decision(
        db_path=db_path,
        run_id=run_id,
        evidence_id=evidence_id,
        request=_verify_request(fingerprint=fingerprint),
        actor_fingerprint="actor-hash",
    )
    projection = get_effective_verification(
        db_path=db_path,
        run_id=run_id,
        evidence_id=evidence_id,
    )

    assert accepted.idempotent_replay is False
    assert accepted.decision.revision == 1
    assert projection.verification_status == "verified"
    assert projection.verification_state == "verified"
    assert projection.verification_origin == "human"
    assert projection.verification_revision == 1
    assert projection.decision_id == "verification-1"


def test_preflight_persistence_is_deterministic_and_idempotent(tmp_path):
    db_path, run_id, evidence_id, _ = _persisted_evidence(tmp_path)

    first = get_or_create_evidence_preflight(
        db_path=db_path,
        run_id=run_id,
        evidence_id=evidence_id,
    )
    second = get_or_create_evidence_preflight(
        db_path=db_path,
        run_id=run_id,
        evidence_id=evidence_id,
    )

    assert first == second
    connection = sqlite3.connect(db_path)
    try:
        count = connection.execute(
            """
            SELECT COUNT(*)
            FROM evidence_verification_preflights_v2
            WHERE preflight_id = ?
            """,
            (first.preflight_id,),
        ).fetchone()[0]
    finally:
        connection.close()
    assert count == 1


def test_same_verification_id_and_request_is_idempotent(tmp_path):
    db_path, run_id, evidence_id, fingerprint = _persisted_evidence(tmp_path)
    request = _verify_request(fingerprint=fingerprint)

    first = accept_verification_decision(
        db_path=db_path,
        run_id=run_id,
        evidence_id=evidence_id,
        request=request,
        actor_fingerprint="actor-hash",
    )
    second = accept_verification_decision(
        db_path=db_path,
        run_id=run_id,
        evidence_id=evidence_id,
        request=request,
        actor_fingerprint="actor-hash",
    )

    assert first.decision == second.decision
    assert second.idempotent_replay is True


def test_decision_rejects_missing_actor_fingerprint(tmp_path):
    db_path, run_id, evidence_id, fingerprint = _persisted_evidence(tmp_path)

    with pytest.raises(
        VerificationConflict,
        match="verification_persistence_conflict",
    ):
        accept_verification_decision(
            db_path=db_path,
            run_id=run_id,
            evidence_id=evidence_id,
            request=_verify_request(fingerprint=fingerprint),
            actor_fingerprint="",
        )


def test_same_verification_id_with_different_request_conflicts(tmp_path):
    db_path, run_id, evidence_id, fingerprint = _persisted_evidence(tmp_path)
    accept_verification_decision(
        db_path=db_path,
        run_id=run_id,
        evidence_id=evidence_id,
        request=_verify_request(fingerprint=fingerprint),
        actor_fingerprint="actor-hash",
    )

    with pytest.raises(VerificationConflict, match="verification_id_conflict"):
        accept_verification_decision(
            db_path=db_path,
            run_id=run_id,
            evidence_id=evidence_id,
            request=_reject_request(
                verification_id="verification-1",
                fingerprint=fingerprint,
                expected_revision=1,
            ),
            actor_fingerprint="actor-hash",
        )


def test_stale_fingerprint_fails_without_persistence(tmp_path):
    db_path, run_id, evidence_id, _ = _persisted_evidence(tmp_path)

    with pytest.raises(
        VerificationConflict,
        match="evidence_fingerprint_mismatch",
    ):
        accept_verification_decision(
            db_path=db_path,
            run_id=run_id,
            evidence_id=evidence_id,
            request=_verify_request(fingerprint="b" * 64),
            actor_fingerprint="actor-hash",
        )

    connection = sqlite3.connect(db_path)
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM evidence_verification_decisions_v2"
        ).fetchone()[0]
    finally:
        connection.close()
    assert count == 0


def test_correction_appends_revision_two_and_keeps_revision_one(tmp_path):
    db_path, run_id, evidence_id, fingerprint = _persisted_evidence(tmp_path)
    accept_verification_decision(
        db_path=db_path,
        run_id=run_id,
        evidence_id=evidence_id,
        request=_verify_request(fingerprint=fingerprint),
        actor_fingerprint="actor-hash",
    )

    corrected = accept_verification_decision(
        db_path=db_path,
        run_id=run_id,
        evidence_id=evidence_id,
        request=_reject_request(
            fingerprint=fingerprint,
            expected_revision=1,
        ),
        actor_fingerprint="actor-hash",
    )
    projection = get_effective_verification(
        db_path=db_path,
        run_id=run_id,
        evidence_id=evidence_id,
    )

    assert corrected.decision.revision == 2
    assert projection.verification_status == "unverified"
    assert projection.verification_state == "rejected"
    assert projection.verification_origin == "human"
    connection = sqlite3.connect(db_path)
    try:
        revisions = [
            row[0]
            for row in connection.execute(
                """
                SELECT revision
                FROM evidence_verification_decisions_v2
                ORDER BY revision
                """
            )
        ]
    finally:
        connection.close()
    assert revisions == [1, 2]


def test_expected_revision_fences_concurrent_writers(tmp_path):
    db_path, run_id, evidence_id, fingerprint = _persisted_evidence(tmp_path)
    init_evidence_verification_schema(db_path)

    def submit(index):
        return accept_verification_decision(
            db_path=db_path,
            run_id=run_id,
            evidence_id=evidence_id,
            request=_verify_request(
                verification_id=f"verification-{index}",
                fingerprint=fingerprint,
                expected_revision=0,
            ),
            actor_fingerprint=f"actor-{index}",
        )

    outcomes = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(submit, index) for index in (1, 2)]
        for future in futures:
            try:
                outcomes.append(future.result())
            except VerificationConflict as exc:
                outcomes.append(exc.code)

    assert sum(not isinstance(item, str) for item in outcomes) == 1
    assert outcomes.count("verification_revision_conflict") == 1


def test_blocked_preflight_cannot_verify_but_can_reject(tmp_path):
    db_path, run_id, evidence_id, fingerprint = _persisted_evidence(
        tmp_path,
        source_url="https://other.example.com/role",
        declared_source_url="https://jobs.example.com/role",
    )

    with pytest.raises(
        VerificationConflict,
        match="evidence_preflight_blocked",
    ):
        accept_verification_decision(
            db_path=db_path,
            run_id=run_id,
            evidence_id=evidence_id,
            request=_verify_request(fingerprint=fingerprint),
            actor_fingerprint="actor-hash",
        )

    rejected = accept_verification_decision(
        db_path=db_path,
        run_id=run_id,
        evidence_id=evidence_id,
        request=_reject_request(
            fingerprint=fingerprint,
            expected_revision=0,
        ),
        actor_fingerprint="actor-hash",
    )
    assert rejected.decision.action == "reject"


def test_baseline_origin_is_not_human_and_legacy_status_alone_is_ignored(tmp_path):
    fixture = _persisted_evidence(
        tmp_path,
        suffix="fixture",
        baseline_origin="declared_fixture",
    )
    ordinary = _persisted_evidence(
        tmp_path,
        suffix="ordinary",
        baseline_origin="none",
    )

    fixture_projection = get_effective_verification(
        db_path=fixture[0],
        run_id=fixture[1],
        evidence_id=fixture[2],
    )
    ordinary_projection = get_effective_verification(
        db_path=ordinary[0],
        run_id=ordinary[1],
        evidence_id=ordinary[2],
    )

    assert fixture_projection.verification_origin == "declared_fixture"
    assert fixture_projection.verification_state == "verified"
    assert fixture_projection.verification_revision == 0
    assert ordinary_projection.verification_origin == "none"
    assert ordinary_projection.verification_state == "unverified"


def test_list_projection_is_stable_and_sorted_by_evidence_id(tmp_path):
    db_path, run_id, _, _ = _persisted_evidence(tmp_path)

    projections = list_effective_verifications(
        db_path=db_path,
        run_id=run_id,
    )

    assert projections == sorted(
        projections,
        key=lambda item: item.evidence_id,
    )
