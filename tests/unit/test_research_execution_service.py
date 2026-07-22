from __future__ import annotations

from pathlib import Path

import pytest

from agent.harness_contracts import CallBudgetDiagnostic, HarnessExecutionError
from api.research_execution_service import ResearchExecutionService


def _diagnostic() -> CallBudgetDiagnostic:
    return CallBudgetDiagnostic(
        limiter_kind="tool",
        tool_scope="task",
        run_count=6,
        run_limit=5,
        thread_count=6,
        thread_limit=None,
        agent_role="not_observed",
    )


class FailingHarness:
    def __init__(self, error: HarnessExecutionError):
        self.error = error

    async def execute(self, request, *, runtime_context, observer):
        del request, runtime_context, observer
        raise self.error


@pytest.mark.asyncio
async def test_execution_service_writes_only_typed_call_budget_diagnostic(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, CallBudgetDiagnostic]] = []
    diagnostic = _diagnostic()
    service = ResearchExecutionService(
        harness=FailingHarness(
            HarnessExecutionError(
                failure_kind="call_budget_exceeded",
                message="private native failure",
                call_budget_diagnostic=diagnostic,
            )
        ),
        project_root=tmp_path,
        call_budget_diagnostic_writer=lambda run_id, value: calls.append(
            (run_id, value)
        ),
    )

    outcome = await service.execute("query", "thread-1", run_id="run-1")

    assert calls == [("run-1", diagnostic)]
    assert outcome.failure_kind == "call_budget_exceeded"
    assert outcome.evidence_entries == []
    assert outcome.report_candidate is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_kind",
    ["recursion_limit_exceeded", "execution_error", "cancelled"],
)
async def test_execution_service_does_not_write_for_other_failures(
    tmp_path: Path,
    failure_kind: str,
) -> None:
    calls: list[object] = []
    service = ResearchExecutionService(
        harness=FailingHarness(
            HarnessExecutionError(
                failure_kind=failure_kind,
                message="private failure",
            )
        ),
        project_root=tmp_path,
        call_budget_diagnostic_writer=lambda *args: calls.append(args),
    )

    outcome = await service.execute("query", "thread-1", run_id="run-1")

    assert calls == []
    assert outcome.failure_kind == failure_kind


@pytest.mark.asyncio
async def test_execution_service_writer_failure_cannot_change_frozen_outcome(
    tmp_path: Path,
) -> None:
    diagnostic = _diagnostic()

    def fail_writer(_run_id: str, _diagnostic: CallBudgetDiagnostic) -> None:
        raise RuntimeError("private filesystem details")

    service = ResearchExecutionService(
        harness=FailingHarness(
            HarnessExecutionError(
                failure_kind="call_budget_exceeded",
                message="native public-compatible message",
                call_budget_diagnostic=diagnostic,
            )
        ),
        project_root=tmp_path,
        call_budget_diagnostic_writer=fail_writer,
    )

    outcome = await service.execute("query", "thread-1", run_id="run-1")

    assert outcome.failure_kind == "call_budget_exceeded"
    assert outcome.error_message == "native public-compatible message"
    assert "private filesystem details" not in repr(outcome)
    assert "call_budget_diagnostic_write_failed" in outcome.diagnostics
