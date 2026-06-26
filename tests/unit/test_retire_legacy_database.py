import json
import sqlite3

import pytest

from api.run_repository import create_run
from api.review_repository import init_review_schema
from tests.legacy_db import init_legacy_db


LEGACY_TABLES = {"tasks", "research_runs", "evidence_entries"}


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


def _seed_database(path):
    connection = init_legacy_db(str(path))
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO tasks(thread_id, query, status, created_at)
                VALUES ('thread-1', 'private query', 'completed', '2026-06-26T00:00:00+00:00')
                """
            )
            connection.execute(
                """
                INSERT INTO research_runs(thread_id, query, status, created_at)
                VALUES ('thread-1', 'private query', 'completed', '2026-06-26T00:00:00+00:00')
                """
            )
            connection.execute(
                """
                INSERT INTO evidence_entries(
                    thread_id, query_text, subagent_name, tool_name, snippet,
                    citation_status, verification_status, created_at
                )
                VALUES (
                    'thread-1', 'private query', 'legacy', 'tool', 'private row',
                    'uncited', 'unverified', '2026-06-26T00:00:00+00:00'
                )
                """
            )
    finally:
        connection.close()
    init_review_schema(str(path))
    create_run(db_path=str(path), thread_id="canonical-thread", query="query")


def _retire(tmp_path, *, drop=False):
    from scripts.retire_legacy_database import retire_legacy_database

    database = tmp_path / "decision_research_agent.db"
    backup = tmp_path / "backup.db"
    archive = tmp_path / "archive.db"
    _seed_database(database)

    result = retire_legacy_database(
        database=database,
        backup=backup,
        archive=archive,
        drop_legacy_tables=drop,
    )
    return result, database, backup, archive


def test_retirement_archives_legacy_tables_without_dropping_by_default(tmp_path):
    result, database, backup, archive = _retire(tmp_path)

    assert result["status"] == "ok"
    assert result["dropped_legacy_tables"] is False
    assert result["legacy_tables_present"] == sorted(LEGACY_TABLES)
    assert LEGACY_TABLES <= _tables(database)
    assert LEGACY_TABLES <= _tables(archive)
    assert backup.exists()
    assert str(database) not in json.dumps(result)


def test_retirement_drops_legacy_tables_only_with_explicit_flag(tmp_path):
    result, database, _, archive = _retire(tmp_path, drop=True)

    assert result["status"] == "ok"
    assert result["dropped_legacy_tables"] is True
    assert LEGACY_TABLES.isdisjoint(_tables(database))
    assert LEGACY_TABLES <= _tables(archive)
    assert "research_runs_v2" in _tables(database)


def test_existing_backup_conflict_fails_closed(tmp_path):
    from scripts.retire_legacy_database import LegacyRetirementError, retire_legacy_database

    database = tmp_path / "decision_research_agent.db"
    backup = tmp_path / "backup.db"
    archive = tmp_path / "archive.db"
    _seed_database(database)
    backup.write_text("existing", encoding="utf-8")

    with pytest.raises(
        LegacyRetirementError,
        match="legacy_backup_already_exists",
    ):
        retire_legacy_database(
            database=database,
            backup=backup,
            archive=archive,
            drop_legacy_tables=True,
        )

    assert LEGACY_TABLES <= _tables(database)


def test_retirement_restores_backup_on_archive_failure(tmp_path, monkeypatch):
    import scripts.retire_legacy_database as retirement

    database = tmp_path / "decision_research_agent.db"
    backup = tmp_path / "backup.db"
    archive = tmp_path / "archive.db"
    _seed_database(database)

    def fail_export(*args, **kwargs):
        raise retirement.LegacyRetirementError("archive_failed")

    monkeypatch.setattr(retirement, "_export_legacy_tables", fail_export)

    with pytest.raises(retirement.LegacyRetirementError, match="archive_failed"):
        retirement.retire_legacy_database(
            database=database,
            backup=backup,
            archive=archive,
            drop_legacy_tables=True,
        )

    assert LEGACY_TABLES <= _tables(database)


def test_verify_only_rerun_after_drop_is_idempotent(tmp_path):
    from scripts.retire_legacy_database import retire_legacy_database

    _, database, backup, archive = _retire(tmp_path, drop=True)
    rerun = retire_legacy_database(
        database=database,
        backup=tmp_path / "second-backup.db",
        archive=tmp_path / "second-archive.db",
        drop_legacy_tables=False,
    )

    assert rerun["status"] == "ok"
    assert rerun["legacy_tables_present"] == []
    assert rerun["dropped_legacy_tables"] is False
    assert backup.exists()
    assert archive.exists()
