import asyncio
from pathlib import PurePosixPath
from typing import Any, Sequence

import pytest
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from agent.deepagents_harness import (
    DeepAgentsHarness,
    build_filesystem_permissions,
)
from agent.harness_contracts import HarnessExecutionError, ReportCandidate
from agent.profile_middleware import build_profile_middleware
from agent.run_result import OutcomeBox
from agent.runtime_context import ResearchRuntimeContext
from api.research_execution_service import ResearchExecutionService


class ScriptedCanonicalWriteModel(BaseChatModel):
    call_count: int = 0
    bound_tool_names: list[str] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted-canonical-write-model"

    def bind_tools(
        self,
        tools: Sequence,
        *,
        tool_choice: dict | str | bool | None = None,
        **kwargs: Any,
    ):
        del tool_choice, kwargs
        self.bound_tool_names = [
            getattr(tool, "name", "")
            if not isinstance(tool, dict)
            else str(tool.get("name", ""))
            for tool in tools
        ]
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        self.call_count += 1
        if self.call_count == 1:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {
                            "file_path": "/workspace/research-report.md",
                            "content": "# Canonical report\n",
                        },
                        "id": "call-write-report",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            message = AIMessage(content="Canonical report written.")
        return ChatResult(generations=[ChatGeneration(message=message)])


class ScriptedMissingThenWriteModel(ScriptedCanonicalWriteModel):
    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        self.call_count += 1
        if self.call_count == 1:
            message = AIMessage(content="Finished without a canonical file.")
        elif self.call_count == 2:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {
                            "file_path": "/workspace/research-report.md",
                            "content": "# Corrected canonical report\n",
                        },
                        "id": "call-corrected-write",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            message = AIMessage(content="Corrected canonical report written.")
        return ChatResult(generations=[ChatGeneration(message=message)])


class ScriptedNeverWriteModel(ScriptedCanonicalWriteModel):
    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        self.call_count += 1
        return ChatResult(
            generations=[
                ChatGeneration(message=AIMessage(content="No canonical file."))
            ]
        )


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


def _real_deepagents_harness(model: BaseChatModel, *, completion_guard: bool):
    backend = CompositeBackend(default=StateBackend(), routes={})
    permissions = tuple(build_filesystem_permissions())
    graph = create_deep_agent(
        model=model,
        tools=[],
        system_prompt="Write the requested canonical report.",
        middleware=(
            build_profile_middleware("generic", role="coordinator")
            if completion_guard
            else []
        ),
        subagents=[],
        permissions=list(permissions),
        backend=backend,
        context_schema=ResearchRuntimeContext,
        name="canonical-write-integration",
    )
    return DeepAgentsHarness(
        graph=graph,
        backend=backend,
        permissions=permissions,
        skills=(),
        profile_graphs={"generic": graph},
    )


@pytest.mark.asyncio
async def test_locked_deepagents_write_file_reaches_application_observer(tmp_path):
    model = ScriptedCanonicalWriteModel()
    harness = _real_deepagents_harness(model, completion_guard=False)
    service = ResearchExecutionService(
        harness=harness,
        project_root=tmp_path,
    )

    outcome = await service.execute(
        "Produce the canonical report.",
        "thread-write-1",
        run_id="run-write-1",
        segment_id="segment-write-1",
        profile_id="generic",
    )

    assert "write_file" in model.bound_tool_names
    assert model.call_count == 2
    assert outcome.report_candidate == ReportCandidate(
        path=PurePosixPath("/workspace/research-report.md"),
        content="# Canonical report\n",
    )


@pytest.mark.asyncio
async def test_generic_completion_guard_adds_no_call_when_report_exists(tmp_path):
    model = ScriptedCanonicalWriteModel()
    service = ResearchExecutionService(
        harness=_real_deepagents_harness(model, completion_guard=True),
        project_root=tmp_path,
    )

    outcome = await service.execute(
        "Produce the canonical report.",
        "thread-existing-report-1",
        run_id="run-existing-report-1",
        segment_id="segment-existing-report-1",
        profile_id="generic",
    )

    assert model.call_count == 2
    assert outcome.report_candidate == ReportCandidate(
        path=PurePosixPath("/workspace/research-report.md"),
        content="# Canonical report\n",
    )


@pytest.mark.asyncio
async def test_generic_completion_guard_uses_native_write_file_once(tmp_path):
    model = ScriptedMissingThenWriteModel()
    service = ResearchExecutionService(
        harness=_real_deepagents_harness(model, completion_guard=True),
        project_root=tmp_path,
    )

    outcome = await service.execute(
        "Produce the canonical report.",
        "thread-correction-1",
        run_id="run-correction-1",
        segment_id="segment-correction-1",
        profile_id="generic",
    )

    assert model.call_count == 3
    assert outcome.report_candidate == ReportCandidate(
        path=PurePosixPath("/workspace/research-report.md"),
        content="# Corrected canonical report\n",
    )


@pytest.mark.asyncio
async def test_generic_completion_guard_stops_after_one_unsuccessful_correction(
    tmp_path,
):
    model = ScriptedNeverWriteModel()
    service = ResearchExecutionService(
        harness=_real_deepagents_harness(model, completion_guard=True),
        project_root=tmp_path,
    )

    outcome = await service.execute(
        "Produce the canonical report.",
        "thread-correction-2",
        run_id="run-correction-2",
        segment_id="segment-correction-2",
        profile_id="generic",
    )

    assert model.call_count == 2
    assert outcome.report_candidate is None


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
