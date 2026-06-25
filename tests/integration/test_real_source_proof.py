from pathlib import Path
import json
import sqlite3

from api.evidence_verification_models import VerificationDecisionRequest
from api.evidence_verification_repository import accept_verification_decision
from api.publication_repository import (
    finalize_verification_publication,
    get_current_publication,
    migrate_publication_with_backup,
)
from api.review_artifacts import build_reviewed_artifacts
from api.review_models import ReviewDecisionRequest
from api.review_repository import (
    accept_review_decision,
    get_original_decision_brief,
    get_review_detail,
    resolve_review,
)
from api.run_repository import get_run
from scripts.real_source_proof import (
    assert_complete_proof_report,
    seed_real_source_run,
)


def _write_manifest(tmp_path: Path, records: list[dict]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "manifest_id": "talent-agent-hiring-signals-v1",
                "manifest_version": 1,
                "question": "What hiring signals appear in AI Agent roles?",
                "records": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _record(sample_id: str, url: str = "https://example.com/careers/agent"):
    return {
        "sample_id": sample_id,
        "source_url": url,
        "source_title": "Agent infrastructure role",
        "organization": "Example",
        "observed_at": "2026-06-23T00:00:00Z",
        "observation": "The role asks for agent infrastructure reliability work.",
        "source_type": "public_job_posting",
    }


def _baseline_origins(db_path: str, run_id: str) -> set[str]:
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT baseline_verification_origin
            FROM evidence_entries_v2
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        connection.close()


def _mark_review_waiting(db_path: str, workflow_id: str) -> None:
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE review_workflows_v2
                SET status = 'waiting_decision'
                WHERE workflow_id = ?
                """,
                (workflow_id,),
            )
    finally:
        connection.close()


def test_seed_real_source_run_persists_origin_none(tmp_path):
    manifest_path = _write_manifest(
        tmp_path,
        [
            _record(f"real_source_00{i}", f"https://example.com/careers/{i}")
            for i in range(1, 6)
        ],
    )
    db_path = str(tmp_path / "tasks.db")

    result = seed_real_source_run(
        manifest_path=manifest_path,
        db_path=db_path,
    )

    run = get_run(db_path=db_path, run_id=result["run_id"])
    assert run["profile_id"] == "talent-hiring-signal"
    assert len(run["evidence"]) == 5
    assert _baseline_origins(db_path, result["run_id"]) == {"none"}
    assert run["review_status"] == "required"
    assert run["delivery_status"] == "review_required"


def test_real_source_lifecycle_requires_human_verification_and_fresh_review(tmp_path):
    manifest_path = _write_manifest(
        tmp_path,
        [
            _record(f"real_source_00{i}", f"https://example.com/careers/{i}")
            for i in range(1, 6)
        ],
    )
    db_path = str(tmp_path / "tasks.db")
    seeded = seed_real_source_run(manifest_path=manifest_path, db_path=db_path)
    migrate_publication_with_backup(
        db_path=db_path,
        backup_path=str(tmp_path / "backup.db"),
    )
    run = get_run(db_path=db_path, run_id=seeded["run_id"])

    for index, evidence in enumerate(run["evidence"], start=1):
        accept_verification_decision(
            db_path=db_path,
            run_id=seeded["run_id"],
            evidence_id=evidence["evidence_id"],
            request=VerificationDecisionRequest(
                verification_id=f"verification-real-{index}",
                evidence_fingerprint=evidence["evidence_fingerprint"],
                expected_revision=0,
                action="verify",
                confirm_source_match=True,
            ),
            actor_fingerprint="operator",
        )

    first = finalize_verification_publication(
        db_path=db_path,
        run_id=seeded["run_id"],
        expected_state_version=get_run(db_path=db_path, run_id=seeded["run_id"])[
            "state_version"
        ],
    )
    second = finalize_verification_publication(
        db_path=db_path,
        run_id=seeded["run_id"],
        expected_state_version=get_run(db_path=db_path, run_id=seeded["run_id"])[
            "state_version"
        ],
    )
    assert second.idempotent_replay is True
    assert second.publication.publication_id == first.publication.publication_id

    detail = get_review_detail(
        db_path=db_path,
        run_id=seeded["run_id"],
        review_id=first.publication.review_id,
    )
    _mark_review_waiting(db_path, detail["workflow"]["workflow_id"])
    detail = get_review_detail(
        db_path=db_path,
        run_id=seeded["run_id"],
        review_id=first.publication.review_id,
    )
    accepted = accept_review_decision(
        db_path=db_path,
        run_id=seeded["run_id"],
        review_id=first.publication.review_id,
        request=ReviewDecisionRequest(
            decision_id="decision-real-proof",
            review_revision=detail["review_revision"],
            action="approve",
            expected_state_version=detail["state_version"],
        ),
        actor_fingerprint="operator",
    )
    result = build_reviewed_artifacts(
        original_brief_json=get_original_decision_brief(
            db_path=db_path,
            run_id=seeded["run_id"],
            review_id=first.publication.review_id,
        ),
        decision=accepted.decision,
        revision=first.publication.revision,
    )
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE review_workflows_v2
                SET status = 'resolution_pending',
                    lease_owner = 'worker',
                    lease_expires_at = '2999-01-01T00:00:00+00:00',
                    attempt_count = 1
                WHERE workflow_id = ?
                """,
                (detail["workflow"]["workflow_id"],),
            )
            connection.execute(
                """
                INSERT INTO review_resume_attempts_v2(
                    workflow_id, attempt, worker_id, started_at
                ) VALUES (?, 1, 'worker', '2026-06-23T00:00:00+00:00')
                """,
                (detail["workflow"]["workflow_id"],),
            )
    finally:
        connection.close()
    resolve_review(
        db_path=db_path,
        workflow_id=detail["workflow"]["workflow_id"],
        worker_id="worker",
        expected_run_state_version=accepted.decision.accepted_state_version,
        result=result,
    )

    current = get_current_publication(db_path=db_path, run_id=seeded["run_id"])
    assert current is not None
    assert current.status == "ready"
    assert current.is_current is True

    assert_complete_proof_report(
        {
            "manifest_id": seeded["manifest_id"],
            "manifest_hash": seeded["manifest_hash"],
            "run_id": seeded["run_id"],
            "source_count": seeded["evidence_count"],
            "decision_mode": "human_operator",
            "verification_summary": {"unresolved_count": 0},
            "publication": {"status": current.status},
            "review": {"status": "approved"},
            "artifact_hashes": {},
            "limits": ["bounded sample"],
        }
    )
