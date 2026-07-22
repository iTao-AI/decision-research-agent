"""Application-owned contracts for Agent harness execution."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, Mapping, Protocol, Sequence

if TYPE_CHECKING:
    from agent.run_result import ExecutionOutcome
    from agent.runtime_context import ResearchRuntimeContext


@dataclass(frozen=True)
class HarnessRequest:
    """Immutable application input passed to an Agent harness."""

    query: str
    thread_id: str
    run_id: str
    segment_id: str
    profile_id: str
    scope: Mapping[str, Any]
    trace_metadata: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope", MappingProxyType(dict(self.scope)))
        object.__setattr__(
            self,
            "trace_metadata",
            MappingProxyType(dict(self.trace_metadata)),
        )


@dataclass(frozen=True)
class ReportCandidate:
    """Bounded Markdown report returned from the harness virtual workspace."""

    path: PurePosixPath
    content: str

    def __post_init__(self) -> None:
        if self.path != PurePosixPath("/workspace/research-report.md"):
            raise ValueError("report candidate must use the canonical workspace path")


class ExecutionObserver(Protocol):
    """Application-owned hooks for stream processing and diagnostics."""

    def on_stream_chunk(self, chunk: Mapping[str, Any]) -> None: ...

    def on_error(self, error: Exception) -> None: ...

    def callbacks(self) -> Sequence[object]: ...

    def snapshot_outcome(self) -> ExecutionOutcome: ...


MAX_CALL_BUDGET_DIAGNOSTIC_COUNT = 1_000_000


@dataclass(frozen=True, slots=True)
class CallBudgetDiagnostic:
    """Closed projection of one native framework call-limit exception."""

    limiter_kind: Literal["model", "tool"]
    tool_scope: Literal["not_applicable", "all_tools", "task"]
    run_count: int
    run_limit: int
    thread_count: int
    thread_limit: int | None
    agent_role: Literal["not_observed"] = "not_observed"

    def __post_init__(self) -> None:
        if (
            type(self.run_count) is not int
            or type(self.run_limit) is not int
            or type(self.thread_count) is not int
            or self.thread_limit is not None
            and type(self.thread_limit) is not int
        ):
            raise ValueError("call_budget_diagnostic_invalid")
        counts = (self.run_count, self.thread_count)
        limits = (self.run_limit,) + (
            () if self.thread_limit is None else (self.thread_limit,)
        )
        if (
            self.limiter_kind not in {"model", "tool"}
            or self.tool_scope not in {"not_applicable", "all_tools", "task"}
            or self.agent_role != "not_observed"
            or any(
                value < 0 or value > MAX_CALL_BUDGET_DIAGNOSTIC_COUNT
                for value in counts
            )
            or any(
                value < 1 or value > MAX_CALL_BUDGET_DIAGNOSTIC_COUNT
                for value in limits
            )
            or self.limiter_kind == "model"
            and self.tool_scope != "not_applicable"
            or self.limiter_kind == "tool"
            and self.tool_scope == "not_applicable"
        ):
            raise ValueError("call_budget_diagnostic_invalid")


class HarnessExecutionError(RuntimeError):
    """Application-owned stable error raised by framework harness adapters."""

    def __init__(
        self,
        *,
        failure_kind: str,
        message: str,
        call_budget_diagnostic: CallBudgetDiagnostic | None = None,
    ):
        super().__init__(message)
        self.failure_kind = failure_kind
        if (
            call_budget_diagnostic is not None
            and type(call_budget_diagnostic) is not CallBudgetDiagnostic
        ):
            raise ValueError("call_budget_diagnostic_invalid")
        self.call_budget_diagnostic = call_budget_diagnostic


class AgentHarness(Protocol):
    """Port implemented by the framework-specific Agent harness."""

    async def execute(
        self,
        request: HarnessRequest,
        *,
        runtime_context: ResearchRuntimeContext,
        observer: ExecutionObserver,
    ) -> ExecutionOutcome: ...
