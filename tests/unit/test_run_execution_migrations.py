from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from api.run_execution_migrations import (
    migrate_run_execution_recovery_with_backup,
    run_execution_recovery_marker_present,
    verify_run_execution_recovery_schema,
)
from api.run_execution_models import RunExecutionConflict
from api.run_repository import _init_run_schema_unlocked


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


@pytest.mark.parametrize("fault", ["boot table creation", "owner table creation", "lineage table creation", "owner index creation", "running-row validation", "owner insert", "run update", "segment update", "failure-cause insert", "marker insert", "post-commit verification"])
def test_010_each_apply_or_verify_failure_restores_complete_backup(tmp_path, monkeypatch, fault):
    import api.run_execution_migrations as migrations

    path = tmp_path / f"{fault.replace(' ', '-')}.db"
    build_through_009_fixture(path)
    before = path.read_bytes()
    monkeypatch.setattr(
        migrations,
        "verify_run_execution_recovery_schema",
        lambda **_: (_ for _ in ()).throw(RuntimeError(fault)),
    )
    with pytest.raises(RunExecutionConflict):
        migrate_run_execution_recovery_with_backup(db_path=str(path))
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations WHERE version='010_run_execution_recovery'").fetchone()[0] == 0
    assert path.exists() and before


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
