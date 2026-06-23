from __future__ import annotations

import json
import sqlite3

import pytest

import api.publication_repository as publication_repository
from api.evidence_verification_repository import init_evidence_verification_schema
from api.publication_repository import (
    PUBLICATION_MIGRATION_VERSION,
    adopt_baseline_publication,
    migrate_publication_with_backup,
    verify_publication_schema,
)
from api.run_repository import create_run


NOW = "2026-06-23T00:00:00+00:00"


def _connect(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _seed_revision_one_review_database(
    tmp_path,
    *,
    with_resolution: bool = True,
    with_canonical_artifact: bool = True,
    bundle_status: str | None = None,
    run_review_status: str | None = None,
    delivery_status: str | None = None,
    workflow_status: str | None = None,
) -> tuple[str, str]:
    db_path = str(tmp_path / "tasks.db")
    init_evidence_verification_schema(db_path)
    created = create_run(
        db_path=db_path,
        thread_id="thread-publication",
        query="query",
        profile_id="talent-hiring-signal",
        scope={
            "target_roles": ["AI Agent Engineer"],
            "target_companies": [],
            "time_window": {
                "start": "2026-01-01",
                "end": "2026-06-23",
            },
            "declared_samples": [],
            "allowed_source_types": ["public_job_posting"],
            "research_questions": ["question"],
            "requested_outputs": ["decision_brief"],
        },
    )
    run_id = created["run_id"]
    review_id = "review_revision_1"
    decision_id = "decision_revision_1"
    connection = _connect(db_path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE research_runs_v2
                SET execution_status = 'completed',
                    review_status = ?,
                    delivery_status = ?,
                    state_version = 3,
                    updated_at = ?
                WHERE run_id = ?
                """,
                (
                    run_review_status
                    or ("resolved" if with_resolution else "required"),
                    delivery_status
                    or ("ready" if with_resolution else "review_required"),
                    NOW,
                    run_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO review_bundles_v2(
                    review_id, run_id, revision, status, bundle_json, created_at
                ) VALUES (?, ?, 1, ?, ?, ?)
                """,
                (
                    review_id,
                    run_id,
                    bundle_status
                    or ("resolved" if with_resolution else "required"),
                    json.dumps(
                        {
                            "review_id": review_id,
                            "run_id": run_id,
                            "revision": 1,
                        },
                        sort_keys=True,
                    ),
                    NOW,
                ),
            )
            selected_workflow_status = (
                workflow_status
                if workflow_status is not None
                else ("approved" if with_resolution else "waiting_decision")
            )
            if selected_workflow_status:
                connection.execute(
                    """
                    INSERT INTO review_workflows_v2(
                        workflow_id, run_id, review_id, review_revision,
                        checkpoint_thread_id, status, post_review_segment_id,
                        lease_owner, lease_expires_at,
                        attempt_count, created_at, updated_at
                    ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        "workflow_revision_1",
                        run_id,
                        review_id,
                        "checkpoint_revision_1",
                        selected_workflow_status,
                        "segment_revision_1",
                        (
                            "legacy-worker"
                            if selected_workflow_status == "waiting_decision"
                            else None
                        ),
                        (
                            "2999-01-01T00:00:00+00:00"
                            if selected_workflow_status == "waiting_decision"
                            else None
                        ),
                        NOW,
                        NOW,
                    ),
                )
            if with_resolution:
                connection.execute(
                    """
                    INSERT INTO review_decisions_v2(
                        decision_id, run_id, review_id, review_revision,
                        action, reason, actor_fingerprint, request_hash,
                        accepted_state_version, created_at
                    ) VALUES (?, ?, ?, 1, 'approve', NULL, ?, ?, 2, ?)
                    """,
                    (
                        decision_id,
                        run_id,
                        review_id,
                        "actor",
                        "request",
                        NOW,
                    ),
                )
                if selected_workflow_status:
                    connection.execute(
                        """
                        UPDATE review_workflows_v2
                        SET decision_id = ?
                        WHERE workflow_id = 'workflow_revision_1'
                        """,
                        (decision_id,),
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
                        "resolution_revision_1",
                        run_id,
                        review_id,
                        decision_id,
                        NOW,
                    ),
                )
            if with_canonical_artifact:
                connection.execute(
                    """
                    INSERT INTO run_artifacts_v2(
                        artifact_id, run_id, kind, media_type, content,
                        content_hash, created_at
                    ) VALUES (
                        'decision-brief.json', ?, 'decision_brief_json',
                        'application/json', '{}', ?, ?
                    )
                    """,
                    (run_id, "a" * 64, NOW),
                )
    finally:
        connection.close()
    return db_path, run_id


def _seed_human_verification_decision(db_path: str, run_id: str) -> None:
    connection = _connect(db_path)
    try:
        segment_id = connection.execute(
            "SELECT segment_id FROM run_segments WHERE run_id = ?",
            (run_id,),
        ).fetchone()["segment_id"]
        with connection:
            connection.execute(
                """
                INSERT INTO evidence_entries_v2(
                    evidence_id, run_id, segment_id, query_text,
                    subagent_name, tool_name, source_url, source_identity,
                    snippet, evidence_fingerprint, retrieved_at,
                    tool_call_id, citation_status, verification_status,
                    baseline_verification_origin, created_at
                ) VALUES (
                    'evidence_migration', ?, ?, 'query', 'agent', 'tool',
                    'https://example.com', 'https://example.com',
                    'snippet', 'fingerprint', NULL, NULL,
                    'cited', 'unverified', 'none', ?
                )
                """,
                (run_id, segment_id, NOW),
            )
            connection.execute(
                """
                INSERT INTO evidence_verification_preflights_v2(
                    preflight_id, run_id, evidence_id,
                    evidence_fingerprint, preflight_version, status,
                    checks_json, preflight_hash, created_at
                ) VALUES (
                    'preflight_migration', ?, 'evidence_migration',
                    'fingerprint', '1', 'eligible', '[]',
                    'preflight-hash', ?
                )
                """,
                (run_id, NOW),
            )
            connection.execute(
                """
                INSERT INTO evidence_verification_decisions_v2(
                    verification_id, run_id, evidence_id,
                    evidence_fingerprint, revision, action,
                    reason_code, reason_note, preflight_id,
                    actor_fingerprint, request_hash, created_at
                ) VALUES (
                    'verification_migration', ?, 'evidence_migration',
                    'fingerprint', 1, 'verify', NULL, NULL,
                    'preflight_migration', 'actor', 'request-hash', ?
                )
                """,
                (run_id, NOW),
            )
    finally:
        connection.close()


def _review_rows(db_path: str) -> dict[str, list[tuple]]:
    connection = _connect(db_path)
    try:
        return {
            table: [
                tuple(row)
                for row in connection.execute(
                    f"SELECT * FROM {table} ORDER BY 1"
                ).fetchall()
            ]
            for table in (
                "review_bundles_v2",
                "review_decisions_v2",
                "review_workflows_v2",
                "review_resolutions_v2",
            )
        }
    finally:
        connection.close()


def _database_dump(db_path: str) -> list[str]:
    connection = sqlite3.connect(db_path)
    try:
        return list(connection.iterdump())
    finally:
        connection.close()


def test_publication_migration_preserves_existing_review_rows(tmp_path):
    db_path, _ = _seed_revision_one_review_database(tmp_path)
    backup_path = str(tmp_path / "backup.db")
    before = _review_rows(db_path)

    migrate_publication_with_backup(
        db_path=db_path,
        backup_path=backup_path,
    )

    assert _review_rows(db_path) == before


def test_migrated_schema_allows_two_review_revisions_for_one_run(tmp_path):
    db_path, run_id = _seed_revision_one_review_database(tmp_path)
    migrate_publication_with_backup(
        db_path=db_path,
        backup_path=str(tmp_path / "backup.db"),
    )
    connection = _connect(db_path)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO review_bundles_v2(
                    review_id, run_id, revision, status, bundle_json, created_at
                ) VALUES ('review_revision_2', ?, 2, 'required', '{}', ?)
                """,
                (run_id, NOW),
            )
            connection.execute(
                """
                INSERT INTO review_workflows_v2(
                    workflow_id, run_id, review_id, review_revision,
                    checkpoint_thread_id, status, post_review_segment_id,
                    attempt_count, created_at, updated_at
                ) VALUES (
                    'workflow_revision_2', ?, 'review_revision_2', 2,
                    'checkpoint_revision_2', 'waiting_decision',
                    'segment_revision_2', 0, ?, ?
                )
                """,
                (run_id, NOW, NOW),
            )
            connection.execute(
                """
                INSERT INTO review_decisions_v2(
                    decision_id, run_id, review_id, review_revision,
                    action, reason, actor_fingerprint, request_hash,
                    accepted_state_version, created_at
                ) VALUES (
                    'decision_revision_2', ?, 'review_revision_2', 2,
                    'reject', 'reason', 'actor', 'request-2', 4, ?
                )
                """,
                (run_id, NOW),
            )
            connection.execute(
                """
                INSERT INTO review_resolutions_v2(
                    resolution_id, run_id, review_id, decision_id,
                    action, resolved_review_json, artifact_ids_json, created_at
                ) VALUES (
                    'resolution_revision_2', ?, 'review_revision_2',
                    'decision_revision_2', 'reject', '{}', '[]', ?
                )
                """,
                (run_id, NOW),
            )
        revisions = [
            row[0]
            for row in connection.execute(
                """
                SELECT revision FROM review_bundles_v2
                WHERE run_id = ? ORDER BY revision
                """,
                (run_id,),
            )
        ]
    finally:
        connection.close()

    assert revisions == [1, 2]


def test_publication_partial_index_rejects_two_current_rows(tmp_path):
    db_path, run_id = _seed_revision_one_review_database(tmp_path)
    migrate_publication_with_backup(
        db_path=db_path,
        backup_path=str(tmp_path / "backup.db"),
    )
    connection = _connect(db_path)
    try:
        current = connection.execute(
            """
            SELECT verification_snapshot_id, review_id
            FROM run_publications_v2
            WHERE run_id = ? AND is_current = 1
            """,
            (run_id,),
        ).fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            with connection:
                connection.execute(
                    """
                    INSERT INTO run_publications_v2(
                        publication_id, run_id, revision,
                        verification_snapshot_id, review_id, status,
                        is_current, artifact_ids_json, content_hash,
                        supersedes_publication_id, created_at,
                        resolved_at, staled_at
                    ) VALUES (
                        'publication_duplicate', ?, 2, ?, ?,
                        'review_required', 1, '[]', ?, NULL, ?, NULL, NULL
                    )
                    """,
                    (
                        run_id,
                        f"{current['verification_snapshot_id']}_other",
                        current["review_id"],
                        "b" * 64,
                        NOW,
                    ),
                )
    finally:
        connection.close()


def test_publication_migration_backfills_revision_one_current_head(tmp_path):
    db_path, run_id = _seed_revision_one_review_database(tmp_path)

    migrate_publication_with_backup(
        db_path=db_path,
        backup_path=str(tmp_path / "backup.db"),
    )

    connection = _connect(db_path)
    try:
        publication = connection.execute(
            """
            SELECT revision, status, is_current, artifact_ids_json
            FROM run_publications_v2
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        snapshot_count = connection.execute(
            """
            SELECT COUNT(*) FROM evidence_verification_snapshots_v2
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()[0]
    finally:
        connection.close()

    assert dict(publication) == {
        "revision": 1,
        "status": "ready",
        "is_current": 1,
        "artifact_ids_json": '["decision-brief.json"]',
    }
    assert snapshot_count == 1


def test_not_required_ready_run_backfills_and_adopts_ready_without_workflow(
    tmp_path,
):
    db_path, run_id = _seed_revision_one_review_database(
        tmp_path,
        with_resolution=False,
        bundle_status="not_required",
        run_review_status="not_required",
        delivery_status="ready",
        workflow_status="",
    )
    migrate_publication_with_backup(
        db_path=db_path,
        backup_path=str(tmp_path / "backup.db"),
    )

    connection = _connect(db_path)
    try:
        publication = connection.execute(
            """
            SELECT status, is_current FROM run_publications_v2
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        workflow_count = connection.execute(
            "SELECT COUNT(*) FROM review_workflows_v2 WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]
        with connection:
            connection.execute(
                "DELETE FROM run_publications_v2 WHERE run_id = ?",
                (run_id,),
            )
            adopted = adopt_baseline_publication(
                connection,
                run_id=run_id,
            )
    finally:
        connection.close()

    assert dict(publication) == {"status": "ready", "is_current": 1}
    assert workflow_count == 0
    assert adopted.status == "ready"
    assert adopted.is_current is True


@pytest.mark.parametrize(
    ("with_resolution", "workflow_status", "expected_workflow_status"),
    [
        (False, "waiting_decision", "superseded"),
        (True, "approved", "approved"),
    ],
)
def test_human_verification_migration_revokes_ready_run_and_supersedes_active(
    tmp_path,
    with_resolution,
    workflow_status,
    expected_workflow_status,
):
    db_path, run_id = _seed_revision_one_review_database(
        tmp_path,
        with_resolution=with_resolution,
        run_review_status="resolved",
        delivery_status="ready",
        workflow_status=workflow_status,
    )
    _seed_human_verification_decision(db_path, run_id)

    migrate_publication_with_backup(
        db_path=db_path,
        backup_path=str(tmp_path / "backup.db"),
    )

    connection = _connect(db_path)
    try:
        run = connection.execute(
            """
            SELECT review_status, delivery_status, state_version
            FROM research_runs_v2 WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        publication = connection.execute(
            """
            SELECT status, is_current FROM run_publications_v2
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        workflow = connection.execute(
            """
            SELECT status, lease_owner, lease_expires_at
            FROM review_workflows_v2 WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
    finally:
        connection.close()

    assert dict(run) == {
        "review_status": "required",
        "delivery_status": "review_required",
        "state_version": 4,
    }
    assert dict(publication) == {"status": "stale", "is_current": 0}
    assert workflow["status"] == expected_workflow_status
    if expected_workflow_status == "superseded":
        assert workflow["lease_owner"] is None
        assert workflow["lease_expires_at"] is None


def test_publication_migration_skips_run_without_canonical_artifact(tmp_path):
    db_path, run_id = _seed_revision_one_review_database(
        tmp_path,
        with_canonical_artifact=False,
    )

    migrate_publication_with_backup(
        db_path=db_path,
        backup_path=str(tmp_path / "backup.db"),
    )

    connection = _connect(db_path)
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM run_publications_v2 WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]
    finally:
        connection.close()
    assert count == 0


def test_failed_publication_migration_restores_backup(tmp_path, monkeypatch):
    db_path, _ = _seed_revision_one_review_database(tmp_path)
    backup_path = str(tmp_path / "backup.db")
    before = _database_dump(db_path)
    monkeypatch.setattr(
        publication_repository,
        "verify_publication_schema",
        lambda **_: (_ for _ in ()).throw(RuntimeError("forced")),
    )

    with pytest.raises(RuntimeError, match="forced"):
        migrate_publication_with_backup(
            db_path=db_path,
            backup_path=backup_path,
        )

    assert _database_dump(db_path) == before
    assert _database_dump(backup_path) == before


def test_publication_schema_verification_reports_exact_marker(tmp_path):
    db_path, _ = _seed_revision_one_review_database(tmp_path)
    migrate_publication_with_backup(
        db_path=db_path,
        backup_path=str(tmp_path / "backup.db"),
    )

    result = verify_publication_schema(db_path=db_path)

    assert PUBLICATION_MIGRATION_VERSION in result["migration_versions"]


def test_restart_after_migration_preserves_original_backup(tmp_path):
    db_path, _ = _seed_revision_one_review_database(tmp_path)
    backup_path = str(tmp_path / "backup.db")
    before = _database_dump(db_path)

    migrate_publication_with_backup(
        db_path=db_path,
        backup_path=backup_path,
    )
    backup_after_first_start = _database_dump(backup_path)
    migrate_publication_with_backup(
        db_path=db_path,
        backup_path=backup_path,
    )

    assert backup_after_first_start == before
    assert _database_dump(backup_path) == before


def test_existing_backup_without_marker_fails_closed(tmp_path):
    db_path, _ = _seed_revision_one_review_database(tmp_path)
    backup_path = str(tmp_path / "backup.db")
    sqlite3.connect(backup_path).close()

    with pytest.raises(
        RuntimeError,
        match="publication_migration_backup_already_exists",
    ):
        migrate_publication_with_backup(
            db_path=db_path,
            backup_path=backup_path,
        )
