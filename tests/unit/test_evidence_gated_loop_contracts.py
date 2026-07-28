from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evidence_gated_loop_contracts import (
    MAX_COLLECTION_ITEMS,
    MAX_DEPTH,
    MAX_REGISTRY_BYTES,
    CASES_ROOT,
    PROJECT_ROOT,
    LoopContractError,
    canonical_json_bytes,
    load_case_file,
    load_registry,
    validate_public_projection,
    validate_case,
    validate_registry,
)


REGISTRY_PATH = (
    PROJECT_ROOT / "benchmarks/evidence-gated-loop-v1/registry.json"
)


def _registry_value() -> dict[str, object]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_registry_accepts_exact_closed_provider_free_contract() -> None:
    registry = load_registry()
    assert registry.schema_version == "dra.evidence-gated-loop-registry.v1"
    assert registry.kernel_id == "dra.evidence-gated-loop-kernel"
    assert [ref.profile_id for ref in registry.verification_profiles] == [
        "context-resolver-coherence",
        "evaluation-sensitivity",
        "strict-citation-consumer",
    ]
    assert list(registry.case_paths) == sorted(registry.case_paths)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda value: value.__setitem__("extra", True), "loop_registry_invalid"),
        (
            lambda value: value["case_paths"].append(value["case_paths"][0]),
            "loop_registry_invalid",
        ),
        (
            lambda value: value["verification_profiles"].append(
                dict(value["verification_profiles"][0])
            ),
            "loop_registry_invalid",
        ),
        (lambda value: value["case_paths"].reverse(), "loop_registry_invalid"),
        (
            lambda value: value["case_paths"].__setitem__(0, "../escape.json"),
            "loop_registry_invalid",
        ),
        (
            lambda value: value["case_paths"].__setitem__(
                0,
                "benchmarks/evidence-gated-loop-v1/cases/nested/case.json",
            ),
            "loop_registry_invalid",
        ),
        (
            lambda value: value["verification_profiles"][0].__setitem__(
                "command", ["pytest"]
            ),
            "loop_registry_invalid",
        ),
        (
            lambda value: value["verification_profiles"][0].__setitem__(
                "selector", "tests/unit/test_private.py"
            ),
            "loop_registry_invalid",
        ),
        (
            lambda value: value["verification_profiles"][0].__setitem__(
                "import_path", "private.module"
            ),
            "loop_registry_invalid",
        ),
        (
            lambda value: value["verification_profiles"][0].__setitem__(
                "environment", {"TOKEN": "value"}
            ),
            "loop_registry_invalid",
        ),
        (
            lambda value: value["verification_profiles"][0].__setitem__(
                "output_path", "/tmp/report"
            ),
            "loop_registry_invalid",
        ),
        (
            lambda value: value["non_claims"].__setitem__(
                0, "No additional boundary."
            ),
            "loop_registry_invalid",
        ),
    ],
)
def test_registry_rejects_schema_order_path_and_executable_surface_mutations(
    mutation, code
) -> None:
    value = _registry_value()
    mutation(value)
    with pytest.raises(LoopContractError, match=code):
        validate_registry(value)


def test_bounded_read_stops_at_limit_plus_one(tmp_path: Path) -> None:
    path = tmp_path / "oversized.json"
    path.write_bytes(b"x" * (MAX_REGISTRY_BYTES + 1))
    with pytest.raises(LoopContractError, match="loop_registry_invalid"):
        load_registry(path)


def test_registry_requires_canonical_bytes(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    value = _registry_value()
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(LoopContractError, match="loop_registry_invalid"):
        load_registry(path)


def test_registry_symlink_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_bytes(canonical_json_bytes(_registry_value()))
    link = tmp_path / "registry.json"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    with pytest.raises(LoopContractError, match="loop_registry_invalid"):
        load_registry(link)


@pytest.mark.parametrize(
    "unsafe",
    [
        {"items": list(range(MAX_COLLECTION_ITEMS + 1))},
        {"number": float("nan")},
    ],
)
def test_public_projection_rejects_excessive_or_nonfinite_values(
    unsafe: object,
) -> None:
    with pytest.raises(LoopContractError, match="loop_public_output_unsafe"):
        validate_public_projection(unsafe)


def test_public_projection_rejects_excessive_depth() -> None:
    unsafe: dict[str, object] = {}
    cursor = unsafe
    for index in range(MAX_DEPTH + 1):
        child: dict[str, object] = {}
        cursor[f"level_{index}"] = child
        cursor = child
    with pytest.raises(LoopContractError, match="loop_public_output_unsafe"):
        validate_public_projection(unsafe)


@pytest.mark.parametrize(
    "unsafe",
    [
        {"prompt": "body"},
        {"safe": "Traceback: private"},
        {"safe": "/Users/private/repo"},
        {"safe": "saved under /private/runtime/report.json"},
        {"safe": "saved under /var/tmp/report.json"},
        {"safe": "saved under /tmp/report.json"},
        {"safe": "saved under /Volumes/work/report.json"},
        {"safe": "saved under /opt/service/report.json"},
        {"safe": "saved under /etc/service/report.json"},
        {"safe": "saved under /root/report.json"},
        {"safe": "api_key=secret"},
        {"tool_payload": {"value": "body"}},
    ],
)
def test_public_projection_rejects_body_path_trace_and_credentials(
    unsafe: object,
) -> None:
    with pytest.raises(LoopContractError, match="loop_public_output_unsafe"):
        validate_public_projection(unsafe)


def _case(name: str) -> dict[str, object]:
    path = CASES_ROOT / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_case_file_requires_canonical_bytes(tmp_path: Path) -> None:
    path = tmp_path / "case.json"
    value = _case("context-resolver-projection")
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(LoopContractError, match="loop_case_invalid"):
        load_case_file(path)


def test_case_file_symlink_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_bytes(
        canonical_json_bytes(_case("context-resolver-projection"))
    )
    link = tmp_path / "case.json"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    with pytest.raises(LoopContractError, match="loop_case_invalid"):
        load_case_file(link)


def test_three_reference_cases_and_four_episodes_are_ordered() -> None:
    cases = [
        load_case_file(CASES_ROOT / "context-resolver-projection.json"),
        load_case_file(CASES_ROOT / "evaluation-sensitivity.json"),
        load_case_file(CASES_ROOT / "strict-citation-consumer.json"),
    ]
    assert [case.case_id for case in cases] == [
        "context-resolver-projection",
        "evaluation-sensitivity",
        "strict-citation-consumer",
    ]
    assert [episode.episode_id for episode in cases[2].episodes] == [
        "strict-citation-change-episode-1",
        "strict-citation-consumer-close-episode-2",
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda case: case["episodes"][0]["carrier_assessments"].append(
            copy.deepcopy(case["episodes"][0]["carrier_assessments"][2])
        ),
        lambda case: case["episodes"][0]["candidate_refs"].append(
            copy.deepcopy(case["episodes"][0]["candidate_refs"][0])
        ),
        lambda case: case["episodes"][0]["action"].__setitem__(
            "selected_carrier", "knowledge"
        ),
        lambda case: case["episodes"][0]["candidate_refs"][0].__setitem__(
            "carrier", "prompt_skill"
        ),
    ],
)
def test_change_rejects_multiple_or_mismatched_carrier_candidate(
    mutation,
) -> None:
    case = _case("context-resolver-projection")
    mutation(case)
    with pytest.raises(LoopContractError, match="loop_action_invalid"):
        validate_case(case)


def test_no_change_rejects_selected_carrier_or_candidate() -> None:
    case = _case("strict-citation-consumer")
    episode = case["episodes"][1]
    episode["candidate_refs"] = [
        copy.deepcopy(case["episodes"][0]["candidate_refs"][0])
    ]
    with pytest.raises(LoopContractError, match="loop_action_invalid"):
        validate_case(case)


def test_inconclusive_diagnosis_cannot_accept_candidate() -> None:
    case = _case("context-resolver-projection")
    case["episodes"][0]["diagnosis"]["status"] = "inconclusive"
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)


def test_evaluation_red_identity_is_pre_candidate() -> None:
    case = _case("evaluation-sensitivity")
    candidate = case["episodes"][0]["candidate_refs"][0]
    predecessor = candidate["predecessor_or_rollback_ref"]
    for evidence_id in ("evaluator-gap", "evaluator-red"):
        evidence = next(
            item
            for item in case["evidence_refs"]
            if item["evidence_id"] == evidence_id
        )
        assert evidence["commit_sha"] == predecessor
        assert evidence["commit_sha"] != candidate["commit_sha"]
        assert (
            evidence["tree_sha"]
            == "56fb2e148da3b4026f5ec430b94336e5e484cb85"
        )


def test_passed_candidate_requires_candidate_bound_pass_receipt() -> None:
    case = _case("context-resolver-projection")
    case["episodes"][0]["reviewed_decision"][
        "reviewed_verification_evidence_ids"
    ] = []
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)


def test_selected_model_parameters_fail_closed() -> None:
    case = _case("context-resolver-projection")
    assessments = case["episodes"][0]["carrier_assessments"]
    assessments[2]["disposition"] = "rejected"
    assessments[3]["disposition"] = "selected"
    case["episodes"][0]["action"]["selected_carrier"] = "model_parameters"
    with pytest.raises(LoopContractError, match="loop_action_invalid"):
        validate_case(case)


def test_pending_consumer_cannot_claim_closed_acceptance() -> None:
    case = _case("strict-citation-consumer")
    case["episodes"][0]["reviewed_decision"]["loop_closure_status"] = (
        "closed_accepted"
    )
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)


def set_nested(value: object, path: tuple[object, ...], replacement: object) -> None:
    current = value
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = replacement


@pytest.mark.parametrize(
    "mutation",
    [
        lambda case: case["episodes"][0]["action"].pop(
            "selected_carrier"
        ),
        lambda case: case["episodes"][0].__setitem__(
            "candidate_refs", []
        ),
    ],
)
def test_change_rejects_missing_selected_carrier_or_candidate(
    mutation,
) -> None:
    case = _case("context-resolver-projection")
    mutation(case)
    with pytest.raises(LoopContractError, match="loop_action_invalid"):
        validate_case(case)


def test_inconclusive_diagnosis_can_wait_with_no_change() -> None:
    case = _case("context-resolver-projection")
    episode = case["episodes"][0]
    episode["diagnosis"]["status"] = "inconclusive"
    episode["carrier_assessments"][2]["disposition"] = "deferred"
    episode["action"] = {
        "kind": "no_change",
        "reason_codes": ["insufficient_evidence_for_change"],
    }
    case["evidence_refs"] = [
        evidence for evidence in case["evidence_refs"]
        if evidence["evidence_id"] != "context-candidate-pass"
    ]
    episode["input_evidence_ids"] = ["context-red"]
    episode["candidate_refs"] = []
    episode["reviewed_decision"] = {
        "reviewed_candidate_verification_status": "not_applicable",
        "reviewed_verification_evidence_ids": [],
        "candidate_verdict": "not_applicable",
        "consumer_proof_status": "not_required",
        "loop_closure_status": "open_waiting_evidence",
        "release_disposition": "hold",
        "rollback_basis": None,
        "rollback_evidence_ids": [],
        "rollback_subject_candidate_id": None,
        "rollback_target": None,
        "reason_codes": ["more_reviewed_evidence_required"],
    }
    assert validate_case(case).episodes[0].reviewed_decision \
        .loop_closure_status == "open_waiting_evidence"


def test_accepted_candidate_requires_historical_red() -> None:
    case = _case("evaluation-sensitivity")
    case["episodes"][0]["input_evidence_ids"] = [
        "evaluator-gap", "evaluator-candidate-pass",
    ]
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository", "https://github.com/iTao-AI/night-voyager"),
        ("commit_sha", "f" * 40),
        ("tree_sha", "e" * 40),
    ],
)
def test_pass_receipt_identity_matches_exact_candidate(field, value) -> None:
    case = _case("context-resolver-projection")
    receipt = next(
        item for item in case["evidence_refs"]
        if item["evidence_id"] == "context-candidate-pass"
    )
    receipt[field] = value
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)


@pytest.mark.parametrize("status", ["failed", "inconclusive"])
def test_accepted_candidate_requires_passed_reviewed_verification(
    status,
) -> None:
    case = _case("context-resolver-projection")
    case["episodes"][0]["reviewed_decision"][
        "reviewed_candidate_verification_status"
    ] = status
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)


def test_reviewed_verification_evidence_ids_match_status_and_inputs() -> None:
    case = _case("context-resolver-projection")
    decision = case["episodes"][0]["reviewed_decision"]
    decision["reviewed_verification_evidence_ids"] = ["context-red"]
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)
    decision["reviewed_candidate_verification_status"] = "failed"
    decision["reviewed_verification_evidence_ids"] = ["missing-evidence"]
    decision["candidate_verdict"] = "rejected"
    decision["loop_closure_status"] = "closed_rejected"
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)


def test_reviewed_verification_evidence_binds_status_proof_kind() -> None:
    case = _case("context-resolver-projection")
    evidence = case["evidence_refs"][1]
    evidence["proof_kind"] = \
        "reviewed_candidate_verification_inconclusive"
    evidence["origin_kind"] = "verification_gap"
    evidence["subject_candidate_id"] = "context-projection-pr-123"
    decision = case["episodes"][0]["reviewed_decision"]
    decision["reviewed_candidate_verification_status"] = "failed"
    decision["reviewed_verification_evidence_ids"] = [
        "context-candidate-pass"
    ]
    decision["candidate_verdict"] = "rejected"
    decision["loop_closure_status"] = "closed_rejected"
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)


def test_candidate_verification_applicability_matches_action_kind() -> None:
    change = _case("context-resolver-projection")
    change["episodes"][0]["reviewed_decision"][
        "reviewed_candidate_verification_status"
    ] = "not_applicable"
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(change)
    no_change = _case("strict-citation-consumer")
    no_change["episodes"][1]["reviewed_decision"][
        "reviewed_candidate_verification_status"
    ] = "passed"
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(no_change)


@pytest.mark.parametrize(
    ("consumer_status", "verdict", "closure"),
    [
        ("pending", "accepted", "open_waiting_consumer"),
        ("rejected", "rejected", "closed_rejected"),
    ],
)
def test_pending_or_rejected_consumer_cannot_be_release_eligible(
    consumer_status, verdict, closure
) -> None:
    case = _case("strict-citation-consumer")
    decision = case["episodes"][0]["reviewed_decision"]
    decision["consumer_proof_status"] = consumer_status
    decision["candidate_verdict"] = verdict
    decision["loop_closure_status"] = closure
    decision["release_disposition"] = "eligible_for_separate_release_review"
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)


def test_accepted_closed_candidate_can_be_eligible_for_separate_review() -> None:
    case = _case("context-resolver-projection")
    decision = case["episodes"][0]["reviewed_decision"]
    decision["release_disposition"] = \
        "eligible_for_separate_release_review"
    decision["reason_codes"] = ["separate_release_review_required"]
    assert validate_case(case).episodes[0].reviewed_decision \
        .release_disposition == "eligible_for_separate_release_review"


def test_nonrollback_decision_rejects_rollback_target() -> None:
    case = _case("context-resolver-projection")
    case["episodes"][0]["reviewed_decision"]["rollback_target"] = \
        "2dadae56f038790f66c4c3af05b7bae10d8e0462"
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)


def test_rollback_recommendation_requires_accepted_predecessor_and_target() -> None:
    case = _case("strict-citation-consumer")
    evidence = next(
        item for item in case["evidence_refs"]
        if item["evidence_id"] == "strict-consumer-pr-75"
    )
    evidence["proof_kind"] = "independent_consumer_rejection"
    evidence["reviewed_summary"] = (
        "A reviewed consumer contract rejected the exact producer tuple "
        "without changing the approved public gate."
    )
    evidence["claim_scope"] = (
        "consumer-owned contract rejection of the exact producer tuple"
    )
    decision = case["episodes"][1]["reviewed_decision"]
    decision["release_disposition"] = "rollback_recommended"
    decision["loop_closure_status"] = "closed_rejected"
    decision["consumer_proof_status"] = "rejected"
    decision["rollback_basis"] = "consumer_rejection"
    decision["rollback_evidence_ids"] = ["strict-consumer-pr-75"]
    decision["rollback_subject_candidate_id"] = "strict-citation-pr-129"
    decision["reason_codes"] = ["reviewed_consumer_rejection"]
    decision["rollback_target"] = None
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)
    decision["rollback_target"] = \
        "6a3020863fbaaf9d218420b7981150a5736b7fb8"
    assert validate_case(case).episodes[1].reviewed_decision \
        .release_disposition == "rollback_recommended"


@pytest.mark.parametrize(
    (
        "basis",
        "proof_kind",
        "origin_kind",
        "consumer_status",
    ),
    [
        (
            "regression",
            "reviewed_candidate_regression",
            "repository_audit",
            "not_required",
        ),
        (
            "safety",
            "reviewed_candidate_safety_failure",
            "verification_gap",
            "not_required",
        ),
        (
            "consumer_rejection",
            "independent_consumer_rejection",
            "downstream_consumer",
            "rejected",
        ),
    ],
)
def test_rollback_basis_binds_new_episode_evidence(
    basis, proof_kind, origin_kind, consumer_status
) -> None:
    case = _case("strict-citation-consumer")
    evidence = next(
        item for item in case["evidence_refs"]
        if item["evidence_id"] == "strict-consumer-pr-75"
    )
    evidence["proof_kind"] = proof_kind
    evidence["origin_kind"] = origin_kind
    evidence["locator"] = f"synthetic reviewed {basis} rollback fixture"
    evidence["reviewed_summary"] = (
        "A bounded synthetic rollback fixture records reviewed "
        f"{basis} evidence for the immutable subject candidate."
    )
    evidence["claim_scope"] = \
        f"contract validation for a reviewed {basis} rollback basis"
    decision = case["episodes"][1]["reviewed_decision"]
    decision["candidate_verdict"] = "not_applicable"
    decision["consumer_proof_status"] = consumer_status
    decision["loop_closure_status"] = "closed_rejected"
    decision["release_disposition"] = "rollback_recommended"
    decision["rollback_basis"] = basis
    decision["rollback_evidence_ids"] = ["strict-consumer-pr-75"]
    decision["rollback_subject_candidate_id"] = "strict-citation-pr-129"
    decision["rollback_target"] = \
        "6a3020863fbaaf9d218420b7981150a5736b7fb8"
    decision["reason_codes"] = [f"reviewed_{basis}"]
    assert validate_case(case).episodes[1].reviewed_decision \
        .rollback_basis == basis


@pytest.mark.parametrize(
    ("evidence_ids", "basis"),
    [
        ([], "consumer_rejection"),
        (["strict-live-25-0"], "consumer_rejection"),
        (["strict-consumer-pr-75"], "regression"),
    ],
)
def test_rollback_rejects_missing_old_or_wrong_kind_evidence(
    evidence_ids, basis
) -> None:
    case = _case("strict-citation-consumer")
    decision = case["episodes"][1]["reviewed_decision"]
    decision["candidate_verdict"] = "not_applicable"
    decision["consumer_proof_status"] = "rejected"
    decision["loop_closure_status"] = "closed_rejected"
    decision["release_disposition"] = "rollback_recommended"
    decision["rollback_basis"] = basis
    decision["rollback_evidence_ids"] = evidence_ids
    decision["rollback_subject_candidate_id"] = "strict-citation-pr-129"
    decision["rollback_target"] = \
        "6a3020863fbaaf9d218420b7981150a5736b7fb8"
    decision["reason_codes"] = ["reviewed_rollback"]
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)


def test_rollback_rejects_subject_mismatch() -> None:
    case = _case("strict-citation-consumer")
    evidence = next(
        item for item in case["evidence_refs"]
        if item["evidence_id"] == "strict-consumer-pr-75"
    )
    evidence["proof_kind"] = "independent_consumer_rejection"
    decision = case["episodes"][1]["reviewed_decision"]
    decision["consumer_proof_status"] = "rejected"
    decision["loop_closure_status"] = "closed_rejected"
    decision["release_disposition"] = "rollback_recommended"
    decision["rollback_basis"] = "consumer_rejection"
    decision["rollback_evidence_ids"] = ["strict-consumer-pr-75"]
    decision["rollback_subject_candidate_id"] = "missing-candidate"
    decision["rollback_target"] = \
        "6a3020863fbaaf9d218420b7981150a5736b7fb8"
    decision["reason_codes"] = ["reviewed_consumer_rejection"]
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)


def test_valid_rejected_and_need_more_records_remain_structurally_valid() -> None:
    for status, proof_kind, origin_kind, verdict, closure in [
        (
            "failed",
            "reviewed_candidate_regression",
            "repository_audit",
            "rejected",
            "closed_rejected",
        ),
        (
            "inconclusive",
            "reviewed_candidate_verification_inconclusive",
            "verification_gap",
            "need_more_evidence",
            "open_waiting_evidence",
        ),
    ]:
        case = _case("context-resolver-projection")
        episode = case["episodes"][0]
        candidate = episode["candidate_refs"][0]
        candidate_id = f"reviewed-{status}-candidate"
        candidate["candidate_id"] = candidate_id
        candidate["commit_sha"] = "1" * 40
        candidate["tree_sha"] = "2" * 40
        evidence = case["evidence_refs"][1]
        evidence["proof_kind"] = proof_kind
        evidence["origin_kind"] = origin_kind
        evidence["subject_candidate_id"] = candidate_id
        evidence["commit_sha"] = candidate["commit_sha"]
        evidence["tree_sha"] = candidate["tree_sha"]
        evidence["locator"] = \
            f"synthetic reviewed {status} candidate fixture"
        evidence["reviewed_summary"] = (
            "A bounded synthetic contract fixture records a reviewed "
            f"{status} candidate verification status."
        )
        evidence["claim_scope"] = \
            "contract validation for a reviewed nonpassing candidate record"
        decision = episode["reviewed_decision"]
        decision["reviewed_candidate_verification_status"] = status
        decision["reviewed_verification_evidence_ids"] = [
            "context-candidate-pass"
        ]
        decision["candidate_verdict"] = verdict
        decision["loop_closure_status"] = closure
        decision["reason_codes"] = [f"reviewed_{verdict}"]
        assert validate_case(case).episodes[0].reviewed_decision.candidate_verdict \
            == verdict


def test_existing_kind_new_case_reuses_v1_case_schema() -> None:
    case = _case("context-resolver-projection")
    case["case_id"] = "future-context-case"
    case["evidence_refs"][0]["evidence_id"] = "future-red"
    case["evidence_refs"][1]["evidence_id"] = "future-pass"
    case["evidence_refs"][1]["subject_candidate_id"] = "future-candidate"
    case["episodes"][0]["episode_id"] = "future-episode-1"
    case["episodes"][0]["input_evidence_ids"] = [
        "future-red", "future-pass",
    ]
    case["episodes"][0]["candidate_refs"][0]["candidate_id"] = \
        "future-candidate"
    case["episodes"][0]["reviewed_decision"][
        "reviewed_verification_evidence_ids"
    ] = ["future-pass"]
    validated = validate_case(case)
    assert validated.schema_version == "dra.evolution-case.v1"
    assert validated.case_id == "future-context-case"


def test_candidate_owned_evidence_requires_exact_subject_candidate() -> None:
    case = _case("strict-citation-consumer")
    evidence = next(
        item for item in case["evidence_refs"]
        if item["evidence_id"] == "strict-consumer-pr-75"
    )
    evidence["subject_candidate_id"] = "missing-candidate"
    with pytest.raises(
        LoopContractError, match="loop_evidence_ref_invalid"
    ):
        validate_case(case)


def test_precandidate_evidence_rejects_candidate_subject() -> None:
    case = _case("context-resolver-projection")
    case["evidence_refs"][0]["subject_candidate_id"] = \
        "context-projection-pr-123"
    with pytest.raises(
        LoopContractError, match="loop_evidence_ref_invalid"
    ):
        validate_case(case)


def test_origin_and_proof_kind_matrix_is_closed() -> None:
    case = _case("strict-citation-consumer")
    evidence = next(
        item for item in case["evidence_refs"]
        if item["evidence_id"] == "strict-consumer-pr-75"
    )
    evidence["origin_kind"] = "repository_audit"
    with pytest.raises(
        LoopContractError, match="loop_evidence_ref_invalid"
    ):
        validate_case(case)


@pytest.mark.parametrize(
    ("field_path", "value", "code"),
    [
        (("schema_version",), "dra.evolution-case.v2",
         "loop_case_invalid"),
        (("evidence_refs", 0, "proof_kind"), "new_kind",
         "loop_evidence_ref_invalid"),
        (("episodes", 0, "predecessor_episode_id"), "missing",
         "loop_episode_invalid"),
        (("episodes", 0, "candidate_refs", 0, "commit_sha"),
         "short", "loop_candidate_identity_invalid"),
        (("episodes", 0, "candidate_refs", 0, "tree_sha"),
         "short", "loop_candidate_identity_invalid"),
    ],
)
def test_unknown_kind_predecessor_and_identity_fail_closed(
    field_path, value, code
) -> None:
    case = _case("context-resolver-projection")
    set_nested(case, field_path, value)
    with pytest.raises(LoopContractError, match=code):
        validate_case(case)


@pytest.mark.parametrize(
    ("target", "code"),
    [
        ("evidence", "loop_evidence_ref_invalid"),
        ("candidate", "loop_candidate_identity_invalid"),
    ],
)
@pytest.mark.parametrize(
    "repository",
    [
        "http://example.com/repository",
        "https://user@example.com/repository",
        "https://example.com/repository?run=1",
        "https://example.com/repository#fragment",
        "https://example.com",
    ],
)
def test_repository_identity_is_inert_public_https(
    target, code, repository
) -> None:
    case = _case("context-resolver-projection")
    if target == "evidence":
        case["evidence_refs"][0]["repository"] = repository
    else:
        case["episodes"][0]["candidate_refs"][0]["repository"] = repository
    with pytest.raises(LoopContractError, match=code):
        validate_case(case)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda case: case["evidence_refs"].append(
                copy.deepcopy(case["evidence_refs"][0])
            ),
            "loop_evidence_ref_invalid",
        ),
        (
            lambda case: case["episodes"][0].__setitem__(
                "input_evidence_ids", ["missing-evidence"]
            ),
            "loop_episode_invalid",
        ),
        (
            lambda case: case["episodes"][0]["diagnosis"].__setitem__(
                "extra", True
            ),
            "loop_diagnosis_invalid",
        ),
        (
            lambda case: case["episodes"][0]["reviewed_decision"].__setitem__(
                "extra", True
            ),
            "loop_decision_invalid",
        ),
        (
            lambda case: case["evidence_refs"][0].__setitem__(
                "reviewed_summary", "Traceback: private"
            ),
            "loop_public_output_unsafe",
        ),
    ],
)
def test_case_reference_section_and_public_safety_fail_closed(
    mutation, code
) -> None:
    case = _case("context-resolver-projection")
    mutation(case)
    with pytest.raises(LoopContractError, match=code):
        validate_case(case)


def test_third_episode_must_reference_immediate_predecessor() -> None:
    case = _case("strict-citation-consumer")
    third = copy.deepcopy(case["episodes"][1])
    third["episode_id"] = "strict-citation-consumer-close-episode-3"
    third["predecessor_episode_id"] = case["episodes"][0]["episode_id"]
    case["episodes"].append(third)
    with pytest.raises(LoopContractError, match="loop_episode_invalid"):
        validate_case(case)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("candidate_verdict", "accepted"),
        ("loop_closure_status", "closed_accepted"),
        ("release_disposition", "rollback_recommended"),
    ],
)
def test_no_change_decision_axes_must_remain_coherent(field, value) -> None:
    case = _case("strict-citation-consumer")
    case["episodes"][1]["reviewed_decision"][field] = value
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)


def test_rollback_requires_earlier_accepted_candidate() -> None:
    case = _case("strict-citation-consumer")
    first = case["episodes"][0]["reviewed_decision"]
    first["candidate_verdict"] = "rejected"
    first["consumer_proof_status"] = "not_required"
    first["loop_closure_status"] = "closed_rejected"
    second = case["episodes"][1]["reviewed_decision"]
    second["consumer_proof_status"] = "rejected"
    second["loop_closure_status"] = "closed_rejected"
    second["release_disposition"] = "rollback_recommended"
    second["rollback_target"] = \
        "6a3020863fbaaf9d218420b7981150a5736b7fb8"
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)


@pytest.mark.parametrize(
    ("case_name", "consumer_status", "closure_status"),
    [
        (
            "context-resolver-projection",
            "not_required",
            "open_waiting_consumer",
        ),
        (
            "context-resolver-projection",
            "not_required",
            "open_waiting_evidence",
        ),
    ],
)
def test_change_decision_axes_must_remain_coherent(
    case_name: str,
    consumer_status: str,
    closure_status: str,
) -> None:
    case = _case(case_name)
    decision = case["episodes"][0]["reviewed_decision"]
    decision["consumer_proof_status"] = consumer_status
    decision["loop_closure_status"] = closure_status
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)


@pytest.mark.parametrize(
    ("consumer_status", "closure_status"),
    [
        ("accepted", "closed_rejected"),
        ("pending", "open_waiting_consumer"),
    ],
)
def test_no_change_consumer_and_closure_axes_must_remain_coherent(
    consumer_status: str,
    closure_status: str,
) -> None:
    case = _case("strict-citation-consumer")
    decision = case["episodes"][1]["reviewed_decision"]
    decision["consumer_proof_status"] = consumer_status
    decision["loop_closure_status"] = closure_status
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)
