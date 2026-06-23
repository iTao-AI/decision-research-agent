from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from typing import Any

from agent.talent_contracts import DecisionBrief
from api.decision_brief import with_content_hash
from api.review_artifacts import ReviewedArtifactResult
from api.review_models import (
    ReviewDecisionRecord,
    ReviewDecisionRequest,
    decision_request_hash,
    encode_review_cursor,
    review_resolution_id,
)
from api.run_repository import _connect, _now, init_run_schema


REVIEW_MIGRATION_VERSION = "004_durable_review_feasibility"
REVIEW_MIGRATION_CHECKSUM = "durable-review-feasibility-v1"


@dataclass(frozen=True)
class DecisionAcceptance:
    decision: ReviewDecisionRecord
    workflow_status: str
    idempotent_replay: bool


@dataclass(frozen=True)
class ReviewResolution:
    resolution_id: str
    run_id: str
    review_id: str
    decision_id: str
    action: str
    artifact_ids: tuple[str, ...]
    created_at: str


@dataclass(frozen=True)
class ReviewWorkflowClaim:
    workflow_id: str
    run_id: str
    review_id: str
    review_revision: int
    checkpoint_thread_id: str
    decision_id: str | None
    post_review_segment_id: str
    original_status: str
    attempt: int


@dataclass(frozen=True)
class ReconcilableWorkflow:
    workflow_id: str
    checkpoint_thread_id: str
    status: str
    decision_id: str | None
    lease_expires_at: str | None

    def lease_expired(self, now: datetime) -> bool:
        if self.lease_expires_at is None:
            return True
        try:
            expires_at = datetime.fromisoformat(self.lease_expires_at)
        except ValueError:
            return True
        if expires_at.tzinfo is None:
            return True
        return expires_at <= now


class ReviewConflict(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def init_review_schema(db_path: str | None = None) -> None:
    """Apply the additive durable review schema idempotently."""
    init_run_schema(db_path)
    connection = _connect(db_path)
    try:
        with connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS review_decisions_v2 (
                    decision_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL
                        REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
                    review_id TEXT NOT NULL
                        REFERENCES review_bundles_v2(review_id) ON DELETE CASCADE,
                    review_revision INTEGER NOT NULL,
                    action TEXT NOT NULL CHECK(action IN ('approve', 'reject')),
                    reason TEXT,
                    actor_fingerprint TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    accepted_state_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(review_id, review_revision)
                );

                CREATE TABLE IF NOT EXISTS review_workflows_v2 (
                    workflow_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE
                        REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
                    review_id TEXT NOT NULL
                        REFERENCES review_bundles_v2(review_id) ON DELETE CASCADE,
                    review_revision INTEGER NOT NULL,
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
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS review_resume_attempts_v2 (
                    workflow_id TEXT NOT NULL
                        REFERENCES review_workflows_v2(workflow_id)
                        ON DELETE CASCADE,
                    attempt INTEGER NOT NULL,
                    worker_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    outcome TEXT,
                    error_code TEXT,
                    PRIMARY KEY(workflow_id, attempt)
                );

                CREATE TABLE IF NOT EXISTS review_resolutions_v2 (
                    resolution_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE
                        REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
                    review_id TEXT NOT NULL
                        REFERENCES review_bundles_v2(review_id) ON DELETE CASCADE,
                    decision_id TEXT NOT NULL UNIQUE
                        REFERENCES review_decisions_v2(decision_id),
                    action TEXT NOT NULL CHECK(action IN ('approve', 'reject')),
                    resolved_review_json TEXT NOT NULL,
                    artifact_ids_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_review_workflows_status_lease
                ON review_workflows_v2(status, lease_expires_at, updated_at);

                CREATE INDEX IF NOT EXISTS idx_review_decisions_run
                ON review_decisions_v2(run_id, created_at);
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, applied_at, checksum)
                VALUES (?, ?, ?)
                """,
                (
                    REVIEW_MIGRATION_VERSION,
                    _now(),
                    REVIEW_MIGRATION_CHECKSUM,
                ),
            )
    finally:
        connection.close()


def _decision_record(row: sqlite3.Row) -> ReviewDecisionRecord:
    return ReviewDecisionRecord.model_validate(dict(row))


def _decision_acceptance(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    idempotent_replay: bool,
) -> DecisionAcceptance:
    workflow = connection.execute(
        """
        SELECT status FROM review_workflows_v2
        WHERE run_id = ? AND review_id = ? AND review_revision = ?
        """,
        (row["run_id"], row["review_id"], row["review_revision"]),
    ).fetchone()
    if workflow is None:
        raise ReviewConflict("review_not_found")
    return DecisionAcceptance(
        decision=_decision_record(row),
        workflow_status=workflow["status"],
        idempotent_replay=idempotent_replay,
    )


def _table_exists(
    connection: sqlite3.Connection,
    table_name: str,
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        is not None
    )


def _publication_for_review(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    review_id: str,
) -> sqlite3.Row | None:
    if not _table_exists(connection, "run_publications_v2"):
        return None
    return connection.execute(
        """
        SELECT *
        FROM run_publications_v2
        WHERE run_id = ? AND review_id = ?
        """,
        (run_id, review_id),
    ).fetchone()


def _require_active_publication_review(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    review_id: str,
) -> None:
    publication = _publication_for_review(
        connection,
        run_id=run_id,
        review_id=review_id,
    )
    if publication is None:
        return
    if not publication["is_current"] or publication["status"] == "stale":
        raise ReviewConflict("review_superseded")
    if publication["status"] != "review_required":
        raise ReviewConflict("review_not_waiting")


def accept_review_decision(
    *,
    run_id: str,
    review_id: str,
    request: ReviewDecisionRequest,
    actor_fingerprint: str,
    db_path: str | None = None,
) -> DecisionAcceptance:
    """Atomically accept one immutable review decision with fenced idempotency."""
    init_review_schema(db_path)
    request_hash = decision_request_hash(
        run_id=run_id,
        review_id=review_id,
        request=request,
    )
    connection = _connect(db_path)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM review_decisions_v2 WHERE decision_id = ?",
                (request.decision_id,),
            ).fetchone()
            if existing is not None:
                if existing["request_hash"] != request_hash:
                    raise ReviewConflict("decision_id_conflict")
                return _decision_acceptance(
                    connection,
                    existing,
                    idempotent_replay=True,
                )

            prior_review_decision = connection.execute(
                """
                SELECT decision_id FROM review_decisions_v2
                WHERE review_id = ? AND review_revision = ?
                """,
                (review_id, request.review_revision),
            ).fetchone()
            if prior_review_decision is not None:
                raise ReviewConflict("review_already_decided")

            run = connection.execute(
                """
                SELECT execution_status, review_status, delivery_status,
                       state_version, profile_id
                FROM research_runs_v2 WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            workflow = connection.execute(
                """
                SELECT * FROM review_workflows_v2
                WHERE run_id = ? AND review_id = ? AND review_revision = ?
                """,
                (run_id, review_id, request.review_revision),
            ).fetchone()
            if run is None or workflow is None:
                raise ReviewConflict("review_not_found")
            if workflow["status"] == "superseded":
                raise ReviewConflict("review_superseded")
            _require_active_publication_review(
                connection,
                run_id=run_id,
                review_id=review_id,
            )
            if run["profile_id"] != "talent-hiring-signal":
                raise ReviewConflict("unsupported_review_profile")
            if (
                run["execution_status"] != "completed"
                or run["review_status"] != "required"
                or run["delivery_status"] != "review_required"
                or workflow["status"] != "waiting_decision"
            ):
                raise ReviewConflict("review_not_waiting")
            if run["state_version"] != request.expected_state_version:
                raise ReviewConflict("stale_state_version")

            accepted_version = run["state_version"] + 1
            now = _now()
            connection.execute(
                """
                INSERT INTO review_decisions_v2 (
                    decision_id, run_id, review_id, review_revision, action,
                    reason, actor_fingerprint, request_hash,
                    accepted_state_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.decision_id,
                    run_id,
                    review_id,
                    request.review_revision,
                    request.action,
                    request.reason,
                    actor_fingerprint,
                    request_hash,
                    accepted_version,
                    now,
                ),
            )
            workflow_cursor = connection.execute(
                """
                UPDATE review_workflows_v2
                SET decision_id = ?, status = 'resume_pending', updated_at = ?
                WHERE workflow_id = ? AND status = 'waiting_decision'
                """,
                (request.decision_id, now, workflow["workflow_id"]),
            )
            if workflow_cursor.rowcount != 1:
                raise ReviewConflict("review_not_waiting")
            run_cursor = connection.execute(
                """
                UPDATE research_runs_v2
                SET state_version = state_version + 1, updated_at = ?
                WHERE run_id = ? AND state_version = ?
                """,
                (now, run_id, request.expected_state_version),
            )
            if run_cursor.rowcount != 1:
                raise ReviewConflict("stale_state_version")
            row = connection.execute(
                "SELECT * FROM review_decisions_v2 WHERE decision_id = ?",
                (request.decision_id,),
            ).fetchone()
            return _decision_acceptance(
                connection,
                row,
                idempotent_replay=False,
            )
    except sqlite3.IntegrityError as exc:
        message = str(exc)
        if (
            "review_decisions_v2.review_id, "
            "review_decisions_v2.review_revision"
        ) in message:
            raise ReviewConflict("review_already_decided") from exc
        if "review_decisions_v2.decision_id" in message:
            raise ReviewConflict("decision_id_conflict") from exc
        raise ReviewConflict("review_persistence_conflict") from exc
    finally:
        connection.close()


def _workflow_projection(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "workflow_id": row["workflow_id"],
        "run_id": row["run_id"],
        "review_id": row["review_id"],
        "review_revision": row["review_revision"],
        "status": row["status"],
        "decision_id": row["decision_id"],
        "post_review_segment_id": row["post_review_segment_id"],
        "attempt_count": row["attempt_count"],
        "last_error_code": row["last_error_code"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _decision_projection(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "decision_id": row["decision_id"],
        "run_id": row["run_id"],
        "review_id": row["review_id"],
        "review_revision": row["review_revision"],
        "action": row["action"],
        "reason_recorded": row["reason"] is not None,
        "accepted_state_version": row["accepted_state_version"],
        "created_at": row["created_at"],
    }


def _decision_detail_projection(
    row: sqlite3.Row | None,
) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "decision_id": row["decision_id"],
        "run_id": row["run_id"],
        "review_id": row["review_id"],
        "review_revision": row["review_revision"],
        "action": row["action"],
        "reason": row["reason"],
        "accepted_state_version": row["accepted_state_version"],
        "created_at": row["created_at"],
    }


def _resolution_projection(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "resolution_id": row["resolution_id"],
        "run_id": row["run_id"],
        "review_id": row["review_id"],
        "decision_id": row["decision_id"],
        "action": row["action"],
        "artifact_ids": json.loads(row["artifact_ids_json"]),
        "created_at": row["created_at"],
    }


def list_review_workflows(
    *,
    status: str,
    limit: int,
    cursor: tuple[str, str] | None,
    db_path: str | None = None,
) -> dict[str, Any]:
    init_review_schema(db_path)
    connection = _connect(db_path)
    try:
        params: list[Any] = [status]
        cursor_sql = ""
        if cursor is not None:
            created_at, workflow_id = cursor
            cursor_sql = """
              AND (
                workflow.created_at < ?
                OR (
                  workflow.created_at = ?
                  AND workflow.workflow_id < ?
                )
              )
            """
            params.extend([created_at, created_at, workflow_id])
        params.append(limit + 1)
        rows = connection.execute(
            f"""
            SELECT
              workflow.workflow_id,
              workflow.run_id,
              workflow.review_id,
              workflow.review_revision,
              workflow.status AS workflow_status,
              workflow.last_error_code,
              workflow.created_at,
              workflow.updated_at,
              run.profile_id,
              run.review_status,
              run.delivery_status,
              run.state_version
            FROM review_workflows_v2 AS workflow
            JOIN research_runs_v2 AS run ON run.run_id = workflow.run_id
            WHERE workflow.status = ?
            {cursor_sql}
            ORDER BY workflow.created_at DESC, workflow.workflow_id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        page = rows[:limit]
        next_cursor = None
        if len(rows) > limit:
            last = page[-1]
            next_cursor = encode_review_cursor(
                created_at=last["created_at"],
                workflow_id=last["workflow_id"],
            )
        return {
            "reviews": [dict(row) for row in page],
            "next_cursor": next_cursor,
        }
    finally:
        connection.close()


def get_review_detail(
    *,
    run_id: str,
    review_id: str,
    db_path: str | None = None,
) -> dict[str, Any] | None:
    init_review_schema(db_path)
    connection = _connect(db_path)
    try:
        connection.execute("BEGIN")
        row = connection.execute(
            """
            SELECT
              workflow.*,
              run.profile_id,
              run.review_status,
              run.delivery_status,
              run.state_version,
              bundle.bundle_json
            FROM review_workflows_v2 AS workflow
            JOIN research_runs_v2 AS run ON run.run_id = workflow.run_id
            JOIN review_bundles_v2 AS bundle
              ON bundle.review_id = workflow.review_id
            WHERE workflow.run_id = ? AND workflow.review_id = ?
            """,
            (run_id, review_id),
        ).fetchone()
        if row is None:
            return None
        decision = connection.execute(
            "SELECT * FROM review_decisions_v2 WHERE review_id = ?",
            (review_id,),
        ).fetchone()
        resolution = connection.execute(
            "SELECT * FROM review_resolutions_v2 WHERE review_id = ?",
            (review_id,),
        ).fetchone()
        return {
            "run_id": run_id,
            "review_id": review_id,
            "review_revision": row["review_revision"],
            "profile_id": row["profile_id"],
            "state_version": row["state_version"],
            "review_status": row["review_status"],
            "delivery_status": row["delivery_status"],
            "workflow": _workflow_projection(row),
            "review_bundle": json.loads(row["bundle_json"]),
            "decision": _decision_detail_projection(decision),
            "resolution": _resolution_projection(resolution),
        }
    finally:
        connection.close()


def get_review_projection(
    *,
    run_id: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Return bounded review state without audit-only or checkpoint internals."""
    init_review_schema(db_path)
    connection = _connect(db_path)
    try:
        review_id = None
        has_publications = False
        if _table_exists(connection, "run_publications_v2"):
            has_publications = (
                connection.execute(
                    """
                    SELECT 1 FROM run_publications_v2
                    WHERE run_id = ? LIMIT 1
                    """,
                    (run_id,),
                ).fetchone()
                is not None
            )
            publication = connection.execute(
                """
                SELECT review_id FROM run_publications_v2
                WHERE run_id = ? AND is_current = 1
                """,
                (run_id,),
            ).fetchone()
            review_id = publication["review_id"] if publication else None
        if review_id is not None:
            workflow = connection.execute(
                """
                SELECT * FROM review_workflows_v2
                WHERE run_id = ? AND review_id = ?
                """,
                (run_id, review_id),
            ).fetchone()
            decision = connection.execute(
                """
                SELECT * FROM review_decisions_v2
                WHERE review_id = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (review_id,),
            ).fetchone()
            resolution = connection.execute(
                """
                SELECT * FROM review_resolutions_v2
                WHERE review_id = ?
                """,
                (review_id,),
            ).fetchone()
        elif has_publications:
            workflow = None
            decision = None
            resolution = None
        else:
            workflow = connection.execute(
                "SELECT * FROM review_workflows_v2 WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            decision = connection.execute(
                """
                SELECT * FROM review_decisions_v2
                WHERE run_id = ? ORDER BY created_at DESC LIMIT 1
                """,
                (run_id,),
            ).fetchone()
            resolution = connection.execute(
                "SELECT * FROM review_resolutions_v2 WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return {
            "workflow": _workflow_projection(workflow),
            "decision": _decision_projection(decision),
            "resolution": _resolution_projection(resolution),
        }
    finally:
        connection.close()


def _claim_time(now: datetime | None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("review workflow time must be timezone-aware")
    return value.astimezone(timezone.utc)


def claim_review_workflow(
    *,
    worker_id: str,
    lease_seconds: int,
    db_path: str | None = None,
    now: datetime | None = None,
) -> ReviewWorkflowClaim | None:
    """Claim one due workflow without changing ResearchRun state_version."""
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    init_review_schema(db_path)
    claimed_at = _claim_time(now)
    claimed_at_text = claimed_at.isoformat()
    lease_expires_at = (
        claimed_at + timedelta(seconds=lease_seconds)
    ).isoformat()
    connection = _connect(db_path)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            workflow = connection.execute(
                """
                SELECT *
                FROM review_workflows_v2
                WHERE status IN (
                    'checkpoint_pending',
                    'resume_pending',
                    'resuming',
                    'resolution_pending'
                )
                  AND (
                    lease_owner IS NULL
                    OR lease_expires_at IS NULL
                    OR lease_expires_at <= ?
                  )
                ORDER BY created_at, workflow_id
                LIMIT 1
                """,
                (claimed_at_text,),
            ).fetchone()
            if workflow is None:
                return None

            original_status = workflow["status"]
            claimed_status = (
                "resuming"
                if original_status in {"resume_pending", "resuming"}
                else original_status
            )
            attempt = workflow["attempt_count"] + 1
            cursor = connection.execute(
                """
                UPDATE review_workflows_v2
                SET status = ?, lease_owner = ?, lease_expires_at = ?,
                    attempt_count = ?, updated_at = ?
                WHERE workflow_id = ?
                  AND status = ?
                  AND lease_owner IS ?
                  AND lease_expires_at IS ?
                """,
                (
                    claimed_status,
                    worker_id,
                    lease_expires_at,
                    attempt,
                    claimed_at_text,
                    workflow["workflow_id"],
                    original_status,
                    workflow["lease_owner"],
                    workflow["lease_expires_at"],
                ),
            )
            if cursor.rowcount != 1:
                return None
            connection.execute(
                """
                INSERT OR IGNORE INTO run_segments (
                    segment_id, run_id, kind, sequence, attempt, status,
                    created_at, updated_at
                ) VALUES (?, ?, 'post_review', ?, 1, 'pending', ?, ?)
                """,
                (
                    workflow["post_review_segment_id"],
                    workflow["run_id"],
                    workflow["review_revision"],
                    claimed_at_text,
                    claimed_at_text,
                ),
            )
            segment = connection.execute(
                """
                SELECT segment_id FROM run_segments
                WHERE run_id = ? AND sequence = ?
                """,
                (workflow["run_id"], workflow["review_revision"]),
            ).fetchone()
            if (
                segment is None
                or segment["segment_id"] != workflow["post_review_segment_id"]
            ):
                raise ReviewConflict("post_review_segment_conflict")
            connection.execute(
                """
                INSERT INTO review_resume_attempts_v2 (
                    workflow_id, attempt, worker_id, started_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    workflow["workflow_id"],
                    attempt,
                    worker_id,
                    claimed_at_text,
                ),
            )
            return ReviewWorkflowClaim(
                workflow_id=workflow["workflow_id"],
                run_id=workflow["run_id"],
                review_id=workflow["review_id"],
                review_revision=workflow["review_revision"],
                checkpoint_thread_id=workflow["checkpoint_thread_id"],
                decision_id=workflow["decision_id"],
                post_review_segment_id=workflow["post_review_segment_id"],
                original_status=original_status,
                attempt=attempt,
            )
    finally:
        connection.close()


def _owned_workflow(
    connection: sqlite3.Connection,
    *,
    workflow_id: str,
    worker_id: str,
) -> sqlite3.Row:
    workflow = connection.execute(
        "SELECT * FROM review_workflows_v2 WHERE workflow_id = ?",
        (workflow_id,),
    ).fetchone()
    if workflow is None:
        raise ReviewConflict("review_not_found")
    if (
        workflow["lease_owner"] != worker_id
        or not _lease_is_active(workflow["lease_expires_at"])
    ):
        raise ReviewConflict("lease_not_owned")
    return workflow


def _complete_attempt(
    connection: sqlite3.Connection,
    *,
    workflow: sqlite3.Row,
    worker_id: str,
    now: str,
    outcome: str,
    error_code: str | None = None,
) -> None:
    cursor = connection.execute(
        """
        UPDATE review_resume_attempts_v2
        SET completed_at = ?, outcome = ?, error_code = ?
        WHERE workflow_id = ? AND attempt = ? AND worker_id = ?
          AND completed_at IS NULL
        """,
        (
            now,
            outcome,
            error_code,
            workflow["workflow_id"],
            workflow["attempt_count"],
            worker_id,
        ),
    )
    if cursor.rowcount != 1:
        raise ReviewConflict("resume_attempt_not_found")


def complete_checkpoint_creation(
    *,
    workflow_id: str,
    worker_id: str,
    db_path: str | None = None,
) -> None:
    init_review_schema(db_path)
    connection = _connect(db_path)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            workflow = _owned_workflow(
                connection,
                workflow_id=workflow_id,
                worker_id=worker_id,
            )
            if workflow["status"] != "checkpoint_pending":
                raise ReviewConflict("checkpoint_not_pending")
            now = _now()
            cursor = connection.execute(
                """
                UPDATE review_workflows_v2
                SET status = 'waiting_decision', lease_owner = NULL,
                    lease_expires_at = NULL, last_error_code = NULL,
                    updated_at = ?
                WHERE workflow_id = ? AND status = 'checkpoint_pending'
                  AND lease_owner = ?
                """,
                (now, workflow_id, worker_id),
            )
            if cursor.rowcount != 1:
                raise ReviewConflict("lease_not_owned")
            _complete_attempt(
                connection,
                workflow=workflow,
                worker_id=worker_id,
                now=now,
                outcome="checkpoint_created",
            )
    finally:
        connection.close()


def list_reconcilable_workflows(
    *,
    db_path: str | None = None,
    now: datetime | None = None,
) -> list[ReconcilableWorkflow]:
    init_review_schema(db_path)
    current = _claim_time(now)
    connection = _connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT workflow_id, checkpoint_thread_id, status, decision_id,
                   lease_expires_at
            FROM review_workflows_v2
            WHERE status = 'checkpoint_pending'
               OR (
                    status = 'resuming'
                    AND (
                        lease_expires_at IS NULL
                        OR lease_expires_at <= ?
                    )
               )
            ORDER BY created_at, workflow_id
            """,
            (current.isoformat(),),
        ).fetchall()
        return [ReconcilableWorkflow(**dict(row)) for row in rows]
    finally:
        connection.close()


def _complete_attempt_if_open(
    connection: sqlite3.Connection,
    *,
    workflow: sqlite3.Row,
    now: str,
    outcome: str,
    error_code: str | None = None,
) -> None:
    connection.execute(
        """
        UPDATE review_resume_attempts_v2
        SET completed_at = ?, outcome = ?, error_code = ?
        WHERE workflow_id = ? AND attempt = ? AND completed_at IS NULL
        """,
        (
            now,
            outcome,
            error_code,
            workflow["workflow_id"],
            workflow["attempt_count"],
        ),
    )


def mark_waiting_decision(
    *,
    workflow_id: str,
    db_path: str | None = None,
) -> None:
    init_review_schema(db_path)
    connection = _connect(db_path)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            workflow = connection.execute(
                "SELECT * FROM review_workflows_v2 WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if workflow is None:
                raise ReviewConflict("review_not_found")
            if workflow["status"] != "checkpoint_pending":
                return
            now = _now()
            connection.execute(
                """
                UPDATE review_workflows_v2
                SET status = 'waiting_decision', lease_owner = NULL,
                    lease_expires_at = NULL, last_error_code = NULL,
                    updated_at = ?
                WHERE workflow_id = ? AND status = 'checkpoint_pending'
                """,
                (now, workflow_id),
            )
            _complete_attempt_if_open(
                connection,
                workflow=workflow,
                now=now,
                outcome="checkpoint_reconciled",
            )
    finally:
        connection.close()


def get_decision(
    *,
    decision_id: str,
    db_path: str | None = None,
) -> ReviewDecisionRecord | None:
    init_review_schema(db_path)
    connection = _connect(db_path)
    try:
        row = connection.execute(
            "SELECT * FROM review_decisions_v2 WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        return _decision_record(row) if row is not None else None
    finally:
        connection.close()


def get_original_decision_brief(
    *,
    run_id: str,
    review_id: str | None = None,
    db_path: str | None = None,
) -> str:
    init_review_schema(db_path)
    connection = _connect(db_path)
    try:
        row = None
        publication_rows_exist = False
        publication_table_exists = _table_exists(
            connection,
            "run_publications_v2",
        )
        if publication_table_exists:
            publication_rows_exist = (
                connection.execute(
                    """
                    SELECT 1 FROM run_publications_v2
                    WHERE run_id = ? LIMIT 1
                    """,
                    (run_id,),
                ).fetchone()
                is not None
            )
        if review_id is not None and publication_table_exists:
            publication = connection.execute(
                """
                SELECT artifact_ids_json
                FROM run_publications_v2
                WHERE run_id = ? AND review_id = ?
                """,
                (run_id, review_id),
            ).fetchone()
            if publication is not None:
                artifact_ids = json.loads(publication["artifact_ids_json"])
                placeholders = ", ".join("?" for _ in artifact_ids)
                if artifact_ids:
                    row = connection.execute(
                        f"""
                        SELECT content FROM run_artifacts_v2
                        WHERE run_id = ?
                          AND artifact_id IN ({placeholders})
                          AND kind = 'decision_brief_json'
                        ORDER BY artifact_id
                        LIMIT 1
                        """,
                        (run_id, *artifact_ids),
                    ).fetchone()
        if row is None and (
            review_id is None or not publication_rows_exist
        ):
            row = connection.execute(
                """
                SELECT content FROM run_artifacts_v2
                WHERE run_id = ? AND artifact_id = 'decision-brief.json'
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            raise ReviewConflict("decision_brief_not_found")
        return row["content"]
    finally:
        connection.close()


def mark_resolution_pending(
    *,
    workflow_id: str,
    worker_id: str | None,
    decision_id: str,
    db_path: str | None = None,
) -> None:
    init_review_schema(db_path)
    connection = _connect(db_path)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            workflow = connection.execute(
                "SELECT * FROM review_workflows_v2 WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if workflow is None:
                raise ReviewConflict("review_not_found")
            if worker_id is not None:
                workflow = _owned_workflow(
                    connection,
                    workflow_id=workflow_id,
                    worker_id=worker_id,
                )
            if (
                workflow["status"] != "resuming"
                or workflow["decision_id"] != decision_id
            ):
                raise ReviewConflict("checkpoint_decision_mismatch")
            now = _now()
            if worker_id is None:
                cursor = connection.execute(
                    """
                    UPDATE review_workflows_v2
                    SET status = 'resolution_pending', lease_owner = NULL,
                        lease_expires_at = NULL, updated_at = ?
                    WHERE workflow_id = ? AND status = 'resuming'
                      AND decision_id = ?
                    """,
                    (now, workflow_id, decision_id),
                )
                _complete_attempt_if_open(
                    connection,
                    workflow=workflow,
                    now=now,
                    outcome="checkpoint_reconciled",
                )
            else:
                cursor = connection.execute(
                    """
                    UPDATE review_workflows_v2
                    SET status = 'resolution_pending', updated_at = ?
                    WHERE workflow_id = ? AND status = 'resuming'
                      AND lease_owner = ? AND decision_id = ?
                    """,
                    (now, workflow_id, worker_id, decision_id),
                )
            if cursor.rowcount != 1:
                raise ReviewConflict("lease_not_owned")
    finally:
        connection.close()


def mark_manual_recovery(
    *,
    workflow_id: str,
    worker_id: str | None,
    error_code: str,
    db_path: str | None = None,
) -> None:
    init_review_schema(db_path)
    connection = _connect(db_path)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            workflow = connection.execute(
                "SELECT * FROM review_workflows_v2 WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if workflow is None:
                raise ReviewConflict("review_not_found")
            if workflow["status"] == "superseded":
                raise ReviewConflict("review_superseded")
            if worker_id is not None:
                workflow = _owned_workflow(
                    connection,
                    workflow_id=workflow_id,
                    worker_id=worker_id,
                )
            now = _now()
            if worker_id is None:
                cursor = connection.execute(
                    """
                    UPDATE review_workflows_v2
                    SET status = 'manual_recovery', lease_owner = NULL,
                        lease_expires_at = NULL, last_error_code = ?,
                        updated_at = ?
                    WHERE workflow_id = ?
                      AND status NOT IN (
                        'approved',
                        'rejected',
                        'manual_recovery',
                        'superseded'
                      )
                    """,
                    (error_code, now, workflow_id),
                )
            else:
                cursor = connection.execute(
                    """
                    UPDATE review_workflows_v2
                    SET status = 'manual_recovery', lease_owner = NULL,
                        lease_expires_at = NULL, last_error_code = ?,
                        updated_at = ?
                    WHERE workflow_id = ? AND lease_owner = ?
                    """,
                    (error_code, now, workflow_id, worker_id),
                )
            if cursor.rowcount != 1:
                raise ReviewConflict("lease_not_owned")
            if worker_id is None:
                _complete_attempt_if_open(
                    connection,
                    workflow=workflow,
                    now=now,
                    outcome="manual_recovery",
                    error_code=error_code,
                )
            else:
                _complete_attempt(
                    connection,
                    workflow=workflow,
                    worker_id=worker_id,
                    now=now,
                    outcome="manual_recovery",
                    error_code=error_code,
                )
    finally:
        connection.close()


def release_expired_lease(
    *,
    workflow_id: str,
    db_path: str | None = None,
) -> None:
    init_review_schema(db_path)
    connection = _connect(db_path)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            workflow = connection.execute(
                "SELECT * FROM review_workflows_v2 WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if workflow is None:
                raise ReviewConflict("review_not_found")
            now_value = datetime.now(timezone.utc)
            if (
                workflow["status"] != "resuming"
                or not ReconcilableWorkflow(
                    workflow_id=workflow["workflow_id"],
                    checkpoint_thread_id=workflow["checkpoint_thread_id"],
                    status=workflow["status"],
                    decision_id=workflow["decision_id"],
                    lease_expires_at=workflow["lease_expires_at"],
                ).lease_expired(now_value)
            ):
                raise ReviewConflict("lease_not_expired")
            now = now_value.isoformat()
            connection.execute(
                """
                UPDATE review_workflows_v2
                SET status = 'resume_pending', lease_owner = NULL,
                    lease_expires_at = NULL, updated_at = ?
                WHERE workflow_id = ? AND status = 'resuming'
                """,
                (now, workflow_id),
            )
            _complete_attempt_if_open(
                connection,
                workflow=workflow,
                now=now,
                outcome="lease_expired",
            )
    finally:
        connection.close()


def release_workflow_for_retry(
    *,
    workflow_id: str,
    worker_id: str,
    error_code: str,
    max_attempts: int,
    db_path: str | None = None,
) -> None:
    init_review_schema(db_path)
    connection = _connect(db_path)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            workflow = _owned_workflow(
                connection,
                workflow_id=workflow_id,
                worker_id=worker_id,
            )
            now = _now()
            if workflow["attempt_count"] >= max_attempts:
                next_status = "manual_recovery"
                outcome = "manual_recovery"
            elif workflow["status"] == "resuming":
                next_status = "resume_pending"
                outcome = "retry"
            elif workflow["status"] in {
                "checkpoint_pending",
                "resolution_pending",
            }:
                next_status = workflow["status"]
                outcome = "retry"
            else:
                raise ReviewConflict("review_not_retryable")
            cursor = connection.execute(
                """
                UPDATE review_workflows_v2
                SET status = ?, lease_owner = NULL, lease_expires_at = NULL,
                    last_error_code = ?, updated_at = ?
                WHERE workflow_id = ? AND lease_owner = ?
                """,
                (
                    next_status,
                    error_code,
                    now,
                    workflow_id,
                    worker_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ReviewConflict("lease_not_owned")
            _complete_attempt(
                connection,
                workflow=workflow,
                worker_id=worker_id,
                now=now,
                outcome=outcome,
                error_code=error_code,
            )
    finally:
        connection.close()


def _resolution_record(row: sqlite3.Row) -> ReviewResolution:
    return ReviewResolution(
        resolution_id=row["resolution_id"],
        run_id=row["run_id"],
        review_id=row["review_id"],
        decision_id=row["decision_id"],
        action=row["action"],
        artifact_ids=tuple(json.loads(row["artifact_ids_json"])),
        created_at=row["created_at"],
    )


def _lease_is_active(value: str | None) -> bool:
    if value is None:
        return False
    try:
        expires_at = datetime.fromisoformat(value)
    except ValueError:
        return False
    if expires_at.tzinfo is None:
        return False
    return expires_at > datetime.now(timezone.utc)


def resolve_review(
    *,
    workflow_id: str,
    worker_id: str,
    expected_run_state_version: int,
    result: ReviewedArtifactResult,
    db_path: str | None = None,
) -> ReviewResolution:
    """Persist one reviewed outcome exactly once under an active worker lease."""
    init_review_schema(db_path)
    connection = _connect(db_path)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            workflow = connection.execute(
                "SELECT * FROM review_workflows_v2 WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if workflow is None:
                raise ReviewConflict("review_not_found")
            if workflow["status"] == "superseded":
                raise ReviewConflict("review_superseded")
            _require_active_publication_review(
                connection,
                run_id=workflow["run_id"],
                review_id=workflow["review_id"],
            )

            existing = connection.execute(
                "SELECT * FROM review_resolutions_v2 WHERE review_id = ?",
                (workflow["review_id"],),
            ).fetchone()
            if existing is not None:
                return _resolution_record(existing)

            if (
                workflow["status"] != "resolution_pending"
                or workflow["lease_owner"] != worker_id
                or not _lease_is_active(workflow["lease_expires_at"])
            ):
                raise ReviewConflict("lease_not_owned")
            if workflow["decision_id"] is None:
                raise ReviewConflict("review_decision_missing")

            decision = connection.execute(
                "SELECT * FROM review_decisions_v2 WHERE decision_id = ?",
                (workflow["decision_id"],),
            ).fetchone()
            run = connection.execute(
                "SELECT state_version FROM research_runs_v2 WHERE run_id = ?",
                (workflow["run_id"],),
            ).fetchone()
            if decision is None or run is None:
                raise ReviewConflict("review_not_found")
            if (
                decision["accepted_state_version"]
                != expected_run_state_version
                or run["state_version"] != expected_run_state_version
            ):
                raise ReviewConflict("stale_state_version")

            result_decision = result.resolved_review.get("decision", {})
            if (
                result_decision.get("decision_id") != decision["decision_id"]
                or result_decision.get("action") != decision["action"]
            ):
                raise ReviewConflict("resolution_result_mismatch")
            if decision["action"] == "reject" and result.artifacts:
                raise ReviewConflict("resolution_result_mismatch")
            reviewed_content_hash = None
            if decision["action"] == "approve":
                if result.brief is None:
                    raise ReviewConflict("resolution_result_mismatch")
                reviewed_content_hash = with_content_hash(
                    result.brief
                ).content_hash
                if result.brief.content_hash != reviewed_content_hash:
                    raise ReviewConflict("resolution_result_mismatch")
                json_artifacts = [
                    artifact
                    for artifact in result.artifacts
                    if artifact["media_type"] == "application/json"
                ]
                markdown_artifacts = [
                    artifact
                    for artifact in result.artifacts
                    if artifact["media_type"] == "text/markdown"
                ]
                if len(json_artifacts) != 1 or len(markdown_artifacts) != 1:
                    raise ReviewConflict("resolution_result_mismatch")
                if any(
                    artifact["content_hash"] != reviewed_content_hash
                    for artifact in result.artifacts
                ):
                    raise ReviewConflict("resolution_result_mismatch")
                try:
                    stored_brief = DecisionBrief.model_validate_json(
                        json_artifacts[0]["content"]
                    )
                except ValueError as exc:
                    raise ReviewConflict(
                        "resolution_result_mismatch"
                    ) from exc
                if (
                    stored_brief.content_hash != reviewed_content_hash
                    or with_content_hash(stored_brief).content_hash
                    != reviewed_content_hash
                ):
                    raise ReviewConflict("resolution_result_mismatch")

            now = _now()
            artifact_ids = tuple(
                sorted(artifact["artifact_id"] for artifact in result.artifacts)
            )
            resolution = ReviewResolution(
                resolution_id=review_resolution_id(decision["decision_id"]),
                run_id=workflow["run_id"],
                review_id=workflow["review_id"],
                decision_id=decision["decision_id"],
                action=decision["action"],
                artifact_ids=artifact_ids,
                created_at=now,
            )
            connection.executemany(
                """
                INSERT INTO run_artifacts_v2 (
                    artifact_id, run_id, kind, media_type, content,
                    content_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        artifact["artifact_id"],
                        workflow["run_id"],
                        artifact["kind"],
                        artifact["media_type"],
                        artifact["content"],
                        artifact["content_hash"],
                        now,
                    )
                    for artifact in result.artifacts
                ],
            )
            connection.execute(
                """
                INSERT INTO review_resolutions_v2 (
                    resolution_id, run_id, review_id, decision_id, action,
                    resolved_review_json, artifact_ids_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolution.resolution_id,
                    resolution.run_id,
                    resolution.review_id,
                    resolution.decision_id,
                    resolution.action,
                    json.dumps(
                        result.resolved_review,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    json.dumps(artifact_ids, separators=(",", ":")),
                    now,
                ),
            )
            delivery_status = (
                "ready" if decision["action"] == "approve" else "blocked"
            )
            publication = _publication_for_review(
                connection,
                run_id=workflow["run_id"],
                review_id=workflow["review_id"],
            )
            if publication is not None:
                publication_artifact_ids = (
                    artifact_ids
                    if decision["action"] == "approve"
                    else tuple(
                        json.loads(
                            publication["artifact_ids_json"]
                        )
                    )
                )
                publication_cursor = connection.execute(
                    """
                    UPDATE run_publications_v2
                    SET status = ?,
                        artifact_ids_json = ?,
                        content_hash = ?,
                        resolved_at = ?
                    WHERE publication_id = ?
                      AND is_current = 1
                      AND status = 'review_required'
                    """,
                    (
                        delivery_status,
                        json.dumps(
                            publication_artifact_ids,
                            separators=(",", ":"),
                        ),
                        (
                            reviewed_content_hash
                            if decision["action"] == "approve"
                            else publication["content_hash"]
                        ),
                        now,
                        publication["publication_id"],
                    ),
                )
                if publication_cursor.rowcount != 1:
                    raise ReviewConflict("review_superseded")
            run_cursor = connection.execute(
                """
                UPDATE research_runs_v2
                SET review_status = 'resolved',
                    delivery_status = ?,
                    state_version = state_version + 1,
                    updated_at = ?
                WHERE run_id = ? AND state_version = ?
                """,
                (
                    delivery_status,
                    now,
                    workflow["run_id"],
                    expected_run_state_version,
                ),
            )
            if run_cursor.rowcount != 1:
                raise ReviewConflict("stale_state_version")
            terminal_status = (
                "approved" if decision["action"] == "approve" else "rejected"
            )
            workflow_cursor = connection.execute(
                """
                UPDATE review_workflows_v2
                SET status = ?, lease_owner = NULL, lease_expires_at = NULL,
                    updated_at = ?
                WHERE workflow_id = ? AND status = 'resolution_pending'
                  AND lease_owner = ?
                """,
                (terminal_status, now, workflow_id, worker_id),
            )
            if workflow_cursor.rowcount != 1:
                raise ReviewConflict("lease_not_owned")
            attempt_cursor = connection.execute(
                """
                UPDATE review_resume_attempts_v2
                SET completed_at = ?, outcome = ?, error_code = NULL
                WHERE workflow_id = ? AND attempt = ? AND worker_id = ?
                  AND completed_at IS NULL
                """,
                (
                    now,
                    terminal_status,
                    workflow_id,
                    workflow["attempt_count"],
                    worker_id,
                ),
            )
            if attempt_cursor.rowcount != 1:
                raise ReviewConflict("resume_attempt_not_found")
            return resolution
    except sqlite3.IntegrityError as exc:
        raise ReviewConflict("review_resolution_conflict") from exc
    finally:
        connection.close()
