from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from api.run_dispatch_repository import (
    claim_run_dispatch,
    start_run_dispatch,
)
from api.run_execution_models import new_boot_id
from api.run_execution_repository import (
    activate_run_execution_boot,
    advance_run_execution_phase,
)
from api.run_recovery_models import RunRecoveryConflict
from api.run_recovery_repository import create_or_replay_run_recovery
from api.run_repository import create_run, finalize_run_transaction


RECOVERY_KEY = "authority-recovery-key-1234"


def _create_recovery_lineage(tmp_path):
    db_path = str(tmp_path / "authority-runs.db")
    source = create_run(
        db_path=db_path,
        thread_id="authority-thread",
        query="authority-query",
    )
    first_boot = new_boot_id()
    activate_run_execution_boot(db_path=db_path, boot_id=first_boot)
    claim = claim_run_dispatch(
        db_path=db_path,
        worker_id="dispatch_worker_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        boot_id=first_boot,
        lease_seconds=30,
        run_id=source["run_id"],
    )
    assert claim is not None
    assert start_run_dispatch(db_path=db_path, claim=claim) is not None

    current_boot = new_boot_id()
    interrupted = activate_run_execution_boot(
        db_path=db_path,
        boot_id=current_boot,
    )
    assert interrupted.interrupted_execution_count == 1
    accepted = create_or_replay_run_recovery(
        source_run_id=source["run_id"],
        idempotency_key=RECOVERY_KEY,
        boot_id=current_boot,
        exact_profile_is_available=lambda profile_id, profile_version: (
            profile_id,
            profile_version,
        )
        == ("generic", "1"),
        db_path=db_path,
    )
    return db_path, current_boot, source["run_id"], accepted


def _replay(db_path: str, boot_id: str, source_run_id: str):
    return create_or_replay_run_recovery(
        source_run_id=source_run_id,
        idempotency_key=RECOVERY_KEY,
        boot_id=boot_id,
        exact_profile_is_available=lambda *_: True,
        db_path=db_path,
    )


def _claim_replacement(
    *,
    db_path: str,
    boot_id: str,
    run_id: str,
    worker: str = "b",
    now: datetime | None = None,
    lease_seconds: int = 30,
):
    claim = claim_run_dispatch(
        db_path=db_path,
        worker_id=f"dispatch_worker_{worker * 32}",
        boot_id=boot_id,
        lease_seconds=lease_seconds,
        run_id=run_id,
        now=now,
    )
    assert claim is not None
    return claim


def test_authority_rejects_pending_success_replacement(tmp_path):
    db_path, boot_id, source_run_id, accepted = _create_recovery_lineage(
        tmp_path
    )
    terminal = "2026-07-29T12:00:00+00:00"
    with sqlite3.connect(db_path) as connection:
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
            """
            UPDATE run_segments
            SET status='completed', updated_at=?
            WHERE run_id=?
            """,
            (terminal, accepted.run_id),
        )

    with pytest.raises(
        RunRecoveryConflict,
        match="run_recovery_state_invalid",
    ):
        _replay(db_path, boot_id, source_run_id)


def test_authority_rejects_completed_replacement_with_execution_phase_owner(
    tmp_path,
):
    db_path, boot_id, source_run_id, accepted = _create_recovery_lineage(
        tmp_path
    )
    claim = _claim_replacement(
        db_path=db_path,
        boot_id=boot_id,
        run_id=accepted.run_id,
    )
    owner = start_run_dispatch(db_path=db_path, claim=claim)
    assert owner is not None
    assert advance_run_execution_phase(db_path=db_path, handle=owner)
    assert finalize_run_transaction(
        db_path=db_path,
        run_id=accepted.run_id,
        segment_id=accepted.segment_id,
        expected_state_version=1,
        allowed_previous_statuses={"running"},
        execution_status="completed",
        delivery_status="ready",
        evidence_entries=[],
        owner_handle=owner,
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE run_execution_owners_v1
            SET phase='execution'
            WHERE run_id=?
            """,
            (accepted.run_id,),
        )

    with pytest.raises(
        RunRecoveryConflict,
        match="run_recovery_state_invalid",
    ):
        _replay(db_path, boot_id, source_run_id)


def test_authority_rejects_first_lease_with_invented_prior_error(tmp_path):
    db_path, boot_id, source_run_id, accepted = _create_recovery_lineage(
        tmp_path
    )
    _claim_replacement(
        db_path=db_path,
        boot_id=boot_id,
        run_id=accepted.run_id,
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE run_dispatches_v1
            SET last_error_code='run_dispatch_schedule_failed'
            WHERE run_id=?
            """,
            (accepted.run_id,),
        )

    with pytest.raises(
        RunRecoveryConflict,
        match="run_recovery_state_invalid",
    ):
        _replay(db_path, boot_id, source_run_id)


def test_authority_accepts_reclaimed_second_lease_without_prior_error(
    tmp_path,
):
    db_path, boot_id, source_run_id, accepted = _create_recovery_lineage(
        tmp_path
    )
    first_claim_at = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    first = _claim_replacement(
        db_path=db_path,
        boot_id=boot_id,
        run_id=accepted.run_id,
        worker="c",
        now=first_claim_at,
        lease_seconds=1,
    )
    assert first.attempt_count == 1
    second = _claim_replacement(
        db_path=db_path,
        boot_id=boot_id,
        run_id=accepted.run_id,
        worker="d",
        now=first_claim_at + timedelta(seconds=2),
        lease_seconds=30,
    )
    assert second.attempt_count == 2

    replay = _replay(db_path, boot_id, source_run_id)
    assert replay.run_id == accepted.run_id
    assert replay.idempotent_replay is True


def test_authority_rejects_closed_owner_on_pending_replacement(tmp_path):
    db_path, boot_id, source_run_id, accepted = _create_recovery_lineage(
        tmp_path
    )
    timestamp = "2026-07-29T12:00:00+00:00"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO run_execution_owners_v1(
                run_id, segment_id, status, phase, boot_id, owner_id,
                created_at, phase_updated_at, closed_at, recovery_reason
            ) VALUES (?, ?, 'closed', 'execution', NULL, NULL, ?, ?, ?, NULL)
            """,
            (
                accepted.run_id,
                accepted.segment_id,
                timestamp,
                timestamp,
                timestamp,
            ),
        )

    with pytest.raises(
        RunRecoveryConflict,
        match="run_recovery_state_invalid",
    ):
        _replay(db_path, boot_id, source_run_id)
