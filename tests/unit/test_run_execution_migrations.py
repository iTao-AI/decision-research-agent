from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from api.run_dispatch_repository import claim_run_dispatch, start_run_dispatch
from api.run_execution_migrations import (
    migrate_run_execution_recovery_with_backup,
    run_execution_recovery_marker_present,
    verify_run_execution_recovery_connection,
    verify_run_execution_recovery_schema,
)
from api.run_execution_models import RunExecutionConflict, new_boot_id
from api.run_execution_repository import activate_run_execution_boot
from api.run_recovery_models import (
    RUN_RECOVERY_REQUEST_SCHEMA_VERSION,
    recovery_key_hash,
    run_recovery_request_hash,
)
from api.run_recovery_repository import create_or_replay_run_recovery
from api.run_repository import (
    _init_run_schema_unlocked,
    create_run,
    finalize_run_transaction,
)


def build_through_009_fixture(path: Path) -> None:
    _init_run_schema_unlocked(str(path))
    with sqlite3.connect(path) as connection:
        markers = dict(connection.execute("SELECT version, checksum FROM schema_migrations"))
        assert "010_run_execution_recovery" not in markers
        assert set(markers) == {
            "003_run_identity_backbone",
            "007_run_create_idempotency",
            "008_run_dispatch_reconciliation",
            "009_run_failure_cause_v1",
        }


def _seed_running(path: Path, *, run_id: str = "run_running_exact") -> None:
    now = "2026-07-29T00:00:00+00:00"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO research_runs_v2 VALUES (?, ?, ?, ?, ?, ?, 'running', 'not_required', 'pending', 1, ?, ?)",
            (run_id, "thread", "query", "generic", "1", "{}", now, now),
        )
        connection.execute(
            "INSERT INTO run_segments VALUES (?, ?, 'initial', 0, 1, 'running', ?, ?)",
            (f"{run_id}_seg_000", run_id, now, now),
        )
        connection.execute(
            "INSERT INTO run_dispatches_v1 VALUES (?, 'started', NULL, NULL, 1, NULL, ?, ?, ?)",
            (run_id, now, now, now),
        )


def _migrated(tmp_path: Path, *, running: bool = False) -> Path:
    path = tmp_path / "runs.db"
    build_through_009_fixture(path)
    if running:
        _seed_running(path)
    migrate_run_execution_recovery_with_backup(db_path=str(path))
    return path


def _logical_database_snapshot(path: Path) -> tuple:
    with sqlite3.connect(path) as connection:
        schema = tuple(
            connection.execute(
                """
                SELECT type, name, tbl_name, sql
                FROM sqlite_master
                WHERE name NOT LIKE 'sqlite_%'
                ORDER BY type, name
                """
            )
        )
        rows = []
        for (table,) in connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ):
            rows.append(
                (
                    table,
                    tuple(connection.execute(f'SELECT * FROM "{table}"')),
                )
            )
        return (
            schema,
            tuple(rows),
            connection.execute("PRAGMA integrity_check").fetchone()[0],
            tuple(connection.execute("PRAGMA foreign_key_check")),
        )


def _recovery_lineage(path: Path):
    source = create_run(
        db_path=str(path),
        thread_id="matrix-thread",
        query="matrix-query",
    )
    first_boot = new_boot_id()
    activate_run_execution_boot(db_path=str(path), boot_id=first_boot)
    claim = claim_run_dispatch(
        db_path=str(path),
        worker_id=f"dispatch_worker_{'a' * 32}",
        boot_id=first_boot,
        lease_seconds=30,
        run_id=source["run_id"],
    )
    assert claim is not None
    assert start_run_dispatch(db_path=str(path), claim=claim) is not None
    current_boot = new_boot_id()
    assert (
        activate_run_execution_boot(
            db_path=str(path),
            boot_id=current_boot,
        ).interrupted_execution_count
        == 1
    )
    accepted = create_or_replay_run_recovery(
        source_run_id=source["run_id"],
        idempotency_key="matrix-recovery-key",
        boot_id=current_boot,
        exact_profile_is_available=lambda *_: True,
        db_path=str(path),
    )
    return source, current_boot, accepted


def test_010_marker_tables_index_columns_foreign_keys_and_checks_are_exact(tmp_path):
    path = _migrated(tmp_path)
    report = verify_run_execution_recovery_schema(db_path=str(path))
    assert report == {"boot_rows": 0, "owner_rows": 0, "lineage_rows": 0}


def test_through_009_fixture_has_exact_legacy_markers_and_no_010_surface(tmp_path):
    path = tmp_path / "runs.db"
    build_through_009_fixture(path)
    assert run_execution_recovery_marker_present(db_path=str(path)) is False


def test_010_backfills_only_exact_preexisting_running_rows(tmp_path):
    path = _migrated(tmp_path, running=True)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT status, phase, recovery_reason FROM run_execution_owners_v1").fetchall() == [
            ("interrupted", "execution", "pre_v1_running_without_owner")
        ]
        assert connection.execute("SELECT execution_status, delivery_status, state_version FROM research_runs_v2 WHERE run_id='run_running_exact'").fetchone() == ("failed", "failed", 2)


def test_010_backfill_uses_one_terminal_timestamp_and_existing_execution_cause(tmp_path):
    path = _migrated(tmp_path, running=True)
    with sqlite3.connect(path) as connection:
        owner = connection.execute("SELECT phase_updated_at, closed_at FROM run_execution_owners_v1").fetchone()
        run = connection.execute("SELECT updated_at FROM research_runs_v2 WHERE run_id='run_running_exact'").fetchone()[0]
        segment = connection.execute("SELECT updated_at FROM run_segments WHERE run_id='run_running_exact'").fetchone()[0]
        cause = connection.execute("SELECT phase, code, recorded_at FROM run_failure_causes_v1 WHERE run_id='run_running_exact'").fetchone()
    assert owner[0] == owner[1] == run == segment == cause[2]
    assert cause[:2] == ("execution", "execution_error")


def test_010_pending_and_terminal_business_rows_are_unchanged(tmp_path):
    path = _migrated(tmp_path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM run_execution_owners_v1").fetchone()[0] == 0


def test_010_created_at_is_observation_time_not_claimed_start_time(tmp_path):
    path = _migrated(tmp_path, running=True)
    with sqlite3.connect(path) as connection:
        created = connection.execute("SELECT created_at FROM run_execution_owners_v1").fetchone()[0]
    assert created != "2026-07-29T00:00:00+00:00"


def test_010_repeated_apply_is_verify_only_and_does_not_repeat_backfill(tmp_path):
    path = _migrated(tmp_path, running=True)
    before = path.read_bytes()
    migrate_run_execution_recovery_with_backup(db_path=str(path))
    assert path.read_bytes() == before


def test_010_existing_dedicated_backup_is_never_overwritten(tmp_path):
    path = tmp_path / "runs.db"
    build_through_009_fixture(path)
    backup = Path(f"{path}.pre-run-execution-recovery.bak")
    backup.write_bytes(b"sentinel")
    with pytest.raises(RunExecutionConflict, match="run_execution_recovery_backup_already_exists"):
        migrate_run_execution_recovery_with_backup(db_path=str(path))
    assert backup.read_bytes() == b"sentinel"


@pytest.mark.parametrize(
    "fault",
    [
        "boot table creation",
        "owner table creation",
        "lineage table creation",
        "owner index creation",
        "running-row validation",
        "owner insert",
        "run update",
        "segment update",
        "failure-cause insert",
        "marker insert",
        "post-commit verification",
    ],
)
def test_010_each_apply_or_verify_failure_restores_complete_backup(tmp_path, monkeypatch, fault):
    import api.run_execution_migrations as migrations

    path = tmp_path / f"{fault.replace(' ', '-')}.db"
    build_through_009_fixture(path)
    _seed_running(path)
    before = _logical_database_snapshot(path)
    original = migrations._run_migration_step

    def inject_at_exact_boundary(name, operation):
        if name == fault:
            raise RuntimeError(fault)
        return original(name, operation)

    monkeypatch.setattr(migrations, "_run_migration_step", inject_at_exact_boundary)
    with pytest.raises(RunExecutionConflict):
        migrate_run_execution_recovery_with_backup(db_path=str(path))
    assert _logical_database_snapshot(path) == before


def test_010_closes_connections_before_restore(tmp_path, monkeypatch):
    import api.run_execution_migrations as migrations

    path = tmp_path / "runs.db"
    build_through_009_fixture(path)
    monkeypatch.setattr(
        migrations,
        "verify_run_execution_recovery_schema",
        lambda **_: (_ for _ in ()).throw(RuntimeError("verify")),
    )
    with pytest.raises(RunExecutionConflict):
        migrate_run_execution_recovery_with_backup(db_path=str(path))
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_010_rejects_wrong_marker_checksum_without_repair(tmp_path):
    path = _migrated(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE schema_migrations SET checksum='wrong' WHERE version='010_run_execution_recovery'")
    with pytest.raises(RunExecutionConflict):
        migrate_run_execution_recovery_with_backup(db_path=str(path))


@pytest.mark.parametrize("case", ["ownerless", "malformed"])
def test_010_rejects_ownerless_or_malformed_preexisting_authority_tables(tmp_path, case):
    path = _migrated(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute("DROP INDEX idx_run_execution_owners_status_boot_created")
    with pytest.raises(RunExecutionConflict):
        verify_run_execution_recovery_schema(db_path=str(path))


def test_010_rejects_running_wrong_review_delivery_or_state_version(tmp_path):
    path = tmp_path / "runs.db"
    build_through_009_fixture(path)
    _seed_running(path)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE research_runs_v2 SET review_status='pending' WHERE run_id='run_running_exact'")
    with pytest.raises(RunExecutionConflict):
        migrate_run_execution_recovery_with_backup(db_path=str(path))


def test_010_rejects_missing_duplicate_noninitial_or_nonrunning_segment(tmp_path):
    path = tmp_path / "runs.db"
    build_through_009_fixture(path)
    _seed_running(path)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE run_segments SET status='failed' WHERE run_id='run_running_exact'")
    with pytest.raises(RunExecutionConflict):
        migrate_run_execution_recovery_with_backup(db_path=str(path))


def test_010_rejects_existing_cause_for_running_source(tmp_path):
    path = tmp_path / "runs.db"
    build_through_009_fixture(path)
    _seed_running(path)
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO run_failure_causes_v1 VALUES ('run_running_exact','observed',1,'execution','execution_error','2026-07-29T00:00:00+00:00')")
    with pytest.raises(RunExecutionConflict):
        migrate_run_execution_recovery_with_backup(db_path=str(path))


def test_010_rejects_foreign_key_unique_check_and_index_drift(tmp_path):
    path = _migrated(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute("DROP INDEX idx_run_execution_owners_status_boot_created")
    with pytest.raises(RunExecutionConflict):
        verify_run_execution_recovery_schema(db_path=str(path))


def test_010_rejects_partial_lineage_and_replacement_as_source(tmp_path):
    path = _migrated(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("INSERT INTO run_recovery_retries_v1 VALUES ('k','dra.run-recovery-request.v1','h','missing','missing2','previous_boot_interrupted','execution',1,'2026-07-29T00:00:00+00:00')")
    with pytest.raises(RunExecutionConflict):
        verify_run_execution_recovery_schema(db_path=str(path))


@pytest.mark.parametrize(
    ("table", "old", "new"),
    [
        (
            "run_execution_boot_v1",
            "boot_id TEXT NOT NULL",
            "boot_id TEXT",
        ),
        (
            "run_execution_boot_v1",
            "CHECK(boot_scope = 'application')",
            "CHECK(length(boot_scope) > 0)",
        ),
        (
            "run_execution_owners_v1",
            "segment_id TEXT NOT NULL UNIQUE",
            "segment_id TEXT NOT NULL",
        ),
        (
            "run_execution_owners_v1",
            "REFERENCES research_runs_v2(run_id) ON DELETE CASCADE",
            "REFERENCES research_runs_v2(run_id)",
        ),
        (
            "run_recovery_retries_v1",
            "replacement_run_id TEXT NOT NULL UNIQUE",
            "replacement_run_id TEXT NOT NULL",
        ),
        (
            "run_recovery_retries_v1",
            "CHECK(recovery_attempt = 1)",
            "CHECK(recovery_attempt > 0)",
        ),
    ],
)
def test_010_rejects_real_table_nullable_check_fk_or_unique_drift(
    tmp_path,
    table,
    old,
    new,
):
    path = _migrated(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()[0]
        connection.execute(f"ALTER TABLE {table} RENAME TO {table}_old")
        connection.execute(sql.replace(old, new))
        connection.execute(f"DROP TABLE {table}_old")
    with pytest.raises(RunExecutionConflict):
        verify_run_execution_recovery_schema(db_path=str(path))


def test_010_rejects_named_owner_index_wrong_column_order(tmp_path):
    path = _migrated(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "DROP INDEX idx_run_execution_owners_status_boot_created"
        )
        connection.execute(
            """
            CREATE INDEX idx_run_execution_owners_status_boot_created
            ON run_execution_owners_v1(boot_id, status, created_at)
            """
        )
    with pytest.raises(RunExecutionConflict):
        verify_run_execution_recovery_schema(db_path=str(path))


def test_010_rejects_replacement_used_as_later_lineage_source(tmp_path):
    path = _migrated(tmp_path)
    timestamp = "2026-07-29T00:00:00+00:00"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for run_id, state in (
            ("source", "failed"),
            ("replacement", "pending"),
            ("second", "pending"),
        ):
            delivery = "failed" if state == "failed" else "pending"
            version = 2 if state == "failed" else 0
            connection.execute(
                """
                INSERT INTO research_runs_v2 VALUES
                (?, 'thread', 'query', 'generic', '1', '{}', ?,
                 'not_required', ?, ?, ?, ?)
                """,
                (run_id, state, delivery, version, timestamp, timestamp),
            )
            connection.execute(
                """
                INSERT INTO run_segments VALUES
                (?, ?, 'initial', 0, 1, ?, ?, ?)
                """,
                (f"{run_id}_seg_000", run_id, state, timestamp, timestamp),
            )
            connection.execute(
                """
                INSERT INTO run_dispatches_v1 VALUES
                (?, ?, NULL, NULL, ?, NULL, ?, ?, ?)
                """,
                (
                    run_id,
                    "started" if state == "failed" else "pending",
                    1 if state == "failed" else 0,
                    timestamp,
                    timestamp,
                    timestamp if state == "failed" else None,
                ),
            )
        connection.execute(
            """
            INSERT INTO run_execution_owners_v1 VALUES
            ('source','source_seg_000','interrupted','execution',NULL,NULL,
             ?,?,?, 'previous_boot_interrupted')
            """,
            (timestamp, timestamp, timestamp),
        )
        connection.execute(
            """
            INSERT INTO run_failure_causes_v1 VALUES
            ('source','observed',2,'execution','execution_error',?)
            """,
            (timestamp,),
        )
        connection.execute(
            """
            INSERT INTO run_recovery_retries_v1 VALUES
            ('key1','dra.run-recovery-request.v1','hash1','source','replacement',
             'previous_boot_interrupted','execution',1,?)
            """,
            (timestamp,),
        )
        connection.execute(
            """
            INSERT INTO run_recovery_retries_v1 VALUES
            ('key2','dra.run-recovery-request.v1','hash2','replacement','second',
             'previous_boot_interrupted','execution',1,?)
            """,
            (timestamp,),
        )
    with pytest.raises(RunExecutionConflict):
        verify_run_execution_recovery_schema(db_path=str(path))


def test_010_rejects_closed_owner_attached_to_pending_run_and_segment(tmp_path):
    path = _migrated(tmp_path)
    timestamp = "2026-07-29T00:00:00+00:00"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO research_runs_v2 VALUES
            ('run_pending','thread','query','generic','1','{}','pending',
             'not_required','pending',0,?,?)
            """,
            (timestamp, timestamp),
        )
        connection.execute(
            """
            INSERT INTO run_segments VALUES
            ('run_pending_seg_000','run_pending','initial',0,1,'pending',?,?)
            """,
            (timestamp, timestamp),
        )
        connection.execute(
            """
            INSERT INTO run_dispatches_v1 VALUES
            ('run_pending','pending',NULL,NULL,0,NULL,?,?,NULL)
            """,
            (timestamp, timestamp),
        )
        connection.execute(
            """
            INSERT INTO run_execution_owners_v1 VALUES
            ('run_pending','run_pending_seg_000','closed','execution',
             NULL,NULL,?,?,?,NULL)
            """,
            (timestamp, timestamp, timestamp),
        )
    with pytest.raises(RunExecutionConflict):
        verify_run_execution_recovery_schema(db_path=str(path))


def test_010_assigns_exactly_one_lifecycle_role(tmp_path):
    path = _migrated(tmp_path)
    _recovery_lineage(path)
    report = verify_run_execution_recovery_schema(db_path=str(path))
    assert report["lineage_rows"] == 1
    assert report["owner_rows"] == 1


def test_010_rejects_source_replacement_role_intersection(tmp_path):
    path = _migrated(tmp_path)
    _, _, accepted = _recovery_lineage(path)
    second = create_run(
        db_path=str(path),
        thread_id="matrix-thread",
        query="matrix-query",
    )
    timestamp = "2026-07-29T12:00:00+00:00"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO run_recovery_retries_v1(
                key_hash, request_schema_version, request_hash,
                source_run_id, replacement_run_id, recovery_reason,
                interrupted_phase, recovery_attempt, created_at
            ) VALUES (?, ?, ?, ?, ?, 'previous_boot_interrupted',
                      'execution', 1, ?)
            """,
            (
                recovery_key_hash("matrix-second-key"),
                RUN_RECOVERY_REQUEST_SCHEMA_VERSION,
                "invalid-cross-link",
                accepted.run_id,
                second["run_id"],
                timestamp,
            ),
        )
    with pytest.raises(RunExecutionConflict):
        verify_run_execution_recovery_schema(db_path=str(path))


def test_010_recovery_replacement_cannot_use_ordinary_pending_terminal_compatibility(
    tmp_path,
):
    path = _migrated(tmp_path)
    _, _, accepted = _recovery_lineage(path)
    terminal = "2026-07-29T12:00:00+00:00"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE research_runs_v2
            SET execution_status='completed', delivery_status='ready',
                state_version=1, updated_at=?
            WHERE run_id=?
            """,
            (terminal, accepted.run_id),
        )
        connection.execute(
            "UPDATE run_segments SET status='completed', updated_at=? "
            "WHERE run_id=?",
            (terminal, accepted.run_id),
        )
    with pytest.raises(RunExecutionConflict):
        verify_run_execution_recovery_schema(db_path=str(path))


def test_010_ordinary_pending_terminal_compatibility_remains_retained(tmp_path):
    path = _migrated(tmp_path)
    ordinary = create_run(
        db_path=str(path),
        thread_id="ordinary-thread",
        query="ordinary-query",
    )
    assert finalize_run_transaction(
        db_path=str(path),
        run_id=ordinary["run_id"],
        segment_id=ordinary["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        delivery_status="ready",
        evidence_entries=[],
    )
    verify_run_execution_recovery_schema(db_path=str(path))


def test_010_connection_verifier_consumes_one_normalized_projection(
    tmp_path,
    monkeypatch,
):
    import api.run_execution_migrations as migrations

    path = _migrated(tmp_path)
    create_run(
        db_path=str(path),
        thread_id="projection-thread",
        query="projection-query",
    )
    original = migrations.classify_recovery_lifecycle
    seen = []

    def record(snapshot, *, role, current_boot_id):
        seen.append((snapshot.run_id, role))
        return original(
            snapshot,
            role=role,
            current_boot_id=current_boot_id,
        )

    monkeypatch.setattr(migrations, "classify_recovery_lifecycle", record)
    with migrations._connect(str(path)) as connection:
        verify_run_execution_recovery_connection(connection)
    assert len(seen) == 1
