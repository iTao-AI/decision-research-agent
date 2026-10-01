"""Strict bounded contracts separating model candidates from owned delivery.

These models validate local shape only. Same-run Evidence binding, accepted
question coverage, delivery policy and persistence belong to application code.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator,
)


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("value must not be blank")
    return value


QuestionId = Annotated[
    str, StringConstraints(pattern=r"\A[A-Za-z][A-Za-z0-9_-]{0,63}\z"),
]
QuestionText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4096),
]
Statement = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
]
SourceUrl = Annotated[
    str, StringConstraints(min_length=1, max_length=2048), AfterValidator(_nonblank),
]
ExactExcerpt = Annotated[
    str, StringConstraints(min_length=1, max_length=1000), AfterValidator(_nonblank),
]
Identity = Annotated[
    str, StringConstraints(min_length=1, max_length=500), AfterValidator(_nonblank),
]
Fingerprint = Annotated[str, StringConstraints(pattern=r"\A[0-9a-f]{64}\z")]
FrozenSnippet = Annotated[str, StringConstraints(min_length=1), AfterValidator(_nonblank)]
FindingId = Annotated[str, StringConstraints(pattern=r"\Af[1-9][0-9]*\z")]


class FindingsContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, validate_default=True)


class ResearchQuestion(FindingsContractModel):
    question_id: QuestionId
    text: QuestionText


class ResearchFindingsScope(FindingsContractModel):
    questions: list[ResearchQuestion] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def unique_questions(self):
        ids = [question.question_id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("question_id must be unique")
        return self


def validate_research_findings_scope(scope: dict, *, query: str) -> ResearchFindingsScope:
    """Default only omitted questions; never replace an explicitly empty list."""
    if isinstance(scope, dict) and "questions" not in scope:
        scope = {**scope, "questions": [{"question_id": "q1", "text": query}]}
    return ResearchFindingsScope.model_validate(scope)


class CandidateReference(FindingsContractModel):
    source_url: SourceUrl
    excerpt: ExactExcerpt


class CandidateFinding(FindingsContractModel):
    question_id: QuestionId
    statement: Statement
    references: list[CandidateReference] = Field(min_length=1, max_length=10)


class QuestionDisposition(FindingsContractModel):
    question_id: QuestionId
    status: Literal["candidate_findings", "unresolved"]
    reason: Statement | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def reason_matches_status(self):
        if self.status == "unresolved" and self.reason is None:
            raise ValueError("unresolved disposition requires a reason")
        if self.status == "candidate_findings" and "reason" in self.model_fields_set:
            raise ValueError("candidate_findings disposition must omit reason")
        return self


class ResearchFindingsCandidate(FindingsContractModel):
    schema_version: Literal["dra.research-findings-candidate.v1"]
    findings: list[CandidateFinding] = Field(max_length=20)
    dispositions: list[QuestionDisposition] = Field(min_length=1, max_length=5)
    reported_contradictions: list[Statement] = Field(default_factory=list, max_length=20)
    limitations: list[Statement] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def unique_dispositions(self):
        ids = [disposition.question_id for disposition in self.dispositions]
        if len(ids) != len(set(ids)):
            raise ValueError("disposition question_id must be unique")
        return self


class BoundSourceReference(FindingsContractModel):
    evidence_id: Identity
    evidence_fingerprint: Fingerprint
    source_url: SourceUrl
    source_identity: SourceUrl
    snippet: FrozenSnippet
    excerpt: ExactExcerpt
    excerpt_start: int = Field(ge=0)
    excerpt_end: int = Field(ge=1)

    @model_validator(mode="after")
    def exact_snippet_offsets(self):
        if not 0 <= self.excerpt_start < self.excerpt_end <= len(self.snippet):
            raise ValueError("excerpt offsets must be within the frozen snippet")
        if self.snippet[self.excerpt_start:self.excerpt_end] != self.excerpt:
            raise ValueError("excerpt must match the frozen snippet at code-point offsets")
        return self


class BoundFinding(FindingsContractModel):
    finding_id: FindingId
    question_id: QuestionId
    statement: Statement
    references: list[BoundSourceReference] = Field(min_length=1, max_length=10)


class ResearchFindingsReport(FindingsContractModel):
    schema_version: Literal["dra.research-findings.v1"]
    run_id: Identity
    profile_id: Identity
    profile_version: Identity
    questions: list[ResearchQuestion] = Field(min_length=1, max_length=5)
    findings: list[BoundFinding] = Field(max_length=20)
    dispositions: list[QuestionDisposition] = Field(min_length=1, max_length=5)
    reported_contradictions: list[Statement] = Field(default_factory=list, max_length=20)
    limitations: list[Statement] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def unique_local_ids(self):
        for ids in (
            [question.question_id for question in self.questions],
            [finding.finding_id for finding in self.findings],
            [disposition.question_id for disposition in self.dispositions],
        ):
            if len(ids) != len(set(ids)):
                raise ValueError("report IDs must be locally unique")
        return self


ResearchFindingsIssueCode = Literal[
    "candidate_missing",
    "candidate_too_large",
    "candidate_invalid_json",
    "candidate_contract_invalid",
    "unknown_question_id",
    "duplicate_question_disposition",
    "question_disposition_missing",
    "question_disposition_conflict",
    "empty_research_output",
    "source_url_not_publishable",
    "source_not_observed",
    "excerpt_not_found",
    "ambiguous_reference",
    "reference_binding_failed",
]


class ResearchFindingsDiagnostics(FindingsContractModel):
    schema_version: Literal["dra.research-findings-diagnostics.v1"]
    run_id: Identity
    issue_codes: list[ResearchFindingsIssueCode] = Field(default_factory=list, max_length=20)
    requested_question_count: int = Field(ge=1, le=5)
    covered_question_count: int = Field(ge=0, le=5)
    unresolved_question_count: int = Field(ge=0, le=5)
    reference_binding_failure_count: int = Field(ge=0, le=200)
