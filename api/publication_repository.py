from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from api.evidence_verification_models import (
    EffectiveEvidenceVerification,
    canonical_hash,
    snapshot_id_for,
)
from api.evidence_verification_repository import (
    init_evidence_verification_schema,
)
from api.publication_models import publication_id_for
from api.publication_models import PublicationRecord
from api.publication_service import PublicationArtifacts, build_publication_artifacts
from api.review_models import (
    checkpoint_thread_id,
    post_review_segment_id,
    review_workflow_id,
)
from api.database import sqlite_db_path
from api.run_repository import _now


PUBLICATION_MIGRATION_VERSION = "006_revisioned_publication"
PUBLICATION_MIGRATION_CHECKSUM = "revisioned-publication-v1"

_REVIEW_BUNDLE_COLUMNS = (
    "review_id",
    "run_id",
    "revision",
    "status",
    "bundle_json",
    "created_at",
)
_REVIEW_WORKFLOW_COLUMNS = (
    "workflow_id",
    "run_id",
    "review_id",
    "review_revision",
    "checkpoint_thread_id",
    "status",
    "decision_id",
    "post_review_segment_id",
    "lease_owner",
    "lease_expires_at",
    "attempt_count",
    "last_error_code",
    "created_at",
    "updated_at",
)
_REVIEW_RESOLUTION_COLUMNS = (
    "resolution_id",
    "run_id",
    "review_id",
    "decision_id",
    "action",
    "resolved_review_json",
    "artifact_ids_json",
    "created_at",
)
_PUBLICATION_COLUMNS = (
    "publication_id",
    "run_id",
    "revision",
    "verification_snapshot_id",
    "review_id",
    "status",
    "is_current",
    "artifact_ids_json",
    "content_hash",
    "supersedes_publication_id",
    "created_at",
    "resolved_at",
    "staled_at",
)


@dataclass(frozen=True)
class PublicationFinalization:
    publication: PublicationRecord
    snapshot: Any
    workflow: dict[str, Any] | None
    artifacts: tuple[dict, ...]
    idempotent_replay: bool


class PublicationConflict(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def evidence_verification_enabled() -> bool:
    return os.getenv(
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION",
        "false",
    ).strip().lower() == "true"


def _connect_for_migration(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(sqlite_db_path(db_path))
    connection.row_factory = sqlite3.Row
    return connection


def publication_schema_exists(connection: sqlite3.Connection) -> bool:
    return (
        connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'run_publications_v2'
            """
        ).fetchone()
        is not None
    )


def _column_names(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    return tuple(
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})")
    )


def _row_count(connection: sqlite3.Connection, table: str) -> int:
    return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _copy_table(
    connection: sqlite3.Connection,
    *,
    source: str,
    target: str,
    columns: tuple[str, ...],
) -> None:
    column_sql = ", ".join(columns)
    connection.execute(
        f"INSERT INTO {target} ({column_sql}) "
        f"SELECT {column_sql} FROM {source}"
    )
    if _row_count(connection, source) != _row_count(connection, target):
        raise RuntimeError(f"publication_migration_row_count:{source}")


def _create_rebuilt_review_tables(connection: sqlite3.Connection) -> None:
    for statement in (
        """
        CREATE TABLE review_bundles_v2_new (
            review_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL
                REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
            revision INTEGER NOT NULL CHECK(revision >= 1),
            status TEXT NOT NULL,
            bundle_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(run_id, revision)
        )
        """,
        """
        CREATE TABLE review_workflows_v2_new (
            workflow_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL
                REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
            review_id TEXT NOT NULL
                REFERENCES review_bundles_v2_new(review_id)
                ON DELETE CASCADE,
            review_revision INTEGER NOT NULL CHECK(review_revision >= 1),
            checkpoint_thread_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            decision_id TEXT
                REFERENCES review_decisions_v2(decision_id),
            post_review_segment_id TEXT NOT NULL,
            lease_owner TEXT,
            lease_expires_at TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(run_id, review_revision)
        )
        """,
        """
        CREATE TABLE review_resolutions_v2_new (
            resolution_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL
                REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
            review_id TEXT NOT NULL
                REFERENCES review_bundles_v2_new(review_id)
                ON DELETE CASCADE,
            decision_id TEXT NOT NULL UNIQUE
                REFERENCES review_decisions_v2(decision_id),
            action TEXT NOT NULL CHECK(action IN ('approve', 'reject')),
            resolved_review_json TEXT NOT NULL,
            artifact_ids_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(run_id, review_id)
        )
        """,
    ):
        connection.execute(statement)


def _rebuild_review_tables(connection: sqlite3.Connection) -> None:
    _create_rebuilt_review_tables(connection)
    _copy_table(
        connection,
        source="review_bundles_v2",
        target="review_bundles_v2_new",
        columns=_REVIEW_BUNDLE_COLUMNS,
    )
    _copy_table(
        connection,
        source="review_workflows_v2",
        target="review_workflows_v2_new",
        columns=_REVIEW_WORKFLOW_COLUMNS,
    )
    _copy_table(
        connection,
        source="review_resolutions_v2",
        target="review_resolutions_v2_new",
        columns=_REVIEW_RESOLUTION_COLUMNS,
    )
    for statement in (
        "DROP TABLE review_resolutions_v2",
        "DROP TABLE review_workflows_v2",
        "DROP TABLE review_bundles_v2",
        "ALTER TABLE review_bundles_v2_new RENAME TO review_bundles_v2",
        "ALTER TABLE review_workflows_v2_new RENAME TO review_workflows_v2",
        "ALTER TABLE review_resolutions_v2_new RENAME TO review_resolutions_v2",
        """
        CREATE INDEX idx_review_workflows_status_lease
        ON review_workflows_v2(status, lease_expires_at, updated_at)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_review_decisions_run
        ON review_decisions_v2(run_id, created_at)
        """,
    ):
        connection.execute(statement)


def _create_publication_table(connection: sqlite3.Connection) -> None:
    for statement in (
        """
        CREATE TABLE run_publications_v2 (
            publication_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL
                REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
            revision INTEGER NOT NULL CHECK(revision >= 1),
            verification_snapshot_id TEXT NOT NULL
                REFERENCES evidence_verification_snapshots_v2(snapshot_id),
            review_id TEXT NOT NULL
                REFERENCES review_bundles_v2(review_id),
            status TEXT NOT NULL
                CHECK(
                    status IN (
                        'review_required',
                        'ready',
                        'blocked',
                        'stale'
                    )
                ),
            is_current INTEGER NOT NULL CHECK(is_current IN (0, 1)),
            artifact_ids_json TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            supersedes_publication_id TEXT
                REFERENCES run_publications_v2(publication_id),
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            staled_at TEXT,
            UNIQUE(run_id, revision),
            UNIQUE(run_id, verification_snapshot_id)
        )
        """,
        """
        CREATE UNIQUE INDEX idx_run_publications_current
        ON run_publications_v2(run_id)
        WHERE is_current = 1
        """,
        """
        CREATE INDEX idx_run_publications_review
        ON run_publications_v2(review_id)
        """,
    ):
        connection.execute(statement)


def _baseline_projection(row: sqlite3.Row) -> EffectiveEvidenceVerification:
    if row["baseline_verification_origin"] == "declared_fixture":
        return EffectiveEvidenceVerification(
            run_id=row["run_id"],
            evidence_id=row["evidence_id"],
            evidence_fingerprint=row["evidence_fingerprint"],
            verification_status="verified",
            verification_state="verified",
            verification_origin="declared_fixture",
            verification_revision=0,
        )
    return EffectiveEvidenceVerification(
        run_id=row["run_id"],
        evidence_id=row["evidence_id"],
        evidence_fingerprint=row["evidence_fingerprint"],
        verification_status="unverified",
        verification_state="unverified",
        verification_origin="none",
        verification_revision=0,
    )


def _baseline_snapshot(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    created_at: str,
) -> str:
    evidence = connection.execute(
        """
        SELECT *
        FROM evidence_entries_v2
        WHERE run_id = ?
        ORDER BY evidence_id
        """,
        (run_id,),
    ).fetchall()
    payload = [
        _baseline_projection(row).model_dump(mode="json")
        for row in evidence
    ]
    snapshot_hash = canonical_hash(payload)
    existing = connection.execute(
        """
        SELECT snapshot_id
        FROM evidence_verification_snapshots_v2
        WHERE run_id = ? AND snapshot_hash = ?
        """,
        (run_id, snapshot_hash),
    ).fetchone()
    if existing is not None:
        return existing["snapshot_id"]
    revision = connection.execute(
        """
        SELECT COALESCE(MAX(revision), 0) + 1
        FROM evidence_verification_snapshots_v2
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()[0]
    snapshot_id = snapshot_id_for(
        run_id=run_id,
        snapshot_hash=snapshot_hash,
    )
    connection.execute(
        """
        INSERT INTO evidence_verification_snapshots_v2(
            snapshot_id, run_id, revision, snapshot_json,
            snapshot_hash, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot_id,
            run_id,
            revision,
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            snapshot_hash,
            created_at,
        ),
    )
    return snapshot_id


def _publication_status(
    row: sqlite3.Row,
    *,
    has_human_decisions: bool,
) -> tuple[str, int, str | None, str | None]:
    if has_human_decisions:
        return "stale", 0, None, row["updated_at"]
    if (
        row["bundle_status"] == "not_required"
        and row["delivery_status"] == "ready"
    ):
        return "ready", 1, row["updated_at"], None
    if row["resolution_action"] == "approve" and row["delivery_status"] == "ready":
        return "ready", 1, row["resolution_created_at"] or row["updated_at"], None
    if row["resolution_action"] == "reject" or row["delivery_status"] == "blocked":
        return "blocked", 1, row["resolution_created_at"] or row["updated_at"], None
    return "review_required", 1, None, None


def _backfill_publications(connection: sqlite3.Connection) -> None:
    noncompleted_residue = connection.execute(
        """
        SELECT 1
        FROM research_runs_v2 AS run
        WHERE run.execution_status NOT IN (
            'completed',
            'completed_with_fallback'
        )
          AND (
            EXISTS (
                SELECT 1 FROM review_bundles_v2 AS bundle
                WHERE bundle.run_id = run.run_id
            )
            OR EXISTS (
                SELECT 1 FROM run_publications_v2 AS publication
                WHERE publication.run_id = run.run_id
            )
          )
        LIMIT 1
        """
    ).fetchone()
    if noncompleted_residue is not None:
        raise PublicationConflict("verification_publication_conflict")

    runs = connection.execute(
        """
        SELECT
            run.run_id,
            run.delivery_status,
            run.updated_at,
            bundle.review_id,
            bundle.status AS bundle_status,
            bundle.created_at AS review_created_at,
            resolution.action AS resolution_action,
            resolution.created_at AS resolution_created_at,
            artifact.content_hash
        FROM research_runs_v2 AS run
        JOIN review_bundles_v2 AS bundle
          ON bundle.run_id = run.run_id AND bundle.revision = 1
        JOIN run_artifacts_v2 AS artifact
          ON artifact.run_id = run.run_id
         AND artifact.artifact_id = 'decision-brief.json'
        LEFT JOIN review_resolutions_v2 AS resolution
          ON resolution.run_id = run.run_id
         AND resolution.review_id = bundle.review_id
        WHERE run.profile_id = 'talent-hiring-signal'
        ORDER BY run.run_id
        """
    ).fetchall()
    for row in runs:
        human_decision = connection.execute(
            """
            SELECT 1
            FROM evidence_verification_decisions_v2
            WHERE run_id = ?
            LIMIT 1
            """,
            (row["run_id"],),
        ).fetchone()
        created_at = row["review_created_at"] or row["updated_at"]
        snapshot_id = _baseline_snapshot(
            connection,
            run_id=row["run_id"],
            created_at=created_at,
        )
        artifacts = [
            artifact["artifact_id"]
            for artifact in connection.execute(
                """
                SELECT artifact_id
                FROM run_artifacts_v2
                WHERE run_id = ?
                  AND artifact_id IN (
                    'decision-brief.json',
                    'decision-brief.md',
                    'decision-brief.reviewed.json',
                    'decision-brief.reviewed.md'
                  )
                ORDER BY artifact_id
                """,
                (row["run_id"],),
            ).fetchall()
        ]
        status, is_current, resolved_at, staled_at = _publication_status(
            row,
            has_human_decisions=human_decision is not None,
        )
        connection.execute(
            """
            INSERT INTO run_publications_v2(
                publication_id, run_id, revision,
                verification_snapshot_id, review_id, status,
                is_current, artifact_ids_json, content_hash,
                supersedes_publication_id, created_at,
                resolved_at, staled_at
            ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (
                publication_id_for(
                    run_id=row["run_id"],
                    revision=1,
                    verification_snapshot_id=snapshot_id,
                ),
                row["run_id"],
                snapshot_id,
                row["review_id"],
                status,
                is_current,
                json.dumps(artifacts, separators=(",", ":")),
                row["content_hash"],
                created_at,
                resolved_at,
                staled_at,
            ),
        )
        if human_decision is not None:
            connection.execute(
                """
                UPDATE research_runs_v2
                SET review_status = 'required',
                    delivery_status = 'review_required',
                    state_version = state_version + 1,
                    updated_at = ?
                WHERE run_id = ?
                """,
                (row["updated_at"], row["run_id"]),
            )
            connection.execute(
                """
                UPDATE review_workflows_v2
                SET status = 'superseded',
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    updated_at = ?
                WHERE run_id = ? AND review_id = ?
                  AND status IN (
                    'checkpoint_pending',
                    'waiting_decision',
                    'resume_pending',
                    'resuming',
                    'resolution_pending'
                  )
                """,
                (row["updated_at"], row["run_id"], row["review_id"]),
            )


def _publication_record(row: sqlite3.Row) -> PublicationRecord:
    return PublicationRecord.model_validate(
        {
            "publication_id": row["publication_id"],
            "run_id": row["run_id"],
            "revision": row["revision"],
            "verification_snapshot_id": row[
                "verification_snapshot_id"
            ],
            "review_id": row["review_id"],
            "status": row["status"],
            "is_current": bool(row["is_current"]),
            "artifact_ids": tuple(
                json.loads(row["artifact_ids_json"])
            ),
            "content_hash": row["content_hash"],
            "supersedes_publication_id": row[
                "supersedes_publication_id"
            ],
            "created_at": row["created_at"],
            "resolved_at": row["resolved_at"],
            "staled_at": row["staled_at"],
        }
    )


def get_publication(
    *,
    db_path: str,
    publication_id: str,
) -> PublicationRecord | None:
    connection = _connect_for_migration(db_path)
    try:
        if not publication_schema_exists(connection):
            return None
        row = connection.execute(
            """
            SELECT * FROM run_publications_v2
            WHERE publication_id = ?
            """,
            (publication_id,),
        ).fetchone()
        return _publication_record(row) if row is not None else None
    finally:
        connection.close()


def get_publication_by_revision(
    *,
    db_path: str,
    run_id: str,
    revision: int,
) -> PublicationRecord | None:
    connection = _connect_for_migration(db_path)
    try:
        if not publication_schema_exists(connection):
            return None
        row = connection.execute(
            """
            SELECT * FROM run_publications_v2
            WHERE run_id = ? AND revision = ?
            """,
            (run_id, revision),
        ).fetchone()
        return _publication_record(row) if row is not None else None
    finally:
        connection.close()


def get_current_publication(
    *,
    db_path: str,
    run_id: str,
) -> PublicationRecord | None:
    connection = _connect_for_migration(db_path)
    try:
        if not publication_schema_exists(connection):
            return None
        row = connection.execute(
            """
            SELECT * FROM run_publications_v2
            WHERE run_id = ? AND is_current = 1
            """,
            (run_id,),
        ).fetchone()
        return _publication_record(row) if row is not None else None
    finally:
        connection.close()


def count_current_publications(
    *,
    db_path: str,
    run_id: str,
) -> int:
    connection = _connect_for_migration(db_path)
    try:
        if not publication_schema_exists(connection):
            return 0
        return connection.execute(
            """
            SELECT COUNT(*) FROM run_publications_v2
            WHERE run_id = ? AND is_current = 1
            """,
            (run_id,),
        ).fetchone()[0]
    finally:
        connection.close()


def adopt_baseline_publication(
    connection: sqlite3.Connection,
    *,
    run_id: str,
) -> PublicationRecord | None:
    if not publication_schema_exists(connection):
        return None
    existing = connection.execute(
        """
        SELECT * FROM run_publications_v2
        WHERE run_id = ?
        ORDER BY revision
        LIMIT 1
        """,
        (run_id,),
    ).fetchone()
    if existing is not None:
        return _publication_record(existing)
    row = connection.execute(
        """
        SELECT
            run.run_id,
            run.delivery_status,
            run.updated_at,
            bundle.review_id,
            bundle.status AS bundle_status,
            bundle.created_at AS review_created_at,
            resolution.action AS resolution_action,
            resolution.created_at AS resolution_created_at,
            artifact.content_hash
        FROM research_runs_v2 AS run
        JOIN review_bundles_v2 AS bundle
          ON bundle.run_id = run.run_id AND bundle.revision = 1
        JOIN run_artifacts_v2 AS artifact
          ON artifact.run_id = run.run_id
         AND artifact.artifact_id = 'decision-brief.json'
        LEFT JOIN review_resolutions_v2 AS resolution
          ON resolution.run_id = run.run_id
         AND resolution.review_id = bundle.review_id
        WHERE run.run_id = ?
          AND run.profile_id = 'talent-hiring-signal'
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    created_at = row["review_created_at"] or row["updated_at"]
    snapshot_id = _baseline_snapshot(
        connection,
        run_id=run_id,
        created_at=created_at,
    )
    artifacts = [
        artifact["artifact_id"]
        for artifact in connection.execute(
            """
            SELECT artifact_id FROM run_artifacts_v2
            WHERE run_id = ?
              AND artifact_id IN (
                'decision-brief.json',
                'decision-brief.md',
                'decision-brief.reviewed.json',
                'decision-brief.reviewed.md'
              )
            ORDER BY artifact_id
            """,
            (run_id,),
        ).fetchall()
    ]
    human_decision = connection.execute(
        """
        SELECT 1 FROM evidence_verification_decisions_v2
        WHERE run_id = ? LIMIT 1
        """,
        (run_id,),
    ).fetchone()
    status, is_current, resolved_at, staled_at = _publication_status(
        row,
        has_human_decisions=human_decision is not None,
    )
    publication_id = publication_id_for(
        run_id=run_id,
        revision=1,
        verification_snapshot_id=snapshot_id,
    )
    connection.execute(
        """
        INSERT INTO run_publications_v2(
            publication_id, run_id, revision,
            verification_snapshot_id, review_id, status,
            is_current, artifact_ids_json, content_hash,
            supersedes_publication_id, created_at,
            resolved_at, staled_at
        ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
        """,
        (
            publication_id,
            run_id,
            snapshot_id,
            row["review_id"],
            status,
            is_current,
            json.dumps(artifacts, separators=(",", ":")),
            row["content_hash"],
            created_at,
            resolved_at,
            staled_at,
        ),
    )
    stored = connection.execute(
        """
        SELECT * FROM run_publications_v2
        WHERE publication_id = ?
        """,
        (publication_id,),
    ).fetchone()
    return _publication_record(stored)


def stale_current_publication(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    now: str,
) -> str | None:
    if not publication_schema_exists(connection):
        return None
    current = connection.execute(
        """
        SELECT publication_id, review_id
        FROM run_publications_v2
        WHERE run_id = ? AND is_current = 1
        """,
        (run_id,),
    ).fetchone()
    if current is None:
        return None
    publication_cursor = connection.execute(
        """
        UPDATE run_publications_v2
        SET status = 'stale', is_current = 0, staled_at = ?
        WHERE publication_id = ? AND is_current = 1
        """,
        (now, current["publication_id"]),
    )
    if publication_cursor.rowcount != 1:
        raise PublicationConflict("verification_publication_conflict")
    connection.execute(
        """
        UPDATE review_workflows_v2
        SET status = 'superseded',
            lease_owner = NULL,
            lease_expires_at = NULL,
            updated_at = ?
        WHERE run_id = ? AND review_id = ?
          AND status IN (
            'checkpoint_pending',
            'waiting_decision',
            'resume_pending',
            'resuming',
            'resolution_pending'
          )
        """,
        (now, run_id, current["review_id"]),
    )
    run_cursor = connection.execute(
        """
        UPDATE research_runs_v2
        SET review_status = 'required',
            delivery_status = 'review_required',
            state_version = state_version + 1,
            updated_at = ?
        WHERE run_id = ?
          AND execution_status IN (
            'completed',
            'completed_with_fallback'
          )
        """,
        (now, run_id),
    )
    if run_cursor.rowcount != 1:
        raise PublicationConflict("verification_publication_conflict")
    return current["publication_id"]


def _apply_publication_migration(db_path: str) -> None:
    init_evidence_verification_schema(db_path)
    connection = _connect_for_migration(db_path)
    try:
        marker = connection.execute(
            """
            SELECT checksum
            FROM schema_migrations
            WHERE version = ?
            """,
            (PUBLICATION_MIGRATION_VERSION,),
        ).fetchone()
        if marker is not None:
            if marker["checksum"] != PUBLICATION_MIGRATION_CHECKSUM:
                raise RuntimeError("publication_migration_checksum_mismatch")
            return

        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN IMMEDIATE")
        try:
            _rebuild_review_tables(connection)
            _create_publication_table(connection)
            _backfill_publications(connection)
            foreign_key_errors = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            if foreign_key_errors:
                raise RuntimeError(
                    f"publication_migration_foreign_keys:{foreign_key_errors}"
                )
            connection.execute(
                """
                INSERT INTO schema_migrations(version, applied_at, checksum)
                VALUES (?, ?, ?)
                """,
                (
                    PUBLICATION_MIGRATION_VERSION,
                    _now(),
                    PUBLICATION_MIGRATION_CHECKSUM,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.execute("PRAGMA foreign_keys=ON")
    finally:
        connection.close()


def init_publication_schema(db_path: str) -> None:
    _apply_publication_migration(db_path)


def _workflow_projection(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _insert_review_workflow(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    review_id: str,
    revision: int,
    now: str,
) -> sqlite3.Row:
    workflow_id = review_workflow_id(run_id, review_id, revision)
    connection.execute(
        """
        INSERT INTO review_workflows_v2(
            workflow_id, run_id, review_id, review_revision,
            checkpoint_thread_id, status, post_review_segment_id,
            attempt_count, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'checkpoint_pending', ?, 0, ?, ?)
        """,
        (
            workflow_id,
            run_id,
            review_id,
            revision,
            checkpoint_thread_id(workflow_id),
            post_review_segment_id(run_id, review_id, revision),
            now,
            now,
        ),
    )
    return connection.execute(
        """
        SELECT * FROM review_workflows_v2
        WHERE workflow_id = ?
        """,
        (workflow_id,),
    ).fetchone()


def _insert_publication_artifacts(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    built: PublicationArtifacts,
    now: str,
) -> None:
    connection.executemany(
        """
        INSERT INTO run_artifacts_v2(
            artifact_id, run_id, kind, media_type,
            content, content_hash, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                artifact["artifact_id"],
                run_id,
                artifact["kind"],
                artifact["media_type"],
                artifact["content"],
                artifact["content_hash"],
                now,
            )
            for artifact in built.artifacts
        ],
    )


def finalize_verification_publication(
    *,
    db_path: str,
    run_id: str,
    expected_state_version: int,
) -> PublicationFinalization:
    from api.evidence_verification_repository import (
        finalize_verification_snapshot_in_transaction,
    )

    connection = _connect_for_migration(db_path)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        if not publication_schema_exists(connection):
            raise PublicationConflict("verification_schema_not_ready")
        connection.execute("BEGIN IMMEDIATE")
        try:
            run = connection.execute(
                """
                SELECT state_version, execution_status
                FROM research_runs_v2
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if run is None:
                raise PublicationConflict("publication_run_not_found")
            if run["state_version"] != expected_state_version:
                raise PublicationConflict("stale_state_version")
            if run["execution_status"] not in {
                "completed",
                "completed_with_fallback",
            }:
                raise PublicationConflict(
                    "verification_publication_conflict"
                )

            adopt_baseline_publication(
                connection,
                run_id=run_id,
            )
            snapshot_acceptance = (
                finalize_verification_snapshot_in_transaction(
                    connection,
                    run_id=run_id,
                )
            )
            current = connection.execute(
                """
                SELECT * FROM run_publications_v2
                WHERE run_id = ? AND is_current = 1
                """,
                (run_id,),
            ).fetchone()
            if (
                current is not None
                and current["verification_snapshot_id"]
                == snapshot_acceptance.snapshot.snapshot_id
            ):
                workflow = connection.execute(
                    """
                    SELECT * FROM review_workflows_v2
                    WHERE run_id = ? AND review_id = ?
                    """,
                    (run_id, current["review_id"]),
                ).fetchone()
                repaired = False
                if (
                    current["status"] == "review_required"
                    and workflow is None
                ):
                    now = _now()
                    workflow = _insert_review_workflow(
                        connection,
                        run_id=run_id,
                        review_id=current["review_id"],
                        revision=current["revision"],
                        now=now,
                    )
                    run_cursor = connection.execute(
                        """
                        UPDATE research_runs_v2
                        SET review_status = 'required',
                            delivery_status = 'review_required',
                            state_version = state_version + 1,
                            updated_at = ?
                        WHERE run_id = ? AND state_version = ?
                          AND execution_status IN (
                            'completed',
                            'completed_with_fallback'
                          )
                        """,
                        (now, run_id, expected_state_version),
                    )
                    if run_cursor.rowcount != 1:
                        raise PublicationConflict(
                            "verification_publication_conflict"
                        )
                    repaired = True
                connection.commit()
                return PublicationFinalization(
                    publication=_publication_record(current),
                    snapshot=snapshot_acceptance.snapshot,
                    workflow=_workflow_projection(workflow),
                    artifacts=(),
                    idempotent_replay=not repaired,
                )
            if current is not None:
                raise PublicationConflict(
                    "verification_publication_conflict"
                )

            previous = connection.execute(
                """
                SELECT * FROM run_publications_v2
                WHERE run_id = ?
                ORDER BY revision DESC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
            revision = 1 if previous is None else previous["revision"] + 1
            built = build_publication_artifacts(
                connection=connection,
                run_id=run_id,
                snapshot_id=snapshot_acceptance.snapshot.snapshot_id,
                revision=revision,
            )
            now = _now()
            _insert_publication_artifacts(
                connection,
                run_id=run_id,
                built=built,
                now=now,
            )
            connection.execute(
                """
                INSERT INTO review_bundles_v2(
                    review_id, run_id, revision,
                    status, bundle_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    built.review.review_id,
                    run_id,
                    revision,
                    built.review.status,
                    built.review.model_dump_json(),
                    now,
                ),
            )
            publication_id = publication_id_for(
                run_id=run_id,
                revision=revision,
                verification_snapshot_id=(
                    snapshot_acceptance.snapshot.snapshot_id
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
                ) VALUES (
                    ?, ?, ?, ?, ?, 'review_required', 1,
                    ?, ?, ?, ?, NULL, NULL
                )
                """,
                (
                    publication_id,
                    run_id,
                    revision,
                    snapshot_acceptance.snapshot.snapshot_id,
                    built.review.review_id,
                    json.dumps(
                        sorted(built.artifact_ids),
                        separators=(",", ":"),
                    ),
                    built.brief.content_hash,
                    (
                        previous["publication_id"]
                        if previous is not None
                        else None
                    ),
                    now,
                ),
            )
            workflow = _insert_review_workflow(
                connection,
                run_id=run_id,
                review_id=built.review.review_id,
                revision=revision,
                now=now,
            )
            run_cursor = connection.execute(
                """
                UPDATE research_runs_v2
                SET review_status = 'required',
                    delivery_status = 'review_required',
                    state_version = state_version + 1,
                    updated_at = ?
                WHERE run_id = ? AND state_version = ?
                  AND execution_status IN (
                    'completed',
                    'completed_with_fallback'
                  )
                """,
                (now, run_id, expected_state_version),
            )
            if run_cursor.rowcount != 1:
                raise PublicationConflict("stale_state_version")
            stored = connection.execute(
                """
                SELECT * FROM run_publications_v2
                WHERE publication_id = ?
                """,
                (publication_id,),
            ).fetchone()
            connection.commit()
            return PublicationFinalization(
                publication=_publication_record(stored),
                snapshot=snapshot_acceptance.snapshot,
                workflow=_workflow_projection(workflow),
                artifacts=built.artifacts,
                idempotent_replay=False,
            )
        except Exception:
            connection.rollback()
            raise
    except sqlite3.IntegrityError as exc:
        raise PublicationConflict(
            "verification_publication_conflict"
        ) from exc
    finally:
        connection.close()


def _unique_index_columns(
    connection: sqlite3.Connection,
    *,
    table: str,
) -> set[tuple[str, ...]]:
    result: set[tuple[str, ...]] = set()
    for index in connection.execute(f"PRAGMA index_list({table})"):
        if index["unique"] != 1:
            continue
        result.add(
            tuple(
                row["name"]
                for row in connection.execute(
                    f"PRAGMA index_info({index['name']})"
                )
            )
        )
    return result


def verify_publication_schema(*, db_path: str) -> dict[str, Any]:
    connection = _connect_for_migration(db_path)
    try:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        required_tables = {
            "review_bundles_v2",
            "review_workflows_v2",
            "review_resolutions_v2",
            "run_publications_v2",
        }
        missing_tables = sorted(required_tables - tables)
        invalid_columns = {
            table: {
                "expected": expected,
                "actual": _column_names(connection, table),
            }
            for table, expected in {
                "review_bundles_v2": _REVIEW_BUNDLE_COLUMNS,
                "review_workflows_v2": _REVIEW_WORKFLOW_COLUMNS,
                "review_resolutions_v2": _REVIEW_RESOLUTION_COLUMNS,
                "run_publications_v2": _PUBLICATION_COLUMNS,
            }.items()
            if table in tables and _column_names(connection, table) != expected
        }
        marker = connection.execute(
            """
            SELECT checksum FROM schema_migrations
            WHERE version = ?
            """,
            (PUBLICATION_MIGRATION_VERSION,),
        ).fetchone()
        invalid_marker = (
            marker is None
            or marker["checksum"] != PUBLICATION_MIGRATION_CHECKSUM
        )
        unique_indexes = {
            table: _unique_index_columns(connection, table=table)
            for table in required_tables
            if table in tables
        }
        invalid_unique_indexes = []
        for table, required in {
            "review_bundles_v2": ("run_id", "revision"),
            "review_workflows_v2": ("run_id", "review_revision"),
            "review_resolutions_v2": ("run_id", "review_id"),
            "run_publications_v2": ("run_id", "revision"),
        }.items():
            if table in unique_indexes and required not in unique_indexes[table]:
                invalid_unique_indexes.append(f"{table}:{required}")
        for table in (
            "review_bundles_v2",
            "review_workflows_v2",
            "review_resolutions_v2",
        ):
            if table in unique_indexes and ("run_id",) in unique_indexes[table]:
                invalid_unique_indexes.append(f"{table}:legacy_run_unique")
        publication_sql_row = connection.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type='table' AND name='run_publications_v2'
            """
        ).fetchone()
        publication_sql = publication_sql_row["sql"] if publication_sql_row else ""
        current_index = connection.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type='index' AND name='idx_run_publications_current'
            """
        ).fetchone()
        normalized_index = (
            "".join(current_index["sql"].lower().split())
            if current_index is not None and current_index["sql"]
            else ""
        )
        invalid_checks = not all(
            fragment in "".join(publication_sql.lower().split())
            for fragment in (
                "check(revision>=1)",
                "check(is_currentin(0,1))",
                "check(statusin('review_required','ready','blocked','stale'))",
            )
        )
        invalid_current_index = (
            "createuniqueindexidx_run_publications_current"
            "onrun_publications_v2(run_id)whereis_current=1"
            not in normalized_index
        )
        foreign_key_errors = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        if (
            missing_tables
            or invalid_columns
            or invalid_marker
            or invalid_unique_indexes
            or invalid_checks
            or invalid_current_index
            or foreign_key_errors
        ):
            raise RuntimeError(
                "publication_schema_verification_failed:"
                f"tables={missing_tables},columns={invalid_columns},"
                f"marker={invalid_marker},unique={invalid_unique_indexes},"
                f"checks={invalid_checks},current_index={invalid_current_index},"
                f"foreign_keys={foreign_key_errors}"
            )
        return {
            "migration_versions": [PUBLICATION_MIGRATION_VERSION],
            "tables": sorted(required_tables),
            "indexes": [
                "idx_run_publications_current",
                "idx_run_publications_review",
            ],
        }
    finally:
        connection.close()


def migrate_publication_with_backup(
    *,
    db_path: str,
    backup_path: str,
) -> dict[str, Any]:
    from api.run_migrations import backup_database, restore_database

    connection = _connect_for_migration(db_path)
    try:
        has_migration_table = connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'schema_migrations'
            """
        ).fetchone()
        marker = (
            connection.execute(
                """
                SELECT checksum FROM schema_migrations
                WHERE version = ?
                """,
                (PUBLICATION_MIGRATION_VERSION,),
            ).fetchone()
            if has_migration_table is not None
            else None
        )
    finally:
        connection.close()
    if marker is not None:
        if marker["checksum"] != PUBLICATION_MIGRATION_CHECKSUM:
            raise RuntimeError("publication_migration_checksum_mismatch")
        return verify_publication_schema(db_path=db_path)
    if Path(backup_path).exists():
        raise RuntimeError("publication_migration_backup_already_exists")

    backup_database(db_path=db_path, backup_path=backup_path)
    try:
        _apply_publication_migration(db_path)
        return verify_publication_schema(db_path=db_path)
    except Exception:
        restore_database(backup_path=backup_path, db_path=db_path)
        raise
