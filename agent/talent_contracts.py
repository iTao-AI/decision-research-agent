"""Versioned service contracts for the Talent Hiring Signal profile."""
from __future__ import annotations

from datetime import date, datetime
import re
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


BoundedString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
SourceType = Literal["public_job_posting", "provided_aggregate"]
_AGGREGATE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TimeWindow(ContractModel):
    start: date
    end: date

    @model_validator(mode="after")
    def validate_window(self):
        days = (self.end - self.start).days
        if days < 0:
            raise ValueError("time_window end must not be before start")
        if days > 366:
            raise ValueError("time_window must not exceed 366 days")
        return self


class SampleRef(ContractModel):
    sample_id: BoundedString
    source_type: SourceType
    reference: BoundedString

    @model_validator(mode="after")
    def validate_public_reference(self):
        if self.source_type == "public_job_posting":
            parsed = urlparse(self.reference)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("public_job_posting reference must be an http(s) URL")
        if self.source_type == "provided_aggregate" and not _AGGREGATE_ID_RE.fullmatch(
            self.reference
        ):
            raise ValueError("provided_aggregate reference must be a versioned aggregate ID")
        return self


class ResearchScope(ContractModel):
    target_roles: list[BoundedString] = Field(min_length=1, max_length=20)
    target_companies: list[BoundedString] = Field(max_length=50)
    time_window: TimeWindow
    declared_samples: list[SampleRef] = Field(max_length=500)
    allowed_source_types: list[SourceType] = Field(min_length=1, max_length=2)
    research_questions: list[BoundedString] = Field(min_length=1, max_length=20)
    requested_outputs: list[BoundedString] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_declared_source_types(self):
        allowed = set(self.allowed_source_types)
        undeclared = {
            sample.source_type for sample in self.declared_samples
            if sample.source_type not in allowed
        }
        if undeclared:
            raise ValueError(
                "declared sample source types must be included in allowed_source_types"
            )
        return self


class Finding(ContractModel):
    finding_id: BoundedString
    research_question_id: BoundedString
    statement: BoundedString
    evidence_refs: list[BoundedString] = Field(min_length=1)
    observed_at: datetime | None = None
    sample_scope: BoundedString
    confidence: float = Field(ge=0, le=1)
    evidence_gaps: list[BoundedString] = Field(default_factory=list)
    contradictions: list[BoundedString] = Field(default_factory=list)
    limitations: list[BoundedString] = Field(default_factory=list)


class Claim(ContractModel):
    claim_id: BoundedString
    text: BoundedString
    claim_type: BoundedString
    finding_refs: list[BoundedString] = Field(min_length=1)
    evidence_refs: list[BoundedString] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    citation_status: Literal["cited", "uncited"]
    verification_status: Literal["verified", "unverified"]
    review_status: Literal["pending", "not_required", "required", "resolved"]
    conflict_status: Literal["none", "conflicting"]
    limitations: list[BoundedString] = Field(default_factory=list)


class ResearchPacket(ContractModel):
    packet_id: BoundedString
    scope_id: BoundedString
    findings: list[Finding]
    candidate_claims: list[Claim]
    contradictions: list[BoundedString] = Field(default_factory=list)
    limitations: list[BoundedString] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self):
        finding_ids = [finding.finding_id for finding in self.findings]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("finding_id must be unique within a ResearchPacket")

        claim_ids = [claim.claim_id for claim in self.candidate_claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim_id must be unique within a ResearchPacket")

        known_findings = set(finding_ids)
        for claim in self.candidate_claims:
            unknown = set(claim.finding_refs) - known_findings
            if unknown:
                raise ValueError(
                    f"claim {claim.claim_id} references unknown finding: "
                    + ", ".join(sorted(unknown))
                )
        return self


class EvidenceSnapshot(ContractModel):
    evidence_id: BoundedString
    source_url: BoundedString | None = None
    snippet: BoundedString
    verification_status: Literal["verified", "unverified"]
    verification_state: Literal[
        "unverified",
        "verified",
        "rejected",
    ] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    verification_origin: Literal[
        "none",
        "declared_fixture",
        "human",
    ] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    verification_revision: int | None = Field(
        default=None,
        ge=0,
        exclude_if=lambda value: value is None,
    )


class ReviewBundle(ContractModel):
    review_id: BoundedString
    run_id: BoundedString
    revision: int = Field(ge=1)
    status: Literal["not_required", "required", "resolved"]
    claim_snapshots: list[Claim]
    evidence_snapshots: list[EvidenceSnapshot]
    triggers: list[str]
    recommended_actions: list[str]
    required_before_delivery: bool


class DecisionBrief(ContractModel):
    schema_version: BoundedString
    run_id: BoundedString
    profile_id: BoundedString
    profile_version: BoundedString
    input_snapshot_hash: BoundedString
    renderer_version: BoundedString
    canonicalization_version: BoundedString
    scope: ResearchScope
    executive_summary: str
    findings: list[Finding]
    claims: list[Claim]
    evidence_summary: list[dict[str, Any]]
    conflicts: list[str]
    limitations: list[str]
    recommendations: list[str]
    review_summary: dict[str, Any]
    quality_summary: dict[str, Any]
    generated_at: datetime
    content_hash: str = ""
