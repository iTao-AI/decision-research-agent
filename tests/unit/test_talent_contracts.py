from datetime import date

import pytest
from pydantic import ValidationError


def _scope_payload():
    return {
        "target_roles": ["AI Agent Engineer"],
        "target_companies": ["Example Company"],
        "time_window": {"start": "2026-01-01", "end": "2026-06-12"},
        "declared_samples": [
            {
                "sample_id": "sample-1",
                "source_type": "public_job_posting",
                "reference": "https://example.com/job",
            }
        ],
        "allowed_source_types": ["public_job_posting"],
        "research_questions": ["Which skills recur?"],
        "requested_outputs": ["decision_brief"],
    }


def test_research_scope_accepts_declared_bounded_public_samples():
    from agent.talent_contracts import ResearchScope

    scope = ResearchScope.model_validate(_scope_payload())

    assert scope.time_window.start == date(2026, 1, 1)
    assert scope.declared_samples[0].source_type == "public_job_posting"


def test_research_scope_rejects_more_than_366_days():
    from agent.talent_contracts import ResearchScope

    payload = _scope_payload()
    payload["time_window"] = {"start": "2025-01-01", "end": "2026-06-12"}

    with pytest.raises(ValidationError, match="366"):
        ResearchScope.model_validate(payload)


def test_research_scope_rejects_personal_candidate_fields():
    from agent.talent_contracts import ResearchScope

    payload = _scope_payload()
    payload["candidate_email"] = "person@example.com"

    with pytest.raises(ValidationError):
        ResearchScope.model_validate(payload)


def test_research_scope_rejects_non_url_public_job_posting_reference():
    from agent.talent_contracts import ResearchScope

    payload = _scope_payload()
    payload["declared_samples"][0]["reference"] = "internal note"

    with pytest.raises(ValidationError, match="http"):
        ResearchScope.model_validate(payload)


def test_deterministic_review_requires_claim_without_evidence():
    from agent.talent_contracts import Claim, EvidenceSnapshot
    from api.review_service import build_review_bundle

    claim = Claim(
        claim_id="claim-1",
        text="Agent skills recur across the declared sample.",
        claim_type="hiring_signal",
        finding_refs=["finding-1"],
        evidence_refs=[],
        confidence=0.9,
        citation_status="uncited",
        verification_status="unverified",
        review_status="pending",
        conflict_status="none",
        limitations=[],
    )

    bundle = build_review_bundle(
        run_id="run-1",
        claims=[claim],
        evidence=[],
        confidence_threshold=0.6,
    )

    assert bundle.status == "required"
    assert "claim_without_evidence:claim-1" in bundle.triggers
    assert bundle.required_before_delivery is True


def test_deterministic_review_does_not_invent_claims():
    from agent.talent_contracts import EvidenceSnapshot
    from api.review_service import build_review_bundle

    bundle = build_review_bundle(
        run_id="run-1",
        claims=[],
        evidence=[
            EvidenceSnapshot(
                evidence_id="ev-1",
                source_url="https://example.com",
                snippet="Evidence only",
                verification_status="unverified",
            )
        ],
        confidence_threshold=0.6,
    )

    assert bundle.claim_snapshots == []
    assert bundle.status == "not_required"


def _research_packet_payload():
    return {
        "packet_id": "packet-1",
        "scope_id": "scope-1",
        "findings": [
            {
                "finding_id": "finding-1",
                "research_question_id": "question-1",
                "statement": "Agent evaluation appears in the declared sample.",
                "evidence_refs": ["evidence-1"],
                "sample_scope": "declared samples",
                "confidence": 0.8,
            }
        ],
        "candidate_claims": [
            {
                "claim_id": "claim-1",
                "text": "Agent evaluation is a recurring signal.",
                "claim_type": "hiring_signal",
                "finding_refs": ["finding-1"],
                "evidence_refs": ["evidence-1"],
                "confidence": 0.8,
                "citation_status": "cited",
                "verification_status": "unverified",
                "review_status": "pending",
                "conflict_status": "none",
            }
        ],
    }


def test_research_packet_rejects_duplicate_finding_ids():
    from agent.talent_contracts import ResearchPacket

    payload = _research_packet_payload()
    payload["findings"].append(dict(payload["findings"][0]))

    with pytest.raises(ValueError, match="finding_id must be unique"):
        ResearchPacket.model_validate(payload)


def test_research_packet_rejects_claim_reference_to_unknown_finding():
    from agent.talent_contracts import ResearchPacket

    payload = _research_packet_payload()
    payload["candidate_claims"][0]["finding_refs"] = ["missing-finding"]

    with pytest.raises(ValueError, match="unknown finding"):
        ResearchPacket.model_validate(payload)
