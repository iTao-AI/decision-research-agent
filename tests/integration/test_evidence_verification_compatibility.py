from datetime import datetime, timezone
from pathlib import Path

from agent.research import EvidenceEntry
from agent.talent_contracts import ResearchPacket
from api.evidence_verification_repository import get_effective_verification
from api.run_repository import (
    create_run,
    finalize_run_transaction,
    get_run,
)
from api.talent_artifacts import build_talent_artifacts


def test_declared_fixture_origin_preserves_p1a_artifact_contract(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    scope = {
        "target_roles": ["AI Agent Engineer"],
        "target_companies": [],
        "time_window": {"start": "2026-01-01", "end": "2026-06-12"},
        "declared_samples": [
            {
                "sample_id": "aggregate-v1",
                "source_type": "provided_aggregate",
                "reference": "aggregate-v1",
            }
        ],
        "allowed_source_types": ["provided_aggregate"],
        "research_questions": ["question-1"],
        "requested_outputs": ["decision_brief"],
    }
    created = create_run(
        db_path=db_path,
        thread_id="thread-1",
        query="query",
        profile_id="talent-hiring-signal",
        scope=scope,
    )
    evidence = EvidenceEntry(
        thread_id="thread-1",
        query_text="query",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url="https://jobs.example.com/role",
        snippet="Evaluation and observability are required.",
        citation_status="cited",
        verification_status="verified",
        baseline_verification_origin="declared_fixture",
    )
    evidence_id = (
        f"ev_{created['run_id']}_{evidence.evidence_fingerprint}"
    )
    packet = ResearchPacket.model_validate(
        {
            "packet_id": "packet-1",
            "scope_id": "aggregate-v1",
            "findings": [
                {
                    "finding_id": "finding-1",
                    "research_question_id": "question-1",
                    "statement": "Evaluation is present.",
                    "evidence_refs": [evidence_id],
                    "sample_scope": "declared aggregate",
                    "confidence": 0.8,
                }
            ],
            "candidate_claims": [
                {
                    "claim_id": "claim-1",
                    "text": "Evaluation is a hiring signal.",
                    "claim_type": "signal",
                    "finding_refs": ["finding-1"],
                    "evidence_refs": [evidence_id],
                    "confidence": 0.8,
                    "citation_status": "cited",
                    "verification_status": "unverified",
                    "review_status": "pending",
                    "conflict_status": "none",
                }
            ],
        }
    )
    review, brief, artifacts = build_talent_artifacts(
        run_id=created["run_id"],
        scope=scope,
        packets=[packet],
        evidence_entries=[evidence],
        generated_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
    )

    assert finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        review_status=review.status,
        delivery_status="ready",
        evidence_entries=[evidence],
        research_packets=[packet],
        review_bundle=review,
        artifacts=artifacts,
    )

    stored = get_run(db_path=db_path, run_id=created["run_id"])
    projection = get_effective_verification(
        db_path=db_path,
        run_id=created["run_id"],
        evidence_id=evidence_id,
    )

    assert brief.evidence_summary[0]["verification_status"] == "verified"
    assert review.status == "not_required"
    assert stored["evidence"][0]["verification_status"] == "verified"
    assert "baseline_verification_origin" not in stored["evidence"][0]
    assert projection.verification_origin == "declared_fixture"
    assert projection.verification_state == "verified"
    assert projection.verification_revision == 0


def test_pr1_creates_no_publication_or_new_review_revision_tables(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    created = create_run(
        db_path=db_path,
        thread_id="thread-1",
        query="query",
    )

    get_effective_verification(
        db_path=db_path,
        run_id=created["run_id"],
        evidence_id="missing",
    )

    import sqlite3

    connection = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        connection.close()
    assert "run_publications_v2" not in tables


def test_authority_adr_states_exact_legacy_backfill_boundary():
    adr = (
        Path(__file__).parents[2]
        / "docs"
        / "decisions"
        / "evidence-verification-authority.md"
    ).read_text(encoding="utf-8")

    assert "aggregate-only Talent scope" in adr
    assert "legacy `verification_status=verified`" in adr


def test_pr2_public_contract_docs_cover_supersession_and_operator_cli():
    root = Path(__file__).resolve().parents[2]
    api_contract = (root / "spec/api-contract.md").read_text(encoding="utf-8")
    data_models = (root / "spec/data-models.md").read_text(encoding="utf-8")
    integration = (root / "docs/AGENT_INTEGRATION.md").read_text(
        encoding="utf-8"
    )
    runbook = (
        root / "docs/operations/evidence-verification-workflow.md"
    ).read_text(encoding="utf-8")
    release_notes = (root / "docs/releases/v0.1.0.md").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")

    assert "approved | rejected | manual_recovery | superseded" in api_contract
    assert "`superseded`" in data_models
    assert "同一 `run_id` 内创建新的 publication revision" in data_models
    assert "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION" in integration
    assert "evidence_verification.status" in integration
    assert "evidence list" in integration
    assert "evidence finalize" in integration
    assert "publication_migration_backup_already_exists" in runbook
    assert "decision_history" in runbook
    assert "controlled durable review and evidence verification workflows" in release_notes
    assert "Application DB = business authority" in release_notes
    assert "Controlled Evidence Verification" in readme
