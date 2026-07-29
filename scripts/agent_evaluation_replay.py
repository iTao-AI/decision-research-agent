"""Provider-free persisted replay lanes for sensitivity gate v2."""
from __future__ import annotations

import asyncio
import copy
import importlib
import json
import os
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import sys
from threading import Lock
from types import ModuleType
from typing import Any, Literal, Mapping, Sequence
from unittest.mock import patch

from langchain_core.messages import AIMessage, ToolMessage

from agent.harness_contracts import (
    AgentHarness,
    ExecutionObserver,
    HarnessRequest,
)
from agent.run_result import ExecutionOutcome, OutcomeBox
from agent.runtime_context import ResearchRuntimeContext
from api import task_tracker
from api.research_execution_service import ResearchExecutionService
from api.run_dispatch_repository import claim_run_dispatch
from api.run_execution_models import RunExecutionOwnerBox, new_boot_id
from api.run_execution_repository import activate_run_execution_boot
from api.run_repository import create_run, get_run
from api.run_result_service import resolve_run_result
from api.task_tracker import (
    FinalizationCheckpoint,
    TerminationOrigin,
    create_tracked_task,
    close_tracked_task_admission,
    drain_tracked_tasks,
    open_tracked_task_admission,
)
from scripts.agent_evaluation_context import (
    compare_context_reliability_outcomes,
    project_context_reliability_outcome,
)
from scripts.agent_evaluation_contracts import validate_observation
from scripts.agent_evaluation_v2_contracts import (
    CHECKPOINT_NAMES,
    SEMANTIC_COMPARISON_SCHEMA_VERSION,
    validate_dataset,
    validate_public_projection,
)
from tools import tavily_tools


def _load_server_without_provider_initialization():
    existing = sys.modules.get("api.server")
    if existing is not None:
        return existing
    previous_main = sys.modules.get("agent.main_agent")
    placeholder = ModuleType("agent.main_agent")

    async def unavailable_run_deep_agent(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise RuntimeError("evaluation_v2_replay_adapter_not_installed")

    placeholder.run_deep_agent = unavailable_run_deep_agent
    sys.modules["agent.main_agent"] = placeholder
    try:
        return importlib.import_module("api.server")
    finally:
        if previous_main is None:
            sys.modules.pop("agent.main_agent", None)
        else:
            sys.modules["agent.main_agent"] = previous_main


server = _load_server_without_provider_initialization()
_RunStage = server._RunStage
_run_dispatched_with_persistence = server._run_dispatched_with_persistence


REPLAY_TIMEOUT_SECONDS = 30
_FEATURE_FLAGS = (
    "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL",
    "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION",
    "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES",
)
_WORKER_ID = "dispatch_worker_0000000000000000000000000000e2a1"
_PAIR_RUN_TOKEN = "run_evaluation_v2_pair"
_PAIR_EVIDENCE_TOKEN = "ev_run_evaluation_v2_pair_0001"
_PAIR_RETRIEVED_AT = "2000-01-01T00:00:00+00:00"
_REPLAY_GUARD = Lock()


class EvaluationV2ReplayError(ValueError):
    """Stable replay error without runtime-private details."""

    def __init__(self) -> None:
        super().__init__("evaluation_v2_replay_invalid")
        self.code = "evaluation_v2_replay_invalid"


def _fail() -> None:
    raise EvaluationV2ReplayError()


class _LifecycleCheckpointRecorder:
    def __init__(self) -> None:
        self._records: list[tuple[str, bool]] = []

    def observe(self, checkpoint: str, passed: bool) -> None:
        next_index = len(self._records)
        if (
            next_index >= len(CHECKPOINT_NAMES)
            or checkpoint != CHECKPOINT_NAMES[next_index]
            or passed is not True
        ):
            _fail()
        self._records.append((checkpoint, True))

    def finish(self) -> tuple[tuple[str, bool], ...]:
        if [name for name, _ in self._records] != list(CHECKPOINT_NAMES):
            _fail()
        return tuple(self._records)


@dataclass(frozen=True, slots=True)
class LaneProjection:
    case_id: str
    lane_role: Literal["current", "control_anchor"]
    checkpoints: Sequence[tuple[str, bool]]
    application_projection: Mapping[str, Any]
    semantic_observation_projection: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ReplayLaneResult:
    validated_observation: dict[str, Any]
    projection: LaneProjection


class ReplayHarness(AgentHarness):
    """Emit one reviewed case through the real application observer."""

    def __init__(self, case: Mapping[str, Any]) -> None:
        dataset = validate_dataset(
            {
                "schema_version": "dra.agent-evaluation-v2-cases.v1",
                "cases": _ordered_case_set(case),
            }
        )
        self.case = next(
            item for item in dataset["cases"] if item["case_id"] == case["case_id"]
        )
        self.trajectory: list[dict[str, Any]] = []

    async def execute(
        self,
        request: HarnessRequest,
        *,
        runtime_context: ResearchRuntimeContext,
        observer: ExecutionObserver,
    ) -> ExecutionOutcome:
        if (
            request.query != self.case["synthetic_query"]
            or request.run_id != runtime_context.run_id
            or request.profile_id != "generic"
        ):
            _fail()
        self.trajectory = []
        for event in self.case["trajectory"]:
            recorded = {"event_id": event["event_id"], "kind": event["kind"]}
            recorded["run_id"] = request.run_id
            if event["kind"] == "assistant":
                observer.on_stream_chunk(
                    {"agent": {"messages": [AIMessage(content="")]}}
                )
            elif event["kind"] == "tool_call":
                recorded["call_id"] = event["call_id"]
                recorded["tool_name"] = event["tool_name"]
                observer.on_stream_chunk(
                    {
                        "agent": {
                            "messages": [
                                AIMessage(
                                    content="",
                                    tool_calls=[
                                        {
                                            "name": event["tool_name"],
                                            "args": {"query": self.case["synthetic_query"]},
                                            "id": event["call_id"],
                                            "type": "tool_call",
                                        }
                                    ],
                                )
                            ]
                        }
                    }
                )
            elif event["kind"] == "tool_result":
                recorded["call_id"] = event["call_id"]
                recorded["trust"] = event["trust"]
                tool_name = _tool_name_for_call(self.case, event["call_id"])
                content = (
                    json.dumps(
                        {
                            "results": [
                                {
                                    "url": self.case["source_url"],
                                    "content": self.case["synthetic_source_text"],
                                }
                            ]
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    if tool_name == "internet_search"
                    else "Synthetic write result."
                )
                observer.on_stream_chunk(
                    {
                        "network_search" if tool_name == "internet_search" else "agent": {
                            "messages": [
                                ToolMessage(
                                    content=content,
                                    name=tool_name,
                                    tool_call_id=event["call_id"],
                                )
                            ]
                        }
                    }
                )
            elif event["kind"] == "terminal":
                observer.on_stream_chunk(
                    {"agent": {"messages": [AIMessage(content="")]}}
                )
            else:
                _fail()
            self.trajectory.append(recorded)
        report = (
            self.case["synthetic_report_markdown"].rstrip()
            + "\n\nSource: "
            + self.case["source_url"]
            + "\n"
        )
        observer.on_stream_chunk(
            {
                "agent": {
                    "files": {
                        "/workspace/research-report.md": {
                            "content": report,
                        }
                    }
                }
            }
        )
        return observer.snapshot_outcome()


def _ordered_case_set(selected: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Rebuild the exact dataset order while replacing one selected case."""
    dataset_path = Path(__file__).resolve().parents[1] / (
        "benchmarks/agent-evaluation-v2/cases.json"
    )
    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _fail()
    cases = []
    for case in payload.get("cases", []):
        cases.append(
            copy.deepcopy(selected)
            if case.get("case_id") == selected.get("case_id")
            else case
        )
    return cases


def _tool_name_for_call(case: Mapping[str, Any], call_id: str) -> str:
    names = [
        event["tool_name"]
        for event in case["trajectory"]
        if event["kind"] == "tool_call" and event["call_id"] == call_id
    ]
    if len(names) != 1:
        _fail()
    return names[0]


def _evidence_projection(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = run.get("evidence")
    if not isinstance(rows, list) or len(rows) != 1:
        _fail()
    allowed = (
        "evidence_id",
        "source_url",
        "source_identity",
        "retrieved_at",
        "citation_status",
        "verification_status",
    )
    row = rows[0]
    if not isinstance(row, Mapping) or any(key not in row for key in allowed):
        _fail()
    return [{key: row[key] for key in allowed}]


def _result_payload(resolution: Any) -> dict[str, Any]:
    try:
        payload = asdict(resolution)
    except TypeError:
        _fail()
    return {"http_status": 200, "body": payload}


def _build_observation(
    *,
    case: Mapping[str, Any],
    run: Mapping[str, Any],
    resolution: Any,
    trajectory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    evidence = _evidence_projection(run)
    evidence_id = evidence[0]["evidence_id"]
    observation = {
        "case_id": case["case_id"],
        "source": "deterministic",
        "run": {
            "run_id": run["run_id"],
            "execution_status": run["execution_status"],
            "review_status": run["review_status"],
            "delivery_status": run["delivery_status"],
            "state_version": run["state_version"],
        },
        "evidence": evidence,
        "result": _result_payload(resolution),
        "trajectory_status": "complete",
        "trajectory": [dict(event) for event in trajectory],
        "evidence_ref_status": "observed",
        "typed_evidence_refs": [evidence_id],
        "trust_signal_status": "observed",
        "trust_signals": copy.deepcopy(case["trust_signals"]),
        "policy": copy.deepcopy(case["policy"]),
        "metrics": {
            **copy.deepcopy(case["metrics"]),
            "token_usage": {
                **copy.deepcopy(case["metrics"]["token_usage"]),
                "cost_estimate": {
                    "amount": "0.00000000",
                    "currency": "USD",
                    "pricing_basis": "deterministic-replay-v2",
                    "estimate": True,
                },
            },
        },
        "expected": copy.deepcopy(case["expected"]),
    }
    return validate_observation(observation)


def build_semantic_observation_projection(
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    canonical = validate_observation(copy.deepcopy(dict(observation)))
    evidence = canonical["evidence"]
    if len(evidence) != 1:
        _fail()
    real_run_id = canonical["run"]["run_id"]
    real_evidence_id = evidence[0]["evidence_id"]
    if not real_evidence_id.startswith(f"ev_{real_run_id}_"):
        _fail()
    try:
        retrieved = datetime.fromisoformat(evidence[0]["retrieved_at"])
    except (TypeError, ValueError):
        _fail()
    if retrieved.tzinfo is None:
        _fail()

    projected = copy.deepcopy(canonical)
    projected["run"]["run_id"] = _PAIR_RUN_TOKEN
    projected["result"]["body"]["run_id"] = _PAIR_RUN_TOKEN
    for event in projected["trajectory"]:
        event["run_id"] = _PAIR_RUN_TOKEN
    projected["evidence"][0]["evidence_id"] = _PAIR_EVIDENCE_TOKEN
    projected["evidence"][0]["retrieved_at"] = _PAIR_RETRIEVED_AT
    projected["typed_evidence_refs"] = [
        _PAIR_EVIDENCE_TOKEN if ref == real_evidence_id else ref
        for ref in projected["typed_evidence_refs"]
    ]
    artifact = projected["result"]["body"]["artifact"]
    projected["result"]["body"]["artifact"] = {
        key: artifact[key]
        for key in ("artifact_id", "kind", "media_type", "content_hash")
    }
    result = {
        "schema_version": SEMANTIC_COMPARISON_SCHEMA_VERSION,
        "observation": projected,
    }
    validate_public_projection(result)
    return result


def _worker_live() -> bool:
    worker = getattr(server.app.state, "run_dispatch_worker_task", None)
    return worker is not None and not worker.done()


async def run_persisted_lane(
    *,
    case: Mapping[str, Any],
    lane_role: Literal["current", "control_anchor"],
    db_path: Path,
    project_root: Path,
) -> ReplayLaneResult:
    if lane_role not in {"current", "control_anchor"}:
        _fail()
    if not _REPLAY_GUARD.acquire(blocking=False):
        _fail()
    try:
        if task_tracker.active_tasks or _worker_live():
            _fail()
        if db_path.exists() or project_root.exists():
            _fail()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        project_root.mkdir(parents=True, exist_ok=False)

        checkpoints = _LifecycleCheckpointRecorder()
        harness = ReplayHarness(case)
        cache_key = f"agent-evaluation-v2:{case['case_id']}:{lane_role}"
        with tavily_tools._search_cache_lock:
            cache_existed = cache_key in tavily_tools._search_cache
            previous_cache = tavily_tools._search_cache.get(cache_key)
            tavily_tools._search_cache[cache_key] = {"owned": True}

        try:
            service = ResearchExecutionService(
                harness=harness,
                project_root=project_root,
            )

            async def replay_adapter(
                query: str,
                thread_id: str,
                **kwargs: Any,
            ) -> ExecutionOutcome:
                outcome = await service.execute(
                    query,
                    thread_id,
                    run_id=kwargs["run_id"],
                    segment_id=kwargs["segment_id"],
                    outcome_box=kwargs["outcome_box"],
                    profile_id=kwargs["profile_id"],
                    scope=kwargs["scope"],
                )
                checkpoints.observe(
                    "research_execution_service",
                    isinstance(outcome, ExecutionOutcome),
                )
                return outcome

            with ExitStack() as stack:
                stack.enter_context(patch.object(server, "run_deep_agent", replay_adapter))
                stack.enter_context(
                    patch.dict(
                        os.environ,
                        {name: "false" for name in _FEATURE_FLAGS},
                        clear=False,
                    )
                )
                identity = create_run(
                    thread_id=f"thread_{case['case_id']}_{lane_role}",
                    query=case["synthetic_query"],
                    db_path=str(db_path),
                )
                checkpoints.observe(
                    "create_run",
                    isinstance(identity.get("run_id"), str)
                    and isinstance(identity.get("segment_id"), str),
                )
                boot_id = new_boot_id()
                activate_run_execution_boot(
                    db_path=str(db_path),
                    boot_id=boot_id,
                )
                claim = claim_run_dispatch(
                    db_path=str(db_path),
                    worker_id=_WORKER_ID,
                    boot_id=boot_id,
                    lease_seconds=REPLAY_TIMEOUT_SECONDS,
                    run_id=identity["run_id"],
                )
                if claim is None:
                    _fail()
                checkpoints.observe(
                    "claim_run_dispatch",
                    claim.run_id == identity["run_id"]
                    and claim.segment_id == identity["segment_id"],
                )
                outcome_box = OutcomeBox()
                stage = _RunStage()
                termination_origin = TerminationOrigin()
                finalization_checkpoint = FinalizationCheckpoint()
                owner_box = RunExecutionOwnerBox()
                close_tracked_task_admission()
                await drain_tracked_tasks()
                open_tracked_task_admission()
                tracked = create_tracked_task(
                    _run_dispatched_with_persistence(
                        claim,
                        db_path=str(db_path),
                        outcome_box=outcome_box,
                        stage=stage,
                        termination_origin=termination_origin,
                        finalization_checkpoint=finalization_checkpoint,
                        owner_box=owner_box,
                    ),
                    task_id=identity["run_id"],
                    timeout_seconds=REPLAY_TIMEOUT_SECONDS,
                    termination_origin=termination_origin,
                    finalization_checkpoint=finalization_checkpoint,
                )
                checkpoints.observe(
                    "create_tracked_task_dispatch_fence",
                    identity["run_id"] in task_tracker.active_tasks
                    and task_tracker.active_tasks[identity["run_id"]][0] is tracked,
                )
                try:
                    await tracked
                    await asyncio.sleep(0)
                finally:
                    close_tracked_task_admission()
                    await drain_tracked_tasks()
                if termination_origin.value == "timeout":
                    _fail()
                if termination_origin.value != "unset":
                    _fail()
                checkpoints.observe(
                    "finalize_run_transaction",
                    stage.value == "finalization",
                )
                run = get_run(run_id=identity["run_id"], db_path=str(db_path))
                if run is None:
                    _fail()
                checkpoints.observe(
                    "get_run",
                    run.get("run_id") == identity["run_id"],
                )
                resolution = resolve_run_result(
                    run_id=identity["run_id"],
                    db_path=str(db_path),
                )
                checkpoints.observe(
                    "resolve_run_result",
                    getattr(resolution, "run_id", None) == identity["run_id"],
                )
                application_projection = project_context_reliability_outcome(
                    run=run,
                    resolution=resolution,
                )
                observation = _build_observation(
                    case=harness.case,
                    run=run,
                    resolution=resolution,
                    trajectory=harness.trajectory,
                )
                semantic_projection = build_semantic_observation_projection(
                    observation
                )
        finally:
            with tavily_tools._search_cache_lock:
                if cache_existed:
                    tavily_tools._search_cache[cache_key] = previous_cache
                else:
                    tavily_tools._search_cache.pop(cache_key, None)

        if task_tracker.active_tasks:
            _fail()
        projection = LaneProjection(
            case_id=case["case_id"],
            lane_role=lane_role,
            checkpoints=checkpoints.finish(),
            application_projection=application_projection,
            semantic_observation_projection=semantic_projection,
        )
        public = {
            "case_id": projection.case_id,
            "lane_role": projection.lane_role,
            "checkpoints": list(projection.checkpoints),
            "application_projection": projection.application_projection,
            "semantic_observation_projection": (
                projection.semantic_observation_projection
            ),
        }
        validate_public_projection(public)
        return ReplayLaneResult(
            validated_observation=observation,
            projection=projection,
        )
    finally:
        _REPLAY_GUARD.release()


def assert_application_equivalent(
    current: ReplayLaneResult,
    control_anchor: ReplayLaneResult,
) -> None:
    if compare_context_reliability_outcomes(
        current.projection.application_projection,
        control_anchor.projection.application_projection,
    ):
        _fail()
