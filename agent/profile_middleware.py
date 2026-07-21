"""Compile server-owned model and tool call budgets for each Agent role."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Sequence

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
    hook_config,
)
from langchain.agents.middleware.types import AgentState, PrivateStateAttr
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime
from typing_extensions import NotRequired


_CANONICAL_REPORT_PATH = "/workspace/research-report.md"
_MAX_CANONICAL_REPORT_BYTES = 1024 * 1024
_CANONICAL_REPORT_CORRECTION = (
    "The required canonical artifact is still missing. Before ending, use the "
    "native write_file tool to create /workspace/research-report.md with the "
    "final Markdown report. Do not return the report only as chat text."
)


class CanonicalReportCompletionState(AgentState):
    canonical_report_correction_count: NotRequired[
        Annotated[int, PrivateStateAttr]
    ]


def _has_valid_canonical_report(state: Mapping[str, Any]) -> bool:
    files = state.get("files")
    if not isinstance(files, Mapping):
        return False
    file_data = files.get(_CANONICAL_REPORT_PATH)
    if not isinstance(file_data, Mapping):
        return False
    content = file_data.get("content")
    if isinstance(content, list):
        content = "\n".join(str(item) for item in content)
    return (
        isinstance(content, str)
        and bool(content.strip())
        and len(content.encode("utf-8")) <= _MAX_CANONICAL_REPORT_BYTES
    )


class CanonicalReportCompletionMiddleware(
    AgentMiddleware[CanonicalReportCompletionState]
):
    """Give the generic coordinator one native chance to close its report."""

    state_schema = CanonicalReportCompletionState

    @hook_config(can_jump_to=["model"])
    def after_model(
        self,
        state: CanonicalReportCompletionState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        del runtime
        messages = state.get("messages", [])
        last_message = messages[-1] if messages else None
        if (
            not isinstance(last_message, AIMessage)
            or last_message.tool_calls
            or _has_valid_canonical_report(state)
            or state.get("canonical_report_correction_count", 0) >= 1
        ):
            return None
        return {
            "messages": [HumanMessage(content=_CANONICAL_REPORT_CORRECTION)],
            "canonical_report_correction_count": 1,
            "jump_to": "model",
        }


def build_profile_middleware(
    profile_id: str,
    *,
    role: str,
) -> list[Any]:
    """Return immutable-policy Middleware for one profile role."""
    if profile_id == "generic" and role == "coordinator":
        return [
            CanonicalReportCompletionMiddleware(),
            ModelCallLimitMiddleware(run_limit=40, exit_behavior="error"),
            ToolCallLimitMiddleware(run_limit=40, exit_behavior="error"),
            ToolCallLimitMiddleware(
                tool_name="task",
                run_limit=8,
                exit_behavior="error",
            ),
        ]
    if profile_id == "generic" and role in {
        "network_search",
        "database_query",
        "knowledge_base",
    }:
        return [
            ModelCallLimitMiddleware(run_limit=20, exit_behavior="error"),
            ToolCallLimitMiddleware(run_limit=12, exit_behavior="error"),
        ]
    if profile_id == "talent-hiring-signal" and role == "researcher":
        return [
            ModelCallLimitMiddleware(run_limit=12, exit_behavior="error"),
        ]
    raise ValueError(f"unsupported profile middleware role: {profile_id}:{role}")


def middleware_contract(middleware: Sequence[Any]) -> dict[str, Any]:
    """Return the bounded call-limit policy represented by Middleware."""
    contract = {
        "model_run_limit": None,
        "global_tool_run_limit": None,
        "task_run_limit": None,
        "exit_behavior": "error",
    }
    for item in middleware:
        if isinstance(item, ModelCallLimitMiddleware):
            contract["model_run_limit"] = item.run_limit
            contract["exit_behavior"] = item.exit_behavior
        elif isinstance(item, ToolCallLimitMiddleware):
            key = (
                "task_run_limit"
                if item.tool_name == "task"
                else "global_tool_run_limit"
            )
            contract[key] = item.run_limit
            contract["exit_behavior"] = item.exit_behavior
    return contract
