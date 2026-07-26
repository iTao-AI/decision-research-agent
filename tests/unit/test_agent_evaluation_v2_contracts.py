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
    MAX_DATASET_BYTES,
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
REPORT_PATH = Path("docs/evidence/agent-evaluation-sensitivity-v2.json")
RUNNER = {
    "runner_id": "dra.agent-evaluation-v2-runner",
    "version": "1",
}
EVALUATOR_REGISTRY = {
    "registry_id": "dra.agent-evaluation-v1-registry",
    "version": "1",
    "evaluators": [
        {"evaluator_id": "result_contract", "version": "1"},
        {"evaluator_id": "trajectory_policy", "version": "1"},
        {"evaluator_id": "evidence_integrity", "version": "1"},
        {"evaluator_id": "terminal_state", "version": "1"},
        {"evaluator_id": "safety_boundary", "version": "1"},
        {"evaluator_id": "efficiency_observation", "version": "1"},
    ],
}
SEMANTIC_COMPARISON = {
    "schema_version": "dra.agent-evaluation-v2-semantic-comparison.v1",
    "normalized_fields": [
        "observation.run.run_id",
        "observation.result.body.run_id",
        "observation.trajectory[*].run_id",
        "observation.evidence[0].evidence_id",
        "observation.typed_evidence_refs[*]",
        "observation.evidence[0].retrieved_at",
    ],
}


def _dataset() -> dict:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def _report() -> dict:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    report["dataset"]["sha256"] = dataset_hash(_dataset())
    for pair in report["pairs"]:
        for field in ("checkpoints_current", "checkpoints_control_anchor"):
            if pair[field] and isinstance(pair[field][0], list):
                pair[field] = [
                    {"checkpoint": checkpoint, "passed": passed}
                    for checkpoint, passed in pair[field]
                ]
    report["runner"] = copy.deepcopy(RUNNER)
    report["evaluator_registry"] = copy.deepcopy(EVALUATOR_REGISTRY)
    report["semantic_comparison"] = copy.deepcopy(SEMANTIC_COMPARISON)
    return report


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


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    [
        ("synthetic_query", "/Users/example/private-query"),
        ("synthetic_query", "api_key=not-a-real-key"),
        ("synthetic_query", "Traceback (most recent call last): synthetic"),
        ("synthetic_source_text", "/home/example/private-source"),
        ("synthetic_source_text", "secret=not-a-real-secret"),
        ("synthetic_source_text", "Traceback: synthetic source"),
        ("synthetic_report_markdown", "/private/example/report.md"),
        ("synthetic_report_markdown", "credential: not-a-real-credential"),
        ("synthetic_report_markdown", "Traceback (most recent call last)"),
        ("source_url", "/Users/example/source"),
    ],
)
def test_dataset_rejects_host_path_credential_and_traceback_markers_in_string_values(
    field,
    unsafe_value,
):
    dataset = _dataset()
    dataset["cases"][0][field] = unsafe_value
    with pytest.raises(
        EvaluationV2ValidationError,
        match="evaluation_v2_dataset_invalid",
    ):
        validate_dataset(dataset)


def test_dataset_rejects_dead_artifact_descriptor_authority():
    dataset = validate_dataset(_dataset())
    assert all("artifact" not in case for case in dataset["cases"])
    changed = copy.deepcopy(dataset)
    changed["cases"][0]["artifact"] = {
        "artifact_id": "research-report.md",
        "kind": "research_report_markdown",
        "media_type": "text/markdown",
    }
    with pytest.raises(EvaluationV2ValidationError):
        validate_dataset(changed)


def test_dataset_oversize_read_is_bounded_before_validation(tmp_path, monkeypatch):
    oversized = tmp_path / "oversized-dataset.json"
    oversized.write_bytes(b"x" * (MAX_DATASET_BYTES + 2))
    requested_sizes: list[int] = []
    real_open = Path.open

    class TrackingReader:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            self.handle.close()

        def read(self, size=-1):
            requested_sizes.append(size)
            return self.handle.read(size)

    def tracking_open(path, *args, **kwargs):
        handle = real_open(path, *args, **kwargs)
        return TrackingReader(handle) if path == oversized else handle

    monkeypatch.setattr(Path, "open", tracking_open)
    with pytest.raises(
        EvaluationV2ValidationError,
        match="evaluation_v2_dataset_invalid",
    ):
        load_dataset(oversized)
    assert requested_sizes == [MAX_DATASET_BYTES + 1]


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


def test_report_requires_exact_runner_registry_and_semantic_comparison_identities():
    report = _report()
    assert validate_report(report) == report
    mutations = (
        lambda value: value.pop("runner"),
        lambda value: value["runner"].update(version="2"),
        lambda value: value["evaluator_registry"]["evaluators"].reverse(),
        lambda value: value["evaluator_registry"].update(version="2"),
        lambda value: value["semantic_comparison"]["normalized_fields"].reverse(),
        lambda value: value["semantic_comparison"].update(
            schema_version="dra.agent-evaluation-v2-semantic-comparison.v2"
        ),
    )
    original_bytes = canonical_json_bytes(report)
    for mutate in mutations:
        changed = copy.deepcopy(report)
        mutate(changed)
        assert canonical_json_bytes(changed) != original_bytes
        with pytest.raises(
            EvaluationV2ValidationError,
            match="evaluation_v2_report_invalid",
        ):
            validate_report(changed)


def test_report_pairs_are_closed_ordered_unique_and_summary_derived():
    report = _report()
    mutations = (
        lambda value: value["pairs"][0].update(unknown="safe"),
        lambda value: value["pairs"][0].pop("application_projection"),
        lambda value: value["pairs"].reverse(),
        lambda value: value["pairs"].__setitem__(
            1, copy.deepcopy(value["pairs"][0])
        ),
        lambda value: value["pairs"][0]["checkpoints_current"].pop(),
        lambda value: value["pairs"][0]["checkpoints_current"].reverse(),
        lambda value: value["pairs"][0]["current_anchor_evaluators"].reverse(),
        lambda value: value["pairs"][0]["current_anchor_evaluators"].append(
            copy.deepcopy(value["pairs"][0]["current_anchor_evaluators"][0])
        ),
        lambda value: value["pairs"][0]["application_projection"].update(
            unknown="safe"
        ),
        lambda value: value["pairs"][0][
            "current_semantic_observation_projection"
        ].update(unknown="safe"),
        lambda value: value["summary"].update(pair_count=0),
        lambda value: value["summary"].update(healthy_anchor_count=0),
        lambda value: value["summary"].update(sensitive_pair_count=0),
        lambda value: value["summary"].update(gate_passed=False),
    )
    for mutate in mutations:
        changed = copy.deepcopy(report)
        mutate(changed)
        with pytest.raises(
            EvaluationV2ValidationError,
            match="evaluation_v2_report_invalid",
        ):
            validate_report(changed)


def test_report_binds_application_projection_to_all_semantic_inputs():
    semantic_fields = (
        "current_semantic_observation_projection",
        "control_anchor_semantic_observation_projection",
        "synthetic_control_semantic_observation_projection",
    )
    changed_reports = []

    swapped = _report()
    swapped["pairs"][0]["application_projection"], swapped["pairs"][1][
        "application_projection"
    ] = (
        swapped["pairs"][1]["application_projection"],
        swapped["pairs"][0]["application_projection"],
    )
    changed_reports.append(swapped)

    artifact_drift = _report()
    for field in semantic_fields:
        artifact_drift["pairs"][0][field]["observation"]["result"]["body"][
            "artifact"
        ]["content_hash"] = "0" * 64
    changed_reports.append(artifact_drift)

    source_drift = _report()
    source_drift["pairs"][0]["application_projection"]["evidence"][0][
        "source_identity_sha256"
    ] = "0" * 64
    changed_reports.append(source_drift)

    for changed in changed_reports:
        with pytest.raises(
            EvaluationV2ValidationError,
            match="evaluation_v2_report_invalid",
        ):
            validate_report(changed)


def test_report_rejects_unknown_nested_semantic_projection_vocabulary():
    semantic_fields = (
        "current_semantic_observation_projection",
        "control_anchor_semantic_observation_projection",
        "synthetic_control_semantic_observation_projection",
    )

    def mutate_all(report, mutation):
        for field in semantic_fields:
            mutation(report["pairs"][0][field]["observation"])

    mutations = (
        lambda report: mutate_all(
            report,
            lambda observation: observation["policy"].update(
                allowed_tools=["arbitrary_tool"]
            ),
        ),
        lambda report: mutate_all(
            report,
            lambda observation: observation["evidence"][0].update(
                source_url="https://example.invalid/arbitrary",
                source_identity="https://example.invalid/arbitrary",
            ),
        ),
        lambda report: mutate_all(
            report,
            lambda observation: observation["trajectory"][0].update(
                event_id="arbitrary-assistant"
            ),
        ),
    )
    for mutate in mutations:
        changed = _report()
        mutate(changed)
        with pytest.raises(
            EvaluationV2ValidationError,
            match="evaluation_v2_report_invalid",
        ):
            validate_report(changed)


def test_report_enforces_declared_two_mib_canonical_public_byte_bound(monkeypatch):
    import scripts.agent_evaluation_v2_contracts as contracts

    report = _report()
    canonical_size = len(canonical_json_bytes(report))
    monkeypatch.setattr(contracts, "MAX_PUBLIC_BYTES", canonical_size - 1)
    with pytest.raises(
        EvaluationV2ValidationError,
        match="evaluation_v2_report_invalid",
    ):
        validate_report(report)


def test_comparison_requires_stable_unique_order_and_coherent_flags():
    comparison = _comparison()
    assert validate_comparison(comparison) == comparison
    mutations = (
        lambda value: value["changed_case_ids"].extend(
            [CASE_IDS[1], CASE_IDS[0]]
        ),
        lambda value: value["changed_case_ids"].extend(
            [CASE_IDS[0], CASE_IDS[0]]
        ),
        lambda value: value["false_green_case_ids"].append("unknown-case"),
        lambda value: value[
            "observed_declared_control_finding_codes"
        ].reverse(),
        lambda value: value[
            "observed_declared_control_finding_codes"
        ].append("arbitrary.finding"),
        lambda value: value["unexpected_blocking_finding_codes"].append(
            "arbitrary.finding"
        ),
        lambda value: value.update(gate_passed=False),
        lambda value: (
            value["changed_case_ids"].append(CASE_IDS[0]),
            value.update(match=True),
        ),
    )
    for mutate in mutations:
        changed = copy.deepcopy(comparison)
        mutate(changed)
        with pytest.raises(
            EvaluationV2ValidationError,
            match="evaluation_v2_report_invalid",
        ):
            validate_comparison(changed)


def test_comparison_accepts_one_coherent_false_green_in_stable_case_order():
    comparison = _comparison()
    comparison.update(match=False, gate_passed=False)
    comparison["changed_case_ids"] = [CASE_IDS[0]]
    comparison["false_green_case_ids"] = [CASE_IDS[0]]
    comparison["observed_declared_control_finding_codes"] = [
        "evidence.reference_unresolved",
        "safety.action_after_untrusted_instruction",
    ]
    assert validate_comparison(comparison) == comparison


def test_comparison_enforces_declared_two_mib_canonical_public_byte_bound(
    monkeypatch,
):
    import scripts.agent_evaluation_v2_contracts as contracts

    comparison = _comparison()
    canonical_size = len(canonical_json_bytes(comparison))
    monkeypatch.setattr(contracts, "MAX_PUBLIC_BYTES", canonical_size - 1)
    with pytest.raises(
        EvaluationV2ValidationError,
        match="evaluation_v2_report_invalid",
    ):
        validate_comparison(comparison)
