"""Lightweight agent run result contracts.

This module intentionally avoids importing agent.main_agent so tests can cover
stream processing without initializing the LLM-backed DeepAgent.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.research import EvidenceEntry, extract_evidence_entries
from langchain_core.messages import AIMessage, ToolMessage


@dataclass(frozen=True)
class AgentRunResult:
    """Summary of one main-agent execution."""

    thread_id: str
    query: str
    session_dir: Path
    started_at: datetime | None = None
    last_agent_text: str = ""
    assistant_calls: int = 0
    tool_starts: int = 0
    diagnostics: list[str] = field(default_factory=list)
    evidence_entries: list[EvidenceEntry] = field(default_factory=list)
    error_message: str | None = None


@dataclass
class AgentRunAccumulator:
    """Mutable state collected while streaming LangGraph chunks."""

    thread_id: str
    query: str
    session_dir: Path
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_agent_text: str = ""
    assistant_calls: int = 0
    tool_starts: int = 0
    diagnostics: list[str] = field(default_factory=list)
    evidence_entries: list[EvidenceEntry] = field(default_factory=list)

    def to_result(self, error_message: str | None = None) -> AgentRunResult:
        return AgentRunResult(
            thread_id=self.thread_id,
            query=self.query,
            session_dir=self.session_dir,
            started_at=self.started_at,
            last_agent_text=self.last_agent_text,
            assistant_calls=self.assistant_calls,
            tool_starts=self.tool_starts,
            diagnostics=list(self.diagnostics),
            evidence_entries=list(self.evidence_entries),
            error_message=error_message,
        )


def _text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return str(content) if content is not None else ""


def _tool_value(tool: Any, key: str, default: Any = None) -> Any:
    if isinstance(tool, dict):
        return tool.get(key, default)
    return getattr(tool, key, default)


def process_stream_chunk(
    chunk: dict[str, Any], accumulator: AgentRunAccumulator, monitor
) -> None:
    """Process LangGraph stream output and report events to frontend."""
    for node_name, state in chunk.items():
        if not state or "messages" not in state:
            continue

        messages = state["messages"]
        if not isinstance(messages, list) or not messages:
            continue

        last_msg = messages[-1]

        if isinstance(last_msg, AIMessage):
            if last_msg.tool_calls:
                for tool in last_msg.tool_calls:
                    if _tool_value(tool, "name") != "task":
                        continue

                    args = _tool_value(tool, "args", {}) or {}
                    accumulator.assistant_calls += 1
                    monitor.report_assistant(
                        args.get("subagent_type", "Agent"),
                        {"desc": args.get("description")},
                    )
            elif last_msg.content:
                text = _text_from_content(last_msg.content).strip()
                if text:
                    accumulator.last_agent_text = text
                    monitor.report_task_result(text)

        elif isinstance(last_msg, ToolMessage):
            accumulator.tool_starts += 1
            tool_name = getattr(last_msg, "name", None) or node_name
            accumulator.diagnostics.append(f"tool:{tool_name}")
            accumulator.evidence_entries.extend(
                extract_evidence_entries(
                    thread_id=accumulator.thread_id,
                    query_text=accumulator.query,
                    subagent_name=node_name,
                    tool_name=tool_name,
                    content=last_msg.content,
                )
            )
