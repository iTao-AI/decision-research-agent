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
    try:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
        return Path(handle.name)
    finally:
        handle.close()


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
                restore = _stage_file(markdown_target, prior_markdown)
                os.replace(restore, markdown_target)
            raise
    except (OSError, LoopGateError):
        raise LoopGateError("loop_output_invalid") from None
    finally:
        for temp in (json_temp, markdown_temp):
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
