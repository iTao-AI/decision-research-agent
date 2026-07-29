from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from itertools import combinations
import sqlite3
import threading

import pytest

from api.run_dispatch_repository import (
    claim_run_dispatch,
    release_run_dispatch_for_retry,
    start_run_dispatch,
)
from api.run_execution_repository import (
    activate_run_execution_boot,
    advance_run_execution_phase,
)
from api.run_failure_cause_models import RunFailureCauseWrite
from api.run_recovery_lifecycle import (
    LifecycleFamily,
    LifecycleRole,
    LifecycleStateInvalid,
    RecoveryLifecycleSnapshot,
    classify_recovery_lifecycle,
)
from api.run_recovery_models import RunRecoveryConflict
from api.run_recovery_repository import create_or_replay_run_recovery
from api.run_repository import finalize_run_transaction
from tests.unit.test_run_execution_repository import _active, _database
from tests.unit.test_run_recovery_lifecycle import FIELD_GROUPS, GROUP_FIELDS


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


def _claim_replacement(path, boot, run_id, *, worker_hex="d"):
    claim = claim_run_dispatch(
        db_path=str(path),
        worker_id=f"dispatch_worker_{worker_hex * 32}",
        boot_id=boot,
        lease_seconds=30,
        run_id=run_id,
    )
    assert claim is not None
    return claim


def _replacement_snapshot(path, run_id):
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT dispatch.run_id, dispatch.status AS dispatch_status,
                   dispatch.lease_owner, dispatch.lease_expires_at,
                   dispatch.attempt_count, dispatch.last_error_code,
                   dispatch.created_at AS dispatch_created_at,
                   dispatch.updated_at AS dispatch_updated_at,
                   dispatch.started_at,
                   run.execution_status, run.review_status,
                   run.delivery_status, run.state_version,
                   run.created_at AS run_created_at,
                   run.updated_at AS run_updated_at,
                   segment.segment_id, segment.run_id AS segment_run_id,
                   segment.kind, segment.sequence,
                   segment.attempt AS segment_attempt,
                   segment.status AS segment_status,
                   segment.created_at AS segment_created_at,
                   segment.updated_at AS segment_updated_at,
                   owner.segment_id AS owner_segment_id,
                   owner.status AS owner_status,
                   owner.phase AS owner_phase,
                   owner.boot_id AS owner_boot_id,
                   owner.owner_id,
                   owner.created_at AS owner_created_at,
                   owner.phase_updated_at AS owner_phase_updated_at,
                   owner.closed_at AS owner_closed_at,
                   owner.recovery_reason,
                   cause.observation_status,
                   cause.terminal_state_version,
                   cause.phase AS cause_phase,
                   cause.code AS cause_code,
                   cause.recorded_at,
                   (
                       SELECT COUNT(*)
                       FROM run_segments AS exact_segment
                       WHERE exact_segment.run_id=run.run_id
                         AND exact_segment.kind='initial'
                         AND exact_segment.sequence=0
                         AND exact_segment.attempt=1
                   ) AS initial_segment_count
            FROM run_dispatches_v1 AS dispatch
            JOIN research_runs_v2 AS run ON run.run_id=dispatch.run_id
            LEFT JOIN run_segments AS segment
              ON segment.run_id=run.run_id
             AND segment.kind='initial'
             AND segment.sequence=0
             AND segment.attempt=1
            LEFT JOIN run_execution_owners_v1 AS owner
              ON owner.run_id=run.run_id
            LEFT JOIN run_failure_causes_v1 AS cause
              ON cause.run_id=run.run_id
            WHERE run.run_id=?
            """,
            (run_id,),
        ).fetchone()
    assert row is not None
    return RecoveryLifecycleSnapshot(
        **{
            field_name: row[field_name]
            for field_name in RecoveryLifecycleSnapshot.__dataclass_fields__
        }
    )


def _producer_replacement_snapshot(tmp_path, family):
    root = tmp_path / family
    root.mkdir()
    path, boot = _source(root)
    accepted = _recover(path, boot)
    if family.startswith("initial"):
        return _replacement_snapshot(path, accepted.run_id), boot

    claim = _claim_replacement(path, boot, accepted.run_id)
    if family == "leased":
        return _replacement_snapshot(path, accepted.run_id), boot
    owner = start_run_dispatch(db_path=str(path), claim=claim)
    assert owner is not None
    if family == "running_execution":
        return _replacement_snapshot(path, accepted.run_id), boot
    if family == "later_boot_interrupted":
        boot = f"boot_{'e' * 32}"
        activate_run_execution_boot(db_path=str(path), boot_id=boot)
        return _replacement_snapshot(path, accepted.run_id), boot
    if family in {"closed_completed", "closed_failed_finalization"}:
        assert advance_run_execution_phase(db_path=str(path), handle=owner)
    if family == "closed_completed":
        assert finalize_run_transaction(
            run_id=accepted.run_id,
            segment_id=accepted.segment_id,
            expected_state_version=1,
            allowed_previous_statuses={"running"},
            execution_status="completed",
            delivery_status="ready",
            evidence_entries=[],
            owner_handle=owner,
            db_path=str(path),
        )
    elif family == "closed_failed_finalization":
        assert finalize_run_transaction(
            run_id=accepted.run_id,
            segment_id=accepted.segment_id,
            expected_state_version=1,
            allowed_previous_statuses={"running"},
            execution_status="failed",
            delivery_status="failed",
            evidence_entries=[],
            failure_cause=RunFailureCauseWrite(
                phase="finalization",
                code="run_finalization_failed",
            ),
            owner_handle=owner,
            db_path=str(path),
        )
    elif family in {
        "closed_failed_execution",
        "closed_failed_execution_alt",
    }:
        assert finalize_run_transaction(
            run_id=accepted.run_id,
            segment_id=accepted.segment_id,
            expected_state_version=1,
            allowed_previous_statuses={"running"},
            execution_status="failed",
            delivery_status="failed",
            evidence_entries=[],
            failure_cause=RunFailureCauseWrite(
                phase="execution",
                code=(
                    "execution_error"
                    if family == "closed_failed_execution"
                    else "call_budget_exceeded"
                ),
            ),
            owner_handle=owner,
            db_path=str(path),
        )
    else:
        raise AssertionError(f"unsupported producer family: {family}")
    return _replacement_snapshot(path, accepted.run_id), boot


def _replace_snapshot_group(snapshot, donor, group):
    return replace(
        snapshot,
        **{
            field_name: getattr(donor, field_name)
            for field_name in GROUP_FIELDS[group]
        },
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


def test_same_key_replay_rejects_mixed_replacement_lifecycle(tmp_path):
    path, boot = _source(tmp_path)
    accepted = _recover(path, boot)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE research_runs_v2
            SET execution_status='failed', review_status='not_required',
                delivery_status='pending', state_version=1
            WHERE run_id=?
            """,
            (accepted.run_id,),
        )
        connection.execute(
            "UPDATE run_segments SET status='completed' WHERE run_id=?",
            (accepted.run_id,),
        )
        connection.execute(
            """
            UPDATE run_dispatches_v1
            SET status='started', attempt_count=1, started_at=updated_at
            WHERE run_id=?
            """,
            (accepted.run_id,),
        )
    with pytest.raises(RunRecoveryConflict, match="run_recovery_state_invalid"):
        _recover(path, boot)


def test_same_key_replay_accepts_real_production_dispatch_lease(tmp_path):
    path, boot = _source(tmp_path)
    accepted = _recover(path, boot)
    _claim_replacement(path, boot, accepted.run_id)
    replay = _recover(path, boot)
    assert replay.run_id == accepted.run_id
    assert replay.segment_id == accepted.segment_id
    assert replay.idempotent_replay is True


@pytest.mark.parametrize(
    "lifecycle",
    [
        "initial_pending",
        "retry_pending",
        "leased",
        "running_execution",
        "running_finalization",
        "closed_terminal",
        "prestart_failed",
        "dispatch_exhausted",
        "later_boot_interrupted",
    ],
)
def test_same_key_replay_accepts_each_producer_derived_replacement_family(
    tmp_path,
    lifecycle,
):
    path, boot = _source(tmp_path)
    accepted = _recover(path, boot)
    if lifecycle not in {"initial_pending", "prestart_failed"}:
        claim = _claim_replacement(path, boot, accepted.run_id)
        if lifecycle == "retry_pending":
            assert (
                release_run_dispatch_for_retry(
                    db_path=str(path),
                    claim=claim,
                    error_code="run_dispatch_schedule_failed",
                )
                == "retry"
            )
        elif lifecycle in {
            "running_execution",
            "running_finalization",
            "closed_terminal",
            "later_boot_interrupted",
        }:
            owner = start_run_dispatch(db_path=str(path), claim=claim)
            assert owner is not None
            if lifecycle in {"running_finalization", "closed_terminal"}:
                assert advance_run_execution_phase(
                    db_path=str(path),
                    handle=owner,
                )
            if lifecycle == "closed_terminal":
                assert finalize_run_transaction(
                    run_id=accepted.run_id,
                    segment_id=accepted.segment_id,
                    expected_state_version=1,
                    allowed_previous_statuses={"running"},
                    execution_status="completed",
                    delivery_status="ready",
                    evidence_entries=[],
                    owner_handle=owner,
                    db_path=str(path),
                )
            elif lifecycle == "later_boot_interrupted":
                boot = f"boot_{'e' * 32}"
                result = activate_run_execution_boot(
                    db_path=str(path),
                    boot_id=boot,
                )
                assert result.interrupted_execution_count == 1
        elif lifecycle == "dispatch_exhausted":
            for attempt in range(1, 4):
                assert claim.attempt_count == attempt
                outcome = release_run_dispatch_for_retry(
                    db_path=str(path),
                    claim=claim,
                    error_code="run_dispatch_schedule_failed",
                )
                if attempt < 3:
                    assert outcome == "retry"
                    claim = _claim_replacement(
                        path,
                        boot,
                        accepted.run_id,
                        worker_hex=str(attempt),
                    )
                else:
                    assert outcome == "failed"
    if lifecycle == "prestart_failed":
        assert finalize_run_transaction(
            run_id=accepted.run_id,
            segment_id=accepted.segment_id,
            expected_state_version=0,
            allowed_previous_statuses={"pending"},
            execution_status="failed",
            delivery_status="failed",
            evidence_entries=[],
            failure_cause=RunFailureCauseWrite(
                phase="execution",
                code="cancelled",
            ),
            db_path=str(path),
        )

    replay = _recover(path, boot)
    assert replay.run_id == accepted.run_id
    assert replay.segment_id == accepted.segment_id
    assert replay.idempotent_replay is True
    if lifecycle == "later_boot_interrupted":
        with pytest.raises(RunRecoveryConflict, match="run_recovery_exhausted"):
            create_or_replay_run_recovery(
                source_run_id=accepted.run_id,
                idempotency_key="recovery-key-second-hop",
                boot_id=boot,
                exact_profile_is_available=lambda *_: True,
                db_path=str(path),
            )


@pytest.mark.parametrize(
    "mixed_case",
    [
        "pending_segment_terminal",
        "leased_run_started_without_owner",
        "running_dispatch_released",
        "closed_terminal_segment_drift",
        "dispatch_failed_cause_drift",
        "interrupted_terminal_timestamp_drift",
    ],
)
def test_same_key_replay_rejects_each_pairwise_family_cross_product(
    tmp_path,
    mixed_case,
):
    path, boot = _source(tmp_path)
    accepted = _recover(path, boot)
    claim = None
    owner = None
    if mixed_case != "pending_segment_terminal":
        claim = _claim_replacement(path, boot, accepted.run_id)
    if mixed_case in {
        "running_dispatch_released",
        "closed_terminal_segment_drift",
        "interrupted_terminal_timestamp_drift",
    }:
        owner = start_run_dispatch(db_path=str(path), claim=claim)
        assert owner is not None
    if mixed_case == "closed_terminal_segment_drift":
        assert advance_run_execution_phase(db_path=str(path), handle=owner)
        assert finalize_run_transaction(
            run_id=accepted.run_id,
            segment_id=accepted.segment_id,
            expected_state_version=1,
            allowed_previous_statuses={"running"},
            execution_status="completed",
            delivery_status="ready",
            evidence_entries=[],
            owner_handle=owner,
            db_path=str(path),
        )
    elif mixed_case == "dispatch_failed_cause_drift":
        for attempt in range(1, 4):
            assert claim is not None and claim.attempt_count == attempt
            outcome = release_run_dispatch_for_retry(
                db_path=str(path),
                claim=claim,
                error_code="run_dispatch_schedule_failed",
            )
            if attempt < 3:
                assert outcome == "retry"
                claim = _claim_replacement(
                    path,
                    boot,
                    accepted.run_id,
                    worker_hex=str(attempt),
                )
            else:
                assert outcome == "failed"
    elif mixed_case == "interrupted_terminal_timestamp_drift":
        boot = f"boot_{'e' * 32}"
        activate_run_execution_boot(db_path=str(path), boot_id=boot)

    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        mutations = {
            "pending_segment_terminal": (
                "UPDATE run_segments SET status='completed' WHERE run_id=?",
                (accepted.run_id,),
            ),
            "leased_run_started_without_owner": (
                """
                UPDATE research_runs_v2
                SET execution_status='running', state_version=1
                WHERE run_id=?
                """,
                (accepted.run_id,),
            ),
            "running_dispatch_released": (
                """
                UPDATE run_dispatches_v1
                SET status='leased',
                    lease_owner='dispatch_worker_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                    lease_expires_at='2026-07-30T00:00:00+00:00',
                    started_at=NULL
                WHERE run_id=?
                """,
                (accepted.run_id,),
            ),
            "closed_terminal_segment_drift": (
                "UPDATE run_segments SET status='failed' WHERE run_id=?",
                (accepted.run_id,),
            ),
            "dispatch_failed_cause_drift": (
                """
                UPDATE run_failure_causes_v1
                SET code='run_dispatch_start_timeout'
                WHERE run_id=?
                """,
                (accepted.run_id,),
            ),
            "interrupted_terminal_timestamp_drift": (
                """
                UPDATE run_execution_owners_v1
                SET closed_at='2026-07-30T00:00:00+00:00'
                WHERE run_id=?
                """,
                (accepted.run_id,),
            ),
        }
        sql, params = mutations[mixed_case]
        connection.execute(sql, params)

    with pytest.raises(RunRecoveryConflict, match="run_recovery_state_invalid"):
        _recover(path, boot)


def test_full_pairwise_matrix_uses_producer_derived_legal_families(tmp_path):
    produced = {
        family: _producer_replacement_snapshot(tmp_path, family)[0]
        for family in (
            "initial_pending",
            "initial_lineage",
            "leased",
            "running_execution",
            "later_boot_interrupted",
            "closed_completed",
            "closed_failed_execution",
            "closed_failed_execution_alt",
            "closed_failed_finalization",
        )
    }
    base = produced["initial_pending"]
    donors = {
        "run": produced["running_execution"],
        "segment": produced["running_execution"],
        "dispatch": produced["leased"],
        "owner": produced["running_execution"],
        "cause": produced["later_boot_interrupted"],
        "boot": produced["running_execution"],
        "timestamp": produced["running_execution"],
        "lineage": produced["initial_lineage"],
    }
    pairs = tuple(combinations(FIELD_GROUPS, 2))
    assert len(pairs) == 28

    for left_group, right_group in pairs:
        if (left_group, right_group) == ("owner", "cause"):
            mixed = _replace_snapshot_group(
                produced["closed_failed_execution"],
                produced["closed_failed_finalization"],
                "owner",
            )
            mixed = _replace_snapshot_group(
                mixed,
                produced["closed_failed_execution_alt"],
                "cause",
            )
        elif (left_group, right_group) == ("owner", "timestamp"):
            closed = produced["closed_completed"]
            owner_donor = replace(
                closed,
                started_at="2026-07-29T02:00:00+00:00",
                owner_created_at="2026-07-29T02:00:00+00:00",
            )
            timestamp_donor = replace(
                closed,
                dispatch_updated_at="2026-07-29T03:00:00+00:00",
                started_at="2026-07-29T03:00:00+00:00",
                run_updated_at="2026-07-29T03:01:00+00:00",
                segment_updated_at="2026-07-29T03:01:00+00:00",
                owner_phase_updated_at="2026-07-29T03:01:00+00:00",
                owner_closed_at="2026-07-29T03:01:00+00:00",
            )
            mixed = _replace_snapshot_group(closed, owner_donor, "owner")
            mixed = _replace_snapshot_group(
                mixed,
                timestamp_donor,
                "timestamp",
            )
        else:
            mixed = _replace_snapshot_group(
                base,
                donors[left_group],
                left_group,
            )
            mixed = _replace_snapshot_group(
                mixed,
                donors[right_group],
                right_group,
            )

        if (left_group, right_group) == ("dispatch", "lineage"):
            assert (
                classify_recovery_lifecycle(
                    mixed,
                    role=LifecycleRole.RECOVERY_REPLACEMENT,
                    current_boot_id=f"boot_{'c' * 32}",
                )
                is LifecycleFamily.LEASED
            )
            continue
        with pytest.raises(
            LifecycleStateInvalid,
            match="^lifecycle_state_invalid$",
        ):
            classify_recovery_lifecycle(
                mixed,
                role=LifecycleRole.RECOVERY_REPLACEMENT,
                current_boot_id=f"boot_{'c' * 32}",
            )


def test_same_key_replay_rejects_pending_success_ordinary_escape(tmp_path):
    path, boot = _source(tmp_path)
    accepted = _recover(path, boot)
    terminal = "2026-07-29T12:00:00+00:00"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE research_runs_v2
            SET execution_status='completed', delivery_status='ready',
                state_version=1, updated_at=?
            WHERE run_id=?
            """,
            (terminal, accepted.run_id),
        )
        connection.execute(
            "UPDATE run_segments SET status='completed', updated_at=? "
            "WHERE run_id=?",
            (terminal, accepted.run_id),
        )
    with pytest.raises(RunRecoveryConflict, match="run_recovery_state_invalid"):
        _recover(path, boot)


def test_same_key_replay_rejects_completed_owner_phase_drift(tmp_path):
    path, boot = _source(tmp_path)
    accepted = _recover(path, boot)
    claim = _claim_replacement(path, boot, accepted.run_id)
    owner = start_run_dispatch(db_path=str(path), claim=claim)
    assert owner is not None
    assert advance_run_execution_phase(db_path=str(path), handle=owner)
    assert finalize_run_transaction(
        run_id=accepted.run_id,
        segment_id=accepted.segment_id,
        expected_state_version=1,
        allowed_previous_statuses={"running"},
        execution_status="completed",
        delivery_status="ready",
        evidence_entries=[],
        owner_handle=owner,
        db_path=str(path),
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE run_execution_owners_v1 SET phase='execution' "
            "WHERE run_id=?",
            (accepted.run_id,),
        )
    with pytest.raises(RunRecoveryConflict, match="run_recovery_state_invalid"):
        _recover(path, boot)


def test_same_key_replay_rejects_completed_owner_created_at_drift(tmp_path):
    path, boot = _source(tmp_path)
    accepted = _recover(path, boot)
    claim = _claim_replacement(path, boot, accepted.run_id)
    owner = start_run_dispatch(db_path=str(path), claim=claim)
    assert owner is not None
    assert advance_run_execution_phase(db_path=str(path), handle=owner)
    assert finalize_run_transaction(
        run_id=accepted.run_id,
        segment_id=accepted.segment_id,
        expected_state_version=1,
        allowed_previous_statuses={"running"},
        execution_status="completed",
        delivery_status="ready",
        evidence_entries=[],
        owner_handle=owner,
        db_path=str(path),
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE run_execution_owners_v1 SET created_at=? "
            "WHERE run_id=?",
            ("2030-01-01T00:00:00+00:00", accepted.run_id),
        )

    with pytest.raises(RunRecoveryConflict, match="run_recovery_state_invalid"):
        _recover(path, boot)


def test_same_key_replay_rejects_first_lease_with_prior_error(tmp_path):
    path, boot = _source(tmp_path)
    accepted = _recover(path, boot)
    _claim_replacement(path, boot, accepted.run_id)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE run_dispatches_v1 "
            "SET last_error_code='run_dispatch_schedule_failed' "
            "WHERE run_id=?",
            (accepted.run_id,),
        )
    with pytest.raises(RunRecoveryConflict, match="run_recovery_state_invalid"):
        _recover(path, boot)


def test_same_key_replay_accepts_reclaimed_lease_without_prior_error(tmp_path):
    path, boot = _source(tmp_path)
    accepted = _recover(path, boot)
    first = _claim_replacement(path, boot, accepted.run_id, worker_hex="a")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE run_dispatches_v1 SET lease_expires_at=? WHERE run_id=?",
            ("2020-01-01T00:00:00+00:00", accepted.run_id),
        )
    second = _claim_replacement(path, boot, accepted.run_id, worker_hex="b")
    assert first.attempt_count == 1
    assert second.attempt_count == 2
    replay = _recover(path, boot)
    assert replay.run_id == accepted.run_id
    assert replay.idempotent_replay is True
