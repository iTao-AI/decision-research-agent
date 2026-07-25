from __future__ import annotations

import json
import re
import sqlite3
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
from scripts.agent_evaluation_context import (
    compare_context_reliability_outcomes,
    project_context_reliability_outcome,
)


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
FORCED_EVENT_ORDER = (
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
)
_SUMMARY_MARKER_RE = re.compile(r"\[(summary_[1-9][0-9]*)\]")


@dataclass
class ContextCallRecorder:
    coordinator_calls: int = 0
    researcher_calls: int = 0
    summary_calls: int = 0
    consumed_summary_calls: int = 0
    consumed_summary_markers: list[str] = field(default_factory=list)
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
        expected_summary_marker = (
            f"summary_{self.recorder.consumed_summary_calls + 1}"
        )
        received_summary_markers = [
            marker
            for item in messages
            if (
                isinstance(item, HumanMessage)
                and item.additional_kwargs.get("lc_source")
                == "summarization"
                and isinstance(item.content, str)
            )
            for marker in _SUMMARY_MARKER_RE.findall(item.content)
        ]
        receives_expected_summary = (
            expected_summary_marker in received_summary_markers
        )
        if (
            receives_expected_summary
            and self.recorder.consumed_summary_calls
            < self.recorder.summary_calls
        ):
            self.recorder.consumed_summary_calls += 1
            self.recorder.consumed_summary_markers.append(
                expected_summary_marker
            )
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
            marker = f"summary_{self.recorder.summary_calls}"
            self.recorder.events.append(marker)
            message = AIMessage(
                content=f"Bounded native summary [{marker}]."
            )
        elif (
            "internet_search" in self.bound_tool_names
            and "task" not in self.bound_tool_names
        ):
            message = self._researcher_response()
        else:
            message = self._coordinator_response(messages)
        return ChatResult(generations=[ChatGeneration(message=message)])


def test_stale_summary_message_cannot_satisfy_next_consumption_boundary() -> None:
    recorder = ContextCallRecorder(
        coordinator_calls=1,
        summary_calls=2,
        consumed_summary_calls=1,
    )
    model = ScriptedContextReliabilityModel(recorder=recorder)

    model._coordinator_response(
        [
            HumanMessage(
                content=(
                    "Here is a summary of the conversation to date:\n\n"
                    "Bounded native summary [summary_1]."
                ),
                additional_kwargs={"lc_source": "summarization"},
            )
        ]
    )

    assert recorder.consumed_summary_calls == 1
    assert recorder.consumed_summary_markers == []
    assert "coordinator_after_summary_2" not in recorder.events


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
    assert forced_recorder.consumed_summary_markers == [
        "summary_1",
        "summary_2",
    ]
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
    assert [
        event
        for event in forced_recorder.events
        if event in FORCED_EVENT_ORDER
    ] == list(FORCED_EVENT_ORDER)
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


async def _run_persisted_lane(
    *,
    db_path: str,
    thread_id: str,
    harness,
    monkeypatch,
    project_root,
):
    import api.server as server
    from api.run_dispatch_repository import claim_run_dispatch
    from api.run_repository import create_run, get_run
    from api.run_result_service import resolve_run_result

    service = ResearchExecutionService(
        harness=harness,
        project_root=project_root,
    )

    async def test_adapter(
        query: str,
        persisted_thread_id: str,
        **kwargs,
    ):
        return await service.execute(
            query,
            persisted_thread_id,
            run_id=kwargs["run_id"],
            segment_id=kwargs["segment_id"],
            outcome_box=kwargs["outcome_box"],
            profile_id=kwargs["profile_id"],
            scope=kwargs["scope"],
        )

    monkeypatch.setattr(server, "run_deep_agent", test_adapter)
    created = create_run(
        db_path=db_path,
        thread_id=thread_id,
        query=FIXED_QUERY,
    )
    claim = claim_run_dispatch(
        db_path=db_path,
        worker_id=WORKER_ID,
        lease_seconds=30,
        run_id=created["run_id"],
    )
    assert claim is not None
    stage = server._RunStage()
    origin = server.TerminationOrigin()
    checkpoint = server.FinalizationCheckpoint()
    task = server.create_tracked_task(
        server._run_dispatched_with_persistence(
            claim,
            db_path=db_path,
            outcome_box=server.OutcomeBox(),
            stage=stage,
            termination_origin=origin,
            finalization_checkpoint=checkpoint,
        ),
        f"{claim.run_id}:context-reliability:{claim.attempt_count}",
        timeout_seconds=30,
        termination_origin=origin,
        finalization_checkpoint=checkpoint,
    )
    await task
    persisted = get_run(db_path=db_path, run_id=created["run_id"])
    assert persisted is not None
    resolved = resolve_run_result(
        db_path=db_path,
        run_id=created["run_id"],
    )
    return created, persisted, resolved


def _dispatch_status(db_path: str, run_id: str) -> str:
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT status FROM run_dispatches_v1 WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    return row[0]


@pytest.mark.asyncio
async def test_paired_persisted_application_outcomes_remain_equivalent(
    tmp_path,
    monkeypatch,
) -> None:
    from tools.tavily_tools import _search_cache

    lane_results = {}
    lane_recorders = {}
    for forced in (False, True):
        lane_name = "forced" if forced else "control"
        lane_db_path = str(tmp_path / f"{lane_name}.db")
        harness, recorder, _ = _build_lane_harness(
            monkeypatch,
            forced=forced,
        )
        created, persisted, resolved = await _run_persisted_lane(
            db_path=lane_db_path,
            thread_id=f"thread-{lane_name}",
            harness=harness,
            monkeypatch=monkeypatch,
            project_root=tmp_path / lane_name,
        )
        lane_recorders[forced] = recorder
        assert persisted["state_version"] == 2
        assert persisted["segments"][0]["status"] == "completed"
        assert persisted["failure_cause"] is None
        assert persisted["execution_status"] == "completed"
        assert persisted["review_status"] == "not_required"
        assert persisted["delivery_status"] == "ready"
        assert _dispatch_status(
            lane_db_path,
            created["run_id"],
        ) == "started"
        assert [item["artifact_id"] for item in persisted["artifacts"]] == [
            "research-report.md"
        ]
        assert len(persisted["evidence"]) == 1
        evidence = persisted["evidence"][0]
        assert evidence["evidence_id"] == (
            f"ev_{created['run_id']}_{evidence['evidence_fingerprint']}"
        )
        assert evidence["subagent_name"] == "network_search"
        assert evidence["tool_name"] == "internet_search"
        assert evidence["source_url"] == SOURCE_URL
        assert evidence["snippet"] == SOURCE_CONTENT
        assert evidence["citation_status"] == "cited"
        assert evidence["verification_status"] == "unverified"
        lane_results[forced] = project_context_reliability_outcome(
            run=persisted,
            resolution=resolved,
        )
        assert created["run_id"] not in _search_cache

    assert lane_recorders[False].summary_calls == 0
    assert lane_recorders[True].summary_calls == 2
    assert compare_context_reliability_outcomes(
        lane_results[False],
        lane_results[True],
    ) == []


@pytest.mark.asyncio
async def test_forced_lane_preserves_nested_evidence_and_clears_exact_search_cache(
    tmp_path,
    monkeypatch,
) -> None:
    from tools.tavily_tools import _search_cache

    db_path = str(tmp_path / "forced-evidence.db")
    harness, recorder, search_calls = _build_lane_harness(
        monkeypatch,
        forced=True,
    )
    created, persisted, _ = await _run_persisted_lane(
        db_path=db_path,
        thread_id="thread-forced-evidence",
        harness=harness,
        monkeypatch=monkeypatch,
        project_root=tmp_path / "forced-evidence",
    )

    assert [
        event
        for event in recorder.events
        if event in FORCED_EVENT_ORDER
    ] == list(FORCED_EVENT_ORDER)
    assert recorder.summary_calls == 2
    assert recorder.consumed_summary_calls == 2
    assert recorder.consumed_summary_markers == [
        "summary_1",
        "summary_2",
    ]
    assert (
        recorder.search_tool_emissions.count(
            POST_SUMMARY_SEARCH_QUERY
        )
        == 2
    )
    assert search_calls == [
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
        [query for query, _ in search_calls].count(
            POST_SUMMARY_SEARCH_QUERY
        )
        == 1
    )
    assert len(persisted["evidence"]) == 1
    evidence = persisted["evidence"][0]
    assert evidence["evidence_id"] == (
        f"ev_{created['run_id']}_{evidence['evidence_fingerprint']}"
    )
    assert evidence["subagent_name"] == "network_search"
    assert evidence["tool_name"] == "internet_search"
    assert evidence["source_url"] == SOURCE_URL
    assert evidence["snippet"] == SOURCE_CONTENT
    assert evidence["citation_status"] == "cited"
    assert evidence["verification_status"] == "unverified"
    assert created["run_id"] not in _search_cache
