from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Iterable

from api.run_migrations import verify_run_schema


LEGACY_TABLES = ("tasks", "research_runs", "evidence_entries")


class LegacyRetirementError(RuntimeError):
    pass


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    return connection


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _verify_source(database: Path) -> set[str]:
    if not database.exists():
        raise LegacyRetirementError("database_not_found")
    try:
        verify_run_schema(db_path=str(database))
    except Exception as exc:
        raise LegacyRetirementError("canonical_schema_not_ready") from exc
    connection = _connect(database)
    try:
        return _table_names(connection)
    finally:
        connection.close()


def _copy_backup(database: Path, backup: Path) -> None:
    if backup.exists():
        raise LegacyRetirementError("legacy_backup_already_exists")
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(database, backup)


def _restore_backup(database: Path, backup: Path) -> None:
    shutil.copy2(backup, database)


def _export_legacy_tables(
    *,
    database: Path,
    archive: Path,
    tables: Iterable[str],
) -> dict[str, int]:
    if archive.exists():
        raise LegacyRetirementError("legacy_archive_already_exists")
    archive.parent.mkdir(parents=True, exist_ok=True)
    source = _connect(database)
    destination = _connect(archive)
    try:
        exported: dict[str, int] = {}
        with destination:
            for table in tables:
                create_sql = source.execute(
                    """
                    SELECT sql FROM sqlite_master
                    WHERE type='table' AND name=?
                    """,
                    (table,),
                ).fetchone()
                if create_sql is None or not create_sql["sql"]:
                    continue
                destination.execute(create_sql["sql"])
                columns = [
                    row["name"]
                    for row in source.execute(f"PRAGMA table_info({table})")
                ]
                column_sql = ", ".join(f'"{column}"' for column in columns)
                rows = source.execute(f"SELECT {column_sql} FROM {table}").fetchall()
                if rows:
                    placeholders = ", ".join("?" for _ in columns)
                    destination.executemany(
                        f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})",
                        [tuple(row[column] for column in columns) for row in rows],
                    )
                exported[table] = len(rows)
        return exported
    finally:
        destination.close()
        source.close()


def _drop_legacy_tables(database: Path, tables: Iterable[str]) -> None:
    connection = _connect(database)
    try:
        with connection:
            for table in tables:
                connection.execute(f"DROP TABLE IF EXISTS {table}")
    finally:
        connection.close()


def retire_legacy_database(
    *,
    database: Path,
    backup: Path,
    archive: Path,
    drop_legacy_tables: bool,
) -> dict:
    database = database.expanduser().resolve()
    backup = backup.expanduser().resolve()
    archive = archive.expanduser().resolve()
    source_tables = _verify_source(database)
    legacy_tables = tuple(table for table in LEGACY_TABLES if table in source_tables)
    if not legacy_tables:
        return {
            "status": "ok",
            "legacy_tables_present": [],
            "archived_tables": {},
            "dropped_legacy_tables": False,
            "canonical_schema_verified": True,
        }

    _copy_backup(database, backup)
    try:
        archived = _export_legacy_tables(
            database=database,
            archive=archive,
            tables=legacy_tables,
        )
        if drop_legacy_tables:
            _drop_legacy_tables(database, legacy_tables)
            _verify_source(database)
        return {
            "status": "ok",
            "legacy_tables_present": sorted(legacy_tables),
            "archived_tables": archived,
            "dropped_legacy_tables": drop_legacy_tables,
            "canonical_schema_verified": True,
        }
    except Exception:
        _restore_backup(database, backup)
        raise


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Archive and optionally drop pre-v0.1.0 legacy tables."
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--drop-legacy-tables", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = retire_legacy_database(
            database=args.database,
            backup=args.backup,
            archive=args.archive,
            drop_legacy_tables=args.drop_legacy_tables,
        )
    except LegacyRetirementError as exc:
        result = {
            "status": "failed",
            "error": str(exc),
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
