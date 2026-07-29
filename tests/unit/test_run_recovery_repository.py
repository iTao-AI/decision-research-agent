from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import sqlite3
import threading

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
    path, boot = _source(tmp_path)
    barrier = threading.Barrier(3)

    def recover_after_barrier():
        barrier.wait(timeout=5)
        return _recover(path, boot)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(recover_after_barrier) for _ in range(2)]
        barrier.wait(timeout=5)
        accepted = [future.result(timeout=10) for future in futures]

    assert accepted[0].run_id == accepted[1].run_id
    assert sorted(item.idempotent_replay for item in accepted) == [False, True]
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM run_recovery_retries_v1"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM research_runs_v2"
        ).fetchone()[0] == 2


def test_same_key_replay_ignores_current_profile_availability(tmp_path):
    path, boot = _source(tmp_path)
    first = _recover(path, boot)
    profile_calls = []
    replay = create_or_replay_run_recovery(
        source_run_id="run_source",
        idempotency_key="recovery-key-1234",
        boot_id=boot,
        exact_profile_is_available=lambda *values: profile_calls.append(values)
        or False,
        db_path=str(path),
    )
    assert replay.run_id == first.run_id
    assert replay.idempotent_replay is True
    assert profile_calls == []


def _row_counts(path):
    with sqlite3.connect(path) as connection:
        return tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "research_runs_v2",
                "run_segments",
                "run_dispatches_v1",
                "run_recovery_retries_v1",
            )
        )


@pytest.mark.parametrize(
    "corruption",
    [
        "replacement_run",
        "replacement_segment_missing",
        "replacement_segment_drift",
        "replacement_dispatch_missing",
        "replacement_dispatch_drift",
        "lineage_schema",
        "lineage_attempt",
        "lineage_reason",
        "lineage_phase",
        "lineage_hash",
    ],
)
def test_same_key_replay_requires_complete_durable_binding(
    tmp_path,
    corruption,
):
    path, boot = _source(tmp_path)
    accepted = _recover(path, boot)
    with sqlite3.connect(path) as connection:
        if corruption in {"lineage_schema", "lineage_attempt"}:
            connection.execute("PRAGMA ignore_check_constraints=ON")
        mutations = {
            "replacement_run": (
                "UPDATE research_runs_v2 SET query='drift' WHERE run_id=?",
                (accepted.run_id,),
            ),
            "replacement_segment_missing": (
                "DELETE FROM run_segments WHERE run_id=?",
                (accepted.run_id,),
            ),
            "replacement_segment_drift": (
                "UPDATE run_segments SET attempt=2 WHERE run_id=?",
                (accepted.run_id,),
            ),
            "replacement_dispatch_missing": (
                "DELETE FROM run_dispatches_v1 WHERE run_id=?",
                (accepted.run_id,),
            ),
            "replacement_dispatch_drift": (
                "UPDATE run_dispatches_v1 SET status='leased', "
                "lease_owner='dispatch_worker_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', "
                "lease_expires_at='2026-07-29T01:00:00+00:00' WHERE run_id=?",
                (accepted.run_id,),
            ),
            "lineage_schema": (
                "UPDATE run_recovery_retries_v1 SET request_schema_version='wrong'",
                (),
            ),
            "lineage_attempt": (
                "UPDATE run_recovery_retries_v1 SET recovery_attempt=2",
                (),
            ),
            "lineage_reason": (
                "UPDATE run_recovery_retries_v1 SET recovery_reason="
                "'pre_v1_running_without_owner'",
                (),
            ),
            "lineage_phase": (
                "UPDATE run_recovery_retries_v1 SET interrupted_phase='finalization'",
                (),
            ),
            "lineage_hash": (
                "UPDATE run_recovery_retries_v1 SET request_hash='wrong'",
                (),
            ),
        }
        sql, params = mutations[corruption]
        connection.execute(sql, params)
    before = _row_counts(path)
    with pytest.raises(RunRecoveryConflict, match="run_recovery_state_invalid"):
        _recover(path, boot)
    assert _row_counts(path) == before


@pytest.mark.parametrize(
    ("sql", "params"),
    [
        (
            "UPDATE run_execution_owners_v1 SET segment_id='run_source_seg_bad'",
            (),
        ),
        ("UPDATE run_execution_owners_v1 SET recovery_reason=NULL", ()),
        ("UPDATE run_execution_owners_v1 SET phase='finalization'", ()),
        (
            "UPDATE run_failure_causes_v1 SET code='run_timeout'",
            (),
        ),
        (
            "UPDATE run_failure_causes_v1 SET observation_status='unobserved'",
            (),
        ),
        (
            "UPDATE run_failure_causes_v1 SET terminal_state_version=1",
            (),
        ),
        (
            "UPDATE run_segments SET kind='continuation'",
            (),
        ),
        (
            "UPDATE run_segments SET sequence=1",
            (),
        ),
        (
            "UPDATE run_segments SET attempt=2",
            (),
        ),
        (
            "UPDATE run_segments SET updated_at='2026-07-29T02:00:00+00:00'",
            (),
        ),
        (
            "UPDATE run_execution_owners_v1 "
            "SET closed_at='2026-07-29T02:00:00+00:00'",
            (),
        ),
        (
            "UPDATE run_execution_owners_v1 "
            "SET phase_updated_at='2026-07-29T02:00:00+00:00'",
            (),
        ),
        (
            "UPDATE run_failure_causes_v1 "
            "SET recorded_at='2026-07-29T02:00:00+00:00'",
            (),
        ),
        (
            "UPDATE research_runs_v2 "
            "SET updated_at='2026-07-29T02:00:00+00:00'",
            (),
        ),
    ],
)
def test_corrupt_interrupted_source_fails_before_profile_or_mutation(
    tmp_path,
    sql,
    params,
):
    path, boot = _source(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(sql, params)
    before = _row_counts(path)
    profile_calls = []
    with pytest.raises(RunRecoveryConflict, match="run_recovery_state_invalid"):
        create_or_replay_run_recovery(
            source_run_id="run_source",
            idempotency_key="recovery-key-1234",
            boot_id=boot,
            exact_profile_is_available=lambda *values: profile_calls.append(values)
            or True,
            db_path=str(path),
        )
    assert profile_calls == []
    assert _row_counts(path) == before


def test_different_key_bound_source_conflicts_before_profile_eligibility(tmp_path):
    path, boot = _source(tmp_path)
    _recover(path, boot)
    profile_calls = []
    with pytest.raises(RunRecoveryConflict, match="run_recovery_conflict"):
        create_or_replay_run_recovery(
            source_run_id="run_source",
            idempotency_key="recovery-key-different",
            boot_id=boot,
            exact_profile_is_available=lambda *values: profile_calls.append(values)
            or False,
            db_path=str(path),
        )
    assert profile_calls == []
