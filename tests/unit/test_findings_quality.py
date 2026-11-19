"""Bad-case intake and provider-free findings quality evaluation."""
import copy
import json
from pathlib import Path

import pytest

from test_research_findings_consumer import package, rehash


def intake_arguments(tmp_path, delivery, *selection):
    path = tmp_path / "delivery.json"
    path.write_text(json.dumps(delivery), encoding="utf-8")
    return ["intake", "--delivery", str(path), "--reason", "Check the draft's scope",
            "--output", str(tmp_path / "suspect.json"), *selection]


def test_intake_preserves_the_report_identity_and_every_exact_reference(tmp_path):
    from scripts.findings_quality import main

    delivery = package()
    second = copy.deepcopy(delivery["report"]["findings"][0]["references"][0])
    second.update(excerpt="material", excerpt_start=13, excerpt_end=21)
    delivery["report"]["findings"][0]["references"].append(second)
    rehash(delivery)
    args = intake_arguments(tmp_path, delivery, "--question-id", "q1", "--finding-id", "f1",
                            "--expected-behavior", "Limit the statement to the source version.")
    assert main(args) == 0
    output = tmp_path / "suspect.json"
    first_bytes = output.read_bytes()
    case = json.loads(first_bytes)
    assert case["run_id"] == "run_fixture"
    assert case["report_hash"] == delivery["artifact"]["content_hash"]
    assert case["finding_id"] == "f1"
    assert case["statement"] == "Candidate"
    assert case["expected_behavior"] == "Limit the statement to the source version."
    assert [(ref["excerpt"], ref["excerpt_start"], ref["excerpt_end"]) for ref in case["references"]] == [
        ("observed", 4, 12), ("material", 13, 21)]
    assert all(ref["snippet"] == "A 🧪 observed material." for ref in case["references"])
    assert all(ref["evidence_id"].startswith("ev_run_fixture_") for ref in case["references"])
    assert main(args) == 0
    assert output.read_bytes() == first_bytes
    different = [item if item != "Check the draft's scope" else "Different observation" for item in args]
    assert main(different) == 1
    assert output.read_bytes() == first_bytes

    delivery["report"]["findings"][0]["statement"] = "Revised"
    rehash(delivery)
    (tmp_path / "delivery.json").write_text(json.dumps(delivery), encoding="utf-8")
    new_target = tmp_path / "revision.json"
    assert main([str(new_target) if item == str(output) else item for item in args]) == 0
    assert json.loads(new_target.read_bytes())["case_id"] != case["case_id"]


def test_intake_accepts_an_unresolved_question_without_a_finding(tmp_path):
    from scripts.findings_quality import main

    delivery = package()
    delivery["report"]["questions"].append({"question_id": "q2", "text": "What is the measured availability?"})
    delivery["report"]["dispositions"].append(
        {"question_id": "q2", "status": "unresolved", "reason": "The sources give no measurements."})
    rehash(delivery)
    assert main(intake_arguments(tmp_path, delivery, "--question-id", "q2")) == 0
    case = json.loads((tmp_path / "suspect.json").read_bytes())
    assert case["finding_id"] is None
    assert case["statement"] is None
    assert case["references"] == []
    assert case["disposition"]["reason"] == "The sources give no measurements."
    assert len(case["accepted_dispositions"]) == 2


@pytest.mark.parametrize("defect", ["artifact", "foreign_evidence", "missing_finding", "absent_question"])
def test_intake_rejects_invalid_delivery_or_selection(tmp_path, defect):
    from scripts.findings_quality import main

    delivery = package()
    selection = ["--question-id", "q1", "--finding-id", "f1"]
    if defect == "artifact":
        delivery["artifact"]["content_hash"] = "0" * 64
    elif defect == "foreign_evidence":
        delivery["evidence"][0]["run_id"] = "different-run"
    elif defect == "missing_finding":
        selection = ["--question-id", "q1"]
    else:
        selection = ["--question-id", "q2", "--finding-id", "f1"]
    assert main(intake_arguments(tmp_path, delivery, *selection)) == 1
    assert not (tmp_path / "suspect.json").exists()


def cited_case(case_id, statement):
    excerpt = "The feature requires release 2."
    return {"case_id": case_id, "family": "fixture", "split": "development", "origin": "synthetic_control",
            "question": {"question_id": "q1", "text": "Which release is required?"},
            "statement": statement, "references": [
                {"source_url": "https://example.com/requirements", "source_identity": "https://example.com/requirements",
                 "source_version": "2", "snippet": "Release requirements. " + excerpt, "excerpt": excerpt,
                 "excerpt_start": 22, "excerpt_end": 53}],
            "diagnosis": {"status": "unobserved", "earliest_stage": None, "basis": "fixture", "locator": None}}


def judgement(verdict, references=("R1",)):
    return {"verdict": verdict, "matched_reference_ids": list(references), "rationale": "Evaluate release scope.",
            "parts": [{"assertion": "release required", "reference_ids": list(references),
                       "rationale": "Compare against the exact passage."}]}


def outcome(task, arm, state, *, claims=(), unresolved=False):
    dispositions = ([{"question_id": "q1", "status": "unresolved", "reason": "No answer found.", "justified": False}]
                    if unresolved else [{"question_id": "q1", "status": "candidate_findings"}])
    return {"task_id": task, "arm": arm, "outcome": state, "basis": "scripted_fixture",
            "run_id": None, "resources": {}, "claims": [
                {"case_id": case_id, "covered_points": points, "new_material": new, "forbidden_matches": []}
                for case_id, points, new in claims], "dispositions": dispositions if state == "delivered" else []}


def eval_inputs():
    from scripts.findings_quality import digest
    from scripts.findings_quality_replay import judge_input

    cases = [cited_case("right", "Release 2 is a prerequisite."),
             cited_case("wrong", "The feature works with release 1."),
             cited_case("partial", "The feature requires release 2 and a US address."),
             cited_case("conflict", "Release 2 is required across all locations."),
             cited_case("broken", "The feature requires release 2."),
             cited_case("failed", "Release 1 alone suffices.")]
    ref = cases[3]["references"][0]
    other = "Release 2 is not required."
    cases[3]["references"].append({**ref, "source_url": "https://example.com/exemption",
        "source_identity": "https://example.com/exemption", "snippet": other, "excerpt": other, "excerpt_start": 0,
        "excerpt_end": len(other)})
    cases[4]["references"][0]["excerpt"] = "A fabricated excerpt."
    second_answer = cited_case("appendix", "The appendix requires release 2.")
    second_answer["question"] = {"question_id": "q2", "text": "Which release does the appendix require?"}
    cases.append(second_answer)
    receipts = []
    for case, verdict in zip(cases[:4], ["supported", "contradicted", "insufficient_evidence", "conflicting_evidence"]):
        values = ("R1", "R2") if verdict == "conflicting_evidence" else ("R1",)
        receipts.append({"input_sha256": digest(judge_input(case)), "model": "recorded-test-judge",
                         "rubric_version": "v1-test", "outcome": "completed", "basis": "scripted_fixture",
                         "judgment": judgement(verdict, values), "resources": {}})
    receipts.append({"input_sha256": digest(judge_input(cases[5])), "model": "recorded-test-judge",
                     "rubric_version": "v1-test", "outcome": "timeout", "basis": "scripted_fixture",
                     "judgment": None, "resources": {}})
    receipts.append({"input_sha256": digest(judge_input(second_answer)), "model": "recorded-test-judge",
                     "rubric_version": "v1-test", "outcome": "completed", "basis": "scripted_fixture",
                     "judgment": judgement("supported"), "resources": {}})
    rubric = [{"question_id": "q1", "text": "Which release is required?",
               "required_points": [{"point_id": "release", "text": "Release 2 is required."}],
               "unresolved_expectation": None, "forbidden_claims": []}]
    experiment = {"schema_version": "dra.findings-quality.experiment.v1",
                  "judge": {"model": "recorded-test-judge", "rubric_version": "v1-test"},
                  "tasks": [{"task_id": key, "rubric": rubric} for key in ("regression", "gap")]}
    experiment["tasks"].append({"task_id": "abstain", "rubric": rubric + [
        {**rubric[0], **second_answer["question"]},
    ]})
    rows = [outcome("regression", "A", "delivered", claims=[("right", ["release"], False)]),
            outcome("regression", "B", "delivered", claims=[("wrong", [], True)]),
            outcome("gap", "A", "report_absent"), outcome("gap", "B", "not_started"),
            outcome("abstain", "A", "delivered", unresolved=True, claims=[("appendix", ["release"], False)]),
            outcome("abstain", "B", "delivered", unresolved=True, claims=[("appendix", ["release"], False)])]
    for row in rows[-2:]:
        row["dispositions"].append({"question_id": "q2", "status": "candidate_findings"})
    annotations = [{"case_id": c["case_id"], "verdict": v, "authority": "synthetic_expectation",
                    "rationale": "Synthetic rubric.", "reviewer": None, "review_date": None, "blind_review": True}
                   for c, v in zip(cases, ["supported", "contradicted", "insufficient_evidence", "conflicting_evidence"])]
    return cases, annotations, [], experiment, rows, receipts


def test_replay_preserves_semantics_structure_and_execution_denominators():
    from scripts.findings_quality_replay import evaluate

    result = evaluate(*eval_inputs(), reviews=[])
    scored = {row["case_id"]: row for row in result["cases"]}
    assert [scored[key]["verdict"] for key in ("right", "wrong", "partial", "conflict")] == [
        "supported", "contradicted", "insufficient_evidence", "conflicting_evidence"]
    assert scored["broken"]["outcome"] == "structural_error"
    assert scored["failed"]["outcome"] == "judge_timeout"
    assert scored["failed"]["verdict"] is None
    assert result["calibration"]["reviewed"] == 0
    assert result["calibration"]["accuracy"] is None
    assert result["generation"]["counts"] == {
        "planned": 6, "started": 5, "delivered": 4, "scorable": 4, "unscored": 2, "comparable": 2}
    assert result["generation"]["pair_counts"] == {"both_pass": 0, "a_only": 1, "b_only": 0, "neither_pass": 1}
    assert result["generation"]["regressions"] == ["regression"]
    assert result["generation"]["wrong_refusals"] == 2
    assert result["generation"]["supported_coverage"] == {
        "supported": 3, "planned": 8, "delivered": 6, "assessed": 6, "unassessed": 0, "rate_assessed": 0.5,
    }
    assert result["generation"]["resources"]["input_tokens"]["total"] is None
    assert result["decision"]["status"] == "insufficient_evidence"


def test_replay_can_retain_arm_scores_without_comparing_generation():
    from scripts.findings_quality_replay import evaluate

    generation = evaluate(*eval_inputs(), reviews=[], compare_generation=False)["generation"]
    pair = next(pair for pair in generation["pairs"] if pair["task_id"] == "regression")
    assert pair["A"]["passed"] is True
    assert pair["B"]["passed"] is False
    assert all(pair["comparison"] is None for pair in generation["pairs"])
    assert generation["counts"]["scorable"] == 4
    assert generation["counts"]["comparable"] == 0
    assert all(value == 0 for value in generation["pair_counts"].values())
    assert generation["fixes"] == generation["regressions"] == []


@pytest.mark.parametrize(
    "judge_outcomes, coverage_pending, supported, unassessed, passed",
    [
        (("completed", "timeout"), False, ["release"], ["account"], None),
        (("completed", "completed"), False, ["account", "release"], [], True),
        (("timeout", "timeout"), False, [], ["account", "release"], None),
        (("completed", "completed"), True, [], ["account", "release"], None),
    ],
    ids=["one-timeout", "full-success", "all-unknown", "coverage-pending"],
)
def test_replay_counts_assessed_points_independently_of_task_pass(
    judge_outcomes, coverage_pending, supported, unassessed, passed,
):
    from scripts.findings_quality import digest
    from scripts.findings_quality_replay import evaluate, judge_input

    required = {"release": "Release 2 is required.", "account": "An active account is required."}
    question = {"question_id": "q1", "text": "What are the release and account requirements?"}
    judge = {"model": "recorded-test-judge", "rubric_version": "v1-test"}
    cases, receipts = [], []
    for (point, statement), judge_outcome in zip(required.items(), judge_outcomes, strict=True):
        case = cited_case(point, statement)
        case["question"] = question
        case["references"][0].update(snippet=statement, excerpt=statement,
                                      excerpt_start=0, excerpt_end=len(statement))
        cases.append(case)
        receipts.append({
            **judge, "input_sha256": digest(judge_input(case)), "basis": "scripted_fixture",
            "outcome": judge_outcome, "judgment": judgement("supported") if judge_outcome == "completed" else None,
        })
    rubric = {**question, "required_points": [{"point_id": point, "text": text} for point, text in required.items()],
              "unresolved_expectation": None, "forbidden_claims": []}
    experiment = {"schema_version": "dra.findings-quality.experiment.v1", "judge": judge,
                  "tasks": [{"task_id": "requirements", "rubric": [rubric]}]}
    claims = [(point, [] if coverage_pending else [point], False) for point in required]
    row = outcome("requirements", "A", "delivered", claims=claims)
    row["coverage_review_pending"] = coverage_pending

    generation = evaluate(cases, [], [], experiment, [row], receipts, reviews=[])["generation"]
    arm = generation["pairs"][0]["A"]
    assert arm["passed"] is passed
    assert generation["pairs"][0]["comparison"] is None
    assert generation["counts"]["scorable"] == int(passed is not None)
    assert arm["questions"][0]["supported_points"] == supported
    assert generation["supported_coverage"] == {
        "supported": len(supported), "planned": 4, "delivered": 2,
        "assessed": len(supported), "unassessed": len(unassessed), "rate_assessed": 1.0 if supported else None,
    }
    assert arm["questions"][0]["missing_points"] == []
    assert arm["questions"][0]["unassessed_points"] == unassessed
    assert arm["questions"][0]["unscored_claims"] == sorted(
        point for point, state in zip(required, judge_outcomes, strict=True) if state == "timeout"
    )


def test_judge_receipts_reject_invented_evidence_and_blind_payload_excludes_labels():
    from scripts.findings_quality import QualityError
    from scripts.findings_quality_replay import judge_input, validate_judgment

    case = cited_case("control-with-invented-label", "Release 2 is required.")
    case.update(verdict="supported", arm="B", expected_behavior="Do not disclose.", gold=["anything"])
    blind = judge_input(case)
    assert set(blind) == {"question", "statement", "citations"}
    assert set(blind["citations"][0]) == {"reference_id", "source_url", "source_version", "excerpt"}
    assert "Release requirements." not in json.dumps(blind)
    with pytest.raises(QualityError, match="reference"):
        validate_judgment(blind, judgement("supported", ["R37"]))


def test_only_completed_human_review_matches_enter_four_class_calibration():
    from scripts.findings_quality_replay import evaluate

    base = evaluate(*eval_inputs(), reviews=[])
    review_ids = {case["case_id"]: case["review_id"] for case in base["cases"]}
    reviews = [{"review_id": review_ids[key], "verdict": verdict, "reviewer": "Fixture reviewer",
                "review_date": "2026-11-18", "rationale": "Independently assessed for this test.",
                "blind": True} for key, verdict in (("right", "insufficient_evidence"), ("wrong", "supported"))]
    result = evaluate(*eval_inputs(), reviews=reviews)
    assert result["calibration"]["reviewed"] == 2
    assert result["calibration"]["compared"] == 0
    assert result["calibration"]["accuracy"] is None
    assert all(row["outcome"] == "scripted_prediction" for row in result["calibration"]["unavailable"])
    cases, annotations, historical, experiment, _, records = eval_inputs()
    observed = [{**record, "basis": "live_judge"} for record in records]
    result = evaluate(cases, annotations, historical, experiment, [], observed, reviews=reviews, execution_mode="live")
    assert result["calibration"]["compared"] == 2
    assert result["calibration"]["false_passes"] == {"count": 1, "denominator": 1}
    assert result["calibration"]["false_alarms"] == {"count": 1, "denominator": 1}
    assert result["calibration"]["confusion"]["insufficient_evidence"]["supported"] == 1
    assert result["calibration"]["confusion"]["supported"]["contradicted"] == 1
    assert result["calibration"]["uncovered_categories"] == ["contradicted", "conflicting_evidence"]


def test_replay_outputs_are_stable_under_reordered_input_records(tmp_path):
    from scripts.findings_quality_replay import evaluate, write_report

    cases, annotations, historical, experiment, rows, receipts = eval_inputs()
    for record, elapsed in zip(receipts, [1e15, 0.1, 0.2]):
        record["resources"]["elapsed_seconds"] = elapsed
    a = evaluate(cases, annotations, historical, experiment, rows, receipts, reviews=[])
    shuffled = {**experiment, "tasks": list(reversed(experiment["tasks"]))}
    b = evaluate(cases[::-1], annotations[::-1], historical, shuffled, rows[::-1], receipts[::-1], reviews=[])
    write_report(tmp_path / "a", a)
    write_report(tmp_path / "b", b)
    for filename in ["report.json", "report.md", "blind-review.json", "blind-review.md"]:
        assert (tmp_path / "a" / filename).read_bytes() == (tmp_path / "b" / filename).read_bytes()
    rendered = (tmp_path / "a" / "report.md").read_text()
    assert "The feature works with release 1." in rendered
    assert "The feature requires release 2." in rendered
    assert "[wrong](#case-wrong)" in rendered


def test_diagnostics_distinguish_unobserved_from_completed_zero_and_find_earliest_deviation():
    from scripts.findings_quality_replay import evaluate

    absent = {"case_id": "known-no-delivery", "run_id": "r-known", "primary_artifact_available": False,
              "source_calls": {"state": "completed", "count": 0, "locator": "source summary"},
              "steps": [{"stage": "generation", "result": "deviation", "locator": "call 8", "basis": "No report."},
                        {"stage": "capture", "result": "deviation", "locator": "call 4", "basis": "No passage captured."}]}
    unknown = {"case_id": "other-no-delivery", "run_id": "r-unknown", "primary_artifact_available": False,
               "source_calls": {"state": "unobserved", "count": None}, "steps": []}
    report = evaluate(*eval_inputs(), reviews=[], diagnostics=[unknown, absent])
    known, unknown = report["execution_only"]
    assert known["execution_observation"]["signals"] == ["zero_source_calls"]
    assert known["diagnosis"] == {"status": "confirmed", "earliest_stage": "capture",
                                  "basis": "No passage captured.", "locator": "call 4"}
    assert unknown["execution_observation"]["source_calls"]["count"] is None
    assert unknown["execution_observation"]["signals"] == []
    assert unknown["diagnosis"]["status"] == "unobserved"
    assert report["case_origins"] == {"synthetic_control": 7}


def test_replay_entrypoint_runs_without_network_and_preserves_existing_outputs(tmp_path):
    import os
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    filenames = ("cases", "annotations", "historical", "experiment", "generation", "judge")
    for filename, value in zip(filenames, eval_inputs()):
        (dataset / f"{filename}.json").write_text(json.dumps(value), encoding="utf-8")
    guard = tmp_path / "sitecustomize.py"
    guard.write_text(
        "import socket\n"
        "def forbidden(*args, **kwargs):\n    raise AssertionError('network in offline replay')\n"
        "socket.create_connection = socket.socket.connect = socket.socket.connect_ex = forbidden\n",
        encoding="utf-8",
    )
    stub_path = os.pathsep.join(filter(None, (str(tmp_path), os.environ.get("PYTHONPATH"))))
    env = {key: value for key, value in os.environ.items() if not key.endswith(("_API_KEY", "_API_TOKEN"))}
    env.update(PYTHONPATH=stub_path, PYTHON_DOTENV_DISABLED="1", LANGSMITH_TRACING="false",
               LANGCHAIN_TRACING_V2="false")
    command = [sys.executable, str(root / "scripts/findings_quality.py"), "replay", "--dataset", str(dataset),
               "--output-dir"]
    for name in ("a", "b"):
        process = subprocess.run([*command, str(tmp_path / name)], env=env, cwd=tmp_path, capture_output=True, timeout=15)
        assert process.returncode == 0, process.stderr.decode()
    for name in ("report.json", "report.md", "blind-review.json", "blind-review.md"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
    existing = tmp_path / "a" / "report.json"
    existing.write_text("Another observation", encoding="utf-8")
    process = subprocess.run([*command, str(tmp_path / "a")], env=env, capture_output=True, timeout=15)
    assert process.returncode == 1
    assert existing.read_text() == "Another observation"


def test_scripted_replay_rejects_rows_claiming_live_generation():
    from scripts.findings_quality_io import QualityError
    from scripts.findings_quality_replay import evaluate

    cases, annotations, historical, experiment, rows, receipts = eval_inputs()
    for row in rows:
        row["basis"] = "live_generation"
    with pytest.raises(QualityError, match="provenance"):
        evaluate(cases, annotations, historical, experiment, rows, receipts, reviews=[])


def test_budget_block_before_a_request_keeps_arm_unstarted():
    from scripts.findings_quality_replay import evaluate

    cases, annotations, historical, experiment, rows, receipts = eval_inputs()
    row = next(item for item in rows if (item["task_id"], item["arm"]) == ("gap", "B"))
    row.update(outcome="budget_exhausted", resources={"calls": 0})
    result = evaluate(cases, annotations, historical, experiment, rows, receipts, reviews=[])
    assert result["generation"]["counts"]["started"] == 5
    assert result["generation"]["outcomes"]["budget_exhausted"] == 1


def test_an_all_abstain_candidate_cannot_be_replayed_as_a_delivered_report():
    from scripts.findings_quality_io import QualityError
    from scripts.findings_quality_replay import evaluate

    cases, annotations, historical, experiment, rows, receipts = eval_inputs()
    row = next(item for item in rows if item["task_id"] == "abstain" and item["arm"] == "A")
    row["claims"] = []
    row["dispositions"][1] = {"question_id": "q2", "status": "unresolved", "reason": "Unanswered.", "justified": False}
    with pytest.raises(QualityError, match="at least one finding"):
        evaluate(cases, annotations, historical, experiment, rows, receipts, reviews=[])
    row.update(outcome="structural_error", dispositions=[])
    report = evaluate(cases, annotations, historical, experiment, rows, receipts, reviews=[])
    assert report["generation"]["outcomes"]["structural_error"] == 1
    assert report["generation"]["counts"]["comparable"] == 1
