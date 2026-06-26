import asyncio
from pathlib import PurePosixPath

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from agent.harness_contracts import HarnessExecutionError, ReportCandidate
from agent.run_result import OutcomeBox
from api.research_execution_service import ResearchExecutionService


class RecordingHarness:
    def __init__(self):
        self.request = None
        self.runtime_context = None
        self.observer = None

    async def execute(self, request, *, runtime_context, observer):
        self.request = request
        self.runtime_context = runtime_context
        self.observer = observer
        observer.on_stream_chunk(
            {
                "network_search": {
                    "messages": [
                        ToolMessage(
                            content=(
                                '[{"url":"https://example.com/source",'
                                '"content":"bounded evidence"}]'
                            ),
                            tool_call_id="call-1",
                            name="internet_search",
                        )
                    ]
                }
            }
        )
        observer.on_stream_chunk(
            {
                "agent": {
                    "messages": [AIMessage(content="final answer")],
                    "files": {
                        "/workspace/research-report.md": {
                            "content": "# Report\n",
                            "encoding": "utf-8",
                        }
                    },
                }
            }
        )
        return observer.snapshot_outcome()


@pytest.mark.asyncio
async def test_service_passes_identity_policy_and_bounded_trace_metadata(tmp_path):
    harness = RecordingHarness()
    service = ResearchExecutionService(
        harness=harness,
        project_root=tmp_path,
    )

    outcome = await service.execute(
        "query",
        "thread-1",
        run_id="run-1",
        segment_id="segment-1",
        profile_id="generic",
        scope={"allowed_source_types": ["public_web"]},
    )

    assert harness.request.thread_id == "thread-1"
    assert harness.request.run_id == "run-1"
    assert harness.request.segment_id == "segment-1"
    assert harness.request.trace_metadata == {
        "research_run_id": "run-1",
        "thread_id": "thread-1",
        "profile_id": "generic",
    }
    assert not hasattr(harness.request, "callbacks")
    assert harness.runtime_context.allowed_source_types == ("public_web",)
    assert harness.observer.callbacks()
    assert outcome.report_candidate == ReportCandidate(
        path=PurePosixPath("/workspace/research-report.md"),
        content="# Report\n",
    )
    assert outcome.evidence_entries[0].source_url == "https://example.com/source"


@pytest.mark.asyncio
async def test_service_publishes_outcome_before_cache_cleanup(tmp_path):
    order = []
    box = OutcomeBox()

    def clear_cache(run_id):
        assert box.latest() is not None
        order.append(("clear", run_id))

    service = ResearchExecutionService(
        harness=RecordingHarness(),
        project_root=tmp_path,
        clear_run_cache=clear_cache,
    )

    await service.execute(
        "query",
        "thread-1",
        run_id="run-1",
        segment_id="segment-1",
        outcome_box=box,
    )

    assert order == [("clear", "run-1")]
    assert box.latest().report_candidate.content == "# Report\n"


@pytest.mark.asyncio
async def test_service_publishes_partial_outcome_before_cancellation_cleanup(tmp_path):
    class CancellingHarness:
        async def execute(self, request, *, runtime_context, observer):
            observer.on_stream_chunk(
                {
                    "agent": {
                        "messages": [AIMessage(content="partial")],
                    }
                }
            )
            raise asyncio.CancelledError

    box = OutcomeBox()
    service = ResearchExecutionService(
        harness=CancellingHarness(),
        project_root=tmp_path,
    )

    with pytest.raises(asyncio.CancelledError):
        await service.execute(
            "query",
            "thread-1",
            run_id="run-1",
            segment_id="segment-1",
            outcome_box=box,
        )

    assert box.latest().last_agent_text == "partial"
    assert box.latest().failure_kind == "cancelled"
    assert box.latest().cancellation_state == "cancelled"


@pytest.mark.asyncio
async def test_service_maps_harness_error_to_stable_failure(tmp_path):
    class LimitedHarness:
        async def execute(self, request, *, runtime_context, observer):
            raise HarnessExecutionError(
                failure_kind="call_budget_exceeded",
                message="tool call budget exceeded",
            )

    service = ResearchExecutionService(
        harness=LimitedHarness(),
        project_root=tmp_path,
    )

    outcome = await service.execute(
        "query",
        "thread-1",
        run_id="run-1",
        segment_id="segment-1",
    )

    assert outcome.failure_kind == "call_budget_exceeded"
