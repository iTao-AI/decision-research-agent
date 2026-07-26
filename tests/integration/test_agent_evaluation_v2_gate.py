from __future__ import annotations

import asyncio
import copy
from dataclasses import replace
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys

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
from scripts.agent_evaluation_v2_gate import (
    BASELINE_JSON_PATH,
    BASELINE_MARKDOWN_PATH,
    EvaluationV2GateError,
    apply_control_mutation,
    build_semantic_comparison_projection,
    build_report,
    compare_artifacts,
    evaluate_negative_control_sensitivity,
    render_markdown,
    serialize_report,
    write_artifacts_atomically,
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


def test_comparison_projection_uses_the_approved_semantic_allowlist(replay_pairs):
    observation = replay_pairs[CASE_IDS[0]][0].validated_observation
    assert build_semantic_comparison_projection(observation) == (
        build_semantic_observation_projection(observation)
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


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_declared_control_triggers_only_responsible_evaluator(
    case_id,
    replay_pairs,
):
    current, control_anchor = replay_pairs[case_id]
    pair = evaluate_negative_control_sensitivity(
        case=_cases()[case_id],
        current=current,
        control_anchor=control_anchor,
    )
    assert pair["negative_control_sensitivity"] is True
    responsible = _cases()[case_id]["responsible_evaluator"]
    expected = _cases()[case_id]["expected_control_finding"]
    by_id = {
        item["evaluator_id"]: item
        for item in pair["synthetic_control_evaluators"]
    }
    assert by_id[responsible] == {
        "evaluator_id": responsible,
        "status": "regression",
        "finding_codes": [expected],
    }


def test_both_unmutated_anchors_pass_all_six_evaluators(replay_pairs):
    for case_id, (current, control_anchor) in replay_pairs.items():
        pair = evaluate_negative_control_sensitivity(
            case=_cases()[case_id],
            current=current,
            control_anchor=control_anchor,
        )
        for field in ("current_anchor_evaluators", "control_anchor_evaluators"):
            assert len(pair[field]) == 6
            assert {item["status"] for item in pair[field]} == {"pass"}


def test_current_and_control_expected_bytes_are_equal(replay_pairs):
    for case_id, (current, control_anchor) in replay_pairs.items():
        synthetic = apply_control_mutation(
            _cases()[case_id],
            control_anchor.validated_observation,
        )
        expected = json.dumps(
            current.validated_observation["expected"],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        assert json.dumps(
            control_anchor.validated_observation["expected"],
            sort_keys=True,
            separators=(",", ":"),
        ).encode() == expected
        assert json.dumps(
            synthetic["expected"], sort_keys=True, separators=(",", ":")
        ).encode() == expected


def test_target_current_is_pass_and_control_is_regression(replay_pairs):
    for case_id, (current, control_anchor) in replay_pairs.items():
        pair = evaluate_negative_control_sensitivity(
            case=_cases()[case_id],
            current=current,
            control_anchor=control_anchor,
        )
        responsible = _cases()[case_id]["responsible_evaluator"]
        for field in ("current_anchor_evaluators", "control_anchor_evaluators"):
            result = next(
                item for item in pair[field] if item["evaluator_id"] == responsible
            )
            assert result == {
                "evaluator_id": responsible,
                "status": "pass",
                "finding_codes": [],
            }
        result = next(
            item
            for item in pair["synthetic_control_evaluators"]
            if item["evaluator_id"] == responsible
        )
        assert result["status"] == "regression"


def test_trajectory_mutator_removes_only_named_non_signal_result(replay_pairs):
    case = _cases()[CASE_IDS[0]]
    anchor = replay_pairs[CASE_IDS[0]][1].validated_observation
    mutated = apply_control_mutation(case, anchor)
    removed = [event for event in anchor["trajectory"] if event not in mutated["trajectory"]]
    assert removed == [
        {
            "event_id": "result-search",
            "kind": "tool_result",
            "run_id": anchor["run"]["run_id"],
            "call_id": "search-1",
            "trust": "untrusted",
        }
    ]
    assert len(mutated["trajectory"]) == len(anchor["trajectory"]) - 1


def test_evidence_mutator_replaces_only_one_real_current_run_reference(replay_pairs):
    case = _cases()[CASE_IDS[1]]
    anchor = replay_pairs[CASE_IDS[1]][1].validated_observation
    mutated = apply_control_mutation(case, anchor)
    assert mutated["typed_evidence_refs"] == ["ev_run_evaluation_v2_unresolved_0001"]
    unchanged = copy.deepcopy(mutated)
    unchanged["typed_evidence_refs"] = anchor["typed_evidence_refs"]
    assert unchanged == anchor


def test_safety_mutator_moves_only_one_adjacent_pair_and_preserves_other_relative_order(
    replay_pairs,
):
    case = _cases()[CASE_IDS[2]]
    anchor = replay_pairs[CASE_IDS[2]][1].validated_observation
    mutated = apply_control_mutation(case, anchor)
    ids = [event["event_id"] for event in mutated["trajectory"]]
    assert ids == [
        "assistant-1",
        "call-search",
        "result-search",
        "call-write",
        "result-write",
        "terminal-1",
    ]
    assert sorted(ids) == sorted(event["event_id"] for event in anchor["trajectory"])


def test_false_green_fails_the_whole_gate(replay_pairs, monkeypatch):
    import scripts.agent_evaluation_v2_gate as gate

    real = gate.evaluate_observation

    def false_green(observation):
        result = real(observation)
        if observation["case_id"] == CASE_IDS[0] and len(observation["trajectory"]) == 3:
            result["status"] = "pass"
            result["expectation_match"] = True
            result["blocking_finding_codes"] = []
            result["findings"] = []
            for item in result["evaluators"]:
                item["status"] = "pass"
                item["finding_codes"] = []
        return result

    monkeypatch.setattr(gate, "evaluate_observation", false_green)
    with pytest.raises(EvaluationV2GateError, match="evaluation_v2_control_invalid"):
        evaluate_negative_control_sensitivity(
            case=_cases()[CASE_IDS[0]],
            current=replay_pairs[CASE_IDS[0]][0],
            control_anchor=replay_pairs[CASE_IDS[0]][1],
        )


def test_missing_or_multidimensional_mutation_fails_closed(replay_pairs):
    case = copy.deepcopy(_cases()[CASE_IDS[0]])
    case["mutation_id"] = "unknown.mutation"
    with pytest.raises(EvaluationV2GateError):
        apply_control_mutation(
            case,
            replay_pairs[CASE_IDS[0]][1].validated_observation,
        )
    case = _cases()[CASE_IDS[0]]
    drifted = copy.deepcopy(replay_pairs[CASE_IDS[0]][1].validated_observation)
    drifted["metrics"]["elapsed_ms"] += 1
    with pytest.raises(EvaluationV2GateError):
        evaluate_negative_control_sensitivity(
            case=case,
            current=replay_pairs[CASE_IDS[0]][0],
            control_anchor=replace(
                replay_pairs[CASE_IDS[0]][1],
                validated_observation=drifted,
            ),
        )


def test_non_responsible_evaluator_drift_fails_closed(replay_pairs, monkeypatch):
    import scripts.agent_evaluation_v2_gate as gate

    real = gate.evaluate_observation

    def drift(observation):
        result = real(observation)
        if len(observation["trajectory"]) == 3:
            result["evaluators"][0]["status"] = "regression"
            result["evaluators"][0]["finding_codes"] = ["result.contract_invalid"]
        return result

    monkeypatch.setattr(gate, "evaluate_observation", drift)
    with pytest.raises(EvaluationV2GateError):
        evaluate_negative_control_sensitivity(
            case=_cases()[CASE_IDS[0]],
            current=replay_pairs[CASE_IDS[0]][0],
            control_anchor=replay_pairs[CASE_IDS[0]][1],
        )


def test_persisted_application_projection_drift_fails_closed(replay_pairs):
    current, control = replay_pairs[CASE_IDS[0]]
    projection = copy.deepcopy(control.projection.application_projection)
    projection["terminal"]["delivery_status"] = "failed"
    drifted = replace(
        control,
        projection=replace(control.projection, application_projection=projection),
    )
    with pytest.raises(EvaluationV2GateError):
        evaluate_negative_control_sensitivity(
            case=_cases()[CASE_IDS[0]],
            current=current,
            control_anchor=drifted,
        )


@pytest.mark.asyncio
async def test_two_fresh_builds_are_byte_identical(tmp_path):
    first = await build_report(work_root=tmp_path / "first")
    second = await build_report(work_root=tmp_path / "second")
    assert serialize_report(first) == serialize_report(second)
    assert render_markdown(first) == render_markdown(second)


@pytest.mark.asyncio
async def test_markdown_is_rendered_only_from_validated_json(tmp_path):
    report = await build_report(work_root=tmp_path / "report")
    markdown = render_markdown(report)
    broken = copy.deepcopy(report)
    broken["unexpected"] = True
    with pytest.raises(EvaluationV2GateError):
        render_markdown(broken)
    assert markdown.startswith("# Agent Evaluation Sensitivity Gate v2\n")


@pytest.mark.asyncio
async def test_markdown_leads_with_healthy_anchor_boundary_and_exact_pair_columns(
    tmp_path,
):
    markdown = render_markdown(await build_report(work_root=tmp_path / "report"))
    lines = markdown.splitlines()
    assert lines[2] == (
        "All six persisted lifecycle anchors are healthy and equivalent; "
        "regressions below exist only in post-traversal synthetic evaluator inputs."
    )
    assert (
        "| healthy anchor | post-traversal synthetic control | "
        "application projection equal | responsible evaluator | "
        "expected control finding |"
    ) in markdown


@pytest.mark.asyncio
async def test_fixture_body_markers_never_reach_projection_json_markdown_stdout_stderr_or_logs(
    tmp_path,
):
    report = await build_report(work_root=tmp_path / "report")
    surfaces = serialize_report(report) + render_markdown(report).encode()
    for case in _cases().values():
        for field in (
            "synthetic_query",
            "synthetic_source_text",
            "synthetic_report_markdown",
        ):
            assert case[field].encode() not in surfaces


@pytest.mark.asyncio
async def test_build_refuses_committed_aliases_and_cleans_partial_outputs(
    tmp_path,
):
    report = await build_report(work_root=tmp_path / "report")
    markdown = render_markdown(report)
    with pytest.raises(EvaluationV2GateError):
        write_artifacts_atomically(
            report,
            markdown,
            json_output=BASELINE_JSON_PATH,
            markdown_output=tmp_path / "candidate.md",
        )
    alias = tmp_path / "alias"
    with pytest.raises(EvaluationV2GateError):
        write_artifacts_atomically(
            report,
            markdown,
            json_output=alias,
            markdown_output=alias,
        )
    assert not alias.exists()


@pytest.mark.asyncio
async def test_check_emits_exact_comparison_envelope_and_safe_errors(tmp_path):
    report = await build_report(work_root=tmp_path / "report")
    comparison = compare_artifacts(
        report,
        render_markdown(report),
        serialize_report(report),
        render_markdown(report).encode(),
    )
    assert list(comparison) == [
        "schema_version",
        "match",
        "gate_passed",
        "changed_case_ids",
        "false_green_case_ids",
        "observed_declared_control_finding_codes",
        "unexpected_blocking_finding_codes",
    ]
    assert comparison["match"] is True


@pytest.mark.asyncio
async def test_passing_comparison_separates_declared_control_findings_from_unexpected_blockers(
    tmp_path,
):
    report = await build_report(work_root=tmp_path / "report")
    comparison = compare_artifacts(
        report,
        render_markdown(report),
        serialize_report(report),
        render_markdown(report).encode(),
    )
    assert comparison["observed_declared_control_finding_codes"] == [
        _cases()[case_id]["expected_control_finding"] for case_id in CASE_IDS
    ]
    assert comparison["unexpected_blocking_finding_codes"] == []


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/agent_evaluation_v2_gate.py", *args],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"},
    )


def test_check_stdout_stderr_and_exit_matrix_is_exact_for_pass_drift_and_false_green():
    passed = _run_cli("check")
    assert passed.returncode == 0
    assert passed.stderr == ""
    payload = json.loads(passed.stdout)
    assert payload["match"] is True
    assert passed.stdout.endswith("\n") and not passed.stdout.endswith("\n\n")


def test_check_rejects_byte_matching_baseline_when_gate_passed_is_false():
    report = {
        "schema_version": "dra.agent-evaluation-v2-report.v1",
        "dataset": {
            "schema_version": "dra.agent-evaluation-v2-cases.v1",
            "sha256": "0" * 64,
            "case_ids": list(CASE_IDS),
        },
        "pairs": [],
        "summary": {
            "pair_count": 0,
            "healthy_anchor_count": 0,
            "sensitive_pair_count": 0,
            "gate_passed": False,
        },
        "limits": ["Synthetic evaluator-input control proof only."],
        "non_claims": ["No runtime incident or provider-quality claim."],
    }
    markdown = render_markdown(report)
    comparison = compare_artifacts(
        report, markdown, serialize_report(report), markdown.encode()
    )
    assert comparison["match"] is True
    assert comparison["gate_passed"] is False


def test_build_exit_zero_means_valid_artifacts_and_reports_gate_passed_boolean(
    tmp_path,
):
    result = _run_cli(
        "build",
        "--json-output",
        str(tmp_path / "candidate.json"),
        "--markdown-output",
        str(tmp_path / "candidate.md"),
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout) == {"status": "built", "gate_passed": True}


def test_root_and_subcommand_help_parse_failures_and_terminal_newlines_are_stable():
    for args in (("--help",), ("build", "--help")):
        result = _run_cli(*args)
        assert result.returncode == 0
        assert result.stderr == ""
        assert result.stdout.endswith("\n")
    invalid = _run_cli("unknown")
    assert invalid.returncode == 1
    assert invalid.stdout == ""
    assert json.loads(invalid.stderr) == {
        "status": "invalid",
        "code": "evaluation_v2_cli_invalid",
    }


def test_committed_json_and_markdown_match_fresh_build():
    result = _run_cli("check")
    assert result.returncode == 0, (result.stdout, result.stderr)
