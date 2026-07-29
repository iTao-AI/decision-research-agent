"""Dormant atomic repository for explicit one-hop replacement runs."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
import uuid
from typing import Callable

from api.database import sqlite_db_path
from api.run_execution_migrations import verify_run_execution_recovery_connection
from api.run_execution_models import RunExecutionConflict
from api.run_recovery_models import (
    RUN_RECOVERY_REQUEST_SCHEMA_VERSION,
    RunRecoveryAcceptance,
    RunRecoveryConflict,
    recovery_key_hash,
    run_recovery_request_hash,
    validate_recovery_key,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conflict(code: str) -> RunRecoveryConflict:
    return RunRecoveryConflict(code)


def _canonical_scope(run: sqlite3.Row) -> dict:
    try:
        scope = json.loads(run["scope_json"])
    except json.JSONDecodeError as exc:
        raise _conflict("run_recovery_state_invalid") from exc
    if (
        not isinstance(scope, dict)
        or json.dumps(scope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        != run["scope_json"]
    ):
        raise _conflict("run_recovery_state_invalid")
    return scope


def _validated_source(
    connection: sqlite3.Connection,
    source_run_id: str,
) -> tuple[sqlite3.Row, sqlite3.Row, sqlite3.Row, sqlite3.Row, dict]:
    run = connection.execute(
        "SELECT * FROM research_runs_v2 WHERE run_id=?", (source_run_id,)
    ).fetchone()
    if run is None:
        raise _conflict("run_recovery_source_not_found")
    segments = connection.execute(
        "SELECT * FROM run_segments WHERE run_id=? ORDER BY sequence, attempt",
        (source_run_id,),
    ).fetchall()
    owners = connection.execute(
        "SELECT * FROM run_execution_owners_v1 WHERE run_id=?", (source_run_id,)
    ).fetchall()
    causes = connection.execute(
        "SELECT * FROM run_failure_causes_v1 WHERE run_id=?", (source_run_id,)
    ).fetchall()
    if len(segments) != 1 or len(owners) != 1 or len(causes) != 1:
        raise _conflict("run_recovery_state_invalid")
    segment, owner, cause = segments[0], owners[0], causes[0]
    expected_code = {
        "execution": "execution_error",
        "finalization": "run_finalization_failed",
    }.get(owner["phase"])
    terminal_timestamp = run["updated_at"]
    if (
        run["execution_status"] != "failed"
        or run["review_status"] != "not_required"
        or run["delivery_status"] != "failed"
        or run["state_version"] != 2
        or segment["segment_id"] != owner["segment_id"]
        or segment["kind"] != "initial"
        or segment["sequence"] != 0
        or segment["attempt"] != 1
        or segment["status"] != "failed"
        or owner["status"] != "interrupted"
        or owner["boot_id"] is not None
        or owner["owner_id"] is not None
        or owner["recovery_reason"]
        not in {"previous_boot_interrupted", "pre_v1_running_without_owner"}
        or expected_code is None
        or cause["observation_status"] != "observed"
        or cause["terminal_state_version"] != 2
        or cause["phase"] != owner["phase"]
        or cause["code"] != expected_code
        or terminal_timestamp is None
        or segment["updated_at"] != terminal_timestamp
        or owner["phase_updated_at"] != terminal_timestamp
        or owner["closed_at"] != terminal_timestamp
        or cause["recorded_at"] != terminal_timestamp
    ):
        raise _conflict("run_recovery_state_invalid")
    return run, segment, owner, cause, _canonical_scope(run)


def _validated_replacement(
    connection: sqlite3.Connection,
    *,
    source: sqlite3.Row,
    lineage: sqlite3.Row,
) -> tuple[sqlite3.Row, sqlite3.Row]:
    replacement = connection.execute(
        "SELECT * FROM research_runs_v2 WHERE run_id=?",
        (lineage["replacement_run_id"],),
    ).fetchone()
    if replacement is None:
        raise _conflict("run_recovery_state_invalid")
    segments = connection.execute(
        "SELECT * FROM run_segments WHERE run_id=?",
        (lineage["replacement_run_id"],),
    ).fetchall()
    dispatches = connection.execute(
        "SELECT * FROM run_dispatches_v1 WHERE run_id=?",
        (lineage["replacement_run_id"],),
    ).fetchall()
    if len(segments) != 1 or len(dispatches) != 1:
        raise _conflict("run_recovery_state_invalid")
    segment, dispatch = segments[0], dispatches[0]
    if (
        replacement["thread_id"] != source["thread_id"]
        or replacement["query"] != source["query"]
        or replacement["profile_id"] != source["profile_id"]
        or replacement["profile_version"] != source["profile_version"]
        or replacement["scope_json"] != source["scope_json"]
        or segment["segment_id"] != f"{replacement['run_id']}_seg_000"
        or segment["kind"] != "initial"
        or segment["sequence"] != 0
        or segment["attempt"] != 1
        or segment["created_at"] != replacement["created_at"]
        or dispatch["created_at"] != replacement["created_at"]
    ):
        raise _conflict("run_recovery_state_invalid")
    return replacement, segment


def create_or_replay_run_recovery(
    *,
    source_run_id: str,
    idempotency_key: str,
    boot_id: str,
    exact_profile_is_available: Callable[[str, str], bool],
    db_path: str,
) -> RunRecoveryAcceptance:
    validate_recovery_key(idempotency_key)
    key_hash = recovery_key_hash(idempotency_key)
    connection = sqlite3.connect(sqlite_db_path(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    try:
        connection.execute("BEGIN IMMEDIATE")
        try:
            verify_run_execution_recovery_connection(connection)
        except RunExecutionConflict as exc:
            raise _conflict("run_recovery_state_invalid") from exc
        current = connection.execute(
            "SELECT boot_id FROM run_execution_boot_v1 WHERE boot_scope='application'"
        ).fetchone()
        if current is None or current["boot_id"] != boot_id:
            raise _conflict("run_execution_boot_stale")
        key_row = connection.execute(
            "SELECT * FROM run_recovery_retries_v1 WHERE key_hash=?", (key_hash,)
        ).fetchone()
        if key_row is not None and key_row["source_run_id"] != source_run_id:
            raise _conflict("run_recovery_conflict")
        if connection.execute(
            "SELECT 1 FROM run_recovery_retries_v1 WHERE replacement_run_id=?",
            (source_run_id,),
        ).fetchone():
            raise _conflict("run_recovery_exhausted")
        source_binding = connection.execute(
            "SELECT key_hash FROM run_recovery_retries_v1 WHERE source_run_id=?",
            (source_run_id,),
        ).fetchone()
        if key_row is None and source_binding is not None:
            raise _conflict("run_recovery_conflict")
        run, segment, owner, cause, scope = _validated_source(
            connection, source_run_id
        )
        request_hash = run_recovery_request_hash(
            source_run_id=source_run_id,
            segment_id=segment["segment_id"],
            query=run["query"],
            thread_id=run["thread_id"],
            profile_id=run["profile_id"],
            profile_version=run["profile_version"],
            scope=scope,
            execution_status="failed",
            review_status="not_required",
            delivery_status="failed",
            terminal_state_version=2,
            failure_phase=cause["phase"],
            failure_code=cause["code"],
            recovery_reason=owner["recovery_reason"],
            interrupted_phase=owner["phase"],
            recovery_attempt=1,
        )
        if key_row is not None:
            if (
                key_row["request_schema_version"]
                != RUN_RECOVERY_REQUEST_SCHEMA_VERSION
                or key_row["request_hash"] != request_hash
                or key_row["recovery_reason"] != owner["recovery_reason"]
                or key_row["interrupted_phase"] != owner["phase"]
                or key_row["recovery_attempt"] != 1
            ):
                raise _conflict("run_recovery_state_invalid")
            replacement, replacement_segment = _validated_replacement(
                connection,
                source=run,
                lineage=key_row,
            )
            connection.commit()
            return RunRecoveryAcceptance(
                reason=owner["recovery_reason"],
                interrupted_phase=owner["phase"],
                source_run_id=source_run_id,
                run_id=replacement["run_id"],
                thread_id=replacement["thread_id"],
                segment_id=replacement_segment["segment_id"],
                recovery_attempt=1,
                idempotent_replay=True,
            )
        if not exact_profile_is_available(run["profile_id"], run["profile_version"]):
            raise _conflict("run_recovery_not_eligible")
        replacement_id = f"run_{uuid.uuid4().hex}"
        replacement_segment = f"{replacement_id}_seg_000"
        timestamp = _now()
        connection.execute(
            """
            INSERT INTO research_runs_v2 VALUES
            (?, ?, ?, ?, ?, ?, 'pending', 'not_required', 'pending', 0, ?, ?)
            """,
            (
                replacement_id,
                run["thread_id"],
                run["query"],
                run["profile_id"],
                run["profile_version"],
                run["scope_json"],
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            "INSERT INTO run_segments VALUES (?, ?, 'initial', 0, 1, 'pending', ?, ?)",
            (replacement_segment, replacement_id, timestamp, timestamp),
        )
        connection.execute(
            "INSERT INTO run_dispatches_v1 VALUES (?, 'pending', NULL, NULL, 0, NULL, ?, ?, NULL)",
            (replacement_id, timestamp, timestamp),
        )
        connection.execute(
            """
            INSERT INTO run_recovery_retries_v1 VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                key_hash,
                RUN_RECOVERY_REQUEST_SCHEMA_VERSION,
                request_hash,
                source_run_id,
                replacement_id,
                owner["recovery_reason"],
                owner["phase"],
                timestamp,
            ),
        )
        connection.commit()
        return RunRecoveryAcceptance(
            reason=owner["recovery_reason"],
            interrupted_phase=owner["phase"],
            source_run_id=source_run_id,
            run_id=replacement_id,
            thread_id=run["thread_id"],
            segment_id=replacement_segment,
            recovery_attempt=1,
            idempotent_replay=False,
        )
    except RunRecoveryConflict:
        connection.rollback()
        raise
    except Exception as exc:
        connection.rollback()
        raise _conflict("run_recovery_unavailable") from exc
    finally:
        connection.close()
