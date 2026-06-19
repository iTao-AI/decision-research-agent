"""Run-scoped persistence for the evidence-governed research API."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
import uuid
from typing import Any

from api.persistence import _get_db_path


EXECUTION_STATUSES = {
    "pending",
    "running",
    "completed",
    "completed_with_fallback",
    "failed",
}
REVIEW_STATUSES = {"not_required", "required", "resolved"}
DELIVERY_STATUSES = {"pending", "ready", "review_required", "failed"}
MIGRATION_VERSION = "003_run_identity_backbone"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(_get_db_path(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_run_schema(db_path: str | None = None) -> None:
    """Apply the additive run identity migration idempotently."""
    conn = _connect(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL,
                    checksum TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_runs_v2 (
                    run_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    profile_version TEXT NOT NULL,
                    scope_json TEXT NOT NULL,
                    execution_status TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    delivery_status TEXT NOT NULL,
                    state_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_segments (
                    segment_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    attempt INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(run_id, sequence)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_entries_v2 (
                    evidence_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
                    segment_id TEXT NOT NULL REFERENCES run_segments(segment_id) ON DELETE CASCADE,
                    query_text TEXT NOT NULL,
                    subagent_name TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    source_url TEXT,
                    source_identity TEXT NOT NULL,
                    snippet TEXT NOT NULL,
                    evidence_fingerprint TEXT NOT NULL,
                    retrieved_at TEXT,
                    tool_call_id TEXT,
                    citation_status TEXT NOT NULL,
                    verification_status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(run_id, evidence_fingerprint)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_packets_v2 (
                    packet_id TEXT NOT NULL,
                    run_id TEXT NOT NULL REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
                    segment_id TEXT NOT NULL REFERENCES run_segments(segment_id) ON DELETE CASCADE,
                    packet_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(run_id, packet_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS review_bundles_v2 (
                    review_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
                    revision INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    bundle_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_artifacts_v2 (
                    artifact_id TEXT NOT NULL,
                    run_id TEXT NOT NULL REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(run_id, artifact_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_research_runs_v2_thread "
                "ON research_runs_v2(thread_id, created_at DESC)"
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, applied_at, checksum)
                VALUES (?, ?, ?)
                """,
                (MIGRATION_VERSION, _now(), "run-identity-backbone-v1"),
            )
    finally:
        conn.close()


def create_run(
    *,
    thread_id: str,
    query: str,
    db_path: str | None = None,
    profile_id: str = "generic",
    profile_version: str = "1",
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create one immutable run identity and its initial business segment."""
    init_run_schema(db_path)
    run_id = f"run_{uuid.uuid4().hex}"
    segment_id = f"{run_id}_seg_000"
    now = _now()
    conn = _connect(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO research_runs_v2 (
                    run_id, thread_id, query, profile_id, profile_version, scope_json,
                    execution_status, review_status, delivery_status, state_version,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', 'not_required', 'pending', 0, ?, ?)
                """,
                (
                    run_id,
                    thread_id,
                    query,
                    profile_id,
                    profile_version,
                    json.dumps(scope or {}, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO run_segments (
                    segment_id, run_id, kind, sequence, attempt, status, created_at, updated_at
                ) VALUES (?, ?, 'initial', 0, 1, 'pending', ?, ?)
                """,
                (segment_id, run_id, now, now),
            )
    finally:
        conn.close()
    return {"run_id": run_id, "thread_id": thread_id, "segment_id": segment_id}


def _run_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["scope"] = json.loads(data.pop("scope_json"))
    return data


def get_run(*, run_id: str, db_path: str | None = None) -> dict[str, Any] | None:
    from api.review_repository import get_review_projection, init_review_schema

    init_review_schema(db_path)
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM research_runs_v2 WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        segments = conn.execute(
            "SELECT * FROM run_segments WHERE run_id = ? ORDER BY sequence ASC",
            (run_id,),
        ).fetchall()
        result = _run_row(row)
        result["segments"] = [dict(segment) for segment in segments]
        evidence = conn.execute(
            """
            SELECT * FROM evidence_entries_v2
            WHERE run_id = ?
            ORDER BY created_at ASC, evidence_id ASC
            """,
            (run_id,),
        ).fetchall()
        result["evidence"] = [dict(entry) for entry in evidence]
        packets = conn.execute(
            "SELECT packet_json FROM research_packets_v2 WHERE run_id = ? ORDER BY packet_id",
            (run_id,),
        ).fetchall()
        result["research_packets"] = [json.loads(item["packet_json"]) for item in packets]
        review = conn.execute(
            "SELECT bundle_json FROM review_bundles_v2 WHERE run_id = ?", (run_id,)
        ).fetchone()
        result["review_bundle"] = json.loads(review["bundle_json"]) if review else None
        artifacts = conn.execute(
            """
            SELECT artifact_id, kind, media_type, content_hash, created_at
            FROM run_artifacts_v2 WHERE run_id = ? ORDER BY artifact_id
            """,
            (run_id,),
        ).fetchall()
        result["artifacts"] = [dict(item) for item in artifacts]
        review_projection = get_review_projection(db_path=db_path, run_id=run_id)
        result["review_workflow"] = review_projection["workflow"]
        result["review_decision"] = review_projection["decision"]
        result["review_resolution"] = review_projection["resolution"]
        return result
    finally:
        conn.close()


def finalize_run_transaction(
    *,
    run_id: str,
    segment_id: str,
    expected_state_version: int,
    allowed_previous_statuses: set[str],
    execution_status: str,
    delivery_status: str,
    evidence_entries: list[Any],
    db_path: str | None = None,
    review_status: str = "not_required",
    research_packets: list[Any] | None = None,
    review_bundle: Any | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    review_workflow: dict[str, str] | None = None,
) -> bool:
    """Atomically persist terminal run, segment, and evidence state."""
    if execution_status not in EXECUTION_STATUSES:
        raise ValueError(f"invalid execution_status: {execution_status}")
    if delivery_status not in DELIVERY_STATUSES:
        raise ValueError(f"invalid delivery_status: {delivery_status}")
    if review_status not in REVIEW_STATUSES:
        raise ValueError(f"invalid review_status: {review_status}")
    if not allowed_previous_statuses:
        raise ValueError("allowed_previous_statuses must not be empty")

    from api.review_repository import init_review_schema

    init_review_schema(db_path)
    conn = _connect(db_path)
    now = _now()
    placeholders = ", ".join("?" for _ in allowed_previous_statuses)
    try:
        with conn:
            cursor = conn.execute(
                f"""
                UPDATE research_runs_v2
                SET execution_status = ?,
                    review_status = ?,
                    delivery_status = ?,
                    state_version = state_version + 1,
                    updated_at = ?
                WHERE run_id = ?
                  AND state_version = ?
                  AND execution_status IN ({placeholders})
                """,
                (
                    execution_status,
                    review_status,
                    delivery_status,
                    now,
                    run_id,
                    expected_state_version,
                    *sorted(allowed_previous_statuses),
                ),
            )
            if cursor.rowcount != 1:
                return False
            segment_cursor = conn.execute(
                """
                UPDATE run_segments
                SET status = ?, updated_at = ?
                WHERE segment_id = ? AND run_id = ?
                """,
                (execution_status, now, segment_id, run_id),
            )
            if segment_cursor.rowcount != 1:
                raise ValueError("segment_id does not belong to run_id")
            conn.executemany(
                """
                INSERT INTO evidence_entries_v2 (
                    evidence_id, run_id, segment_id, query_text, subagent_name,
                    tool_name, source_url, source_identity, snippet,
                    evidence_fingerprint, retrieved_at, tool_call_id,
                    citation_status, verification_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        f"ev_{run_id}_{entry.evidence_fingerprint}",
                        run_id,
                        segment_id,
                        entry.query_text,
                        entry.subagent_name,
                        entry.tool_name,
                        entry.source_url,
                        entry.source_identity,
                        entry.snippet,
                        entry.evidence_fingerprint,
                        entry.retrieved_at,
                        entry.tool_call_id,
                        entry.citation_status,
                        entry.verification_status,
                        entry.created_at,
                    )
                    for entry in evidence_entries
                ],
            )
            conn.executemany(
                """
                INSERT INTO research_packets_v2 (
                    packet_id, run_id, segment_id, packet_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        packet.packet_id,
                        run_id,
                        segment_id,
                        packet.model_dump_json(),
                        now,
                    )
                    for packet in (research_packets or [])
                ],
            )
            if review_bundle is not None:
                conn.execute(
                    """
                    INSERT INTO review_bundles_v2 (
                        review_id, run_id, revision, status, bundle_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review_bundle.review_id,
                        run_id,
                        review_bundle.revision,
                        review_bundle.status,
                        review_bundle.model_dump_json(),
                        now,
                    ),
                )
            if review_workflow is not None:
                if (
                    review_bundle is None
                    or not review_bundle.required_before_delivery
                ):
                    raise ValueError(
                        "review_workflow requires a required review_bundle"
                    )
                conn.execute(
                    """
                    INSERT INTO review_workflows_v2 (
                        workflow_id, run_id, review_id, review_revision,
                        checkpoint_thread_id, status, post_review_segment_id,
                        attempt_count, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'checkpoint_pending', ?, 0, ?, ?)
                    """,
                    (
                        review_workflow["workflow_id"],
                        run_id,
                        review_bundle.review_id,
                        review_bundle.revision,
                        review_workflow["checkpoint_thread_id"],
                        review_workflow["post_review_segment_id"],
                        now,
                        now,
                    ),
                )
            conn.executemany(
                """
                INSERT INTO run_artifacts_v2 (
                    artifact_id, run_id, kind, media_type, content, content_hash, created_at
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
                    for artifact in (artifacts or [])
                ],
            )
            return True
    finally:
        conn.close()


def get_artifact(
    *, run_id: str, artifact_id: str, db_path: str | None = None
) -> dict[str, Any] | None:
    init_run_schema(db_path)
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM run_artifacts_v2 WHERE run_id = ? AND artifact_id = ?",
            (run_id, artifact_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def transition_run(
    *,
    run_id: str,
    expected_state_version: int,
    allowed_previous_statuses: set[str],
    db_path: str | None = None,
    execution_status: str | None = None,
    review_status: str | None = None,
    delivery_status: str | None = None,
) -> bool:
    """Apply a fenced status transition, returning False for a stale write."""
    if execution_status is not None and execution_status not in EXECUTION_STATUSES:
        raise ValueError(f"invalid execution_status: {execution_status}")
    if review_status is not None and review_status not in REVIEW_STATUSES:
        raise ValueError(f"invalid review_status: {review_status}")
    if delivery_status is not None and delivery_status not in DELIVERY_STATUSES:
        raise ValueError(f"invalid delivery_status: {delivery_status}")
    if not allowed_previous_statuses:
        raise ValueError("allowed_previous_statuses must not be empty")

    updates = ["state_version = state_version + 1", "updated_at = ?"]
    params: list[Any] = [_now()]
    for column, value in (
        ("execution_status", execution_status),
        ("review_status", review_status),
        ("delivery_status", delivery_status),
    ):
        if value is not None:
            updates.append(f"{column} = ?")
            params.append(value)

    placeholders = ", ".join("?" for _ in allowed_previous_statuses)
    params.extend([run_id, expected_state_version, *sorted(allowed_previous_statuses)])
    conn = _connect(db_path)
    try:
        with conn:
            cursor = conn.execute(
                f"""
                UPDATE research_runs_v2
                SET {", ".join(updates)}
                WHERE run_id = ?
                  AND state_version = ?
                  AND execution_status IN ({placeholders})
                """,
                params,
            )
            return cursor.rowcount == 1
    finally:
        conn.close()
