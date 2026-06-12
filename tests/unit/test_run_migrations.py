import sqlite3

import pytest

from api.persistence import init_db
from api.run_migrations import (
    backup_database,
    migrate_with_backup,
    restore_database,
    verify_run_schema,
)
from api.run_repository import init_run_schema


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
    init_db(db_path).close()

    init_run_schema(db_path)
    init_run_schema(db_path)
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
    init_db(db_path).close()
    original_tables = _table_names(db_path)

    backup_database(db_path=db_path, backup_path=backup_path)
    init_run_schema(db_path)
    assert "research_runs_v2" in _table_names(db_path)

    restore_database(backup_path=backup_path, db_path=db_path)
    assert _table_names(db_path) == original_tables


def test_migration_verification_failure_restores_backup(tmp_path, monkeypatch):
    import api.run_migrations as migrations

    db_path = str(tmp_path / "tasks.db")
    backup_path = str(tmp_path / "tasks.pre-run-identity.db")
    init_db(db_path).close()
    original_tables = _table_names(db_path)

    def fail_verification(*, db_path):
        raise RuntimeError("verification failed")

    monkeypatch.setattr(migrations, "verify_run_schema", fail_verification)
    with pytest.raises(RuntimeError, match="verification failed"):
        migrate_with_backup(db_path=db_path, backup_path=backup_path)

    assert _table_names(db_path) == original_tables
