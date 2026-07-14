import concurrent.futures
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from api.run_dispatch_models import RunDispatchConflict
from api.run_dispatch_repository import (
    claim_run_dispatch,
    dispatch_attempt_is_started,
    get_run_dispatch,
    release_run_dispatch_for_retry,
    start_run_dispatch,
)
from api.run_repository import create_run


NOW = datetime(2026, 7, 14, tzinfo=timezone.utc)
WORKER_1 = "dispatch_worker_00000000000000000000000000000001"
WORKER_2 = "dispatch_worker_00000000000000000000000000000002"


def _claim(db_path, run_id=None, worker_id=WORKER_1, now=NOW):
    return claim_run_dispatch(
        db_path=db_path,
        worker_id=worker_id,
        lease_seconds=30,
        run_id=run_id,
        now=now,
    )


def test_get_pending_dispatch_and_claim_oldest_first(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    first = create_run(db_path=db_path, thread_id="thread-1", query="first")
    second = create_run(db_path=db_path, thread_id="thread-2", query="second")
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                "UPDATE run_dispatches_v1 SET created_at = ? WHERE run_id = ?",
                ("2026-07-14T00:00:00+00:00", first["run_id"]),
            )
            connection.execute(
                "UPDATE run_dispatches_v1 SET created_at = ? WHERE run_id = ?",
                ("2026-07-14T00:00:01+00:00", second["run_id"]),
            )
    finally:
        connection.close()

    assert get_run_dispatch(db_path=db_path, run_id=first["run_id"])["status"] == "pending"
    claim = _claim(db_path)

    assert claim.run_id == first["run_id"]
    assert claim.attempt_count == 1
    assert claim.lease_owner == WORKER_1
    assert get_run_dispatch(db_path=db_path, run_id=second["run_id"])["status"] == "pending"


def test_targeted_claim_only_claims_requested_run(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    first = create_run(db_path=db_path, thread_id="thread-1", query="first")
    second = create_run(db_path=db_path, thread_id="thread-2", query="second")

    claim = _claim(db_path, run_id=second["run_id"])

    assert claim.run_id == second["run_id"]
    assert get_run_dispatch(db_path=db_path, run_id=first["run_id"])["status"] == "pending"


def test_same_worker_old_attempt_cannot_start_after_reclaim(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="research")
    first = _claim(db_path, run_id=created["run_id"])
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                "UPDATE run_dispatches_v1 SET lease_expires_at = ? WHERE run_id = ?",
                ((NOW - timedelta(seconds=1)).isoformat(), created["run_id"]),
            )
    finally:
        connection.close()

    second = _claim(
        db_path,
        run_id=created["run_id"],
        worker_id=first.lease_owner,
        now=NOW + timedelta(minutes=1),
    )

    assert second.attempt_count == first.attempt_count + 1
    assert start_run_dispatch(db_path=db_path, claim=first) is False
    assert start_run_dispatch(db_path=db_path, claim=second) is True


def test_start_fence_atomically_starts_dispatch_run_and_segment(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    created = create_run(
        db_path=db_path,
        thread_id="thread-1",
        query="research",
        scope={"region": "cn"},
    )
    claim = _claim(db_path, run_id=created["run_id"])

    assert start_run_dispatch(db_path=db_path, claim=claim) is True
    assert dispatch_attempt_is_started(db_path=db_path, claim=claim) is True

    connection = sqlite3.connect(db_path)
    try:
        dispatch = connection.execute(
            "SELECT status, lease_owner, lease_expires_at, started_at, last_error_code "
            "FROM run_dispatches_v1 WHERE run_id = ?",
            (created["run_id"],),
        ).fetchone()
        run = connection.execute(
            "SELECT execution_status, state_version FROM research_runs_v2 WHERE run_id = ?",
            (created["run_id"],),
        ).fetchone()
        segment = connection.execute(
            "SELECT status FROM run_segments WHERE segment_id = ?",
            (created["segment_id"],),
        ).fetchone()
    finally:
        connection.close()

    assert dispatch[0] == "started"
    assert dispatch[1:3] == (None, None)
    assert dispatch[3] is not None
    assert dispatch[4] is None
    assert run == ("running", 1)
    assert segment == ("running",)


def test_start_rejects_stale_owner_and_claim_payload_mismatch(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="research")
    claim = _claim(db_path, run_id=created["run_id"])
    stale_owner = claim.model_copy(update={"lease_owner": WORKER_2})
    changed_query = claim.model_copy(update={"query": "different"})

    assert start_run_dispatch(db_path=db_path, claim=stale_owner) is False
    assert start_run_dispatch(db_path=db_path, claim=changed_query) is False
    assert get_run_dispatch(db_path=db_path, run_id=created["run_id"])["status"] == "leased"


def test_concurrent_connections_admit_one_claim(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="research")

    def claim(worker_id):
        return _claim(db_path, run_id=created["run_id"], worker_id=worker_id)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, [WORKER_1, WORKER_2]))

    assert sum(item is not None for item in claims) == 1
    assert get_run_dispatch(db_path=db_path, run_id=created["run_id"])["attempt_count"] == 1


def test_retry_release_is_exact_and_retains_bounded_code(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="research")
    claim = _claim(db_path, run_id=created["run_id"])
    stale = claim.model_copy(update={"attempt_count": claim.attempt_count + 1})

    assert release_run_dispatch_for_retry(
        db_path=db_path,
        claim=stale,
        error_code="run_dispatch_schedule_failed",
    ) == "stale"
    assert release_run_dispatch_for_retry(
        db_path=db_path,
        claim=claim,
        error_code="run_dispatch_schedule_failed",
    ) == "retry"

    row = get_run_dispatch(db_path=db_path, run_id=created["run_id"])
    assert row["status"] == "pending"
    assert row["lease_owner"] is None
    assert row["last_error_code"] == "run_dispatch_schedule_failed"


@pytest.mark.parametrize(
    "error_code",
    ["", "has space", "credential=/private/token", "A" * 129],
)
def test_retry_rejects_unbounded_error_codes(tmp_path, error_code):
    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="research")
    claim = _claim(db_path, run_id=created["run_id"])

    with pytest.raises(ValueError, match="run_dispatch_error_code_invalid"):
        release_run_dispatch_for_retry(
            db_path=db_path,
            claim=claim,
            error_code=error_code,
        )


def test_third_failed_claim_fails_dispatch_run_and_segment_consistently(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="secret query")
    outcomes = []
    for attempt in range(1, 4):
        claim = _claim(
            db_path,
            run_id=created["run_id"],
            now=NOW + timedelta(minutes=attempt),
        )
        outcomes.append(
            release_run_dispatch_for_retry(
                db_path=db_path,
                claim=claim,
                error_code="run_dispatch_schedule_failed",
            )
        )

    assert outcomes == ["retry", "retry", "failed"]
    connection = sqlite3.connect(db_path)
    try:
        dispatch = connection.execute(
            "SELECT status, attempt_count, last_error_code, lease_owner "
            "FROM run_dispatches_v1 WHERE run_id = ?",
            (created["run_id"],),
        ).fetchone()
        run = connection.execute(
            "SELECT execution_status, review_status, delivery_status, state_version "
            "FROM research_runs_v2 WHERE run_id = ?",
            (created["run_id"],),
        ).fetchone()
        segment = connection.execute(
            "SELECT status FROM run_segments WHERE segment_id = ?",
            (created["segment_id"],),
        ).fetchone()
    finally:
        connection.close()

    assert dispatch == ("failed", 3, "run_dispatch_schedule_failed", None)
    assert run == ("failed", "not_required", "failed", 1)
    assert segment == ("failed",)
    assert "secret query" not in str(dispatch)


def test_expired_third_claim_is_failed_before_scanning_next_pending_run(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    exhausted = create_run(
        db_path=db_path,
        thread_id="thread-1",
        query="exhausted",
    )
    pending = create_run(
        db_path=db_path,
        thread_id="thread-2",
        query="pending",
    )
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                "UPDATE run_dispatches_v1 SET created_at = ? WHERE run_id = ?",
                ("2026-07-14T00:00:00+00:00", exhausted["run_id"]),
            )
            connection.execute(
                "UPDATE run_dispatches_v1 SET created_at = ? WHERE run_id = ?",
                ("2026-07-14T00:00:01+00:00", pending["run_id"]),
            )
    finally:
        connection.close()

    claims = []
    for attempt in range(1, 4):
        claim = _claim(
            db_path,
            run_id=exhausted["run_id"],
            now=NOW + timedelta(minutes=attempt),
        )
        claims.append(claim)
        connection = sqlite3.connect(db_path)
        try:
            with connection:
                connection.execute(
                    "UPDATE run_dispatches_v1 SET lease_expires_at = ? WHERE run_id = ?",
                    (
                        (NOW + timedelta(minutes=attempt, seconds=-1)).isoformat(),
                        exhausted["run_id"],
                    ),
                )
        finally:
            connection.close()

    next_claim = _claim(db_path, now=NOW + timedelta(minutes=4))

    assert [claim.attempt_count for claim in claims] == [1, 2, 3]
    assert next_claim.run_id == pending["run_id"]
    assert next_claim.attempt_count == 1
    dispatch = get_run_dispatch(db_path=db_path, run_id=exhausted["run_id"])
    assert dispatch["status"] == "failed"
    assert dispatch["attempt_count"] == 3
    assert dispatch["last_error_code"] == "run_dispatch_lease_expired"
    connection = sqlite3.connect(db_path)
    try:
        run = connection.execute(
            "SELECT execution_status, delivery_status FROM research_runs_v2 WHERE run_id = ?",
            (exhausted["run_id"],),
        ).fetchone()
        segment = connection.execute(
            "SELECT status FROM run_segments WHERE segment_id = ?",
            (exhausted["segment_id"],),
        ).fetchone()
    finally:
        connection.close()
    assert run == ("failed", "failed")
    assert segment == ("failed",)
    assert start_run_dispatch(db_path=db_path, claim=claims[-1]) is False


def test_claim_fails_closed_for_noncanonical_scope(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="research")
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                "UPDATE research_runs_v2 SET scope_json = ? WHERE run_id = ?",
                ('{"b": 1}', created["run_id"]),
            )
    finally:
        connection.close()

    with pytest.raises(RunDispatchConflict, match="run_dispatch_state_invalid"):
        _claim(db_path, run_id=created["run_id"])
    assert get_run_dispatch(db_path=db_path, run_id=created["run_id"])["status"] == "pending"


def test_claim_fails_closed_for_missing_initial_segment(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="research")
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                "DELETE FROM run_segments WHERE segment_id = ?",
                (created["segment_id"],),
            )
    finally:
        connection.close()

    with pytest.raises(RunDispatchConflict, match="run_dispatch_state_invalid"):
        _claim(db_path, run_id=created["run_id"])


def test_terminal_or_wrong_version_run_cannot_be_claimed(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    terminal = create_run(db_path=db_path, thread_id="thread-1", query="terminal")
    wrong_version = create_run(db_path=db_path, thread_id="thread-2", query="version")
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                "UPDATE research_runs_v2 SET execution_status = 'failed', state_version = 1 "
                "WHERE run_id = ?",
                (terminal["run_id"],),
            )
            connection.execute(
                "UPDATE research_runs_v2 SET state_version = 2 WHERE run_id = ?",
                (wrong_version["run_id"],),
            )
    finally:
        connection.close()

    assert _claim(db_path, run_id=terminal["run_id"]) is None
    assert _claim(db_path, run_id=wrong_version["run_id"]) is None
