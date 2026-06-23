from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3

import pytest

from api.publication_models import publication_id_for
from api.publication_repository import migrate_publication_with_backup
from api.review_models import ReviewDecisionRequest
from api.review_repository import (
    ReviewConflict,
    accept_review_decision,
    claim_review_workflow,
    get_original_decision_brief,
    get_review_detail,
    get_review_projection,
)
from tests.unit.test_review_repository import _required_review_run


NOW = "2026-06-23T00:00:00+00:00"


@dataclass(frozen=True)
class RevisionedReviewRun:
    db_path: str
    run_id: str
    review_id_1: str
    review_id_2: str
    workflow_id_1: str
    workflow_id_2: str
    post_review_segment_id_2: str
    state_version: int


def _connect(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _add_revision_two(
    tmp_path,
    *,
    workflow_status: str,
    current_status: str = "review_required",
) -> RevisionedReviewRun:
    required = _required_review_run(tmp_path, suffix="revisioned")
    migrate_publication_with_backup(
        db_path=required.db_path,
        backup_path=str(tmp_path / "publication-backup.db"),
    )
    review_id_2 = "review_revision_2"
    workflow_id_2 = "workflow_revision_2"
    segment_id_2 = f"{required.run_id}_seg_review_revision_2"
    snapshot_id_2 = "vsnap_revision_2"
    connection = _connect(required.db_path)
    try:
        with connection:
            first_brief = connection.execute(
                """
                SELECT content, content_hash
                FROM run_artifacts_v2
                WHERE run_id = ? AND artifact_id = 'decision-brief.json'
                """,
                (required.run_id,),
            ).fetchone()
            connection.execute(
                """
                UPDATE run_publications_v2
                SET status = 'stale', is_current = 0, staled_at = ?
                WHERE run_id = ? AND revision = 1
                """,
                (NOW, required.run_id),
            )
            connection.execute(
                """
                UPDATE review_workflows_v2
                SET status = 'superseded'
                WHERE workflow_id = ?
                """,
                (required.workflow_id,),
            )
            connection.execute(
                """
                INSERT INTO evidence_verification_snapshots_v2(
                    snapshot_id, run_id, revision, snapshot_json,
                    snapshot_hash, created_at
                ) VALUES (?, ?, 2, '[]', ?, ?)
                """,
                (snapshot_id_2, required.run_id, "b" * 64, NOW),
            )
            connection.execute(
                """
                INSERT INTO review_bundles_v2(
                    review_id, run_id, revision, status, bundle_json, created_at
                ) VALUES (?, ?, 2, 'required', ?, ?)
                """,
                (
                    review_id_2,
                    required.run_id,
                    json.dumps(
                        {
                            "review_id": review_id_2,
                            "run_id": required.run_id,
                            "revision": 2,
                        },
                        sort_keys=True,
                    ),
                    NOW,
                ),
            )
            connection.execute(
                """
                INSERT INTO review_workflows_v2(
                    workflow_id, run_id, review_id, review_revision,
                    checkpoint_thread_id, status, post_review_segment_id,
                    attempt_count, created_at, updated_at
                ) VALUES (?, ?, ?, 2, ?, ?, ?, 0, ?, ?)
                """,
                (
                    workflow_id_2,
                    required.run_id,
                    review_id_2,
                    "checkpoint_revision_2",
                    workflow_status,
                    segment_id_2,
                    NOW,
                    NOW,
                ),
            )
            connection.execute(
                """
                INSERT INTO run_artifacts_v2(
                    artifact_id, run_id, kind, media_type, content,
                    content_hash, created_at
                ) VALUES (
                    'decision-brief.r2.json', ?, 'decision_brief_json',
                    'application/json', ?, ?, ?
                )
                """,
                (
                    required.run_id,
                    first_brief["content"],
                    first_brief["content_hash"],
                    NOW,
                ),
            )
            connection.execute(
                """
                INSERT INTO run_publications_v2(
                    publication_id, run_id, revision,
                    verification_snapshot_id, review_id, status,
                    is_current, artifact_ids_json, content_hash,
                    supersedes_publication_id, created_at,
                    resolved_at, staled_at
                ) VALUES (?, ?, 2, ?, ?, ?, 1, ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    publication_id_for(
                        run_id=required.run_id,
                        revision=2,
                        verification_snapshot_id=snapshot_id_2,
                    ),
                    required.run_id,
                    snapshot_id_2,
                    review_id_2,
                    current_status,
                    '["decision-brief.r2.json"]',
                    first_brief["content_hash"],
                    publication_id_for(
                        run_id=required.run_id,
                        revision=1,
                        verification_snapshot_id=connection.execute(
                            """
                            SELECT verification_snapshot_id
                            FROM run_publications_v2
                            WHERE run_id = ? AND revision = 1
                            """,
                            (required.run_id,),
                        ).fetchone()[0],
                    ),
                    NOW,
                ),
            )
        state_version = connection.execute(
            """
            SELECT state_version FROM research_runs_v2 WHERE run_id = ?
            """,
            (required.run_id,),
        ).fetchone()[0]
    finally:
        connection.close()
    return RevisionedReviewRun(
        db_path=required.db_path,
        run_id=required.run_id,
        review_id_1=required.review_id,
        review_id_2=review_id_2,
        workflow_id_1=required.workflow_id,
        workflow_id_2=workflow_id_2,
        post_review_segment_id_2=segment_id_2,
        state_version=state_version,
    )


def _resolve_both_revisions(seeded: RevisionedReviewRun) -> None:
    connection = _connect(seeded.db_path)
    try:
        with connection:
            for revision, review_id, workflow_id in (
                (1, seeded.review_id_1, seeded.workflow_id_1),
                (2, seeded.review_id_2, seeded.workflow_id_2),
            ):
                decision_id = f"decision_revision_{revision}"
                connection.execute(
                    """
                    INSERT INTO review_decisions_v2(
                        decision_id, run_id, review_id, review_revision,
                        action, reason, actor_fingerprint, request_hash,
                        accepted_state_version, created_at
                    ) VALUES (?, ?, ?, ?, 'approve', NULL, 'actor', ?, ?, ?)
                    """,
                    (
                        decision_id,
                        seeded.run_id,
                        review_id,
                        revision,
                        f"request-{revision}",
                        revision + 2,
                        NOW,
                    ),
                )
                connection.execute(
                    """
                    UPDATE review_workflows_v2
                    SET status = 'approved', decision_id = ?
                    WHERE workflow_id = ?
                    """,
                    (decision_id, workflow_id),
                )
                connection.execute(
                    """
                    INSERT INTO review_resolutions_v2(
                        resolution_id, run_id, review_id, decision_id,
                        action, resolved_review_json, artifact_ids_json,
                        created_at
                    ) VALUES (?, ?, ?, ?, 'approve', '{}', '[]', ?)
                    """,
                    (
                        f"resolution_revision_{revision}",
                        seeded.run_id,
                        review_id,
                        decision_id,
                        NOW,
                    ),
                )
    finally:
        connection.close()


def test_review_projection_uses_current_publication_review(tmp_path):
    seeded = _add_revision_two(
        tmp_path,
        workflow_status="waiting_decision",
    )

    projection = get_review_projection(
        run_id=seeded.run_id,
        db_path=seeded.db_path,
    )

    assert projection["workflow"]["review_revision"] == 2


def test_review_detail_selects_decision_and_resolution_by_review_id(tmp_path):
    seeded = _add_revision_two(
        tmp_path,
        workflow_status="approved",
        current_status="ready",
    )
    _resolve_both_revisions(seeded)

    first = get_review_detail(
        run_id=seeded.run_id,
        review_id=seeded.review_id_1,
        db_path=seeded.db_path,
    )
    second = get_review_detail(
        run_id=seeded.run_id,
        review_id=seeded.review_id_2,
        db_path=seeded.db_path,
    )

    assert first["decision"]["review_id"] == seeded.review_id_1
    assert first["resolution"]["review_id"] == seeded.review_id_1
    assert second["decision"]["review_id"] == seeded.review_id_2
    assert second["resolution"]["review_id"] == seeded.review_id_2


def test_post_review_segment_sequence_matches_review_revision(tmp_path):
    seeded = _add_revision_two(
        tmp_path,
        workflow_status="checkpoint_pending",
    )

    claim = claim_review_workflow(
        db_path=seeded.db_path,
        worker_id="worker_1",
        lease_seconds=30,
    )

    connection = _connect(seeded.db_path)
    try:
        segment = connection.execute(
            """
            SELECT sequence FROM run_segments
            WHERE segment_id = ?
            """,
            (claim.post_review_segment_id,),
        ).fetchone()
    finally:
        connection.close()
    assert segment["sequence"] == claim.review_revision == 2


def test_superseded_workflow_is_not_claimed_or_decided(tmp_path):
    seeded = _add_revision_two(
        tmp_path,
        workflow_status="superseded",
    )

    assert claim_review_workflow(
        db_path=seeded.db_path,
        worker_id="worker_1",
        lease_seconds=30,
    ) is None
    with pytest.raises(ReviewConflict, match="review_superseded"):
        accept_review_decision(
            db_path=seeded.db_path,
            run_id=seeded.run_id,
            review_id=seeded.review_id_2,
            request=ReviewDecisionRequest(
                decision_id="decision_superseded",
                review_revision=2,
                action="approve",
                expected_state_version=seeded.state_version,
            ),
            actor_fingerprint="actor",
        )


def test_original_decision_brief_uses_publication_bound_artifact(tmp_path):
    seeded = _add_revision_two(
        tmp_path,
        workflow_status="waiting_decision",
    )
    connection = _connect(seeded.db_path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE run_artifacts_v2
                SET content = '{"revision": 2}'
                WHERE run_id = ? AND artifact_id = 'decision-brief.r2.json'
                """,
                (seeded.run_id,),
            )
    finally:
        connection.close()

    assert get_original_decision_brief(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        review_id=seeded.review_id_2,
    ) == '{"revision": 2}'
