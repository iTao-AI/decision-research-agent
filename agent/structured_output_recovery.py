"""Recover provider-valid history after malformed structured tool calls."""
from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentState, Runtime, after_model
from langchain_core.messages import AIMessage, ToolMessage


_RETRY_MESSAGE = (
    "Error: The structured response arguments were not valid JSON. "
    "Return exactly one schema-valid structured response and do not include Markdown."
)


@after_model(name="InvalidStructuredToolCallRecoveryMiddleware")
def pair_invalid_structured_tool_calls(
    state: AgentState,
    runtime: Runtime,
) -> dict[str, Any] | None:
    """Pair malformed tool calls so the provider can accept the retry turn."""
    messages = state.get("messages", [])
    if not messages or not isinstance(messages[-1], AIMessage):
        return None

    tool_messages: list[ToolMessage] = []
    seen_ids: set[str] = set()
    for call in messages[-1].invalid_tool_calls:
        tool_call_id = call.get("id")
        if (
            not isinstance(tool_call_id, str)
            or not tool_call_id
            or tool_call_id in seen_ids
        ):
            continue
        seen_ids.add(tool_call_id)
        name = call.get("name")
        tool_messages.append(
            ToolMessage(
                content=_RETRY_MESSAGE,
                tool_call_id=tool_call_id,
                name=name if isinstance(name, str) and name else None,
                status="error",
            )
        )

    return {"messages": tool_messages} if tool_messages else None
