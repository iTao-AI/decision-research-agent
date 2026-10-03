"""Strict producer/delivery boundary tests; no providers or runtime registration."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from agent.research_findings_contracts import (
    BoundFinding,
    BoundSourceReference,
    CandidateFinding,
    CandidateReference,
    QuestionDisposition,
    ResearchFindingsCandidate,
    ResearchFindingsDiagnostics,
    ResearchFindingsReport,
    ResearchFindingsScope,
    ResearchQuestion,
    validate_research_findings_scope,
)


def candidate():
    return {
        "schema_version": "dra.research-findings-candidate.v1",
        "findings": [{
            "question_id": "q1", "statement": "Observed signal",
            "references": [{"source_url": "https://example.com/source", "excerpt": " signal "}],
        }],
        "dispositions": [{"question_id": "q1", "status": "candidate_findings"}],
        "reported_contradictions": [], "limitations": [],
    }


def bound_reference():
    return {
        "evidence_id": "ev_run1_" + "a" * 64,
        "evidence_fingerprint": "a" * 64,
        "source_url": "https://example.com/source",
        "source_identity": "https://example.com/source",
        "snippet": "中🙂 signal 末", "excerpt": " signal ",
        "excerpt_start": 2, "excerpt_end": 10,
    }


def report():
    return {
        "schema_version": "dra.research-findings.v1",
        "run_id": "run1", "profile_id": "generic-evidence-report", "profile_version": "1",
        "questions": [{"question_id": "q1", "text": "What is observed?"}],
        "findings": [{"finding_id": "f1", "question_id": "q1", "statement": "Observed signal",
                      "references": [bound_reference()]}],
        "dispositions": [{"question_id": "q1", "status": "candidate_findings"}],
        "reported_contradictions": [], "limitations": [],
    }


def test_scope_omission_defaults_to_trimmed_query_without_mutating_input():
    scope = {}
    parsed = validate_research_findings_scope(scope, query="  What is observed?  ")
    assert parsed.model_dump() == {"questions": [{"question_id": "q1", "text": "What is observed?"}]}
    assert scope == {}
    explicit = {"questions": [{"question_id": "q2", "text": " Another question "}]}
    assert validate_research_findings_scope(explicit, query="ignored").questions[0].text == "Another question"


@pytest.mark.parametrize("scope", [
    {"questions": []}, {"questions": None}, {"unexpected": True},
    {"questions": [{"question_id": "q1", "text": "a"}] * 2},
    {"questions": [{"question_id": f"q{i}", "text": "a"} for i in range(6)]},
    {"questions": ({"question_id": "q1", "text": "a"},)},
])
def test_scope_rejects_empty_duplicate_unknown_fields_and_coerced_collections(scope):
    with pytest.raises(ValidationError):
        validate_research_findings_scope(scope, query="question")


@pytest.mark.parametrize("question_id", ["", "1q", "q.dot", "q x", "问题", "q\n", "a" * 65, 1])
def test_question_ids_are_bounded_ascii_identifiers(question_id):
    with pytest.raises(ValidationError):
        ResearchQuestion(question_id=question_id, text="question")


def test_question_and_scope_boundaries():
    question = ResearchQuestion(question_id="a" * 64, text=" " + "中" * 4096 + " ")
    assert len(question.text) == 4096
    assert len(ResearchFindingsScope(questions=[question] * 1).questions) == 1
    with pytest.raises(ValidationError):
        ResearchQuestion(question_id="q1", text="x" * 4097)
    for text in ["", " \n ", 1, b"question"]:
        with pytest.raises(ValidationError):
            validate_research_findings_scope({}, query=text)


@pytest.mark.parametrize("field,value", [
    ("source_url", ""), ("source_url", " " * 5), ("source_url", "x" * 2049),
    ("source_url", 1), ("excerpt", ""), ("excerpt", " \n "),
    ("excerpt", "x" * 1001), ("excerpt", b"signal"),
    ("evidence_id", "invented"), ("confidence", 1), ("verification_status", "verified"),
])
def test_candidate_references_reject_invalid_bounds_types_and_authority(field, value):
    data = {"source_url": "https://example.com", "excerpt": "signal", field: value}
    with pytest.raises(ValidationError):
        CandidateReference.model_validate(data)


def test_candidate_reference_preserves_exact_excerpt_including_whitespace():
    excerpt = " \n中🙂 signal\t "
    reference = CandidateReference(source_url="x" * 2048, excerpt=excerpt)
    assert reference.excerpt == excerpt
    assert CandidateReference(source_url="source", excerpt="x" * 1000).excerpt == "x" * 1000


@pytest.mark.parametrize("field,value", [
    ("question_id", "unknown.id"), ("statement", ""), ("statement", " \n "),
    ("statement", "x" * 2001), ("statement", 123), ("references", []),
    ("references", [{"source_url": "source", "excerpt": "x"}] * 11),
    ("references", ({"source_url": "source", "excerpt": "x"},)),
    ("finding_id", "model-assigned"), ("delivery_status", "ready"), ("confidence", 0.9),
])
def test_candidate_finding_requires_bounded_statement_references_and_no_authority(field, value):
    data = candidate()["findings"][0] | {field: value}
    with pytest.raises(ValidationError):
        CandidateFinding.model_validate(data)


@pytest.mark.parametrize("data", [
    {"question_id": "q1", "status": "unresolved"},
    {"question_id": "q1", "status": "unresolved", "reason": " \n "},
    {"question_id": "q1", "status": "unresolved", "reason": "x" * 2001},
    {"question_id": "q1", "status": "candidate_findings", "reason": "not allowed"},
    {"question_id": "q1", "status": "candidate_findings", "reason": None},
    {"question_id": "q1", "status": "ready"},
])
def test_disposition_enforces_unresolved_reason_and_omits_reason_for_findings(data):
    with pytest.raises(ValidationError):
        QuestionDisposition.model_validate(data)


def test_disposition_serialization_omits_absent_reason():
    assert QuestionDisposition(question_id="q1", status="candidate_findings").model_dump() == {
        "question_id": "q1", "status": "candidate_findings",
    }
    assert QuestionDisposition(question_id="q1", status="unresolved", reason=" No evidence ").reason == "No evidence"


@pytest.mark.parametrize("field,value", [
    ("schema_version", "1"), ("findings", candidate()["findings"] * 21),
    ("dispositions", []), ("dispositions", candidate()["dispositions"] * 2),
    ("dispositions", [{"question_id": f"q{i}", "status": "unresolved", "reason": "gap"} for i in range(6)]),
    ("reported_contradictions", ["x"] * 21), ("limitations", ["x"] * 21),
    ("limitations", [""]), ("reported_contradictions", ["x" * 2001]),
    ("limitations", [False]), ("findings", tuple(candidate()["findings"])),
    ("approved", True), ("confidence", 0.9), ("run_id", "model-run"),
])
def test_candidate_rejects_excess_bounds_duplicates_coercion_and_invented_authority(field, value):
    with pytest.raises(ValidationError):
        ResearchFindingsCandidate.model_validate(candidate() | {field: value})


def test_candidate_allows_bounded_empty_findings_for_application_policy_to_decide():
    data = candidate()
    data["findings"] = []
    data["dispositions"] = [{"question_id": "q1", "status": "unresolved", "reason": "No evidence"}]
    assert ResearchFindingsCandidate.model_validate(data).findings == []
    full = candidate()
    full["findings"] *= 20
    full["findings"][0]["statement"] = "x" * 2000
    full["limitations"] = ["x" * 2000] * 20
    full["reported_contradictions"] = ["x" * 2000] * 20
    full["dispositions"] = [{"question_id": f"q{i}", "status": "unresolved", "reason": "gap"} for i in range(5)]
    assert len(ResearchFindingsCandidate.model_validate(full).findings) == 20


def test_contracts_are_frozen_and_json_round_trip_preserves_unicode_excerpt():
    parsed = ResearchFindingsReport.model_validate(report())
    with pytest.raises(ValidationError):
        parsed.run_id = "changed"
    assert ResearchFindingsReport.model_validate_json(parsed.model_dump_json()) == parsed
    reference = parsed.findings[0].references[0]
    assert reference.snippet[reference.excerpt_start:reference.excerpt_end] == " signal "


@pytest.mark.parametrize("field,value", [
    ("excerpt_start", "2"), ("excerpt_end", True), ("excerpt_start", -1),
    ("excerpt_end", 2), ("excerpt_end", 100), ("excerpt", "invented excerpt"),
    ("evidence_fingerprint", "not-a-sha256"), ("verification_status", "verified"),
])
def test_bound_reference_requires_exact_codepoint_offsets_and_no_verification_claim(field, value):
    with pytest.raises(ValidationError):
        BoundSourceReference.model_validate(bound_reference() | {field: value})


def test_canonical_report_requires_local_unique_identity_and_strict_authority_boundary():
    for field, value in [("approved", True), ("confidence", 0.9), ("profile_version", 1)]:
        with pytest.raises(ValidationError):
            ResearchFindingsReport.model_validate(report() | {field: value})
    data = report()
    data["findings"] *= 2
    with pytest.raises(ValidationError):
        ResearchFindingsReport.model_validate(data)
    data = report()
    data["questions"] *= 2
    with pytest.raises(ValidationError):
        ResearchFindingsReport.model_validate(data)
    finding = deepcopy(report()["findings"][0])
    for finding_id in ["model-f1", "f0", "f01"]:
        with pytest.raises(ValidationError):
            BoundFinding.model_validate(finding | {"finding_id": finding_id})


def diagnostics():
    return {
        "schema_version": "dra.research-findings-diagnostics.v1", "run_id": "run1",
        "issue_codes": ["empty_research_output"], "requested_question_count": 2,
        "covered_question_count": 0, "unresolved_question_count": 2,
        "reference_binding_failure_count": 0,
    }


def test_diagnostics_are_bounded_closed_codes_and_strict_integer_counts():
    parsed = ResearchFindingsDiagnostics.model_validate(diagnostics())
    assert parsed.issue_codes == ["empty_research_output"]
    for field, value in [
        ("issue_codes", ["raw exception with private path"]),
        ("issue_codes", ["candidate_missing"] * 21),
        ("requested_question_count", "2"), ("covered_question_count", True),
        ("unresolved_question_count", -1), ("reference_binding_failure_count", -1),
        ("raw_exception", "private text"),
    ]:
        with pytest.raises(ValidationError):
            ResearchFindingsDiagnostics.model_validate(diagnostics() | {field: value})
