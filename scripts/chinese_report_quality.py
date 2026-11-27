"""Prepare, bind and record local Chinese report evaluations without provider calls."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import fields
import hashlib
import json
from pathlib import Path
import re
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import Field, ValidationError

from agent.research import EvidenceEntry, source_identity_for
from agent.research_findings_contracts import (
    CandidateReference,
    FindingsContractModel,
    ResearchFindingsScope,
)
from api.research_findings import _bind_reference, build_research_findings_artifacts
from scripts.findings_quality_io import QualityError, digest, json_bytes, read_json, write_new
from scripts.findings_quality_replay import validate_judgment


GENERATOR_INSTRUCTIONS = [
    '只输出 JSON，根对象为 {"cases":[{"id":"...","condition":"...","candidate":...}]}。',
    "逐个完成给定案例，使用简体中文回答，引文使用材料里的原句。每个案例的所有 sources 同时可见。",
    'web-general-markdown 使用 {"markdown":"...","citations":[{"source_url":"...","excerpt":"..."}]}。',
    "其余候选使用 ResearchFindingsCandidate JSON。依次使用 q1、q2 等题号。每条引文的 source_url 和 excerpt 各自取自对应来源。",
]
SOURCE_FIELDS = ("id", "title", "source_url", "version", "anchor", "snippet")
PUBLIC_CITATION_FIXTURE = (
    Path(__file__).resolve().parents[1] / "benchmarks/chinese-report-quality-v1/public-citation-replay.json"
)
PUBLIC_CITATION_OUTPUT = Path("output/chinese-report-quality-v1/public-citation-replay.json")
INLINE_CITATION = re.compile(r"(?<!\\)\[([0-9]+)\](?![:(])")


class MarkdownCandidate(FindingsContractModel):
    markdown: str = Field(min_length=1, max_length=250_000)
    citations: list[CandidateReference] = Field(max_length=100)


def require(condition, message):
    if not condition:
        raise QualityError(message)


def sha256(raw):
    return hashlib.sha256(raw if isinstance(raw, bytes) else raw.encode("utf-8")).hexdigest()


def index(rows, key):
    items = {}
    for row in rows:
        identity = key(row)
        require(identity not in items, "duplicate evaluation identity")
        items[identity] = row
    return items


def case_key(row):
    return row["id"], row["condition"]


def prepare(cases, sources):
    """Give the generator a whitelist of fields and the selected material set."""
    by_source = index(sources["sources"], lambda row: row["id"])
    for source in by_source.values():
        snippet = source["snippet"]
        require(sha256(snippet) == source["snippet_sha256"], "source snippet hash differs")
        for ref in source["excerpts"]:
            start, end = ref["excerpt_start"], ref["excerpt_end"]
            excerpt = ref["excerpt"]
            require(snippet[start:end] == excerpt and sha256(excerpt) == ref["excerpt_sha256"],
                    "frozen source excerpt differs")
    rows = []
    for case in index(cases["cases"], lambda row: row["id"]).values():
        questions = [{"question_id": f"q{number}", "text": text} for number, text in enumerate(case["prompt"], 1)]
        for name, condition in case["material_conditions"].items():
            source_ids = condition["source_ids"]
            require(len(set(source_ids)) == len(source_ids) and
                    not set(source_ids).intersection(condition.get("excluded_source_ids", ())),
                    "invalid or duplicated condition source")
            row = {
                "id": case["id"], "condition": name, "entry": case["entry"], "report_language": case["report_language"],
                "questions": questions,
                "sources": [{key: by_source[sid][key] for key in SOURCE_FIELDS} for sid in source_ids],
            }
            if "generation_instruction" in condition:
                row["additional_instruction"] = condition["generation_instruction"]
            rows.append(row)
    return {"instructions": GENERATOR_INSTRUCTIONS, "cases": rows}


def _bound_citation(reference, sources, number):
    # Multiple receipts may share the same publication URL. Resolve the exact
    # snapshot by both source and matching snippet.
    source = next(s for s in sources if s["source_url"] == reference.source_url and s["snippet"] == reference.snippet)
    return {
        "reference_id": f"R{number}", "source_id": source["id"], "source_url": reference.source_url,
        "source_version": source["version"], "excerpt": reference.excerpt,
    }


def _bind_case(row, candidate):
    run_id = "run_chinese_eval_" + digest(row)[:24]
    entries = [
        EvidenceEntry(thread_id=run_id, query_text=row["questions"][0]["text"], subagent_name="controlled_materials",
                      tool_name="frozen_source_receipt", source_url=source["source_url"], snippet=source["snippet"])
        for source in row["sources"]
    ]
    if row["entry"] == "web-general-markdown":
        result = {"binding": "receipt_check_only"}
        try:
            markdown = MarkdownCandidate.model_validate(candidate)
            require(markdown.markdown.strip(), "empty Markdown report")
        except (QualityError, ValidationError):
            return {**result, "outcome": "blocked", "issues": ["invalid_markdown_candidate"]}, None
        hits, issues = [], []
        for number, reference in enumerate(markdown.citations, 1):
            match, issue = _bind_reference(reference, entries, run_id)
            if match is not None:
                hits.append(_bound_citation(match, row["sources"], number))
            else:
                issues.append(issue)
        markers = set(INLINE_CITATION.findall(markdown.markdown))
        bound_numbers = {ref["reference_id"][1:] for ref in hits}
        binding_failures = len(issues)
        if markers - bound_numbers:
            issues.append("unresolved_markdown_citation_marker")
        if bound_numbers - markers:
            issues.append("unused_markdown_citation_receipt")
        return {
            **result, "outcome": "markdown_available", "references_bound": len(hits),
            "reference_binding_failures": binding_failures, "issues": list(dict.fromkeys(issues)),
            "report_sha256": sha256(markdown.markdown),
        }, {"markdown": markdown.markdown, "claims": [{
            "finding_id": "markdown", "question_id": "q1", "statement": markdown.markdown,
            "citations": [ref for ref in hits if ref["reference_id"][1:] in markers],
        }]}

    require(row["entry"] in {"web-evidence-research", "controlled-materials"}, "unknown research entry")
    structured = build_research_findings_artifacts(
        run_id=run_id,
        scope=ResearchFindingsScope.model_validate({"questions": row["questions"], "report_language": row["report_language"]}),
        candidate_content=None if candidate is None else json.dumps(candidate, ensure_ascii=False, allow_nan=False),
        evidence_entries=entries,
    )
    result = {
        "binding": "dra_application", "outcome": structured.delivery_status,
        "reference_binding_failures": structured.diagnostics.reference_binding_failure_count,
        "issues": structured.diagnostics.issue_codes,
    }
    if structured.report is None:
        return result, None
    report = structured.report
    claims = [
        {
            "finding_id": finding.finding_id, "question_id": finding.question_id, "statement": finding.statement,
            "citations": [_bound_citation(ref, row["sources"], number) for number, ref in enumerate(finding.references, 1)],
        }
        for finding in report.findings
    ]
    return {
        **result, "references_bound": sum(len(claim["citations"]) for claim in claims),
        "report_sha256": next(artifact["content_hash"] for artifact in structured.artifacts
                              if artifact["kind"] == "research_findings_json"),
    }, {
        "claims": claims, "dispositions": [d.model_dump(mode="json") for d in report.dispositions],
        "reported_contradictions": report.reported_contradictions, "limitations": report.limitations,
    }


def bind(inputs, candidates, materials):
    """Produce deterministic structure receipts and versioned, strategy-blind reviews."""
    expected = index(inputs["cases"], case_key)
    given = index(candidates["cases"], case_key)
    require(expected.keys() == given.keys(), "candidate cases must exactly match prepared cases and conditions")
    by_case = index(materials["cases"], lambda row: row["id"])
    results, blind = [], []
    for (case_id, condition), row in expected.items():
        identity = {"id": case_id, "condition": condition}
        candidate = given[(case_id, condition)]["candidate"]
        result, semantic = _bind_case(row, candidate)
        results.append({
            **identity, **result, "entry": row["entry"], "candidate_sha256": digest(candidate),
            "semantic": "unscorable" if semantic is None else "judge_pending",
        })
        if semantic is None:
            continue
        case = by_case[case_id]
        overrides = case["material_conditions"][condition].get("coverage_overrides", {})
        review = {
            "questions": row["questions"], **semantic,
            "coverage": [{**criterion, **overrides.get(criterion["id"], {})} for criterion in case["coverage"]],
            "critical_errors": case["critical_errors"], "rubric": materials["judge_rubric"],
        }
        review_identity = {**identity, "input_sha256": digest(review)}
        blind.append({**review_identity, "identity_sha256": digest(review_identity), "input": review})
    return {"cases": results}, {"cases": blind}


def _reason(value):
    return isinstance(value, str) and bool(value.strip())


def record(blind, receipts):
    """Validate independent Judge receipts and summarize required coverage and verdicts."""
    judge = receipts["judge"]
    require(isinstance(judge, dict) and _reason(judge.get("model")) and _reason(judge.get("prompt_version")),
            "judge model and prompt version are required")
    expected = index(blind["cases"], lambda row: row["input_sha256"])
    given = index(receipts["cases"], lambda row: row["input_sha256"])
    require(expected.keys() == given.keys(), "judge receipts must exactly match the blind input hashes")
    results = []
    for input_hash, envelope in expected.items():
        review = envelope["input"]
        require(input_hash == digest(review), "blind input hash differs")
        identity = {key: envelope[key] for key in ("id", "condition", "input_sha256")}
        require(envelope.get("identity_sha256") == digest(identity), "blind case identity hash differs")
        observed = given[input_hash]

        claims = index(review["claims"], lambda row: row["finding_id"])
        verdicts = index(observed["verdicts"], lambda row: row["finding_id"])
        require(claims.keys() == verdicts.keys(), "judge verdicts must exactly match scorable findings")
        for fid, verdict in verdicts.items():
            validate_judgment(claims[fid], {key: value for key, value in verdict.items() if key != "finding_id"})

        criteria = index(review["coverage"], lambda row: row["id"])
        coverage = index(observed["coverage"], lambda row: row["id"])
        require(criteria.keys() == coverage.keys(), "judge coverage must exactly match the required/optional criteria")
        for verdict in coverage.values():
            require((verdict["score"] is None or type(verdict["score"]) is int and verdict["score"] in (0, 1))
                    and _reason(verdict["reason"]), "invalid coverage score or reason")
        required_ids = [key for key, criterion in criteria.items() if criterion["required"]]

        readability = observed["readability"]
        require(type(readability["score"]) is int and readability["score"] in (0, 1, 2) and _reason(readability["reason"]),
                "invalid readability score or reason")
        errors = index(observed["critical_errors"], lambda row: row["index"])
        require(all(type(key) is int and 1 <= key <= len(review["critical_errors"]) and _reason(row["reason"])
                    for key, row in errors.items()), "invalid critical error index or reason")
        results.append({
            "id": envelope["id"], "condition": envelope["condition"], "input_sha256": input_hash,
            "semantic_verdict_counts": dict(Counter(verdict["verdict"] for verdict in verdicts.values())),
            "coverage": {
                "satisfied": sum(coverage[key]["score"] == 1 for key in required_ids),
                "required": len(required_ids), "unscorable": sum(coverage[key]["score"] is None for key in required_ids),
            },
            "review": observed,
        })
    return {"judge": judge, "cases": results}


def public_citation_inputs(fixture):
    """Build same-question candidates that differ only in the cited source."""
    prepared = prepare(fixture, fixture)
    candidates = []
    for row in prepared["cases"]:
        [source] = row["sources"]
        candidates.append({
            "id": row["id"],
            "condition": row["condition"],
            "candidate": {
                "schema_version": "dra.research-findings-candidate.v1",
                "findings": [{
                    "question_id": "q1",
                    "statement": fixture["conclusion"],
                    "references": [{"source_url": source["source_url"], "excerpt": source["snippet"]}],
                }],
                "dispositions": [{"question_id": "q1", "status": "candidate_findings"}],
            },
        })
    return bind(prepared, {"cases": candidates}, fixture)


def replay_public_citations(fixture):
    """Replay application binding and read back the fixed, input-bound human labels."""
    binding, blind = public_citation_inputs(fixture)
    bindings = index(binding["cases"], case_key)
    reviews = index(blind["cases"], case_key)
    annotations = index(fixture["manual_labels"], case_key)
    sources = index(fixture["sources"], lambda source: source["id"])
    require(bindings.keys() == reviews.keys() == annotations.keys() and len(bindings) == 2,
            "both public controls require a bound claim and a fixed label")

    results = []
    for key, receipt in bindings.items():
        review = reviews[key]
        label = annotations[key]
        require(review["input_sha256"] == label["input_sha256"], "fixed semantic label input has changed")
        require(receipt["binding"] == "dra_application" and receipt["outcome"] == "ready" and
                receipt["references_bound"] == 1 and receipt["reference_binding_failures"] == 0,
                "public control citation did not bind uniquely")
        [claim] = review["input"]["claims"]
        [citation] = claim["citations"]
        [question] = review["input"]["questions"]
        judgment = validate_judgment(claim, label["judgment"])
        source = sources[citation["source_id"]]
        results.append({
            "id": key[0],
            "condition": key[1],
            "question": question["text"],
            "conclusion": claim["statement"],
            "claim_operation": fixture["claim_operation"],
            "citation": {
                **citation,
                "operation": source["operation"],
                "source_line": source["source_line"],
                "source_body_sha256": source["source_body_sha256"],
                "excerpt_sha256": sha256(citation["excerpt"]),
            },
            "binding": {
                "producer": receipt["binding"],
                **{name: receipt[name] for name in ("outcome", "references_bound", "reference_binding_failures")},
            },
            "semantic": {
                "verdict": judgment["verdict"],
                "reason": judgment["rationale"],
                "input_sha256": review["input_sha256"],
            },
        })
    return {
        "evaluation_basis": "frozen_materials_and_fixed_manual_labels",
        "fixture_sha256": digest(fixture),
        "cases": results,
    }


def replay_history(archive, run_id=None):
    """Cross-check an execution-only record and exercise the original ledger with fixed probes."""
    status = read_json(archive / "run-status.json")
    if run_id is None:
        run_id = status["run_id"]
    require(_reason(run_id), "saved run identity is missing")
    diagnostics_path = archive / "research-findings-diagnostics.json"
    diagnostics = read_json(diagnostics_path)
    artifact_hash = sha256(diagnostics_path.read_bytes())
    probes = read_json(archive / "citation-replay.json")
    require(status["run_id"] == diagnostics["run_id"] == probes["run_id"] == run_id and
            status["execution_status"] == "completed" and status["delivery_status"] == "blocked",
            "saved run identity or terminal status differs")
    artifacts = {row["artifact_id"]: row["content_hash"] for row in status["artifacts"]}
    require(artifacts == {diagnostics_path.name: artifact_hash}, "saved diagnostics artifact hash differs or report exists")
    for name in ("result.json", "findings.json"):
        response = read_json(archive / name)
        require(response["run_id"] == run_id and response["code"] == "run_delivery_blocked",
                "saved result does not establish blocked delivery")
    require(status["findings_issues"] == diagnostics["issue_codes"] and
            status["findings_outcome"] == {key: value for key, value in diagnostics.items() if key.endswith("_count")},
            "saved diagnostic codes or counts differ")

    ledger = []
    keys = {field.name for field in fields(EvidenceEntry)} - {"thread_id"}
    for data in status["evidence"]:
        require(data["run_id"] == run_id, "saved evidence belongs to another run")
        ledger.append(EvidenceEntry(thread_id=status["thread_id"], **{key: data[key] for key in keys if key in data}))
    evidence_count = len(ledger)
    source_count = len({entry.source_identity for entry in ledger})
    failures = diagnostics["reference_binding_failure_count"]
    require(type(failures) is int and failures > 0, "saved run has no binding failures")
    source_calls = sum(row["run_id"] == run_id and row["tool_name"] == "tavily_search"
                       for row in read_json(archive / "tool-telemetry.json"))

    results = []
    for probe in probes["cases"]:
        reference = CandidateReference(source_url=probe["source_url"], excerpt=probe["excerpt"])
        match, issue = _bind_reference(reference, ledger, run_id)
        identity = source_identity_for(reference.source_url)
        count = sum(entry.source_identity == identity and reference.excerpt in entry.snippet for entry in ledger)
        outcome = "bound" if match is not None else issue
        require((count, outcome) == (probe["matching_snippets"], probe["result"]), "frozen ledger probe differs")
        results.append({
            "case": probe["case"], "source_url": reference.source_url, "excerpt": reference.excerpt,
            "matching_snippets": count, "result": outcome, "evidence_id": match.evidence_id if match else None,
        })
    require(len(results) == 3 and {(row["matching_snippets"], row["result"]) for row in results} == {
        (0, "excerpt_not_found"), (1, "bound"), (2, "ambiguous_reference"),
    }, "expected zero, unique and ambiguous archived probes")

    locators = {name: sha256((archive / name).read_bytes()) for name in (
        "run-status.json", diagnostics_path.name, "citation-replay.json", "tool-telemetry.json", "result.json", "findings.json",
    )}
    observation = {
        "case_id": f"historical-{run_id}", "run_id": run_id,
        "primary_artifact_available": False,
        "source_calls": {"state": "completed", "count": source_calls,
                         "locator": "Archived tool-telemetry.json records for this run with tool_name=tavily_search"},
        "steps": [{
            "stage": "application_binding", "result": "deviation",
            "locator": f"{diagnostics_path.name}#{artifact_hash}",
            "basis": f"{failures} binding failures with {evidence_count} saved excerpts from {source_count} distinct sources.",
        }],
    }
    receipt = {
        "run_id": run_id, "primary_artifact_available": False,
        "reference_binding_failures": failures, "saved_excerpts": evidence_count, "distinct_sources": source_count,
        "source_calls": source_calls, "semantic": "unscorable",
        "probes_basis": "Fixed independent quotes checked against the original ledger. Original candidates are unavailable.",
        "probes": results, "archive_sha256": locators,
    }
    return observation, receipt


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_new(path, content, idempotent=True)


def read_materials(directory, manifest_path=None):
    cases_path, sources_path = directory / "cases.json", directory / "sources.json"
    if manifest_path is None:
        return read_json(cases_path), read_json(sources_path)
    manifest = read_json(manifest_path)
    return (
        read_json(cases_path, expected_sha256=manifest["case_file_sha256"]),
        read_json(sources_path, expected_sha256=manifest["packet_sha256"]),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preparing = commands.add_parser("prepare", help="Write only blinded generator input.")
    preparing.add_argument("--material-dir", required=True, type=Path)
    preparing.add_argument("--source-manifest", type=Path)
    preparing.add_argument("--output", required=True, type=Path)
    binding = commands.add_parser("bind", help="Bind retained candidates and write blind review inputs.")
    binding.add_argument("--material-dir", required=True, type=Path)
    binding.add_argument("--source-manifest", type=Path)
    binding.add_argument("--generator-input", required=True, type=Path)
    binding.add_argument("--candidates", required=True, type=Path)
    binding.add_argument("--output-dir", required=True, type=Path)
    recording = commands.add_parser("record", help="Validate completed independent Judge receipts.")
    recording.add_argument("--blind-input", required=True, type=Path)
    recording.add_argument("--judgments", required=True, type=Path)
    recording.add_argument("--output", required=True, type=Path)
    public_replay = commands.add_parser(
        "public-citation-replay", help="Replay the tracked pair with fixed manual semantic labels.",
    )
    public_replay.add_argument("--output", type=Path, default=PUBLIC_CITATION_OUTPUT)
    history = commands.add_parser("history", help="Recheck saved diagnostics and replay exactly three binding probes.")
    history.add_argument("--archive", required=True, type=Path)
    history.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command in {"prepare", "bind"}:
            materials, sources = read_materials(args.material_dir, args.source_manifest)
            prepared = prepare(materials, sources)
            if args.command == "prepare":
                # Match the fixed generator payload already used for the baseline.
                content = (json.dumps(prepared, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                _write(args.output, content)
            else:
                require(read_json(args.generator_input) == prepared, "prepared generator input has changed")
                result, blind = bind(prepared, read_json(args.candidates), materials)
                _write(args.output_dir / "binding.json", json_bytes(result))
                _write(args.output_dir / "judge-input.json", json_bytes(blind))
        elif args.command == "record":
            result = record(read_json(args.blind_input), read_json(args.judgments))
            _write(args.output, json_bytes(result))
        elif args.command == "public-citation-replay":
            _write(args.output, json_bytes(replay_public_citations(read_json(PUBLIC_CITATION_FIXTURE))))
        else:
            observation, result = replay_history(args.archive)
            _write(args.output_dir / "observation.json", json_bytes(observation))
            _write(args.output_dir / "binding-probes.json", json_bytes(result))
    except (KeyError, TypeError, ValueError, OSError) as exc:
        print(f"Chinese report evaluation input failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
