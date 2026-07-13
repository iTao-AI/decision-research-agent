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
