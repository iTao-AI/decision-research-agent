from datetime import datetime, timezone
import json

from agent.talent_contracts import DecisionBrief, ResearchScope
from api.decision_brief import with_content_hash
from api.review_artifacts import build_reviewed_artifacts
from api.review_models import ReviewDecisionRecord


def _brief_json() -> str:
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
            run_id="run_1",
            profile_id="talent-hiring-signal",
            profile_version="1",
            input_snapshot_hash="input_hash",
            renderer_version="2",
            canonicalization_version="1",
            scope=scope,
            executive_summary="Summary",
            findings=[],
            claims=[],
            evidence_summary=[
                {
                    "evidence_id": "ev_1",
                    "source_url": "https://example.com",
                    "snippet": "Evidence",
                    "verification_status": "unverified",
                }
            ],
            conflicts=[],
            limitations=[],
            recommendations=[],
            review_summary={
                "review_id": "review_1",
                "status": "required",
                "required_before_delivery": True,
            },
            quality_summary={"status": "passed"},
            generated_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
        )
    )
    return json.dumps(
        brief.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _decision(action: str) -> ReviewDecisionRecord:
    return ReviewDecisionRecord(
        decision_id=f"decision_{action}",
        run_id="run_1",
        review_id="review_1",
        review_revision=1,
        action=action,
        reason="Internal detail" if action == "reject" else None,
        actor_fingerprint="actor_hash",
        request_hash="request_hash",
        accepted_state_version=3,
        created_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
    )


def test_approval_builds_deterministic_reviewed_artifacts_without_verifying_evidence():
    first = build_reviewed_artifacts(
        original_brief_json=_brief_json(),
        decision=_decision("approve"),
    )
    second = build_reviewed_artifacts(
        original_brief_json=_brief_json(),
        decision=_decision("approve"),
    )

    assert first == second
    reviewed = first.brief
    assert reviewed is not None
    assert reviewed.review_summary["status"] == "resolved"
    assert reviewed.review_summary["decision"]["action"] == "approve"
    assert (
        reviewed.review_summary["decision"]["reviewer_kind"]
        == "service_credential"
    )
    assert reviewed.review_summary["decision"]["reason_recorded"] is False
    assert "reason" not in reviewed.review_summary["decision"]
    assert all(
        item["verification_status"] == "unverified"
        for item in reviewed.evidence_summary
    )
    assert {item["artifact_id"] for item in first.artifacts} == {
        "decision-brief.reviewed.json",
        "decision-brief.reviewed.md",
    }


def test_rejection_creates_no_reviewed_delivery_artifacts():
    result = build_reviewed_artifacts(
        original_brief_json=_brief_json(),
        decision=_decision("reject"),
    )

    assert result.brief is None
    assert result.resolved_review["decision"]["reason_recorded"] is True
    assert "reason" not in result.resolved_review["decision"]
    assert result.artifacts == []


def test_revision_two_uses_revisioned_reviewed_artifact_ids():
    result = build_reviewed_artifacts(
        original_brief_json=_brief_json(),
        decision=_decision("approve").model_copy(
            update={
                "review_id": "review_2",
                "review_revision": 2,
            }
        ),
        revision=2,
    )

    assert {item["artifact_id"] for item in result.artifacts} == {
        "decision-brief.r2.reviewed.json",
        "decision-brief.r2.reviewed.md",
    }
