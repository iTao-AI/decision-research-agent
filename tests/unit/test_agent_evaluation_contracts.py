from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.agent_evaluation_contracts import (
    CASE_IDS,
    MAX_MANIFEST_BYTES,
    EvaluationValidationError,
    assert_public_safe,
    dataset_hash,
    load_manifest,
    serialize_json,
    validate_comparison,
    validate_manifest,
    validate_observation,
    validate_report,
)


MANIFEST_PATH = Path("benchmarks/agent-evaluation-v1/scenarios.json")


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _observation() -> dict:
    manifest = _manifest()
    case = copy.deepcopy(manifest["cases"][0])
    case.pop("source_case_id")
    case.pop("evidence_mode")
    trajectory = []
    for event in case.pop("trajectory"):
        event["run_id"] = "run_evaluation_current"
        event.pop("run_ref")
        trajectory.append(event)
    return {
        "case_id": case.pop("case_id"),
        "source": "deterministic",
        "run": {
            "run_id": "run_evaluation_current",
            "execution_status": "completed",
            "review_status": "not_required",
            "delivery_status": "ready",
            "state_version": 1,
        },
        "evidence": [],
        "result": {
            "http_status": 409,
            "body": {
                "code": "run_result_unavailable",
                "problem": "Result unavailable.",
                "fix": "Retry later.",
                "retryable": True,
                "run_id": "run_evaluation_current",
            },
        },
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


def _report() -> dict:
    observation = _observation()
    return {
        "schema_version": "dra.agent-evaluation-report.v1",
        "evaluator_version": "1",
        "source": "deterministic",
        "dataset": {
            "schema_version": "dra.agent-evaluation-cases.v1",
            "sha256": "0" * 64,
            "case_ids": list(CASE_IDS),
        },
        "registry": [
            {"evaluator_id": evaluator_id, "version": "1"}
            for evaluator_id in (
                "result_contract",
                "trajectory_policy",
                "evidence_integrity",
                "terminal_state",
                "safety_boundary",
                "efficiency_observation",
            )
        ],
        "summary": {
            "blocking_regression_count": 0,
            "expectation_mismatch_count": 0,
            "observational_change_count": 0,
            "not_observed_count": 0,
            "release_gate_passed": True,
        },
        "cases": [
            {
                "case_id": observation["case_id"],
                "status": "pass",
                "expectation_match": True,
                "expected": observation["expected"],
                "evaluators": [
                    {
                        "evaluator_id": evaluator_id,
                        "status": "pass",
                        "finding_codes": [],
                    }
                    for evaluator_id in (
                        "result_contract",
                        "trajectory_policy",
                        "evidence_integrity",
                        "terminal_state",
                        "safety_boundary",
                        "efficiency_observation",
                    )
                ],
                "blocking_finding_codes": [],
                "observational_finding_codes": [],
                "findings": [],
                "metrics": observation["metrics"],
            }
        ],
        "limits": ["Deterministic contract regression proof."],
    }


def _comparison() -> dict:
    return {
        "schema_version": "dra.agent-evaluation-comparison.v1",
        "match": True,
        "candidate": {"json_sha256": "0" * 64, "markdown_sha256": "1" * 64},
        "baseline": {"json_sha256": "0" * 64, "markdown_sha256": "1" * 64},
        "changed_case_ids": [],
        "blocking_regression_codes": [],
        "observational_changes": [],
    }


def test_committed_manifest_has_exact_ordered_cases_and_stable_hash():
    manifest = load_manifest(MANIFEST_PATH)
    assert [case["case_id"] for case in manifest["cases"]] == list(CASE_IDS)
    assert dataset_hash(manifest) == dataset_hash(copy.deepcopy(manifest))
    assert len(dataset_hash(manifest)) == 64


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda value: value.update(extra=True), "evaluation_manifest_invalid"),
        (
            lambda value: value.__setitem__("schema_version", "dra.unknown.v1"),
            "evaluation_schema_unsupported",
        ),
        (
            lambda value: value["cases"][0].update(extra=True),
            "evaluation_case_invalid",
        ),
        (
            lambda value: value["cases"][0].__setitem__("requires_evidence", 1),
            "evaluation_case_invalid",
        ),
        (
            lambda value: value["cases"][0]["metrics"].__setitem__(
                "tool_calls", "1"
            ),
            "evaluation_metrics_invalid",
        ),
        (
            lambda value: value["cases"][0]["metrics"].__setitem__(
                "assistant_messages", True
            ),
            "evaluation_metrics_invalid",
        ),
    ],
)
def test_manifest_validation_fails_closed_with_stable_codes(mutate, code):
    payload = _manifest()
    mutate(payload)
    with pytest.raises(EvaluationValidationError) as exc_info:
        validate_manifest(payload)
    assert exc_info.value.code == code
    assert not isinstance(exc_info.value, ValidationError)


def test_manifest_rejects_duplicate_cases_events_and_invalid_signal_refs():
    duplicate_case = _manifest()
    duplicate_case["cases"][1]["case_id"] = duplicate_case["cases"][0]["case_id"]
    with pytest.raises(EvaluationValidationError, match="evaluation_case_invalid"):
        validate_manifest(duplicate_case)

    duplicate_event = _manifest()
    duplicate_event["cases"][0]["trajectory"][1]["event_id"] = "assistant-1"
    with pytest.raises(EvaluationValidationError, match="evaluation_case_invalid"):
        validate_manifest(duplicate_event)

    bad_signal = _manifest()
    bad_signal["cases"][6]["trust_signals"][0]["event_id"] = "missing-event"
    with pytest.raises(EvaluationValidationError, match="evaluation_case_invalid"):
        validate_manifest(bad_signal)


@pytest.mark.parametrize("source_case_id", ["missing_source", "fallback_ready"])
def test_manifest_rejects_unknown_or_cross_case_source_case_id(source_case_id):
    manifest = _manifest()
    manifest["cases"][0]["source_case_id"] = source_case_id
    with pytest.raises(EvaluationValidationError) as exc_info:
        validate_manifest(manifest)
    assert exc_info.value.code == "evaluation_case_invalid"


def test_observation_allows_semantic_orphan_but_rejects_structural_and_metric_errors():
    orphan = _observation()
    orphan["trajectory"] = [
        {
            "event_id": "result-1",
            "kind": "tool_result",
            "run_id": "run_evaluation_current",
            "call_id": "missing-call",
            "trust": "trusted",
        },
        {
            "event_id": "terminal-1",
            "kind": "terminal",
            "run_id": "run_evaluation_current",
        },
    ]
    assert validate_observation(orphan)["trajectory"][0]["call_id"] == "missing-call"

    malformed = copy.deepcopy(orphan)
    malformed["trajectory"][0]["unexpected"] = True
    with pytest.raises(EvaluationValidationError, match="evaluation_case_invalid"):
        validate_observation(malformed)

    metrics = _observation()
    metrics["metrics"]["tool_calls"] = "1"
    with pytest.raises(EvaluationValidationError, match="evaluation_metrics_invalid"):
        validate_observation(metrics)

    inconsistent = _observation()
    inconsistent["metrics"]["tool_calls"] = 7
    assert validate_observation(inconsistent)["metrics"]["tool_calls"] == 7


@pytest.mark.parametrize(
    ("validator", "payload", "code"),
    [
        (validate_manifest, lambda: {"schema_version": "dra.agent-evaluation-cases.v1"}, "evaluation_manifest_invalid"),
        (validate_observation, dict, "evaluation_case_invalid"),
        (validate_report, dict, "evaluation_output_invalid"),
        (validate_comparison, dict, "evaluation_output_invalid"),
    ],
)
def test_library_boundaries_wrap_pydantic_errors(validator, payload, code):
    with pytest.raises(EvaluationValidationError) as exc_info:
        validator(payload())
    assert exc_info.value.code == code
    assert not isinstance(exc_info.value, ValidationError)


def test_report_and_comparison_exact_schema_and_registry_validation():
    report = _report()
    assert validate_report(report) == report
    extra = copy.deepcopy(report)
    extra["extra"] = True
    with pytest.raises(EvaluationValidationError, match="evaluation_output_invalid"):
        validate_report(extra)
    bad_registry = copy.deepcopy(report)
    bad_registry["registry"] = []
    with pytest.raises(EvaluationValidationError, match="evaluation_registry_invalid"):
        validate_report(bad_registry)

    comparison = _comparison()
    assert validate_comparison(comparison) == comparison
    comparison["candidate"]["extra"] = True
    with pytest.raises(EvaluationValidationError, match="evaluation_output_invalid"):
        validate_comparison(comparison)


@pytest.mark.parametrize(
    "payload",
    [
        {"prompt": "hidden"},
        {"safe": {"content": "hidden"}},
        {"safe": "/Users/example/private.txt"},
        {"safe": "Traceback (most recent call last)"},
        {"safe": "api_key=example"},
    ],
)
def test_public_safety_scan_rejects_forbidden_material(payload):
    with pytest.raises(
        EvaluationValidationError, match="evaluation_public_output_unsafe"
    ):
        assert_public_safe(payload)


def test_bounded_loader_rejects_oversized_and_malformed_input(tmp_path):
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"{" + b" " * MAX_MANIFEST_BYTES + b"}")
    with pytest.raises(EvaluationValidationError, match="evaluation_manifest_invalid"):
        load_manifest(oversized)

    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(EvaluationValidationError, match="evaluation_manifest_invalid"):
        load_manifest(malformed)


def test_model_dump_plain_data_round_trip_and_serialization_are_byte_stable():
    manifest = _manifest()
    canonical = validate_manifest(manifest)
    assert canonical == json.loads(json.dumps(canonical))
    assert serialize_json(manifest, validator=validate_manifest) == serialize_json(
        canonical, validator=validate_manifest
    )

    reordered = {"cases": manifest["cases"], "schema_version": manifest["schema_version"]}
    assert dataset_hash(reordered) == dataset_hash(manifest)


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        (("amount",), "1.0"),
        (("amount",), "-0.00100000"),
        (("currency",), "usd"),
        (("currency",), "USDX"),
        (("pricing_basis",), "invalid basis"),
        (("estimate",), False),
        (("input_tokens",), -1),
        (("output_tokens",), 1.5),
    ],
)
def test_manifest_rejects_malformed_cost_and_token_variants(field_path, value):
    manifest = _manifest()
    token_usage = manifest["cases"][0]["metrics"]["token_usage"]
    target = token_usage["cost_estimate"] if field_path[0] in {
        "amount",
        "currency",
        "pricing_basis",
        "estimate",
    } else token_usage
    target[field_path[0]] = value
    with pytest.raises(EvaluationValidationError) as exc_info:
        validate_manifest(manifest)
    assert exc_info.value.code == "evaluation_metrics_invalid"


@pytest.mark.parametrize(("field", "value"), [("elapsed_ms", -1), ("elapsed_ms", 1.5)])
def test_manifest_rejects_negative_or_non_integer_elapsed_metrics(field, value):
    manifest = _manifest()
    manifest["cases"][0]["metrics"][field] = value
    with pytest.raises(EvaluationValidationError) as exc_info:
        validate_manifest(manifest)
    assert exc_info.value.code == "evaluation_metrics_invalid"
