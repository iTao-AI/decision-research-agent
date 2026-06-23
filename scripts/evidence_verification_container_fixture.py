from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys


project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from agent.research import EvidenceEntry
from agent.talent_contracts import ResearchPacket
from api.review_models import (
    checkpoint_thread_id,
    post_review_segment_id,
    review_workflow_id,
)
from api.run_repository import create_run, finalize_run_transaction
from api.talent_artifacts import build_talent_artifacts


def _scope() -> dict:
    return {
        "target_roles": ["AI Agent Engineer"],
        "target_companies": [],
        "time_window": {
            "start": "2026-01-01",
            "end": "2026-06-23",
        },
        "declared_samples": [{
            "sample_id": "container-job-1",
            "source_type": "public_job_posting",
            "reference": "https://example.com/container-job",
        }],
        "allowed_source_types": ["public_job_posting"],
        "research_questions": ["question-1"],
        "requested_outputs": ["decision_brief"],
    }


def seed() -> dict:
    db_path = os.environ["TASKS_DB_PATH"]
    created = create_run(
        db_path=db_path,
        thread_id="verification-container-thread",
        query="synthetic verification container fixture",
        profile_id="talent-hiring-signal",
        profile_version="1",
        scope=_scope(),
    )
    evidence = EvidenceEntry(
        thread_id="verification-container-thread",
        query_text="synthetic verification container fixture",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url="https://example.com/container-job",
        snippet="Synthetic persisted Evidence for the P2A canary.",
        citation_status="cited",
        retrieved_at="2026-06-23T00:00:00+00:00",
        created_at="2026-06-23T00:00:00+00:00",
    )
    evidence_id = (
        f"ev_{created['run_id']}_{evidence.evidence_fingerprint}"
    )
    packet = ResearchPacket.model_validate(
        {
            "packet_id": "container-packet-1",
            "scope_id": "container-scope-1",
            "findings": [{
                "finding_id": "finding-1",
                "research_question_id": "question-1",
                "statement": "Synthetic hiring signal.",
                "evidence_refs": [evidence_id],
                "sample_scope": "synthetic fixture",
                "confidence": 0.8,
            }],
            "candidate_claims": [{
                "claim_id": "claim-1",
                "text": "Synthetic candidate claim.",
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
        evidence_entries=[evidence],
        generated_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
    )
    workflow_id = review_workflow_id(
        created["run_id"],
        review.review_id,
        review.revision,
    )
    finalized = finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        review_status="required",
        delivery_status="review_required",
        evidence_entries=[evidence],
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
    if not finalized:
        raise RuntimeError("container_fixture_finalization_failed")
    return {
        "run_id": created["run_id"],
        "evidence_id": evidence_id,
    }


if __name__ == "__main__":
    print(json.dumps(seed(), sort_keys=True))
