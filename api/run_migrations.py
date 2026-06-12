"""Operational safeguards for the additive run identity migration."""
from __future__ import annotations

from pathlib import Path
import sqlite3

from api.persistence import _get_db_path
from api.run_repository import MIGRATION_VERSION, init_run_schema


REQUIRED_TABLES = {
    "schema_migrations",
    "research_runs_v2",
    "run_segments",
    "evidence_entries_v2",
}
REQUIRED_INDEXES = {"idx_research_runs_v2_thread"}


def backup_database(*, db_path: str, backup_path: str) -> None:
    """Create a transactionally consistent SQLite backup."""
    Path(backup_path).parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(_get_db_path(db_path))
    destination = sqlite3.connect(backup_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def restore_database(*, backup_path: str, db_path: str) -> None:
    """Restore a SQLite backup without copying WAL sidecar files."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(backup_path)
    destination = sqlite3.connect(_get_db_path(db_path))
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def verify_run_schema(*, db_path: str) -> dict:
    """Fail closed unless the run identity schema is complete and consistent."""
    conn = sqlite3.connect(_get_db_path(db_path))
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        missing_tables = sorted(REQUIRED_TABLES - tables)
        missing_indexes = sorted(REQUIRED_INDEXES - indexes)
        migration_count = conn.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
            (MIGRATION_VERSION,),
        ).fetchone()[0] if "schema_migrations" in tables else 0
        foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        if missing_tables or missing_indexes or migration_count != 1 or foreign_key_errors:
            raise RuntimeError(
                "run_schema_verification_failed:"
                f"tables={missing_tables},indexes={missing_indexes},"
                f"migration_count={migration_count},foreign_keys={foreign_key_errors}"
            )
        return {
            "migration_version": MIGRATION_VERSION,
            "tables": sorted(REQUIRED_TABLES),
            "indexes": sorted(REQUIRED_INDEXES),
        }
    finally:
        conn.close()


def migrate_with_backup(*, db_path: str, backup_path: str) -> dict:
    """Back up, apply, and verify; restore the original DB on any failure."""
    backup_database(db_path=db_path, backup_path=backup_path)
    try:
        init_run_schema(db_path)
        return verify_run_schema(db_path=db_path)
    except Exception:
        restore_database(backup_path=backup_path, db_path=db_path)
        raise
