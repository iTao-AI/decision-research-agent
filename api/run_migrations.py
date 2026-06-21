"""Operational safeguards for the additive run identity migration."""
from __future__ import annotations

from pathlib import Path
import sqlite3

from api.persistence import _get_db_path
from api.review_repository import (
    REVIEW_MIGRATION_CHECKSUM,
    REVIEW_MIGRATION_VERSION,
    init_review_schema,
)
from api.run_repository import MIGRATION_VERSION


REQUIRED_TABLES = {
    "schema_migrations",
    "research_runs_v2",
    "run_segments",
    "evidence_entries_v2",
    "review_bundles_v2",
    "review_decisions_v2",
    "review_workflows_v2",
    "review_resume_attempts_v2",
    "review_resolutions_v2",
}
REQUIRED_INDEXES = {
    "idx_research_runs_v2_thread",
    "idx_review_workflows_status_lease",
    "idx_review_decisions_run",
}
EXPECTED_MIGRATIONS = {
    MIGRATION_VERSION: "run-identity-backbone-v1",
    REVIEW_MIGRATION_VERSION: REVIEW_MIGRATION_CHECKSUM,
}
REQUIRED_COLUMNS = {
    "research_runs_v2": {
        "run_id",
        "thread_id",
        "query",
        "profile_id",
        "profile_version",
        "scope_json",
        "execution_status",
        "review_status",
        "delivery_status",
        "state_version",
        "created_at",
        "updated_at",
    },
    "review_bundles_v2": {
        "review_id",
        "run_id",
        "revision",
        "status",
        "bundle_json",
        "created_at",
    },
    "review_decisions_v2": {
        "decision_id",
        "run_id",
        "review_id",
        "review_revision",
        "action",
        "reason",
        "actor_fingerprint",
        "request_hash",
        "accepted_state_version",
        "created_at",
    },
    "review_workflows_v2": {
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
    },
    "review_resume_attempts_v2": {
        "workflow_id",
        "attempt",
        "worker_id",
        "started_at",
        "completed_at",
        "outcome",
        "error_code",
    },
    "review_resolutions_v2": {
        "resolution_id",
        "run_id",
        "review_id",
        "decision_id",
        "action",
        "resolved_review_json",
        "artifact_ids_json",
        "created_at",
    },
}


def backup_database(*, db_path: str, backup_path: str) -> None:
    """Create a transactionally consistent SQLite backup."""
    Path(backup_path).parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(_get_db_path(db_path))
    destination = sqlite3.connect(backup_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def restore_database(*, backup_path: str, db_path: str) -> None:
    """Restore a SQLite backup without copying WAL sidecar files."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(backup_path)
    destination = sqlite3.connect(_get_db_path(db_path))
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def verify_run_schema(*, db_path: str) -> dict:
    """Fail closed unless the run identity schema is complete and consistent."""
    conn = sqlite3.connect(_get_db_path(db_path))
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        missing_tables = sorted(REQUIRED_TABLES - tables)
        missing_indexes = sorted(REQUIRED_INDEXES - indexes)
        missing_columns = {
            table: sorted(
                required
                - {
                    row[1]
                    for row in conn.execute(f"PRAGMA table_info({table})")
                }
            )
            for table, required in REQUIRED_COLUMNS.items()
            if table in tables
        }
        missing_columns = {
            table: columns
            for table, columns in missing_columns.items()
            if columns
        }
        migration_rows = (
            conn.execute(
                "SELECT version, checksum FROM schema_migrations"
            ).fetchall()
            if "schema_migrations" in tables
            else []
        )
        migrations = {row[0]: row[1] for row in migration_rows}
        invalid_migrations = sorted(
            version
            for version, checksum in EXPECTED_MIGRATIONS.items()
            if migrations.get(version) != checksum
        )
        try:
            foreign_key_errors = conn.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        except sqlite3.DatabaseError:
            foreign_key_errors = [("schema_mismatch",)]
        if (
            missing_tables
            or missing_indexes
            or missing_columns
            or invalid_migrations
            or foreign_key_errors
        ):
            raise RuntimeError(
                "run_schema_verification_failed:"
                f"tables={missing_tables},indexes={missing_indexes},"
                f"columns={missing_columns},"
                f"migrations={invalid_migrations},"
                f"foreign_keys={foreign_key_errors}"
            )
        return {
            "migration_version": MIGRATION_VERSION,
            "migration_versions": sorted(EXPECTED_MIGRATIONS),
            "tables": sorted(REQUIRED_TABLES),
            "indexes": sorted(REQUIRED_INDEXES),
            "columns": {
                table: sorted(columns)
                for table, columns in REQUIRED_COLUMNS.items()
            },
        }
    finally:
        conn.close()


def migrate_with_backup(*, db_path: str, backup_path: str) -> dict:
    """Back up, apply, and verify; restore the original DB on any failure."""
    backup_database(db_path=db_path, backup_path=backup_path)
    try:
        init_review_schema(db_path)
        return verify_run_schema(db_path=db_path)
    except Exception:
        restore_database(backup_path=backup_path, db_path=db_path)
        raise
