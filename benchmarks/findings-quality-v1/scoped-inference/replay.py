"""Rebind retained public candidates and replay their frozen blind assessments."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

SUITE = Path(__file__).resolve().parent
sys.path.insert(0, str(SUITE.parents[2]))

from langchain_core.messages import AIMessage

from scripts.findings_quality import build_bad_case
from scripts.findings_quality_io import digest, json_bytes, read_json, write_new
from scripts.findings_quality_native import (
    QUALIFICATION_INSTRUCTION,
    load_native_fixture,
    rebind_captured_report,
    run_native_arm,
)
from scripts.findings_quality_replay import _grade_arm, judge_input, validate_judgment
from scripts.research_findings_consumer import validate_delivery


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def coordinator_input(request, instruction):
    messages = request.messages
    if instruction:
        system, *rest = messages
        require(system["role"] == "system", "coordinator must start with the system message")
        messages = [{**system, "content": system["content"] + "\n\n" + instruction}, *rest]
    return {"messages": messages, "tools": request.tools}


def blind_findings(fixture, source_version, delivery):
    report = delivery["report"]
    assessed = {}
    claims = []
    for finding in report["findings"]:
        fid = finding["finding_id"]
        case = build_bad_case(
            delivery, question_id=finding["question_id"], finding_id=fid,
            reason="Public comparison replay", expected_behavior=None,
        )
        case["references"] = [{**ref, "source_version": source_version} for ref in case["references"]]
        require(all("[excerpt gap]" not in ref["excerpt"] for ref in case["references"]),
                "a reference crossed an excerpt gap")
        blind = judge_input(case)
        blind["question"] = fixture.query + "\n\nAccepted question: " + blind["question"]
        assessed[fid] = (case, blind)
        claims.append({"finding_id": fid, "question_id": finding["question_id"], **blind})
    return assessed, claims


def replay_assessments(task, fixture, delivery, frozen):
    report = delivery["report"]
    assessments, claims = blind_findings(fixture, task["source_version"], delivery)
    sheet = {
        "stated_scenario": fixture.query, "questions": report["questions"],
        "dispositions": report["dispositions"], "claims": claims, "rubric": task["rubric"],
    }
    require(digest(sheet) == frozen["coverage_input_sha256"], "blind coverage input changed")
    coverage = frozen["coverage"]
    labels = {row["finding_id"]: row for row in coverage["claims"]}
    require(len(labels) == len(coverage["claims"]) and labels.keys() == assessments.keys()
            and frozen["semantic"].keys() == assessments.keys(), "finding assessment IDs do not match")
    unresolved = {row["question_id"]: row["justified"] for row in coverage["unresolved"]}
    require(len(unresolved) == len(coverage["unresolved"]) and all(type(x) is bool for x in unresolved.values())
            and unresolved.keys() == {row["question_id"] for row in report["dispositions"]
                                      if row["status"] == "unresolved"}, "unresolved assessment IDs do not match")

    cases, rows = {}, []
    for fid, (case, blind) in assessments.items():
        record = frozen["semantic"][fid]
        require(digest(blind) == record["input_sha256"], "blind semantic input changed")
        judgment = validate_judgment(blind, record["judgment"])
        label = labels[fid]
        extras = label.get("new_material_assertions", [])
        require(all(quote and quote in case["statement"] for quote in extras), "invalid new assertion quotation")
        case_id = case["case_id"]
        cases[case_id] = {**case, "outcome": "scored", "verdict": judgment["verdict"]}
        rows.append({
            "case_id": case_id, "covered_points": label["covered_points"],
            "forbidden_matches": label["forbidden_matches"], "new_material": bool(extras),
        })
    return coverage, cases, rows, unresolved


async def replay_arm(task, arm, frozen, instruction):
    fixture = load_native_fixture(SUITE / "fixtures" / task["fixture"])
    require(fixture.sha256 == task["fixture_sha256"], "fixture bytes changed")
    candidate = frozen["candidate_content"]
    require(sha256(candidate) == frozen["candidate_sha256"], "candidate bytes changed")
    wire = None

    async def generate(request):
        nonlocal wire
        wire = coordinator_input(request, instruction)
        require(digest(wire) == frozen["generation_input_sha256"], "coordinator input changed")
        return AIMessage(content="", tool_calls=[{
            "id": "public-regression-write", "name": "write_file",
            "args": {"file_path": "/workspace/research-findings.json", "content": candidate},
        }])

    observed = await run_native_arm(fixture=fixture, arm="A", generate=generate)
    receipt, delivery = observed.receipt, observed.delivery
    require(wire is not None and receipt["outcome"] == frozen["delivery_outcome"] == "delivered"
            and delivery is not None and candidate == observed.candidate_content, "delivery did not replay")
    source = receipt["visible_source"]
    content = wire["messages"][source["message_index"]]["content"]
    excerpt = json.loads('"' + content[source["start"]:source["end"]] + '"')
    require(excerpt == fixture.passage and sha256(excerpt) == task["visible_source_sha256"]
            and receipt["tools_sha256"] == task["tools_sha256"], "visible source or tools changed")
    checked = validate_delivery(delivery, receipt["run_id"])
    require(rebind_captured_report(fixture, candidate=candidate, delivery=delivery, receipt=receipt),
            "delivery differs from the rebound canonical report")
    coverage, cases, rows, unresolved = replay_assessments(task, fixture, delivery, frozen)

    record = {
        "arm": arm, "basis": "live_generation", "started": True, "outcome": receipt["outcome"],
        "run_id": receipt["run_id"], "report_hash": checked["artifact"]["content_hash"], "claims": rows,
        "dispositions": [{**d, "justified": unresolved.get(d["question_id"])}
                         for d in delivery["report"]["dispositions"]],
    }
    grade = _grade_arm(record, task, cases)
    if coverage.get("optional_inference", {}).get("classification") == "assertion_without_support":
        grade["passed"] = False
    require(grade["passed"] is frozen["passed"], "paired outcome did not replay")
    return {
        **grade, "basis": "offline replay of retained Codex output and frozen assessments",
        "observed_run_id": frozen["original_run_id"], "observed_report_hash": frozen["original_report_sha256"],
        "coverage": coverage, "verdicts": {value["finding_id"]: value["verdict"] for value in cases.values()},
    }


async def replay(corpus):
    instructions = corpus["instructions"]
    for entry in instructions.values():
        text = entry["text"]
        require(sha256(text) == entry["sha256"] and len(text.encode("utf-8")) == entry["byte_length"],
                "instruction fingerprint changed")
    require(instructions["generic"]["text"] == QUALIFICATION_INSTRUCTION, "generic instruction changed")
    scoped = instructions["scoped"]["text"]
    cross = corpus["phases"]["cross-family"]
    plan = cross["preregistered_plan"]
    require(digest(plan) == cross["plan_sha256"] and plan["candidate_instruction"] == scoped,
            "preregistered plan or candidate changed")
    categories = {
        (True, True): "both_pass", (True, False): "original_only",
        (False, True): "candidate_only", (False, False): "neither_pass",
    }
    results, counts = {}, Counter()
    for pair in corpus["pairs"]:
        task = corpus["tasks"][pair["task_id"]]
        arms = {arm: await replay_arm(task, arm, frozen, scoped if arm == "C" else "")
                for arm, frozen in pair["arms"].items()}
        category = categories.get((arms["A"]["passed"], arms["C"]["passed"]), "unscored")
        require(category == pair["outcome"], "pair classification changed")
        results[pair["id"]] = {"task_id": pair["task_id"], "phase": pair["phase"],
                               "category": category, "arms": arms}
        counts[category] += 1
    require(len(results) == len(corpus["pairs"]) and counts == corpus["totals"], "corpus outcome counts changed")
    return {"pairs": results, "totals": dict(counts)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    corpus = read_json(SUITE / "corpus.json")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "scoped-inference-replay.json"
    require(not output.exists(), "choose an output directory without an existing replay result")
    result = asyncio.run(replay(corpus))
    write_new(output, json_bytes(result))
    print(f"Verified {len(result['pairs'])} pairs: {result['totals']}")


if __name__ == "__main__":
    main()
