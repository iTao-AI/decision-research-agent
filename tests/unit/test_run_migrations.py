import sqlite3
from pathlib import Path

import pytest

from tests.legacy_db import init_legacy_db
from api.run_migrations import (
    backup_database,
    migrate_with_backup,
    restore_database,
    verify_run_schema,
)
from api.review_repository import init_review_schema


RUN_FAILURE_CAUSE_MIGRATION_VERSION = "009_run_failure_cause_v1"
RUN_FAILURE_CAUSE_MIGRATION_CHECKSUM = "run-failure-cause-v1"
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


def _database_dump(db_path):
    connection = sqlite3.connect(db_path)
    try:
        return "\n".join(connection.iterdump())
    finally:
        connection.close()


def _failure_backup_path(db_path):
    return Path(f"{db_path}.pre-run-failure-cause.bak")


def _remove_failure_cause_migration(db_path):
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute("DROP TABLE IF EXISTS run_failure_causes_v1")
            has_markers = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'schema_migrations'
                """
            ).fetchone()
            if has_markers is not None:
                connection.execute(
                    "DELETE FROM schema_migrations WHERE version = ?",
                    (RUN_FAILURE_CAUSE_MIGRATION_VERSION,),
                )
    finally:
        connection.close()
    _failure_backup_path(db_path).unlink(missing_ok=True)


def _seed_pre_009_runs(db_path, *, statuses=()):
    init_legacy_db(db_path).close()
    migrate_with_backup(
        db_path=db_path,
        backup_path=f"{db_path}.pre-seed-chain.bak",
    )
    _remove_failure_cause_migration(db_path)

    connection = sqlite3.connect(db_path)
    try:
        with connection:
            for index, status in enumerate(statuses):
                run_id = f"run_{status}_{index}"
                now = f"2026-07-15T00:00:0{index}+00:00"
                state_version = 3 if status == "failed" else 0
                delivery_status = (
                    "ready"
                    if status in {"completed", "completed_with_fallback"}
                    else "failed"
                    if status == "failed"
                    else "pending"
                )
                connection.execute(
                    """
                    INSERT INTO research_runs_v2 (
                        run_id, thread_id, query, profile_id, profile_version,
                        scope_json, execution_status, review_status,
                        delivery_status, state_version, created_at, updated_at
                    ) VALUES (?, ?, ?, 'generic', '1', '{}', ?,
                              'not_required', ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        f"thread-{index}",
                        f"query-{index}",
                        status,
                        delivery_status,
                        state_version,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO run_segments (
                        segment_id, run_id, kind, sequence, attempt, status,
                        created_at, updated_at
                    ) VALUES (?, ?, 'initial', 0, 1, ?, ?, ?)
                    """,
                    (f"{run_id}_seg_000", run_id, status, now, now),
                )
    finally:
        connection.close()


def _apply_009(db_path):
    return migrate_with_backup(
        db_path=db_path,
        backup_path=f"{db_path}.pre-run-dispatch.bak",
    )


def _replace_failure_cause_table(db_path, table_sql):
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        with connection:
            connection.execute("DROP TABLE run_failure_causes_v1")
            connection.execute(table_sql)
        connection.execute("PRAGMA foreign_keys=ON")
    finally:
        connection.close()


def _normalized_sql(value):
    return " ".join((value or "").split()).lower()


def _seed_observed_failure(db_path):
    _seed_pre_009_runs(db_path, statuses=("failed",))
    _apply_009(db_path)
    run_id = "run_failed_0"
    recorded_at = "2026-07-15T00:00:00+00:00"
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE research_runs_v2
                SET state_version = 3, execution_status = 'failed', updated_at = ?
                WHERE run_id = ?
                """,
                (recorded_at, run_id),
            )
            connection.execute(
                """
                UPDATE run_segments
                SET status = 'failed', updated_at = ?
                WHERE run_id = ?
                """,
                (recorded_at, run_id),
            )
            connection.execute(
                """
                UPDATE run_failure_causes_v1
                SET observation_status = 'observed',
                    terminal_state_version = 3,
                    phase = 'execution',
                    code = 'execution_error',
                    recorded_at = ?
                WHERE run_id = ?
                """,
                (recorded_at, run_id),
            )
    finally:
        connection.close()
    return run_id


def _table_names(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        conn.close()


def test_run_identity_migration_applies_twice_and_verifies(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    init_legacy_db(db_path).close()

    init_review_schema(db_path)
    init_review_schema(db_path)
    result = verify_run_schema(db_path=db_path)

    assert result["migration_version"] == "003_run_identity_backbone"
    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM schema_migrations "
            "WHERE version = '003_run_identity_backbone'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 1


def test_backup_and_restore_recovers_pre_migration_database(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    backup_path = str(tmp_path / "tasks.pre-run-identity.db")
    init_legacy_db(db_path).close()
    original_tables = _table_names(db_path)

    backup_database(db_path=db_path, backup_path=backup_path)
    init_review_schema(db_path)
    assert "research_runs_v2" in _table_names(db_path)

    restore_database(backup_path=backup_path, db_path=db_path)
    assert _table_names(db_path) == original_tables


def test_migration_verification_failure_restores_backup(tmp_path, monkeypatch):
    import api.run_migrations as migrations

    db_path = str(tmp_path / "tasks.db")
    backup_path = str(tmp_path / "tasks.pre-run-identity.db")
    init_legacy_db(db_path).close()
    original_tables = _table_names(db_path)

    def fail_verification(
        *,
        db_path,
        include_evidence_verification=False,
        include_publication=False,
    ):
        raise RuntimeError("verification failed")

    monkeypatch.setattr(migrations, "verify_run_schema", fail_verification)
    with pytest.raises(RuntimeError, match="verification failed"):
        migrate_with_backup(db_path=db_path, backup_path=backup_path)

    assert _table_names(db_path) == original_tables


def test_full_migration_includes_revisioned_publication_schema(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    backup_path = str(tmp_path / "tasks.pre-publication.db")
    init_legacy_db(db_path).close()

    result = migrate_with_backup(
        db_path=db_path,
        backup_path=backup_path,
    )

    assert "006_revisioned_publication" in result["migration_versions"]
    assert "run_publications_v2" in result["tables"]


def test_restart_verification_failure_preserves_migrated_db_and_backup(
    tmp_path,
    monkeypatch,
):
    import api.run_migrations as migrations

    db_path = str(tmp_path / "tasks.db")
    backup_path = str(tmp_path / "tasks.pre-publication.db")
    init_legacy_db(db_path).close()
    migrate_with_backup(db_path=db_path, backup_path=backup_path)
    backup_tables = _table_names(backup_path)

    monkeypatch.setattr(
        migrations,
        "verify_run_schema",
        lambda **_: (_ for _ in ()).throw(RuntimeError("verification failed")),
    )
    with pytest.raises(RuntimeError, match="verification failed"):
        migrate_with_backup(db_path=db_path, backup_path=backup_path)

    assert "run_publications_v2" in _table_names(db_path)
    assert _table_names(backup_path) == backup_tables


def _remove_idempotency_migration(db_path):
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute("DROP TABLE run_create_idempotency_v1")
            connection.execute(
                "DELETE FROM schema_migrations WHERE version = '007_run_create_idempotency'"
            )
    finally:
        connection.close()


def test_full_migration_includes_run_create_idempotency_schema(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    backup_path = str(tmp_path / "tasks.pre-idempotency.db")
    init_legacy_db(db_path).close()
    result = migrate_with_backup(db_path=db_path, backup_path=backup_path)
    assert "007_run_create_idempotency" in result["migration_versions"]
    assert "run_create_idempotency_v1" in result["tables"]
    connection = sqlite3.connect(db_path)
    try:
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(run_create_idempotency_v1)"
        ).fetchall()
    finally:
        connection.close()
    assert any(
        row[2] == "research_runs_v2"
        and row[3] == "run_id"
        and row[4] == "run_id"
        and row[6].upper() == "CASCADE"
        for row in foreign_keys
    )


def test_existing_publication_database_gets_new_backup_and_007(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    first_backup = str(tmp_path / "tasks.pre-publication.db")
    init_legacy_db(db_path).close()
    migrate_with_backup(db_path=db_path, backup_path=first_backup)
    _remove_idempotency_migration(db_path)
    second_backup = str(tmp_path / "tasks.pre-idempotency.db")
    result = migrate_with_backup(db_path=db_path, backup_path=second_backup)
    assert "007_run_create_idempotency" in result["migration_versions"]
    assert Path(second_backup).exists()


def test_007_failure_restores_existing_publication_database(tmp_path, monkeypatch):
    import api.run_migrations as migrations

    db_path = str(tmp_path / "tasks.db")
    init_legacy_db(db_path).close()
    migrate_with_backup(
        db_path=db_path,
        backup_path=str(tmp_path / "tasks.pre-publication.db"),
    )
    _remove_idempotency_migration(db_path)
    connection = sqlite3.connect(db_path)
    try:
        before_sql = "\n".join(connection.iterdump())
    finally:
        connection.close()
    original = migrations.init_run_schema

    def apply_then_fail(path):
        original(path)
        raise RuntimeError("idempotency migration failed")

    monkeypatch.setattr(migrations, "init_run_schema", apply_then_fail)
    with pytest.raises(RuntimeError, match="idempotency migration failed"):
        migrate_with_backup(
            db_path=db_path,
            backup_path=str(tmp_path / "tasks.pre-idempotency.db"),
        )
    connection = sqlite3.connect(db_path)
    try:
        after_sql = "\n".join(connection.iterdump())
    finally:
        connection.close()
    assert after_sql == before_sql


def test_existing_backup_is_not_overwritten_for_007_upgrade(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    init_legacy_db(db_path).close()
    migrate_with_backup(
        db_path=db_path,
        backup_path=str(tmp_path / "tasks.pre-publication.db"),
    )
    _remove_idempotency_migration(db_path)
    backup_path = tmp_path / "tasks.pre-idempotency.db"
    backup_path.write_bytes(b"keep")
    with pytest.raises(RuntimeError, match="run_idempotency_migration_backup_already_exists"):
        migrate_with_backup(db_path=db_path, backup_path=str(backup_path))
    assert backup_path.read_bytes() == b"keep"


def _replace_idempotency_table_without_constraint(
    db_path,
    *,
    key_hash_definition,
    run_id_definition,
):
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute("PRAGMA foreign_keys=OFF")
            connection.execute("DROP TABLE run_create_idempotency_v1")
            connection.execute(
                f"""
                CREATE TABLE run_create_idempotency_v1 (
                    key_hash {key_hash_definition},
                    request_schema_version TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    run_id {run_id_definition}
                        REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL
                )
                """
            )
    finally:
        connection.close()


def test_verifier_rejects_idempotency_table_without_key_hash_primary_key(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    init_legacy_db(db_path).close()
    migrate_with_backup(
        db_path=db_path,
        backup_path=str(tmp_path / "backup.db"),
    )
    _replace_idempotency_table_without_constraint(
        db_path,
        key_hash_definition="TEXT NOT NULL",
        run_id_definition="TEXT NOT NULL UNIQUE",
    )

    with pytest.raises(
        RuntimeError,
        match="missing_constraints=.*key_hash_primary_key",
    ):
        verify_run_schema(
            db_path=db_path,
            include_evidence_verification=True,
            include_publication=True,
        )


def test_verifier_rejects_idempotency_table_without_unique_run_id(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    init_legacy_db(db_path).close()
    migrate_with_backup(
        db_path=db_path,
        backup_path=str(tmp_path / "backup.db"),
    )
    _replace_idempotency_table_without_constraint(
        db_path,
        key_hash_definition="TEXT PRIMARY KEY",
        run_id_definition="TEXT NOT NULL",
    )

    with pytest.raises(
        RuntimeError,
        match="missing_constraints=.*run_id_unique",
    ):
        verify_run_schema(
            db_path=db_path,
            include_evidence_verification=True,
            include_publication=True,
        )


def test_verifier_rejects_partial_unique_run_id_index(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    init_legacy_db(db_path).close()
    migrate_with_backup(
        db_path=db_path,
        backup_path=str(tmp_path / "backup.db"),
    )
    _replace_idempotency_table_without_constraint(
        db_path,
        key_hash_definition="TEXT PRIMARY KEY",
        run_id_definition="TEXT NOT NULL",
    )
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                """
                CREATE UNIQUE INDEX fake_run_id_unique
                ON run_create_idempotency_v1(run_id)
                WHERE run_id LIKE 'allow-%'
                """
            )
    finally:
        connection.close()

    with pytest.raises(
        RuntimeError,
        match="missing_constraints=.*run_id_unique",
    ):
        verify_run_schema(
            db_path=db_path,
            include_evidence_verification=True,
            include_publication=True,
        )


def _seed_pre_008_pending_run(db_path, *, run_id="run_old"):
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.executescript(
                """
                CREATE TABLE schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL,
                    checksum TEXT NOT NULL
                );
                CREATE TABLE research_runs_v2 (
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
                );
                CREATE TABLE run_segments (
                    segment_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    attempt INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(run_id, sequence)
                );
                """
            )
            connection.execute(
                """
                INSERT INTO research_runs_v2 (
                    run_id, thread_id, query, profile_id, profile_version,
                    scope_json, execution_status, review_status, delivery_status,
                    state_version, created_at, updated_at
                ) VALUES (?, 'thread-old', 'old query', 'generic', '1', '{}',
                          'pending', 'not_required', 'pending', 0,
                          '2026-07-13T00:00:00+00:00',
                          '2026-07-13T00:00:00+00:00')
                """,
                (run_id,),
            )
            connection.execute(
                """
                INSERT INTO run_segments (
                    segment_id, run_id, kind, sequence, attempt, status,
                    created_at, updated_at
                ) VALUES (?, ?, 'initial', 0, 1, 'pending',
                          '2026-07-13T00:00:00+00:00',
                          '2026-07-13T00:00:00+00:00')
                """,
                (f"{run_id}_seg_000", run_id),
            )
    finally:
        connection.close()


def _remove_dispatch_migration(db_path):
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute("DROP INDEX idx_run_dispatches_status_lease_created")
            connection.execute("DROP TABLE run_dispatches_v1")
            connection.execute(
                "DELETE FROM schema_migrations "
                "WHERE version = '008_run_dispatch_reconciliation'"
            )
    finally:
        connection.close()


def test_008_schema_is_exact_and_applies_repeatedly(tmp_path):
    from api.run_repository import init_run_schema

    db_path = str(tmp_path / "tasks.db")
    init_review_schema(db_path)
    init_run_schema(db_path)
    result = verify_run_schema(db_path=db_path)

    assert "008_run_dispatch_reconciliation" in result["migration_versions"]
    assert "run_dispatches_v1" in result["tables"]
    assert "idx_run_dispatches_status_lease_created" in result["indexes"]
    assert result["columns"]["run_dispatches_v1"] == [
        "attempt_count",
        "created_at",
        "last_error_code",
        "lease_expires_at",
        "lease_owner",
        "run_id",
        "started_at",
        "status",
        "updated_at",
    ]


def test_008_does_not_backfill_old_pending_run(tmp_path):
    from api.run_repository import init_run_schema

    db_path = str(tmp_path / "tasks.db")
    _seed_pre_008_pending_run(db_path)
    init_run_schema(db_path)

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM run_dispatches_v1"
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_existing_007_database_gets_separate_008_backup(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    first_backup = str(tmp_path / "tasks.pre-idempotency.db")
    init_legacy_db(db_path).close()
    migrate_with_backup(db_path=db_path, backup_path=first_backup)
    _remove_dispatch_migration(db_path)

    dispatch_backup = str(tmp_path / "tasks.pre-run-dispatch.bak")
    result = migrate_with_backup(db_path=db_path, backup_path=dispatch_backup)

    assert "008_run_dispatch_reconciliation" in result["migration_versions"]
    assert Path(dispatch_backup).exists()
    assert Path(first_backup).exists()


def test_008_failure_restores_existing_007_database(tmp_path, monkeypatch):
    import api.run_migrations as migrations

    db_path = str(tmp_path / "tasks.db")
    init_legacy_db(db_path).close()
    migrate_with_backup(
        db_path=db_path,
        backup_path=str(tmp_path / "tasks.pre-idempotency.db"),
    )
    _remove_dispatch_migration(db_path)
    connection = sqlite3.connect(db_path)
    try:
        before_sql = "\n".join(connection.iterdump())
    finally:
        connection.close()
    original = migrations.init_run_schema

    def apply_then_fail(path):
        original(path)
        raise RuntimeError("dispatch migration failed")

    monkeypatch.setattr(migrations, "init_run_schema", apply_then_fail)
    with pytest.raises(RuntimeError, match="dispatch migration failed"):
        migrate_with_backup(
            db_path=db_path,
            backup_path=str(tmp_path / "tasks.pre-run-dispatch.bak"),
        )

    connection = sqlite3.connect(db_path)
    try:
        after_sql = "\n".join(connection.iterdump())
    finally:
        connection.close()
    assert after_sql == before_sql


def test_existing_backup_is_not_overwritten_for_008_upgrade(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    init_legacy_db(db_path).close()
    migrate_with_backup(
        db_path=db_path,
        backup_path=str(tmp_path / "tasks.pre-idempotency.db"),
    )
    _remove_dispatch_migration(db_path)
    backup_path = tmp_path / "tasks.pre-run-dispatch.bak"
    backup_path.write_bytes(b"keep")

    with pytest.raises(
        RuntimeError,
        match="run_dispatch_migration_backup_already_exists",
    ):
        migrate_with_backup(db_path=db_path, backup_path=str(backup_path))
    assert backup_path.read_bytes() == b"keep"


def _replace_dispatch_table(db_path, table_sql):
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute("PRAGMA foreign_keys=OFF")
            connection.execute("DROP TABLE run_dispatches_v1")
            connection.execute(table_sql)
    finally:
        connection.close()


_VALID_DISPATCH_TABLE_SQL = """
CREATE TABLE run_dispatches_v1 (
    run_id TEXT PRIMARY KEY REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK(status IN ('pending', 'leased', 'started', 'failed')),
    lease_owner TEXT,
    lease_expires_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
    last_error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    CHECK(
        (status = 'leased' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR (status != 'leased' AND lease_owner IS NULL AND lease_expires_at IS NULL)
    ),
    CHECK(
        (status = 'started' AND started_at IS NOT NULL AND last_error_code IS NULL)
        OR (status = 'failed' AND started_at IS NULL AND last_error_code IS NOT NULL)
        OR (status IN ('pending', 'leased') AND started_at IS NULL)
    )
)
"""


@pytest.mark.parametrize(
    ("label", "old", "new"),
    [
        ("dispatch_run_id_primary_key", "run_id TEXT PRIMARY KEY", "run_id TEXT NOT NULL"),
        (
            "dispatch_run_id_foreign_key",
            "REFERENCES research_runs_v2(run_id) ON DELETE CASCADE",
            "",
        ),
        (
            "dispatch_status_check",
            "CHECK(status IN ('pending', 'leased', 'started', 'failed'))",
            "",
        ),
        ("dispatch_attempt_check", "CHECK(attempt_count >= 0)", ""),
        (
            "dispatch_state_check",
            "CHECK(\n        (status = 'leased' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)\n        OR (status != 'leased' AND lease_owner IS NULL AND lease_expires_at IS NULL)\n    )",
            "CHECK(1)",
        ),
    ],
)
def test_verifier_rejects_malformed_dispatch_table(tmp_path, label, old, new):
    db_path = str(tmp_path / "tasks.db")
    init_review_schema(db_path)
    _replace_dispatch_table(db_path, _VALID_DISPATCH_TABLE_SQL.replace(old, new))

    with pytest.raises(RuntimeError, match=f"missing_constraints=.*{label}"):
        verify_run_schema(db_path=db_path)


def test_verifier_rejects_wrong_dispatch_scan_index(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    init_review_schema(db_path)
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute("DROP INDEX idx_run_dispatches_status_lease_created")
            connection.execute(
                "CREATE UNIQUE INDEX idx_run_dispatches_status_lease_created "
                "ON run_dispatches_v1(created_at, status, lease_expires_at) "
                "WHERE status = 'pending'"
            )
    finally:
        connection.close()

    with pytest.raises(
        RuntimeError,
        match="missing_constraints=.*dispatch_scan_index",
    ):
        verify_run_schema(db_path=db_path)


def test_009_marks_only_preexisting_failed_runs_not_observed(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    _seed_pre_009_runs(
        db_path,
        statuses=("completed", "pending", "running", "failed"),
    )

    _apply_009(db_path)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT * FROM run_failure_causes_v1 ORDER BY run_id"
        ).fetchall()
        marker_count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
            (RUN_FAILURE_CAUSE_MIGRATION_VERSION,),
        ).fetchone()[0]
    finally:
        connection.close()

    assert marker_count == 1
    assert len(rows) == 1
    assert rows[0]["run_id"] == "run_failed_3"
    assert rows[0]["observation_status"] == "not_observed"
    assert rows[0]["terminal_state_version"] is None
    assert rows[0]["phase"] is None
    assert rows[0]["code"] is None
    assert rows[0]["recorded_at"] is None


def test_009_schema_marker_fk_and_variant_check_are_exact(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    _seed_pre_009_runs(db_path)

    result = _apply_009(db_path)

    connection = sqlite3.connect(db_path)
    try:
        marker = connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version = ?",
            (RUN_FAILURE_CAUSE_MIGRATION_VERSION,),
        ).fetchall()
        columns = connection.execute(
            "PRAGMA table_info(run_failure_causes_v1)"
        ).fetchall()
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(run_failure_causes_v1)"
        ).fetchall()
        table_sql = connection.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = 'run_failure_causes_v1'
            """
        ).fetchone()[0]
    finally:
        connection.close()

    assert marker == [(RUN_FAILURE_CAUSE_MIGRATION_CHECKSUM,)]
    assert [tuple(row[1:6]) for row in columns] == [
        ("run_id", "TEXT", 1, None, 1),
        ("observation_status", "TEXT", 1, None, 0),
        ("terminal_state_version", "INTEGER", 0, None, 0),
        ("phase", "TEXT", 0, None, 0),
        ("code", "TEXT", 0, None, 0),
        ("recorded_at", "TEXT", 0, None, 0),
    ]
    assert len(foreign_keys) == 1
    assert foreign_keys[0][2:7] == (
        "research_runs_v2",
        "run_id",
        "run_id",
        "NO ACTION",
        "CASCADE",
    )
    assert _normalized_sql(table_sql) == _normalized_sql(
        RUN_FAILURE_CAUSE_TABLE_SQL
    )
    assert RUN_FAILURE_CAUSE_MIGRATION_VERSION in result["migration_versions"]
    assert "run_failure_causes_v1" in result["tables"]
    assert result["columns"]["run_failure_causes_v1"] == [
        "code",
        "observation_status",
        "phase",
        "recorded_at",
        "run_id",
        "terminal_state_version",
    ]


def test_009_inserts_historical_rows_before_single_marker(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    _seed_pre_009_runs(db_path, statuses=("failed",))
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                """
                CREATE TRIGGER require_009_history_before_marker
                BEFORE INSERT ON schema_migrations
                WHEN NEW.version = '009_run_failure_cause_v1'
                BEGIN
                    SELECT CASE
                        WHEN (
                            SELECT COUNT(*) FROM run_failure_causes_v1
                        ) != (
                            SELECT COUNT(*) FROM research_runs_v2
                            WHERE execution_status = 'failed'
                        )
                        THEN RAISE(ABORT, '009 history missing')
                    END;
                END
                """
            )
    finally:
        connection.close()

    _apply_009(db_path)

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM run_failure_causes_v1"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
            (RUN_FAILURE_CAUSE_MIGRATION_VERSION,),
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_009_marker_present_is_verify_only_and_never_repairs(tmp_path):
    from api.run_failure_cause_models import RunFailureCauseConflict
    from api.run_repository import init_run_schema

    db_path = str(tmp_path / "tasks.db")
    _seed_pre_009_runs(db_path, statuses=("failed",))
    _apply_009(db_path)
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                "DELETE FROM run_failure_causes_v1 WHERE run_id = 'run_failed_0'"
            )
    finally:
        connection.close()

    with pytest.raises(
        RunFailureCauseConflict,
        match="run_failure_cause_corrupt",
    ):
        init_run_schema(db_path)

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM run_failure_causes_v1"
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_009_rejects_nullable_run_id_or_observation_status(tmp_path):
    from api.run_failure_cause_models import RunFailureCauseConflict
    from api.run_repository import init_run_schema

    mutations = (
        ("run_id TEXT NOT NULL PRIMARY KEY", "run_id TEXT PRIMARY KEY"),
        (
            "observation_status TEXT NOT NULL",
            "observation_status TEXT",
        ),
    )
    for index, (old, new) in enumerate(mutations):
        db_path = str(tmp_path / f"nullable-{index}.db")
        _seed_pre_009_runs(db_path)
        _apply_009(db_path)
        _replace_failure_cause_table(
            db_path,
            RUN_FAILURE_CAUSE_TABLE_SQL.replace(old, new, 1),
        )

        with pytest.raises(
            RunFailureCauseConflict,
            match="run_failure_cause_corrupt",
        ):
            init_run_schema(db_path)


def test_009_rejects_null_observed_fields_and_noninteger_terminal_version(
    tmp_path,
):
    from api.run_failure_cause_models import RunFailureCauseConflict
    from api.run_repository import init_run_schema

    invalid_values = (
        (None, "execution", "execution_error", "2026-07-15T00:00:00+00:00"),
        (3, None, "execution_error", "2026-07-15T00:00:00+00:00"),
        (3, "execution", None, "2026-07-15T00:00:00+00:00"),
        (3, "execution", "execution_error", None),
        (
            "not-an-integer",
            "execution",
            "execution_error",
            "2026-07-15T00:00:00+00:00",
        ),
    )
    for index, values in enumerate(invalid_values):
        db_path = str(tmp_path / f"invalid-observed-{index}.db")
        run_id = _seed_observed_failure(db_path)
        connection = sqlite3.connect(db_path)
        try:
            connection.execute("PRAGMA ignore_check_constraints=ON")
            with connection:
                connection.execute(
                    """
                    UPDATE run_failure_causes_v1
                    SET terminal_state_version = ?, phase = ?, code = ?,
                        recorded_at = ?
                    WHERE run_id = ?
                    """,
                    (*values, run_id),
                )
            connection.execute("PRAGMA ignore_check_constraints=OFF")
        finally:
            connection.close()

        with pytest.raises(
            RunFailureCauseConflict,
            match="run_failure_cause_corrupt",
        ):
            init_run_schema(db_path)


def test_009_rejects_zero_and_negative_terminal_version(tmp_path):
    from api.run_failure_cause_models import RunFailureCauseConflict
    from api.run_repository import init_run_schema

    for value in (0, -1):
        db_path = str(tmp_path / f"terminal-version-{value}.db")
        run_id = _seed_observed_failure(db_path)
        connection = sqlite3.connect(db_path)
        try:
            connection.execute("PRAGMA ignore_check_constraints=ON")
            with connection:
                connection.execute(
                    """
                    UPDATE run_failure_causes_v1
                    SET terminal_state_version = ? WHERE run_id = ?
                    """,
                    (value, run_id),
                )
            connection.execute("PRAGMA ignore_check_constraints=OFF")
        finally:
            connection.close()

        with pytest.raises(
            RunFailureCauseConflict,
            match="run_failure_cause_corrupt",
        ):
            init_run_schema(db_path)


def test_009_rejects_observed_terminal_version_mismatch(tmp_path):
    from api.run_failure_cause_models import RunFailureCauseConflict
    from api.run_repository import init_run_schema

    db_path = str(tmp_path / "tasks.db")
    run_id = _seed_observed_failure(db_path)
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE research_runs_v2 SET state_version = 4 WHERE run_id = ?
                """,
                (run_id,),
            )
    finally:
        connection.close()

    with pytest.raises(
        RunFailureCauseConflict,
        match="run_failure_cause_corrupt",
    ):
        init_run_schema(db_path)


def test_009_rejects_observed_recorded_at_or_segment_timestamp_mismatch(
    tmp_path,
):
    from api.run_failure_cause_models import RunFailureCauseConflict
    from api.run_repository import init_run_schema

    cases = (
        (
            "2026-07-15T00:00:00+00:00",
            "2026-07-15T00:00:01+00:00",
            "2026-07-15T00:00:00+00:00",
        ),
        (
            "2026-07-15T00:00:00+00:00",
            "2026-07-15T00:00:00+00:00",
            "2026-07-15T00:00:01+00:00",
        ),
        ("not-a-timestamp", "not-a-timestamp", "not-a-timestamp"),
    )
    for index, (recorded_at, run_updated_at, segment_updated_at) in enumerate(
        cases
    ):
        db_path = str(tmp_path / f"timestamp-{index}.db")
        run_id = _seed_observed_failure(db_path)
        connection = sqlite3.connect(db_path)
        try:
            with connection:
                connection.execute(
                    "UPDATE research_runs_v2 SET updated_at = ? WHERE run_id = ?",
                    (run_updated_at, run_id),
                )
                connection.execute(
                    "UPDATE run_segments SET updated_at = ? WHERE run_id = ?",
                    (segment_updated_at, run_id),
                )
                connection.execute(
                    """
                    UPDATE run_failure_causes_v1
                    SET recorded_at = ? WHERE run_id = ?
                    """,
                    (recorded_at, run_id),
                )
        finally:
            connection.close()

        with pytest.raises(
            RunFailureCauseConflict,
            match="run_failure_cause_corrupt",
        ):
            init_run_schema(db_path)


def test_009_repeated_apply_is_idempotent(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    _seed_pre_009_runs(db_path, statuses=("failed",))

    first = _apply_009(db_path)
    before = _database_dump(db_path)
    second = _apply_009(db_path)

    assert first == second
    assert RUN_FAILURE_CAUSE_MIGRATION_VERSION in first["migration_versions"]
    assert "run_failure_causes_v1" in first["tables"]
    assert _database_dump(db_path) == before


def test_fresh_pre_003_database_applies_legacy_chain_then_009_without_nested_transaction(
    tmp_path,
):
    from api.run_repository import init_run_schema

    db_path = str(tmp_path / "tasks.db")
    init_legacy_db(db_path).close()

    init_run_schema(db_path)

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version = ?",
            (RUN_FAILURE_CAUSE_MIGRATION_VERSION,),
        ).fetchone() == (RUN_FAILURE_CAUSE_MIGRATION_CHECKSUM,)
        assert connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'run_failure_causes_v1'
            """
        ).fetchone() == (1,)
    finally:
        connection.close()


def _deny_009_operation(monkeypatch, *, action_code, table_name):
    import api.run_repository as repository

    original_connect = repository._connect
    connection_count = 0

    def connect_with_denied_009_operation(db_path=None):
        nonlocal connection_count
        connection = original_connect(db_path)
        connection_count += 1
        if connection_count == 2:
            connection.set_authorizer(
                lambda action, arg1, _arg2, _database, _trigger: (
                    sqlite3.SQLITE_DENY
                    if action == action_code and arg1 == table_name
                    else sqlite3.SQLITE_OK
                )
            )
        return connection

    monkeypatch.setattr(repository, "_connect", connect_with_denied_009_operation)


def _assert_009_failure_restores_complete_backup(db_path):
    from api.run_failure_cause_models import RunFailureCauseConflict
    from api.run_repository import init_run_schema

    before = _database_dump(db_path)
    with pytest.raises(
        RunFailureCauseConflict,
        match="run_failure_cause_corrupt",
    ):
        init_run_schema(db_path)

    backup_path = _failure_backup_path(db_path)
    assert backup_path.exists()
    assert _database_dump(db_path) == before
    assert _database_dump(backup_path) == before


def test_009_table_create_failure_restores_complete_dedicated_backup(
    tmp_path,
    monkeypatch,
):
    db_path = str(tmp_path / "tasks.db")
    _seed_pre_009_runs(db_path, statuses=("failed",))
    _deny_009_operation(
        monkeypatch,
        action_code=sqlite3.SQLITE_CREATE_TABLE,
        table_name="run_failure_causes_v1",
    )

    _assert_009_failure_restores_complete_backup(db_path)


def test_009_historical_insert_failure_restores_complete_dedicated_backup(
    tmp_path,
    monkeypatch,
):
    db_path = str(tmp_path / "tasks.db")
    _seed_pre_009_runs(db_path, statuses=("failed",))
    _deny_009_operation(
        monkeypatch,
        action_code=sqlite3.SQLITE_INSERT,
        table_name="run_failure_causes_v1",
    )

    _assert_009_failure_restores_complete_backup(db_path)


def test_009_marker_insert_failure_restores_complete_dedicated_backup(
    tmp_path,
    monkeypatch,
):
    db_path = str(tmp_path / "tasks.db")
    _seed_pre_009_runs(db_path, statuses=("failed",))
    _deny_009_operation(
        monkeypatch,
        action_code=sqlite3.SQLITE_INSERT,
        table_name="schema_migrations",
    )

    _assert_009_failure_restores_complete_backup(db_path)


def test_009_post_verify_failure_restores_complete_dedicated_backup(
    tmp_path,
    monkeypatch,
):
    import api.run_repository as repository
    from api.run_failure_cause_models import RunFailureCauseConflict

    db_path = str(tmp_path / "tasks.db")
    _seed_pre_009_runs(db_path, statuses=("failed",))

    def fail_row_verification(_connection):
        raise RunFailureCauseConflict("run_failure_cause_corrupt")

    monkeypatch.setattr(
        repository,
        "_verify_run_failure_cause_rows",
        fail_row_verification,
        raising=False,
    )

    _assert_009_failure_restores_complete_backup(db_path)


def test_009_existing_dedicated_backup_is_not_overwritten(tmp_path):
    from api.run_repository import init_run_schema

    db_path = str(tmp_path / "tasks.db")
    _seed_pre_009_runs(db_path, statuses=("failed",))
    backup_path = _failure_backup_path(db_path)
    backup_path.write_bytes(b"keep-dedicated-backup")
    before = _database_dump(db_path)

    with pytest.raises(
        RuntimeError,
        match="run_failure_cause_migration_backup_already_exists",
    ):
        init_run_schema(db_path)

    assert backup_path.read_bytes() == b"keep-dedicated-backup"
    assert _database_dump(db_path) == before


def test_direct_init_on_pre_009_database_creates_dedicated_backup_before_writes(
    tmp_path,
    monkeypatch,
):
    import api.run_repository as repository

    db_path = str(tmp_path / "tasks.db")
    _seed_pre_009_runs(db_path, statuses=("failed",))
    before = _database_dump(db_path)
    observed = {}
    original = repository._init_run_schema_unlocked

    def assert_backup_then_initialize(path):
        backup_path = _failure_backup_path(path)
        observed["exists"] = backup_path.exists()
        observed["dump"] = _database_dump(backup_path)
        return original(path)

    monkeypatch.setattr(
        repository,
        "_init_run_schema_unlocked",
        assert_backup_then_initialize,
    )

    repository.init_run_schema(db_path)

    assert observed == {"exists": True, "dump": before}


def test_create_run_cannot_bypass_009_backup_or_verification(tmp_path):
    from api.run_repository import create_run

    db_path = str(tmp_path / "tasks.db")
    _seed_pre_009_runs(db_path)

    created = create_run(db_path=db_path, thread_id="thread-new", query="query")

    backup_path = _failure_backup_path(db_path)
    assert backup_path.exists()
    backup_dump = _database_dump(backup_path)
    assert RUN_FAILURE_CAUSE_MIGRATION_VERSION not in backup_dump
    assert created["run_id"] not in backup_dump
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
            (RUN_FAILURE_CAUSE_MIGRATION_VERSION,),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM research_runs_v2 WHERE run_id = ?",
            (created["run_id"],),
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_dispatch_review_and_publication_init_cannot_bypass_009_backup(
    tmp_path,
):
    from api.publication_repository import init_publication_schema
    from api.review_repository import init_review_schema
    from api.run_dispatch_repository import get_run_dispatch

    initializers = (
        lambda path: get_run_dispatch(db_path=path, run_id="run-missing"),
        init_review_schema,
        init_publication_schema,
    )
    for index, initialize in enumerate(initializers):
        db_path = str(tmp_path / f"initializer-{index}.db")
        _seed_pre_009_runs(db_path)

        initialize(db_path)

        backup_path = _failure_backup_path(db_path)
        assert backup_path.exists()
        assert RUN_FAILURE_CAUSE_MIGRATION_VERSION not in _database_dump(
            backup_path
        )
        connection = sqlite3.connect(db_path)
        try:
            assert connection.execute(
                "SELECT checksum FROM schema_migrations WHERE version = ?",
                (RUN_FAILURE_CAUSE_MIGRATION_VERSION,),
            ).fetchone() == (RUN_FAILURE_CAUSE_MIGRATION_CHECKSUM,)
        finally:
            connection.close()


def test_wrong_009_checksum_fails_init_migration_and_creation_without_repair(
    tmp_path,
):
    from api.run_failure_cause_models import RunFailureCauseConflict
    from api.run_repository import create_run, init_run_schema

    db_path = str(tmp_path / "tasks.db")
    _seed_pre_009_runs(db_path)
    _apply_009(db_path)
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                "UPDATE schema_migrations SET checksum = 'wrong' WHERE version = ?",
                (RUN_FAILURE_CAUSE_MIGRATION_VERSION,),
            )
    finally:
        connection.close()
    before = _database_dump(db_path)
    caller_backup = tmp_path / "wrong-checksum-caller.bak"

    for operation in (
        lambda: init_run_schema(db_path),
        lambda: migrate_with_backup(
            db_path=db_path,
            backup_path=str(caller_backup),
        ),
        lambda: create_run(
            db_path=db_path,
            thread_id="thread-new",
            query="query",
        ),
    ):
        with pytest.raises(
            RunFailureCauseConflict,
            match="run_failure_cause_unavailable",
        ):
            operation()

    assert not caller_backup.exists()
    assert _database_dump(db_path) == before
