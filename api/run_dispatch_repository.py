"""Application-owned lease and start fencing for durable run dispatch."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
import sqlite3
from typing import Any, Literal

from pydantic import ValidationError

from api.run_dispatch_models import (
    MAX_RUN_DISPATCH_ATTEMPTS,
    RunDispatchClaim,
    RunDispatchConflict,
)
from api.run_repository import _connect, _now, init_run_schema


_WORKER_ID_PATTERN = re.compile(r"^dispatch_worker_[0-9a-f]{32}$")
_ERROR_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,127}$")


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("run_dispatch_lease_invalid")
    return value


def _candidate_row(
    connection: sqlite3.Connection,
    *,
    run_id: str | None,
    now_text: str,
) -> sqlite3.Row | None:
    params: list[Any] = [now_text]
    target = ""
    if run_id is not None:
        target = "AND run_id = ?"
        params.append(run_id)
    return connection.execute(
        f"""
        SELECT run_id
        FROM run_dispatches_v1
        WHERE (
            status = 'pending'
            OR (status = 'leased' AND lease_expires_at <= ?)
        )
        {target}
        ORDER BY created_at, run_id
        LIMIT 1
        """,
        params,
    ).fetchone()


def _joined_claim_row(
    connection: sqlite3.Connection,
    *,
    run_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT
            dispatch.run_id,
            dispatch.status AS dispatch_status,
            dispatch.lease_owner,
            dispatch.lease_expires_at,
            dispatch.attempt_count,
            run.thread_id,
            run.query,
            run.profile_id,
            run.profile_version,
            run.scope_json,
            run.execution_status,
            run.state_version,
            segment.segment_id,
            segment.status AS segment_status
        FROM run_dispatches_v1 AS dispatch
        JOIN research_runs_v2 AS run ON run.run_id = dispatch.run_id
        LEFT JOIN run_segments AS segment
          ON segment.run_id = run.run_id
         AND segment.sequence = 0
         AND segment.kind = 'initial'
        WHERE dispatch.run_id = ?
        """,
        (run_id,),
    ).fetchone()


def claim_run_dispatch(
    *,
    db_path: str | None,
    worker_id: str,
    lease_seconds: int,
    run_id: str | None = None,
    now: datetime | None = None,
) -> RunDispatchClaim | None:
    """Claim the oldest or targeted eligible dispatch under an immediate write lock."""
    if _WORKER_ID_PATTERN.fullmatch(worker_id) is None:
        raise ValueError("run_dispatch_worker_invalid")
    if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or lease_seconds <= 0:
        raise ValueError("run_dispatch_lease_invalid")
    claimed_at = _require_aware(now or datetime.now(timezone.utc))
    lease_expires_at = claimed_at + timedelta(seconds=lease_seconds)
    now_text = claimed_at.isoformat()
    lease_text = lease_expires_at.isoformat()

    init_run_schema(db_path)
    connection = _connect(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        candidate = _candidate_row(
            connection,
            run_id=run_id,
            now_text=now_text,
        )
        if candidate is None:
            connection.commit()
            return None
        joined = _joined_claim_row(connection, run_id=candidate["run_id"])
        if joined is None or joined["segment_id"] is None:
            raise RunDispatchConflict("run_dispatch_state_invalid")
        if (
            joined["execution_status"] != "pending"
            or joined["state_version"] != 0
            or joined["segment_status"] != "pending"
        ):
            connection.commit()
            return None

        cursor = connection.execute(
            """
            UPDATE run_dispatches_v1
            SET status = 'leased', lease_owner = ?, lease_expires_at = ?,
                attempt_count = attempt_count + 1, updated_at = ?
            WHERE run_id = ?
              AND (
                  status = 'pending'
                  OR (status = 'leased' AND lease_expires_at <= ?)
              )
            """,
            (worker_id, lease_text, now_text, candidate["run_id"], now_text),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            return None
        claimed = _joined_claim_row(connection, run_id=candidate["run_id"])
        if claimed is None or claimed["segment_id"] is None:
            raise RunDispatchConflict("run_dispatch_state_invalid")
        try:
            claim = RunDispatchClaim.model_validate(
                {
                    "run_id": claimed["run_id"],
                    "thread_id": claimed["thread_id"],
                    "segment_id": claimed["segment_id"],
                    "query": claimed["query"],
                    "profile_id": claimed["profile_id"],
                    "profile_version": claimed["profile_version"],
                    "scope_json": claimed["scope_json"],
                    "lease_owner": claimed["lease_owner"],
                    "attempt_count": claimed["attempt_count"],
                    "lease_expires_at": datetime.fromisoformat(
                        claimed["lease_expires_at"]
                    ),
                },
                strict=True,
            )
        except (ValidationError, ValueError, TypeError) as exc:
            raise RunDispatchConflict("run_dispatch_state_invalid") from exc
        connection.commit()
        return claim
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _claim_matches_joined(row: sqlite3.Row, claim: RunDispatchClaim) -> bool:
    return (
        row["dispatch_status"] == "leased"
        and row["lease_owner"] == claim.lease_owner
        and row["attempt_count"] == claim.attempt_count
        and row["thread_id"] == claim.thread_id
        and row["segment_id"] == claim.segment_id
        and row["query"] == claim.query
        and row["profile_id"] == claim.profile_id
        and row["profile_version"] == claim.profile_version
        and row["scope_json"] == claim.scope_json
        and row["execution_status"] == "pending"
        and row["state_version"] == 0
        and row["segment_status"] == "pending"
    )


def start_run_dispatch(
    *,
    db_path: str | None,
    claim: RunDispatchClaim,
) -> bool:
    """Atomically win the exact dispatch, run, and initial-segment start fence."""
    init_run_schema(db_path)
    connection = _connect(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = _joined_claim_row(connection, run_id=claim.run_id)
        if row is None or row["segment_id"] is None or not _claim_matches_joined(row, claim):
            connection.commit()
            return False
        now = _now()
        dispatch_cursor = connection.execute(
            """
            UPDATE run_dispatches_v1
            SET status = 'started', lease_owner = NULL, lease_expires_at = NULL,
                last_error_code = NULL, started_at = ?, updated_at = ?
            WHERE run_id = ? AND status = 'leased'
              AND lease_owner = ? AND attempt_count = ?
            """,
            (now, now, claim.run_id, claim.lease_owner, claim.attempt_count),
        )
        run_cursor = connection.execute(
            """
            UPDATE research_runs_v2
            SET execution_status = 'running', state_version = 1, updated_at = ?
            WHERE run_id = ? AND execution_status = 'pending' AND state_version = 0
            """,
            (now, claim.run_id),
        )
        segment_cursor = connection.execute(
            """
            UPDATE run_segments
            SET status = 'running', updated_at = ?
            WHERE segment_id = ? AND run_id = ? AND sequence = 0
              AND kind = 'initial' AND status = 'pending'
            """,
            (now, claim.segment_id, claim.run_id),
        )
        if (
            dispatch_cursor.rowcount != 1
            or run_cursor.rowcount != 1
            or segment_cursor.rowcount != 1
        ):
            connection.rollback()
            return False
        connection.commit()
        return True
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def release_run_dispatch_for_retry(
    *,
    db_path: str | None,
    claim: RunDispatchClaim,
    error_code: str,
) -> Literal["retry", "failed", "stale"]:
    """Release an exact lease or atomically terminalize its third failed attempt."""
    if _ERROR_CODE_PATTERN.fullmatch(error_code) is None:
        raise ValueError("run_dispatch_error_code_invalid")
    init_run_schema(db_path)
    connection = _connect(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = _joined_claim_row(connection, run_id=claim.run_id)
        if (
            row is None
            or row["segment_id"] is None
            or row["dispatch_status"] != "leased"
            or row["lease_owner"] != claim.lease_owner
            or row["attempt_count"] != claim.attempt_count
        ):
            connection.commit()
            return "stale"
        now = _now()
        if claim.attempt_count < MAX_RUN_DISPATCH_ATTEMPTS:
            cursor = connection.execute(
                """
                UPDATE run_dispatches_v1
                SET status = 'pending', lease_owner = NULL, lease_expires_at = NULL,
                    last_error_code = ?, updated_at = ?
                WHERE run_id = ? AND status = 'leased'
                  AND lease_owner = ? AND attempt_count = ?
                """,
                (error_code, now, claim.run_id, claim.lease_owner, claim.attempt_count),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return "stale"
            connection.commit()
            return "retry"

        if (
            row["execution_status"] != "pending"
            or row["state_version"] != 0
            or row["segment_status"] != "pending"
        ):
            connection.commit()
            return "stale"
        dispatch_cursor = connection.execute(
            """
            UPDATE run_dispatches_v1
            SET status = 'failed', lease_owner = NULL, lease_expires_at = NULL,
                last_error_code = ?, updated_at = ?, started_at = NULL
            WHERE run_id = ? AND status = 'leased'
              AND lease_owner = ? AND attempt_count = ?
            """,
            (error_code, now, claim.run_id, claim.lease_owner, claim.attempt_count),
        )
        run_cursor = connection.execute(
            """
            UPDATE research_runs_v2
            SET execution_status = 'failed', review_status = 'not_required',
                delivery_status = 'failed', state_version = 1, updated_at = ?
            WHERE run_id = ? AND execution_status = 'pending' AND state_version = 0
            """,
            (now, claim.run_id),
        )
        segment_cursor = connection.execute(
            """
            UPDATE run_segments
            SET status = 'failed', updated_at = ?
            WHERE segment_id = ? AND run_id = ? AND status = 'pending'
            """,
            (now, claim.segment_id, claim.run_id),
        )
        if (
            dispatch_cursor.rowcount != 1
            or run_cursor.rowcount != 1
            or segment_cursor.rowcount != 1
        ):
            connection.rollback()
            return "stale"
        connection.commit()
        return "failed"
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def dispatch_attempt_is_started(
    *,
    db_path: str | None,
    claim: RunDispatchClaim,
) -> bool:
    init_run_schema(db_path)
    connection = _connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT 1 FROM run_dispatches_v1
            WHERE run_id = ? AND status = 'started' AND attempt_count = ?
            """,
            (claim.run_id, claim.attempt_count),
        ).fetchone()
        return row is not None
    finally:
        connection.close()


def get_run_dispatch(
    *,
    db_path: str | None,
    run_id: str,
) -> dict[str, Any] | None:
    init_run_schema(db_path)
    connection = _connect(db_path)
    try:
        row = connection.execute(
            "SELECT * FROM run_dispatches_v1 WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        connection.close()
