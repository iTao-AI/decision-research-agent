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


MAX_FINDINGS_CANDIDATE_BYTES = 256 * 1024
FINDINGS_CANDIDATE_PATH = PurePosixPath("/workspace/research-findings.json")


@dataclass(frozen=True)
class FindingsCandidate:
    """Bounded root virtual-workspace input, never delivery authority."""

    path: PurePosixPath
    content: str

    def __post_init__(self) -> None:
        if self.path != FINDINGS_CANDIDATE_PATH:
            raise ValueError("findings candidate must use the canonical workspace path")
        if type(self.content) is not str or len(self.content.encode("utf-8")) > MAX_FINDINGS_CANDIDATE_BYTES:
            raise ValueError("findings candidate must be bounded UTF-8")


def capture_findings_candidate(
    file_data: Any,
) -> tuple[FindingsCandidate | None, Literal[
    "candidate_contract_invalid", "candidate_too_large", "candidate_invalid_json",
] | None]:
    """Check byte bounds before joining native lines; discard invalid replacements."""
    if not isinstance(file_data, Mapping):
        return None, "candidate_contract_invalid"
    content = file_data.get("content")
    if type(content) is str:
        parts = [content]
    elif type(content) is list and all(type(item) is str for item in content):
        parts = content
    else:
        return None, "candidate_contract_invalid"
    total = max(0, len(parts) - 1)
    if total > MAX_FINDINGS_CANDIDATE_BYTES:
        return None, "candidate_too_large"
    try:
        for part in parts:
            if len(part) > MAX_FINDINGS_CANDIDATE_BYTES - total:
                return None, "candidate_too_large"
            total += len(part.encode("utf-8"))
            if total > MAX_FINDINGS_CANDIDATE_BYTES:
                return None, "candidate_too_large"
    except UnicodeError:
        return None, "candidate_invalid_json"
    return FindingsCandidate(FINDINGS_CANDIDATE_PATH, "\n".join(parts)), None


class ExecutionObserver(Protocol):
    """Application-owned hooks for stream processing and diagnostics."""

    def on_stream_chunk(self, chunk: Mapping[str, Any]) -> None: ...

    def on_nested_stream_chunk(
        self,
        namespace: tuple[str, ...],
        chunk: Mapping[str, Any],
    ) -> None: ...

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
