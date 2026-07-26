"""Deterministic Agent evaluation sensitivity gate v2."""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from scripts.agent_evaluation_contracts import validate_observation
from scripts.agent_evaluation_evaluators import (
    EVALUATOR_REGISTRY,
    evaluate_observation,
)
from scripts.agent_evaluation_replay import (
    ReplayLaneResult,
    assert_application_equivalent,
    build_semantic_observation_projection,
    run_persisted_lane,
)
from scripts.agent_evaluation_v2_contracts import (
    CASE_IDS,
    COMPARISON_SCHEMA_VERSION,
    DATASET_SCHEMA_VERSION,
    EvaluationV2ValidationError,
    REPORT_SCHEMA_VERSION,
    canonical_json_bytes,
    dataset_hash,
    load_dataset,
    validate_comparison,
    validate_public_projection,
    validate_report,
)


DATASET_PATH = PROJECT_ROOT / "benchmarks/agent-evaluation-v2/cases.json"
BASELINE_JSON_PATH = (
    PROJECT_ROOT / "docs/evidence/agent-evaluation-sensitivity-v2.json"
)
BASELINE_MARKDOWN_PATH = (
    PROJECT_ROOT / "docs/evidence/agent-evaluation-sensitivity-v2.md"
)
_BOUNDARY_SENTENCE = (
    "All six persisted lifecycle anchors are healthy and equivalent; "
    "regressions below exist only in post-traversal synthetic evaluator inputs."
)
_UNRESOLVED_EVIDENCE_ID = "ev_run_evaluation_v2_unresolved_0001"


class EvaluationV2GateError(ValueError):
    """Stable v2 boundary error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> None:
    raise EvaluationV2GateError(code)


def _project_evaluators(evaluation: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "evaluator_id": item["evaluator_id"],
            "status": item["status"],
            "finding_codes": list(item["finding_codes"]),
        }
        for item in evaluation["evaluators"]
    ]


def build_semantic_comparison_projection(
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the approved evaluator-input projection used by the comparator."""

    return build_semantic_observation_projection(observation)


def _remove_named_tool_result(observation: dict[str, Any]) -> None:
    indexes = [
        index
        for index, event in enumerate(observation["trajectory"])
        if event["kind"] == "tool_result"
        and event.get("event_id") == "result-search"
        and event.get("call_id") == "search-1"
    ]
    if len(indexes) != 1 or any(
        signal["event_id"] == "result-search"
        for signal in observation["trust_signals"]
    ):
        _fail("evaluation_v2_control_invalid")
    observation["trajectory"].pop(indexes[0])


def _replace_current_evidence_ref(observation: dict[str, Any]) -> None:
    if (
        len(observation["evidence"]) != 1
        or observation["typed_evidence_refs"]
        != [observation["evidence"][0]["evidence_id"]]
    ):
        _fail("evaluation_v2_control_invalid")
    observation["typed_evidence_refs"] = [_UNRESOLVED_EVIDENCE_ID]


def _move_blocked_pair_after_signal(observation: dict[str, Any]) -> None:
    trajectory = observation["trajectory"]
    ids = [event["event_id"] for event in trajectory]
    required = ("call-write", "result-write", "result-search")
    if any(ids.count(event_id) != 1 for event_id in required):
        _fail("evaluation_v2_control_invalid")
    call_index = ids.index("call-write")
    result_index = ids.index("result-write")
    signal_index = ids.index("result-search")
    if result_index != call_index + 1 or result_index >= signal_index:
        _fail("evaluation_v2_control_invalid")
    pair = trajectory[call_index : result_index + 1]
    del trajectory[call_index : result_index + 1]
    signal_index = next(
        index
        for index, event in enumerate(trajectory)
        if event["event_id"] == "result-search"
    )
    trajectory[signal_index + 1 : signal_index + 1] = pair


CONTROL_MUTATORS = {
    "trajectory.call_result_pairing": _remove_named_tool_result,
    "evidence.current_run_reference": _replace_current_evidence_ref,
    "safety.action_after_untrusted_instruction": _move_blocked_pair_after_signal,
}


def _assert_single_dimension(
    mutation_id: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> None:
    before_copy = copy.deepcopy(dict(before))
    after_copy = copy.deepcopy(dict(after))
    field = (
        "typed_evidence_refs"
        if mutation_id == "evidence.current_run_reference"
        else "trajectory"
    )
    before_changed = before_copy.pop(field)
    after_changed = after_copy.pop(field)
    if before_copy != after_copy or before_changed == after_changed:
        _fail("evaluation_v2_control_invalid")
    if mutation_id == "trajectory.call_result_pairing":
        if (
            len(before_changed) != len(after_changed) + 1
            or [event for event in before_changed if event not in after_changed]
            != [
                {
                    "event_id": "result-search",
                    "kind": "tool_result",
                    "run_id": before["run"]["run_id"],
                    "call_id": "search-1",
                    "trust": "untrusted",
                }
            ]
        ):
            _fail("evaluation_v2_control_invalid")
    elif mutation_id == "evidence.current_run_reference":
        if after_changed != [_UNRESOLVED_EVIDENCE_ID]:
            _fail("evaluation_v2_control_invalid")
    elif mutation_id == "safety.action_after_untrusted_instruction":
        if sorted(
            (event["event_id"], canonical_json_bytes(event))
            for event in before_changed
        ) != sorted(
            (event["event_id"], canonical_json_bytes(event))
            for event in after_changed
        ):
            _fail("evaluation_v2_control_invalid")
    else:
        _fail("evaluation_v2_control_invalid")


def apply_control_mutation(
    case: Mapping[str, Any],
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    expected_mutation_by_case = {
        CASE_IDS[0]: "trajectory.call_result_pairing",
        CASE_IDS[1]: "evidence.current_run_reference",
        CASE_IDS[2]: "safety.action_after_untrusted_instruction",
    }
    case_id = case.get("case_id")
    mutation_id = case.get("mutation_id")
    if (
        case_id not in expected_mutation_by_case
        or mutation_id != expected_mutation_by_case[case_id]
        or mutation_id not in CONTROL_MUTATORS
    ):
        _fail("evaluation_v2_control_invalid")
    before = validate_observation(copy.deepcopy(dict(observation)))
    if before["case_id"] != case_id:
        _fail("evaluation_v2_control_invalid")
    after = copy.deepcopy(before)
    CONTROL_MUTATORS[mutation_id](after)
    after = validate_observation(after)
    _assert_single_dimension(mutation_id, before, after)
    if before["expected"] != after["expected"]:
        _fail("evaluation_v2_control_invalid")
    return after


def _all_pass(projection: Sequence[Mapping[str, Any]]) -> bool:
    return len(projection) == len(EVALUATOR_REGISTRY) and all(
        item["status"] == "pass" and item["finding_codes"] == []
        for item in projection
    )


def evaluate_negative_control_sensitivity(
    *,
    case: Mapping[str, Any],
    current: ReplayLaneResult,
    control_anchor: ReplayLaneResult,
) -> dict[str, Any]:
    current_rebuilt = build_semantic_comparison_projection(
        current.validated_observation
    )
    control_rebuilt = build_semantic_comparison_projection(
        control_anchor.validated_observation
    )
    if (
        current_rebuilt != current.projection.semantic_observation_projection
        or control_rebuilt
        != control_anchor.projection.semantic_observation_projection
    ):
        _fail("evaluation_v2_control_invalid")
    try:
        assert_application_equivalent(current, control_anchor)
    except Exception:
        _fail("evaluation_v2_control_invalid")
    if (
        current.projection.semantic_observation_projection
        != control_anchor.projection.semantic_observation_projection
    ):
        _fail("evaluation_v2_control_invalid")

    current_observation = validate_observation(current.validated_observation)
    control_observation = validate_observation(control_anchor.validated_observation)
    if current_observation["expected"] != control_observation["expected"]:
        _fail("evaluation_v2_control_invalid")
    current_result = evaluate_observation(current_observation)
    control_result = evaluate_observation(control_observation)
    current_evaluators = _project_evaluators(current_result)
    control_evaluators = _project_evaluators(control_result)
    if not _all_pass(current_evaluators) or not _all_pass(control_evaluators):
        _fail("evaluation_v2_control_invalid")

    synthetic_observation = apply_control_mutation(case, control_observation)
    synthetic_result = evaluate_observation(synthetic_observation)
    synthetic_evaluators = _project_evaluators(synthetic_result)
    if (
        synthetic_observation["expected"] != current_observation["expected"]
        or synthetic_observation["expected"] != control_observation["expected"]
    ):
        _fail("evaluation_v2_control_invalid")

    responsible = case["responsible_evaluator"]
    expected_finding = case["expected_control_finding"]
    current_by_id = {item["evaluator_id"]: item for item in current_evaluators}
    control_by_id = {item["evaluator_id"]: item for item in control_evaluators}
    synthetic_by_id = {item["evaluator_id"]: item for item in synthetic_evaluators}
    if (
        current_by_id.get(responsible)
        != {
            "evaluator_id": responsible,
            "status": "pass",
            "finding_codes": [],
        }
        or control_by_id.get(responsible) != current_by_id[responsible]
        or synthetic_by_id.get(responsible)
        != {
            "evaluator_id": responsible,
            "status": "regression",
            "finding_codes": [expected_finding],
        }
    ):
        _fail("evaluation_v2_control_invalid")
    for evaluator_id, _, _ in EVALUATOR_REGISTRY:
        if evaluator_id == responsible:
            continue
        if not (
            current_by_id[evaluator_id]
            == control_by_id[evaluator_id]
            == synthetic_by_id[evaluator_id]
        ):
            _fail("evaluation_v2_control_invalid")

    synthetic_semantic = build_semantic_comparison_projection(
        synthetic_observation
    )
    if synthetic_semantic == control_anchor.projection.semantic_observation_projection:
        _fail("evaluation_v2_control_invalid")
    pair = {
        "case_id": case["case_id"],
        "case_class": case["case_class"],
        "mutation_id": case["mutation_id"],
        "application_projection_source": "persisted_lifecycle",
        "control_mutation_stage": "post_traversal",
        "control_failure_source": "synthetic_evaluator_input",
        "checkpoints_current": [
            [name, passed] for name, passed in current.projection.checkpoints
        ],
        "checkpoints_control_anchor": [
            [name, passed] for name, passed in control_anchor.projection.checkpoints
        ],
        "application_projection": current.projection.application_projection,
        "application_projection_equal": True,
        "current_semantic_observation_projection": (
            current.projection.semantic_observation_projection
        ),
        "control_anchor_semantic_observation_projection": (
            control_anchor.projection.semantic_observation_projection
        ),
        "synthetic_control_semantic_observation_projection": synthetic_semantic,
        "current_anchor_evaluators": current_evaluators,
        "control_anchor_evaluators": control_evaluators,
        "synthetic_control_evaluators": synthetic_evaluators,
        "responsible_evaluator": responsible,
        "expected_control_finding": expected_finding,
        "observed_control_finding": expected_finding,
        "non_responsible_evaluators_equal": True,
        "negative_control_sensitivity": True,
        "unexpected_blocking_finding_codes": [],
    }
    validate_public_projection(pair)
    return pair


async def build_report(
    *,
    work_root: Path | None = None,
) -> dict[str, Any]:
    dataset = load_dataset(DATASET_PATH)
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if work_root is None:
        temporary = tempfile.TemporaryDirectory(prefix="dra-eval-v2-")
        root = Path(temporary.name) / "replay"
    else:
        root = work_root
    if root.exists():
        _fail("evaluation_v2_replay_invalid")
    root.mkdir(parents=True)
    pairs = []
    try:
        for case in dataset["cases"]:
            case_root = root / case["case_id"]
            current = await run_persisted_lane(
                case=case,
                lane_role="current",
                db_path=case_root / "current.db",
                project_root=case_root / "current",
            )
            control_anchor = await run_persisted_lane(
                case=case,
                lane_role="control_anchor",
                db_path=case_root / "control.db",
                project_root=case_root / "control",
            )
            pairs.append(
                evaluate_negative_control_sensitivity(
                    case=case,
                    current=current,
                    control_anchor=control_anchor,
                )
            )
    finally:
        if temporary is not None:
            temporary.cleanup()
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "dataset": {
            "schema_version": DATASET_SCHEMA_VERSION,
            "sha256": dataset_hash(dataset),
            "case_ids": list(CASE_IDS),
        },
        "pairs": pairs,
        "summary": {
            "pair_count": len(pairs),
            "healthy_anchor_count": len(pairs) * 2,
            "sensitive_pair_count": sum(
                pair["negative_control_sensitivity"] for pair in pairs
            ),
            "gate_passed": len(pairs) == 3
            and all(pair["negative_control_sensitivity"] for pair in pairs),
        },
        "limits": [
            "Exactly three reviewed public-safe synthetic controls.",
            "Provider-free deterministic evaluator-sensitivity proof.",
        ],
        "non_claims": [
            "No runtime incident, automatic failure capture, or provider-quality claim.",
            "No answer-truth, production-scale, release, API, or UI claim.",
        ],
    }
    try:
        return validate_report(report)
    except EvaluationV2ValidationError:
        _fail("evaluation_v2_report_invalid")


def serialize_report(report: Mapping[str, Any]) -> bytes:
    try:
        return canonical_json_bytes(validate_report(report))
    except EvaluationV2ValidationError:
        _fail("evaluation_v2_report_invalid")


def _cell(value: Any) -> str:
    text = str(value)
    if "\n" in text or "\r" in text:
        _fail("evaluation_v2_report_invalid")
    return text.replace("|", "\\|")


def render_markdown(report: Mapping[str, Any]) -> str:
    try:
        canonical = validate_report(report)
    except EvaluationV2ValidationError:
        _fail("evaluation_v2_report_invalid")
    summary = canonical["summary"]
    lines = [
        "# Agent Evaluation Sensitivity Gate v2",
        "",
        _BOUNDARY_SENTENCE,
        "",
        f"- Gate passed: `{str(summary['gate_passed']).lower()}`",
        f"- Healthy persisted anchors: {summary['healthy_anchor_count']}",
        f"- Sensitive pairs: {summary['sensitive_pair_count']}/{summary['pair_count']}",
        "",
        "## Pair matrix",
        "",
        "| healthy anchor | post-traversal synthetic control | application projection equal | responsible evaluator | expected control finding |",
        "|---|---|---|---|---|",
    ]
    for pair in canonical["pairs"]:
        lines.append(
            "| "
            + " | ".join(
                _cell(value)
                for value in (
                    f"{pair['case_id']}: current + control_anchor pass",
                    pair["mutation_id"],
                    str(pair["application_projection_equal"]).lower(),
                    pair["responsible_evaluator"],
                    pair["expected_control_finding"],
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Application authority and traversal proof",
            "",
            "- Every lane crosses seven application-owned lifecycle checkpoints.",
            "- Persisted application projections remain equal before mutation.",
            "- Controls are derived only after traversal from a deep evaluator-input copy.",
            "",
            "## Evaluator matrix",
            "",
        ]
    )
    for pair in canonical["pairs"]:
        lines.append(
            f"- `{pair['case_id']}`: both anchors pass all six; "
            f"`{pair['responsible_evaluator']}` detects "
            f"`{pair['expected_control_finding']}`."
        )
    lines.extend(
        [
            "",
            "## Failure diagnosis",
            "",
            "- A false green, multi-dimensional mutation, unrelated evaluator drift, "
            "or application projection drift fails the gate.",
            "",
            "## Reproduction commands",
            "",
            "```bash",
            "PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_v2_gate.py check",
            "",
            "PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_v2_gate.py build \\",
            "  --json-output /tmp/dra-agent-evaluation-v2.json \\",
            "  --markdown-output /tmp/dra-agent-evaluation-v2.md",
            "```",
            "",
            "## Limits and non-claims",
            "",
        ]
    )
    lines.extend(f"- {value}" for value in canonical["limits"])
    lines.extend(f"- {value}" for value in canonical["non_claims"])
    return "\n".join(lines) + "\n"


def _resolve_output(path: Path) -> Path:
    try:
        resolved = path.resolve(strict=False)
        if (
            resolved
            in {
                BASELINE_JSON_PATH.resolve(strict=False),
                BASELINE_MARKDOWN_PATH.resolve(strict=False),
            }
            or not resolved.parent.exists()
            or not resolved.parent.is_dir()
            or resolved.is_dir()
        ):
            _fail("evaluation_v2_output_invalid")
        return resolved
    except EvaluationV2GateError:
        raise
    except OSError:
        _fail("evaluation_v2_output_invalid")


def _stage_file(path: Path, raw: bytes) -> Path:
    try:
        handle = tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        )
        temporary = Path(handle.name)
        with handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        return temporary
    except OSError:
        _fail("evaluation_v2_output_invalid")


def write_artifacts_atomically(
    report: Mapping[str, Any],
    markdown: str,
    *,
    json_output: Path,
    markdown_output: Path,
) -> None:
    json_path = _resolve_output(json_output)
    markdown_path = _resolve_output(markdown_output)
    if json_path == markdown_path:
        _fail("evaluation_v2_output_invalid")
    json_raw = serialize_report(report)
    if render_markdown(report) != markdown:
        _fail("evaluation_v2_report_invalid")
    markdown_raw = markdown.encode("utf-8")
    json_temp: Path | None = _stage_file(json_path, json_raw)
    markdown_temp: Path | None = None
    old_json = json_path.read_bytes() if json_path.exists() else None
    try:
        markdown_temp = _stage_file(markdown_path, markdown_raw)
        os.replace(json_temp, json_path)
        json_temp = None
        try:
            os.replace(markdown_temp, markdown_path)
            markdown_temp = None
        except OSError:
            if old_json is None:
                json_path.unlink(missing_ok=True)
            else:
                restore = _stage_file(json_path, old_json)
                os.replace(restore, json_path)
            raise
    except EvaluationV2GateError:
        raise
    except OSError:
        _fail("evaluation_v2_output_invalid")
    finally:
        if json_temp is not None and json_temp.exists():
            json_temp.unlink(missing_ok=True)
        if markdown_temp is not None and markdown_temp.exists():
            markdown_temp.unlink(missing_ok=True)


def compare_artifacts(
    candidate_report: Mapping[str, Any],
    candidate_markdown: str,
    baseline_json: bytes,
    baseline_markdown: bytes,
) -> dict[str, Any]:
    candidate = validate_report(candidate_report)
    candidate_json = serialize_report(candidate)
    if render_markdown(candidate) != candidate_markdown:
        _fail("evaluation_v2_report_invalid")
    try:
        baseline = validate_report(json.loads(baseline_json))
        baseline_markdown_text = baseline_markdown.decode("utf-8")
    except (
        EvaluationV2ValidationError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        _fail("evaluation_v2_baseline_invalid")
    if render_markdown(baseline) != baseline_markdown_text:
        _fail("evaluation_v2_baseline_invalid")
    candidate_pairs = {pair["case_id"]: pair for pair in candidate["pairs"]}
    baseline_pairs = {pair["case_id"]: pair for pair in baseline["pairs"]}
    changed = [
        case_id
        for case_id in CASE_IDS
        if candidate_pairs.get(case_id) != baseline_pairs.get(case_id)
    ]
    false_green = [
        pair["case_id"]
        for pair in candidate["pairs"]
        if not pair["negative_control_sensitivity"]
    ]
    observed = [
        pair["observed_control_finding"] for pair in candidate["pairs"]
    ]
    unexpected = [
        code
        for pair in candidate["pairs"]
        for code in pair["unexpected_blocking_finding_codes"]
    ]
    comparison = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "match": candidate_json == baseline_json
        and candidate_markdown.encode("utf-8") == baseline_markdown,
        "gate_passed": candidate["summary"]["gate_passed"],
        "changed_case_ids": changed,
        "false_green_case_ids": false_green,
        "observed_declared_control_finding_codes": observed,
        "unexpected_blocking_finding_codes": unexpected,
    }
    try:
        return validate_comparison(comparison)
    except EvaluationV2ValidationError:
        _fail("evaluation_v2_baseline_invalid")


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        _fail("evaluation_v2_cli_invalid")


def _parser() -> _ArgumentParser:
    parser = _ArgumentParser(prog="agent_evaluation_v2_gate.py")
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        parser_class=_ArgumentParser,
    )
    build = subparsers.add_parser("build")
    build.add_argument("--json-output", type=Path, required=True)
    build.add_argument("--markdown-output", type=Path, required=True)
    subparsers.add_parser("check")
    return parser


def _error(code: str) -> int:
    sys.stderr.write(
        json.dumps(
            {"status": "invalid", "code": code},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    )
    return 1


def _read_baseline(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        _fail("evaluation_v2_baseline_invalid")


async def _run(args: argparse.Namespace) -> int:
    report = await build_report()
    markdown = render_markdown(report)
    if args.command == "build":
        write_artifacts_atomically(
            report,
            markdown,
            json_output=args.json_output,
            markdown_output=args.markdown_output,
        )
        sys.stdout.write(
            json.dumps(
                {"status": "built", "gate_passed": report["summary"]["gate_passed"]},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        )
        return 0
    comparison = compare_artifacts(
        report,
        markdown,
        _read_baseline(BASELINE_JSON_PATH),
        _read_baseline(BASELINE_MARKDOWN_PATH),
    )
    sys.stdout.write(
        json.dumps(
            comparison,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    )
    return 0 if comparison["match"] and comparison["gate_passed"] else 1


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        return asyncio.run(_run(args))
    except EvaluationV2GateError as exc:
        return _error(exc.code)
    except EvaluationV2ValidationError as exc:
        return _error(exc.code)
    except Exception:
        return _error("evaluation_v2_internal_error")


if __name__ == "__main__":
    raise SystemExit(main())
