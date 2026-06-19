import asyncio
import logging

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


def test_app_lifespan_starts_worker_only_when_enabled(monkeypatch):
    starts = []
    stops = []
    monkeypatch.setattr(
        server,
        "create_review_worker",
        lambda: FakeWorker(starts, stops),
        raising=False,
    )

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "false")
    monkeypatch.delenv("API_SECRET", raising=False)
    with TestClient(server.app):
        pass
    assert starts == []

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.setenv("API_SECRET", "configured")
    with TestClient(server.app):
        assert starts == ["started"]
    assert stops == ["stopped"]


def test_app_lifespan_refuses_worker_without_api_secret(
    monkeypatch,
    caplog,
):
    starts = []
    monkeypatch.setattr(
        server,
        "create_review_worker",
        lambda: FakeWorker(starts, []),
    )
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.delenv("API_SECRET", raising=False)

    with caplog.at_level(logging.ERROR):
        with TestClient(server.app):
            pass

    assert starts == []
    assert (
        "durable_hitl_worker_not_started:review_auth_not_configured"
        in caplog.messages
    )
