"""Compatibility entry point routed through the application execution service."""
from __future__ import annotations

import asyncio
from pathlib import Path
import uuid

from agent.deepagents_harness import build_generic_harness
from agent.llm import model
from agent.profile_agents import compile_profile_agent
from agent.profile_registry import AgentFactory, profile_registry
from agent.run_result import (
    AgentRunAccumulator,
    AgentRunResult,
    OutcomeBox,
)
from api.research_execution_service import (
    AccumulatorExecutionObserver,
    ResearchExecutionService,
)

project_root = Path(__file__).parents[1].resolve()

_generic_harness = build_generic_harness(model=model)
main_agent = _generic_harness.graph
agent_factory = AgentFactory(
    profile_registry,
    lambda profile, policy: compile_profile_agent(
        profile,
        policy,
        model=model,
        generic_agent=main_agent,
    ),
)

def _selected_harness(profile_id: str):
    harness = _generic_harness.with_profile_graph("generic", main_agent)
    if profile_id != "generic":
        harness = harness.with_profile_graph(
            profile_id,
            agent_factory.get(profile_id),
        )
    return harness


def _execution_service(profile_id: str) -> ResearchExecutionService:
    return ResearchExecutionService(
        harness=_selected_harness(profile_id),
        project_root=project_root,
    )


async def _preload_declared_aggregate_evidence(
    accumulator: AgentRunAccumulator,
    aggregate_ids: tuple[str, ...],
) -> None:
    service = _execution_service(accumulator.profile_id)
    await service._preload_declared_aggregate_evidence(
        accumulator,
        aggregate_ids,
    )


def _freeze_execution_outcome(
    accumulator: AgentRunAccumulator,
    outcome_box: OutcomeBox | None,
    *,
    error_message: str | None = None,
    failure_kind: str | None = None,
    cancellation_state: str | None = None,
) -> AgentRunResult:
    service = _execution_service(accumulator.profile_id)
    observer = AccumulatorExecutionObserver(accumulator)
    return service._freeze_outcome(
        observer,
        outcome_box,
        error_message=error_message,
        failure_kind=failure_kind,
        cancellation_state=cancellation_state,
    )


async def run_deep_agent(
    task_query: str,
    thread_id: str | None = None,
    run_id: str | None = None,
    segment_id: str | None = None,
    outcome_box: OutcomeBox | None = None,
    profile_id: str = "generic",
    scope: dict | None = None,
) -> AgentRunResult:
    """Execute one request through the application-owned harness port."""
    resolved_thread_id = thread_id or str(uuid.uuid4())
    return await _execution_service(profile_id).execute(
        task_query,
        resolved_thread_id,
        run_id=run_id,
        segment_id=segment_id,
        outcome_box=outcome_box,
        profile_id=profile_id,
        scope=scope,
    )


if __name__ == "__main__":
    task = input("请输入任务: ")
    asyncio.run(run_deep_agent(task))
