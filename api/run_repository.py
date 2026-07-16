"""Run-scoped persistence for the evidence-governed research API."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
import uuid
from typing import Any

from pydantic import ValidationError

from api.database import backup_database, restore_database, sqlite_db_path
from api.run_creation_models import (
    RUN_CREATE_IDEMPOTENCY_MIGRATION_CHECKSUM,
    RUN_CREATE_IDEMPOTENCY_MIGRATION_VERSION,
    RUN_CREATE_REQUEST_SCHEMA_VERSION,
    RunCreationAcceptance,
    idempotency_key_hash,
    run_create_request_hash,
)
from api.run_dispatch_models import (
    RUN_DISPATCH_MIGRATION_CHECKSUM,
    RUN_DISPATCH_MIGRATION_VERSION,
    RunDispatchConflict,
)
from api.run_failure_cause_models import (
    RUN_FAILURE_CAUSE_MIGRATION_CHECKSUM,
    RUN_FAILURE_CAUSE_MIGRATION_VERSION,
    RUN_FAILURE_CAUSE_SCHEMA_VERSION,
    RunFailureCauseConflict,
    RunFailureCauseProjectionAdapter,
    RunFailureCauseWrite,
)


EXECUTION_STATUSES = {
    "pending",
    "running",
    "completed",
    "completed_with_fallback",
    "failed",
}
REVIEW_STATUSES = {"not_required", "required", "resolved"}
DELIVERY_STATUSES = {
    "pending",
    "ready",
    "review_required",
    "blocked",
    "failed",
}
MIGRATION_VERSION = "003_run_identity_backbone"
_SCHEMA_INIT_LOCK = threading.Lock()
RUN_FAILURE_CAUSE_TABLE_SQL = """
CREATE TABLE run_failure_causes_v1 (
    run_id TEXT NOT NULL PRIMARY KEY
        REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
    observation_status TEXT NOT NULL
        CHECK(observation_status IN ('observed', 'not_observed')),
    terminal_state_version INTEGER,
    phase TEXT,
    code TEXT,
    recorded_at TEXT,
    CHECK(
        (
            observation_status = 'not_observed'
            AND terminal_state_version IS NULL
            AND phase IS NULL
            AND code IS NULL
            AND recorded_at IS NULL
        )
        OR
        (
            observation_status = 'observed'
            AND typeof(terminal_state_version) = 'integer'
            AND terminal_state_version > 0
            AND phase IS NOT NULL
            AND code IS NOT NULL
            AND recorded_at IS NOT NULL
            AND (
                (phase = 'dispatch' AND code IN (
                    'run_dispatch_schedule_failed',
                    'run_dispatch_start_failed',
                    'run_dispatch_start_timeout',
                    'run_dispatch_lease_expired'
                ))
                OR
                (phase = 'execution' AND code IN (
                    'call_budget_exceeded',
                    'recursion_limit_exceeded',
                    'invalid_research_packet',
                    'missing_research_packet',
                    'run_timeout',
                    'cancelled',
                    'execution_error'
                ))
                OR
                (phase = 'finalization' AND code IN (
                    'run_timeout',
                    'cancelled',
                    'run_finalization_failed'
                ))
            )
        )
    )
)
"""


class RunCreationConflict(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(sqlite_db_path(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _inspect_run_failure_cause_marker(db_path: str | None) -> bool:
    connection = sqlite3.connect(sqlite_db_path(db_path))
    try:
        has_marker_table = connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'schema_migrations'
            """
        ).fetchone()
        if has_marker_table is None:
            return False
        rows = connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version = ?",
            (RUN_FAILURE_CAUSE_MIGRATION_VERSION,),
        ).fetchall()
    except sqlite3.Error as exc:
        raise RunFailureCauseConflict("run_failure_cause_corrupt") from exc
    finally:
        connection.close()
    if not rows:
        return False
    if (
        len(rows) != 1
        or rows[0][0] != RUN_FAILURE_CAUSE_MIGRATION_CHECKSUM
    ):
        raise RunFailureCauseConflict("run_failure_cause_unavailable")
    return True


def _verify_run_failure_cause_marker(
    connection: sqlite3.Connection,
) -> None:
    try:
        rows = connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version = ?",
            (RUN_FAILURE_CAUSE_MIGRATION_VERSION,),
        ).fetchall()
    except sqlite3.Error as exc:
        raise RunFailureCauseConflict("run_failure_cause_unavailable") from exc
    if (
        len(rows) != 1
        or rows[0][0] != RUN_FAILURE_CAUSE_MIGRATION_CHECKSUM
    ):
        raise RunFailureCauseConflict("run_failure_cause_unavailable")


def _verify_run_failure_cause_schema(
    connection: sqlite3.Connection,
) -> None:
    try:
        table_row = connection.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = 'run_failure_causes_v1'
            """
        ).fetchone()
        if table_row is None:
            raise RunFailureCauseConflict("run_failure_cause_unavailable")
        columns = connection.execute(
            "PRAGMA table_info(run_failure_causes_v1)"
        ).fetchall()
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(run_failure_causes_v1)"
        ).fetchall()
    except RunFailureCauseConflict:
        raise
    except sqlite3.Error as exc:
        raise RunFailureCauseConflict("run_failure_cause_corrupt") from exc

    expected_columns = [
        ("run_id", "TEXT", 1, None, 1),
        ("observation_status", "TEXT", 1, None, 0),
        ("terminal_state_version", "INTEGER", 0, None, 0),
        ("phase", "TEXT", 0, None, 0),
        ("code", "TEXT", 0, None, 0),
        ("recorded_at", "TEXT", 0, None, 0),
    ]
    actual_columns = [tuple(row[1:6]) for row in columns]
    exact_foreign_key = (
        len(foreign_keys) == 1
        and tuple(foreign_keys[0][2:7])
        == (
            "research_runs_v2",
            "run_id",
            "run_id",
            "NO ACTION",
            "CASCADE",
        )
    )
    if (
        actual_columns != expected_columns
        or not exact_foreign_key
        or " ".join(table_row[0].split()).lower()
        != " ".join(RUN_FAILURE_CAUSE_TABLE_SQL.split()).lower()
    ):
        raise RunFailureCauseConflict("run_failure_cause_corrupt")


def _verify_run_failure_cause_rows(
    connection: sqlite3.Connection,
) -> None:
    try:
        rows = connection.execute(
            """
            SELECT cause.run_id,
                   cause.observation_status,
                   cause.terminal_state_version,
                   cause.phase,
                   cause.code,
                   cause.recorded_at,
                   run.execution_status,
                   run.state_version,
                   run.updated_at
            FROM run_failure_causes_v1 AS cause
            LEFT JOIN research_runs_v2 AS run ON run.run_id = cause.run_id
            ORDER BY cause.run_id
            """
        ).fetchall()
        missing_failed_runs = connection.execute(
            """
            SELECT run.run_id
            FROM research_runs_v2 AS run
            LEFT JOIN run_failure_causes_v1 AS cause
              ON cause.run_id = run.run_id
            WHERE run.execution_status = 'failed'
              AND cause.run_id IS NULL
            ORDER BY run.run_id
            """
        ).fetchall()
        if missing_failed_runs:
            raise RunFailureCauseConflict("run_failure_cause_corrupt")

        for row in rows:
            if row["execution_status"] != "failed":
                raise RunFailureCauseConflict("run_failure_cause_corrupt")
            if row["observation_status"] == "not_observed":
                if any(
                    row[name] is not None
                    for name in (
                        "terminal_state_version",
                        "phase",
                        "code",
                        "recorded_at",
                    )
                ):
                    raise RunFailureCauseConflict(
                        "run_failure_cause_corrupt"
                    )
                RunFailureCauseProjectionAdapter.validate_python(
                    {
                        "schema_version": RUN_FAILURE_CAUSE_SCHEMA_VERSION,
                        "observation_status": "not_observed",
                    },
                    strict=True,
                )
                continue

            recorded_at = datetime.fromisoformat(row["recorded_at"])
            RunFailureCauseProjectionAdapter.validate_python(
                {
                    "schema_version": RUN_FAILURE_CAUSE_SCHEMA_VERSION,
                    "observation_status": row["observation_status"],
                    "phase": row["phase"],
                    "code": row["code"],
                    "recorded_at": recorded_at,
                },
                strict=True,
            )
            if (
                type(row["terminal_state_version"]) is not int
                or row["terminal_state_version"] <= 0
                or row["terminal_state_version"] != row["state_version"]
                or row["recorded_at"] != row["updated_at"]
            ):
                raise RunFailureCauseConflict("run_failure_cause_corrupt")
            failed_segment = connection.execute(
                """
                SELECT 1 FROM run_segments
                WHERE run_id = ?
                  AND status = 'failed'
                  AND updated_at = ?
                LIMIT 1
                """,
                (row["run_id"], row["recorded_at"]),
            ).fetchone()
            if failed_segment is None:
                raise RunFailureCauseConflict("run_failure_cause_corrupt")
    except RunFailureCauseConflict:
        raise
    except (sqlite3.Error, TypeError, ValueError) as exc:
        raise RunFailureCauseConflict("run_failure_cause_corrupt") from exc


def _apply_run_failure_cause_migration(
    db_path: str | None,
) -> None:
    connection = _connect(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        marker = connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version = ?",
            (RUN_FAILURE_CAUSE_MIGRATION_VERSION,),
        ).fetchone()
        if marker is not None:
            _verify_run_failure_cause_marker(connection)
            _verify_run_failure_cause_schema(connection)
            _verify_run_failure_cause_rows(connection)
            connection.commit()
            return

        connection.execute(RUN_FAILURE_CAUSE_TABLE_SQL)
        _verify_run_failure_cause_schema(connection)
        connection.execute(
            """
            INSERT INTO run_failure_causes_v1(
                run_id, observation_status, terminal_state_version,
                phase, code, recorded_at
            )
            SELECT run_id, 'not_observed', NULL, NULL, NULL, NULL
            FROM research_runs_v2
            WHERE execution_status = 'failed'
            ORDER BY run_id
            """
        )
        connection.execute(
            """
            INSERT INTO schema_migrations(version, applied_at, checksum)
            VALUES (?, ?, ?)
            """,
            (
                RUN_FAILURE_CAUSE_MIGRATION_VERSION,
                _now(),
                RUN_FAILURE_CAUSE_MIGRATION_CHECKSUM,
            ),
        )
        _verify_run_failure_cause_marker(connection)
        _verify_run_failure_cause_schema(connection)
        _verify_run_failure_cause_rows(connection)
        connection.commit()
    except RunFailureCauseConflict:
        connection.rollback()
        raise
    except (sqlite3.Error, TypeError, ValueError) as exc:
        connection.rollback()
        raise RunFailureCauseConflict("run_failure_cause_corrupt") from exc
    finally:
        connection.close()


def _insert_schema_marker_if_missing(
    connection: sqlite3.Connection,
    *,
    version: str,
    checksum: str,
) -> None:
    marker = connection.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ?",
        (version,),
    ).fetchone()
    if marker is None:
        connection.execute(
            """
            INSERT INTO schema_migrations(version, applied_at, checksum)
            VALUES (?, ?, ?)
            """,
            (version, _now(), checksum),
        )


def _init_run_schema_unlocked(db_path: str | None = None) -> None:
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
                CREATE TABLE IF NOT EXISTS run_create_idempotency_v1 (
                    key_hash TEXT PRIMARY KEY,
                    request_schema_version TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    run_id TEXT NOT NULL UNIQUE
                        REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_dispatches_v1 (
                    run_id TEXT PRIMARY KEY
                        REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
                    status TEXT NOT NULL
                        CHECK(status IN ('pending', 'leased', 'started', 'failed')),
                    lease_owner TEXT,
                    lease_expires_at TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0
                        CHECK(attempt_count >= 0),
                    last_error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    CHECK(
                        (status = 'leased'
                         AND lease_owner IS NOT NULL
                         AND lease_expires_at IS NOT NULL)
                        OR
                        (status != 'leased'
                         AND lease_owner IS NULL
                         AND lease_expires_at IS NULL)
                    ),
                    CHECK(
                        (status = 'started'
                         AND started_at IS NOT NULL
                         AND last_error_code IS NULL)
                        OR
                        (status = 'failed'
                         AND started_at IS NULL
                         AND last_error_code IS NOT NULL)
                        OR
                        (status IN ('pending', 'leased')
                         AND started_at IS NULL)
                    )
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
                    baseline_verification_origin TEXT NOT NULL DEFAULT 'none'
                        CHECK(
                            baseline_verification_origin
                            IN ('none', 'declared_fixture')
                        ),
                    created_at TEXT NOT NULL,
                    UNIQUE(run_id, evidence_fingerprint)
                )
                """
            )
            _ensure_baseline_origin_column(conn)
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
                CREATE INDEX IF NOT EXISTS idx_run_dispatches_status_lease_created
                ON run_dispatches_v1(status, lease_expires_at, created_at)
                """
            )
            _insert_schema_marker_if_missing(
                conn,
                version=MIGRATION_VERSION,
                checksum="run-identity-backbone-v1",
            )
            _insert_schema_marker_if_missing(
                conn,
                version=RUN_CREATE_IDEMPOTENCY_MIGRATION_VERSION,
                checksum=RUN_CREATE_IDEMPOTENCY_MIGRATION_CHECKSUM,
            )
            _insert_schema_marker_if_missing(
                conn,
                version=RUN_DISPATCH_MIGRATION_VERSION,
                checksum=RUN_DISPATCH_MIGRATION_CHECKSUM,
            )
    finally:
        conn.close()
    _apply_run_failure_cause_migration(db_path)


def init_run_schema(db_path: str | None = None) -> None:
    """Apply the additive schema once at a time within this process."""
    with _SCHEMA_INIT_LOCK:
        marker_present = _inspect_run_failure_cause_marker(db_path)
        if marker_present:
            _init_run_schema_unlocked(db_path)
            return

        failure_backup_path = Path(
            f"{sqlite_db_path(db_path)}.pre-run-failure-cause.bak"
        )
        if failure_backup_path.exists():
            raise RuntimeError(
                "run_failure_cause_migration_backup_already_exists"
            )
        backup_database(
            db_path=sqlite_db_path(db_path),
            backup_path=str(failure_backup_path),
        )
        try:
            _init_run_schema_unlocked(db_path)
        except Exception:
            restore_database(
                backup_path=str(failure_backup_path),
                db_path=sqlite_db_path(db_path),
            )
            raise


def _ensure_baseline_origin_column(
    connection: sqlite3.Connection,
) -> None:
    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(evidence_entries_v2)"
        ).fetchall()
    }
    if "baseline_verification_origin" not in columns:
        connection.execute(
            """
            ALTER TABLE evidence_entries_v2
            ADD COLUMN baseline_verification_origin TEXT NOT NULL DEFAULT 'none'
            CHECK(
                baseline_verification_origin
                IN ('none', 'declared_fixture')
            )
            """
        )


def _insert_run_identity(
    connection: sqlite3.Connection,
    *,
    thread_id: str,
    query: str,
    profile_id: str,
    profile_version: str,
    scope: dict[str, Any],
    now: str,
) -> dict[str, str]:
    _verify_run_failure_cause_marker(connection)
    _verify_run_failure_cause_schema(connection)
    _verify_run_failure_cause_rows(connection)
    marker = connection.execute(
        "SELECT checksum FROM schema_migrations WHERE version = ?",
        (RUN_DISPATCH_MIGRATION_VERSION,),
    ).fetchone()
    if (
        marker is None
        or marker["checksum"] != RUN_DISPATCH_MIGRATION_CHECKSUM
    ):
        raise RunDispatchConflict("run_dispatch_unavailable")
    run_id = f"run_{uuid.uuid4().hex}"
    segment_id = f"{run_id}_seg_000"
    connection.execute(
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
            json.dumps(
                scope,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            now,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO run_segments (
            segment_id, run_id, kind, sequence, attempt, status, created_at, updated_at
        ) VALUES (?, ?, 'initial', 0, 1, 'pending', ?, ?)
        """,
        (segment_id, run_id, now, now),
    )
    connection.execute(
        """
        INSERT INTO run_dispatches_v1 (
            run_id, status, lease_owner, lease_expires_at, attempt_count,
            last_error_code, created_at, updated_at, started_at
        ) VALUES (?, 'pending', NULL, NULL, 0, NULL, ?, ?, NULL)
        """,
        (run_id, now, now),
    )
    return {"run_id": run_id, "thread_id": thread_id, "segment_id": segment_id}


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
    now = _now()
    conn = _connect(db_path)
    try:
        with conn:
            return _insert_run_identity(
                conn,
                thread_id=thread_id,
                query=query,
                profile_id=profile_id,
                profile_version=profile_version,
                scope=scope or {},
                now=now,
            )
    finally:
        conn.close()


def create_or_replay_run(
    *,
    idempotency_key: str,
    thread_id: str | None,
    query: str,
    db_path: str | None = None,
    profile_id: str = "generic",
    profile_version: str = "1",
    scope: dict[str, Any] | None = None,
) -> RunCreationAcceptance:
    key_hash = idempotency_key_hash(idempotency_key)
    normalized_scope = scope or {}
    request_hash = run_create_request_hash(
        query=query,
        thread_id=thread_id,
        profile_id=profile_id,
        scope=normalized_scope,
    )
    connection = None
    try:
        init_run_schema(db_path)
        connection = _connect(db_path)
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            marker = connection.execute(
                "SELECT checksum FROM schema_migrations WHERE version = ?",
                (RUN_CREATE_IDEMPOTENCY_MIGRATION_VERSION,),
            ).fetchone()
            if (
                marker is None
                or marker["checksum"] != RUN_CREATE_IDEMPOTENCY_MIGRATION_CHECKSUM
            ):
                raise RunCreationConflict("run_idempotency_unavailable")
            existing = connection.execute(
                """
                SELECT request_schema_version, request_hash, run_id
                FROM run_create_idempotency_v1
                WHERE key_hash = ?
                """,
                (key_hash,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["request_schema_version"]
                    != RUN_CREATE_REQUEST_SCHEMA_VERSION
                    or existing["request_hash"] != request_hash
                ):
                    raise RunCreationConflict("run_idempotency_conflict")
                identity = connection.execute(
                    """
                    SELECT run.run_id, run.thread_id, segment.segment_id
                    FROM research_runs_v2 AS run
                    JOIN run_segments AS segment
                      ON segment.run_id = run.run_id
                     AND segment.sequence = 0
                     AND segment.kind = 'initial'
                    WHERE run.run_id = ?
                    """,
                    (existing["run_id"],),
                ).fetchone()
                if identity is None:
                    raise RunCreationConflict("run_idempotency_unavailable")
                return RunCreationAcceptance(
                    run_id=identity["run_id"],
                    thread_id=identity["thread_id"],
                    segment_id=identity["segment_id"],
                    idempotent_replay=True,
                )

            now = _now()
            created = _insert_run_identity(
                connection,
                thread_id=thread_id or str(uuid.uuid4()),
                query=query,
                profile_id=profile_id,
                profile_version=profile_version,
                scope=normalized_scope,
                now=now,
            )
            connection.execute(
                """
                INSERT INTO run_create_idempotency_v1 (
                    key_hash, request_schema_version, request_hash, run_id, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    key_hash,
                    RUN_CREATE_REQUEST_SCHEMA_VERSION,
                    request_hash,
                    created["run_id"],
                    now,
                ),
            )
            return RunCreationAcceptance(**created, idempotent_replay=False)
    except RunCreationConflict:
        raise
    except sqlite3.Error as exc:
        raise RunCreationConflict("run_idempotency_unavailable") from exc
    finally:
        if connection is not None:
            connection.close()


_FAILURE_CAUSE_JOIN_COLUMNS = (
    "failure_observation_status",
    "failure_terminal_state_version",
    "failure_phase",
    "failure_code",
    "failure_recorded_at",
)


def _failure_cause_projection(row: sqlite3.Row | dict[str, Any]):
    try:
        data = dict(row)
        observation_status = data["failure_observation_status"]
        terminal_state_version = data["failure_terminal_state_version"]
        phase = data["failure_phase"]
        code = data["failure_code"]
        recorded_at = data["failure_recorded_at"]
        storage_values = (
            observation_status,
            terminal_state_version,
            phase,
            code,
            recorded_at,
        )

        if data["execution_status"] != "failed":
            if any(value is not None for value in storage_values):
                raise RunFailureCauseConflict("run_failure_cause_corrupt")
            return None

        if observation_status is None:
            raise RunFailureCauseConflict("run_failure_cause_corrupt")
        if observation_status == "not_observed":
            if any(
                value is not None
                for value in (
                    terminal_state_version,
                    phase,
                    code,
                    recorded_at,
                )
            ):
                raise RunFailureCauseConflict("run_failure_cause_corrupt")
            payload = {
                "schema_version": RUN_FAILURE_CAUSE_SCHEMA_VERSION,
                "observation_status": "not_observed",
            }
        else:
            if (
                type(terminal_state_version) is not int
                or terminal_state_version <= 0
                or terminal_state_version != data["state_version"]
                or recorded_at != data["updated_at"]
            ):
                raise RunFailureCauseConflict("run_failure_cause_corrupt")
            payload = {
                "schema_version": RUN_FAILURE_CAUSE_SCHEMA_VERSION,
                "observation_status": observation_status,
                "phase": phase,
                "code": code,
                "recorded_at": datetime.fromisoformat(recorded_at),
            }

        projection = RunFailureCauseProjectionAdapter.validate_python(
            payload,
            strict=True,
        )
        return projection.model_dump(mode="json")
    except RunFailureCauseConflict:
        raise
    except (ValidationError, KeyError, TypeError, ValueError) as exc:
        raise RunFailureCauseConflict("run_failure_cause_corrupt") from exc


def _run_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    data["scope"] = json.loads(data.pop("scope_json"))
    return data


def _public_evidence_row(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    value.pop("baseline_verification_origin", None)
    return value


def get_run(*, run_id: str, db_path: str | None = None) -> dict[str, Any] | None:
    from api.review_repository import get_review_projection, init_review_schema

    init_review_schema(db_path)
    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT
                r.*,
                c.observation_status AS failure_observation_status,
                c.terminal_state_version AS failure_terminal_state_version,
                c.phase AS failure_phase,
                c.code AS failure_code,
                c.recorded_at AS failure_recorded_at
            FROM research_runs_v2 AS r
            LEFT JOIN run_failure_causes_v1 AS c ON c.run_id = r.run_id
            WHERE r.run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        failure_cause = _failure_cause_projection(row)
        run_data = dict(row)
        for column in _FAILURE_CAUSE_JOIN_COLUMNS:
            run_data.pop(column)
        segments = conn.execute(
            "SELECT * FROM run_segments WHERE run_id = ? ORDER BY sequence ASC",
            (run_id,),
        ).fetchall()
        result = _run_row(run_data)
        result["failure_cause"] = failure_cause
        result["segments"] = [dict(segment) for segment in segments]
        evidence = conn.execute(
            """
            SELECT * FROM evidence_entries_v2
            WHERE run_id = ?
            ORDER BY created_at ASC, evidence_id ASC
            """,
            (run_id,),
        ).fetchall()
        result["evidence"] = [_public_evidence_row(entry) for entry in evidence]
        packets = conn.execute(
            "SELECT packet_json FROM research_packets_v2 WHERE run_id = ? ORDER BY packet_id",
            (run_id,),
        ).fetchall()
        result["research_packets"] = [json.loads(item["packet_json"]) for item in packets]
        publication_table_exists = (
            conn.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'run_publications_v2'
                """
            ).fetchone()
            is not None
        )
        current_publication = (
            conn.execute(
                """
                SELECT * FROM run_publications_v2
                WHERE run_id = ? AND is_current = 1
                """,
                (run_id,),
            ).fetchone()
            if publication_table_exists
            else None
        )
        if current_publication is not None:
            review = conn.execute(
                """
                SELECT bundle_json FROM review_bundles_v2
                WHERE review_id = ?
                """,
                (current_publication["review_id"],),
            ).fetchone()
        else:
            publication_rows_exist = (
                publication_table_exists
                and conn.execute(
                    """
                    SELECT 1 FROM run_publications_v2
                    WHERE run_id = ? LIMIT 1
                    """,
                    (run_id,),
                ).fetchone()
                is not None
            )
            review = (
                None
                if publication_rows_exist
                else conn.execute(
                    """
                    SELECT bundle_json FROM review_bundles_v2
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()
            )
        result["review_bundle"] = json.loads(review["bundle_json"]) if review else None
        artifacts = conn.execute(
            """
            SELECT artifact_id, kind, media_type, content_hash, created_at
            FROM run_artifacts_v2 WHERE run_id = ? ORDER BY artifact_id
            """,
            (run_id,),
        ).fetchall()
        result["artifacts"] = [dict(item) for item in artifacts]
        if current_publication is not None:
            artifact_ids = json.loads(
                current_publication["artifact_ids_json"]
            )
            current_artifact_rows = []
            if artifact_ids:
                placeholders = ", ".join("?" for _ in artifact_ids)
                rows = conn.execute(
                    f"""
                    SELECT artifact_id, kind, media_type, content_hash,
                           created_at
                    FROM run_artifacts_v2
                    WHERE run_id = ?
                      AND artifact_id IN ({placeholders})
                    """,
                    (run_id, *artifact_ids),
                ).fetchall()
                by_id = {row["artifact_id"]: dict(row) for row in rows}
                current_artifact_rows = [
                    by_id[artifact_id]
                    for artifact_id in artifact_ids
                    if artifact_id in by_id
                ]
            snapshot = conn.execute(
                """
                SELECT snapshot_json, snapshot_hash
                FROM evidence_verification_snapshots_v2
                WHERE snapshot_id = ?
                """,
                (current_publication["verification_snapshot_id"],),
            ).fetchone()
            snapshot_items = (
                json.loads(snapshot["snapshot_json"])
                if snapshot is not None
                else []
            )
            state_counts: dict[str, int] = {}
            origin_counts: dict[str, int] = {}
            for item in snapshot_items:
                state = item["verification_state"]
                origin = item["verification_origin"]
                state_counts[state] = state_counts.get(state, 0) + 1
                origin_counts[origin] = origin_counts.get(origin, 0) + 1
            result["current_publication"] = {
                "publication_id": current_publication["publication_id"],
                "revision": current_publication["revision"],
                "status": current_publication["status"],
                "artifact_ids": artifact_ids,
            }
            result["current_artifacts"] = current_artifact_rows
            result["verification_summary"] = {
                "state_counts": dict(sorted(state_counts.items())),
                "origin_counts": dict(sorted(origin_counts.items())),
                "snapshot_hash": (
                    snapshot["snapshot_hash"]
                    if snapshot is not None
                    else None
                ),
            }
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
    failure_cause: RunFailureCauseWrite | None = None,
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
    if not allowed_previous_statuses or not allowed_previous_statuses <= {
        "pending",
        "running",
    }:
        raise RunFailureCauseConflict(
            "run_failure_cause_transition_invalid"
        )
    if execution_status == "failed" and failure_cause is None:
        raise RunFailureCauseConflict("run_failure_cause_required")
    if execution_status != "failed" and failure_cause is not None:
        raise RunFailureCauseConflict("run_failure_cause_forbidden")

    from api.publication_repository import (
        adopt_baseline_publication,
        evidence_verification_enabled,
        publication_schema_exists,
    )
    from api.review_repository import init_review_schema

    publication_enabled = evidence_verification_enabled()
    init_review_schema(db_path)
    conn = _connect(db_path)
    if publication_enabled and not publication_schema_exists(conn):
        conn.close()
        raise RuntimeError("verification_schema_not_ready")
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
            terminal_state_version = expected_state_version + 1
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
                    citation_status, verification_status,
                    baseline_verification_origin, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        entry.baseline_verification_origin,
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
            if publication_enabled:
                adopt_baseline_publication(
                    conn,
                    run_id=run_id,
                )
            if failure_cause is not None:
                try:
                    conn.execute(
                        """
                        INSERT INTO run_failure_causes_v1(
                            run_id, observation_status,
                            terminal_state_version, phase, code, recorded_at
                        ) VALUES (?, 'observed', ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            terminal_state_version,
                            failure_cause.phase,
                            failure_cause.code,
                            now,
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    raise RunFailureCauseConflict(
                        "run_failure_cause_conflict"
                    ) from exc
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
    if execution_status == "failed" or "failed" in allowed_previous_statuses:
        raise RunFailureCauseConflict(
            "run_failure_cause_transition_invalid"
        )

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
