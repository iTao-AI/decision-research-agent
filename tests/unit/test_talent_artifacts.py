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
    assert "missing_evidence_ref:finding-1:ev_missing" in first[0].triggers
    assert "missing_evidence_ref:claim-1:ev_missing" in first[0].triggers
    assert first[2] == second[2]
    assert first[1].renderer_version == "2"
    assert first[1].schema_version == "1"
    assert first[1].canonicalization_version == "1"
    assert [artifact["artifact_id"] for artifact in first[2]] == [
        "decision-brief.json",
        "decision-brief.md",
    ]
    assert [artifact["media_type"] for artifact in first[2]] == [
        "application/json",
        "text/markdown",
    ]


def test_talent_artifacts_require_review_for_findings_and_claims_without_evidence():
    from agent.talent_contracts import Claim, Finding, ResearchPacket
    from api.talent_artifacts import build_talent_artifacts

    packet = ResearchPacket.model_construct(
        packet_id="packet-1",
        scope_id="scope-1",
        findings=[
            Finding.model_construct(
                finding_id="finding-1",
                research_question_id="question-1",
                statement="Signal",
                evidence_refs=[],
                sample_scope="declared",
                confidence=0.8,
            )
        ],
        candidate_claims=[
            Claim.model_construct(
                claim_id="claim-1",
                text="Claim",
                claim_type="signal",
                finding_refs=["finding-1"],
                evidence_refs=[],
                confidence=0.8,
                citation_status="uncited",
                verification_status="unverified",
                review_status="pending",
                conflict_status="none",
            )
        ],
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

    review, brief, _ = build_talent_artifacts(
        run_id="run-1",
        scope=scope,
        packets=[packet],
        evidence_entries=[],
        generated_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
    )

    assert review.status == "required"
    assert review.required_before_delivery is True
    assert "finding_without_evidence:finding-1" in review.triggers
    assert "claim_without_evidence:claim-1" in review.triggers
    assert brief.review_summary["required_before_delivery"] is True


def test_revision_two_uses_new_ids_and_snapshot_metadata():
    from agent.research import EvidenceEntry
    from agent.talent_contracts import ResearchPacket
    from api.evidence_verification_models import EffectiveEvidenceVerification
    from api.talent_artifacts import build_talent_artifacts

    entry = EvidenceEntry(
        thread_id="thread-1",
        query_text="query",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url="https://example.com/job",
        snippet="Evidence",
    )
    evidence_id = f"ev_run-1_{entry.evidence_fingerprint}"
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
    scope = {
        "target_roles": ["AI Agent Engineer"],
        "target_companies": [],
        "time_window": {"start": "2026-01-01", "end": "2026-06-12"},
        "declared_samples": [],
        "allowed_source_types": ["public_job_posting"],
        "research_questions": ["question-1"],
        "requested_outputs": ["decision_brief"],
    }

    review, brief, artifacts = build_talent_artifacts(
        run_id="run-1",
        scope=scope,
        packets=[packet],
        evidence_entries=[entry],
        generated_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
        revision=2,
        verification_snapshot_id="vsnap_2",
        verification_snapshot_hash="a" * 64,
        verification_by_evidence_id={
            evidence_id: EffectiveEvidenceVerification(
                run_id="run-1",
                evidence_id=evidence_id,
                evidence_fingerprint=entry.evidence_fingerprint,
                verification_status="verified",
                verification_state="verified",
                verification_origin="human",
                verification_revision=1,
                decision_id="verification_1",
            )
        },
        mandatory_review_triggers=("verification_snapshot_changed",),
    )

    assert [artifact["artifact_id"] for artifact in artifacts] == [
        "decision-brief.r2.json",
        "decision-brief.r2.md",
    ]
    assert review.revision == 2
    assert "verification_snapshot_changed" in review.triggers
    assert brief.quality_summary["publication_revision"] == 2
    assert brief.quality_summary["verification_snapshot_id"] == "vsnap_2"
    assert brief.quality_summary["verification_state_counts"] == {
        "verified": 1
    }
    assert brief.evidence_summary[0]["verification_origin"] == "human"
