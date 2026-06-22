from pydantic import ValidationError
import pytest

from agent.research import (
    EvidenceEntry,
    evidence_fingerprint_for,
    source_identity_for,
)
from api.evidence_verification_models import (
    VerificationDecisionRequest,
    canonical_hash,
    preflight_id_for,
    verification_request_hash,
)


def test_verify_requires_explicit_bounded_confirmation():
    with pytest.raises(ValidationError, match="confirm_source_match"):
        VerificationDecisionRequest(
            verification_id="verification-1",
            evidence_fingerprint="a" * 64,
            expected_revision=0,
            action="verify",
        )


def test_reject_requires_reason_and_rejects_verify_only_fields():
    with pytest.raises(ValidationError, match="reason_code"):
        VerificationDecisionRequest(
            verification_id="verification-1",
            evidence_fingerprint="a" * 64,
            expected_revision=0,
            action="reject",
        )

    with pytest.raises(ValidationError, match="reason_code"):
        VerificationDecisionRequest(
            verification_id="verification-1",
            evidence_fingerprint="a" * 64,
            expected_revision=0,
            action="verify",
            confirm_source_match=True,
            reason_code="content_mismatch",
        )


def test_rejection_note_is_bounded():
    with pytest.raises(ValidationError, match="reason_note"):
        VerificationDecisionRequest(
            verification_id="verification-1",
            evidence_fingerprint="a" * 64,
            expected_revision=0,
            action="reject",
            reason_code="other",
            reason_note="x" * 1001,
        )


def test_canonical_identities_ignore_mapping_order():
    first = {"run_id": "run-1", "checks": [{"code": "a", "passed": True}]}
    second = {"checks": [{"passed": True, "code": "a"}], "run_id": "run-1"}

    assert canonical_hash(first) == canonical_hash(second)
    assert preflight_id_for(first) == preflight_id_for(second)


def test_request_hash_binds_run_evidence_and_request():
    request = VerificationDecisionRequest(
        verification_id="verification-1",
        evidence_fingerprint="a" * 64,
        expected_revision=0,
        action="verify",
        confirm_source_match=True,
    )

    assert verification_request_hash(
        run_id="run-1",
        evidence_id="ev-1",
        request=request,
    ) != verification_request_hash(
        run_id="run-2",
        evidence_id="ev-1",
        request=request,
    )


def test_evidence_entry_has_immutable_baseline_origin_and_stable_fingerprint():
    entry = EvidenceEntry(
        thread_id="thread-1",
        query_text="query",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url="https://example.com/source.",
        snippet="  stable   snippet ",
        baseline_verification_origin="declared_fixture",
    )

    assert entry.source_identity == source_identity_for(
        "https://example.com/source."
    )
    assert entry.evidence_fingerprint == evidence_fingerprint_for(
        entry.source_identity,
        entry.snippet,
    )
    assert entry.baseline_verification_origin == "declared_fixture"


def test_evidence_entry_rejects_unknown_baseline_origin():
    with pytest.raises(ValueError, match="baseline_verification_origin"):
        EvidenceEntry(
            thread_id="thread-1",
            query_text="query",
            subagent_name="network_search",
            tool_name="internet_search",
            source_url="https://example.com/source",
            snippet="snippet",
            baseline_verification_origin="human",
        )
