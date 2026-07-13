"""Deterministic Agent evaluation report, baseline comparison, and CLI."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from scripts import downstream_consumer_contract
from scripts.agent_evaluation_contracts import (
    CASE_IDS,
    COMPARISON_SCHEMA_VERSION,
    EVALUATOR_VERSION,
    MANIFEST_SCHEMA_VERSION,
    MAX_REPORT_BYTES,
    REPORT_SCHEMA_VERSION,
    EvaluationValidationError,
    dataset_hash,
    load_manifest,
    serialize_json,
    validate_comparison,
    validate_manifest,
    validate_observation,
    validate_report,
)
from scripts.agent_evaluation_evaluators import EVALUATOR_REGISTRY, evaluate_observation


MANIFEST_PATH = PROJECT_ROOT / "benchmarks/agent-evaluation-v1/scenarios.json"
BASELINE_JSON_PATH = PROJECT_ROOT / "docs/evidence/agent-evaluation-regression-v1.json"
BASELINE_MARKDOWN_PATH = PROJECT_ROOT / "docs/evidence/agent-evaluation-regression-v1.md"


def _fail(code: str) -> None:
    raise EvaluationValidationError(code)


def build_deterministic_observations(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    canonical_manifest = load_manifest(MANIFEST_PATH) if manifest is None else manifest
    canonical_manifest = validate_manifest(canonical_manifest)
    bundle = downstream_consumer_contract.build_fixture_bundle()
    downstream_consumer_contract.validate_fixture_bundle(bundle)
    consumer_cases = {case["case_id"]: case for case in bundle["cases"]}
    observations = []
    for manifest_case in canonical_manifest["cases"]:
        case = copy.deepcopy(manifest_case)
        source = copy.deepcopy(consumer_cases[case.pop("source_case_id")])
        evidence_mode = case.pop("evidence_mode")
        current_run_id = source["run"]["run_id"]
        trajectory = []
        for event in case.pop("trajectory"):
            event["run_id"] = (
                current_run_id
                if event.pop("run_ref") == "current"
                else "run_evaluation_foreign"
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
        observations.append(validate_observation(observation))
    return observations


def build_deterministic_report(manifest: dict[str, Any]) -> dict[str, Any]:
    evaluated_cases = [
        evaluate_observation(observation)
        for observation in build_deterministic_observations(manifest)
    ]
    expectation_mismatches = sum(
        not case["expectation_match"] for case in evaluated_cases
    )
    blocking_regressions = sum(
        case["status"] == "regression" and bool(case["blocking_finding_codes"])
        for case in evaluated_cases
    )
    observational_changes = sum(
        len(case["observational_finding_codes"]) for case in evaluated_cases
    )
    not_observed = sum(
        evaluator["status"] == "not_observed"
        for case in evaluated_cases
        for evaluator in case["evaluators"]
    )
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "evaluator_version": EVALUATOR_VERSION,
        "source": "deterministic",
        "dataset": {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "sha256": dataset_hash(manifest),
            "case_ids": list(CASE_IDS),
        },
        "registry": [
            {"evaluator_id": evaluator_id, "version": version}
            for evaluator_id, version, _ in EVALUATOR_REGISTRY
        ],
        "summary": {
            "blocking_regression_count": blocking_regressions,
            "expectation_mismatch_count": expectation_mismatches,
            "observational_change_count": observational_changes,
            "not_observed_count": not_observed,
            "release_gate_passed": not blocking_regressions
            and not expectation_mismatches,
        },
        "cases": evaluated_cases,
        "limits": [
            "Deterministic contract regression proof, not answer-truth verification.",
            "Efficiency and cost are fixture observations; cost is an estimate.",
            "LangSmith diagnostics are separate and are not invoked by this gate.",
        ],
    }
    return validate_report(report)


def _markdown_cell(value: Any) -> str:
    text = str(value)
    if "\n" in text or "\r" in text:
        _fail("evaluation_output_invalid")
    return text.replace("|", "\\|")


def render_markdown(report: dict[str, Any]) -> str:
    canonical = validate_report(report)
    summary = canonical["summary"]
    lines = [
        "# Agent Evaluation Regression Gate v1",
        "",
        f"- Report schema: `{canonical['schema_version']}`",
        f"- Dataset schema: `{canonical['dataset']['schema_version']}`",
        f"- Dataset SHA-256: `{canonical['dataset']['sha256']}`",
        f"- Release gate passed: `{str(summary['release_gate_passed']).lower()}`",
        "",
        "## Summary",
        "",
        f"- Blocking regressions: {summary['blocking_regression_count']}",
        f"- Expectation mismatches: {summary['expectation_mismatch_count']}",
        f"- Observational changes: {summary['observational_change_count']}",
        f"- Not observed: {summary['not_observed_count']}",
        "",
        "## Cases",
        "",
        "| Case | Status | Blocking findings | Observational findings |",
        "|---|---|---|---|",
    ]
    for case in canonical["cases"]:
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(value)
                for value in (
                    case["case_id"],
                    case["status"],
                    ", ".join(case["blocking_finding_codes"]) or "none",
                    ", ".join(case["observational_finding_codes"]) or "none",
                )
            )
            + " |"
        )
    lines.extend(["", "## Limits", ""])
    lines.extend(f"- {limit}" for limit in canonical["limits"])
    return "\n".join(lines) + "\n"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _case_map(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {case["case_id"]: case for case in report["cases"]}


def compare_artifacts(
    candidate_report: dict[str, Any],
    candidate_markdown: str,
    baseline_json: bytes,
    baseline_markdown: bytes,
) -> dict[str, Any]:
    candidate_json = serialize_json(candidate_report, validator=validate_report)
    candidate_markdown_bytes = candidate_markdown.encode("utf-8")
    if len(baseline_json) > MAX_REPORT_BYTES or len(baseline_markdown) > MAX_REPORT_BYTES:
        _fail("evaluation_baseline_invalid")
    try:
        baseline_payload = json.loads(baseline_json.decode("utf-8"))
        baseline_report = validate_report(baseline_payload)
        baseline_markdown_text = baseline_markdown.decode("utf-8")
    except (UnicodeError, json.JSONDecodeError, EvaluationValidationError):
        _fail("evaluation_baseline_invalid")
    if render_markdown(baseline_report) != baseline_markdown_text:
        _fail("evaluation_baseline_invalid")

    candidate_cases = _case_map(candidate_report)
    baseline_cases = _case_map(baseline_report)
    changed_case_ids = [
        case_id
        for case_id in CASE_IDS
        if candidate_cases.get(case_id) != baseline_cases.get(case_id)
    ]
    blocking_regression_codes = [
        code
        for case in candidate_report["cases"]
        if case["status"] == "regression"
        for code in case["blocking_finding_codes"]
    ]
    observational_changes = [
        case_id
        for case_id in CASE_IDS
        if candidate_cases.get(case_id, {}).get("observational_finding_codes")
        != baseline_cases.get(case_id, {}).get("observational_finding_codes")
    ]
    comparison = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "match": candidate_json == baseline_json
        and candidate_markdown_bytes == baseline_markdown,
        "candidate": {
            "json_sha256": _sha256(candidate_json),
            "markdown_sha256": _sha256(candidate_markdown_bytes),
        },
        "baseline": {
            "json_sha256": _sha256(baseline_json),
            "markdown_sha256": _sha256(baseline_markdown),
        },
        "changed_case_ids": changed_case_ids,
        "blocking_regression_codes": blocking_regression_codes,
        "observational_changes": observational_changes,
    }
    return validate_comparison(comparison)


def _bounded_read(path: Path, *, baseline: bool) -> bytes:
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_REPORT_BYTES + 1)
    except OSError:
        _fail("evaluation_baseline_invalid" if baseline else "evaluation_output_invalid")
    if len(raw) > MAX_REPORT_BYTES:
        _fail("evaluation_baseline_invalid" if baseline else "evaluation_output_invalid")
    return raw


def _resolved_output(path: Path) -> Path:
    try:
        resolved = path.resolve(strict=False)
        parent = resolved.parent
        if not parent.exists() or not parent.is_dir() or path.is_dir():
            _fail("evaluation_output_invalid")
        if path.exists() and not os.access(path, os.W_OK):
            _fail("evaluation_output_invalid")
        if not os.access(parent, os.W_OK):
            _fail("evaluation_output_invalid")
        baselines = {
            BASELINE_JSON_PATH.resolve(strict=False),
            BASELINE_MARKDOWN_PATH.resolve(strict=False),
        }
        if resolved in baselines:
            _fail("evaluation_output_invalid")
        return resolved
    except EvaluationValidationError:
        raise
    except OSError:
        _fail("evaluation_output_invalid")


def _write_bytes(path: Path, raw: bytes) -> None:
    resolved = _resolved_output(path)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=resolved.parent,
            prefix=f".{resolved.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, resolved)
        temporary = None
    except OSError:
        _fail("evaluation_output_invalid")
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _error(code: str) -> int:
    print(
        json.dumps({"status": "invalid", "code": code}, separators=(",", ":")),
        file=sys.stderr,
    )
    return 1


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        _fail("evaluation_output_invalid")


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(description="Build or check Agent evaluation artifacts.")
    subparsers = parser.add_subparsers(
        dest="command", required=True, parser_class=_ArgumentParser
    )
    build = subparsers.add_parser("build")
    build.add_argument("--json-output", required=True)
    build.add_argument("--markdown-output", required=True)
    check = subparsers.add_parser("check")
    check.add_argument("--comparison-output")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        manifest = load_manifest(MANIFEST_PATH)
        report = build_deterministic_report(manifest)
        markdown = render_markdown(report)
        if args.command == "build":
            json_path = Path(args.json_output)
            markdown_path = Path(args.markdown_output)
            resolved_json = _resolved_output(json_path)
            resolved_markdown = _resolved_output(markdown_path)
            if resolved_json == resolved_markdown:
                _fail("evaluation_output_invalid")
            report_bytes = serialize_json(report, validator=validate_report)
            validate_report(json.loads(report_bytes.decode("utf-8")))
            _write_bytes(json_path, report_bytes)
            _write_bytes(markdown_path, markdown.encode("utf-8"))
            print(json.dumps({"status": "built"}, separators=(",", ":")))
            return 0

        baseline_json = _bounded_read(BASELINE_JSON_PATH, baseline=True)
        baseline_markdown = _bounded_read(BASELINE_MARKDOWN_PATH, baseline=True)
        comparison = compare_artifacts(
            report, markdown, baseline_json, baseline_markdown
        )
        comparison_bytes = serialize_json(
            comparison, validator=validate_comparison
        )
        if args.comparison_output:
            _write_bytes(Path(args.comparison_output), comparison_bytes)
        sys.stdout.buffer.write(comparison_bytes)
        return 0 if comparison["match"] and report["summary"]["release_gate_passed"] else 1
    except EvaluationValidationError as exc:
        return _error(exc.code)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _error("evaluation_output_invalid")
    except Exception:
        return _error("evaluation_internal_error")


if __name__ == "__main__":
    raise SystemExit(main())
