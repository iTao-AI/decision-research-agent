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
