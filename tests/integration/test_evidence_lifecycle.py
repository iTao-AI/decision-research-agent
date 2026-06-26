import json

import pytest
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphRecursionError

from agent.run_result import OutcomeBox
from api.research_execution_service import ResearchExecutionService


class EmptyHarness:
    async def execute(self, request, *, runtime_context, observer):
        return observer.snapshot_outcome()


@pytest.mark.asyncio
async def test_talent_preload_freezes_verified_evidence_and_normalizes_refs(
    tmp_path,
    monkeypatch,
):
    fixtures = tmp_path / "benchmarks" / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "aggregate-v1.json").write_text(
        json.dumps(
            {
                "aggregate_id": "aggregate-v1",
                "samples": [
                    {
                        "sample_id": "sample-1",
                        "source_url": "https://jobs.example.com/role",
                        "content": "Agent evaluation and observability.",
                    },
                    {
                        "sample_id": "sample-2",
                        "source_url": "https://jobs.example.com/role-2",
                        "content": "Agent retrieval and tool integration.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES",
        "true",
    )
    import tools.provided_aggregate as aggregate_tool

    monkeypatch.setattr(aggregate_tool, "FIXTURE_ROOT", fixtures)

    class TalentHarness:
        async def execute(self, request, *, runtime_context, observer):
            packet = {
                "packet_id": "packet-1",
                "scope_id": "aggregate-v1",
                "findings": [
                    {
                        "finding_id": "finding-1",
                        "research_question_id": "question-1",
                        "statement": "Evaluation is present.",
                        "evidence_refs": ["S1", "sample-snapshot-2"],
                        "sample_scope": "declared samples",
                        "confidence": 0.8,
                    }
                ],
                "candidate_claims": [
                    {
                        "claim_id": "claim-1",
                        "text": "Evaluation is a hiring signal.",
                        "claim_type": "signal",
                        "finding_refs": ["finding-1"],
                        "evidence_refs": ["aggregate-v1"],
                        "confidence": 0.8,
                        "citation_status": "cited",
                        "verification_status": "unverified",
                        "review_status": "pending",
                        "conflict_status": "none",
                    }
                ],
            }
            observer.on_stream_chunk(
                {
                    "tools": {
                        "messages": [
                            ToolMessage(
                                content=json.dumps(packet),
                                tool_call_id="call-task",
                                name="task",
                            )
                        ]
                    }
                }
            )
            return observer.snapshot_outcome()

    outcome = await ResearchExecutionService(
        harness=TalentHarness(),
        project_root=tmp_path,
    ).execute(
        "query",
        "thread-talent",
        run_id="run-talent",
        segment_id="segment-talent",
        profile_id="talent-hiring-signal",
        scope={
            "declared_samples": [
                {
                    "sample_id": "aggregate-v1",
                    "source_type": "provided_aggregate",
                    "reference": "aggregate-v1",
                }
            ]
        },
    )

    assert [entry.source_url for entry in outcome.evidence_entries] == [
        "https://jobs.example.com/role",
        "https://jobs.example.com/role-2",
    ]
    assert all(
        entry.verification_status == "verified"
        and entry.baseline_verification_origin == "declared_fixture"
        for entry in outcome.evidence_entries
    )
    evidence_ids = [
        f"ev_run-talent_{entry.evidence_fingerprint}"
        for entry in outcome.evidence_entries
    ]
    assert outcome.research_packets[0].findings[0].evidence_refs == evidence_ids
    assert outcome.research_packets[0].candidate_claims[0].evidence_refs == evidence_ids


@pytest.mark.asyncio
async def test_talent_run_does_not_copy_uploaded_files(tmp_path):
    upload_dir = tmp_path / "updated" / "session_run-talent"
    upload_dir.mkdir(parents=True)
    (upload_dir / "private.txt").write_text("private", encoding="utf-8")

    outcome = await ResearchExecutionService(
        harness=EmptyHarness(),
        project_root=tmp_path,
    ).execute(
        "query",
        "thread-talent",
        run_id="run-talent",
        segment_id="segment-talent",
        profile_id="talent-hiring-signal",
        scope={"declared_samples": []},
    )

    assert not (outcome.session_dir / "private.txt").exists()


@pytest.mark.asyncio
async def test_recursion_failure_publishes_bounded_outcome(tmp_path):
    class LoopingHarness:
        async def execute(self, request, *, runtime_context, observer):
            raise GraphRecursionError("recursion limit reached")

    box = OutcomeBox()
    outcome = await ResearchExecutionService(
        harness=LoopingHarness(),
        project_root=tmp_path,
    ).execute(
        "query",
        "thread-loop",
        run_id="run-loop",
        segment_id="segment-loop",
        outcome_box=box,
    )

    assert outcome.failure_kind == "recursion_limit_exceeded"
    assert box.latest() == outcome
