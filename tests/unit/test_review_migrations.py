import sqlite3

import pytest

from api.persistence import init_db
from api.review_repository import REVIEW_MIGRATION_VERSION, init_review_schema
from api.run_migrations import (
    backup_database,
    restore_database,
    verify_run_schema,
)


REVIEW_TABLES = {
    "review_decisions_v2",
    "review_workflows_v2",
    "review_resume_attempts_v2",
    "review_resolutions_v2",
}


def _tables(path):
    connection = sqlite3.connect(path)
    try:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        connection.close()


def test_review_migration_is_idempotent_and_verified(tmp_path):
    path = str(tmp_path / "tasks.db")
    init_db(path).close()
    init_review_schema(path)
    init_review_schema(path)

    result = verify_run_schema(db_path=path)

    assert REVIEW_TABLES <= _tables(path)
    assert REVIEW_MIGRATION_VERSION in result["migration_versions"]


def test_review_schema_backup_restore_removes_additive_tables(tmp_path):
    path = str(tmp_path / "tasks.db")
    backup = str(tmp_path / "tasks.pre-review.db")
    init_db(path).close()
    before = _tables(path)

    backup_database(db_path=path, backup_path=backup)
    init_review_schema(path)
    assert REVIEW_TABLES <= _tables(path)

    restore_database(backup_path=backup, db_path=path)
    assert _tables(path) == before


def test_review_schema_verification_fails_on_checksum_mismatch(tmp_path):
    path = str(tmp_path / "tasks.db")
    init_db(path).close()
    init_review_schema(path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE schema_migrations SET checksum = ? WHERE version = ?",
            ("tampered", REVIEW_MIGRATION_VERSION),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        RuntimeError,
        match="run_schema_verification_failed:.*migrations",
    ):
        verify_run_schema(db_path=path)


def test_review_schema_verification_fails_on_incomplete_existing_table(tmp_path):
    path = str(tmp_path / "tasks.db")
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE review_workflows_v2 (
                status TEXT,
                lease_expires_at TEXT,
                updated_at TEXT
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    init_review_schema(path)

    with pytest.raises(
        RuntimeError,
        match="run_schema_verification_failed:.*columns",
    ):
        verify_run_schema(db_path=path)


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("research_runs_v2", "query"),
        ("review_bundles_v2", "bundle_json"),
        ("review_decisions_v2", "actor_fingerprint"),
        ("review_workflows_v2", "last_error_code"),
        ("review_resume_attempts_v2", "worker_id"),
        ("review_resolutions_v2", "artifact_ids_json"),
    ],
)
def test_review_schema_verification_checks_required_columns(
    tmp_path,
    table,
    column,
):
    path = str(tmp_path / f"{table}.db")
    init_review_schema(path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        RuntimeError,
        match=rf"run_schema_verification_failed:.*{table}.*{column}",
    ):
        verify_run_schema(db_path=path)
