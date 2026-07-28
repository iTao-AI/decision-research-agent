from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Annotated, Any, Literal, Mapping, Sequence

from pydantic import Field, StringConstraints, ValidationError

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.evidence_gated_loop_contracts import (
    MAX_REPORT_BYTES,
    PROJECT_ROOT,
    REGISTRY_PATH,
    REQUIRED_NON_CLAIMS,
    EvolutionCase,
    LoopBoundedReadError,
    LoopContractError,
    LoopRegistry,
    RegistryLimits,
    _StrictModel,
    canonical_json_bytes,
    load_case_file,
    load_registry,
    read_bounded_bytes,
    validate_case,
    validate_public_projection,
    validate_registry,
)
from scripts.evidence_gated_loop_profiles import (
    PROFILE_REGISTRY,
    LoopProfileError,
    VerificationResult,
    run_required_profiles,
)


BASELINE_JSON_PATH = (
    PROJECT_ROOT / "docs/evidence/evidence-gated-loop-kernel-v1.json"
)
BASELINE_MARKDOWN_PATH = (
    PROJECT_ROOT / "docs/evidence/evidence-gated-loop-kernel-v1.md"
)
STABLE_ERROR_CODES = (
    "loop_registry_invalid",
    "loop_case_invalid",
    "loop_evidence_ref_invalid",
    "loop_episode_invalid",
    "loop_diagnosis_invalid",
    "loop_action_invalid",
    "loop_candidate_identity_invalid",
    "loop_verification_profile_invalid",
    "loop_verification_failed",
    "loop_decision_invalid",
    "loop_report_invalid",
    "loop_baseline_invalid",
    "loop_output_invalid",
    "loop_public_output_unsafe",
    "loop_internal_error",
)
_REFERENCE_CANDIDATE_IDENTITIES = {
    "context-resolver-projection": {
        "context-projection-pr-123": (
            "https://github.com/iTao-AI/decision-research-agent",
            "2c50f233c2cc1df4fe2818551e95ab98cd61ede5",
            "8da21672e9fd63352e9bc15365818f7edd12d106",
            None,
            "program_harness",
            "evaluation_proof",
            "2dadae56f038790f66c4c3af05b7bae10d8e0462",
        ),
    },
    "evaluation-sensitivity": {
        "evaluation-sensitivity-pr-128": (
            "https://github.com/iTao-AI/decision-research-agent",
            "6a3020863fbaaf9d218420b7981150a5736b7fb8",
            "d6b0dd3a0911125795eb7146bcd659c99233067d",
            None,
            "program_harness",
            "evaluation_proof",
            "8efc7d5a39cc515e15f7ea9b29901f7e6e064ae9",
        ),
    },
    "strict-citation-consumer": {
        "strict-citation-pr-129": (
            "https://github.com/iTao-AI/decision-research-agent",
            "01ba21f2996769e68cbc88f4bb0596740df27f6b",
            "06e5282414d3801b11040bba735dd107105e8a30",
            {
                "profile_id": "generic-strict-citation",
                "profile_version": "1",
                "proof_schema": "dra.strict-citation-profile.v1",
            },
            "program_harness",
            "runtime_harness",
            "6a3020863fbaaf9d218420b7981150a5736b7fb8",
        ),
    },
}
_REFERENCE_EVIDENCE_IDENTITIES = {
    "context-resolver-projection": {
        "context-red": (
            "https://github.com/iTao-AI/decision-research-agent",
            "2dadae56f038790f66c4c3af05b7bae10d8e0462",
            "1c27d38370cd9ecbb04b77630b75df9b0c4d46f1",
            "PR #122 provider-free context regression",
            "reviewed_historical_red",
            None,
            "repository_audit",
            "PR #122 preserved the reviewed provider-free regression surface "
            "later used to expose context projection false greens.",
            "incompatible resolver and persisted-state combinations were not "
            "yet rejected by the retained projection test set",
            True,
        ),
        "context-candidate-pass": (
            "https://github.com/iTao-AI/decision-research-agent",
            "2c50f233c2cc1df4fe2818551e95ab98cd61ede5",
            "8da21672e9fd63352e9bc15365818f7edd12d106",
            "PR #123 reviewed provider-free verification and merge surface",
            "reviewed_candidate_verification_passed",
            "context-projection-pr-123",
            "repository_audit",
            "The reviewed PR #123 verification and merge surface passed the "
            "context regression and retained checks for the exact candidate.",
            "exact candidate passed reviewed provider-free context projection "
            "verification",
            True,
        ),
    },
    "evaluation-sensitivity": {
        "evaluator-gap": (
            "https://github.com/iTao-AI/decision-research-agent",
            "8efc7d5a39cc515e15f7ea9b29901f7e6e064ae9",
            "56fb2e148da3b4026f5ec430b94336e5e484cb85",
            "PR #128 review of pre-candidate main",
            "reviewed_verification_gap",
            None,
            "verification_gap",
            "Review found that pre-candidate healthy anchors alone did not "
            "prove that each responsible evaluator detected its declared "
            "failure dimension.",
            "healthy anchors alone did not prove sensitivity to each "
            "evaluator's declared failure dimension",
            True,
        ),
        "evaluator-red": (
            "https://github.com/iTao-AI/decision-research-agent",
            "8efc7d5a39cc515e15f7ea9b29901f7e6e064ae9",
            "56fb2e148da3b4026f5ec430b94336e5e484cb85",
            "PR #128 reviewed RED against pre-candidate main",
            "reviewed_historical_red",
            None,
            "repository_audit",
            "PR #128 recorded that pre-candidate main lacked "
            "one-dimensional post-traversal controls that distinguish "
            "responsible sensitivity from unrelated drift.",
            "responsible evaluators had to detect their fixed synthetic "
            "control while unrelated projections remained stable",
            True,
        ),
        "evaluator-candidate-pass": (
            "https://github.com/iTao-AI/decision-research-agent",
            "6a3020863fbaaf9d218420b7981150a5736b7fb8",
            "d6b0dd3a0911125795eb7146bcd659c99233067d",
            "PR #128 reviewed provider-free verification and merge surface",
            "reviewed_candidate_verification_passed",
            "evaluation-sensitivity-pr-128",
            "repository_audit",
            "The reviewed PR #128 verification and merge surface passed "
            "Evaluation Sensitivity v2 and retained checks for the exact "
            "candidate.",
            "exact candidate passed reviewed provider-free evaluator "
            "sensitivity verification",
            True,
        ),
    },
    "strict-citation-consumer": {
        "strict-live-25-0": (
            "https://github.com/iTao-AI/night-voyager",
            "95cce4f28357150450c7f87105adcb47abf1a15d",
            "7e310124de9c7d081723eee5b42c152a258b0919",
            "docs/decisions/0011-dra-v0-1-6-live-consumer-boundary.md "
            "reviewed 25 Evidence and zero cited summary",
            "reviewed_historical_red",
            None,
            "downstream_consumer",
            "The first governed live attempt retained 25 same-run Evidence "
            "rows, produced zero cited rows, and stopped before import.",
            "governed live attempt stopped before import with 25 same-run "
            "Evidence rows and zero cited rows",
            True,
        ),
        "strict-live-83-0": (
            "https://github.com/iTao-AI/night-voyager",
            "95cce4f28357150450c7f87105adcb47abf1a15d",
            "7e310124de9c7d081723eee5b42c152a258b0919",
            "docs/decisions/0011-dra-v0-1-6-live-consumer-boundary.md "
            "reviewed 83 Evidence and zero cited summary",
            "reviewed_historical_red",
            None,
            "downstream_consumer",
            "The second governed live attempt retained 83 same-run Evidence "
            "rows, produced zero cited rows, and stopped before import.",
            "governed live attempt stopped before import with 83 same-run "
            "Evidence rows and zero cited rows",
            True,
        ),
        "strict-candidate-pass": (
            "https://github.com/iTao-AI/decision-research-agent",
            "01ba21f2996769e68cbc88f4bb0596740df27f6b",
            "06e5282414d3801b11040bba735dd107105e8a30",
            "PR #129 reviewed tree with seven successful hosted checks",
            "reviewed_candidate_verification_passed",
            "strict-citation-pr-129",
            "repository_audit",
            "The reviewed PR #129 tree and hosted checks passed the strict "
            "producer verification surface for the exact candidate.",
            "exact strict producer candidate passed reviewed hosted "
            "verification before independent consumer proof",
            True,
        ),
        "strict-consumer-pr-75": (
            "https://github.com/iTao-AI/night-voyager",
            "95cce4f28357150450c7f87105adcb47abf1a15d",
            "7e310124de9c7d081723eee5b42c152a258b0919",
            "PR #75 merge-SHA run 30257237706 with successful python, "
            "frontend, and compose jobs",
            "independent_consumer_contract",
            "strict-citation-pr-129",
            "downstream_consumer",
            "Night Voyager PR #75 pinned the exact strict producer tuple and "
            "passed consumer-owned provider-free contract checks.",
            "exact producer tuple, zero-cited stop, reconciliation, and "
            "evaluation contracts passed consumer-owned provider-free checks",
            True,
        ),
    },
}


def _candidate_identity(value: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        value.get("repository"),
        value.get("commit_sha"),
        value.get("tree_sha"),
        value.get("capability_identity"),
        value.get("carrier"),
        value.get("change_surface"),
        value.get("predecessor_or_rollback_ref"),
    )


def _evidence_identity(value: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        value.get("repository"),
        value.get("commit_sha"),
        value.get("tree_sha"),
        value.get("locator"),
        value.get("proof_kind"),
        value.get("subject_candidate_id"),
        value.get("origin_kind"),
        value.get("reviewed_summary"),
        value.get("claim_scope"),
        value.get("public_safe"),
    )


def _validate_reference_identities(
    cases: Sequence[Mapping[str, Any]],
    *,
    require_complete: bool,
) -> None:
    for case in cases:
        case_id = case.get("case_id")
        expected_candidates = _REFERENCE_CANDIDATE_IDENTITIES.get(case_id)
        episodes = case.get("episodes")
        if expected_candidates is not None and isinstance(episodes, list):
            actual_candidates = {
                candidate.get("candidate_id"): _candidate_identity(candidate)
                for episode in episodes
                if isinstance(episode, Mapping)
                for candidate in episode.get("candidate_refs", [])
                if isinstance(candidate, Mapping)
                and candidate.get("candidate_id") in expected_candidates
            }
            if (
                (require_complete or actual_candidates)
                and actual_candidates != expected_candidates
            ):
                raise LoopContractError("loop_candidate_identity_invalid")
        expected_evidence = _REFERENCE_EVIDENCE_IDENTITIES.get(case_id)
        evidence_refs = case.get("evidence_refs")
        if expected_evidence is not None and isinstance(evidence_refs, list):
            actual_evidence = {
                evidence.get("evidence_id"): _evidence_identity(evidence)
                for evidence in evidence_refs
                if isinstance(evidence, Mapping)
                and evidence.get("evidence_id") in expected_evidence
            }
            if (
                (require_complete or actual_evidence)
                and actual_evidence != expected_evidence
            ):
                raise LoopContractError("loop_evidence_ref_invalid")


class LoopGateError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class HashedRegistry(_StrictModel):
    sha256: Sha256
    value: LoopRegistry


class HashedCase(_StrictModel):
    sha256: Sha256
    value: EvolutionCase


class ReportSummary(_StrictModel):
    accepted_candidate_count: int = Field(ge=0, le=256)
    case_count: int = Field(ge=1, le=32)
    closed_no_change_count: int = Field(ge=0, le=256)
    episode_count: int = Field(ge=1, le=256)
    need_more_evidence_count: int = Field(ge=0, le=256)
    record_status: Literal["valid"]
    rejected_candidate_count: int = Field(ge=0, le=256)
    release_disposition: Literal[
        "hold",
        "eligible_for_separate_release_review",
        "rollback_recommended",
    ]


class LoopReport(_StrictModel):
    schema_version: Literal["dra.evidence-gated-loop-report.v1"]
    kernel_id: Literal["dra.evidence-gated-loop-kernel"]
    kernel_version: Literal["1"]
    registry: HashedRegistry
    cases: list[HashedCase] = Field(min_length=1, max_length=32)
    verification_results: list[VerificationResult] = Field(
        min_length=1, max_length=16
    )
    summary: ReportSummary
    limits: RegistryLimits
    non_claims: list[str] = Field(min_length=3, max_length=16)


def _resolve_registered_case_path(
    relative_path: str,
    *,
    project_root: Path = PROJECT_ROOT,
) -> Path:
    cases_root = project_root / "benchmarks/evidence-gated-loop-v1/cases"
    candidate = project_root / relative_path
    try:
        if candidate.is_symlink():
            raise OSError
        resolved_root = cases_root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
        if (
            not resolved.is_relative_to(resolved_root)
            or not resolved.is_file()
        ):
            raise OSError
        return resolved
    except OSError:
        raise LoopContractError("loop_case_invalid") from None


def validate_kernel_inputs(
    registry: LoopRegistry,
    cases: Sequence[EvolutionCase],
) -> None:
    expected_case_ids = [Path(path).stem for path in registry.case_paths]
    actual_case_ids = [case.case_id for case in cases]
    if (
        len(cases) != len(registry.case_paths)
        or actual_case_ids != expected_case_ids
    ):
        raise LoopContractError("loop_case_invalid")
    identity_sets = {
        "loop_case_invalid": actual_case_ids,
        "loop_evidence_ref_invalid": [
            item.evidence_id for case in cases for item in case.evidence_refs
        ],
        "loop_episode_invalid": [
            item.episode_id for case in cases for item in case.episodes
        ],
        "loop_candidate_identity_invalid": [
            candidate.candidate_id
            for case in cases
            for episode in case.episodes
            for candidate in episode.candidate_refs
        ],
    }
    for code, identities in identity_sets.items():
        if len(identities) != len(set(identities)):
            raise LoopContractError(code)
    _validate_reference_identities(
        tuple(case.model_dump(mode="json") for case in cases),
        require_complete=True,
    )
    declared = [
        (item.profile_id, item.profile_version)
        for item in registry.verification_profiles
    ]
    referenced: list[tuple[str, str]] = []
    for case in cases:
        for episode in case.episodes:
            identity = (
                episode.verification_profile_ref.profile_id,
                episode.verification_profile_ref.profile_version,
            )
            if identity not in referenced:
                referenced.append(identity)
    if (
        set(referenced) != set(declared)
        or any(identity not in PROFILE_REGISTRY for identity in declared)
    ):
        raise LoopContractError("loop_verification_profile_invalid")
    expected_bindings = {
        (case_id, episode_id): profile_identity
        for profile_identity in declared
        for case_id, episode_id in PROFILE_REGISTRY[
            profile_identity
        ].episode_bindings
    }
    actual_bindings = {
        (case.case_id, episode.episode_id): (
            episode.verification_profile_ref.profile_id,
            episode.verification_profile_ref.profile_version,
        )
        for case in cases
        for episode in case.episodes
    }
    if actual_bindings != expected_bindings:
        raise LoopContractError("loop_verification_profile_invalid")


def _load_kernel_inputs() -> tuple[LoopRegistry, tuple[EvolutionCase, ...]]:
    registry = load_registry(REGISTRY_PATH)
    cases = tuple(
        load_case_file(_resolve_registered_case_path(path))
        for path in registry.case_paths
    )
    validate_kernel_inputs(registry, cases)
    return registry, cases


def _derive_release_disposition(dispositions: Sequence[str]) -> str:
    if not dispositions or any(
        item
        not in {
            "hold",
            "eligible_for_separate_release_review",
            "rollback_recommended",
        }
        for item in dispositions
    ):
        raise LoopGateError("loop_report_invalid")
    if "rollback_recommended" in dispositions:
        return "rollback_recommended"
    if "hold" in dispositions:
        return "hold"
    return "eligible_for_separate_release_review"


def _derive_release_disposition_from_cases(
    cases: Sequence[EvolutionCase],
) -> str:
    return _derive_release_disposition(
        [
            case.episodes[-1].reviewed_decision.release_disposition
            for case in cases
        ]
    )


def _summary(cases: Sequence[EvolutionCase]) -> dict[str, Any]:
    decisions = [
        episode.reviewed_decision
        for case in cases
        for episode in case.episodes
    ]
    return {
        "accepted_candidate_count": sum(
            item.candidate_verdict == "accepted" for item in decisions
        ),
        "case_count": len(cases),
        "closed_no_change_count": sum(
            item.loop_closure_status == "closed_no_change"
            for item in decisions
        ),
        "episode_count": len(decisions),
        "need_more_evidence_count": sum(
            item.candidate_verdict == "need_more_evidence"
            for item in decisions
        ),
        "record_status": "valid",
        "rejected_candidate_count": sum(
            item.candidate_verdict == "rejected" for item in decisions
        ),
        "release_disposition": _derive_release_disposition_from_cases(cases),
    }


def _hash_value(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def build_report() -> dict[str, Any]:
    try:
        registry, cases = _load_kernel_inputs()
        results = run_required_profiles(registry)
        value = {
            "schema_version": "dra.evidence-gated-loop-report.v1",
            "kernel_id": registry.kernel_id,
            "kernel_version": registry.kernel_version,
            "registry": {
                "sha256": _hash_value(registry),
                "value": registry.model_dump(mode="json"),
            },
            "cases": [
                {
                    "sha256": _hash_value(case),
                    "value": case.model_dump(mode="json"),
                }
                for case in cases
            ],
            "verification_results": [
                item.model_dump(mode="json") for item in results
            ],
            "summary": _summary(cases),
            "limits": registry.limits.model_dump(mode="json"),
            "non_claims": list(registry.non_claims),
        }
        return validate_report(value)
    except (LoopContractError, LoopProfileError, LoopGateError) as exc:
        raise LoopGateError(exc.code) from None
    except Exception:
        raise LoopGateError("loop_report_invalid") from None


def validate_report(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        validate_public_projection(value)
        raw_cases = value.get("cases")
        if isinstance(raw_cases, list):
            _validate_reference_identities(
                tuple(
                    item["value"]
                    for item in raw_cases
                    if isinstance(item, Mapping)
                    and isinstance(item.get("value"), Mapping)
                ),
                require_complete=False,
            )
        raw_results = value.get("verification_results")
        if not isinstance(raw_results, list) or any(
            not isinstance(item, Mapping)
            or item.get("coverage")
            != ["fail_to_pass", "retained", "safety_compatibility"]
            for item in raw_results
        ):
            raise LoopGateError("loop_verification_profile_invalid")
        report = LoopReport.model_validate(value, strict=True)
        registry = validate_registry(
            report.registry.value.model_dump(mode="json")
        )
        cases = tuple(
            validate_case(item.value.model_dump(mode="json"))
            for item in report.cases
        )
        validate_kernel_inputs(registry, cases)
        if report.registry.sha256 != _hash_value(registry):
            raise ValueError("registry hash")
        for hashed, case in zip(report.cases, cases, strict=True):
            if hashed.sha256 != _hash_value(case):
                raise ValueError("case hash")
        identities = [
            (item.profile_id, item.profile_version)
            for item in registry.verification_profiles
        ]
        actual_identities = [
            (item.profile_id, item.profile_version)
            for item in report.verification_results
        ]
        if actual_identities != identities:
            raise ValueError("profile order")
        for item in report.verification_results:
            if item.coverage != [
                "fail_to_pass",
                "retained",
                "safety_compatibility",
            ]:
                raise ValueError("coverage")
        if report.summary.model_dump(mode="json") != _summary(cases):
            raise ValueError("summary")
        if report.limits != registry.limits:
            raise ValueError("limits")
        if tuple(report.non_claims) != REQUIRED_NON_CLAIMS:
            raise ValueError("nonclaims")
        canonical = canonical_json_bytes(report)
        if len(canonical) > MAX_REPORT_BYTES:
            raise ValueError("oversized")
        return report.model_dump(mode="json")
    except LoopGateError:
        raise
    except LoopContractError as exc:
        raise LoopGateError(exc.code) from None
    except (ValidationError, ValueError, TypeError):
        raise LoopGateError("loop_report_invalid") from None


def serialize_report(report: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(validate_report(report))


def _cell(value: Any) -> str:
    text = str(value)
    validate_public_projection(text)
    return text.replace("|", "\\|")


def render_markdown(report: Mapping[str, Any]) -> str:
    value = validate_report(report)
    summary = value["summary"]
    lines = [
        "# Evidence-Gated Loop Kernel v1",
        "",
        "This is provider-free offline verification of reviewed evidence-gated lineages.",
        "",
        "## Record Status",
        "",
        f"- Record status: `{summary['record_status']}`",
        f"- Cases: `{summary['case_count']}`; episodes: `{summary['episode_count']}`",
        "",
        "## Case Lineage Matrix",
        "",
        "| Case | Episodes |",
        "|---|---:|",
    ]
    for item in value["cases"]:
        case = item["value"]
        lines.append(f"| {_cell(case['case_id'])} | {len(case['episodes'])} |")
    lines.extend(
        [
            "",
            "## Evidence And Historical RED Boundary",
            "",
            "Historical RED is reviewed provenance; it is not re-executed by this report.",
            "",
            "## Fixed Verification Profiles",
            "",
        ]
    )
    for result in value["verification_results"]:
        lines.append(
            f"- `{_cell(result['profile_id'])}@{_cell(result['profile_version'])}`: "
            f"`{_cell(result['status'])}`"
        )
    lines.extend(
        [
            "",
            "## Candidate, Consumer, And Closure Axes",
            "",
            f"- Accepted candidates: `{summary['accepted_candidate_count']}`",
            f"- Closed no-change episodes: `{summary['closed_no_change_count']}`",
            "",
            "## Release Hold And Rollback",
            "",
            f"Release disposition: `{summary['release_disposition']}`",
            "Rollback is recommendation-only and is never executed by this kernel.",
            "",
            "## Reproduce",
            "",
            "```bash",
            "PYTHON_DOTENV_DISABLED=1 python scripts/evidence_gated_loop_gate.py check",
            "```",
            "",
            "## Limits",
            "",
            f"- Maximum case bytes: `{value['limits']['max_case_bytes']}`",
            "",
            "## Non-Claims",
            "",
        ]
    )
    lines.extend(f"- {_cell(item)}" for item in value["non_claims"])
    lines.extend(
        [
            "- No live-provider strict success is claimed.",
            "",
        ]
    )
    return "\n".join(lines)


def compare_artifacts(
    candidate_report: Mapping[str, Any],
    candidate_markdown: str,
    baseline_json: bytes,
    baseline_markdown: bytes,
) -> dict[str, Any]:
    try:
        baseline_value = json.loads(baseline_json)
        validated = validate_report(baseline_value)
        canonical_json = serialize_report(validated)
        canonical_markdown = render_markdown(validated).encode("utf-8")
        if (
            baseline_json != canonical_json
            or baseline_markdown != canonical_markdown
            or serialize_report(candidate_report) != baseline_json
            or candidate_markdown.encode("utf-8") != baseline_markdown
        ):
            raise ValueError("drift")
        return {"match": True, "record_status": "valid", "status": "valid"}
    except Exception:
        raise LoopGateError("loop_baseline_invalid") from None


def _resolve_output(path: Path) -> Path:
    try:
        if path.is_symlink():
            raise OSError
        parent = path.parent.resolve(strict=True)
        if not parent.is_dir() or path.is_dir():
            raise OSError
        resolved = parent / path.name
        baseline_aliases = {
            BASELINE_JSON_PATH.resolve(),
            BASELINE_MARKDOWN_PATH.resolve(),
        }
        if resolved in baseline_aliases:
            raise OSError
        return resolved
    except OSError:
        raise LoopGateError("loop_output_invalid") from None


def _stage_file(target: Path, value: bytes) -> Path:
    handle = tempfile.NamedTemporaryFile(
        mode="wb", dir=target.parent, prefix=f".{target.name}.", delete=False
    )
    staged = Path(handle.name)
    try:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
    except OSError:
        try:
            handle.close()
        except OSError:
            pass
        try:
            staged.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return staged


def write_artifacts_recoverably(
    report: Mapping[str, Any],
    markdown: str,
    *,
    json_output: Path,
    markdown_output: Path,
) -> None:
    validated = validate_report(report)
    json_bytes = serialize_report(validated)
    expected_markdown = render_markdown(validated)
    if markdown != expected_markdown:
        raise LoopGateError("loop_output_invalid")
    json_target = _resolve_output(json_output)
    markdown_target = _resolve_output(markdown_output)
    if json_target == markdown_target:
        raise LoopGateError("loop_output_invalid")
    for target in (json_target, markdown_target):
        if target.exists():
            try:
                read_bounded_bytes(target, limit=MAX_REPORT_BYTES)
            except LoopBoundedReadError:
                raise LoopGateError("loop_output_invalid") from None
    json_temp: Path | None = None
    markdown_temp: Path | None = None
    restore_temp: Path | None = None
    prior_markdown = (
        markdown_target.read_bytes() if markdown_target.exists() else None
    )
    try:
        json_temp = _stage_file(json_target, json_bytes)
        markdown_temp = _stage_file(
            markdown_target, expected_markdown.encode("utf-8")
        )
        os.replace(markdown_temp, markdown_target)
        markdown_temp = None
        try:
            os.replace(json_temp, json_target)
            json_temp = None
        except OSError:
            if prior_markdown is None:
                markdown_target.unlink(missing_ok=True)
            else:
                restore_temp = _stage_file(
                    markdown_target, prior_markdown
                )
                os.replace(restore_temp, markdown_target)
                restore_temp = None
            raise
    except (OSError, LoopGateError):
        raise LoopGateError("loop_output_invalid") from None
    finally:
        for temp in (json_temp, markdown_temp, restore_temp):
            if temp is not None:
                temp.unlink(missing_ok=True)


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        raise LoopGateError("loop_output_invalid")


def _parser() -> _ArgumentParser:
    parser = _ArgumentParser(prog="evidence_gated_loop_gate.py")
    commands = parser.add_subparsers(
        dest="command", required=True, parser_class=_ArgumentParser
    )
    build = commands.add_parser("build")
    build.add_argument("--json-output", type=Path, required=True)
    build.add_argument("--markdown-output", type=Path, required=True)
    commands.add_parser("check")
    return parser


def _error(code: str) -> int:
    sys.stderr.write(
        json.dumps(
            {"code": code, "status": "invalid"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    return 1


def _run(args: argparse.Namespace) -> int:
    report = build_report()
    markdown = render_markdown(report)
    if args.command == "build":
        write_artifacts_recoverably(
            report,
            markdown,
            json_output=args.json_output,
            markdown_output=args.markdown_output,
        )
        payload = {"record_status": "valid", "status": "built"}
    else:
        try:
            baseline_json = read_bounded_bytes(
                BASELINE_JSON_PATH, limit=MAX_REPORT_BYTES
            )
            baseline_markdown = read_bounded_bytes(
                BASELINE_MARKDOWN_PATH, limit=MAX_REPORT_BYTES
            )
        except LoopBoundedReadError:
            raise LoopGateError("loop_baseline_invalid") from None
        payload = compare_artifacts(
            report, markdown, baseline_json, baseline_markdown
        )
    sys.stdout.write(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        return _run(args)
    except SystemExit as exc:
        if exc.code == 0:
            return 0
        return _error("loop_output_invalid")
    except (LoopGateError, LoopProfileError, LoopContractError) as exc:
        return _error(exc.code)
    except Exception:
        return _error("loop_internal_error")


if __name__ == "__main__":
    raise SystemExit(main())
