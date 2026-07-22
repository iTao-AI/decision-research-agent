import concurrent.futures
import sqlite3

import pytest


FIXED_TERMINAL_TIME = "2026-07-16T00:00:00+00:00"


def _execution_error_cause():
    from api.run_failure_cause_models import RunFailureCauseWrite

    return RunFailureCauseWrite(
        phase="execution",
        code="execution_error",
    )


def _seed_observed_failed_run(*, db_path, monkeypatch):
    import api.run_repository as repository

    monkeypatch.setattr(repository, "_now", lambda: FIXED_TERMINAL_TIME)
    created = repository.create_run(
        db_path=db_path,
        thread_id="thread-failed",
        query="query",
    )
    assert repository.finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="failed",
        delivery_status="failed",
        evidence_entries=[],
        failure_cause=_execution_error_cause(),
    )
    return created


def _table_snapshot(db_path, table_names):
    connection = sqlite3.connect(db_path)
    try:
        return {
            table_name: connection.execute(
                f"SELECT * FROM {table_name} ORDER BY rowid"
            ).fetchall()
            for table_name in table_names
        }
    finally:
        connection.close()


def test_run_delivery_snapshot_rejects_malformed_current_artifact_ids(tmp_path):
    from api.run_repository import (
        RunDeliverySnapshotConflict,
        create_run,
        get_run_delivery_snapshot,
    )

    db_path = str(tmp_path / "runs.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                """
                CREATE TABLE run_publications_v2 (
                    run_id TEXT NOT NULL,
                    is_current INTEGER NOT NULL,
                    artifact_ids_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO run_publications_v2(
                    run_id, is_current, artifact_ids_json
                ) VALUES (?, 1, ?)
                """,
                (created["run_id"], '{"not":"a-list"}'),
            )
    finally:
        connection.close()

    with pytest.raises(
        RunDeliverySnapshotConflict,
        match="run_delivery_snapshot_corrupt",
    ):
        get_run_delivery_snapshot(db_path=db_path, run_id=created["run_id"])


def test_run_delivery_snapshot_rejects_multiple_current_publications(tmp_path):
    from api.run_repository import (
        RunDeliverySnapshotConflict,
        create_run,
        get_run_delivery_snapshot,
    )

    db_path = str(tmp_path / "runs.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                """
                CREATE TABLE run_publications_v2 (
                    run_id TEXT NOT NULL,
                    is_current INTEGER NOT NULL,
                    artifact_ids_json TEXT NOT NULL
                )
                """
            )
            connection.executemany(
                """
                INSERT INTO run_publications_v2(
                    run_id, is_current, artifact_ids_json
                ) VALUES (?, 1, ?)
                """,
                [
                    (created["run_id"], '["decision-brief.md"]'),
                    (created["run_id"], '["research-report.md"]'),
                ],
            )
    finally:
        connection.close()

    with pytest.raises(
        RunDeliverySnapshotConflict,
        match="run_delivery_snapshot_corrupt",
    ):
        get_run_delivery_snapshot(db_path=db_path, run_id=created["run_id"])


def _assert_corrupt_in_init_and_joined_projection(
    *,
    db_path,
    run_id,
    monkeypatch,
):
    import api.review_repository as review_repository
    from api.run_failure_cause_models import RunFailureCauseConflict
    from api.run_repository import get_run

    with pytest.raises(
        RunFailureCauseConflict,
        match="run_failure_cause_corrupt",
    ):
        get_run(db_path=db_path, run_id=run_id)

    monkeypatch.setattr(
        review_repository,
        "init_review_schema",
        lambda db_path=None: None,
    )
    with pytest.raises(
        RunFailureCauseConflict,
        match="run_failure_cause_corrupt",
    ):
        get_run(db_path=db_path, run_id=run_id)


def test_same_thread_can_own_multiple_independent_runs(tmp_path):
    from api.run_repository import create_run, get_run

    db_path = str(tmp_path / "runs.db")
    first = create_run(db_path=db_path, thread_id="thread-1", query="first")
    second = create_run(db_path=db_path, thread_id="thread-1", query="second")

    assert first["run_id"] != second["run_id"]
    assert first["segment_id"] != second["segment_id"]
    assert get_run(db_path=db_path, run_id=first["run_id"])["query"] == "first"
    assert get_run(db_path=db_path, run_id=second["run_id"])["query"] == "second"


def test_keyed_run_create_replays_original_generated_identity(tmp_path):
    from api.run_repository import create_or_replay_run

    db_path = str(tmp_path / "runs.db")
    kwargs = dict(
        db_path=db_path,
        idempotency_key="run-key-00000001",
        thread_id=None,
        query="query",
        profile_id="generic",
        profile_version="1",
        scope={},
    )
    first = create_or_replay_run(**kwargs)
    second = create_or_replay_run(**kwargs)
    assert first.idempotent_replay is False
    assert second.idempotent_replay is True
    assert second.model_copy(update={"idempotent_replay": False}) == first


def test_keyed_explicit_thread_replays_and_profile_version_is_not_fingerprinted(tmp_path):
    from api.run_repository import create_or_replay_run

    db_path = str(tmp_path / "runs.db")
    first = create_or_replay_run(
        db_path=db_path,
        idempotency_key="run-key-explicit-0001",
        thread_id="thread-1",
        query="query",
        profile_version="1",
        scope={},
    )
    second = create_or_replay_run(
        db_path=db_path,
        idempotency_key="run-key-explicit-0001",
        thread_id="thread-1",
        query="query",
        profile_version="2",
        scope={},
    )
    assert first.thread_id == second.thread_id == "thread-1"
    assert first.run_id == second.run_id
    assert second.idempotent_replay is True


def test_same_key_with_different_request_conflicts_and_creates_nothing(tmp_path):
    from api.run_repository import RunCreationConflict, create_or_replay_run

    db_path = str(tmp_path / "runs.db")
    base = dict(
        db_path=db_path,
        idempotency_key="run-key-00000002",
        thread_id="thread-1",
        profile_id="generic",
        profile_version="1",
        scope={},
    )
    create_or_replay_run(query="first", **base)
    with pytest.raises(RunCreationConflict, match="run_idempotency_conflict"):
        create_or_replay_run(query="second", **base)
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM research_runs_v2").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM run_segments").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM run_create_idempotency_v1").fetchone()[0] == 1
    finally:
        connection.close()


def test_raw_key_is_not_persisted(tmp_path):
    from api.run_repository import create_or_replay_run

    db_path = str(tmp_path / "runs.db")
    raw_key = "raw-key-should-not-persist"
    create_or_replay_run(
        db_path=db_path,
        idempotency_key=raw_key,
        thread_id=None,
        query="query",
        scope={},
    )
    assert raw_key.encode("utf-8") not in (tmp_path / "runs.db").read_bytes()
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT key_hash, request_schema_version, request_hash "
            "FROM run_create_idempotency_v1"
        ).fetchone()
        assert len(row[0]) == len(row[2]) == 64
        assert row[1] == "dra.run-create-request.v1"
    finally:
        connection.close()


def test_concurrent_duplicate_create_serializes_to_one_run(tmp_path):
    from api.run_repository import create_or_replay_run

    db_path = str(tmp_path / "runs.db")
    kwargs = dict(
        db_path=db_path,
        idempotency_key="run-key-concurrent-0001",
        thread_id=None,
        query="query",
        profile_id="generic",
        profile_version="1",
        scope={},
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        accepted = list(pool.map(lambda _: create_or_replay_run(**kwargs), range(8)))
    assert sum(not item.idempotent_replay for item in accepted) == 1
    assert len({item.run_id for item in accepted}) == 1
    assert len({item.thread_id for item in accepted}) == 1
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM research_runs_v2").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM run_segments").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM run_create_idempotency_v1").fetchone()[0] == 1
    finally:
        connection.close()


def test_corrupt_ledger_binding_fails_closed(tmp_path):
    from api.run_repository import RunCreationConflict, create_or_replay_run

    db_path = str(tmp_path / "runs.db")
    kwargs = dict(
        db_path=db_path,
        idempotency_key="run-key-corrupt-0001",
        thread_id=None,
        query="query",
        scope={},
    )
    created = create_or_replay_run(**kwargs)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("DELETE FROM research_runs_v2 WHERE run_id = ?", (created.run_id,))
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(RunCreationConflict, match="run_idempotency_unavailable"):
        create_or_replay_run(**kwargs)


def test_keyed_path_rejects_wrong_007_checksum_without_creating_run(tmp_path):
    from api.run_repository import RunCreationConflict, create_or_replay_run, init_run_schema

    db_path = str(tmp_path / "runs.db")
    init_run_schema(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "UPDATE schema_migrations SET checksum = 'forged' "
            "WHERE version = '007_run_create_idempotency'"
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(RunCreationConflict, match="run_idempotency_unavailable"):
        create_or_replay_run(
            db_path=db_path,
            idempotency_key="run-key-marker-0001",
            thread_id=None,
            query="query",
            scope={},
        )
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM research_runs_v2").fetchone()[0] == 0
    finally:
        connection.close()


def test_run_identity_keeps_segment_and_attempt_separate(tmp_path):
    from api.run_repository import create_run, get_run

    db_path = str(tmp_path / "runs.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")
    run = get_run(db_path=db_path, run_id=created["run_id"])

    assert run["segments"][0]["segment_id"] == created["segment_id"]
    assert run["segments"][0]["sequence"] == 0
    assert run["segments"][0]["attempt"] == 1


def test_transition_rejects_stale_state_version(tmp_path):
    from api.run_repository import create_run, get_run, transition_run

    db_path = str(tmp_path / "runs.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")

    assert transition_run(
        db_path=db_path,
        run_id=created["run_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="running",
    )
    assert not transition_run(
        db_path=db_path,
        run_id=created["run_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
    )
    run = get_run(db_path=db_path, run_id=created["run_id"])
    assert run["execution_status"] == "running"
    assert run["state_version"] == 1


def test_unknown_status_transition_is_rejected(tmp_path):
    from api.run_repository import create_run, transition_run

    db_path = str(tmp_path / "runs.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")

    with pytest.raises(ValueError, match="execution_status"):
        transition_run(
            db_path=db_path,
            run_id=created["run_id"],
            expected_state_version=0,
            allowed_previous_statuses={"pending"},
            execution_status="mystery",
        )


def test_finalize_run_transaction_persists_terminal_state_and_evidence(tmp_path):
    from agent.research import EvidenceEntry
    from api.run_repository import create_run, finalize_run_transaction, get_run

    db_path = str(tmp_path / "runs.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")
    evidence = EvidenceEntry(
        thread_id="thread-1",
        query_text="query",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url="https://example.com/source",
        snippet="source evidence",
    )

    assert finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        delivery_status="ready",
        evidence_entries=[evidence],
    )

    run = get_run(db_path=db_path, run_id=created["run_id"])
    assert run["execution_status"] == "completed"
    assert run["delivery_status"] == "ready"
    assert run["segments"][0]["status"] == "completed"
    assert run["evidence"][0]["evidence_fingerprint"] == evidence.evidence_fingerprint
    assert run["evidence"][0]["evidence_id"] == (
        f"ev_{created['run_id']}_{evidence.evidence_fingerprint}"
    )


def test_finalize_run_transaction_rolls_back_terminal_state_on_evidence_failure(tmp_path):
    from agent.research import EvidenceEntry
    from api.run_repository import create_run, finalize_run_transaction, get_run

    db_path = str(tmp_path / "runs.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")
    broken = EvidenceEntry(
        thread_id="thread-1",
        query_text="query",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url="https://example.com/source",
        snippet="source evidence",
    )
    object.__setattr__(broken, "snippet", None)

    with pytest.raises(Exception):
        finalize_run_transaction(
            db_path=db_path,
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            expected_state_version=0,
            allowed_previous_statuses={"pending"},
            execution_status="completed",
            delivery_status="ready",
            evidence_entries=[broken],
        )

    run = get_run(db_path=db_path, run_id=created["run_id"])
    assert run["execution_status"] == "pending"
    assert run["state_version"] == 0
    assert run["segments"][0]["status"] == "pending"
    assert run["evidence"] == []


def test_failed_finalization_requires_a_typed_failure_cause(tmp_path):
    from api.run_failure_cause_models import RunFailureCauseConflict
    from api.run_repository import create_run, finalize_run_transaction

    db_path = str(tmp_path / "runs.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")

    with pytest.raises(
        RunFailureCauseConflict,
        match="run_failure_cause_required",
    ):
        finalize_run_transaction(
            db_path=db_path,
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            expected_state_version=0,
            allowed_previous_statuses={"pending"},
            execution_status="failed",
            delivery_status="failed",
            evidence_entries=[],
        )


def test_nonfailed_finalization_rejects_a_failure_cause(tmp_path):
    from api.run_failure_cause_models import RunFailureCauseConflict
    from api.run_repository import create_run, finalize_run_transaction

    db_path = str(tmp_path / "runs.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")

    with pytest.raises(
        RunFailureCauseConflict,
        match="run_failure_cause_forbidden",
    ):
        finalize_run_transaction(
            db_path=db_path,
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            expected_state_version=0,
            allowed_previous_statuses={"pending"},
            execution_status="completed",
            delivery_status="ready",
            evidence_entries=[],
            failure_cause=_execution_error_cause(),
        )


def test_failed_finalization_inserts_cause_at_winning_state_version(tmp_path):
    from api.run_repository import create_run, finalize_run_transaction

    db_path = str(tmp_path / "runs.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")

    assert finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="failed",
        delivery_status="failed",
        evidence_entries=[],
        failure_cause=_execution_error_cause(),
    )

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT observation_status, terminal_state_version, phase, code
            FROM run_failure_causes_v1 WHERE run_id = ?
            """,
            (created["run_id"],),
        ).fetchone()
    finally:
        connection.close()

    assert row == ("observed", 1, "execution", "execution_error")


def test_failed_finalization_uses_one_timestamp_for_run_segment_and_cause(
    tmp_path,
    monkeypatch,
):
    import api.run_repository as repository

    db_path = str(tmp_path / "runs.db")
    created = repository.create_run(
        db_path=db_path,
        thread_id="thread-1",
        query="query",
    )
    monkeypatch.setattr(repository, "_now", lambda: FIXED_TERMINAL_TIME)

    assert repository.finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="failed",
        delivery_status="failed",
        evidence_entries=[],
        failure_cause=_execution_error_cause(),
    )

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT run.updated_at, segment.updated_at, cause.recorded_at
            FROM research_runs_v2 AS run
            JOIN run_segments AS segment ON segment.run_id = run.run_id
            JOIN run_failure_causes_v1 AS cause ON cause.run_id = run.run_id
            WHERE run.run_id = ?
            """,
            (created["run_id"],),
        ).fetchone()
    finally:
        connection.close()

    assert row == (FIXED_TERMINAL_TIME,) * 3


def test_stale_failed_finalization_inserts_no_cause(tmp_path):
    from api.run_repository import create_run, finalize_run_transaction, get_run

    db_path = str(tmp_path / "runs.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")

    assert not finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=1,
        allowed_previous_statuses={"pending"},
        execution_status="failed",
        delivery_status="failed",
        evidence_entries=[],
        failure_cause=_execution_error_cause(),
    )

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM run_failure_causes_v1"
        ).fetchone()[0] == 0
    finally:
        connection.close()
    assert get_run(db_path=db_path, run_id=created["run_id"])[
        "execution_status"
    ] == "pending"


def test_cause_insert_failure_rolls_back_run_segment_evidence_packet_artifact_and_review(
    tmp_path,
):
    from agent.research import EvidenceEntry
    from agent.talent_contracts import ResearchPacket, ReviewBundle
    from api.review_models import (
        checkpoint_thread_id,
        post_review_segment_id,
        review_workflow_id,
    )
    from api.review_repository import init_review_schema
    from api.run_failure_cause_models import RunFailureCauseConflict
    from api.run_repository import create_run, finalize_run_transaction

    db_path = str(tmp_path / "runs.db")
    created = create_run(
        db_path=db_path,
        thread_id="thread-1",
        query="query",
        profile_id="talent-hiring-signal",
    )
    init_review_schema(db_path)
    evidence = EvidenceEntry(
        thread_id="thread-1",
        query_text="query",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url="https://example.com/source",
        snippet="source evidence",
    )
    packet = ResearchPacket(
        packet_id="packet-1",
        scope_id="scope-1",
        findings=[],
        candidate_claims=[],
    )
    review = ReviewBundle(
        review_id="review-1",
        run_id=created["run_id"],
        revision=1,
        status="required",
        claim_snapshots=[],
        evidence_snapshots=[],
        triggers=["manual_review_required"],
        recommended_actions=[],
        required_before_delivery=True,
    )
    workflow_id = review_workflow_id(
        created["run_id"],
        review.review_id,
        review.revision,
    )
    tables = (
        "research_runs_v2",
        "run_segments",
        "evidence_entries_v2",
        "research_packets_v2",
        "review_bundles_v2",
        "review_workflows_v2",
        "run_artifacts_v2",
        "run_failure_causes_v1",
    )
    before = _table_snapshot(db_path, tables)
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                """
                CREATE TRIGGER abort_failure_cause_insert
                AFTER INSERT ON run_failure_causes_v1
                BEGIN
                    SELECT RAISE(ABORT, 'cause insert failed');
                END
                """
            )
    finally:
        connection.close()

    with pytest.raises(
        RunFailureCauseConflict,
        match="run_failure_cause_conflict",
    ):
        finalize_run_transaction(
            db_path=db_path,
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            expected_state_version=0,
            allowed_previous_statuses={"pending"},
            execution_status="failed",
            review_status="required",
            delivery_status="failed",
            evidence_entries=[evidence],
            research_packets=[packet],
            review_bundle=review,
            artifacts=[
                {
                    "artifact_id": "decision-brief.md",
                    "kind": "decision_brief_markdown",
                    "media_type": "text/markdown",
                    "content": "# Brief",
                    "content_hash": "hash-1",
                }
            ],
            review_workflow={
                "workflow_id": workflow_id,
                "checkpoint_thread_id": checkpoint_thread_id(workflow_id),
                "post_review_segment_id": post_review_segment_id(
                    created["run_id"],
                    review.review_id,
                    review.revision,
                ),
            },
            failure_cause=_execution_error_cause(),
        )

    assert _table_snapshot(db_path, tables) == before


def test_transition_run_rejects_failed_target_and_failed_previous_status(tmp_path):
    from api.run_failure_cause_models import RunFailureCauseConflict
    from api.run_repository import create_run, get_run, transition_run

    db_path = str(tmp_path / "runs.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")
    invalid_transitions = (
        ({"pending"}, "failed"),
        ({"failed"}, "running"),
    )

    for allowed_previous_statuses, execution_status in invalid_transitions:
        with pytest.raises(
            RunFailureCauseConflict,
            match="run_failure_cause_transition_invalid",
        ):
            transition_run(
                db_path=db_path,
                run_id=created["run_id"],
                expected_state_version=0,
                allowed_previous_statuses=allowed_previous_statuses,
                execution_status=execution_status,
            )

    run = get_run(db_path=db_path, run_id=created["run_id"])
    assert run["execution_status"] == "pending"
    assert run["state_version"] == 0


@pytest.mark.parametrize(
    "allowed_previous_statuses",
    [set(), {"completed"}, {"pending", "failed"}, {"mystery"}],
)
def test_allowed_previous_statuses_are_nonempty_pending_or_running_only(
    tmp_path,
    allowed_previous_statuses,
):
    from api.run_failure_cause_models import RunFailureCauseConflict
    from api.run_repository import create_run, finalize_run_transaction

    db_path = str(tmp_path / "runs.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")

    with pytest.raises(
        RunFailureCauseConflict,
        match="run_failure_cause_transition_invalid",
    ):
        finalize_run_transaction(
            db_path=db_path,
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            expected_state_version=0,
            allowed_previous_statuses=allowed_previous_statuses,
            execution_status="completed",
            delivery_status="ready",
            evidence_entries=[],
        )


def test_finalize_run_transaction_persists_talent_artifacts_atomically(tmp_path):
    from datetime import datetime, timezone
    from agent.talent_contracts import ResearchPacket
    from api.run_repository import create_run, finalize_run_transaction, get_artifact, get_run
    from api.talent_artifacts import build_talent_artifacts

    db_path = str(tmp_path / "runs.db")
    created = create_run(
        db_path=db_path,
        thread_id="thread-1",
        query="query",
        profile_id="talent-hiring-signal",
        scope={
            "target_roles": ["AI Agent Engineer"],
            "target_companies": [],
            "time_window": {"start": "2026-01-01", "end": "2026-06-12"},
            "declared_samples": [],
            "allowed_source_types": ["public_job_posting"],
            "research_questions": ["question-1"],
            "requested_outputs": ["decision_brief"],
        },
    )
    packet = ResearchPacket(
        packet_id="packet-1", scope_id="scope-1", findings=[], candidate_claims=[]
    )
    review, _, artifacts = build_talent_artifacts(
        run_id=created["run_id"],
        scope=get_run(db_path=db_path, run_id=created["run_id"])["scope"],
        packets=[packet],
        evidence_entries=[],
        generated_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
    )

    assert finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        review_status=review.status,
        delivery_status="ready",
        evidence_entries=[],
        research_packets=[packet],
        review_bundle=review,
        artifacts=artifacts,
    )

    run = get_run(db_path=db_path, run_id=created["run_id"])
    assert run["research_packets"][0]["packet_id"] == "packet-1"
    assert run["review_bundle"]["review_id"] == review.review_id
    for expected in artifacts:
        stored = get_artifact(
            db_path=db_path,
            run_id=created["run_id"],
            artifact_id=expected["artifact_id"],
        )
        assert stored["artifact_id"] == expected["artifact_id"]
        assert stored["kind"] == expected["kind"]
        assert stored["media_type"] == expected["media_type"]
        assert stored["content"] == expected["content"]
        assert stored["content_hash"] == expected["content_hash"]


def test_fenced_finalization_persists_exactly_one_generic_result_artifact(tmp_path):
    from api.run_repository import (
        create_run,
        finalize_run_transaction,
        get_artifact,
        get_run,
    )

    db_path = str(tmp_path / "runs.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")
    artifact = {
        "artifact_id": "research-report.md",
        "kind": "research_report_markdown",
        "media_type": "text/markdown",
        "content": "# Report",
        "content_hash": "hash-1",
    }
    different_artifact = {
        **artifact,
        "content": "# Different",
        "content_hash": "hash-2",
    }

    first = finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        delivery_status="ready",
        evidence_entries=[],
        artifacts=[artifact],
    )
    second = finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        delivery_status="ready",
        evidence_entries=[],
        artifacts=[different_artifact],
    )

    run = get_run(db_path=db_path, run_id=created["run_id"])
    assert first is True
    assert second is False
    assert run["state_version"] == 1
    assert [item["artifact_id"] for item in run["artifacts"]] == [
        "research-report.md"
    ]
    assert get_artifact(
        db_path=db_path,
        run_id=created["run_id"],
        artifact_id="research-report.md",
    )["content"] == "# Report"


def test_required_review_finalization_seeds_workflow_atomically(tmp_path):
    from agent.talent_contracts import ReviewBundle
    from api.review_models import (
        checkpoint_thread_id,
        post_review_segment_id,
        review_workflow_id,
    )
    from api.run_repository import (
        create_run,
        finalize_run_transaction,
        get_run,
        transition_run,
    )

    db_path = str(tmp_path / "runs.db")
    created = create_run(
        db_path=db_path,
        thread_id="thread-1",
        query="query",
        profile_id="talent-hiring-signal",
    )
    assert transition_run(
        db_path=db_path,
        run_id=created["run_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="running",
    )
    review = ReviewBundle(
        review_id="review_1",
        run_id=created["run_id"],
        revision=1,
        status="required",
        claim_snapshots=[],
        evidence_snapshots=[],
        triggers=["manual_review_required"],
        recommended_actions=[],
        required_before_delivery=True,
    )
    workflow_id = review_workflow_id(
        created["run_id"],
        review.review_id,
        review.revision,
    )

    assert finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=1,
        allowed_previous_statuses={"running"},
        execution_status="completed",
        review_status="required",
        delivery_status="review_required",
        evidence_entries=[],
        review_bundle=review,
        review_workflow={
            "workflow_id": workflow_id,
            "checkpoint_thread_id": checkpoint_thread_id(workflow_id),
            "post_review_segment_id": post_review_segment_id(
                created["run_id"],
                review.review_id,
                review.revision,
            ),
        },
    )

    run = get_run(db_path=db_path, run_id=created["run_id"])
    assert run["state_version"] == 2
    assert run["review_workflow"]["status"] == "checkpoint_pending"


def test_review_workflow_seed_failure_rolls_back_finalization(tmp_path):
    from agent.talent_contracts import ReviewBundle
    from api.run_repository import (
        create_run,
        finalize_run_transaction,
        get_run,
        transition_run,
    )

    db_path = str(tmp_path / "runs.db")
    created = create_run(
        db_path=db_path,
        thread_id="thread-1",
        query="query",
        profile_id="talent-hiring-signal",
    )
    assert transition_run(
        db_path=db_path,
        run_id=created["run_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="running",
    )
    review = ReviewBundle(
        review_id="review_1",
        run_id=created["run_id"],
        revision=1,
        status="required",
        claim_snapshots=[],
        evidence_snapshots=[],
        triggers=["manual_review_required"],
        recommended_actions=[],
        required_before_delivery=True,
    )

    with pytest.raises(KeyError, match="checkpoint_thread_id"):
        finalize_run_transaction(
            db_path=db_path,
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            expected_state_version=1,
            allowed_previous_statuses={"running"},
            execution_status="completed",
            review_status="required",
            delivery_status="review_required",
            evidence_entries=[],
            review_bundle=review,
            review_workflow={
                "workflow_id": "rwf_broken",
                "post_review_segment_id": "segment_broken",
            },
        )

    run = get_run(db_path=db_path, run_id=created["run_id"])
    assert run["execution_status"] == "running"
    assert run["state_version"] == 1
    assert run["review_bundle"] is None
    assert run["review_workflow"] is None


def test_same_evidence_can_be_persisted_in_two_runs_without_id_collision(tmp_path):
    from agent.research import EvidenceEntry
    from api.run_repository import create_run, finalize_run_transaction, get_run

    db_path = str(tmp_path / "runs.db")
    evidence = EvidenceEntry(
        thread_id="thread-1",
        query_text="query",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url="https://example.com/source",
        snippet="same evidence",
    )
    runs = [
        create_run(db_path=db_path, thread_id="thread-1", query="query"),
        create_run(db_path=db_path, thread_id="thread-1", query="query"),
    ]

    for created in runs:
        assert finalize_run_transaction(
            db_path=db_path,
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            expected_state_version=0,
            allowed_previous_statuses={"pending"},
            execution_status="completed",
            delivery_status="ready",
            evidence_entries=[evidence],
        )

    ids = [
        get_run(db_path=db_path, run_id=item["run_id"])["evidence"][0]["evidence_id"]
        for item in runs
    ]
    assert ids[0] != ids[1]


def test_unkeyed_create_inserts_pending_dispatch_with_canonical_scope(tmp_path):
    from api.run_repository import create_run

    db_path = str(tmp_path / "runs.db")
    created = create_run(
        db_path=db_path,
        thread_id="thread-1",
        query="query",
        scope={"z": 2, "a": {"b": 1}},
    )

    connection = sqlite3.connect(db_path)
    try:
        dispatch = connection.execute(
            "SELECT status, attempt_count FROM run_dispatches_v1 WHERE run_id = ?",
            (created["run_id"],),
        ).fetchone()
        scope_json = connection.execute(
            "SELECT scope_json FROM research_runs_v2 WHERE run_id = ?",
            (created["run_id"],),
        ).fetchone()[0]
    finally:
        connection.close()

    assert dispatch == ("pending", 0)
    assert scope_json == '{"a":{"b":1},"z":2}'


def test_keyed_replay_keeps_one_dispatch(tmp_path):
    from api.run_repository import create_or_replay_run

    db_path = str(tmp_path / "runs.db")
    first = create_or_replay_run(
        idempotency_key="run-key-dispatch-0001",
        thread_id=None,
        query="research",
        db_path=db_path,
    )
    second = create_or_replay_run(
        idempotency_key="run-key-dispatch-0001",
        thread_id=None,
        query="research",
        db_path=db_path,
    )

    connection = sqlite3.connect(db_path)
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM run_dispatches_v1 WHERE run_id = ?",
            (first.run_id,),
        ).fetchone()[0]
    finally:
        connection.close()

    assert second.idempotent_replay is True
    assert count == 1


def test_same_thread_unkeyed_runs_each_get_dispatch(tmp_path):
    from api.run_repository import create_run

    db_path = str(tmp_path / "runs.db")
    first = create_run(db_path=db_path, thread_id="thread-1", query="same")
    second = create_run(db_path=db_path, thread_id="thread-1", query="same")

    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "SELECT run_id, status FROM run_dispatches_v1 ORDER BY run_id"
        ).fetchall()
    finally:
        connection.close()

    assert {row[0] for row in rows} == {first["run_id"], second["run_id"]}
    assert {row[1] for row in rows} == {"pending"}


def test_wrong_dispatch_marker_fails_before_identity_insert(tmp_path):
    from api.run_dispatch_models import RUN_DISPATCH_MIGRATION_VERSION
    from api.run_repository import RunDispatchConflict, create_run, init_run_schema

    db_path = str(tmp_path / "runs.db")
    init_run_schema(db_path)
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                "UPDATE schema_migrations SET checksum = 'wrong' WHERE version = ?",
                (RUN_DISPATCH_MIGRATION_VERSION,),
            )
    finally:
        connection.close()

    with pytest.raises(RunDispatchConflict, match="run_dispatch_unavailable"):
        create_run(db_path=db_path, thread_id="thread-1", query="query")

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM research_runs_v2").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM run_segments").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM run_dispatches_v1").fetchone()[0] == 0
    finally:
        connection.close()


def test_dispatch_insert_failure_rolls_back_run_and_segment(tmp_path):
    from api.run_repository import create_run, init_run_schema

    db_path = str(tmp_path / "runs.db")
    init_run_schema(db_path)
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                """
                CREATE TRIGGER fail_dispatch_insert
                BEFORE INSERT ON run_dispatches_v1
                BEGIN
                    SELECT RAISE(ABORT, 'dispatch insert failed');
                END
                """
            )
    finally:
        connection.close()

    with pytest.raises(sqlite3.DatabaseError, match="dispatch insert failed"):
        create_run(db_path=db_path, thread_id="thread-1", query="query")

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM research_runs_v2").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM run_segments").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM run_dispatches_v1").fetchone()[0] == 0
    finally:
        connection.close()


def test_key_binding_failure_rolls_back_run_segment_and_dispatch(tmp_path):
    from api.run_repository import RunCreationConflict, create_or_replay_run, init_run_schema

    db_path = str(tmp_path / "runs.db")
    init_run_schema(db_path)
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                """
                CREATE TRIGGER fail_key_binding_insert
                BEFORE INSERT ON run_create_idempotency_v1
                BEGIN
                    SELECT RAISE(ABORT, 'key binding insert failed');
                END
                """
            )
    finally:
        connection.close()

    with pytest.raises(RunCreationConflict, match="run_idempotency_unavailable"):
        create_or_replay_run(
            db_path=db_path,
            idempotency_key="run-key-dispatch-0002",
            thread_id=None,
            query="query",
        )

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM research_runs_v2").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM run_segments").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM run_dispatches_v1").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM run_create_idempotency_v1").fetchone()[0] == 0
    finally:
        connection.close()


def test_run_creation_rejects_missing_or_wrong_009_marker_before_insert(
    tmp_path,
    monkeypatch,
):
    import api.run_repository as repository
    from api.run_failure_cause_models import (
        RUN_FAILURE_CAUSE_MIGRATION_CHECKSUM,
        RUN_FAILURE_CAUSE_MIGRATION_VERSION,
        RunFailureCauseConflict,
    )

    db_path = str(tmp_path / "runs.db")
    repository.init_run_schema(db_path)
    monkeypatch.setattr(repository, "init_run_schema", lambda _path: None)

    for checksum in (None, "wrong"):
        connection = sqlite3.connect(db_path)
        try:
            with connection:
                connection.execute(
                    "DELETE FROM schema_migrations WHERE version = ?",
                    (RUN_FAILURE_CAUSE_MIGRATION_VERSION,),
                )
                if checksum is not None:
                    connection.execute(
                        """
                        INSERT INTO schema_migrations(version, applied_at, checksum)
                        VALUES (?, '2026-07-16T00:00:00+00:00', ?)
                        """,
                        (RUN_FAILURE_CAUSE_MIGRATION_VERSION, checksum),
                    )
        finally:
            connection.close()

        with pytest.raises(
            RunFailureCauseConflict,
            match="run_failure_cause_unavailable",
        ):
            repository.create_run(
                db_path=db_path,
                thread_id="thread-1",
                query="query",
            )

        connection = sqlite3.connect(db_path)
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM research_runs_v2"
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM run_segments"
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM run_dispatches_v1"
            ).fetchone()[0] == 0
        finally:
            connection.close()


def test_historical_failed_run_projects_not_observed_failure_cause(tmp_path):
    from api.run_repository import get_run
    from tests.unit.test_run_migrations import _apply_009, _seed_pre_009_runs

    db_path = str(tmp_path / "runs.db")
    _seed_pre_009_runs(db_path, statuses=("failed",))
    _apply_009(db_path)

    run = get_run(db_path=db_path, run_id="run_failed_0")

    assert run["failure_cause"] == {
        "schema_version": "dra.run-failure-cause.v1",
        "observation_status": "not_observed",
    }


def test_new_failed_run_projects_observed_failure_cause_without_storage_version(
    tmp_path,
    monkeypatch,
):
    from api.run_repository import get_run

    db_path = str(tmp_path / "runs.db")
    created = _seed_observed_failed_run(
        db_path=db_path,
        monkeypatch=monkeypatch,
    )

    cause = get_run(db_path=db_path, run_id=created["run_id"])[
        "failure_cause"
    ]

    assert cause == {
        "schema_version": "dra.run-failure-cause.v1",
        "observation_status": "observed",
        "phase": "execution",
        "code": "execution_error",
        "recorded_at": "2026-07-16T00:00:00Z",
    }
    assert "terminal_state_version" not in cause


@pytest.mark.parametrize(
    "execution_status",
    ["pending", "running", "completed", "completed_with_fallback"],
)
def test_nonfailed_run_projects_null_failure_cause(tmp_path, execution_status):
    from api.run_repository import (
        create_run,
        finalize_run_transaction,
        get_run,
        transition_run,
    )

    db_path = str(tmp_path / f"{execution_status}.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")
    if execution_status == "running":
        assert transition_run(
            db_path=db_path,
            run_id=created["run_id"],
            expected_state_version=0,
            allowed_previous_statuses={"pending"},
            execution_status="running",
        )
    elif execution_status in {"completed", "completed_with_fallback"}:
        assert finalize_run_transaction(
            db_path=db_path,
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            expected_state_version=0,
            allowed_previous_statuses={"pending"},
            execution_status=execution_status,
            delivery_status="ready",
            evidence_entries=[],
        )

    assert get_run(db_path=db_path, run_id=created["run_id"])[
        "failure_cause"
    ] is None


@pytest.mark.parametrize(
    ("mutation_sql", "ignore_constraints"),
    [
        (
            "DELETE FROM run_failure_causes_v1 WHERE run_id = ?",
            False,
        ),
        (
            "UPDATE run_failure_causes_v1 "
            "SET terminal_state_version = terminal_state_version + 1 "
            "WHERE run_id = ?",
            False,
        ),
        (
            "UPDATE run_failure_causes_v1 "
            "SET recorded_at = '2026-07-16T00:00:01+00:00' "
            "WHERE run_id = ?",
            False,
        ),
        (
            "UPDATE run_failure_causes_v1 "
            "SET observation_status = 'not_observed', "
            "terminal_state_version = 1, phase = NULL, code = NULL, "
            "recorded_at = NULL WHERE run_id = ?",
            True,
        ),
        (
            "UPDATE run_failure_causes_v1 SET recorded_at = 'not-a-time' "
            "WHERE run_id = ?",
            False,
        ),
        (
            "UPDATE run_failure_causes_v1 "
            "SET phase = 'dispatch', code = 'execution_error' "
            "WHERE run_id = ?",
            True,
        ),
    ],
    ids=[
        "failed-with-no-row",
        "terminal-version-mismatch",
        "recorded-at-mismatch",
        "historical-with-terminal-version",
        "invalid-recorded-at",
        "invalid-phase-code",
    ],
)
def test_corrupt_failure_cause_fails_closed_in_init_and_direct_joined_projection(
    tmp_path,
    monkeypatch,
    mutation_sql,
    ignore_constraints,
):
    db_path = str(tmp_path / "runs.db")
    created = _seed_observed_failed_run(
        db_path=db_path,
        monkeypatch=monkeypatch,
    )
    connection = sqlite3.connect(db_path)
    try:
        if ignore_constraints:
            connection.execute("PRAGMA ignore_check_constraints=ON")
        with connection:
            connection.execute(mutation_sql, (created["run_id"],))
        if ignore_constraints:
            connection.execute("PRAGMA ignore_check_constraints=OFF")
    finally:
        connection.close()

    _assert_corrupt_in_init_and_joined_projection(
        db_path=db_path,
        run_id=created["run_id"],
        monkeypatch=monkeypatch,
    )


def test_nonfailed_run_with_any_cause_row_fails_closed_in_joined_projection(
    tmp_path,
    monkeypatch,
):
    from api.run_repository import create_run

    db_path = str(tmp_path / "runs.db")
    created = create_run(db_path=db_path, thread_id="thread-1", query="query")
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO run_failure_causes_v1(
                    run_id, observation_status, terminal_state_version,
                    phase, code, recorded_at
                ) VALUES (?, 'not_observed', NULL, NULL, NULL, NULL)
                """,
                (created["run_id"],),
            )
    finally:
        connection.close()

    _assert_corrupt_in_init_and_joined_projection(
        db_path=db_path,
        run_id=created["run_id"],
        monkeypatch=monkeypatch,
    )


def test_failure_cause_projection_maps_row_shape_errors_to_bounded_conflict():
    from api.run_failure_cause_models import RunFailureCauseConflict
    from api.run_repository import _failure_cause_projection

    with pytest.raises(
        RunFailureCauseConflict,
        match="run_failure_cause_corrupt",
    ):
        _failure_cause_projection(
            {
                "execution_status": "failed",
                "state_version": 1,
                "updated_at": FIXED_TERMINAL_TIME,
            }
        )
