"""Operational safeguards for the additive run identity migration."""
from __future__ import annotations

from pathlib import Path
import re
import sqlite3

from api.database import sqlite_db_path
from api.evidence_verification_repository import (
    VERIFICATION_MIGRATION_CHECKSUM,
    VERIFICATION_MIGRATION_VERSION,
)
from api.review_repository import (
    REVIEW_MIGRATION_CHECKSUM,
    REVIEW_MIGRATION_VERSION,
)
from api.publication_repository import (
    PUBLICATION_MIGRATION_CHECKSUM,
    PUBLICATION_MIGRATION_VERSION,
    migrate_publication_with_backup,
    verify_publication_schema,
)
from api.run_repository import MIGRATION_VERSION
from api.run_repository import init_run_schema
from api.run_creation_models import (
    RUN_CREATE_IDEMPOTENCY_MIGRATION_CHECKSUM,
    RUN_CREATE_IDEMPOTENCY_MIGRATION_VERSION,
)
from api.run_dispatch_models import (
    RUN_DISPATCH_MIGRATION_CHECKSUM,
    RUN_DISPATCH_MIGRATION_VERSION,
)


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
    "run_create_idempotency_v1",
    "run_dispatches_v1",
}
REQUIRED_INDEXES = {
    "idx_research_runs_v2_thread",
    "idx_review_workflows_status_lease",
    "idx_review_decisions_run",
    "idx_run_dispatches_status_lease_created",
}
EXPECTED_MIGRATIONS = {
    MIGRATION_VERSION: "run-identity-backbone-v1",
    REVIEW_MIGRATION_VERSION: REVIEW_MIGRATION_CHECKSUM,
    RUN_CREATE_IDEMPOTENCY_MIGRATION_VERSION: RUN_CREATE_IDEMPOTENCY_MIGRATION_CHECKSUM,
    RUN_DISPATCH_MIGRATION_VERSION: RUN_DISPATCH_MIGRATION_CHECKSUM,
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
    "run_create_idempotency_v1": {
        "key_hash",
        "request_schema_version",
        "request_hash",
        "run_id",
        "created_at",
    },
    "run_dispatches_v1": {
        "run_id",
        "status",
        "lease_owner",
        "lease_expires_at",
        "attempt_count",
        "last_error_code",
        "created_at",
        "updated_at",
        "started_at",
    },
}
VERIFICATION_TABLES = {
    "evidence_verification_preflights_v2",
    "evidence_verification_decisions_v2",
    "evidence_verification_snapshots_v2",
}
VERIFICATION_INDEXES = {
    "idx_evidence_preflights_evidence",
    "idx_evidence_decisions_current",
}
VERIFICATION_COLUMNS = {
    "evidence_entries_v2": {"baseline_verification_origin"},
    "evidence_verification_preflights_v2": {
        "preflight_id",
        "run_id",
        "evidence_id",
        "evidence_fingerprint",
        "preflight_version",
        "status",
        "checks_json",
        "preflight_hash",
        "created_at",
    },
    "evidence_verification_decisions_v2": {
        "verification_id",
        "run_id",
        "evidence_id",
        "evidence_fingerprint",
        "revision",
        "action",
        "reason_code",
        "reason_note",
        "preflight_id",
        "actor_fingerprint",
        "request_hash",
        "created_at",
    },
    "evidence_verification_snapshots_v2": {
        "snapshot_id",
        "run_id",
        "revision",
        "snapshot_json",
        "snapshot_hash",
        "created_at",
    },
}


def backup_database(*, db_path: str, backup_path: str) -> None:
    """Create a transactionally consistent SQLite backup."""
    Path(backup_path).parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(sqlite_db_path(db_path))
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
    destination = sqlite3.connect(sqlite_db_path(db_path))
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def _normalized_schema_sql(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def verify_run_schema(
    *,
    db_path: str,
    include_evidence_verification: bool = False,
    include_publication: bool = False,
) -> dict:
    """Fail closed unless the run identity schema is complete and consistent."""
    required_tables = set(REQUIRED_TABLES)
    required_indexes = set(REQUIRED_INDEXES)
    required_columns = {
        table: set(columns)
        for table, columns in REQUIRED_COLUMNS.items()
    }
    expected_migrations = dict(EXPECTED_MIGRATIONS)
    if include_evidence_verification:
        required_tables.update(VERIFICATION_TABLES)
        required_indexes.update(VERIFICATION_INDEXES)
        for table, columns in VERIFICATION_COLUMNS.items():
            required_columns.setdefault(table, set()).update(columns)
        expected_migrations[VERIFICATION_MIGRATION_VERSION] = (
            VERIFICATION_MIGRATION_CHECKSUM
        )
    if include_publication:
        required_tables.add("run_publications_v2")
        required_indexes.update(
            {
                "idx_run_publications_current",
                "idx_run_publications_review",
            }
        )
        required_columns["run_publications_v2"] = {
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
        }
        expected_migrations[PUBLICATION_MIGRATION_VERSION] = (
            PUBLICATION_MIGRATION_CHECKSUM
        )
    conn = sqlite3.connect(sqlite_db_path(db_path))
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
        missing_tables = sorted(required_tables - tables)
        missing_indexes = sorted(required_indexes - indexes)
        missing_columns = {
            table: sorted(
                required
                - {
                    row[1]
                    for row in conn.execute(f"PRAGMA table_info({table})")
                }
            )
            for table, required in required_columns.items()
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
            for version, checksum in expected_migrations.items()
            if migrations.get(version) != checksum
        )
        try:
            foreign_key_errors = conn.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        except sqlite3.DatabaseError:
            foreign_key_errors = [("schema_mismatch",)]
        declared_foreign_keys = (
            conn.execute(
                "PRAGMA foreign_key_list(run_create_idempotency_v1)"
            ).fetchall()
            if "run_create_idempotency_v1" in tables
            else []
        )
        required_idempotency_fk = any(
            row[2] == "research_runs_v2"
            and row[3] == "run_id"
            and row[4] == "run_id"
            and row[6].upper() == "CASCADE"
            for row in declared_foreign_keys
        )
        missing_foreign_keys = (
            [] if required_idempotency_fk else ["run_create_idempotency_v1.run_id"]
        )
        missing_constraints = []
        if "run_create_idempotency_v1" in tables:
            idempotency_columns = conn.execute(
                "PRAGMA table_info(run_create_idempotency_v1)"
            ).fetchall()
            primary_key_columns = [
                row[1]
                for row in sorted(idempotency_columns, key=lambda row: row[5])
                if row[5] > 0
            ]
            if primary_key_columns != ["key_hash"]:
                missing_constraints.append("key_hash_primary_key")
            run_id_unique = False
            for index_row in conn.execute(
                "PRAGMA index_list(run_create_idempotency_v1)"
            ).fetchall():
                if index_row[2] != 1 or index_row[4] != 0:
                    continue
                escaped_name = str(index_row[1]).replace('"', '""')
                index_columns = [
                    row[2]
                    for row in conn.execute(
                        f'PRAGMA index_info("{escaped_name}")'
                    ).fetchall()
                ]
                if index_columns == ["run_id"]:
                    run_id_unique = True
                    break
            if not run_id_unique:
                missing_constraints.append("run_id_unique")
        if "run_dispatches_v1" in tables:
            dispatch_columns = conn.execute(
                "PRAGMA table_info(run_dispatches_v1)"
            ).fetchall()
            dispatch_primary_key = [
                row[1]
                for row in sorted(dispatch_columns, key=lambda row: row[5])
                if row[5] > 0
            ]
            if dispatch_primary_key != ["run_id"]:
                missing_constraints.append("dispatch_run_id_primary_key")

            dispatch_foreign_keys = conn.execute(
                "PRAGMA foreign_key_list(run_dispatches_v1)"
            ).fetchall()
            if not any(
                row[2] == "research_runs_v2"
                and row[3] == "run_id"
                and row[4] == "run_id"
                and row[6].upper() == "CASCADE"
                for row in dispatch_foreign_keys
            ):
                missing_constraints.append("dispatch_run_id_foreign_key")

            dispatch_sql_row = conn.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'table' AND name = 'run_dispatches_v1'"
            ).fetchone()
            dispatch_sql = _normalized_schema_sql(
                dispatch_sql_row[0] if dispatch_sql_row else None
            )
            if (
                "check(status in ('pending', 'leased', 'started', 'failed'))"
                not in dispatch_sql
            ):
                missing_constraints.append("dispatch_status_check")
            if "check(attempt_count >= 0)" not in dispatch_sql:
                missing_constraints.append("dispatch_attempt_check")
            required_state_fragments = (
                "status = 'leased' and lease_owner is not null and lease_expires_at is not null",
                "status != 'leased' and lease_owner is null and lease_expires_at is null",
                "status = 'started' and started_at is not null and last_error_code is null",
                "status = 'failed' and started_at is null and last_error_code is not null",
                "status in ('pending', 'leased') and started_at is null",
            )
            if not all(
                fragment in dispatch_sql
                for fragment in required_state_fragments
            ):
                missing_constraints.append("dispatch_state_check")

            exact_dispatch_index = False
            for index_row in conn.execute(
                "PRAGMA index_list(run_dispatches_v1)"
            ).fetchall():
                if index_row[1] != "idx_run_dispatches_status_lease_created":
                    continue
                if index_row[2] != 0 or index_row[4] != 0:
                    continue
                escaped_name = str(index_row[1]).replace('"', '""')
                index_columns = [
                    row[2]
                    for row in conn.execute(
                        f'PRAGMA index_info("{escaped_name}")'
                    ).fetchall()
                ]
                if index_columns == ["status", "lease_expires_at", "created_at"]:
                    exact_dispatch_index = True
                    break
            if not exact_dispatch_index:
                missing_constraints.append("dispatch_scan_index")
        if (
            missing_tables
            or missing_indexes
            or missing_columns
            or invalid_migrations
            or foreign_key_errors
            or missing_foreign_keys
            or missing_constraints
        ):
            raise RuntimeError(
                "run_schema_verification_failed:"
                f"tables={missing_tables},indexes={missing_indexes},"
                f"columns={missing_columns},"
                f"migrations={invalid_migrations},"
                f"foreign_keys={foreign_key_errors}"
                f",missing_foreign_keys={missing_foreign_keys}"
                f",missing_constraints={missing_constraints}"
            )
        if include_publication:
            verify_publication_schema(db_path=db_path)
        return {
            "migration_version": MIGRATION_VERSION,
            "migration_versions": sorted(expected_migrations),
            "tables": sorted(required_tables),
            "indexes": sorted(required_indexes),
            "columns": {
                table: sorted(columns)
                for table, columns in required_columns.items()
            },
        }
    finally:
        conn.close()


def _migration_markers(db_path: str) -> dict[str, str]:
    connection = sqlite3.connect(sqlite_db_path(db_path))
    try:
        has_migration_table = connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'schema_migrations'
            """
        ).fetchone()
        if has_migration_table is None:
            return {}
        markers = dict(
            connection.execute(
                "SELECT version, checksum FROM schema_migrations"
            ).fetchall()
        )
    finally:
        connection.close()
    known = {
        PUBLICATION_MIGRATION_VERSION: PUBLICATION_MIGRATION_CHECKSUM,
        RUN_CREATE_IDEMPOTENCY_MIGRATION_VERSION: RUN_CREATE_IDEMPOTENCY_MIGRATION_CHECKSUM,
        RUN_DISPATCH_MIGRATION_VERSION: RUN_DISPATCH_MIGRATION_CHECKSUM,
    }
    invalid = [
        version
        for version, checksum in known.items()
        if version in markers and markers[version] != checksum
    ]
    if invalid:
        raise RuntimeError(f"run_schema_migration_checksum_invalid:{sorted(invalid)}")
    return markers


def migrate_with_backup(*, db_path: str, backup_path: str) -> dict:
    """Back up, apply, and verify; restore the original DB on any failure."""
    backup_existed = Path(backup_path).exists()
    markers = _migration_markers(db_path)
    publication_applied = (
        markers.get(PUBLICATION_MIGRATION_VERSION)
        == PUBLICATION_MIGRATION_CHECKSUM
    )
    idempotency_applied = (
        markers.get(RUN_CREATE_IDEMPOTENCY_MIGRATION_VERSION)
        == RUN_CREATE_IDEMPOTENCY_MIGRATION_CHECKSUM
    )
    dispatch_applied = (
        markers.get(RUN_DISPATCH_MIGRATION_VERSION)
        == RUN_DISPATCH_MIGRATION_CHECKSUM
    )

    if not publication_applied:
        migrate_publication_with_backup(
            db_path=db_path,
            backup_path=backup_path,
        )
    elif not idempotency_applied:
        if Path(backup_path).exists():
            raise RuntimeError("run_idempotency_migration_backup_already_exists")
        backup_database(db_path=db_path, backup_path=backup_path)
        try:
            init_run_schema(db_path)
            verify_run_schema(
                db_path=db_path,
                include_evidence_verification=True,
                include_publication=True,
            )
        except Exception:
            restore_database(backup_path=backup_path, db_path=db_path)
            raise
    elif not dispatch_applied:
        if Path(backup_path).exists():
            raise RuntimeError("run_dispatch_migration_backup_already_exists")
        backup_database(db_path=db_path, backup_path=backup_path)
        try:
            init_run_schema(db_path)
            verify_run_schema(
                db_path=db_path,
                include_evidence_verification=True,
                include_publication=True,
            )
        except Exception:
            restore_database(backup_path=backup_path, db_path=db_path)
            raise

    try:
        return verify_run_schema(
            db_path=db_path,
            include_evidence_verification=True,
            include_publication=True,
        )
    except Exception:
        if (
            not publication_applied
            and not backup_existed
            and Path(backup_path).exists()
        ):
            restore_database(backup_path=backup_path, db_path=db_path)
        raise
