"""Dormant, backup-protected migration for run execution recovery."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from threading import Lock

from api.database import backup_database, restore_database, sqlite_db_path
from api.run_execution_models import (
    RUN_EXECUTION_RECOVERY_MIGRATION_CHECKSUM,
    RUN_EXECUTION_RECOVERY_MIGRATION_VERSION,
    RunExecutionConflict,
)


_MIGRATION_LOCK = Lock()
_OWNER_INDEX = "idx_run_execution_owners_status_boot_created"

BOOT_TABLE_SQL = """
CREATE TABLE run_execution_boot_v1 (
    boot_scope TEXT PRIMARY KEY
        CHECK(boot_scope = 'application'),
    boot_id TEXT NOT NULL
        CHECK(length(boot_id) > 0),
    activated_at TEXT NOT NULL
)
"""
OWNER_TABLE_SQL = """
CREATE TABLE run_execution_owners_v1 (
    run_id TEXT PRIMARY KEY
        REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
    segment_id TEXT NOT NULL UNIQUE
        REFERENCES run_segments(segment_id) ON DELETE CASCADE,
    status TEXT NOT NULL
        CHECK(status IN ('active', 'closed', 'interrupted')),
    phase TEXT NOT NULL
        CHECK(phase IN ('execution', 'finalization')),
    boot_id TEXT,
    owner_id TEXT,
    created_at TEXT NOT NULL,
    phase_updated_at TEXT NOT NULL,
    closed_at TEXT,
    recovery_reason TEXT,
    CHECK(
        (
            status = 'active'
            AND boot_id IS NOT NULL
            AND length(boot_id) > 0
            AND owner_id IS NOT NULL
            AND length(owner_id) > 0
            AND closed_at IS NULL
            AND recovery_reason IS NULL
        )
        OR
        (
            status = 'closed'
            AND boot_id IS NULL
            AND owner_id IS NULL
            AND closed_at IS NOT NULL
            AND recovery_reason IS NULL
        )
        OR
        (
            status = 'interrupted'
            AND boot_id IS NULL
            AND owner_id IS NULL
            AND closed_at IS NOT NULL
            AND recovery_reason IN (
                'previous_boot_interrupted',
                'pre_v1_running_without_owner'
            )
        )
    )
)
"""
OWNER_INDEX_SQL = f"""
CREATE INDEX {_OWNER_INDEX}
ON run_execution_owners_v1(status, boot_id, created_at)
"""
LINEAGE_TABLE_SQL = """
CREATE TABLE run_recovery_retries_v1 (
    key_hash TEXT PRIMARY KEY,
    request_schema_version TEXT NOT NULL
        CHECK(request_schema_version = 'dra.run-recovery-request.v1'),
    request_hash TEXT NOT NULL,
    source_run_id TEXT NOT NULL UNIQUE
        REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
    replacement_run_id TEXT NOT NULL UNIQUE
        REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
    recovery_reason TEXT NOT NULL
        CHECK(recovery_reason IN (
            'previous_boot_interrupted',
            'pre_v1_running_without_owner'
        )),
    interrupted_phase TEXT NOT NULL
        CHECK(interrupted_phase IN ('execution', 'finalization')),
    recovery_attempt INTEGER NOT NULL
        CHECK(recovery_attempt = 1),
    created_at TEXT NOT NULL,
    CHECK(source_run_id != replacement_run_id)
)
"""


def _connect(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(sqlite_db_path(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded(exc: BaseException) -> RunExecutionConflict:
    if isinstance(exc, RunExecutionConflict):
        return exc
    return RunExecutionConflict("run_execution_recovery_unavailable")


def run_execution_recovery_marker_present(*, db_path: str) -> bool:
    try:
        connection = _connect(db_path)
        try:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
            if table is None:
                return False
            rows = connection.execute(
                "SELECT checksum FROM schema_migrations WHERE version=?",
                (RUN_EXECUTION_RECOVERY_MIGRATION_VERSION,),
            ).fetchall()
            if not rows:
                return False
            if len(rows) != 1 or rows[0]["checksum"] != RUN_EXECUTION_RECOVERY_MIGRATION_CHECKSUM:
                raise RunExecutionConflict("run_execution_recovery_unavailable")
            return True
        finally:
            connection.close()
    except (sqlite3.Error, OSError) as exc:
        raise _bounded(exc) from exc


def verify_run_execution_recovery_connection(
    connection: sqlite3.Connection,
) -> dict[str, int]:
    connection.row_factory = sqlite3.Row
    marker = connection.execute(
        "SELECT checksum FROM schema_migrations WHERE version=?",
        (RUN_EXECUTION_RECOVERY_MIGRATION_VERSION,),
    ).fetchall()
    if len(marker) != 1 or marker[0]["checksum"] != RUN_EXECUTION_RECOVERY_MIGRATION_CHECKSUM:
        raise RunExecutionConflict("run_execution_recovery_unavailable")
    required = {
        "run_execution_boot_v1",
        "run_execution_owners_v1",
        "run_recovery_retries_v1",
    }
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if not required.issubset(tables):
        raise RunExecutionConflict("run_execution_recovery_unavailable")
    index = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (_OWNER_INDEX,)
    ).fetchone()
    if index is None or "run_execution_owners_v1" not in (index["sql"] or ""):
        raise RunExecutionConflict("run_execution_recovery_unavailable")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise RunExecutionConflict("run_execution_recovery_unavailable")
    boot_rows = connection.execute(
        "SELECT COUNT(*) AS count FROM run_execution_boot_v1"
    ).fetchone()["count"]
    if boot_rows not in (0, 1):
        raise RunExecutionConflict("run_execution_recovery_unavailable")
    ownerless = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM research_runs_v2 AS run
        LEFT JOIN run_execution_owners_v1 AS owner ON owner.run_id=run.run_id
        WHERE run.execution_status='running'
          AND (owner.run_id IS NULL OR owner.status!='active')
        """
    ).fetchone()["count"]
    active_nonrunning = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM run_execution_owners_v1 AS owner
        JOIN research_runs_v2 AS run ON run.run_id=owner.run_id
        WHERE owner.status='active'
          AND (run.execution_status!='running' OR run.state_version!=1)
        """
    ).fetchone()["count"]
    if ownerless or active_nonrunning:
        raise RunExecutionConflict("run_execution_recovery_unavailable")
    return {
        "boot_rows": boot_rows,
        "owner_rows": connection.execute(
            "SELECT COUNT(*) AS count FROM run_execution_owners_v1"
        ).fetchone()["count"],
        "lineage_rows": connection.execute(
            "SELECT COUNT(*) AS count FROM run_recovery_retries_v1"
        ).fetchone()["count"],
    }


def verify_run_execution_recovery_schema(*, db_path: str) -> dict[str, int]:
    try:
        connection = _connect(db_path)
        try:
            return verify_run_execution_recovery_connection(connection)
        finally:
            connection.close()
    except (sqlite3.Error, OSError) as exc:
        raise _bounded(exc) from exc


def _validate_running_source(
    connection: sqlite3.Connection, run: sqlite3.Row
) -> sqlite3.Row:
    if (
        run["review_status"] != "not_required"
        or run["delivery_status"] != "pending"
        or run["state_version"] != 1
    ):
        raise RunExecutionConflict("run_execution_recovery_unavailable")
    segments = connection.execute(
        """
        SELECT * FROM run_segments
        WHERE run_id=? AND kind='initial' AND sequence=0 AND attempt=1
        """,
        (run["run_id"],),
    ).fetchall()
    if len(segments) != 1 or segments[0]["status"] != "running":
        raise RunExecutionConflict("run_execution_recovery_unavailable")
    if connection.execute(
        "SELECT 1 FROM run_failure_causes_v1 WHERE run_id=?", (run["run_id"],)
    ).fetchone():
        raise RunExecutionConflict("run_execution_recovery_unavailable")
    return segments[0]


def _apply(connection: sqlite3.Connection) -> None:
    connection.execute(BOOT_TABLE_SQL)
    connection.execute(OWNER_TABLE_SQL)
    connection.execute(LINEAGE_TABLE_SQL)
    connection.execute(OWNER_INDEX_SQL)
    observed_at = _now()
    running = connection.execute(
        "SELECT * FROM research_runs_v2 WHERE execution_status='running'"
    ).fetchall()
    for run in running:
        segment = _validate_running_source(connection, run)
        connection.execute(
            """
            INSERT INTO run_execution_owners_v1 (
                run_id, segment_id, status, phase, boot_id, owner_id,
                created_at, phase_updated_at, closed_at, recovery_reason
            ) VALUES (?, ?, 'interrupted', 'execution', NULL, NULL, ?, ?, ?,
                      'pre_v1_running_without_owner')
            """,
            (run["run_id"], segment["segment_id"], observed_at, observed_at, observed_at),
        )
        updated = connection.execute(
            """
            UPDATE research_runs_v2
            SET execution_status='failed', review_status='not_required',
                delivery_status='failed', state_version=2, updated_at=?
            WHERE run_id=? AND execution_status='running'
              AND review_status='not_required' AND delivery_status='pending'
              AND state_version=1
            """,
            (observed_at, run["run_id"]),
        )
        segment_updated = connection.execute(
            "UPDATE run_segments SET status='failed', updated_at=? WHERE segment_id=? AND status='running'",
            (observed_at, segment["segment_id"]),
        )
        if updated.rowcount != 1 or segment_updated.rowcount != 1:
            raise RunExecutionConflict("run_execution_recovery_unavailable")
        connection.execute(
            """
            INSERT INTO run_failure_causes_v1 (
                run_id, observation_status, terminal_state_version,
                phase, code, recorded_at
            ) VALUES (?, 'observed', 2, 'execution', 'execution_error', ?)
            """,
            (run["run_id"], observed_at),
        )
    connection.execute(
        "INSERT INTO schema_migrations(version, applied_at, checksum) VALUES (?, ?, ?)",
        (
            RUN_EXECUTION_RECOVERY_MIGRATION_VERSION,
            observed_at,
            RUN_EXECUTION_RECOVERY_MIGRATION_CHECKSUM,
        ),
    )
    verify_run_execution_recovery_connection(connection)


def migrate_run_execution_recovery_with_backup(*, db_path: str) -> dict[str, int]:
    with _MIGRATION_LOCK:
        if run_execution_recovery_marker_present(db_path=db_path):
            return verify_run_execution_recovery_schema(db_path=db_path)
        canonical = sqlite_db_path(db_path)
        backup_path = Path(f"{canonical}.pre-run-execution-recovery.bak")
        if backup_path.exists():
            raise RunExecutionConflict(
                "run_execution_recovery_backup_already_exists"
            )
        backup_database(db_path=canonical, backup_path=str(backup_path))
        connection: sqlite3.Connection | None = None
        try:
            connection = _connect(canonical)
            connection.execute("BEGIN IMMEDIATE")
            _apply(connection)
            connection.commit()
            connection.close()
            connection = None
            return verify_run_execution_recovery_schema(db_path=canonical)
        except Exception as exc:
            if connection is not None:
                connection.rollback()
                connection.close()
            restore_database(backup_path=str(backup_path), db_path=canonical)
            raise _bounded(exc) from exc
