"""Dormant, backup-protected migration for run execution recovery."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re
import sqlite3
from threading import Lock
from typing import Callable, TypeVar

from api.database import backup_database, restore_database, sqlite_db_path
from api.run_dispatch_models import MAX_RUN_DISPATCH_ATTEMPTS
from api.run_execution_models import (
    RUN_EXECUTION_RECOVERY_MIGRATION_CHECKSUM,
    RUN_EXECUTION_RECOVERY_MIGRATION_VERSION,
    RunExecutionConflict,
)
from api.run_recovery_models import (
    RUN_RECOVERY_REQUEST_SCHEMA_VERSION,
    run_recovery_request_hash,
)


_MIGRATION_LOCK = Lock()
_OWNER_INDEX = "idx_run_execution_owners_status_boot_created"
_T = TypeVar("_T")

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


def _run_migration_step(name: str, operation: Callable[[], _T]) -> _T:
    del name
    return operation()


def _normalized_sql(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().rstrip(";")).casefold()


def _valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _require(condition: bool) -> None:
    if not condition:
        raise RunExecutionConflict("run_execution_recovery_unavailable")


def _valid_identifier(value: object, prefix: str) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(rf"{re.escape(prefix)}[0-9a-f]{{32}}", value) is not None
    )


def _cause_matches(
    row: sqlite3.Row,
    *,
    terminal_state_version: int,
    terminal_timestamp: str,
) -> bool:
    return (
        row["observation_status"] == "observed"
        and row["terminal_state_version"] == terminal_state_version
        and isinstance(row["cause_phase"], str)
        and isinstance(row["cause_code"], str)
        and row["recorded_at"] == terminal_timestamp
    )


def _verify_dispatch_shape(row: sqlite3.Row) -> None:
    status = row["dispatch_status"]
    attempt = row["attempt_count"]
    _require(
        isinstance(attempt, int)
        and 0 <= attempt <= MAX_RUN_DISPATCH_ATTEMPTS
        and _valid_timestamp(row["dispatch_created_at"])
        and _valid_timestamp(row["dispatch_updated_at"])
    )
    if status == "pending":
        _require(
            row["lease_owner"] is None
            and row["lease_expires_at"] is None
            and row["started_at"] is None
            and (
                (
                    attempt == 0
                    and row["last_error_code"] is None
                )
                or (
                    1 <= attempt < MAX_RUN_DISPATCH_ATTEMPTS
                    and isinstance(row["last_error_code"], str)
                    and bool(row["last_error_code"])
                )
            )
        )
    elif status == "leased":
        _require(
            1 <= attempt <= MAX_RUN_DISPATCH_ATTEMPTS
            and _valid_identifier(row["lease_owner"], "dispatch_worker_")
            and _valid_timestamp(row["lease_expires_at"])
            and row["started_at"] is None
        )
    elif status == "started":
        _require(
            1 <= attempt <= MAX_RUN_DISPATCH_ATTEMPTS
            and row["lease_owner"] is None
            and row["lease_expires_at"] is None
            and row["last_error_code"] is None
            and _valid_timestamp(row["started_at"])
            and row["dispatch_updated_at"] == row["started_at"]
        )
    else:
        _require(
            status == "failed"
            and attempt == MAX_RUN_DISPATCH_ATTEMPTS
            and row["lease_owner"] is None
            and row["lease_expires_at"] is None
            and isinstance(row["last_error_code"], str)
            and bool(row["last_error_code"])
            and row["started_at"] is None
        )


def _verify_lifecycle_row(
    row: sqlite3.Row,
    *,
    current_boot_id: str | None,
    lineage_replacement: bool,
) -> None:
    _verify_dispatch_shape(row)
    _require(
        row["initial_segment_count"] == 1
        and row["segment_id"] is not None
        and row["segment_run_id"] == row["run_id"]
        and row["kind"] == "initial"
        and row["sequence"] == 0
        and row["segment_attempt"] == 1
        and _valid_timestamp(row["run_created_at"])
        and _valid_timestamp(row["segment_created_at"])
        and _valid_timestamp(row["run_updated_at"])
        and _valid_timestamp(row["segment_updated_at"])
    )
    owner_status = row["owner_status"]
    has_cause = row["observation_status"] is not None
    if owner_status is not None:
        _require(
            _valid_timestamp(row["owner_created_at"])
            and _valid_timestamp(row["owner_phase_updated_at"])
            and row["owner_phase"] in {"execution", "finalization"}
        )
    pending_state = (
        row["execution_status"] == "pending"
        and row["review_status"] == "not_required"
        and row["delivery_status"] == "pending"
        and row["state_version"] == 0
        and row["segment_status"] == "pending"
        and row["run_updated_at"] == row["run_created_at"]
        and row["segment_updated_at"] == row["segment_created_at"]
    )
    if row["dispatch_status"] in {"pending", "leased"}:
        if pending_state:
            _require(owner_status is None and not has_cause)
            return
        if owner_status is None and not lineage_replacement:
            return
        execution_terminal = row["segment_updated_at"]
        _require(
            row["execution_status"]
            in {"completed", "completed_with_fallback", "failed"}
            and row["state_version"] >= 1
            and row["segment_status"] == row["execution_status"]
            and owner_status is None
            and _valid_timestamp(execution_terminal)
            and (
                row["state_version"] > 1
                or row["run_updated_at"] == execution_terminal
            )
        )
        if row["execution_status"] == "failed":
            _require(
                row["state_version"] == 1
                and _cause_matches(
                    row,
                    terminal_state_version=1,
                    terminal_timestamp=execution_terminal,
                )
            )
        else:
            _require(not has_cause)
        return

    if row["dispatch_status"] == "failed":
        terminal = row["run_updated_at"]
        _require(
            row["execution_status"] == "failed"
            and row["review_status"] == "not_required"
            and row["delivery_status"] == "failed"
            and row["state_version"] == 1
            and row["segment_status"] == "failed"
            and owner_status is None
            and row["segment_updated_at"] == terminal
            and row["dispatch_updated_at"] == terminal
            and _cause_matches(
                row,
                terminal_state_version=1,
                terminal_timestamp=terminal,
            )
            and row["cause_phase"] == "dispatch"
            and row["cause_code"] == row["last_error_code"]
        )
        return

    _require(row["dispatch_status"] == "started")
    if row["execution_status"] == "running":
        _require(
            row["state_version"] == 1
            and row["segment_status"] == "running"
            and owner_status == "active"
            and current_boot_id is not None
            and row["owner_boot_id"] == current_boot_id
            and _valid_identifier(row["owner_id"], "owner_")
            and row["owner_closed_at"] is None
            and row["recovery_reason"] is None
            and row["owner_segment_id"] == row["segment_id"]
            and _valid_timestamp(row["owner_phase_updated_at"])
            and not has_cause
        )
        return

    if owner_status is None and not lineage_replacement:
        return
    _require(
        row["execution_status"]
        in {"completed", "completed_with_fallback", "failed"}
        and row["segment_status"] == row["execution_status"]
        and owner_status in {"closed", "interrupted"}
        and row["owner_boot_id"] is None
        and row["owner_id"] is None
        and row["owner_segment_id"] == row["segment_id"]
    )
    if owner_status == "closed":
        execution_terminal = row["segment_updated_at"]
        _require(
            row["state_version"] >= 2
            and row["recovery_reason"] is None
            and row["owner_closed_at"] == execution_terminal
            and row["owner_phase_updated_at"] == execution_terminal
            and _valid_timestamp(execution_terminal)
            and (
                row["state_version"] > 2
                or row["run_updated_at"] == execution_terminal
            )
        )
        if row["execution_status"] == "failed":
            _require(
                row["state_version"] == 2
                and _cause_matches(
                    row,
                    terminal_state_version=2,
                    terminal_timestamp=execution_terminal,
                )
            )
        else:
            _require(not has_cause)
        return

    terminal = row["run_updated_at"]
    expected_code = {
        "execution": "execution_error",
        "finalization": "run_finalization_failed",
    }.get(row["owner_phase"])
    _require(
        row["execution_status"] == "failed"
        and row["review_status"] == "not_required"
        and row["delivery_status"] == "failed"
        and row["state_version"] == 2
        and row["owner_closed_at"] == terminal
        and row["owner_phase_updated_at"] == terminal
        and row["segment_updated_at"] == terminal
        and _valid_timestamp(terminal)
        and row["recovery_reason"]
        in {"previous_boot_interrupted", "pre_v1_running_without_owner"}
        and expected_code is not None
        and _cause_matches(
            row,
            terminal_state_version=2,
            terminal_timestamp=terminal,
        )
        and row["cause_phase"] == row["owner_phase"]
        and row["cause_code"] == expected_code
    )


def _verify_exact_schema(connection: sqlite3.Connection) -> None:
    expected_sql = {
        "run_execution_boot_v1": BOOT_TABLE_SQL,
        "run_execution_owners_v1": OWNER_TABLE_SQL,
        "run_recovery_retries_v1": LINEAGE_TABLE_SQL,
    }
    for table, expected in expected_sql.items():
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        _require(
            row is not None
            and _normalized_sql(row["sql"] or "") == _normalized_sql(expected)
        )
    expected_columns = {
        "run_execution_boot_v1": (
            ("boot_scope", "TEXT", 0, None, 1),
            ("boot_id", "TEXT", 1, None, 0),
            ("activated_at", "TEXT", 1, None, 0),
        ),
        "run_execution_owners_v1": (
            ("run_id", "TEXT", 0, None, 1),
            ("segment_id", "TEXT", 1, None, 0),
            ("status", "TEXT", 1, None, 0),
            ("phase", "TEXT", 1, None, 0),
            ("boot_id", "TEXT", 0, None, 0),
            ("owner_id", "TEXT", 0, None, 0),
            ("created_at", "TEXT", 1, None, 0),
            ("phase_updated_at", "TEXT", 1, None, 0),
            ("closed_at", "TEXT", 0, None, 0),
            ("recovery_reason", "TEXT", 0, None, 0),
        ),
        "run_recovery_retries_v1": (
            ("key_hash", "TEXT", 0, None, 1),
            ("request_schema_version", "TEXT", 1, None, 0),
            ("request_hash", "TEXT", 1, None, 0),
            ("source_run_id", "TEXT", 1, None, 0),
            ("replacement_run_id", "TEXT", 1, None, 0),
            ("recovery_reason", "TEXT", 1, None, 0),
            ("interrupted_phase", "TEXT", 1, None, 0),
            ("recovery_attempt", "INTEGER", 1, None, 0),
            ("created_at", "TEXT", 1, None, 0),
        ),
    }
    for table, expected in expected_columns.items():
        actual = tuple(
            (row["name"], row["type"], row["notnull"], row["dflt_value"], row["pk"])
            for row in connection.execute(f"PRAGMA table_info({table})")
        )
        _require(actual == expected)
    expected_fks = {
        "run_execution_boot_v1": (),
        "run_execution_owners_v1": (
            ("run_segments", "segment_id", "segment_id", "NO ACTION", "CASCADE"),
            ("research_runs_v2", "run_id", "run_id", "NO ACTION", "CASCADE"),
        ),
        "run_recovery_retries_v1": (
            (
                "research_runs_v2",
                "replacement_run_id",
                "run_id",
                "NO ACTION",
                "CASCADE",
            ),
            ("research_runs_v2", "source_run_id", "run_id", "NO ACTION", "CASCADE"),
        ),
    }
    for table, expected in expected_fks.items():
        actual = tuple(
            (
                row["table"],
                row["from"],
                row["to"],
                row["on_update"],
                row["on_delete"],
            )
            for row in connection.execute(f"PRAGMA foreign_key_list({table})")
        )
        _require(actual == expected)
    index = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (_OWNER_INDEX,)
    ).fetchone()
    _require(
        index is not None
        and _normalized_sql(index["sql"] or "") == _normalized_sql(OWNER_INDEX_SQL)
    )
    _require(
        tuple(
            row["name"]
            for row in connection.execute(f"PRAGMA index_info({_OWNER_INDEX})")
        )
        == ("status", "boot_id", "created_at")
    )
    expected_unique = {
        "run_execution_boot_v1": {("boot_scope",): "pk"},
        "run_execution_owners_v1": {("run_id",): "pk", ("segment_id",): "u"},
        "run_recovery_retries_v1": {
            ("key_hash",): "pk",
            ("source_run_id",): "u",
            ("replacement_run_id",): "u",
        },
    }
    for table, expected in expected_unique.items():
        actual = {}
        for row in connection.execute(f"PRAGMA index_list({table})"):
            if row["unique"]:
                columns = tuple(
                    item["name"]
                    for item in connection.execute(f"PRAGMA index_info({row['name']})")
                )
                actual[columns] = row["origin"]
        _require(actual == expected)


def _verify_rows(connection: sqlite3.Connection) -> None:
    boots = connection.execute("SELECT * FROM run_execution_boot_v1").fetchall()
    _require(len(boots) in (0, 1))
    if boots:
        _require(
            boots[0]["boot_scope"] == "application"
            and bool(boots[0]["boot_id"])
            and _valid_timestamp(boots[0]["activated_at"])
        )
    lineage_replacement_ids = {
        row["replacement_run_id"]
        for row in connection.execute(
            "SELECT replacement_run_id FROM run_recovery_retries_v1"
        )
    }
    lifecycle = connection.execute(
        """
        SELECT dispatch.run_id, dispatch.status AS dispatch_status,
               dispatch.lease_owner, dispatch.lease_expires_at,
               dispatch.attempt_count, dispatch.last_error_code,
               dispatch.created_at AS dispatch_created_at,
               dispatch.updated_at AS dispatch_updated_at,
               dispatch.started_at,
               run.execution_status, run.review_status, run.delivery_status,
               run.state_version, run.created_at AS run_created_at,
               run.updated_at AS run_updated_at,
               segment.segment_id, segment.run_id AS segment_run_id,
               segment.kind, segment.sequence,
               segment.attempt AS segment_attempt,
               segment.status AS segment_status,
               segment.created_at AS segment_created_at,
               segment.updated_at AS segment_updated_at,
               owner.segment_id AS owner_segment_id,
               owner.status AS owner_status, owner.phase AS owner_phase,
               owner.boot_id AS owner_boot_id, owner.owner_id,
               owner.created_at AS owner_created_at,
               owner.phase_updated_at AS owner_phase_updated_at,
               owner.closed_at AS owner_closed_at, owner.recovery_reason,
               cause.observation_status, cause.terminal_state_version,
               cause.phase AS cause_phase, cause.code AS cause_code,
               cause.recorded_at,
               (
                   SELECT COUNT(*)
                   FROM run_segments AS exact_segment
                   WHERE exact_segment.run_id=run.run_id
                     AND exact_segment.kind='initial'
                     AND exact_segment.sequence=0
                     AND exact_segment.attempt=1
               ) AS initial_segment_count
        FROM run_dispatches_v1 AS dispatch
        JOIN research_runs_v2 AS run ON run.run_id=dispatch.run_id
        LEFT JOIN run_segments AS segment
          ON segment.run_id=run.run_id
         AND segment.kind='initial'
         AND segment.sequence=0
         AND segment.attempt=1
        LEFT JOIN run_execution_owners_v1 AS owner ON owner.run_id=run.run_id
        LEFT JOIN run_failure_causes_v1 AS cause ON cause.run_id=run.run_id
        """
    ).fetchall()
    current_boot_id = boots[0]["boot_id"] if boots else None
    for row in lifecycle:
        _verify_lifecycle_row(
            row,
            current_boot_id=current_boot_id,
            lineage_replacement=row["run_id"] in lineage_replacement_ids,
        )
    lifecycle_by_run = {row["run_id"]: row for row in lifecycle}
    owner_ids = {
        row["run_id"]
        for row in connection.execute("SELECT run_id FROM run_execution_owners_v1")
    }
    _require(
        owner_ids
        == {
            row["run_id"]
            for row in lifecycle
            if row["owner_status"] is not None
        }
    )
    running_ids = {
        row["run_id"]
        for row in connection.execute(
            "SELECT run_id FROM research_runs_v2 WHERE execution_status='running'"
        )
    }
    active_ids = {
        row["run_id"] for row in lifecycle if row["owner_status"] == "active"
    }
    _require(running_ids == active_ids)
    lineage = connection.execute(
        """
        SELECT retry.*, source.thread_id AS source_thread,
               source.query AS source_query, source.profile_id AS source_profile,
               source.profile_version AS source_profile_version,
               source.scope_json AS source_scope,
               replacement.thread_id AS replacement_thread,
               replacement.query AS replacement_query,
               replacement.profile_id AS replacement_profile,
               replacement.profile_version AS replacement_profile_version,
               replacement.scope_json AS replacement_scope,
               replacement.created_at AS replacement_created_at
        FROM run_recovery_retries_v1 AS retry
        JOIN research_runs_v2 AS source ON source.run_id=retry.source_run_id
        JOIN research_runs_v2 AS replacement
          ON replacement.run_id=retry.replacement_run_id
        """
    ).fetchall()
    _require(
        len(lineage)
        == connection.execute(
            "SELECT COUNT(*) FROM run_recovery_retries_v1"
        ).fetchone()[0]
    )
    _require(
        not {row["replacement_run_id"] for row in lineage}.intersection(
            row["source_run_id"] for row in lineage
        )
    )
    owner_by_run = {
        row["run_id"]: row
        for row in lifecycle
        if row["owner_status"] is not None
    }
    for row in lineage:
        _require(
            row["request_schema_version"] == RUN_RECOVERY_REQUEST_SCHEMA_VERSION
            and row["recovery_attempt"] == 1
            and _valid_timestamp(row["created_at"])
            and row["source_thread"] == row["replacement_thread"]
            and row["source_query"] == row["replacement_query"]
            and row["source_profile"] == row["replacement_profile"]
            and row["source_profile_version"] == row["replacement_profile_version"]
            and row["source_scope"] == row["replacement_scope"]
            and row["source_run_id"] in owner_by_run
        )
        source = owner_by_run[row["source_run_id"]]
        replacement_segments = connection.execute(
            "SELECT * FROM run_segments WHERE run_id=?",
            (row["replacement_run_id"],),
        ).fetchall()
        replacement_dispatches = connection.execute(
            "SELECT * FROM run_dispatches_v1 WHERE run_id=?",
            (row["replacement_run_id"],),
        ).fetchall()
        _require(len(replacement_segments) == 1 and len(replacement_dispatches) == 1)
        replacement_segment = replacement_segments[0]
        replacement_dispatch = replacement_dispatches[0]
        _require(
            row["replacement_run_id"] in lifecycle_by_run
            and replacement_segment["segment_id"]
            == f"{row['replacement_run_id']}_seg_000"
            and replacement_segment["kind"] == "initial"
            and replacement_segment["sequence"] == 0
            and replacement_segment["attempt"] == 1
            and replacement_segment["created_at"] == row["replacement_created_at"]
            and replacement_dispatch["created_at"] == row["replacement_created_at"]
        )
        try:
            scope = json.loads(row["source_scope"])
        except (TypeError, ValueError) as exc:
            raise RunExecutionConflict(
                "run_execution_recovery_unavailable"
            ) from exc
        expected_hash = run_recovery_request_hash(
            source_run_id=row["source_run_id"],
            segment_id=source["segment_id"],
            query=row["source_query"],
            thread_id=row["source_thread"],
            profile_id=row["source_profile"],
            profile_version=row["source_profile_version"],
            scope=scope,
            execution_status="failed",
            review_status="not_required",
            delivery_status="failed",
            terminal_state_version=2,
            failure_phase=source["cause_phase"],
            failure_code=source["cause_code"],
            recovery_reason=source["recovery_reason"],
            interrupted_phase=source["owner_phase"],
            recovery_attempt=1,
        )
        _require(
            row["request_hash"] == expected_hash
            and row["recovery_reason"] == source["recovery_reason"]
            and row["interrupted_phase"] == source["owner_phase"]
        )


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
    _verify_exact_schema(connection)
    _require(connection.execute("PRAGMA foreign_key_check").fetchone() is None)
    _verify_rows(connection)
    boot_rows = connection.execute(
        "SELECT COUNT(*) AS count FROM run_execution_boot_v1"
    ).fetchone()["count"]
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
    _run_migration_step(
        "boot table creation", lambda: connection.execute(BOOT_TABLE_SQL)
    )
    _run_migration_step(
        "owner table creation", lambda: connection.execute(OWNER_TABLE_SQL)
    )
    _run_migration_step(
        "lineage table creation", lambda: connection.execute(LINEAGE_TABLE_SQL)
    )
    _run_migration_step(
        "owner index creation", lambda: connection.execute(OWNER_INDEX_SQL)
    )
    observed_at = _now()
    running = connection.execute(
        "SELECT * FROM research_runs_v2 WHERE execution_status='running'"
    ).fetchall()
    for run in running:
        segment = _run_migration_step(
            "running-row validation",
            lambda run=run: _validate_running_source(connection, run),
        )
        _run_migration_step(
            "owner insert",
            lambda run=run, segment=segment: connection.execute(
                """
                INSERT INTO run_execution_owners_v1 (
                    run_id, segment_id, status, phase, boot_id, owner_id,
                    created_at, phase_updated_at, closed_at, recovery_reason
                ) VALUES (?, ?, 'interrupted', 'execution', NULL, NULL, ?, ?, ?,
                          'pre_v1_running_without_owner')
                """,
                (
                    run["run_id"],
                    segment["segment_id"],
                    observed_at,
                    observed_at,
                    observed_at,
                ),
            ),
        )
        updated = _run_migration_step(
            "run update",
            lambda run=run: connection.execute(
                """
                UPDATE research_runs_v2
                SET execution_status='failed', review_status='not_required',
                    delivery_status='failed', state_version=2, updated_at=?
                WHERE run_id=? AND execution_status='running'
                  AND review_status='not_required' AND delivery_status='pending'
                  AND state_version=1
                """,
                (observed_at, run["run_id"]),
            ),
        )
        segment_updated = _run_migration_step(
            "segment update",
            lambda segment=segment: connection.execute(
                "UPDATE run_segments SET status='failed', updated_at=? WHERE segment_id=? AND status='running'",
                (observed_at, segment["segment_id"]),
            ),
        )
        if updated.rowcount != 1 or segment_updated.rowcount != 1:
            raise RunExecutionConflict("run_execution_recovery_unavailable")
        _run_migration_step(
            "failure-cause insert",
            lambda run=run: connection.execute(
                """
                INSERT INTO run_failure_causes_v1 (
                    run_id, observation_status, terminal_state_version,
                    phase, code, recorded_at
                ) VALUES (?, 'observed', 2, 'execution', 'execution_error', ?)
                """,
                (run["run_id"], observed_at),
            ),
        )
    _run_migration_step(
        "marker insert",
        lambda: connection.execute(
            "INSERT INTO schema_migrations(version, applied_at, checksum) VALUES (?, ?, ?)",
            (
                RUN_EXECUTION_RECOVERY_MIGRATION_VERSION,
                observed_at,
                RUN_EXECUTION_RECOVERY_MIGRATION_CHECKSUM,
            ),
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
            return _run_migration_step(
                "post-commit verification",
                lambda: verify_run_execution_recovery_schema(db_path=canonical),
            )
        except Exception as exc:
            if connection is not None:
                connection.rollback()
                connection.close()
            restore_database(backup_path=str(backup_path), db_path=canonical)
            raise _bounded(exc) from exc
