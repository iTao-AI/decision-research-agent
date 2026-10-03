"""Pure frozen-ledger delivery behavior; no runtime or provider calls."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib
import json

import pytest

from agent.research import EvidenceEntry
from agent.research_findings_contracts import ResearchFindingsReport, ResearchFindingsScope


URL = "https://example.com/source"


def resolver():
    return importlib.import_module("api.research_findings")


def scope(two=False):
    questions = [{"question_id": "q1", "text": "What is observed?"}]
    if two:
        questions.append({"question_id": "q2", "text": "What remains unknown?"})
    return ResearchFindingsScope.model_validate({"questions": questions})


def evidence(snippet="中🙂 signal 末", url=URL):
    return EvidenceEntry(thread_id="conversation", query_text="question", subagent_name="researcher",
                         tool_name="search", source_url=url, snippet=snippet)


def candidate():
    return {"schema_version": "dra.research-findings-candidate.v1",
            "findings": [{"question_id": "q1", "statement": "Observed signal",
                          "references": [{"source_url": URL, "excerpt": " signal "}]}],
            "dispositions": [{"question_id": "q1", "status": "candidate_findings"}],
            "reported_contradictions": [], "limitations": []}


def build(data=None, *, content=None, entries=None, requested_scope=None, capture_issue=None):
    return resolver().build_research_findings_artifacts(
        run_id="run1", scope=requested_scope or scope(),
        candidate_content=content if content is not None else json.dumps(data or candidate()),
        evidence_entries=[evidence()] if entries is None else entries, capture_issue=capture_issue)


def rows(entries):
    return [entry.to_dict() | {"run_id": "run1", "evidence_id": f"ev_run1_{entry.evidence_fingerprint}"}
            for entry in entries]


def assert_blocked(result, code):
    assert result.delivery_status == "blocked"
    assert result.report is None
    assert code in result.diagnostics.issue_codes
    assert [a["kind"] for a in result.artifacts] == ["research_findings_diagnostics_json"]
    content = result.artifacts[0]["content"]
    assert json.loads(content)["issue_codes"] == result.diagnostics.issue_codes
    assert "Observed signal" not in content


def test_complete_output_binds_unicode_offsets_and_preserves_verification_authority():
    entries = [evidence(), evidence("unused", "https://example.com/unused")]
    result = build(entries=entries)
    assert result.delivery_status == "ready"
    reference = result.report.findings[0].references[0]
    assert reference.excerpt_start == 2
    assert reference.excerpt_end == 10
    assert reference.snippet == "中🙂 signal 末"
    assert reference.evidence_id == f"ev_run1_{entries[0].evidence_fingerprint}"
    assert result.report.profile_id == "generic-evidence-report"
    assert result.report.profile_version == "1"
    assert result.report.findings[0].finding_id == "f1"
    assert [e.citation_status for e in result.evidence_entries] == ["cited", "uncited"]
    assert all(e.verification_status == "unverified" for e in result.evidence_entries)
    assert entries[0].citation_status == "uncited"
    assert result.diagnostics.covered_question_count == 1
    assert resolver().validate_research_findings_report(result.report, run_id="run1", scope=scope(), evidence_rows=rows(entries))


def test_partial_and_model_reported_contradictory_output_remains_inspectable():
    data = candidate()
    data["dispositions"].append({"question_id": "q2", "status": "unresolved", "reason": "No observed evidence"})
    data["reported_contradictions"] = ["Sources disagree"]
    data["limitations"] = ["Snippets only"]
    result = build(data, requested_scope=scope(two=True))
    assert result.delivery_status == "ready"
    assert result.diagnostics.unresolved_question_count == 1
    markdown = result.artifacts[1]["content"]
    for text in ["source-bound candidate", "No observed evidence", "Sources disagree", "model-reported", "Snippets only", "unverified", ">  signal "]:
        assert text in markdown


def test_deterministic_artifact_bytes_hashes_and_markdown_escape_untrusted_text():
    data = candidate()
    data["findings"][0]["statement"] = "<script>alert(1)</script> [click](javascript:evil)"
    first = build(data)
    second = build(data, entries=[replace(evidence(), created_at="different time")])
    assert first.artifacts == second.artifacts
    assert [a["artifact_id"] for a in first.artifacts] == ["research-findings.json", "research-report.md", "research-findings-diagnostics.json"]
    for artifact in first.artifacts:
        assert artifact["content_hash"] == hashlib.sha256(artifact["content"].encode("utf-8")).hexdigest()
    assert first.artifacts[0]["content"] == json.dumps(first.report.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert first.artifacts[1]["content"] == resolver().render_research_findings_markdown(first.report)
    assert "<script>" not in first.artifacts[1]["content"]
    assert "[click](javascript:evil)" not in first.artifacts[1]["content"]


def test_publishable_url_path_cannot_break_markdown_source_link_into_html():
    url = "https://example.com/source><img/src=x/onerror=alert(1)>"
    data = candidate()
    data["findings"][0]["references"][0]["source_url"] = url
    result = build(data, entries=[evidence(url=url)])
    assert result.delivery_status == "ready"
    markdown = result.artifacts[1]["content"]
    assert "<img/" not in markdown
    assert "source%3E%3Cimg/src%3Dx/onerror%3Dalert%281%29%3E" in markdown


@pytest.mark.parametrize("content,code", [
    ("", "candidate_missing"), ("{", "candidate_invalid_json"),
    ('{"x":1,"x":2}', "candidate_invalid_json"),
    ('{"x":{"y":1,"y":2}}', "candidate_invalid_json"),
    ('{"x":NaN}', "candidate_invalid_json"), ('{"x":Infinity}', "candidate_invalid_json"),
    ('{"x":-Infinity}', "candidate_invalid_json"),
    ("[]", "candidate_contract_invalid"),
    ("中" * 90000, "candidate_too_large"),
    (" " * (256 * 1024 + 1), "candidate_too_large"),
    ("\ud800", "candidate_invalid_json"),
], ids=["missing", "broken", "duplicate-root", "duplicate-nested", "nan", "infinity",
        "negative-infinity", "array", "oversized-unicode", "oversized-whitespace", "invalid-utf8"])
def test_bad_candidate_is_bounded_diagnostics_only(content, code):
    assert_blocked(build(content=content), code)


def test_absence_and_capture_failure_override_previous_valid_candidate():
    result = resolver().build_research_findings_artifacts(run_id="run1", scope=scope(), candidate_content=None, evidence_entries=[evidence()])
    assert_blocked(result, "candidate_missing")
    assert_blocked(build(capture_issue="candidate_invalid_json"), "candidate_invalid_json")


def test_independent_validator_accepts_ready_package_with_uncited_unpublishable_ledger_rows():
    entries = [evidence(), evidence("not referenced", "http://example.com/legacy")]
    result = build(entries=entries)
    assert result.delivery_status == "ready"
    assert resolver().validate_research_findings_report(result.report, run_id="run1", scope=scope(), evidence_rows=rows(entries))


def test_candidate_size_limit_includes_utf8_bytes_with_exact_boundary_allowed():
    content = json.dumps(candidate(), ensure_ascii=False)
    at_limit = content + " " * (256 * 1024 - len(content.encode("utf-8")))
    assert build(content=at_limit).delivery_status == "ready"
    assert_blocked(build(content=at_limit + " "), "candidate_too_large")


def test_escaped_non_utf8_unicode_and_deeply_nested_json_fail_closed():
    data = candidate()
    data["limitations"] = ["\ud800"]
    assert_blocked(build(content=json.dumps(data)), "candidate_invalid_json")
    assert_blocked(build(content="[" * 2000 + "]" * 2000), "candidate_invalid_json")


@pytest.mark.parametrize("change,code", [
    ("unknown_finding", "unknown_question_id"), ("unknown_disposition", "unknown_question_id"),
    ("missing", "question_disposition_missing"), ("duplicate", "duplicate_question_disposition"),
    ("unresolved_with_finding", "question_disposition_conflict"),
    ("covered_without_finding", "question_disposition_conflict"),
    ("all_unresolved", "empty_research_output"), ("authority", "candidate_contract_invalid"),
])
def test_scope_disposition_and_empty_output_fail_closed(change, code):
    data = candidate()
    requested = scope()
    if change == "unknown_finding": data["findings"][0]["question_id"] = "qX"
    if change == "unknown_disposition": data["dispositions"][0]["question_id"] = "qX"
    if change == "missing": requested = scope(two=True)
    if change == "duplicate": data["dispositions"] *= 2
    if change == "unresolved_with_finding": data["dispositions"] = [{"question_id": "q1", "status": "unresolved", "reason": "gap"}]
    if change == "covered_without_finding": data["findings"] = []
    if change == "all_unresolved":
        data["findings"] = []
        data["dispositions"] = [{"question_id": "q1", "status": "unresolved", "reason": "gap"}]
    if change == "authority": data["findings"][0]["references"][0]["evidence_id"] = "invented"
    assert_blocked(build(data, requested_scope=requested), code)


@pytest.mark.parametrize("url", ["https://localhost/source", "https://example.com/source?q=secret", "http://example.com/source", "https://user:secret@example.com/source"])
def test_unsafe_candidate_source_rejected(url):
    data = candidate()
    data["findings"][0]["references"][0]["source_url"] = url
    assert_blocked(build(data), "source_url_not_publishable")


@pytest.mark.parametrize("entries,excerpt,code", [
    ([], " signal ", "source_not_observed"),
    ([evidence("other")], " signal ", "excerpt_not_found"),
    ([evidence("aaa")], "aa", "ambiguous_reference"),
    ([evidence("signal signal")], "signal", "ambiguous_reference"),
    ([evidence(), evidence("different signal elsewhere")], "signal", "ambiguous_reference"),
    ([evidence(), evidence()], " signal ", "ambiguous_reference"),
    ([replace(evidence(), source_url=URL + ".")], " signal ", "source_url_not_publishable"),
    ([replace(evidence(), evidence_fingerprint="a" * 64)], " signal ", "reference_binding_failed"),
    ([replace(evidence(), snippet=" signal \ud800")], " signal ", "reference_binding_failed"),
])
def test_reference_requires_unique_observed_publishable_exact_excerpt(entries, excerpt, code):
    data = candidate()
    data["findings"][0]["references"][0]["excerpt"] = excerpt
    result = build(data, entries=entries)
    assert_blocked(result, code)
    assert result.diagnostics.reference_binding_failure_count == 1


def test_one_invalid_reference_blocks_every_finding_without_citing_partial_evidence():
    data = candidate()
    other = deepcopy(data["findings"][0])
    other["references"][0]["source_url"] = "https://invented.example/source"
    data["findings"].append(other)
    result = build(data)
    assert_blocked(result, "source_not_observed")
    assert result.evidence_entries[0].citation_status == "uncited"


def test_derived_package_larger_than_reader_limit_blocks_instead_of_becoming_unreadable():
    # 200 bindings repeat even a normal 1000-code-point frozen snippet.
    data = candidate()
    data["findings"] = [deepcopy(data["findings"][0]) for _ in range(20)]
    url = "https://example.com/" + "x" * 500
    for finding in data["findings"]:
        finding["references"][0]["source_url"] = url
        finding["references"] *= 10
    snippet = " signal " + "🙂" * 992
    assert len(snippet) == 1000
    assert len(json.dumps(data).encode()) < 256 * 1024
    assert_blocked(build(data, entries=[evidence(snippet, url)]), "artifact_package_too_large")


@pytest.mark.parametrize("mutation", ["run", "profile", "version", "scope", "foreign_id", "row_run", "row_id", "row_fingerprint", "row_snippet", "row_url", "duplicate_row", "missing_row", "offset", "repeated_excerpt", "disposition", "finding_id"])
def test_independent_validation_rejects_rehashed_foreign_refs_scope_and_corrupt_rows(mutation):
    result = build()
    data = result.report.model_dump(mode="json")
    evidence_rows = rows([evidence()])
    expected_scope = scope()
    ref = data["findings"][0]["references"][0]
    if mutation == "run": data["run_id"] = "other"
    if mutation == "profile": data["profile_id"] = "generic"
    if mutation == "version": data["profile_version"] = "2"
    if mutation == "scope": expected_scope = scope(two=True)
    if mutation == "foreign_id": ref["evidence_id"] = "ev_other_" + ref["evidence_fingerprint"]
    if mutation == "row_run": evidence_rows[0]["run_id"] = "other"
    if mutation == "row_id": evidence_rows[0]["evidence_id"] = "ev_other_" + ref["evidence_fingerprint"]
    if mutation == "row_fingerprint": evidence_rows[0]["evidence_fingerprint"] = "a" * 64
    if mutation == "row_snippet": evidence_rows[0]["snippet"] = "invented"
    if mutation == "row_url": evidence_rows[0]["source_url"] = "https://localhost/"
    if mutation == "duplicate_row": evidence_rows *= 2
    if mutation == "missing_row": evidence_rows = []
    if mutation == "offset":
        ref["snippet"] = "xx signal "
        ref["excerpt_start"] = 2
        ref["excerpt_end"] = 10
    if mutation == "repeated_excerpt":
        evidence_rows.append(rows([evidence("other signal elsewhere")])[0])
        ref["excerpt"] = "signal"
        ref["excerpt_start"] = 3
        ref["excerpt_end"] = 9
    if mutation == "disposition": data["dispositions"] = [{"question_id": "q1", "status": "unresolved", "reason": "gap"}]
    if mutation == "finding_id": data["findings"][0]["finding_id"] = "f2"
    report = ResearchFindingsReport.model_validate(data)
    assert not resolver().validate_research_findings_report(report, run_id="run1", scope=expected_scope, evidence_rows=evidence_rows)


def test_independent_validation_revalidates_mutated_pydantic_lists_and_constructed_offsets():
    report = build().report
    report.findings.clear()
    assert not resolver().validate_research_findings_report(report, run_id="run1", scope=scope(), evidence_rows=rows([evidence()]))
    report = build().report
    ref = report.findings[0].references[0].model_copy(update={"excerpt_start": True})
    report.findings[0].references[0] = ref
    assert not resolver().validate_research_findings_report(report, run_id="run1", scope=scope(), evidence_rows=rows([evidence()]))
