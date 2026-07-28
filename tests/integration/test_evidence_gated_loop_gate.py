from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.evidence_gated_loop_gate as gate
import scripts.evidence_gated_loop_profiles as profiles
from scripts.evidence_gated_loop_contracts import (
    CASES_ROOT,
    MAX_REPORT_BYTES,
    PROJECT_ROOT,
    REGISTRY_PATH,
    LoopContractError,
    canonical_json_bytes,
    load_case_file,
    load_registry,
    validate_case,
    validate_registry,
)
from scripts.evidence_gated_loop_gate import (
    BASELINE_JSON_PATH,
    BASELINE_MARKDOWN_PATH,
    STABLE_ERROR_CODES,
    LoopGateError,
    build_report,
    compare_artifacts,
    main,
    render_markdown,
    serialize_report,
    validate_kernel_inputs,
    validate_report,
    write_artifacts_recoverably,
)
from scripts.evidence_gated_loop_profiles import (
    LoopProfileError,
    VerificationResult,
)


def _case(name: str) -> dict[str, object]:
    path = CASES_ROOT / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _passing_profile_results() -> tuple[VerificationResult, ...]:
    coverage = ["fail_to_pass", "retained", "safety_compatibility"]
    return tuple(
        VerificationResult(
            profile_id=profile_id,
            profile_version="1",
            provider_free=True,
            status="passed",
            coverage=coverage,
            diagnostic_code="loop_verification_passed",
        )
        for profile_id in (
            "context-resolver-coherence",
            "evaluation-sensitivity",
            "strict-citation-consumer",
        )
    )


@pytest.fixture
def deterministic_report(monkeypatch) -> dict[str, object]:
    monkeypatch.setattr(
        gate,
        "run_required_profiles",
        lambda registry, **kwargs: _passing_profile_results(),
    )
    return gate.build_report()


def test_report_keeps_record_candidate_and_closure_axes_separate(
    deterministic_report,
) -> None:
    assert deterministic_report["summary"] == {
        "accepted_candidate_count": 3,
        "case_count": 3,
        "closed_no_change_count": 1,
        "episode_count": 4,
        "need_more_evidence_count": 0,
        "record_status": "valid",
        "rejected_candidate_count": 0,
        "release_disposition": "hold",
    }
    assert "loop_outcome" not in json.dumps(deterministic_report)


def test_report_binds_registry_case_hashes_and_profile_results(
    deterministic_report,
) -> None:
    assert deterministic_report["registry"]["sha256"] == hashlib.sha256(
        canonical_json_bytes(deterministic_report["registry"]["value"])
    ).hexdigest()
    assert [item["value"]["case_id"] for item in deterministic_report["cases"]] == [
        "context-resolver-projection",
        "evaluation-sensitivity",
        "strict-citation-consumer",
    ]
    assert [
        item["status"] for item in deterministic_report["verification_results"]
    ] == ["passed", "passed", "passed"]
    assert [
        (
            item["profile_id"],
            item["profile_version"],
            item["coverage"],
        )
        for item in deterministic_report["verification_results"]
    ] == [
        (
            "context-resolver-coherence",
            "1",
            ["fail_to_pass", "retained", "safety_compatibility"],
        ),
        (
            "evaluation-sensitivity",
            "1",
            ["fail_to_pass", "retained", "safety_compatibility"],
        ),
        (
            "strict-citation-consumer",
            "1",
            ["fail_to_pass", "retained", "safety_compatibility"],
        ),
    ]


def test_registry_case_count_order_and_path_identity_are_exact() -> None:
    registry = load_registry()
    cases = tuple(
        load_case_file(PROJECT_ROOT / path) for path in registry.case_paths
    )
    with pytest.raises(LoopContractError, match="loop_case_invalid"):
        validate_kernel_inputs(registry, cases[:-1])
    with pytest.raises(LoopContractError, match="loop_case_invalid"):
        validate_kernel_inputs(registry, tuple(reversed(cases)))
    mutated = _case("context-resolver-projection")
    mutated["case_id"] = "different-case-id"
    mismatched = (validate_case(mutated), *cases[1:])
    with pytest.raises(LoopContractError, match="loop_case_invalid"):
        validate_kernel_inputs(registry, mismatched)


def test_two_renderings_are_byte_identical(deterministic_report) -> None:
    assert gate.serialize_report(deterministic_report) == gate.serialize_report(
        copy.deepcopy(deterministic_report)
    )
    assert gate.render_markdown(deterministic_report) == gate.render_markdown(
        copy.deepcopy(deterministic_report)
    )


def test_markdown_is_derived_only_from_validated_json(
    deterministic_report,
) -> None:
    markdown = render_markdown(deterministic_report)
    assert "provider-free offline verification" in markdown
    assert "Release disposition: `hold`" in markdown
    assert "live-provider strict success" in markdown
    unsafe = copy.deepcopy(deterministic_report)
    unsafe["cases"][0]["value"]["title"] = "/private/example/path"
    with pytest.raises(
        LoopGateError, match="loop_public_output_unsafe"
    ):
        render_markdown(unsafe)


@pytest.mark.parametrize("argv", [["--help"], ["build", "--help"]])
def test_cli_help_is_successful(argv, capsys) -> None:
    assert gate.main(argv) == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out
    assert captured.err == ""


def test_cli_shape_error_is_stable(capsys) -> None:
    assert gate.main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        '{"code":"loop_output_invalid","status":"invalid"}\n'
    )


def test_strict_case_preserves_change_then_no_change_lineage() -> None:
    case = load_case_file(
        CASES_ROOT / "strict-citation-consumer.json"
    )
    first, second = case.episodes
    assert first.action.kind == "change"
    assert first.reviewed_decision.candidate_verdict == "accepted"
    assert first.reviewed_decision.consumer_proof_status == "pending"
    producer = first.candidate_refs[0]
    assert producer.commit_sha == \
        "01ba21f2996769e68cbc88f4bb0596740df27f6b"
    assert producer.tree_sha == \
        "06e5282414d3801b11040bba735dd107105e8a30"
    assert producer.capability_identity is not None
    assert producer.capability_identity.model_dump() == {
        "profile_id": "generic-strict-citation",
        "profile_version": "1",
        "proof_schema": "dra.strict-citation-profile.v1",
    }
    assert second.predecessor_episode_id == first.episode_id
    assert second.action.kind == "no_change"
    assert second.reviewed_decision.candidate_verdict == "not_applicable"
    assert second.reviewed_decision.consumer_proof_status == "accepted"
    assert second.reviewed_decision.loop_closure_status == "closed_no_change"
    consumer = next(
        item for item in case.evidence_refs
        if item.evidence_id == "strict-consumer-pr-75"
    )
    assert consumer.commit_sha == \
        "95cce4f28357150450c7f87105adcb47abf1a15d"
    assert consumer.tree_sha == \
        "7e310124de9c7d081723eee5b42c152a258b0919"
    assert consumer.locator == (
        "PR #75 merge-SHA run 30257237706 with successful python, "
        "frontend, and compose jobs"
    )
    assert "live-provider" not in consumer.claim_scope


def test_reference_case_git_identities_are_exact() -> None:
    context = load_case_file(
        CASES_ROOT / "context-resolver-projection.json"
    )
    evaluation = load_case_file(
        CASES_ROOT / "evaluation-sensitivity.json"
    )
    strict = load_case_file(
        CASES_ROOT / "strict-citation-consumer.json"
    )
    context_evidence = {
        item.evidence_id: item for item in context.evidence_refs
    }
    evaluation_evidence = {
        item.evidence_id: item for item in evaluation.evidence_refs
    }
    strict_evidence = {
        item.evidence_id: item for item in strict.evidence_refs
    }
    observed = [
        (
            context_evidence["context-red"].commit_sha,
            context_evidence["context-red"].tree_sha,
            context.episodes[0].candidate_refs[0].commit_sha,
            context.episodes[0].candidate_refs[0].tree_sha,
        ),
        (
            evaluation_evidence["evaluator-gap"].commit_sha,
            evaluation_evidence["evaluator-gap"].tree_sha,
            evaluation.episodes[0].candidate_refs[0].commit_sha,
            evaluation.episodes[0].candidate_refs[0].tree_sha,
        ),
        (
            strict_evidence["strict-live-25-0"].commit_sha,
            strict_evidence["strict-live-25-0"].tree_sha,
            strict.episodes[0].candidate_refs[0].commit_sha,
            strict.episodes[0].candidate_refs[0].tree_sha,
        ),
    ]
    assert observed == [
        (
            "2dadae56f038790f66c4c3af05b7bae10d8e0462",
            "1c27d38370cd9ecbb04b77630b75df9b0c4d46f1",
            "2c50f233c2cc1df4fe2818551e95ab98cd61ede5",
            "8da21672e9fd63352e9bc15365818f7edd12d106",
        ),
        (
            "8efc7d5a39cc515e15f7ea9b29901f7e6e064ae9",
            "56fb2e148da3b4026f5ec430b94336e5e484cb85",
            "6a3020863fbaaf9d218420b7981150a5736b7fb8",
            "d6b0dd3a0911125795eb7146bcd659c99233067d",
        ),
        (
            "95cce4f28357150450c7f87105adcb47abf1a15d",
            "7e310124de9c7d081723eee5b42c152a258b0919",
            "01ba21f2996769e68cbc88f4bb0596740df27f6b",
            "06e5282414d3801b11040bba735dd107105e8a30",
        ),
    ]
    assert (
        evaluation_evidence["evaluator-red"].commit_sha,
        evaluation_evidence["evaluator-red"].tree_sha,
    ) == (
        "8efc7d5a39cc515e15f7ea9b29901f7e6e064ae9",
        "56fb2e148da3b4026f5ec430b94336e5e484cb85",
    )
    assert (
        evaluation_evidence["evaluator-candidate-pass"].commit_sha,
        evaluation_evidence["evaluator-candidate-pass"].tree_sha,
    ) == (
        evaluation.episodes[0].candidate_refs[0].commit_sha,
        evaluation.episodes[0].candidate_refs[0].tree_sha,
    )


def test_committed_json_and_markdown_match_fresh_validated_build(
    deterministic_report,
) -> None:
    assert serialize_report(deterministic_report) \
        == BASELINE_JSON_PATH.read_bytes()
    assert render_markdown(deterministic_report).encode("utf-8") \
        == BASELINE_MARKDOWN_PATH.read_bytes()


def test_two_builds_are_byte_identical(
    deterministic_report,
) -> None:
    second = gate.build_report()
    assert serialize_report(deterministic_report) \
        == serialize_report(second) \
        == BASELINE_JSON_PATH.read_bytes()
    assert render_markdown(deterministic_report).encode("utf-8") \
        == render_markdown(second).encode("utf-8") \
        == BASELINE_MARKDOWN_PATH.read_bytes()


def test_direct_script_help_uses_repository_import_path() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/evidence_gated_loop_gate.py", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "usage:" in completed.stdout
    assert completed.stderr == ""

def test_frozen_generic_downstream_fixture_rejects_strict_profile() -> None:
    from scripts.downstream_consumer_contract import (
        ContractValidationError,
        build_fixture_bundle,
        validate_fixture_bundle,
    )

    payload = build_fixture_bundle()
    payload["cases"][0]["profile_id"] = "generic-strict-citation"
    with pytest.raises(ContractValidationError, match="contract_schema_invalid"):
        validate_fixture_bundle(payload)


@pytest.mark.parametrize(
    ("dispositions", "expected"),
    [
        (
            [
                "eligible_for_separate_release_review",
                "eligible_for_separate_release_review",
            ],
            "eligible_for_separate_release_review",
        ),
        (
            ["eligible_for_separate_release_review", "hold"],
            "hold",
        ),
        (
            ["hold", "rollback_recommended"],
            "rollback_recommended",
        ),
    ],
)
def test_report_release_disposition_uses_terminal_case_priority(
    dispositions, expected
) -> None:
    assert gate._derive_release_disposition(dispositions) == expected


def test_historical_hold_does_not_freeze_later_terminal_eligibility() -> None:
    values = [
        _case("context-resolver-projection"),
        _case("evaluation-sensitivity"),
        _case("strict-citation-consumer"),
    ]
    values[0]["episodes"][0]["reviewed_decision"][
        "release_disposition"
    ] = "eligible_for_separate_release_review"
    values[1]["episodes"][0]["reviewed_decision"][
        "release_disposition"
    ] = "eligible_for_separate_release_review"
    values[2]["episodes"][1]["reviewed_decision"][
        "release_disposition"
    ] = "eligible_for_separate_release_review"
    cases = tuple(validate_case(value) for value in values)
    assert values[2]["episodes"][0]["reviewed_decision"][
        "release_disposition"
    ] == "hold"
    assert gate._derive_release_disposition_from_cases(cases) \
        == "eligible_for_separate_release_review"


@pytest.mark.parametrize(
    ("kind", "code"),
    [
        ("case", "loop_case_invalid"),
        ("evidence", "loop_evidence_ref_invalid"),
        ("episode", "loop_episode_invalid"),
        ("candidate", "loop_candidate_identity_invalid"),
    ],
)
def test_cross_case_duplicate_identities_fail_closed(kind, code) -> None:
    values = [
        _case("context-resolver-projection"),
        _case("evaluation-sensitivity"),
        _case("strict-citation-consumer"),
    ]
    if kind == "case":
        values[1]["case_id"] = values[0]["case_id"]
    elif kind == "evidence":
        duplicate = values[0]["evidence_refs"][0]["evidence_id"]
        old = values[1]["evidence_refs"][0]["evidence_id"]
        values[1]["evidence_refs"][0]["evidence_id"] = duplicate
        values[1]["episodes"][0]["input_evidence_ids"] = [
            duplicate if item == old else item
            for item in values[1]["episodes"][0]["input_evidence_ids"]
        ]
    elif kind == "episode":
        values[1]["episodes"][0]["episode_id"] = \
            values[0]["episodes"][0]["episode_id"]
    else:
        old_candidate_id = values[1]["episodes"][0][
            "candidate_refs"
        ][0]["candidate_id"]
        duplicate_candidate_id = values[0]["episodes"][0][
            "candidate_refs"
        ][0]["candidate_id"]
        values[1]["episodes"][0]["candidate_refs"][0]["candidate_id"] = \
            duplicate_candidate_id
        for evidence in values[1]["evidence_refs"]:
            if evidence["subject_candidate_id"] == old_candidate_id:
                evidence["subject_candidate_id"] = duplicate_candidate_id
    cases = tuple(validate_case(value) for value in values)
    with pytest.raises(LoopContractError, match=code):
        validate_kernel_inputs(load_registry(), cases)


def test_unknown_verification_profile_fails_closed_before_execution(
    monkeypatch,
) -> None:
    values = [
        _case("context-resolver-projection"),
        _case("evaluation-sensitivity"),
        _case("strict-citation-consumer"),
    ]
    values[0]["episodes"][0]["verification_profile_ref"] = {
        "profile_id": "unknown",
        "profile_version": "1",
    }
    calls = []
    monkeypatch.setattr(
        profiles,
        "run_verification_profile",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    with pytest.raises(LoopContractError,
                       match="loop_verification_profile_invalid"):
        validate_kernel_inputs(
            load_registry(),
            tuple(validate_case(value) for value in values),
        )
    assert calls == []


def test_swapping_two_known_episode_profiles_fails_before_execution(
    monkeypatch,
) -> None:
    values = [
        _case("context-resolver-projection"),
        _case("evaluation-sensitivity"),
        _case("strict-citation-consumer"),
    ]
    first = values[0]["episodes"][0]["verification_profile_ref"]
    second = values[1]["episodes"][0]["verification_profile_ref"]
    values[0]["episodes"][0]["verification_profile_ref"] = second
    values[1]["episodes"][0]["verification_profile_ref"] = first
    calls = []
    monkeypatch.setattr(
        profiles,
        "run_verification_profile",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    with pytest.raises(
        LoopContractError, match="loop_verification_profile_invalid"
    ):
        validate_kernel_inputs(
            load_registry(),
            tuple(validate_case(value) for value in values),
        )
    assert calls == []


def test_existing_kind_case_requires_versioned_code_owned_binding(
    monkeypatch,
) -> None:
    values = {
        case_id: _case(case_id)
        for case_id in (
            "context-resolver-projection",
            "evaluation-sensitivity",
            "strict-citation-consumer",
        )
    }
    context = values["context-resolver-projection"]
    context["episodes"][0]["verification_profile_ref"][
        "profile_version"
    ] = "2"
    future = copy.deepcopy(context)
    future["case_id"] = "future-context-case"
    future["case_version"] = "1"
    future["evidence_refs"][0]["evidence_id"] = "future-context-red"
    future["evidence_refs"][1]["evidence_id"] = "future-context-pass"
    future["evidence_refs"][1]["subject_candidate_id"] = \
        "future-context-candidate"
    episode = future["episodes"][0]
    episode["episode_id"] = "future-context-episode-1"
    episode["input_evidence_ids"] = [
        "future-context-red", "future-context-pass",
    ]
    episode["candidate_refs"][0]["candidate_id"] = \
        "future-context-candidate"
    episode["reviewed_decision"]["reviewed_verification_evidence_ids"] = [
        "future-context-pass"
    ]

    registry_value = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    registry_value["case_paths"].append(
        "benchmarks/evidence-gated-loop-v1/cases/future-context-case.json"
    )
    registry_value["case_paths"].sort()
    registry_value["verification_profiles"][0]["profile_version"] = "2"
    registry = validate_registry(registry_value)
    cases_by_id = {
        **values,
        "future-context-case": future,
    }
    cases = tuple(
        validate_case(cases_by_id[Path(path).stem])
        for path in registry.case_paths
    )

    with pytest.raises(
        LoopContractError, match="loop_verification_profile_invalid"
    ):
        validate_kernel_inputs(registry, cases)

    current = gate.PROFILE_REGISTRY[
        ("context-resolver-coherence", "1")
    ]
    reviewed = dataclasses.replace(
        current,
        profile_version="2",
        episode_bindings=(
            *current.episode_bindings,
            ("future-context-case", "future-context-episode-1"),
        ),
    )
    updated_profiles = dict(gate.PROFILE_REGISTRY)
    del updated_profiles[("context-resolver-coherence", "1")]
    updated_profiles[("context-resolver-coherence", "2")] = reviewed
    monkeypatch.setattr(gate, "PROFILE_REGISTRY", updated_profiles)

    validate_kernel_inputs(registry, cases)


def test_declared_unused_unknown_profile_fails_closed() -> None:
    value = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    value["verification_profiles"].append(
        {"profile_id": "zz-unknown", "profile_version": "1"}
    )
    registry = validate_registry(value)
    cases = tuple(
        load_case_file(PROJECT_ROOT / path)
        for path in registry.case_paths
    )
    with pytest.raises(LoopContractError,
                       match="loop_verification_profile_invalid"):
        validate_kernel_inputs(registry, cases)


def test_registered_case_symlink_fails_before_case_parse(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.json"
    outside.write_bytes(
        canonical_json_bytes(_case("context-resolver-projection"))
    )
    cases_root = tmp_path / "benchmarks/evidence-gated-loop-v1/cases"
    cases_root.mkdir(parents=True)
    link = cases_root / "context-resolver-projection.json"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    with pytest.raises(LoopContractError, match="loop_case_invalid"):
        gate._resolve_registered_case_path(
            "benchmarks/evidence-gated-loop-v1/cases/"
            "context-resolver-projection.json",
            project_root=tmp_path,
        )


@pytest.mark.parametrize(
    "verdict", ["accepted", "rejected", "need_more_evidence"]
)
def test_failed_current_profile_invalidates_every_report(
    monkeypatch, verdict
) -> None:
    cases = [
        _case("context-resolver-projection"),
        _case("evaluation-sensitivity"),
        _case("strict-citation-consumer"),
    ]
    decision = cases[0]["episodes"][0]["reviewed_decision"]
    decision["candidate_verdict"] = verdict
    if verdict == "rejected":
        candidate = cases[0]["episodes"][0]["candidate_refs"][0]
        candidate["candidate_id"] = "reviewed-failed-candidate"
        candidate["commit_sha"] = "1" * 40
        candidate["tree_sha"] = "2" * 40
        evidence = cases[0]["evidence_refs"][1]
        evidence["proof_kind"] = "reviewed_candidate_regression"
        evidence["subject_candidate_id"] = candidate["candidate_id"]
        evidence["commit_sha"] = candidate["commit_sha"]
        evidence["tree_sha"] = candidate["tree_sha"]
        evidence["locator"] = "synthetic reviewed failed candidate fixture"
        evidence["reviewed_summary"] = (
            "A bounded synthetic contract fixture records a reviewed "
            "failed candidate verification status."
        )
        evidence["claim_scope"] = \
            "contract validation for a reviewed failed candidate record"
        decision["reviewed_candidate_verification_status"] = "failed"
        decision["reviewed_verification_evidence_ids"] = [
            "context-candidate-pass"
        ]
        decision["loop_closure_status"] = "closed_rejected"
    elif verdict == "need_more_evidence":
        candidate = cases[0]["episodes"][0]["candidate_refs"][0]
        candidate["candidate_id"] = "reviewed-inconclusive-candidate"
        candidate["commit_sha"] = "1" * 40
        candidate["tree_sha"] = "2" * 40
        evidence = cases[0]["evidence_refs"][1]
        evidence["proof_kind"] = \
            "reviewed_candidate_verification_inconclusive"
        evidence["origin_kind"] = "verification_gap"
        evidence["subject_candidate_id"] = candidate["candidate_id"]
        evidence["commit_sha"] = candidate["commit_sha"]
        evidence["tree_sha"] = candidate["tree_sha"]
        evidence["locator"] = \
            "synthetic reviewed inconclusive candidate fixture"
        evidence["reviewed_summary"] = (
            "A bounded synthetic contract fixture records a reviewed "
            "inconclusive candidate verification status."
        )
        evidence["claim_scope"] = (
            "contract validation for a reviewed inconclusive "
            "candidate record"
        )
        decision["reviewed_candidate_verification_status"] = "inconclusive"
        decision["reviewed_verification_evidence_ids"] = [
            "context-candidate-pass"
        ]
        decision["loop_closure_status"] = "open_waiting_evidence"
    registry = load_registry()
    validated_cases = tuple(validate_case(value) for value in cases)
    monkeypatch.setattr(
        gate, "_load_kernel_inputs", lambda: (registry, validated_cases)
    )
    def fail_profiles(*args, **kwargs):
        raise LoopProfileError("loop_verification_failed")
    monkeypatch.setattr(gate, "run_required_profiles", fail_profiles)
    with pytest.raises(LoopGateError, match="loop_verification_failed"):
        build_report()


def test_report_enforces_declared_canonical_byte_bound(
    deterministic_report, monkeypatch
) -> None:
    monkeypatch.setattr(gate, "MAX_REPORT_BYTES", 64)
    with pytest.raises(LoopGateError, match="loop_report_invalid"):
        validate_report(deterministic_report)


@pytest.mark.parametrize(
    "missing",
    ["fail_to_pass", "retained", "safety_compatibility"],
)
def test_accepted_report_requires_all_verification_coverage(
    monkeypatch, missing
) -> None:
    results = list(_passing_profile_results())
    first = results[0].model_copy(
        update={
            "coverage": [
                item for item in results[0].coverage if item != missing
            ]
        }
    )
    results[0] = first
    monkeypatch.setattr(
        gate,
        "run_required_profiles",
        lambda registry, **kwargs: tuple(results),
    )
    with pytest.raises(LoopGateError,
                       match="loop_verification_profile_invalid"):
        build_report()


def test_build_refuses_baseline_alias_and_identical_outputs(
    deterministic_report, tmp_path
) -> None:
    markdown = render_markdown(deterministic_report)
    with pytest.raises(LoopGateError, match="loop_output_invalid"):
        write_artifacts_recoverably(
            deterministic_report,
            markdown,
            json_output=BASELINE_JSON_PATH,
            markdown_output=tmp_path / "report.md",
        )
    same = tmp_path / "same"
    with pytest.raises(LoopGateError, match="loop_output_invalid"):
        write_artifacts_recoverably(
            deterministic_report,
            markdown,
            json_output=same,
            markdown_output=same,
        )


def test_build_refuses_symlink_output_without_mutating_target(
    deterministic_report, tmp_path
) -> None:
    target = tmp_path / "target.json"
    target.write_bytes(b"unchanged\n")
    link = tmp_path / "report.json"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    with pytest.raises(LoopGateError, match="loop_output_invalid"):
        write_artifacts_recoverably(
            deterministic_report,
            render_markdown(deterministic_report),
            json_output=link,
            markdown_output=tmp_path / "report.md",
        )
    assert target.read_bytes() == b"unchanged\n"
    assert link.is_symlink()


@pytest.mark.parametrize(
    "json_output_factory",
    [
        lambda root: root / "missing-parent/report.json",
        lambda root: root,
    ],
)
def test_build_refuses_missing_parent_and_directory_target(
    deterministic_report, tmp_path, json_output_factory
) -> None:
    with pytest.raises(LoopGateError, match="loop_output_invalid"):
        write_artifacts_recoverably(
            deterministic_report,
            render_markdown(deterministic_report),
            json_output=json_output_factory(tmp_path),
            markdown_output=tmp_path / "report.md",
        )


def test_compare_rejects_noncanonical_json_markdown_drift_and_byte_drift(
    deterministic_report
) -> None:
    candidate_json = serialize_report(deterministic_report)
    candidate_markdown = render_markdown(deterministic_report)
    pretty_json = (
        json.dumps(deterministic_report, indent=2).encode("utf-8") + b"\n"
    )
    with pytest.raises(LoopGateError, match="loop_baseline_invalid"):
        compare_artifacts(
            deterministic_report,
            candidate_markdown,
            pretty_json,
            candidate_markdown.encode("utf-8"),
        )
    with pytest.raises(LoopGateError, match="loop_baseline_invalid"):
        compare_artifacts(
            deterministic_report,
            candidate_markdown,
            candidate_json,
            (candidate_markdown + "\n").encode("utf-8"),
        )
    drifted = copy.deepcopy(deterministic_report)
    drifted["cases"][0]["value"]["title"] = \
        "Context resolver projection reviewed lineage"
    drifted["cases"][0]["sha256"] = hashlib.sha256(
        canonical_json_bytes(drifted["cases"][0]["value"])
    ).hexdigest()
    with pytest.raises(LoopGateError, match="loop_baseline_invalid"):
        compare_artifacts(
            deterministic_report,
            candidate_markdown,
            serialize_report(drifted),
            render_markdown(drifted).encode("utf-8"),
        )


def test_second_replace_failure_restores_first_and_leaves_no_temps(
    deterministic_report, tmp_path, monkeypatch
) -> None:
    json_output = tmp_path / "report.json"
    markdown_output = tmp_path / "report.md"
    json_output.write_bytes(b"old-json\n")
    markdown_output.write_bytes(b"old-markdown\n")
    actual_replace = os.replace
    calls = 0
    targets = []
    def fail_second(source, target):
        nonlocal calls
        calls += 1
        targets.append(Path(target))
        if calls == 2:
            raise OSError("private replace detail")
        actual_replace(source, target)
    monkeypatch.setattr(os, "replace", fail_second)
    with pytest.raises(LoopGateError, match="loop_output_invalid"):
        write_artifacts_recoverably(
            deterministic_report,
            render_markdown(deterministic_report),
            json_output=json_output,
            markdown_output=markdown_output,
        )
    assert json_output.read_bytes() == b"old-json\n"
    assert markdown_output.read_bytes() == b"old-markdown\n"
    assert targets[:2] == [markdown_output, json_output]
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "report.json", "report.md",
    ]


def test_second_replace_failure_removes_new_first_when_no_prior_file(
    deterministic_report, tmp_path, monkeypatch
) -> None:
    json_output = tmp_path / "report.json"
    markdown_output = tmp_path / "report.md"
    actual_replace = os.replace
    calls = 0
    def fail_second(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("private replace detail")
        actual_replace(source, target)
    monkeypatch.setattr(os, "replace", fail_second)
    with pytest.raises(LoopGateError, match="loop_output_invalid"):
        write_artifacts_recoverably(
            deterministic_report,
            render_markdown(deterministic_report),
            json_output=json_output,
            markdown_output=markdown_output,
        )
    assert not json_output.exists()
    assert not markdown_output.exists()
    assert list(tmp_path.iterdir()) == []


def test_oversized_existing_output_fails_before_mutation(
    deterministic_report, tmp_path
) -> None:
    json_output = tmp_path / "report.json"
    markdown_output = tmp_path / "report.md"
    json_output.write_bytes(b"x" * (MAX_REPORT_BYTES + 1))
    markdown_output.write_bytes(b"old-markdown\n")
    with pytest.raises(LoopGateError, match="loop_output_invalid"):
        write_artifacts_recoverably(
            deterministic_report,
            render_markdown(deterministic_report),
            json_output=json_output,
            markdown_output=markdown_output,
        )
    assert json_output.stat().st_size == MAX_REPORT_BYTES + 1
    assert markdown_output.read_bytes() == b"old-markdown\n"


def test_cli_error_matrix_has_one_safe_json_line(monkeypatch, capsys) -> None:
    for code in STABLE_ERROR_CODES:
        def fail_known(args, *, selected_code=code):
            raise LoopGateError(selected_code)
        monkeypatch.setattr(gate, "_run", fail_known)
        assert main(["check"]) == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == json.dumps(
            {"code": code, "status": "invalid"},
            ensure_ascii=False,
            separators=(",", ":"),
        ) + "\n"
    def fail_private(args):
        raise RuntimeError("private host detail")
    monkeypatch.setattr(gate, "_run", fail_private)
    assert main(["check"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == \
        '{"code":"loop_internal_error","status":"invalid"}\n'
    assert "private host detail" not in captured.err


def test_historical_red_and_executable_profiles_are_distinct(
    deterministic_report
) -> None:
    evidence = [
        ref for item in deterministic_report["cases"]
        for ref in item["value"]["evidence_refs"]
    ]
    assert any(ref["proof_kind"] == "reviewed_historical_red"
               for ref in evidence)
    assert all(
        result["status"] == "passed"
        for result in deterministic_report["verification_results"]
    )
    assert "historical RED was re-executed" not in \
        json.dumps(deterministic_report)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda strict: strict["value"]["episodes"][0][
                "candidate_refs"
            ][0].__setitem__("capability_identity", None),
            "loop_candidate_identity_invalid",
        ),
        (
            lambda strict: next(
                item for item in strict["value"]["evidence_refs"]
                if item["evidence_id"] == "strict-consumer-pr-75"
            ).__setitem__("commit_sha", "1" * 40),
            "loop_evidence_ref_invalid",
        ),
        (
            lambda strict: next(
                item for item in strict["value"]["evidence_refs"]
                if item["evidence_id"] == "strict-consumer-pr-75"
            ).__setitem__("tree_sha", "2" * 40),
            "loop_evidence_ref_invalid",
        ),
        (
            lambda strict: next(
                item for item in strict["value"]["evidence_refs"]
                if item["evidence_id"] == "strict-consumer-pr-75"
            ).__setitem__("locator", "PR #75 replacement locator"),
            "loop_evidence_ref_invalid",
        ),
    ],
)
def test_reference_identity_drift_fails_closed_in_report(
    deterministic_report,
    mutation,
    code,
) -> None:
    report = copy.deepcopy(deterministic_report)
    strict = next(
        item for item in report["cases"]
        if item["value"]["case_id"] == "strict-citation-consumer"
    )
    mutation(strict)
    strict["sha256"] = hashlib.sha256(
        canonical_json_bytes(strict["value"])
    ).hexdigest()
    with pytest.raises(LoopGateError, match=code):
        validate_report(report)


@pytest.mark.parametrize("failure_at", ["write", "flush", "fsync"])
def test_stage_failure_cleans_task_created_temp_and_keeps_public_error(
    deterministic_report,
    tmp_path,
    monkeypatch,
    failure_at,
) -> None:
    actual_named_temporary_file = gate.tempfile.NamedTemporaryFile

    class FailingStage:
        def __init__(self, handle) -> None:
            self._handle = handle
            self.name = handle.name

        def write(self, value):
            if failure_at == "write":
                raise OSError("private write detail")
            return self._handle.write(value)

        def flush(self):
            if failure_at == "flush":
                raise OSError("private flush detail")
            return self._handle.flush()

        def fileno(self):
            return self._handle.fileno()

        def close(self):
            return self._handle.close()

    def failing_named_temporary_file(*args, **kwargs):
        return FailingStage(actual_named_temporary_file(*args, **kwargs))

    monkeypatch.setattr(
        gate.tempfile,
        "NamedTemporaryFile",
        failing_named_temporary_file,
    )
    if failure_at == "fsync":
        monkeypatch.setattr(
            gate.os,
            "fsync",
            lambda file_descriptor: (_ for _ in ()).throw(
                OSError("private fsync detail")
            ),
        )

    with pytest.raises(LoopGateError, match="loop_output_invalid"):
        write_artifacts_recoverably(
            deterministic_report,
            render_markdown(deterministic_report),
            json_output=tmp_path / "report.json",
            markdown_output=tmp_path / "report.md",
        )
    assert list(tmp_path.iterdir()) == []
