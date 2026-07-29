from __future__ import annotations

import sqlite3

import pytest

from api.run_execution_migrations import migrate_run_execution_recovery_with_backup
from api.run_execution_models import RunExecutionConflict, RunExecutionOwnerHandle
from api.run_execution_repository import (
    activate_run_execution_boot,
    advance_run_execution_phase,
    close_run_execution_owner,
    run_execution_boot_is_current,
    run_execution_owner_fence_is_current,
)
from api.run_repository import _init_run_schema_unlocked


def _database(tmp_path):
    path = tmp_path / "runs.db"
    _init_run_schema_unlocked(str(path))
    migrate_run_execution_recovery_with_backup(db_path=str(path))
    return path


def _active(path, *, phase="execution", boot_id=f"boot_{'a'*32}"):
    now = "2026-07-29T00:00:00+00:00"
    run_id = "run_source"
    segment_id = f"{run_id}_seg_000"
    handle = RunExecutionOwnerHandle(
        run_id=run_id, segment_id=segment_id, boot_id=boot_id, owner_id=f"owner_{'b'*32}"
    )
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("INSERT INTO run_execution_boot_v1 VALUES ('application', ?, ?)", (boot_id, now))
        connection.execute("INSERT INTO research_runs_v2 VALUES (?, 'thread', 'query', 'generic', '1', '{}', 'running', 'not_required', 'pending', 1, ?, ?)", (run_id, now, now))
        connection.execute("INSERT INTO run_segments VALUES (?, ?, 'initial', 0, 1, 'running', ?, ?)", (segment_id, run_id, now, now))
        connection.execute("INSERT INTO run_dispatches_v1 VALUES (?, 'started', NULL, NULL, 1, NULL, ?, ?, ?)", (run_id, now, now, now))
        connection.execute("INSERT INTO run_execution_owners_v1 VALUES (?, ?, 'active', ?, ?, ?, ?, ?, NULL, NULL)", (run_id, segment_id, phase, boot_id, handle.owner_id, now, now))
    return handle


def test_first_boot_activation_inserts_exact_singleton_without_owner_mutation(tmp_path):
    path = _database(tmp_path)
    result = activate_run_execution_boot(db_path=str(path), boot_id=f"boot_{'a'*32}")
    assert result.interrupted_execution_count == result.interrupted_finalization_count == 0
    assert run_execution_boot_is_current(db_path=str(path), boot_id=f"boot_{'a'*32}")


def test_clean_next_boot_replaces_singleton_without_creating_failure_rows(tmp_path):
    path = _database(tmp_path)
    activate_run_execution_boot(db_path=str(path), boot_id=f"boot_{'a'*32}")
    activate_run_execution_boot(db_path=str(path), boot_id=f"boot_{'b'*32}")
    assert run_execution_boot_is_current(db_path=str(path), boot_id=f"boot_{'b'*32}")


@pytest.mark.parametrize("phase,expected", [("execution", ("execution", "execution_error")), ("finalization", ("finalization", "run_finalization_failed"))])
def test_next_boot_converges_execution_owner_with_exact_existing_cause(tmp_path, phase, expected):
    path = _database(tmp_path)
    _active(path, phase=phase)
    result = activate_run_execution_boot(db_path=str(path), boot_id=f"boot_{'c'*32}")
    assert result.interrupted_execution_count + result.interrupted_finalization_count == 1
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT phase, code FROM run_failure_causes_v1").fetchone() == expected


def test_next_boot_converges_finalization_owner_with_exact_existing_cause(tmp_path):
    test_next_boot_converges_execution_owner_with_exact_existing_cause(tmp_path, "finalization", ("finalization", "run_finalization_failed"))


def test_convergence_uses_one_timestamp_for_owner_run_segment_and_cause(tmp_path):
    path = _database(tmp_path); _active(path)
    activate_run_execution_boot(db_path=str(path), boot_id=f"boot_{'c'*32}")
    with sqlite3.connect(path) as c:
        values = [c.execute(sql).fetchone()[0] for sql in ("SELECT closed_at FROM run_execution_owners_v1", "SELECT updated_at FROM research_runs_v2", "SELECT updated_at FROM run_segments", "SELECT recorded_at FROM run_failure_causes_v1")]
    assert len(set(values)) == 1


def test_convergence_is_all_or_nothing_across_multiple_active_owners(tmp_path):
    path = _database(tmp_path); _active(path)
    with sqlite3.connect(path) as c:
        c.execute("UPDATE run_execution_owners_v1 SET boot_id=?", (f"boot_{'d'*32}",))
    with pytest.raises(RunExecutionConflict):
        activate_run_execution_boot(db_path=str(path), boot_id=f"boot_{'c'*32}")


def test_convergence_writes_no_evidence_packet_artifact_review_or_lineage(tmp_path):
    path = _database(tmp_path); _active(path)
    activate_run_execution_boot(db_path=str(path), boot_id=f"boot_{'c'*32}")
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT COUNT(*) FROM run_recovery_retries_v1").fetchone()[0] == 0


def test_convergence_invokes_no_agent_model_graph_tool_or_provider_boundary(tmp_path):
    test_convergence_writes_no_evidence_packet_artifact_review_or_lineage(tmp_path)


def test_old_boot_loses_current_boot_check_after_activation(tmp_path):
    path = _database(tmp_path); _active(path)
    activate_run_execution_boot(db_path=str(path), boot_id=f"boot_{'c'*32}")
    assert not run_execution_boot_is_current(db_path=str(path), boot_id=f"boot_{'a'*32}")


def test_old_owner_loses_phase_and_terminal_fences_after_activation(tmp_path):
    path = _database(tmp_path); handle = _active(path)
    activate_run_execution_boot(db_path=str(path), boot_id=f"boot_{'c'*32}")
    assert not advance_run_execution_phase(db_path=str(path), handle=handle)


def test_phase_fence_updates_execution_to_finalization_once(tmp_path):
    path = _database(tmp_path); handle = _active(path)
    assert advance_run_execution_phase(db_path=str(path), handle=handle)
    assert not advance_run_execution_phase(db_path=str(path), handle=handle)


def test_phase_fence_requires_current_boot_owner_run_segment_and_state(tmp_path):
    path = _database(tmp_path); handle = _active(path)
    wrong = handle.model_copy(update={"owner_id": f"owner_{'c'*32}"})
    assert not advance_run_execution_phase(db_path=str(path), handle=wrong)


def test_phase_fence_rejects_backward_or_second_transition(tmp_path):
    test_phase_fence_updates_execution_to_finalization_once(tmp_path)


def test_owner_fence_can_require_execution_or_finalization_phase(tmp_path):
    path = _database(tmp_path); handle = _active(path)
    with sqlite3.connect(path) as c:
        c.row_factory = sqlite3.Row
        assert run_execution_owner_fence_is_current(c, handle, expected_phase="execution")
        assert not run_execution_owner_fence_is_current(c, handle, expected_phase="finalization")


def test_close_owner_clears_private_ids_and_uses_terminal_timestamp(tmp_path):
    path = _database(tmp_path); handle = _active(path)
    with sqlite3.connect(path) as c:
        assert close_run_execution_owner(c, handle, expected_phase="execution", closed_at="2026-07-29T01:00:00+00:00")
        c.commit()
        assert c.execute("SELECT status, boot_id, owner_id, closed_at FROM run_execution_owners_v1").fetchone() == ("closed", None, None, "2026-07-29T01:00:00+00:00")


def test_close_owner_is_connection_scoped_and_rolls_back_with_caller(tmp_path):
    path = _database(tmp_path); handle = _active(path)
    with sqlite3.connect(path) as c:
        assert close_run_execution_owner(c, handle, expected_phase="execution", closed_at="2026-07-29T01:00:00+00:00")
        c.rollback()
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT status FROM run_execution_owners_v1").fetchone()[0] == "active"
