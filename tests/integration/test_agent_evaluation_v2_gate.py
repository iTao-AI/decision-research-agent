from __future__ import annotations

import asyncio
import copy
import inspect
import json
import os
from pathlib import Path

import pytest
import pytest_asyncio

from agent.harness_contracts import AgentHarness, HarnessRequest
from api import server, task_tracker
from scripts.agent_evaluation_v2_contracts import (
    CASE_IDS,
    load_dataset,
    validate_public_projection,
)
from scripts.agent_evaluation_replay import (
    CHECKPOINTS,
    REPLAY_TIMEOUT_SECONDS,
    EvaluationV2ReplayError,
    LaneProjection,
    ReplayHarness,
    ReplayLaneResult,
    build_semantic_observation_projection,
    run_persisted_lane,
)


DATASET_PATH = Path("benchmarks/agent-evaluation-v2/cases.json")
FEATURE_FLAGS = (
    "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL",
    "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION",
    "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES",
)


def _cases() -> dict[str, dict]:
    dataset = load_dataset(DATASET_PATH)
    return {case["case_id"]: case for case in dataset["cases"]}


@pytest_asyncio.fixture(scope="module")
async def replay_pairs(tmp_path_factory):
    root = tmp_path_factory.mktemp("agent-evaluation-v2-replay")
    pairs: dict[str, tuple[ReplayLaneResult, ReplayLaneResult]] = {}
    for case_id, case in _cases().items():
        current = await run_persisted_lane(
            case=case,
            lane_role="current",
            db_path=root / f"{case_id}-current.db",
            project_root=root / f"{case_id}-current",
        )
        control = await run_persisted_lane(
            case=case,
            lane_role="control_anchor",
            db_path=root / f"{case_id}-control.db",
            project_root=root / f"{case_id}-control",
        )
        pairs[case_id] = (current, control)
    return pairs


def test_replay_harness_satisfies_agent_harness_contract():
    harness = ReplayHarness(_cases()[CASE_IDS[0]])
    assert AgentHarness in type(harness).__mro__
    assert inspect.iscoroutinefunction(harness.execute)
    assert list(inspect.signature(harness.execute).parameters) == [
        "request",
        "runtime_context",
        "observer",
    ]


def test_lane_projection_contains_only_public_safe_application_and_evaluator_fields(
    replay_pairs,
):
    result = replay_pairs[CASE_IDS[0]][0]
    assert isinstance(result, ReplayLaneResult)
    assert isinstance(result.projection, LaneProjection)
    public = {
        "case_id": result.projection.case_id,
        "lane_role": result.projection.lane_role,
        "checkpoints": list(result.projection.checkpoints),
        "application_projection": result.projection.application_projection,
        "semantic_observation_projection": (
            result.projection.semantic_observation_projection
        ),
    }
    assert validate_public_projection(public) == public
    assert not hasattr(result.projection, "__dict__")
    assert "synthetic_query" not in json.dumps(public)


def test_each_current_and_control_lane_crosses_exact_application_checkpoints(
    replay_pairs,
):
    for pair in replay_pairs.values():
        for lane in pair:
            assert tuple(lane.projection.checkpoints) == CHECKPOINTS
            assert len(lane.projection.checkpoints) == 7


def test_control_mutation_occurs_only_after_persisted_projection(replay_pairs):
    for current, control_anchor in replay_pairs.values():
        assert current.validated_observation["expected"] == (
            control_anchor.validated_observation["expected"]
        )
        assert current.projection.application_projection == (
            control_anchor.projection.application_projection
        )
        assert current.projection.semantic_observation_projection == (
            control_anchor.projection.semantic_observation_projection
        )


def test_all_lane_databases_workspaces_caches_and_run_ids_are_isolated(replay_pairs):
    run_ids = []
    evidence_ids = []
    for pair in replay_pairs.values():
        for lane in pair:
            run_ids.append(lane.validated_observation["run"]["run_id"])
            evidence_ids.append(lane.validated_observation["evidence"][0]["evidence_id"])
    assert len(run_ids) == len(set(run_ids)) == 6
    assert len(evidence_ids) == len(set(evidence_ids)) == 6
    assert task_tracker.active_tasks == {}


def test_distinct_run_ids_evidence_ids_and_retrieved_at_normalize_for_healthy_anchors(
    replay_pairs,
):
    for current, control_anchor in replay_pairs.values():
        assert current.validated_observation["run"]["run_id"] != (
            control_anchor.validated_observation["run"]["run_id"]
        )
        assert current.validated_observation["evidence"][0]["evidence_id"] != (
            control_anchor.validated_observation["evidence"][0]["evidence_id"]
        )
        assert current.projection.semantic_observation_projection == (
            control_anchor.projection.semantic_observation_projection
        )


def test_evaluator_evidence_adapter_excludes_every_persistence_only_field(
    replay_pairs,
):
    expected = {
        "evidence_id",
        "source_url",
        "source_identity",
        "retrieved_at",
        "citation_status",
        "verification_status",
    }
    for pair in replay_pairs.values():
        for lane in pair:
            assert set(lane.validated_observation["evidence"][0]) == expected


def test_canonical_artifact_identity_and_metadata_drift_fail_closed(replay_pairs):
    observation = replay_pairs[CASE_IDS[0]][0].validated_observation
    changed = copy.deepcopy(observation)
    changed["result"]["body"]["artifact"]["kind"] = "changed"
    assert build_semantic_observation_projection(changed) != (
        build_semantic_observation_projection(observation)
    )


def test_source_citation_verification_policy_metrics_and_unlisted_drift_fail_closed(
    replay_pairs,
):
    observation = replay_pairs[CASE_IDS[0]][0].validated_observation
    for mutate in (
        lambda value: value["evidence"][0].update(source_identity="changed"),
        lambda value: value["evidence"][0].update(citation_status="uncited"),
        lambda value: value["evidence"][0].update(verification_status="verified"),
        lambda value: value["policy"].update(requires_evidence=False),
        lambda value: value["metrics"].update(elapsed_ms=101),
    ):
        changed = copy.deepcopy(observation)
        mutate(changed)
        assert build_semantic_observation_projection(changed) != (
            build_semantic_observation_projection(observation)
        )


def test_normalization_cannot_hide_control_mutation_or_application_projection_drift(
    replay_pairs,
):
    observation = replay_pairs[CASE_IDS[0]][0].validated_observation
    changed = copy.deepcopy(observation)
    changed["trajectory"].pop(2)
    assert build_semantic_observation_projection(changed) != (
        build_semantic_observation_projection(observation)
    )
    current, control = replay_pairs[CASE_IDS[0]]
    drifted = copy.deepcopy(control.projection.application_projection)
    drifted["terminal"]["delivery_status"] = "failed"
    assert drifted != current.projection.application_projection


@pytest.mark.asyncio
async def test_server_adapter_and_resources_restore_in_finally_on_success_and_failure(
    tmp_path,
    monkeypatch,
):
    original_adapter = server.run_deep_agent
    original_flags = {name: os.environ.get(name) for name in FEATURE_FLAGS}
    case = _cases()[CASE_IDS[0]]
    await run_persisted_lane(
        case=case,
        lane_role="current",
        db_path=tmp_path / "success.db",
        project_root=tmp_path / "success",
    )
    assert server.run_deep_agent is original_adapter
    assert {name: os.environ.get(name) for name in FEATURE_FLAGS} == original_flags

    async def fail(self, request, *, runtime_context, observer):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(ReplayHarness, "execute", fail)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        await run_persisted_lane(
            case=case,
            lane_role="current",
            db_path=tmp_path / "failure.db",
            project_root=tmp_path / "failure",
        )
    assert server.run_deep_agent is original_adapter
    assert {name: os.environ.get(name) for name in FEATURE_FLAGS} == original_flags
    assert task_tracker.active_tasks == {}


@pytest.mark.asyncio
async def test_replay_guard_rejects_concurrent_entry_without_waiting(
    tmp_path,
    monkeypatch,
):
    entered = asyncio.Event()
    release = asyncio.Event()
    original = ReplayHarness.execute

    async def hold(self, request, *, runtime_context, observer):
        entered.set()
        await release.wait()
        return await original(
            self,
            request,
            runtime_context=runtime_context,
            observer=observer,
        )

    monkeypatch.setattr(ReplayHarness, "execute", hold)
    case = _cases()[CASE_IDS[0]]
    first = asyncio.create_task(
        run_persisted_lane(
            case=case,
            lane_role="current",
            db_path=tmp_path / "first.db",
            project_root=tmp_path / "first",
        )
    )
    await entered.wait()
    with pytest.raises(EvaluationV2ReplayError, match="evaluation_v2_replay_invalid"):
        await run_persisted_lane(
            case=case,
            lane_role="control_anchor",
            db_path=tmp_path / "second.db",
            project_root=tmp_path / "second",
        )
    release.set()
    await first


@pytest.mark.asyncio
async def test_active_task_or_dispatch_worker_rejects_replay(tmp_path):
    case = _cases()[CASE_IDS[0]]
    task_tracker.active_tasks["foreign"] = (object(), 1, 0.0)
    try:
        with pytest.raises(EvaluationV2ReplayError):
            await run_persisted_lane(
                case=case,
                lane_role="current",
                db_path=tmp_path / "active.db",
                project_root=tmp_path / "active",
            )
    finally:
        task_tracker.active_tasks.pop("foreign", None)


@pytest.mark.asyncio
async def test_timeout_cancellation_and_exception_restore_patch_flags_cache_and_task_registry(
    tmp_path,
    monkeypatch,
):
    case = _cases()[CASE_IDS[0]]
    original_adapter = server.run_deep_agent
    original_flags = {name: os.environ.get(name) for name in FEATURE_FLAGS}

    async def cancelled(self, request, *, runtime_context, observer):
        raise asyncio.CancelledError

    monkeypatch.setattr(ReplayHarness, "execute", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await run_persisted_lane(
            case=case,
            lane_role="current",
            db_path=tmp_path / "cancel.db",
            project_root=tmp_path / "cancel",
        )
    assert server.run_deep_agent is original_adapter
    assert {name: os.environ.get(name) for name in FEATURE_FLAGS} == original_flags
    assert task_tracker.active_tasks == {}


def test_successful_none_result_is_not_misclassified_as_timeout(replay_pairs):
    assert REPLAY_TIMEOUT_SECONDS == 30
    for pair in replay_pairs.values():
        for lane in pair:
            assert lane.validated_observation["run"]["execution_status"] == "completed"


@pytest.mark.asyncio
async def test_tracker_timeout_origin_fails_before_run_reread(tmp_path, monkeypatch):
    import scripts.agent_evaluation_replay as replay

    def timeout_task(coroutine, task_id, **kwargs):
        coroutine.close()

        async def finish():
            kwargs["termination_origin"].claim_timeout()
            return None

        return asyncio.create_task(finish())

    monkeypatch.setattr(replay, "create_tracked_task", timeout_task)
    monkeypatch.setattr(
        replay,
        "get_run",
        lambda **kwargs: pytest.fail("get_run must not run after timeout"),
    )
    with pytest.raises(EvaluationV2ReplayError):
        await run_persisted_lane(
            case=_cases()[CASE_IDS[0]],
            lane_role="current",
            db_path=tmp_path / "timeout.db",
            project_root=tmp_path / "timeout",
        )


@pytest.mark.asyncio
async def test_direct_final_projection_fixture_is_rejected(tmp_path):
    with pytest.raises(TypeError):
        await run_persisted_lane(
            case=_cases()[CASE_IDS[0]],
            lane_role="current",
            db_path=tmp_path / "direct.db",
            project_root=tmp_path / "direct",
            final_projection={"execution_status": "completed"},
        )
