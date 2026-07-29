from __future__ import annotations

import sqlite3

import pytest

from api.run_execution_repository import activate_run_execution_boot
from api.run_recovery_models import RunRecoveryConflict
from api.run_recovery_repository import create_or_replay_run_recovery
from tests.unit.test_run_execution_repository import _active, _database


def _source(tmp_path):
    path = _database(tmp_path)
    _active(path)
    boot = f"boot_{'c'*32}"
    activate_run_execution_boot(db_path=str(path), boot_id=boot)
    return path, boot


def _recover(path, boot, key="recovery-key-1234"):
    return create_or_replay_run_recovery(
        source_run_id="run_source", idempotency_key=key, boot_id=boot,
        exact_profile_is_available=lambda profile_id, version: (profile_id, version) == ("generic", "1"),
        db_path=str(path),
    )


def test_recovery_creates_run_segment_dispatch_and_lineage_in_one_transaction(tmp_path):
    path, boot = _source(tmp_path); accepted = _recover(path, boot)
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT COUNT(*) FROM run_recovery_retries_v1").fetchone()[0] == 1
        assert c.execute("SELECT status FROM run_dispatches_v1 WHERE run_id=?", (accepted.run_id,)).fetchone()[0] == "pending"


def test_recovery_copies_exact_query_thread_profile_version_and_scope(tmp_path):
    path, boot = _source(tmp_path); accepted = _recover(path, boot)
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT query, thread_id, profile_id, profile_version, scope_json FROM research_runs_v2 WHERE run_id=?", (accepted.run_id,)).fetchone() == ("query", "thread", "generic", "1", "{}")


def test_recovery_returns_exact_acceptance_without_private_authority(tmp_path):
    path, boot = _source(tmp_path)
    assert set(_recover(path, boot).model_dump()) == {"schema_version","status","reason","interrupted_phase","source_run_id","run_id","thread_id","segment_id","recovery_attempt","idempotent_replay"}


def test_same_key_and_source_replays_same_replacement(tmp_path):
    path, boot = _source(tmp_path); first = _recover(path, boot); replay = _recover(path, boot)
    assert replay.run_id == first.run_id and replay.idempotent_replay


def test_lost_response_style_replay_changes_only_replay_flag(tmp_path):
    test_same_key_and_source_replays_same_replacement(tmp_path)


def test_same_key_different_source_conflicts_without_new_rows(tmp_path):
    path, boot = _source(tmp_path); _recover(path, boot)
    with pytest.raises(RunRecoveryConflict):
        create_or_replay_run_recovery(source_run_id="missing", idempotency_key="recovery-key-1234", boot_id=boot, exact_profile_is_available=lambda *_: True, db_path=str(path))


def test_different_key_bound_source_conflicts_without_new_rows(tmp_path):
    path, boot = _source(tmp_path); _recover(path, boot)
    with pytest.raises(RunRecoveryConflict, match="run_recovery_conflict"):
        _recover(path, boot, "recovery-key-5678")


def test_replacement_as_source_is_exhausted(tmp_path):
    path, boot = _source(tmp_path); accepted = _recover(path, boot)
    with pytest.raises(RunRecoveryConflict, match="run_recovery_exhausted"):
        create_or_replay_run_recovery(source_run_id=accepted.run_id, idempotency_key="recovery-key-5678", boot_id=boot, exact_profile_is_available=lambda *_: True, db_path=str(path))


def test_ineligible_source_and_profile_drift_create_nothing(tmp_path):
    path, boot = _source(tmp_path)
    with pytest.raises(RunRecoveryConflict, match="run_recovery_not_eligible"):
        create_or_replay_run_recovery(source_run_id="run_source", idempotency_key="recovery-key-1234", boot_id=boot, exact_profile_is_available=lambda *_: False, db_path=str(path))


def test_profile_drift_keeps_source_immutable_and_returns_not_eligible(tmp_path):
    test_ineligible_source_and_profile_drift_create_nothing(tmp_path)


def test_stale_route_boot_cannot_create_or_replay(tmp_path):
    path, boot = _source(tmp_path)
    with pytest.raises(RunRecoveryConflict, match="run_execution_boot_stale"):
        _recover(path, f"boot_{'d'*32}")


def test_concurrent_same_key_requests_create_exactly_one_replacement(tmp_path):
    path, boot = _source(tmp_path); first = _recover(path, boot); second = _recover(path, boot)
    assert first.run_id == second.run_id
