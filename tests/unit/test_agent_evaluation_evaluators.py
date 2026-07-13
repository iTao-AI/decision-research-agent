from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scripts.agent_evaluation_contracts import CASE_IDS, load_manifest, validate_observation
from scripts.agent_evaluation_evaluators import (
    EVALUATOR_REGISTRY,
    build_evaluation_context,
    evaluate_observation,
)
from scripts.downstream_consumer_contract import build_fixture_bundle


_MANIFEST = load_manifest(Path("benchmarks/agent-evaluation-v1/scenarios.json"))
_SOURCES = {case["case_id"]: case for case in build_fixture_bundle()["cases"]}


def _observation(case_id: str) -> dict:
    case = copy.deepcopy(next(case for case in _MANIFEST["cases"] if case["case_id"] == case_id))
    source = copy.deepcopy(_SOURCES[case.pop("source_case_id")])
    evidence_mode = case.pop("evidence_mode")
    current_run_id = source["run"]["run_id"]
    trajectory = []
    for event in case.pop("trajectory"):
        event["run_id"] = (
            current_run_id if event.pop("run_ref") == "current" else "run_evaluation_foreign"
        )
        trajectory.append(event)
    observation = {
        "case_id": case.pop("case_id"),
        "source": "deterministic",
        "run": source["run"],
        "evidence": source["evidence"] if evidence_mode == "source" else [],
        "result": source["result"],
        "trajectory": trajectory,
        "policy": {
            "requires_evidence": case.pop("requires_evidence"),
            "allowed_tools": case.pop("allowed_tools"),
            "blocked_after_untrusted_signal": case.pop(
                "blocked_after_untrusted_signal"
            ),
        },
        **case,
    }
    return validate_observation(observation)


def test_registry_order_is_stable():
    assert [(name, version) for name, version, _ in EVALUATOR_REGISTRY] == [
        ("result_contract", "1"),
        ("trajectory_policy", "1"),
        ("evidence_integrity", "1"),
        ("terminal_state", "1"),
        ("safety_boundary", "1"),
        ("efficiency_observation", "1"),
    ]


def test_canonical_success_has_no_blocking_findings():
    evaluated = evaluate_observation(_observation("canonical_success"))
    assert evaluated["status"] == "pass"
    assert evaluated["blocking_finding_codes"] == []
    assert evaluated["expectation_match"] is True


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_all_baseline_cases_emit_exact_expected_findings(case_id):
    observation = _observation(case_id)
    evaluated = evaluate_observation(observation)
    assert evaluated["blocking_finding_codes"] == observation["expected"][
        "blocking_finding_codes"
    ]
    assert evaluated["observational_finding_codes"] == observation["expected"][
        "observational_finding_codes"
    ]
    assert evaluated["expectation_match"] is True
    expected_status = "expected_block" if evaluated["blocking_finding_codes"] else "pass"
    assert evaluated["status"] == expected_status


def test_expected_finding_dictionaries_are_exact():
    evaluated = evaluate_observation(_observation("prohibited_tool"))
    assert evaluated["findings"] == [
        {
            "evaluator_id": "trajectory_policy",
            "code": "trajectory.tool_prohibited",
            "severity": "blocking",
        }
    ]


def test_consumer_contract_failure_is_projected_once(monkeypatch):
    observation = _observation("canonical_success")
    observation["result"]["body"]["artifact"]["content_hash"] = "0" * 64
    calls = []

    from scripts import agent_evaluation_evaluators as module

    original = module.project_consumer_case

    def tracked(**kwargs):
        calls.append(kwargs["case_id"])
        return original(**kwargs)

    monkeypatch.setattr(module, "project_consumer_case", tracked)
    context = build_evaluation_context(observation)
    assert calls == ["canonical_success"]
    assert context["consumer_case"] is None
    assert context["consumer_error"] == "contract_artifact_invalid"


@pytest.mark.parametrize(
    ("mutate", "code", "evaluator_id"),
    [
        (
            lambda value: value["trajectory"].insert(
                -1,
                {
                    "event_id": "orphan-result",
                    "kind": "tool_result",
                    "run_id": value["run"]["run_id"],
                    "call_id": "missing-call",
                    "trust": "trusted",
                },
            ),
            "trajectory.event_invalid",
            "trajectory_policy",
        ),
        (
            lambda value: value["trajectory"].append(
                {
                    "event_id": "assistant-after-terminal",
                    "kind": "assistant",
                    "run_id": value["run"]["run_id"],
                }
            ),
            "trajectory.event_invalid",
            "trajectory_policy",
        ),
        (
            lambda value: value.update(
                evidence_ref_status="observed", typed_evidence_refs=["ev_missing"]
            ),
            "evidence.reference_unresolved",
            "evidence_integrity",
        ),
        (
            lambda value: value["metrics"].__setitem__("tool_calls", 7),
            "metrics.invalid",
            "efficiency_observation",
        ),
    ],
)
def test_semantic_mutations_produce_stable_regression_findings(
    mutate, code, evaluator_id
):
    observation = _observation("canonical_success")
    mutate(observation)
    observation = validate_observation(observation)
    evaluated = evaluate_observation(observation)
    assert evaluated["status"] == "regression"
    assert {
        "evaluator_id": evaluator_id,
        "code": code,
        "severity": "blocking",
    } in evaluated["findings"]


def test_missing_expected_or_unexpected_finding_is_regression():
    missing = _observation("prohibited_tool")
    missing["expected"]["blocking_finding_codes"] = []
    assert evaluate_observation(validate_observation(missing))["status"] == "regression"

    unexpected = _observation("canonical_success")
    tool_call = next(event for event in unexpected["trajectory"] if event["kind"] == "tool_call")
    tool_call["tool_name"] = "write_file"
    assert evaluate_observation(validate_observation(unexpected))["status"] == "regression"


def test_observed_none_trust_signal_is_safe_and_markdown_is_never_inspected():
    observation = _observation("canonical_success")
    observation["result"]["body"]["artifact"]["content"] = (
        "# Claims\n\nNo typed facts are inferred from this Markdown."
    )
    import hashlib

    observation["result"]["body"]["artifact"]["content_hash"] = hashlib.sha256(
        observation["result"]["body"]["artifact"]["content"].encode("utf-8")
    ).hexdigest()
    evaluated = evaluate_observation(validate_observation(observation))
    assert evaluated["status"] == "pass"
    assert evaluated["findings"] == []
