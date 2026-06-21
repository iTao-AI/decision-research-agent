import pytest
from pydantic import ValidationError

from api.review_models import (
    ReviewDecisionRequest,
    ReviewListQuery,
    checkpoint_thread_id,
    decode_review_cursor,
    decision_request_hash,
    durable_hitl_enabled,
    encode_review_cursor,
    post_review_segment_id,
    review_resolution_id,
    review_workflow_id,
)


def _request(**overrides) -> ReviewDecisionRequest:
    payload = {
        "decision_id": "decision_001",
        "review_revision": 1,
        "action": "approve",
        "expected_state_version": 2,
    }
    payload.update(overrides)
    return ReviewDecisionRequest(**payload)


def test_reject_requires_reason():
    with pytest.raises(ValidationError, match="reason"):
        _request(action="reject")


def test_approve_accepts_optional_reason():
    request = _request()
    assert request.reason is None


def test_review_identities_are_stable_and_scoped():
    first = review_workflow_id("run_1", "review_1", 1)
    assert first == review_workflow_id("run_1", "review_1", 1)
    assert first != review_workflow_id("run_2", "review_1", 1)
    assert checkpoint_thread_id(first).startswith("review_rwf_")
    assert post_review_segment_id("run_1", "review_1", 1).startswith(
        "run_1_seg_review_"
    )


def test_resolution_identity_is_stable_and_decision_scoped():
    assert review_resolution_id("decision_1") == review_resolution_id("decision_1")
    assert review_resolution_id("decision_1") != review_resolution_id("decision_2")


def test_decision_request_hash_is_stable_and_content_scoped():
    request = _request(reason="Reviewed")
    first = decision_request_hash(
        run_id="run_1",
        review_id="review_1",
        request=request,
    )
    assert first == decision_request_hash(
        run_id="run_1",
        review_id="review_1",
        request=request,
    )
    assert first != decision_request_hash(
        run_id="run_2",
        review_id="review_1",
        request=request,
    )


def test_decision_request_rejects_unbounded_identifier():
    with pytest.raises(ValidationError, match="decision_id"):
        _request(decision_id="../decision")


def test_review_cursor_round_trips_without_exposing_sql():
    cursor = encode_review_cursor(
        created_at="2026-06-20T00:00:00+00:00",
        workflow_id="rwf_example",
    )

    assert decode_review_cursor(cursor) == (
        "2026-06-20T00:00:00+00:00",
        "rwf_example",
    )
    assert "rwf_example" not in cursor


def test_review_cursor_rejects_invalid_datetime_and_workflow_id():
    invalid_datetime = encode_review_cursor(
        created_at="not-a-datetime",
        workflow_id="rwf_example",
    )
    invalid_workflow_id = encode_review_cursor(
        created_at="2026-06-20T00:00:00+00:00",
        workflow_id="../workflow",
    )

    with pytest.raises(ValueError, match="invalid_review_cursor"):
        decode_review_cursor(invalid_datetime)
    with pytest.raises(ValueError, match="invalid_review_cursor"):
        decode_review_cursor(invalid_workflow_id)


def test_review_list_query_rejects_unknown_status_and_unbounded_limit():
    with pytest.raises(ValidationError):
        ReviewListQuery(status="unknown")
    with pytest.raises(ValidationError):
        ReviewListQuery(limit=101)


def test_durable_hitl_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv(
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL",
        raising=False,
    )
    assert durable_hitl_enabled() is False


def test_durable_hitl_requires_explicit_true(monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "TRUE")
    assert durable_hitl_enabled() is True

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "1")
    assert durable_hitl_enabled() is False
