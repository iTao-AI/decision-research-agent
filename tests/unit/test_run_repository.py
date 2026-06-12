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
