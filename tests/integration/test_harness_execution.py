import asyncio
from pathlib import PurePosixPath
from typing import Any, Sequence

import pytest
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool
from pydantic import Field

from agent.deepagents_harness import (
    DeepAgentsHarness,
    build_filesystem_permissions,
)
from agent.harness_contracts import (
    CallBudgetDiagnostic,
    HarnessExecutionError,
    HarnessRequest,
    ReportCandidate,
)
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


class ScriptedTaskDelegationModel(ScriptedCanonicalWriteModel):
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
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "task",
                                "args": {
                                    "description": "Run the bounded researcher.",
                                    "subagent_type": "bounded-researcher",
                                },
                                "id": "call-bounded-researcher",
                                "type": "tool_call",
                            }
                        ],
                    )
                )
            ]
        )


class ScriptedParallelToolModel(ScriptedCanonicalWriteModel):
    tool_rounds: int

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        self.call_count += 1
        if self.call_count <= self.tool_rounds:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "counted_tool",
                        "args": {"value": self.call_count * 2 + offset},
                        "id": f"call-{self.call_count}-{offset}",
                        "type": "tool_call",
                    }
                    for offset in range(2)
                ],
            )
        else:
            message = AIMessage(content="Finished.")
        return ChatResult(generations=[ChatGeneration(message=message)])


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


def _real_deepagents_harness(
    model: BaseChatModel,
    *,
    completion_guard: bool,
    middleware_override: Sequence[Any] | None = None,
):
    backend = CompositeBackend(default=StateBackend(), routes={})
    permissions = tuple(build_filesystem_permissions())
    middleware = (
        list(middleware_override)
        if middleware_override is not None
        else (
            build_profile_middleware("generic", role="coordinator")
            if completion_guard
            else []
        )
    )
    graph = create_deep_agent(
        model=model,
        tools=[],
        system_prompt="Write the requested canonical report.",
        middleware=middleware,
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


def _generic_researcher_limit_graph(
    model: BaseChatModel,
    executed_calls: list[int],
):
    def counted_tool(value: int) -> str:
        executed_calls.append(value)
        return str(value)

    tool = StructuredTool.from_function(
        counted_tool,
        name="counted_tool",
        description="Record one deterministic provider-free tool call.",
    )
    return create_agent(
        model=model,
        tools=[tool],
        middleware=build_profile_middleware(
            "generic",
            role="network_search",
        ),
    )


@pytest.mark.asyncio
async def test_generic_researcher_locked_graph_allows_calls_13_and_14():
    model = ScriptedParallelToolModel(tool_rounds=7)
    executed_calls: list[int] = []
    graph = _generic_researcher_limit_graph(model, executed_calls)

    await graph.ainvoke({"messages": [{"role": "user", "content": "run"}]})

    assert model.call_count == 8
    assert len(executed_calls) == 14


@pytest.mark.asyncio
async def test_generic_researcher_locked_graph_blocks_calls_17_and_18():
    model = ScriptedParallelToolModel(tool_rounds=9)
    executed_calls: list[int] = []
    graph = _generic_researcher_limit_graph(model, executed_calls)

    with pytest.raises(ToolCallLimitExceededError) as raised:
        await graph.ainvoke({"messages": [{"role": "user", "content": "run"}]})

    assert len(executed_calls) == 16
    assert raised.value.tool_name is None
    assert raised.value.run_limit == 16
    assert raised.value.run_count == 18
    assert raised.value.thread_limit is None
    assert raised.value.thread_count == 18


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("native_exception", "expected_diagnostic"),
    [
        pytest.param(
            ModelCallLimitExceededError(
                thread_count=7,
                run_count=7,
                thread_limit=None,
                run_limit=7,
            ),
            CallBudgetDiagnostic(
                limiter_kind="model",
                tool_scope="not_applicable",
                run_count=7,
                run_limit=7,
                thread_count=7,
                thread_limit=None,
                agent_role="not_observed",
            ),
            id="model",
        ),
        pytest.param(
            ToolCallLimitExceededError(
                thread_count=5,
                run_count=5,
                thread_limit=None,
                run_limit=5,
                tool_name=None,
            ),
            CallBudgetDiagnostic(
                limiter_kind="tool",
                tool_scope="all_tools",
                run_count=5,
                run_limit=5,
                thread_count=5,
                thread_limit=None,
                agent_role="not_observed",
            ),
            id="tool",
        ),
    ],
)
async def test_locked_deepagents_subagent_limit_reaches_outer_harness(
    native_exception,
    expected_diagnostic,
):
    subagent_calls = 0

    class RaisingSubagentModel(BaseChatModel):
        @property
        def _llm_type(self) -> str:
            return "raising-subagent-model"

        def bind_tools(self, tools: Sequence, **kwargs: Any):
            del tools, kwargs
            return self

        def _generate(
            self,
            messages: list[BaseMessage],
            stop: list[str] | None = None,
            run_manager=None,
            **kwargs: Any,
        ) -> ChatResult:
            nonlocal subagent_calls
            del messages, stop, run_manager, kwargs
            subagent_calls += 1
            raise native_exception

    subagent_graph = create_agent(
        model=RaisingSubagentModel(),
        tools=[],
        name="bounded-researcher",
    )
    coordinator = ScriptedTaskDelegationModel()
    backend = CompositeBackend(default=StateBackend(), routes={})
    permissions = tuple(build_filesystem_permissions())
    graph = create_deep_agent(
        model=coordinator,
        tools=[],
        system_prompt="Delegate exactly one bounded task.",
        middleware=[],
        subagents=[
            {
                "name": "bounded-researcher",
                "description": "Run one deterministic bounded task.",
                "runnable": subagent_graph,
            }
        ],
        permissions=list(permissions),
        backend=backend,
        context_schema=ResearchRuntimeContext,
        name="subagent-limit-integration",
    )
    harness = DeepAgentsHarness(
        graph=graph,
        backend=backend,
        permissions=permissions,
        skills=(),
        profile_graphs={"generic": graph},
    )

    class Observer:
        def callbacks(self):
            return []

        def on_stream_chunk(self, _chunk):
            return None

        def snapshot_outcome(self):
            raise AssertionError("native subagent failure must not produce success")

    context = ResearchRuntimeContext(
        thread_id="thread-subagent-limit-1",
        run_id="run-subagent-limit-1",
        segment_id="segment-subagent-limit-1",
        profile_id="generic",
    )

    with pytest.raises(HarnessExecutionError) as raised:
        await harness.execute(
            HarnessRequest(
                query="Delegate the bounded task.",
                thread_id=context.thread_id,
                run_id=context.run_id,
                segment_id=context.segment_id,
                profile_id=context.profile_id,
                scope={},
                trace_metadata={},
            ),
            runtime_context=context,
            observer=Observer(),
        )

    assert "task" in coordinator.bound_tool_names
    assert coordinator.call_count == 1
    assert subagent_calls == 1
    assert raised.value.failure_kind == "call_budget_exceeded"
    assert raised.value.call_budget_diagnostic == expected_diagnostic
    assert raised.value.__cause__ is native_exception


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
async def test_generic_completion_guard_cannot_bypass_model_call_limit(tmp_path):
    model = ScriptedNeverWriteModel()
    middleware = build_profile_middleware("generic", role="coordinator")
    model_limit_index = next(
        index
        for index, item in enumerate(middleware)
        if isinstance(item, ModelCallLimitMiddleware)
    )
    middleware[model_limit_index] = ModelCallLimitMiddleware(
        run_limit=1,
        exit_behavior="error",
    )
    service = ResearchExecutionService(
        harness=_real_deepagents_harness(
            model,
            completion_guard=False,
            middleware_override=middleware,
        ),
        project_root=tmp_path,
    )

    outcome = await service.execute(
        "Produce the canonical report.",
        "thread-budget-1",
        run_id="run-budget-1",
        segment_id="segment-budget-1",
        profile_id="generic",
    )

    assert outcome.failure_kind == "call_budget_exceeded"
    assert model.call_count == 1


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
