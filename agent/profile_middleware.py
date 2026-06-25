"""Compile server-owned model and tool call budgets for each Agent role."""
from __future__ import annotations

from typing import Any, Sequence

from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)


def build_profile_middleware(
    profile_id: str,
    *,
    role: str,
) -> list[Any]:
    """Return immutable-policy Middleware for one profile role."""
    if profile_id == "generic" and role == "coordinator":
        return [
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
