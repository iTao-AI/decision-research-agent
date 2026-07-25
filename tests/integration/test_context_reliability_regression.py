from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult

from agent.harness_contracts import ReportCandidate
from api.research_execution_service import ResearchExecutionService


FIXED_QUERY = "Compare the fixed synthetic context reliability scenario."
PRE_SUMMARY_SEARCH_QUERY = "fixed context source"
POST_SUMMARY_SEARCH_QUERY = "fixed post-summary context source"
SOURCE_URL = "https://example.com/context-source"
SOURCE_CONTENT = "Bounded synthetic source content."
REPORT_CONTENT = f"# Context report\n\nSource: {SOURCE_URL}\n"
LARGE_TASK_RESULT = "Research complete. " + ("synthetic-context " * 2000)
SECOND_TASK_RESULT = "Post-summary duplicate search complete."
CONTROL_MAX_INPUT_TOKENS = 32768
FORCED_MAX_INPUT_TOKENS = 16384
WORKER_ID = "dispatch_worker_0000000000000000000000000000000c"


@dataclass
class ContextCallRecorder:
    coordinator_calls: int = 0
    researcher_calls: int = 0
    summary_calls: int = 0
    consumed_summary_calls: int = 0
    events: list[str] = field(default_factory=list)
    effective_message_sources: list[list[str | None]] = field(
        default_factory=list
    )
    task_args: list[dict[str, str]] = field(default_factory=list)
    task_results: list[str] = field(default_factory=list)
    search_tool_emissions: list[str] = field(default_factory=list)
    search_payloads: list[bytes] = field(default_factory=list)


class ScriptedContextReliabilityModel(BaseChatModel):
    profile: dict[str, Any] | None = None
    recorder: ContextCallRecorder
    bound_tool_names: tuple[str, ...] = ()

    @property
    def _llm_type(self) -> str:
        return "scripted-context-reliability-model"

    def bind_tools(
        self,
        tools: Sequence,
        *,
        tool_choice: dict | str | bool | None = None,
        **kwargs: Any,
    ):
        del tool_choice, kwargs
        names = tuple(
            (
                getattr(tool, "name", "")
                if not isinstance(tool, dict)
                else str(tool.get("name", ""))
            )
            for tool in tools
        )
        return self.model_copy(update={"bound_tool_names": names})

    @staticmethod
    def _is_summary_call(run_manager) -> bool:
        metadata = getattr(run_manager, "metadata", {}) or {}
        return metadata.get("lc_source") == "summarization"

    def _researcher_response(self) -> AIMessage:
        self.recorder.researcher_calls += 1
        if self.recorder.researcher_calls == 1:
            self.recorder.events.append("pre_search_tool_emission")
            self.recorder.search_tool_emissions.append(
                PRE_SUMMARY_SEARCH_QUERY
            )
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "internet_search",
                        "args": {"query": PRE_SUMMARY_SEARCH_QUERY},
                        "id": "call-pre-summary-search",
                        "type": "tool_call",
                    }
                ],
            )
        if self.recorder.researcher_calls == 2:
            self.recorder.events.append("large_task_result")
            self.recorder.task_results.append(LARGE_TASK_RESULT)
            return AIMessage(content=LARGE_TASK_RESULT)
        if self.recorder.researcher_calls in {3, 4}:
            emission = self.recorder.researcher_calls - 2
            self.recorder.events.append(
                f"post_search_tool_emission_{emission}"
            )
            self.recorder.search_tool_emissions.append(
                POST_SUMMARY_SEARCH_QUERY
            )
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "internet_search",
                        "args": {"query": POST_SUMMARY_SEARCH_QUERY},
                        "id": f"call-post-summary-search-{emission}",
                        "type": "tool_call",
                    }
                ],
            )
        self.recorder.events.append("post_summary_provider_once_observed")
        self.recorder.events.append("second_task_result")
        self.recorder.task_results.append(SECOND_TASK_RESULT)
        return AIMessage(content=SECOND_TASK_RESULT)

    def _coordinator_response(
        self,
        messages: list[BaseMessage],
    ) -> AIMessage:
        self.recorder.coordinator_calls += 1
        self.recorder.effective_message_sources.append(
            [
                message.additional_kwargs.get("lc_source")
                for message in messages
                if isinstance(message, HumanMessage)
            ]
        )
        receives_summary = any(
            isinstance(item, HumanMessage)
            and item.additional_kwargs.get("lc_source") == "summarization"
            for item in messages
        )
        if (
            receives_summary
            and self.recorder.consumed_summary_calls
            < self.recorder.summary_calls
        ):
            self.recorder.consumed_summary_calls += 1
            self.recorder.events.append(
                "coordinator_after_summary_"
                f"{self.recorder.consumed_summary_calls}"
            )
        if self.recorder.coordinator_calls == 1:
            task_args = {
                "description": "Run the pre-summary fixed synthetic search.",
                "subagent_type": "network_search",
            }
            self.recorder.task_args.append(task_args)
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": task_args,
                        "id": "call-pre-summary-task",
                        "type": "tool_call",
                    }
                ],
            )
        if self.recorder.coordinator_calls == 2:
            task_args = {
                "description": (
                    "Run two exact sequential post-summary searches."
                ),
                "subagent_type": "network_search",
            }
            self.recorder.task_args.append(task_args)
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": task_args,
                        "id": "call-post-summary-task",
                        "type": "tool_call",
                    }
                ],
            )
        if not any(
            isinstance(item, ToolMessage) and item.name == "write_file"
            for item in messages
        ):
            assert self.recorder.task_results == [
                LARGE_TASK_RESULT,
                SECOND_TASK_RESULT,
            ]
            self.recorder.events.append("write_file")
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {
                            "file_path": "/workspace/research-report.md",
                            "content": REPORT_CONTENT,
                        },
                        "id": "call-write-report",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content="Context report written.")

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, kwargs
        if self._is_summary_call(run_manager):
            self.recorder.summary_calls += 1
            self.recorder.events.append(
                f"summary_{self.recorder.summary_calls}"
            )
            message = AIMessage(content="Bounded native summary.")
        elif (
            "internet_search" in self.bound_tool_names
            and "task" not in self.bound_tool_names
        ):
            message = self._researcher_response()
        else:
            message = self._coordinator_response(messages)
        return ChatResult(generations=[ChatGeneration(message=message)])


def _build_lane_harness(monkeypatch, *, forced: bool):
    import tools.tavily_tools as tavily_tools

    calls: list[tuple[str, dict[str, Any]]] = []
    recorder = ContextCallRecorder()
    model = ScriptedContextReliabilityModel(
        profile={
            "max_input_tokens": (
                FORCED_MAX_INPUT_TOKENS
                if forced
                else CONTROL_MAX_INPUT_TOKENS
            )
        },
        recorder=recorder,
    )

    def fake_search(query: str, **kwargs: Any) -> str:
        calls.append((query, dict(kwargs)))
        payload = json.dumps(
            {
                "results": [
                    {"url": SOURCE_URL, "content": SOURCE_CONTENT}
                ]
            },
            sort_keys=True,
        )
        recorder.search_payloads.append(payload.encode("utf-8"))
        return payload

    monkeypatch.setattr(tavily_tools, "_internet_search_impl", fake_search)

    from agent.deepagents_harness import build_generic_harness

    return build_generic_harness(model=model), recorder, calls


@pytest.mark.asyncio
async def test_control_and_forced_lanes_observe_native_summary_only_when_forced(
    tmp_path,
    monkeypatch,
) -> None:
    observations = {}
    for forced in (False, True):
        harness, recorder, search_calls = _build_lane_harness(
            monkeypatch,
            forced=forced,
        )
        service = ResearchExecutionService(
            harness=harness,
            project_root=tmp_path / ("forced" if forced else "control"),
        )
        outcome = await service.execute(
            FIXED_QUERY,
            f"thread-{'forced' if forced else 'control'}",
            run_id=f"run-{'forced' if forced else 'control'}",
            segment_id=f"segment-{'forced' if forced else 'control'}",
            profile_id="generic",
        )
        observations[forced] = (
            FIXED_QUERY.encode("utf-8"),
            recorder,
            outcome,
            search_calls,
        )

    control_query, control_recorder, control_outcome, control_calls = (
        observations[False]
    )
    forced_query, forced_recorder, forced_outcome, forced_calls = (
        observations[True]
    )
    assert control_query == forced_query == FIXED_QUERY.encode("utf-8")
    assert control_recorder.summary_calls == 0
    assert forced_recorder.summary_calls == 2, forced_recorder.events
    assert forced_recorder.consumed_summary_calls == 2
    expected_task_args = [
        {
            "description": "Run the pre-summary fixed synthetic search.",
            "subagent_type": "network_search",
        },
        {
            "description": "Run two exact sequential post-summary searches.",
            "subagent_type": "network_search",
        },
    ]
    expected_search_calls = [
        (
            PRE_SUMMARY_SEARCH_QUERY,
            {
                "max_results": 5,
                "topic": "general",
                "include_raw_content": False,
            },
        ),
        (
            POST_SUMMARY_SEARCH_QUERY,
            {
                "max_results": 5,
                "topic": "general",
                "include_raw_content": False,
            },
        ),
    ]
    assert (
        control_recorder.task_args
        == forced_recorder.task_args
        == expected_task_args
    )
    assert (
        control_recorder.task_results
        == forced_recorder.task_results
        == [LARGE_TASK_RESULT, SECOND_TASK_RESULT]
    )
    assert (
        control_recorder.search_tool_emissions
        == forced_recorder.search_tool_emissions
        == [
            PRE_SUMMARY_SEARCH_QUERY,
            POST_SUMMARY_SEARCH_QUERY,
            POST_SUMMARY_SEARCH_QUERY,
        ]
    )
    assert control_recorder.search_payloads == forced_recorder.search_payloads
    assert control_calls == forced_calls == expected_search_calls
    required_forced_order = [
        "pre_search_tool_emission",
        "large_task_result",
        "summary_1",
        "coordinator_after_summary_1",
        "post_search_tool_emission_1",
        "post_search_tool_emission_2",
        "post_summary_provider_once_observed",
        "second_task_result",
        "summary_2",
        "coordinator_after_summary_2",
        "write_file",
    ]
    assert [
        event
        for event in forced_recorder.events
        if event in required_forced_order
    ] == required_forced_order
    assert not any(
        event.startswith("summary_")
        or event.startswith("coordinator_after_summary_")
        for event in control_recorder.events
    )
    assert any(
        "summarization" in sources
        for sources in forced_recorder.effective_message_sources
    )
    assert (
        control_outcome.report_candidate
        == forced_outcome.report_candidate
        == ReportCandidate(
            path=PurePosixPath("/workspace/research-report.md"),
            content=REPORT_CONTENT,
        )
    )
