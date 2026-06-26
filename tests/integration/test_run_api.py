import os
import asyncio

import pytest
from fastapi.testclient import TestClient

from api.server import app


AUTH_HEADERS = {"X-API-Key": "test-integration-key"}


def test_create_and_get_run_returns_distinct_thread_and_run_identity(
    tmp_path, monkeypatch
):
    import api.server as server

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    scheduled = []

    def capture_task(coroutine, task_id, **kwargs):
        scheduled.append((coroutine, task_id))
        coroutine.close()

    monkeypatch.setattr(server, "create_tracked_task", capture_task)
    client = TestClient(app)

    response = client.post(
        "/api/runs",
        json={"query": "research", "thread_id": "thread-1"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    created = response.json()
    assert created["thread_id"] == "thread-1"
    assert created["run_id"].startswith("run_")
    assert created["segment_id"].endswith("_seg_000")
    assert scheduled[0][1] == created["run_id"]

    fetched = client.get(f"/api/runs/{created['run_id']}", headers=AUTH_HEADERS)
    assert fetched.status_code == 200
    assert fetched.json()["run_id"] == created["run_id"]


def test_create_run_registers_run_scoped_timeout_callback(tmp_path, monkeypatch):
    import api.server as server

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    scheduled = []

    def capture_task(coroutine, task_id, **kwargs):
        scheduled.append((coroutine, task_id, kwargs))

    monkeypatch.setattr(server, "create_tracked_task", capture_task)
    client = TestClient(app)

    response = client.post(
        "/api/runs",
        json={"query": "research", "thread_id": "timeout-thread"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    coroutine, task_id, kwargs = scheduled[0]
    try:
        assert task_id == response.json()["run_id"]
        assert callable(kwargs["on_timeout"])
    finally:
        coroutine.close()


def test_create_run_allows_same_thread_without_legacy_guard(tmp_path, monkeypatch):
    import api.server as server

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    scheduled = []

    def capture_task(coroutine, task_id, **kwargs):
        scheduled.append(coroutine)

    monkeypatch.setattr(server, "create_tracked_task", capture_task)
    client = TestClient(app)

    response = client.post(
        "/api/runs",
        json={"query": "research", "thread_id": "shared-thread"},
        headers=AUTH_HEADERS,
    )
    second = client.post(
        "/api/runs",
        json={"query": "research again", "thread_id": "shared-thread"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert second.status_code == 200
    assert response.json()["thread_id"] == "shared-thread"
    assert second.json()["thread_id"] == "shared-thread"
    assert response.json()["run_id"] != second.json()["run_id"]
    for coroutine in scheduled:
        coroutine.close()


def test_create_run_rejects_unknown_profile_fail_closed(tmp_path, monkeypatch):
    import api.server as server

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    client = TestClient(app)

    response = client.post(
        "/api/runs",
        json={"query": "research", "profile_id": "unknown"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unknown_profile"


def test_create_talent_run_rejects_invalid_scope_before_scheduling(
    tmp_path, monkeypatch
):
    import api.server as server

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    scheduled = []
    monkeypatch.setattr(server, "create_tracked_task", scheduled.append)
    client = TestClient(app)

    response = client.post(
        "/api/runs",
        json={
            "query": "research",
            "profile_id": "talent-hiring-signal",
            "scope": {"target_roles": ["AI Agent Engineer"]},
        },
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_research_scope"
    assert scheduled == []


def test_profile_manifest_exposes_policy_without_runtime_secrets():
    os.environ["API_SECRET"] = "test-integration-key"
    client = TestClient(app)

    response = client.get("/api/profiles/talent-hiring-signal", headers=AUTH_HEADERS)

    assert response.status_code == 200
    manifest = response.json()
    assert manifest["profile"]["profile_id"] == "talent-hiring-signal"
    assert manifest["harness_policy"]["allowed_tools"] == []
    assert "api_key" not in str(manifest).lower()


@pytest.mark.asyncio
async def test_run_v2_cancellation_without_outcome_still_finalizes_failed(
    tmp_path, monkeypatch
):
    import api.server as server
    from api.run_repository import create_run, get_run

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    created = create_run(thread_id="cancel-thread", query="query")

    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(server, "run_deep_agent", cancelled)

    with pytest.raises(asyncio.CancelledError):
        await server._run_v2_with_persistence(
            query="query",
            thread_id="cancel-thread",
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            outcome_box=server.OutcomeBox(),
        )

    run = get_run(run_id=created["run_id"])
    assert run["execution_status"] == "failed"
    assert run["delivery_status"] == "failed"


@pytest.mark.asyncio
async def test_run_v2_routes_profile_id_to_agent_execution(tmp_path, monkeypatch):
    import api.server as server
    from agent.run_result import AgentRunResult
    from agent.talent_contracts import ResearchPacket
    from api.run_repository import create_run

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    created = create_run(
        thread_id="talent-thread",
        query="query",
        profile_id="talent-hiring-signal",
    )
    captured = {}
    scope = {
        "target_roles": ["AI Agent Engineer"],
        "target_companies": [],
        "time_window": {"start": "2026-01-01", "end": "2026-06-12"},
        "declared_samples": [],
        "allowed_source_types": ["public_job_posting"],
        "research_questions": ["question-1"],
        "requested_outputs": ["decision_brief"],
    }

    async def capture_agent(*args, **kwargs):
        captured.update(kwargs)
        return AgentRunResult(
            thread_id="talent-thread",
            query="query",
            session_dir=tmp_path,
            profile_id="talent-hiring-signal",
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            research_packets=[
                ResearchPacket(
                    packet_id="packet-1",
                    scope_id="scope-1",
                    findings=[],
                    candidate_claims=[],
                )
            ],
        )

    monkeypatch.setattr(server, "run_deep_agent", capture_agent)

    await server._run_v2_with_persistence(
        query="query",
        thread_id="talent-thread",
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        profile_id="talent-hiring-signal",
        scope=scope,
        outcome_box=server.OutcomeBox(),
    )

    assert captured["profile_id"] == "talent-hiring-signal"


@pytest.mark.asyncio
async def test_talent_run_persists_review_and_canonical_artifacts(tmp_path, monkeypatch):
    import api.server as server
    from agent.run_result import AgentRunResult
    from agent.talent_contracts import ResearchPacket
    from api.run_repository import create_run, get_run

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "false")
    scope = {
        "target_roles": ["AI Agent Engineer"],
        "target_companies": [],
        "time_window": {"start": "2026-01-01", "end": "2026-06-12"},
        "declared_samples": [],
        "allowed_source_types": ["public_job_posting"],
        "research_questions": ["question-1"],
        "requested_outputs": ["decision_brief"],
    }
    created = create_run(
        thread_id="talent-thread", query="query", profile_id="talent-hiring-signal",
        scope=scope,
    )
    packet = ResearchPacket(
        packet_id="packet-1",
        scope_id="scope-1",
        findings=[{
            "finding_id": "finding-1",
            "research_question_id": "question-1",
            "statement": "Signal",
            "evidence_refs": ["ev_missing"],
            "sample_scope": "declared",
            "confidence": 0.8,
        }],
        candidate_claims=[{
            "claim_id": "claim-1",
            "text": "Claim requiring review",
            "claim_type": "signal",
            "finding_refs": ["finding-1"],
            "evidence_refs": ["ev_missing"],
            "confidence": 0.8,
            "citation_status": "cited",
            "verification_status": "unverified",
            "review_status": "pending",
            "conflict_status": "none",
        }],
    )

    async def capture_agent(*args, **kwargs):
        return AgentRunResult(
            thread_id="talent-thread", query="query", session_dir=tmp_path,
            profile_id="talent-hiring-signal", run_id=created["run_id"],
            segment_id=created["segment_id"], research_packets=[packet],
        )

    monkeypatch.setattr(server, "run_deep_agent", capture_agent)
    await server._run_v2_with_persistence(
        query="query", thread_id="talent-thread", run_id=created["run_id"],
        segment_id=created["segment_id"], profile_id="talent-hiring-signal",
        scope=scope, outcome_box=server.OutcomeBox(),
    )

    run = get_run(run_id=created["run_id"])
    assert run["research_packets"][0]["packet_id"] == "packet-1"
    assert run["review_status"] == "required"
    assert run["delivery_status"] == "review_required"
    assert {item["artifact_id"] for item in run["artifacts"]} == {
        "decision-brief.json", "decision-brief.md",
    }
    assert run["review_workflow"] is None


@pytest.mark.asyncio
async def test_generic_run_persists_canonical_result_artifact(tmp_path, monkeypatch):
    import api.server as server
    from agent.harness_contracts import ReportCandidate
    from agent.run_result import AgentRunResult
    from api.run_repository import create_run, get_artifact, get_run
    from pathlib import PurePosixPath

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    created = create_run(
        thread_id="generic-thread",
        query="query",
        profile_id="generic",
    )

    async def capture_agent(*args, **kwargs):
        return AgentRunResult(
            thread_id="generic-thread",
            query="query",
            session_dir=tmp_path,
            profile_id="generic",
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            report_candidate=ReportCandidate(
                path=PurePosixPath("/workspace/research-report.md"),
                content="# Generic Report",
            ),
        )

    monkeypatch.setattr(server, "run_deep_agent", capture_agent)

    await server._run_v2_with_persistence(
        query="query",
        thread_id="generic-thread",
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        profile_id="generic",
        scope={},
        outcome_box=server.OutcomeBox(),
    )

    run = get_run(run_id=created["run_id"])
    assert run["execution_status"] == "completed"
    assert run["delivery_status"] == "ready"
    assert run["review_status"] == "not_required"
    assert [item["artifact_id"] for item in run["artifacts"]] == [
        "research-report.md"
    ]
    artifact = get_artifact(
        run_id=created["run_id"],
        artifact_id="research-report.md",
    )
    assert artifact["kind"] == "research_report_markdown"
    assert artifact["media_type"] == "text/markdown"
    assert artifact["content"] == "# Generic Report"


def test_run_artifact_api_resolves_by_run_and_artifact_id(tmp_path, monkeypatch):
    from api.run_repository import create_run, finalize_run_transaction

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    created = create_run(thread_id="thread-1", query="query")
    finalize_run_transaction(
        run_id=created["run_id"], segment_id=created["segment_id"],
        expected_state_version=0, allowed_previous_statuses={"pending"},
        execution_status="completed", delivery_status="ready", evidence_entries=[],
        artifacts=[{
            "artifact_id": "brief.md", "kind": "markdown", "media_type": "text/markdown",
            "content": "# Brief", "content_hash": "hash",
        }],
    )
    client = TestClient(app)

    response = client.get(
        f"/api/runs/{created['run_id']}/artifacts/brief.md", headers=AUTH_HEADERS
    )

    assert response.status_code == 200
    assert response.text == "# Brief"


def test_run_projection_exposes_current_publication_and_artifacts(
    tmp_path,
    monkeypatch,
):
    from tests.unit.test_publication_repository import (
        _accept_verification,
        _seed_talent_run,
    )
    from api.publication_repository import finalize_verification_publication
    from api.run_repository import get_run

    seeded = _seed_talent_run(tmp_path, migrate=True)
    _accept_verification(seeded)
    finalize_verification_publication(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        expected_state_version=get_run(
            db_path=seeded.db_path,
            run_id=seeded.run_id,
        )["state_version"],
    )
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", seeded.db_path)
    monkeypatch.setenv("API_SECRET", "test-integration-key")

    response = TestClient(app).get(
        f"/api/runs/{seeded.run_id}",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_publication"]["revision"] == 2
    assert {
        item["artifact_id"]
        for item in body["current_artifacts"]
    } == {
        "decision-brief.r2.json",
        "decision-brief.r2.md",
    }
    assert body["verification_summary"]["state_counts"] == {
        "verified": 1
    }


@pytest.mark.asyncio
async def test_mark_run_timeout_finalizes_nonterminal_run_with_frozen_evidence(
    tmp_path, monkeypatch
):
    import api.server as server
    from agent.research import EvidenceEntry
    from agent.run_result import AgentRunResult
    from api.run_repository import create_run, get_run, transition_run

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    events = []
    monkeypatch.setattr(
        server.monitor,
        "_emit",
        lambda *args, **kwargs: events.append((args, kwargs)),
    )
    created = create_run(thread_id="timeout-thread", query="query")
    assert transition_run(
        run_id=created["run_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="running",
    )
    evidence = EvidenceEntry(
        thread_id="timeout-thread",
        query_text="query",
        subagent_name="network_search",
        tool_name="tavily_search",
        source_url="https://example.com/source",
        source_identity="https://example.com/source",
        snippet="partial evidence",
        evidence_fingerprint="timeout-evidence",
    )
    outcome_box = server.OutcomeBox()
    outcome_box.publish(
        AgentRunResult(
            thread_id="timeout-thread",
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            query="query",
            session_dir=tmp_path,
            evidence_entries=[evidence],
        )
    )

    await server._mark_run_timeout(
        created["run_id"],
        7,
        segment_id=created["segment_id"],
        outcome_box=outcome_box,
    )

    run = get_run(run_id=created["run_id"])
    assert run["execution_status"] == "failed"
    assert run["delivery_status"] == "failed"
    assert [item["evidence_fingerprint"] for item in run["evidence"]] == [
        "timeout-evidence"
    ]
    assert run["artifacts"] == []
    assert events[0][0][0] == "run_timeout"
    assert events[0][1]["thread_id"] == "timeout-thread"
    assert events[0][1]["run_id"] == created["run_id"]
    assert events[0][1]["segment_id"] == created["segment_id"]


@pytest.mark.asyncio
async def test_tracked_run_timeout_reaches_persisted_failed_state(tmp_path, monkeypatch):
    import api.server as server
    from api.run_repository import create_run, get_run
    from api.task_tracker import create_tracked_task

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    created = create_run(thread_id="timeout-thread", query="query")

    async def hangs(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(server, "run_deep_agent", hangs)
    outcome_box = server.OutcomeBox()
    run_coroutine = server._run_v2_with_persistence(
        query="query",
        thread_id="timeout-thread",
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        outcome_box=outcome_box,
    )
    task = create_tracked_task(
        run_coroutine,
        created["run_id"],
        timeout_seconds=0.01,
        on_timeout=lambda run_id, timeout_seconds: server._mark_run_timeout(
            run_id,
            timeout_seconds,
            segment_id=created["segment_id"],
            outcome_box=outcome_box,
        ),
    )

    await task

    run = get_run(run_id=created["run_id"])
    assert run["execution_status"] == "failed"
    assert run["delivery_status"] == "failed"


def test_create_run_scheduler_failure_releases_guard_and_marks_run_failed(
    tmp_path, monkeypatch
):
    import api.server as server
    from api.run_repository import create_run as real_create_run, get_run

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    created_runs = []

    def capture_create_run(**kwargs):
        created = real_create_run(**kwargs)
        created_runs.append(created)
        return created

    def fail_to_schedule(*args, **kwargs):
        raise RuntimeError("scheduler unavailable")

    monkeypatch.setattr(server, "create_run", capture_create_run)
    monkeypatch.setattr(server, "create_tracked_task", fail_to_schedule)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/runs",
        json={"query": "research", "thread_id": "schedule-failure"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 500
    runs = get_run(run_id=created_runs[0]["run_id"])
    assert runs["execution_status"] == "failed"
