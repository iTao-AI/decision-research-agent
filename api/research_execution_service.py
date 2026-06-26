"""Application-owned orchestration around the framework Agent harness."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlparse

from langchain.agents.middleware.model_call_limit import (
    ModelCallLimitExceededError,
)
from langchain.agents.middleware.tool_call_limit import (
    ToolCallLimitExceededError,
)
from langgraph.errors import GraphRecursionError

from agent.harness_contracts import (
    AgentHarness,
    ExecutionObserver,
    HarnessRequest,
    ReportCandidate,
)
from agent.research import (
    extract_evidence_entries,
    merge_evidence_entries,
)
from agent.run_result import (
    AgentRunAccumulator,
    ExecutionOutcome,
    OutcomeBox,
    process_stream_chunk,
)
from agent.runtime_context import ResearchRuntimeContext
from agent.runtime_env import resolve_env
from agent.token_tracking import TokenTrackingCallbackHandler
from api.context import (
    reset_execution_context,
    set_allowed_aggregate_ids_context,
    set_allowed_source_domains_context,
    set_run_context,
    set_segment_context,
    set_thread_context,
)
from api.monitor import monitor
from api.thread_ids import safe_session_dir
from tools.tavily_tools import clear_search_cache

_TALENT_PROFILE_ID = "talent-hiring-signal"
_REPORT_PATH = PurePosixPath("/workspace/research-report.md")


def _allowed_source_domains(scope: Mapping[str, Any]) -> tuple[str, ...]:
    domains = set()
    for sample in scope.get("declared_samples", []):
        if not isinstance(sample, Mapping):
            continue
        if sample.get("source_type") != "public_job_posting":
            continue
        hostname = urlparse(str(sample.get("reference", ""))).hostname
        if hostname:
            domains.add(hostname.lower())
    return tuple(sorted(domains))


def _allowed_source_types(scope: Mapping[str, Any]) -> tuple[str, ...]:
    explicit = scope.get("allowed_source_types", [])
    if isinstance(explicit, Sequence) and not isinstance(explicit, (str, bytes)):
        values = [value for value in explicit if isinstance(value, str)]
        if values:
            return tuple(values)
    values = {
        sample["source_type"]
        for sample in scope.get("declared_samples", [])
        if isinstance(sample, Mapping)
        and isinstance(sample.get("source_type"), str)
    }
    return tuple(sorted(values))


def _allowed_aggregate_ids(scope: Mapping[str, Any]) -> tuple[str, ...]:
    aggregate_ids = {
        sample["reference"]
        for sample in scope.get("declared_samples", [])
        if isinstance(sample, Mapping)
        and sample.get("source_type") == "provided_aggregate"
        and isinstance(sample.get("reference"), str)
    }
    return tuple(sorted(aggregate_ids))


def _add_evidence_alias(
    accumulator: AgentRunAccumulator,
    alias: str,
    evidence_id: str,
) -> None:
    existing = list(accumulator.evidence_aliases.get(alias, ()))
    if evidence_id not in existing:
        existing.append(evidence_id)
    accumulator.evidence_aliases[alias] = tuple(existing)


def _mark_declared_fixture_evidence(
    entries,
    *,
    execution_id: str,
    verified_evidence_ids: set[str],
):
    if not verified_evidence_ids:
        return entries
    return [
        replace(
            entry,
            citation_status="cited",
            verification_status="verified",
            baseline_verification_origin="declared_fixture",
        )
        if f"ev_{execution_id}_{entry.evidence_fingerprint}"
        in verified_evidence_ids
        else entry
        for entry in entries
    ]


class AccumulatorExecutionObserver(ExecutionObserver):
    """Translate framework stream output into application-owned state."""

    def __init__(self, accumulator: AgentRunAccumulator):
        self.accumulator = accumulator
        self._callbacks = (
            TokenTrackingCallbackHandler(
                thread_id=accumulator.run_id or accumulator.thread_id
            ),
        )

    def on_stream_chunk(self, chunk: Mapping[str, Any]) -> None:
        process_stream_chunk(dict(chunk), self.accumulator, monitor)
        for state in chunk.values():
            if not isinstance(state, Mapping):
                continue
            files = state.get("files")
            if not isinstance(files, Mapping):
                continue
            file_data = files.get(_REPORT_PATH.as_posix())
            if not isinstance(file_data, Mapping):
                continue
            content = file_data.get("content")
            if isinstance(content, list):
                content = "\n".join(str(item) for item in content)
            if isinstance(content, str):
                self.accumulator.report_candidate = ReportCandidate(
                    path=_REPORT_PATH,
                    content=content,
                )

    def on_error(self, error: Exception) -> None:
        self.accumulator.diagnostics.append(
            f"harness_error:{type(error).__name__}"
        )

    def callbacks(self) -> Sequence[object]:
        return self._callbacks

    def snapshot_outcome(self) -> ExecutionOutcome:
        return self.accumulator.to_outcome()


class ResearchExecutionService:
    """Own accumulator, runtime context, Evidence freeze, and cleanup."""

    def __init__(
        self,
        *,
        harness: AgentHarness,
        project_root: Path,
        clear_run_cache: Callable[[str], None] = clear_search_cache,
    ):
        self.harness = harness
        self.project_root = project_root
        self.clear_run_cache = clear_run_cache

    async def _preload_declared_aggregate_evidence(
        self,
        accumulator: AgentRunAccumulator,
        aggregate_ids: tuple[str, ...],
    ) -> None:
        if not aggregate_ids:
            return
        fixtures_enabled = resolve_env(
            "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES",
            "DEEP_SEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES",
            default="",
        )
        if (fixtures_enabled or "").lower() != "true":
            return

        from tools.provided_aggregate import provided_aggregate

        for aggregate_id in aggregate_ids:
            try:
                result = await asyncio.to_thread(
                    provided_aggregate.invoke,
                    {"aggregate_id": aggregate_id},
                )
            except Exception as exc:
                accumulator.diagnostics.append(
                    f"provided_aggregate_preload_failed:{type(exc).__name__}"
                )
                continue
            if not isinstance(result, dict) or result.get("status") != "ok":
                code = (
                    result.get("error", {}).get("code")
                    if isinstance(result, dict)
                    else "invalid_preload_result"
                )
                accumulator.diagnostics.append(
                    f"provided_aggregate_preload_failed:{code}"
                )
                continue

            accumulator.evidence_entries = merge_evidence_entries(
                accumulator.evidence_entries,
                extract_evidence_entries(
                    thread_id=accumulator.thread_id,
                    query_text=accumulator.query,
                    subagent_name="provided_aggregate",
                    tool_name="provided_aggregate",
                    content=result,
                ),
            )
            processed = 0
            for index, item in enumerate(result.get("results", []), start=1):
                if not isinstance(item, dict):
                    accumulator.diagnostics.append(
                        "provided_aggregate_item_invalid"
                    )
                    continue
                evidence_id = item.get("evidence_id")
                if not isinstance(evidence_id, str) or not evidence_id:
                    accumulator.diagnostics.append(
                        "provided_aggregate_item_missing_evidence_id"
                    )
                    continue
                accumulator.verified_evidence_ids.add(evidence_id)
                _add_evidence_alias(accumulator, aggregate_id, evidence_id)
                sample_id = item.get("sample_id")
                if isinstance(sample_id, str) and sample_id:
                    for alias in (
                        sample_id,
                        f"E-{sample_id}",
                        f"sample_id:{sample_id}",
                    ):
                        _add_evidence_alias(accumulator, alias, evidence_id)
                for alias in (
                    f"src-{index}",
                    f"source-{index}",
                    f"S{index}",
                    f"S-{index:03d}",
                    f"sample-{index}",
                    f"sample-{index:02d}",
                    f"sample-{index:03d}",
                    f"sample-snapshot-{index}",
                    f"sample_id:job-{index}",
                ):
                    _add_evidence_alias(accumulator, alias, evidence_id)
                source_url = item.get("url")
                if isinstance(source_url, str) and source_url:
                    _add_evidence_alias(accumulator, source_url, evidence_id)
                processed += 1
            accumulator.diagnostics.append(
                f"provided_aggregate_prefetched:{aggregate_id}"
                if processed
                else "provided_aggregate_preload_failed:no_valid_results"
            )

    def _freeze_outcome(
        self,
        observer: AccumulatorExecutionObserver,
        outcome_box: OutcomeBox | None,
        *,
        error_message: str | None = None,
        failure_kind: str | None = None,
        cancellation_state: str | None = None,
    ) -> ExecutionOutcome:
        accumulator = observer.accumulator
        execution_id = accumulator.run_id or accumulator.thread_id
        evidence_entries = list(accumulator.evidence_entries)
        evidence_entries = _mark_declared_fixture_evidence(
            evidence_entries,
            execution_id=execution_id,
            verified_evidence_ids=accumulator.verified_evidence_ids,
        )
        outcome = accumulator.to_outcome(
            evidence_entries=evidence_entries,
            error_message=error_message,
            failure_kind=failure_kind,
            cancellation_state=cancellation_state,
        )
        if outcome_box is not None:
            outcome_box.publish(outcome)
        return outcome

    async def execute(
        self,
        query: str,
        thread_id: str,
        *,
        run_id: str | None = None,
        segment_id: str | None = None,
        outcome_box: OutcomeBox | None = None,
        profile_id: str = "generic",
        scope: Mapping[str, Any] | None = None,
    ) -> ExecutionOutcome:
        execution_id = run_id or thread_id
        bounded_scope = dict(scope or {})
        session_dir = safe_session_dir(
            self.project_root / "output",
            execution_id,
        )
        accumulator = AgentRunAccumulator(
            thread_id=thread_id,
            query=query,
            session_dir=session_dir,
            profile_id=profile_id,
            run_id=run_id,
            segment_id=segment_id,
        )
        observer = AccumulatorExecutionObserver(accumulator)
        runtime_context = ResearchRuntimeContext(
            thread_id=thread_id,
            run_id=execution_id,
            segment_id=segment_id or "",
            profile_id=profile_id,
            allowed_source_domains=(
                _allowed_source_domains(bounded_scope)
                if profile_id == _TALENT_PROFILE_ID
                else ()
            ),
            allowed_source_types=_allowed_source_types(bounded_scope),
            allowed_aggregate_ids=(
                _allowed_aggregate_ids(bounded_scope)
                if profile_id == _TALENT_PROFILE_ID
                else ()
            ),
        )
        request = HarnessRequest(
            query=query,
            thread_id=thread_id,
            run_id=execution_id,
            segment_id=segment_id or "",
            profile_id=profile_id,
            scope=bounded_scope,
            trace_metadata={
                "research_run_id": execution_id,
                "thread_id": thread_id,
                "profile_id": profile_id,
            },
        )
        thread_token = set_thread_context(thread_id)
        run_token = set_run_context(execution_id)
        segment_token = set_segment_context(segment_id)
        domains_token = set_allowed_source_domains_context(
            runtime_context.allowed_source_domains
        )
        aggregates_token = set_allowed_aggregate_ids_context(
            runtime_context.allowed_aggregate_ids
        )
        try:
            if profile_id == _TALENT_PROFILE_ID:
                await self._preload_declared_aggregate_evidence(
                    accumulator,
                    runtime_context.allowed_aggregate_ids,
                )
            await self.harness.execute(
                request,
                runtime_context=runtime_context,
                observer=observer,
            )
            return self._freeze_outcome(observer, outcome_box)
        except (ModelCallLimitExceededError, ToolCallLimitExceededError) as exc:
            observer.on_error(exc)
            return self._freeze_outcome(
                observer,
                outcome_box,
                error_message=str(exc),
                failure_kind="call_budget_exceeded",
            )
        except GraphRecursionError as exc:
            observer.on_error(exc)
            return self._freeze_outcome(
                observer,
                outcome_box,
                error_message=str(exc),
                failure_kind="recursion_limit_exceeded",
            )
        except asyncio.CancelledError as exc:
            self._freeze_outcome(
                observer,
                outcome_box,
                error_message=str(exc) or "Agent execution cancelled.",
                failure_kind="cancelled",
                cancellation_state="cancelled",
            )
            raise
        except Exception as exc:
            observer.on_error(exc)
            self._freeze_outcome(
                observer,
                outcome_box,
                error_message=str(exc),
                failure_kind="execution_error",
            )
            raise
        finally:
            reset_execution_context(
                run_token,
                thread_token=thread_token,
                segment_token=segment_token,
                allowed_source_domains_token=domains_token,
                allowed_aggregate_ids_token=aggregates_token,
            )
            self.clear_run_cache(execution_id)
