"""Deterministic replay of findings, blinded judgments and paired task outcomes."""
from __future__ import annotations

from collections import Counter
from datetime import date
import html
import math
from pathlib import Path
import re

from scripts.findings_quality_io import QualityError, digest, json_bytes, read_json, write_new
from scripts.research_findings_consumer import _public_source_url

VERDICTS = ("supported", "contradicted", "insufficient_evidence", "conflicting_evidence")
STAGES = ("source_retrieval", "capture", "coordinator_transfer", "generation", "application_binding", "evaluator")
RESOURCES = ("calls", "input_tokens", "output_tokens", "elapsed_seconds", "estimated_microusd")
ID = re.compile(r"[a-zA-Z0-9_-]{1,100}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
JUDGE_OUTCOMES = ("completed", "timeout", "provider_failure", "invalid_response", "not_started", "budget_exhausted")
GENERATION_OUTCOMES = ("delivered", "report_absent", "not_started", "structural_error", "timeout",
                       "provider_failure", "invalid_response", "budget_exhausted", "filtered", "declined", "local_experiment_failure")


def _require(condition, message):
    if not condition:
        raise QualityError(message)


def _text(value, maximum=4096):
    return type(value) is str and bool(value.strip()) and len(value) <= maximum


def _identifier(value):
    return type(value) is str and ID.fullmatch(value) is not None


def _index(rows, key):
    _require(type(rows) is list, "evaluation rows must be a list")
    result = {}
    for row in rows:
        identity = key(row)
        _require(identity not in result, "duplicate evaluation identity")
        result[identity] = row
    return result


def judge_input(case):
    """Return the exact message contents admitted to a blind evaluator."""
    _require(_text(case["question"]["text"]) and _text(case["statement"], 2000), "invalid claim or question")
    refs = case["references"]
    _require(type(refs) is list and 1 <= len(refs) <= 10, "invalid cited reference count")
    citations = []
    for index, ref in enumerate(refs, 1):
        url = ref["source_url"]
        snippet, excerpt = ref["snippet"], ref["excerpt"]
        start, end = ref["excerpt_start"], ref["excerpt_end"]
        _require(_public_source_url(url) and ref["source_identity"] == url
                 and _text(snippet, 1024 * 1024) and _text(excerpt, 1000)
                 and type(start) is int and type(end) is int and 0 <= start < end <= len(snippet)
                 and snippet[start:end] == excerpt and snippet.find(excerpt) == start
                 and snippet.find(excerpt, start + 1) == -1, "invalid cited reference or exact excerpt")
        version = ref.get("source_version")
        _require(version is None or _text(version, 256), "invalid cited source version")
        citations.append({"reference_id": f"R{index}", "source_url": url, "source_version": version, "excerpt": excerpt})
    return {"question": case["question"]["text"], "statement": case["statement"], "citations": citations}


def validate_judgment(blind, judgment):
    """Admit judgments only when every reported reference is in the blind request."""
    _require(type(judgment) is dict and set(judgment) == {"verdict", "matched_reference_ids", "rationale", "parts"}
             and judgment["verdict"] in VERDICTS and _text(judgment["rationale"], 1500), "invalid Judge output")
    valid = {ref["reference_id"] for ref in blind["citations"]}

    def references(value, allowed):
        _require(type(value) is list and all(type(item) is str and item in allowed for item in value)
                 and len(value) == len(set(value)), "invalid Judge reference IDs")
        return set(value)

    matched = references(judgment["matched_reference_ids"], valid)
    parts = judgment["parts"]
    _require(type(parts) is list and 1 <= len(parts) <= 20, "invalid Judge material parts")
    used = set()
    for part in parts:
        _require(type(part) is dict and set(part) == {"assertion", "reference_ids", "rationale"}
                 and _text(part["assertion"], 1000) and _text(part["rationale"], 1500), "invalid Judge material part")
        used.update(references(part["reference_ids"], matched))
    _require(matched == used and (matched or judgment["verdict"] == "insufficient_evidence"),
             "Judge references must match the cited material parts")
    _require(judgment["verdict"] != "conflicting_evidence" or len(matched) >= 2,
             "conflicting evidence requires competing references")
    _require(judgment["verdict"] != "supported" or all(part["reference_ids"] for part in parts),
             "each supported material part requires a reference")
    return judgment


def _resources(row):
    values = row.get("resources", {})
    result = {}
    for key in RESOURCES:
        value = values.get(key)
        _require(value is None or (
            type(value) in ({int, float} if key == "elapsed_seconds" else {int})
            and 0 <= value <= 10**15 and math.isfinite(value)
        ), "invalid resource observation")
        result[key] = value
    return result


def _resource_totals(rows):
    result = {}
    for name in RESOURCES:
        available = [row["resources"][name] for row in rows if row["resources"][name] is not None]
        total = (math.fsum(available) if name == "elapsed_seconds" else sum(available)) if available else None
        result[name] = {"total": total, "observed": len(available), "rows": len(rows)}
    return result


def _review_rows(rows, blind_ids):
    reviews = _index(rows, lambda row: row["review_id"])
    for identity, row in reviews.items():
        _require(identity in blind_ids and row.get("blind") is True and row.get("verdict") in VERDICTS
                 and _text(row.get("reviewer"), 256) and _text(row.get("rationale"), 1500)
                 and type(row.get("review_date")) is str
                 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["review_date"])
                 and date.fromisoformat(row["review_date"]), "invalid or unbound blind human review")
    return reviews


def _matrix(scored, *, label, predicted):
    table = {truth: dict.fromkeys(VERDICTS, 0) for truth in VERDICTS}
    disagreements = []
    unavailable = []
    for row in scored:
        observed = predicted(row)
        actual = label(row)
        if observed is None:
            unavailable.append({"case_id": row["case_id"], "outcome": row["outcome"]})
            continue
        table[actual][observed] += 1
        if actual != observed:
            disagreements.append({"case_id": row["case_id"], "expected": actual, "predicted": observed})
    compared = len(scored) - len(unavailable)
    supported = sum(table["supported"].values())
    return {
        "compared": compared,
        "accuracy": sum(table[key][key] for key in VERDICTS) / compared if compared else None,
        "confusion": table,
        "false_alarms": {"count": supported - table["supported"]["supported"], "denominator": supported},
        "false_passes": {"count": sum(table[key]["supported"] for key in VERDICTS[1:]),
                         "denominator": compared - supported},
        "uncovered_categories": [key for key in VERDICTS if not sum(table[key].values())],
        "disagreements": disagreements,
        "unavailable": unavailable,
    }


def _case_result(case, annotations, receipts, review_set):
    identity = case["case_id"]
    result = {**case, "annotation": annotations.get(identity), "review_id": None, "verdict": None,
              "outcome": "judge_unobserved", "judge": None}
    if case["statement"] is None and case.get("disposition", {}).get("status") == "unresolved":
        return {**result, "outcome": "question_unresolved"}
    try:
        blind = judge_input(case)
    except (QualityError, KeyError, TypeError):
        return {**result, "outcome": "structural_error"}
    input_hash = digest(blind)
    result["judge_input_sha256"] = input_hash
    annotation = annotations.get(identity, {})
    if annotation.get("blind_review") is True or (
        case.get("schema_version") == "dra.findings-quality.bad-case.v1" and case.get("review_group") != "generation"
    ):
        result["review_id"] = input_hash
        review_set[input_hash] = blind
    if input_hash not in receipts:
        return result
    receipt = receipts[input_hash]
    result["judge"] = {"model": receipt["model"], "rubric_version": receipt["rubric_version"],
                       "basis": receipt["basis"],
                       "authority": "model_proposal" if receipt["basis"] == "live_judge" else "scripted_fixture",
                       "resources": _resources(receipt), "judgment": None}
    if receipt["outcome"] != "completed":
        return {**result, "outcome": "judge_" + receipt["outcome"]}
    try:
        judgment = validate_judgment(blind, receipt["judgment"])
    except (KeyError, TypeError, QualityError):
        return {**result, "outcome": "judge_invalid_response"}
    result["judge"]["judgment"] = judgment
    return {**result, "outcome": "scored", "verdict": judgment["verdict"]}


def _grade_arm(row, task, by_case):
    state = row["outcome"]
    _require(state in GENERATION_OUTCOMES and row["basis"] in {"scripted_fixture", "live_generation"},
             "invalid generation outcome or identity")
    resources = _resources(row)
    started = row.get("started")
    if started is None:
        started = state not in {"not_started", "filtered", "declined"} and resources["calls"] != 0
    _require(type(started) is bool and (state != "delivered" or started), "invalid arm start observation")
    result = {"arm": row["arm"], "outcome": state, "basis": row["basis"], "started": started,
              "run_id": row.get("run_id"), "report_hash": row.get("report_hash"), "resources": resources,
              "passed": None, "questions": []}
    if "candidate_retained" in row:
        result["candidate_retained"] = row["candidate_retained"]
    if state != "delivered":
        _require(not row.get("claims") and not row.get("dispositions"), "non-delivery cannot supply scorable findings")
        return result
    coverage_pending = row.get("coverage_review_pending") is True
    questions = _index(task["rubric"], lambda item: item["question_id"])
    dispositions = _index(row["dispositions"], lambda item: item["question_id"])
    _require(questions and dispositions.keys() == questions.keys(), "generation omitted an accepted question disposition")
    claims = _index(row["claims"], lambda item: item["case_id"])
    _require(claims, "delivered report requires at least one finding")
    if row["basis"] == "live_generation":
        _require(_text(row.get("run_id"), 500) and _text(row.get("report_hash"), 64)
                 and HASH.fullmatch(row["report_hash"]), "live delivery requires a run and report hash")
    per_question = {qid: [] for qid in questions}
    for identity, claim in sorted(claims.items()):
        case = by_case[identity]
        question = case["question"]
        options = questions[question["question_id"]]
        _require(question["text"] == options["text"], "finding question differs from accepted scope")
        if case.get("run_id") is not None or row["basis"] == "live_generation":
            _require(case["run_id"] == row.get("run_id") and case.get("report_hash") == row.get("report_hash"),
                     "finding is from another run or report")
        per_question[question["question_id"]].append((claim, case))

    for qid, question in sorted(questions.items()):
        disposition = dispositions[qid]
        findings = per_question[qid]
        unresolved = disposition["status"] == "unresolved"
        _require(disposition["status"] in {"unresolved", "candidate_findings"}
                 and bool(findings) is not unresolved, "generation dispositions do not match findings")
        required = set(_index(question["required_points"], lambda item: item["point_id"]))
        expect_unresolved = question["unresolved_expectation"] is not None
        _require(bool(required) is not expect_unresolved, "question must require answerable points or justified unresolved")
        forbidden = set(question["forbidden_claims"])
        covered, flagged, new, pending, unsupported = set(), set(), [], [], []
        for claim, case in findings:
            cid = case["case_id"]
            points, matches = set(claim["covered_points"]), set(claim["forbidden_matches"])
            _require(points <= required and matches <= forbidden and type(claim["new_material"]) is bool,
                     "finding assessment references an undeclared rubric point")
            if claim["new_material"]:
                new.append(cid)
            flagged.update(matches)
            if case["verdict"] == "supported":
                covered.update(points)
            elif case["verdict"] is not None or case["outcome"] == "structural_error":
                unsupported.append(cid)
            else:
                pending.append(cid)
        if unresolved:
            _require(_text(disposition.get("reason"), 2000) and disposition.get("justified") in {True, False, None},
                     "invalid unresolved assessment")
        justified = bool(unresolved and expect_unresolved and disposition.get("justified") is True)
        wrong_refusal = unresolved and bool(required)
        passed = (not flagged and not unsupported and not wrong_refusal and
                  (justified if expect_unresolved else covered == required))
        if coverage_pending or pending or (expect_unresolved and unresolved and disposition.get("justified") is None):
            passed = None
        result["questions"].append({
            "question_id": qid, "text": question["text"], "rubric": question,
            "disposition": disposition, "claim_ids": [claim["case_id"] for claim, _ in findings],
            "required_points": sorted(required),
            "supported_points": sorted(covered), "missing_points": [] if coverage_pending else sorted(required - covered),
            "coverage_review_pending": coverage_pending,
            "justified_unresolved": justified, "wrong_refusal": wrong_refusal, "unsupported_claims": unsupported,
            "new_material_claims": new, "forbidden_matches": sorted(flagged), "unscored_claims": pending, "passed": passed,
        })
    if all(question["passed"] is not None for question in result["questions"]):
        result["passed"] = all(question["passed"] for question in result["questions"])
    return result


def _compare(tasks, records, by_case, generation_basis):
    pairs, arms = [], []
    buckets = dict.fromkeys(("both_pass", "a_only", "b_only", "neither_pass"), 0)
    classifications = {(True, True): "both_pass", (True, False): "a_only",
                       (False, True): "b_only", (False, False): "neither_pass"}
    for identity, task in sorted(tasks.items()):
        results = [
            _grade_arm(records.get((identity, arm), {"arm": arm, "outcome": "not_started", "basis": generation_basis}),
                       task, by_case)
            for arm in ("A", "B")
        ]
        arms.extend(results)
        a, b = results
        comparison = classifications.get((a["passed"], b["passed"]))
        if comparison:
            _require(a["basis"] == b["basis"], "cannot compare scripted and observed generation")
            buckets[comparison] += 1
        pairs.append({"task_id": identity, "A": a, "B": b, "comparison": comparison})
    questions = [question for arm in arms for question in arm["questions"]]
    scorable = sum(arm["passed"] is not None for arm in arms)
    covered = sum(len(question["supported_points"]) for question in questions if question["passed"] is not None)
    observed_required = sum(len(question["required_points"]) for question in questions)
    assessed_required = sum(len(question["required_points"]) for question in questions
                            if question["passed"] is not None)
    planned_required = 2 * sum(len(question["required_points"])
                               for task in tasks.values() for question in task["rubric"])
    return {
        "pairs": pairs, "pair_counts": buckets,
        "counts": {"planned": len(arms), "started": sum(arm["started"] for arm in arms),
                   "delivered": sum(arm["outcome"] == "delivered" for arm in arms),
                   "scorable": scorable, "unscored": len(arms) - scorable, "comparable": sum(buckets.values())},
        "outcomes": dict(Counter(arm["outcome"] for arm in arms)),
        "fixes": [row["task_id"] for row in pairs if row["comparison"] == "b_only"],
        "regressions": [row["task_id"] for row in pairs if row["comparison"] == "a_only"],
        "wrong_refusals": sum(question["wrong_refusal"] for question in questions),
        "justified_unresolved": sum(question["justified_unresolved"] for question in questions),
        "supported_coverage": {"supported": covered, "planned": planned_required, "delivered": observed_required,
                               "assessed": assessed_required,
                               "rate_assessed": covered / assessed_required if assessed_required else None},
        "resources": _resource_totals(arms),
    }


def evaluate(cases, annotations, historical, experiment, generation, judge_records, *,
             reviews, diagnostics=(), execution_mode="scripted"):
    _require(execution_mode in {"scripted", "live"}, "invalid evaluation provenance")
    generation_basis = "scripted_fixture" if execution_mode == "scripted" else "live_generation"
    judge_basis = "scripted_fixture" if execution_mode == "scripted" else "live_judge"
    _require(experiment.get("generation", {}).get("kind", generation_basis) == generation_basis
             and all(row["basis"] == generation_basis for row in generation)
             and all(row["basis"] == judge_basis for row in judge_records),
             "evaluation data conflicts with its execution provenance")
    _require(experiment["schema_version"] == "dra.findings-quality.experiment.v1", "invalid experiment version")
    inputs = _index(cases, lambda row: row["case_id"])
    annotated = _index(annotations, lambda row: row["case_id"])
    receipts = _index(judge_records, lambda row: row["input_sha256"])
    tasks = _index(experiment["tasks"], lambda row: row["task_id"])
    runs = _index(generation, lambda row: (row["task_id"], row["arm"]))
    _require(all(_identifier(key) for key in inputs.keys() | tasks.keys())
             and annotated.keys() <= inputs.keys()
             and all(task in tasks and arm in ("A", "B") for task, arm in runs), "invalid evaluation identity")
    for value in annotated.values():
        pair = (value["authority"], value["verdict"])
        _require(pair in {("synthetic_expectation", verdict) for verdict in VERDICTS}
                 or pair == ("deterministic_structural", None), "dataset labels cannot confer human review")
    judge = experiment["judge"]
    for identity, receipt in receipts.items():
        _require(type(identity) is str and HASH.fullmatch(identity) and receipt["outcome"] in JUDGE_OUTCOMES
                 and all(receipt[key] == judge[key] for key in ("model", "rubric_version"))
                 and receipt["basis"] in {"scripted_fixture", "live_judge"}, "invalid retained Judge receipt")
    blind = {}
    case_results = [_case_result(row, annotated, receipts, blind) for _, row in sorted(inputs.items())]
    _require(receipts.keys() <= {row.get("judge_input_sha256") for row in case_results}, "Judge receipt has no matching input")
    human = _review_rows(reviews, blind)
    # Identical blind bytes are judged and counted once, even if distinct cases reuse them.
    reviewed = {}
    for row in case_results:
        review = human.get(row["review_id"])
        row["human_review"] = review
        if review:
            reviewed.setdefault(row["review_id"], row)
    reviewed_cases = list(reviewed.values())
    observed_predictions = [
        {**row, "verdict": None, "outcome": "scripted_prediction"} if row["judge"] and
        row["judge"]["basis"] == "scripted_fixture" else row for row in reviewed_cases
    ]
    calibration = {"reviewed": len(human), "selected": len(blind), "pending": len(blind) - len(human),
                   **_matrix(observed_predictions, label=lambda row: row["human_review"]["verdict"],
                             predicted=lambda row: row["verdict"])}
    calibration["predictions_by_basis"] = dict(Counter(row["judge"]["basis"] for row in reviewed_cases if row["judge"]))
    synthetic = [row for row in case_results if (row["annotation"] or {}).get("authority") == "synthetic_expectation"]
    recorded = [{"resources": _resources(row)} for row in receipts.values() if row["outcome"] != "not_started"]
    by_case = {row["case_id"]: row for row in case_results}
    execution_only = {}
    for row in sorted(diagnostics, key=lambda item: item["case_id"]):
        identity = row["case_id"]
        if identity in by_case:
            target = by_case[identity]
        else:
            _require(_identifier(identity) and _text(row.get("run_id"), 500)
                     and row.get("primary_artifact_available") is False,
                     "observations without a case must declare the missing primary artifact")
            target = execution_only.setdefault(identity, {
                "case_id": identity, "run_id": row["run_id"], "origin": "actual_local_run",
                "primary_artifact_available": False,
                "diagnosis": {"status": "unobserved", "earliest_stage": None, "basis": None, "locator": None},
            })
        _attach_diagnostics(target, row)
    generation_result = _compare(tasks, runs, by_case, generation_basis)
    return {
        "schema_version": "dra.findings-quality.report.v1",
        "judge_config": judge,
        "case_outcomes": dict(Counter(row["outcome"] for row in case_results)),
        "case_origins": dict(Counter(row["origin"] for row in case_results)),
        "cases": case_results,
        "historical_pointers": sorted(historical, key=lambda row: row["case_id"]),
        "calibration": calibration,
        "synthetic_accounting": _matrix(synthetic, label=lambda row: row["annotation"]["verdict"],
                                        predicted=lambda row: row["verdict"]),
        "evaluator_resources": _resource_totals(recorded),
        "generation": generation_result,
        "execution_only": list(execution_only.values()),
        "triage": _triage(case_results, execution_only.values(), calibration, generation_result),
        "blind_review": [{"review_id": key, **value} for key, value in sorted(blind.items())],
        "decision": {"status": "insufficient_evidence",
                     "reason": "Generation adoption requires comparable observed outputs and independent review."},
    }


def _triage(cases, execution_only, calibration, generation):
    signals = []
    for row in [*cases, *execution_only]:
        case_id = row["case_id"]
        if row.get("outcome") == "structural_error":
            signals.append({"signal": "broken_binding", "case_id": case_id, "basis": "deterministic_structure"})
        if row.get("execution_observation", {}).get("signals"):
            signals.append({"signal": "zero_source_calls", "case_id": case_id, "basis": "completed_source_observation"})
    for row in calibration["disagreements"]:
        signals.append({"signal": "reviewer_disagreement", **row, "basis": "imported_blind_human_review"})
    for pair in generation["pairs"]:
        for arm in ("A", "B"):
            for question in pair[arm]["questions"]:
                if question["missing_points"] and question["passed"] is not None:
                    signals.append({"signal": "missed_answerable_point", "task_id": pair["task_id"],
                                    "arm": arm, "question_id": question["question_id"],
                                    "points": question["missing_points"], "basis": pair[arm]["basis"]})
    return signals


def _attach_diagnostics(case, row):
    _require(case.get("run_id") and case["run_id"] == row["run_id"]
             and case.get("execution_observation") is None, "observation is duplicate or belongs to another run")
    sources = row["source_calls"]
    state, count = sources["state"], sources["count"]
    _require((state == "unobserved" and count is None) or
             (state == "completed" and type(count) is int and count >= 0 and _text(sources.get("locator"))),
             "source call count requires a completed observation")
    steps = _index(row["steps"], lambda step: step["stage"])
    for stage, step in steps.items():
        _require(stage in STAGES and step["result"] in {"normal", "deviation"} and _text(step.get("locator"))
                 and _text(step.get("basis")), "invalid execution observation")
    deviations = [steps[stage] for stage in STAGES if stage in steps and steps[stage]["result"] == "deviation"]
    case["execution_observation"] = {**row, "steps": [steps[stage] for stage in STAGES if stage in steps],
                                     "signals": ["zero_source_calls"] if state == "completed" and count == 0 else []}
    if deviations:
        first = deviations[0]
        case["diagnosis"] = {"status": "confirmed", "earliest_stage": first["stage"],
                             "basis": first["basis"], "locator": first["locator"]}


def load_replay(dataset: Path, *, case_paths=(), review_path=None, observation_paths=()):
    files = [read_json(dataset / name) for name in (
        "cases.json", "annotations.json", "historical.json", "experiment.json", "generation.json", "judge.json")]
    for path in case_paths:
        case = read_json(path)
        _require(case.get("schema_version") == "dra.findings-quality.bad-case.v1", "expected an intake record")
        files[0].append(case)
    reviews = read_json(review_path) if review_path else []
    return evaluate(*files, reviews=reviews, diagnostics=[read_json(path) for path in observation_paths])


def _cell(value):
    if value is None:
        return "—"
    text = html.escape(" ".join(str(value).split()), quote=False)
    return re.sub(r"([\\|`*_\[\]~])", r"\\\1", text)


def _table(headers, rows):
    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(row) + " |" for row in rows),
    ]


def _case_link(identity):
    return f"[{identity}](#case-{identity})"


def _render_report(report):
    gen, cal, decision = report["generation"], report["calibration"], report["decision"]
    lines = ["# Findings quality comparison", "",
             f"**Decision** {_cell(decision['status'])}. {_cell(decision['reason'])}", "",
             "## Generation", ""]
    if "native_comparison" in report:
        native = report["native_comparison"]
        lines += [f"Envelope evidence **{_cell(native['parity'])}**. Transport mode **{_cell(native['execution_mode'])}**.", ""]
    lines.extend(_table(("Planned arms", "Started", "Delivered", "Scorable", "Unscored", "Comparable pairs"),
                        [[str(gen["counts"][key]) for key in ("planned", "started", "delivered", "scorable",
                                                             "unscored", "comparable")]]))
    coverage = gen["supported_coverage"]
    lines += ["",
              f"Supported points **{coverage['supported']}** out of **{coverage['assessed']}** assessed, "
              f"**{coverage['delivered']}** delivered and **{coverage['planned']}** planned. "
              f"Wrong refusals **{gen['wrong_refusals']}**. "
              f"Justified unresolved **{gen['justified_unresolved']}**.", ""]
    lines.extend(_table(("Both pass", "Only A passes", "Only B passes", "Neither passes"),
                        [[str(gen["pair_counts"][key]) for key in ("both_pass", "a_only", "b_only", "neither_pass")]]))
    lines.append("")
    rows = []
    for pair in gen["pairs"]:
        for arm in ("A", "B"):
            row = pair[arm]
            details = []
            for question in row["questions"]:
                disposition = question["disposition"]
                links = ", ".join(_case_link(key) for key in question["claim_ids"])
                if not links:
                    links = _cell(disposition.get("reason", disposition["status"]))
                points = ("coverage pending" if question["coverage_review_pending"] else
                          f"{len(question['supported_points'])}/{len(question['required_points'])} points")
                changes = []
                if question["new_material_claims"]:
                    changes.append("new " + ", ".join(_case_link(key) for key in question["new_material_claims"]))
                if question["wrong_refusal"]:
                    changes.append("wrong refusal")
                if question["justified_unresolved"]:
                    changes.append("justified unresolved")
                details.append(" · ".join([_cell(question["question_id"]), _cell(question["text"]), points, links, *changes]))
            rows.append([_cell(pair["task_id"]), arm, _cell(row["basis"]), _cell(row["run_id"]), _cell(row["outcome"]),
                         _cell(pair["comparison"]), "<br>".join(details) or
                         ("Candidate retained" if row.get("candidate_retained") else "—")])
    lines.extend(_table(("Task", "Arm", "Basis", "Run", "Outcome", "Pair", "Questions and findings"), rows))

    lines += ["", "## Judge calibration", "",
              f"Human reviews **{cal['reviewed']}/{cal['selected']}**. Completed comparisons **{cal['compared']}**. "
              f"Accuracy **{_cell(cal['accuracy'])}**. Pending **{cal['pending']}**.", "",
              "Human verdicts are rows. Judge verdicts are columns.", ""]
    lines.extend(_table(("Human verdict", *VERDICTS),
                        [[truth, *(str(cal["confusion"][truth][predicted]) for predicted in VERDICTS)]
                         for truth in VERDICTS]))
    lines += ["", "False alarms " + _rate(cal["false_alarms"]) + ". False passes " + _rate(cal["false_passes"]) + ".",
              "Uncovered classes " + (", ".join(cal["uncovered_categories"]) or "none") + ".",
              f"Scripted verdict accounting covers **{report['synthetic_accounting']['compared']}** fixture rows.", ""]
    if cal["disagreements"] or cal["unavailable"]:
        lines.extend(_table(("Case", "Human verdict", "Judge verdict or outcome"),
                            [[_case_link(row["case_id"]), row["expected"], row["predicted"]] for row in cal["disagreements"]]
                            + [[_case_link(row["case_id"]), "—", row["outcome"]] for row in cal["unavailable"]]))
        lines.append("")

    lines += ["## Resource observations", "", "Totals include only observed values.", ""]
    lines.extend(_table(("Measure", "Generation total", "Generation observed rows", "Judge total", "Judge observed rows"),
                        [[_cell(name), _cell(gen["resources"][name]["total"]),
                          f"{gen['resources'][name]['observed']}/{gen['resources'][name]['rows']}",
                          _cell(report["evaluator_resources"][name]["total"]),
                          f"{report['evaluator_resources'][name]['observed']}/{report['evaluator_resources'][name]['rows']}"]
                         for name in RESOURCES]))
    lines += ["", "## Cases", ""]
    lines.extend(_table(("Case", "Origin", "Question", "Statement or disposition", "Judge", "Earliest observed deviation"),
                        [[_case_link(case["case_id"]), _cell(case["origin"]), _cell(case["question"]["text"]),
                          _cell(case["statement"] or case.get("disposition", {}).get("reason")),
                          _cell(case["verdict"] or case["outcome"]), _cell(case.get("diagnosis", {}).get("earliest_stage"))]
                         for case in report["cases"]]))
    for case in report["cases"]:
        identity = case["case_id"]
        lines += ["", f'<a id="case-{identity}"></a>', f"### {_cell(identity)}", "",
                  f"Question **{_cell(case['question']['question_id'])}**. {_cell(case['question']['text'])}"]
        if case.get("run_id"):
            lines += ["", f"Run {_cell(case['run_id'])}, finding {_cell(case.get('finding_id'))}, "
                          f"report hash {_cell(case.get('report_hash'))}."]
        if case.get("observation"):
            lines += ["", f"Intake signal {_cell(case['observation']['signal'])}. {_cell(case['observation']['basis'])}"]
        if case.get("expected_behavior"):
            lines += ["", f"Expected behavior. {_cell(case['expected_behavior'])}"]
        lines += ["", _cell(case["statement"] or case.get("disposition", {}).get("reason"))]
        for index, ref in enumerate(case["references"], 1):
            url = ref.get("source_url")
            source = f"[Source]({url})" if _public_source_url(url) and not re.search(r"[()<>\\]", url) else _cell(url)
            # Keep the exact bytes in JSON. Markdown may fold inline whitespace.
            lines += ["", f"**R{index}** “{_cell(ref.get('excerpt'))}” ({source}, "
                          f"version {_cell(ref.get('source_version'))}, offsets "
                          f"{_cell(ref.get('excerpt_start'))}–{_cell(ref.get('excerpt_end'))})."]
        judge = case["judge"]
        if judge and judge["judgment"]:
            judgment = judge["judgment"]
            lines += ["", f"**{_cell(judgment['verdict'])}** ({_cell(judge['basis'])}). {_cell(judgment['rationale'])}"]
            for part in judgment["parts"]:
                refs = ", ".join(part["reference_ids"]) or "—"
                lines.append(f"- {_cell(part['assertion'])} ({refs}). {_cell(part['rationale'])}")
        diagnosis = case.get("diagnosis", {})
        lines += ["", f"Diagnosis **{_cell(diagnosis.get('status'))}**. {_cell(diagnosis.get('basis'))} "
                      f"Locator {_cell(diagnosis.get('locator'))}."]
        if case.get("execution_observation"):
            observed = case["execution_observation"]["source_calls"]
            lines += ["", f"Source calls **{_cell(observed['count'])}** ({_cell(observed['state'])})."]
    if report["execution_only"]:
        lines += ["", "## Executions without a report", ""]
        lines.extend(_table(("Case", "Run", "Source calls", "Diagnosis", "Receipt locator"), [
            [_cell(row["case_id"]), _cell(row["run_id"]),
             _cell(row["execution_observation"]["source_calls"]["count"]),
             _cell(row["diagnosis"]["earliest_stage"]), _cell(row["diagnosis"]["locator"])]
            for row in report["execution_only"]]))
    if report["historical_pointers"]:
        lines += ["", "## Historical pointers", ""]
        lines.extend(_table(("Case", "Basis", "Primary artifact available"), [
            [_cell(row["case_id"]), _cell(row.get("diagnosis", {}).get("basis")),
             _cell(row.get("primary_artifact_available"))] for row in report["historical_pointers"]]))
    return "\n".join(lines) + "\n"


def _rate(values):
    return f"**{values['count']}/{values['denominator']}**" if values["denominator"] else "—"


def _render_blind(rows):
    lines = ["# Blind review sheet", "",
             "Review each statement against its cited excerpts. Record your own verdict and rationale before opening the comparison.",
             "", "Verdicts are supported, contradicted, insufficient_evidence, and conflicting_evidence.", ""]
    for row in rows:
        lines += [f"## {row['review_id']}", "", _cell(row["question"]), "", f"**{_cell(row['statement'])}**", ""]
        for ref in row["citations"]:
            lines.append(f"- {ref['reference_id']} · {_cell(ref['source_url'])} · "
                         f"{_cell(ref['source_version'])} · “{_cell(ref['excerpt'])}”")
        lines += ["", "Verdict ·", "", "Rationale ·", ""]
    return "\n".join(lines)


def write_report(output_dir: Path, report):
    files = {"report.json": json_bytes(report), "report.md": _render_report(report).encode("utf-8"),
             "blind-review.json": json_bytes(report["blind_review"]),
             "blind-review.md": _render_blind(report["blind_review"]).encode("utf-8")}
    if "generation_review_sheet" in report:
        files["generation-review-sheet.json"] = json_bytes(report["generation_review_sheet"])
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        destination = output_dir / name
        if destination.is_symlink() or (destination.exists() and destination.read_bytes() != content):
            raise QualityError("report directory holds a different result. Choose a new directory.")
    for name, content in files.items():
        write_new(output_dir / name, content, idempotent=True)
