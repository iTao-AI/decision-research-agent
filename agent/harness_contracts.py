"""Application-owned contracts for Agent harness execution."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Mapping, Protocol, Sequence

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


class HarnessExecutionError(RuntimeError):
    """Application-owned stable error raised by framework harness adapters."""

    def __init__(self, *, failure_kind: str, message: str):
        super().__init__(message)
        self.failure_kind = failure_kind


class AgentHarness(Protocol):
    """Port implemented by the framework-specific Agent harness."""

    async def execute(
        self,
        request: HarnessRequest,
        *,
        runtime_context: ResearchRuntimeContext,
        observer: ExecutionObserver,
    ) -> ExecutionOutcome: ...
