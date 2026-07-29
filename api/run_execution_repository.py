"""Dormant transactions for boot activation and execution-owner fencing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3

from api.database import sqlite_db_path
from api.run_execution_migrations import verify_run_execution_recovery_connection
from api.run_execution_models import RunExecutionConflict, RunExecutionOwnerHandle


@dataclass(frozen=True)
class RunExecutionActivation:
    interrupted_execution_count: int
    interrupted_finalization_count: int


def _connect(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(sqlite_db_path(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_execution_boot_is_current(*, db_path: str, boot_id: str) -> bool:
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT boot_id FROM run_execution_boot_v1 WHERE boot_scope='application'"
        ).fetchone()
        return row is not None and row["boot_id"] == boot_id


def activate_run_execution_boot(
    *, db_path: str, boot_id: str
) -> RunExecutionActivation:
    connection = _connect(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        verify_run_execution_recovery_connection(connection)
        previous = connection.execute(
            "SELECT boot_id FROM run_execution_boot_v1 WHERE boot_scope='application'"
        ).fetchone()
        owners = connection.execute(
            "SELECT * FROM run_execution_owners_v1 WHERE status='active' ORDER BY run_id"
        ).fetchall()
        running = connection.execute(
            "SELECT run_id FROM research_runs_v2 WHERE execution_status='running' ORDER BY run_id"
        ).fetchall()
        if {row["run_id"] for row in owners} != {row["run_id"] for row in running}:
            raise RunExecutionConflict("run_execution_recovery_unavailable")
        if owners and (
            previous is None
            or any(row["boot_id"] != previous["boot_id"] for row in owners)
        ):
            raise RunExecutionConflict("run_execution_recovery_unavailable")
        timestamp = _now()
        execution_count = finalization_count = 0
        for owner in owners:
            phase = owner["phase"]
            code = (
                "execution_error"
                if phase == "execution"
                else "run_finalization_failed"
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
                (timestamp, owner["run_id"]),
            )
            segment = connection.execute(
                """
                UPDATE run_segments SET status='failed', updated_at=?
                WHERE segment_id=? AND run_id=? AND kind='initial'
                  AND sequence=0 AND status='running'
                """,
                (timestamp, owner["segment_id"], owner["run_id"]),
            )
            if updated.rowcount != 1 or segment.rowcount != 1:
                raise RunExecutionConflict("run_execution_recovery_unavailable")
            connection.execute(
                """
                INSERT INTO run_failure_causes_v1
                (run_id, observation_status, terminal_state_version, phase, code, recorded_at)
                VALUES (?, 'observed', 2, ?, ?, ?)
                """,
                (owner["run_id"], phase, code, timestamp),
            )
            closed = connection.execute(
                """
                UPDATE run_execution_owners_v1
                SET status='interrupted', boot_id=NULL, owner_id=NULL,
                    phase_updated_at=?, closed_at=?,
                    recovery_reason='previous_boot_interrupted'
                WHERE run_id=? AND status='active' AND boot_id=? AND owner_id=?
                """,
                (
                    timestamp,
                    timestamp,
                    owner["run_id"],
                    owner["boot_id"],
                    owner["owner_id"],
                ),
            )
            if closed.rowcount != 1:
                raise RunExecutionConflict("run_execution_recovery_unavailable")
            execution_count += phase == "execution"
            finalization_count += phase == "finalization"
        connection.execute(
            """
            INSERT INTO run_execution_boot_v1(boot_scope, boot_id, activated_at)
            VALUES ('application', ?, ?)
            ON CONFLICT(boot_scope)
            DO UPDATE SET boot_id=excluded.boot_id, activated_at=excluded.activated_at
            """,
            (boot_id, timestamp),
        )
        verify_run_execution_recovery_connection(connection)
        connection.commit()
        return RunExecutionActivation(
            interrupted_execution_count=execution_count,
            interrupted_finalization_count=finalization_count,
        )
    except Exception as exc:
        connection.rollback()
        if isinstance(exc, RunExecutionConflict):
            raise
        raise RunExecutionConflict("run_execution_recovery_unavailable") from exc
    finally:
        connection.close()


def advance_run_execution_phase(
    *, db_path: str, handle: RunExecutionOwnerHandle
) -> bool:
    with _connect(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        updated = connection.execute(
            """
            UPDATE run_execution_owners_v1
            SET phase='finalization', phase_updated_at=?
            WHERE run_id=? AND segment_id=? AND boot_id=? AND owner_id=?
              AND status='active' AND phase='execution'
              AND EXISTS (
                SELECT 1 FROM run_execution_boot_v1
                WHERE boot_scope='application' AND boot_id=?
              )
              AND EXISTS (
                SELECT 1 FROM research_runs_v2
                WHERE run_id=? AND execution_status='running' AND state_version=1
              )
            """,
            (
                _now(),
                handle.run_id,
                handle.segment_id,
                handle.boot_id,
                handle.owner_id,
                handle.boot_id,
                handle.run_id,
            ),
        )
        return updated.rowcount == 1


def run_execution_owner_fence_is_current(
    connection: sqlite3.Connection,
    handle: RunExecutionOwnerHandle,
    *,
    expected_phase: str,
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1 FROM run_execution_owners_v1 AS owner
            JOIN run_execution_boot_v1 AS boot
              ON boot.boot_scope='application' AND boot.boot_id=owner.boot_id
            JOIN research_runs_v2 AS run ON run.run_id=owner.run_id
            WHERE owner.run_id=? AND owner.segment_id=? AND owner.boot_id=?
              AND owner.owner_id=? AND owner.status='active' AND owner.phase=?
              AND run.execution_status='running' AND run.state_version=1
            """,
            (
                handle.run_id,
                handle.segment_id,
                handle.boot_id,
                handle.owner_id,
                expected_phase,
            ),
        ).fetchone()
        is not None
    )


def close_run_execution_owner(
    connection: sqlite3.Connection,
    handle: RunExecutionOwnerHandle,
    *,
    expected_phase: str,
    closed_at: str,
) -> bool:
    if not run_execution_owner_fence_is_current(
        connection, handle, expected_phase=expected_phase
    ):
        return False
    updated = connection.execute(
        """
        UPDATE run_execution_owners_v1
        SET status='closed', boot_id=NULL, owner_id=NULL,
            phase_updated_at=?, closed_at=?, recovery_reason=NULL
        WHERE run_id=? AND segment_id=? AND boot_id=? AND owner_id=?
          AND status='active' AND phase=?
        """,
        (
            closed_at,
            closed_at,
            handle.run_id,
            handle.segment_id,
            handle.boot_id,
            handle.owner_id,
            expected_phase,
        ),
    )
    return updated.rowcount == 1
