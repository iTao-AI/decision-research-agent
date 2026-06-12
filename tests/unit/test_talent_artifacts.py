from datetime import datetime, timezone


def test_talent_artifacts_are_deterministic_and_require_review_for_unknown_evidence():
    from agent.talent_contracts import ResearchPacket
    from api.talent_artifacts import build_talent_artifacts

    packet = ResearchPacket.model_validate(
        {
            "packet_id": "packet-1",
            "scope_id": "scope-1",
            "findings": [{
                "finding_id": "finding-1",
                "research_question_id": "question-1",
                "statement": "Signal",
                "evidence_refs": ["ev_missing"],
                "sample_scope": "declared",
                "confidence": 0.8,
            }],
            "candidate_claims": [{
                "claim_id": "claim-1",
                "text": "Claim",
                "claim_type": "signal",
                "finding_refs": ["finding-1"],
                "evidence_refs": ["ev_missing"],
                "confidence": 0.8,
                "citation_status": "cited",
                "verification_status": "unverified",
                "review_status": "pending",
                "conflict_status": "none",
            }],
        }
    )
    scope = {
        "target_roles": ["AI Agent Engineer"],
        "target_companies": [],
        "time_window": {"start": "2026-01-01", "end": "2026-06-12"},
        "declared_samples": [],
        "allowed_source_types": ["public_job_posting"],
        "research_questions": ["question-1"],
        "requested_outputs": ["decision_brief"],
    }
    generated_at = datetime(2026, 6, 12, tzinfo=timezone.utc)

    first = build_talent_artifacts(
        run_id="run-1", scope=scope, packets=[packet], evidence_entries=[],
        generated_at=generated_at,
    )
    second = build_talent_artifacts(
        run_id="run-1", scope=scope, packets=[packet], evidence_entries=[],
        generated_at=generated_at,
    )

    assert first[0].status == "required"
    assert "missing_evidence_ref:claim-1:ev_missing" in first[0].triggers
    assert first[2] == second[2]
