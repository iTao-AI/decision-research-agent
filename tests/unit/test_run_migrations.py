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
