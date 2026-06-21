import asyncio
import sqlite3

import pytest
from fastapi.testclient import TestClient

import api.server as server
from agent.run_result import AgentRunResult
from agent.talent_contracts import ResearchPacket
from api.run_repository import create_run, get_run


def _scope():
    return {
        "target_roles": ["AI Agent Engineer"],
        "target_companies": [],
        "time_window": {"start": "2026-01-01", "end": "2026-06-12"},
        "declared_samples": [],
        "allowed_source_types": ["public_job_posting"],
        "research_questions": ["question-1"],
        "requested_outputs": ["decision_brief"],
    }


def _packet():
    return ResearchPacket(
        packet_id="packet-1",
        scope_id="scope-1",
        findings=[
            {
                "finding_id": "finding-1",
                "research_question_id": "question-1",
                "statement": "Signal",
                "evidence_refs": ["ev_missing"],
                "sample_scope": "declared",
                "confidence": 0.8,
            }
        ],
        candidate_claims=[
            {
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
            }
        ],
    )


async def _finalize_talent_fixture(tmp_path, monkeypatch, *, enabled: bool):
    monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL",
        "true" if enabled else "false",
    )
    scope = _scope()
    created = create_run(
        thread_id="talent-thread",
        query="query",
        profile_id="talent-hiring-signal",
        scope=scope,
    )

    async def capture_agent(*args, **kwargs):
        return AgentRunResult(
            thread_id="talent-thread",
            query="query",
            session_dir=tmp_path,
            profile_id="talent-hiring-signal",
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            research_packets=[_packet()],
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
    return get_run(run_id=created["run_id"])


@pytest.mark.asyncio
async def test_talent_finalization_does_not_seed_workflow_when_flag_is_false(
    tmp_path,
    monkeypatch,
):
    run = await _finalize_talent_fixture(tmp_path, monkeypatch, enabled=False)

    assert run["review_status"] == "required"
    assert run["delivery_status"] == "review_required"
    assert run["review_workflow"] is None


@pytest.mark.asyncio
async def test_talent_finalization_atomically_seeds_checkpoint_pending_workflow(
    tmp_path,
    monkeypatch,
):
    run = await _finalize_talent_fixture(tmp_path, monkeypatch, enabled=True)

    assert run["state_version"] == 2
    assert run["review_workflow"]["status"] == "checkpoint_pending"
    assert run["review_workflow"]["review_id"] == run["review_bundle"]["review_id"]
    assert "decision-brief.reviewed.json" not in {
        item["artifact_id"] for item in run["artifacts"]
    }


@pytest.mark.asyncio
async def test_required_review_remains_not_deliverable_before_resolution(
    tmp_path,
    monkeypatch,
):
    run = await _finalize_talent_fixture(tmp_path, monkeypatch, enabled=True)

    assert run["review_status"] == "required"
    assert run["delivery_status"] == "review_required"
    assert "decision-brief.reviewed.json" not in {
        item["artifact_id"] for item in run["artifacts"]
    }


class FakeWorker:
    def __init__(self, starts, stops):
        self.starts = starts
        self.stops = stops
        self.stopped = asyncio.Event()

    async def run_forever(self):
        self.starts.append("started")
        await self.stopped.wait()

    def stop(self):
        self.stops.append("stopped")
        self.stopped.set()


class FailingWorker(FakeWorker):
    async def run_forever(self):
        self.starts.append("started")
        raise RuntimeError("worker_start_failed")


def test_app_lifespan_starts_worker_only_when_enabled(tmp_path, monkeypatch):
    starts = []
    stops = []
    monkeypatch.setattr(
        server,
        "create_review_worker",
        lambda **kwargs: FakeWorker(starts, stops),
        raising=False,
    )

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "false")
    monkeypatch.delenv("API_SECRET", raising=False)
    with TestClient(server.app):
        pass
    assert starts == []

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.setenv("API_SECRET", "configured")
    monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
        str(tmp_path / "review-checkpoints.db"),
    )
    with TestClient(server.app):
        assert starts == ["started"]
    assert stops == ["stopped"]


def test_app_lifespan_hands_normalized_runtime_paths_to_worker(
    tmp_path,
    monkeypatch,
):
    starts = []
    stops = []
    received_paths = []

    def capture_worker(*, application_db_path, checkpoint_db_path):
        received_paths.append((application_db_path, checkpoint_db_path))
        return FakeWorker(starts, stops)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(server, "create_review_worker", capture_worker)
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.setenv("API_SECRET", "configured")
    monkeypatch.setenv("TASKS_DB_PATH", "data/../tasks.db")
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
        "./review-checkpoints.db",
    )

    with TestClient(server.app):
        pass

    assert received_paths == [
        (
            (tmp_path / "tasks.db").resolve(),
            (tmp_path / "review-checkpoints.db").resolve(),
        )
    ]


def test_app_lifespan_cleans_up_when_worker_fails_during_startup(
    tmp_path,
    monkeypatch,
):
    starts = []
    stops = []
    monkeypatch.setattr(
        server,
        "create_review_worker",
        lambda **kwargs: FailingWorker(starts, stops),
    )
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.setenv("API_SECRET", "configured")
    monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
        str(tmp_path / "review-checkpoints.db"),
    )

    with pytest.raises(RuntimeError, match="worker_start_failed"):
        with TestClient(server.app):
            pass

    assert starts == ["started"]
    assert stops == ["stopped"]
    assert server.app.state.review_worker_task is None
    assert server.app.state.review_runtime_readiness is None


def test_app_lifespan_fails_startup_without_api_secret(monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.delenv("API_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="review_auth_not_configured"):
        with TestClient(server.app):
            pass


def test_app_lifespan_fails_startup_with_incomplete_review_schema(
    tmp_path,
    monkeypatch,
):
    tasks_path = tmp_path / "tasks.db"
    connection = sqlite3.connect(tasks_path)
    try:
        connection.execute(
            """
            CREATE TABLE review_workflows_v2 (
                status TEXT,
                lease_expires_at TEXT,
                updated_at TEXT
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.setenv("API_SECRET", "configured")
    monkeypatch.setenv("TASKS_DB_PATH", str(tasks_path))
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
        str(tmp_path / "review-checkpoints.db"),
    )

    with pytest.raises(RuntimeError, match="review_runtime_not_ready"):
        with TestClient(server.app):
            pass
