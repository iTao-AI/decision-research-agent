from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from scripts.agent_evaluation_v2_contracts import (
    CASE_IDS,
    COMPARISON_SCHEMA_VERSION,
    DATASET_SCHEMA_VERSION,
    MUTATION_IDS,
    REPORT_SCHEMA_VERSION,
    EvaluationV2ValidationError,
    canonical_json_bytes,
    dataset_hash,
    load_dataset,
    validate_comparison,
    validate_dataset,
    validate_public_projection,
    validate_report,
)


DATASET_PATH = Path("benchmarks/agent-evaluation-v2/cases.json")


def _dataset() -> dict:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def _report() -> dict:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "dataset": {
            "schema_version": DATASET_SCHEMA_VERSION,
            "sha256": dataset_hash(_dataset()),
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


def _comparison() -> dict:
    return {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "match": True,
        "gate_passed": True,
        "changed_case_ids": [],
        "false_green_case_ids": [],
        "observed_declared_control_finding_codes": [
            "trajectory.event_invalid",
            "evidence.reference_unresolved",
            "safety.action_after_untrusted_instruction",
        ],
        "unexpected_blocking_finding_codes": [],
    }


def test_dataset_requires_exact_schema_and_three_ordered_classes():
    dataset = load_dataset(DATASET_PATH)
    assert dataset["schema_version"] == DATASET_SCHEMA_VERSION
    assert [case["case_id"] for case in dataset["cases"]] == list(CASE_IDS)
    assert [case["case_class"] for case in dataset["cases"]] == [
        "trajectory_regression",
        "evidence_regression",
        "safety_regression",
    ]

    for mutate in (
        lambda value: value.update(schema_version="dra.unknown.v1"),
        lambda value: value["cases"].reverse(),
        lambda value: value["cases"].append(copy.deepcopy(value["cases"][0])),
    ):
        broken = copy.deepcopy(dataset)
        mutate(broken)
        with pytest.raises(EvaluationV2ValidationError):
            validate_dataset(broken)


def test_each_case_has_exactly_one_known_mutation_and_responsible_finding():
    dataset = _dataset()
    assert [case["mutation_id"] for case in dataset["cases"]] == list(MUTATION_IDS)
    assert [
        (case["responsible_evaluator"], case["expected_control_finding"])
        for case in dataset["cases"]
    ] == [
        ("trajectory_policy", "trajectory.event_invalid"),
        ("evidence_integrity", "evidence.reference_unresolved"),
        ("safety_boundary", "safety.action_after_untrusted_instruction"),
    ]
    broken = copy.deepcopy(dataset)
    broken["cases"][0]["mutation_id"] = MUTATION_IDS[1]
    with pytest.raises(EvaluationV2ValidationError, match="evaluation_v2_case_invalid"):
        validate_dataset(broken)


def test_canonical_bytes_and_dataset_hash_are_stable():
    dataset = _dataset()
    assert canonical_json_bytes(dataset).endswith(b"\n")
    assert canonical_json_bytes(dataset) == canonical_json_bytes(copy.deepcopy(dataset))
    assert dataset_hash(dataset) == dataset_hash(copy.deepcopy(dataset))
    assert len(dataset_hash(dataset)) == 64


def test_hash_basis_is_domain_and_schema_bound_and_excludes_itself():
    dataset = _dataset()
    digest = dataset_hash(dataset)
    with_hash = copy.deepcopy(dataset)
    with_hash["sha256"] = digest
    with pytest.raises(EvaluationV2ValidationError):
        validate_dataset(with_hash)
    changed = copy.deepcopy(dataset)
    changed["cases"][0]["synthetic_query"] += " changed"
    assert dataset_hash(changed) != digest


def test_duplicate_unknown_unsafe_unbounded_nonfinite_values_fail_closed():
    dataset = _dataset()
    mutations = [
        lambda value: value["cases"][1].update(case_id=value["cases"][0]["case_id"]),
        lambda value: value.update(unexpected=True),
        lambda value: value["cases"][0].update(unexpected=True),
        lambda value: value["cases"][0].update(synthetic_query="x" * 8193),
        lambda value: value["cases"][0]["metrics"].update(elapsed_ms=math.inf),
        lambda value: value["cases"][0]["metrics"].update(tool_calls=True),
    ]
    for mutate in mutations:
        broken = copy.deepcopy(dataset)
        mutate(broken)
        with pytest.raises(EvaluationV2ValidationError):
            validate_dataset(broken)


def test_public_safety_rejects_raw_evidence_tool_artifact_exception_path_trace_and_credential_fields():
    unsafe = [
        {"raw_evidence": "body"},
        {"tool_payload": "body"},
        {"artifact_body": "body"},
        {"exception": "body"},
        {"safe": "/Users/example/private.txt"},
        {"trace_id": "trace-private"},
        {"credential": "assigned-value"},
    ]
    for payload in unsafe:
        with pytest.raises(
            EvaluationV2ValidationError,
            match="evaluation_v2_public_output_unsafe",
        ):
            validate_public_projection(payload)


def test_dataset_hash_covers_exact_synthetic_query_source_and_report_bytes():
    dataset = _dataset()
    original = dataset_hash(dataset)
    for field in (
        "synthetic_query",
        "synthetic_source_text",
        "synthetic_report_markdown",
    ):
        changed = copy.deepcopy(dataset)
        changed["cases"][0][field] += "x"
        assert dataset_hash(changed) != original


def test_report_and_comparison_reject_all_body_bearing_fields():
    assert validate_report(_report()) == _report()
    assert validate_comparison(_comparison()) == _comparison()
    for field in (
        "synthetic_query",
        "synthetic_source_text",
        "synthetic_report_markdown",
        "raw_evidence",
        "tool_payload",
        "artifact_body",
        "exception",
    ):
        report = _report()
        report[field] = "body"
        with pytest.raises(EvaluationV2ValidationError):
            validate_report(report)
        comparison = _comparison()
        comparison[field] = "body"
        with pytest.raises(EvaluationV2ValidationError):
            validate_comparison(comparison)
