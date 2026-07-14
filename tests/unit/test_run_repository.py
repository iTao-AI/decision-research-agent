import concurrent.futures
import sqlite3

import pytest


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
        execution_status="failed",
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
