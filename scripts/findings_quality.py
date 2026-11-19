"""Intake and replay for the local findings quality benchmark."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.findings_quality_io import QualityError, digest, json_bytes, read_json, write_new
from scripts.research_findings_consumer import ConsumerError, validate_delivery


def build_bad_case(package: dict, *, question_id: str, finding_id: str | None,
                   reason: str, expected_behavior: str | None, origin: str = "actual_local_run") -> dict:
    if not reason.strip() or (expected_behavior is not None and not expected_behavior.strip()):
        raise QualityError("intake reason and any expected behavior must be nonblank")
    run_id = package.get("run_id")
    if type(run_id) is not str or not run_id.strip() or len(run_id) > 500:
        raise QualityError("invalid delivery run ID")
    receipt = validate_delivery(package, run_id)
    report = package["report"]
    questions = {row["question_id"]: row for row in report["questions"]}
    dispositions = {row["question_id"]: row for row in receipt["questions"]}
    if question_id not in questions:
        raise QualityError("question ID is absent from the delivered scope")
    disposition = dispositions[question_id]
    if finding_id is None and disposition["status"] != "unresolved":
        raise QualityError("a finding ID is required for a question with findings")
    if finding_id is not None and finding_id not in disposition["finding_ids"]:
        raise QualityError("finding ID is absent from the selected question")
    finding = next((row for row in report["findings"] if row["finding_id"] == finding_id), None)
    identity = {"run_id": run_id, "question_id": question_id, "finding_id": finding_id,
                "report_hash": receipt["artifact"]["content_hash"]}
    return {
        "schema_version": "dra.findings-quality.bad-case.v1",
        "case_id": "bad-" + digest(identity),
        "origin": origin,
        "label_authority": "unreviewed",
        **identity,
        "question": questions[question_id],
        "statement": finding["statement"] if finding else None,
        "references": finding["references"] if finding else [],
        "accepted_questions": report["questions"],
        "accepted_dispositions": receipt["questions"],
        "disposition": disposition,
        "observation": {"signal": "operator_report", "basis": reason},
        "expected_behavior": expected_behavior,
        "diagnosis": {"status": "unobserved", "earliest_stage": None,
                      "basis": "Delivery validation established structure and exact binding.",
                      "locator": receipt["artifact"]["artifact_id"]},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    intake = commands.add_parser("intake", help="Register a suspect delivered finding or unresolved question.")
    intake.add_argument("--delivery", required=True, type=Path)
    intake.add_argument("--question-id", required=True)
    intake.add_argument("--finding-id")
    intake.add_argument("--reason", required=True)
    intake.add_argument("--expected-behavior")
    intake.add_argument("--output", required=True, type=Path)
    intake.add_argument("--origin", choices=("actual_local_run", "synthetic_control"), default="actual_local_run")
    replay = commands.add_parser("replay", help="Write the deterministic offline comparison and blind review sheet.")
    replay_source = replay.add_mutually_exclusive_group(required=True)
    replay_source.add_argument("--dataset", type=Path)
    replay_source.add_argument("--recorded-live", type=Path)
    replay.add_argument("--output-dir", required=True, type=Path)
    replay.add_argument("--case", action="append", type=Path, default=[])
    replay.add_argument("--observation", action="append", type=Path, default=[])
    replay.add_argument("--reviews", type=Path)
    replay.add_argument("--generation-reviews", type=Path)
    live = commands.add_parser("run-live", help="Execute the separately approved public generator and Judge experiment.")
    live.add_argument("--output-dir", required=True, type=Path)
    live.add_argument("--allow-live", action="store_true")
    live.add_argument("--approval", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "run-live":
            from scripts.findings_quality_live import run_live
            from scripts.findings_quality_transport import LiveCallError

            try:
                status = run_live(args.output_dir, allow_live=args.allow_live, approval=args.approval)
            except LiveCallError as exc:
                status = exc.code
            print(status)
            return int(status != "completed")
        if args.command == "replay":
            from scripts.findings_quality_replay import load_replay, write_report

            if args.recorded_live:
                from scripts.findings_quality_live import replay_capture

                if args.case or args.observation:
                    raise QualityError("case intake and receipt observations require a frozen dataset replay")
                result = replay_capture(args.recorded_live, reviews=read_json(args.reviews) if args.reviews else [],
                                        generation_reviews=read_json(args.generation_reviews) if args.generation_reviews else [])
            else:
                if args.generation_reviews:
                    raise QualityError("generation reviews require a captured generation run")
                result = load_replay(args.dataset, case_paths=args.case, review_path=args.reviews,
                                     observation_paths=args.observation)
            write_report(args.output_dir, result)
            return 0
        package = read_json(args.delivery)
        if not isinstance(package, dict):
            raise QualityError("delivery must be a JSON object")
        case = build_bad_case(package, question_id=args.question_id, finding_id=args.finding_id,
                              reason=args.reason, expected_behavior=args.expected_behavior, origin=args.origin)
        write_new(args.output, json_bytes(case), idempotent=True)
        print(case["case_id"])
        return 0
    except (ConsumerError, QualityError) as exc:
        print(str(exc), file=sys.stderr)
    except (OSError, ValueError, KeyError, AttributeError, TypeError, RecursionError):
        print("invalid local evaluation input or output", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
