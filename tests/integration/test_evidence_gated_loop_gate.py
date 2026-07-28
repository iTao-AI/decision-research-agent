from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys

import pytest

import scripts.evidence_gated_loop_gate as gate
from scripts.evidence_gated_loop_contracts import (
    CASES_ROOT,
    PROJECT_ROOT,
    canonical_json_bytes,
    load_case_file,
    load_registry,
)
from scripts.evidence_gated_loop_profiles import VerificationResult


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


def test_registry_case_count_order_and_path_identity_are_exact() -> None:
    registry = load_registry()
    cases = tuple(
        load_case_file(PROJECT_ROOT / path) for path in registry.case_paths
    )
    gate.validate_kernel_inputs(registry, cases)
    with pytest.raises(Exception, match="loop_case_invalid"):
        gate.validate_kernel_inputs(registry, cases[:-1])


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
    markdown = gate.render_markdown(deterministic_report)
    assert "provider-free offline verification" in markdown
    assert "Release disposition: `hold`" in markdown
    assert "live-provider strict success" in markdown


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
    case = load_case_file(CASES_ROOT / "strict-citation-consumer.json")
    first, second = case.episodes
    assert first.action.kind == "change"
    assert first.reviewed_decision.candidate_verdict == "accepted"
    assert first.reviewed_decision.consumer_proof_status == "pending"
    producer = first.candidate_refs[0]
    assert producer.commit_sha == "01ba21f2996769e68cbc88f4bb0596740df27f6b"
    assert producer.tree_sha == "06e5282414d3801b11040bba735dd107105e8a30"
    assert second.predecessor_episode_id == first.episode_id
    assert second.action.kind == "no_change"
    assert second.reviewed_decision.consumer_proof_status == "accepted"
    assert second.reviewed_decision.loop_closure_status == "closed_no_change"


def test_reference_case_git_identities_are_exact() -> None:
    context = load_case_file(CASES_ROOT / "context-resolver-projection.json")
    evaluation = load_case_file(CASES_ROOT / "evaluation-sensitivity.json")
    strict = load_case_file(CASES_ROOT / "strict-citation-consumer.json")
    assert context.episodes[0].candidate_refs[0].commit_sha == (
        "2c50f233c2cc1df4fe2818551e95ab98cd61ede5"
    )
    assert evaluation.episodes[0].candidate_refs[0].tree_sha == (
        "d6b0dd3a0911125795eb7146bcd659c99233067d"
    )
    assert strict.episodes[0].candidate_refs[0].tree_sha == (
        "06e5282414d3801b11040bba735dd107105e8a30"
    )


def test_committed_json_and_markdown_match_fresh_validated_build(
    deterministic_report,
) -> None:
    assert gate.serialize_report(deterministic_report) == (
        gate.BASELINE_JSON_PATH.read_bytes()
    )
    assert gate.render_markdown(deterministic_report).encode("utf-8") == (
        gate.BASELINE_MARKDOWN_PATH.read_bytes()
    )


def test_two_builds_are_byte_identical(
    deterministic_report, monkeypatch
) -> None:
    monkeypatch.setattr(
        gate,
        "run_required_profiles",
        lambda registry, **kwargs: _passing_profile_results(),
    )
    second = gate.build_report()
    assert gate.serialize_report(deterministic_report) == gate.serialize_report(
        second
    )


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
