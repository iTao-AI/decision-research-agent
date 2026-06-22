from __future__ import annotations

from typing import Any, Literal
import hashlib
import json
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator


VerificationAction = Literal["verify", "reject"]
VerificationOrigin = Literal["none", "declared_fixture", "human"]
VerificationState = Literal["unverified", "verified", "rejected"]
PreflightStatus = Literal["eligible", "blocked"]
RejectReasonCode = Literal[
    "source_unavailable",
    "content_mismatch",
    "source_out_of_scope",
    "ambiguous_source",
    "insufficient_context",
    "other",
]

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


class VerificationContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PreflightCheck(VerificationContract):
    code: str = Field(min_length=1, max_length=100)
    passed: bool
    explanation: str = Field(min_length=1, max_length=300)


class EvidencePreflightResult(VerificationContract):
    preflight_id: str
    run_id: str
    evidence_id: str
    evidence_fingerprint: str
    preflight_version: str
    status: PreflightStatus
    checks: tuple[PreflightCheck, ...]
    preflight_hash: str


class VerificationDecisionRequest(VerificationContract):
    verification_id: str
    evidence_fingerprint: str
    expected_revision: int = Field(ge=0)
    action: VerificationAction
    confirm_source_match: bool = False
    reason_code: RejectReasonCode | None = None
    reason_note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_action_fields(self):
        if not _ID_RE.fullmatch(self.verification_id):
            raise ValueError("verification_id has an invalid format")
        if not _FINGERPRINT_RE.fullmatch(self.evidence_fingerprint):
            raise ValueError("evidence_fingerprint must be lowercase sha256")
        if self.action == "verify":
            if not self.confirm_source_match:
                raise ValueError("confirm_source_match is required for verify")
            if self.reason_code is not None or self.reason_note is not None:
                raise ValueError("reason_code and reason_note are reject-only")
        elif self.reason_code is None:
            raise ValueError("reason_code is required for reject")
        return self


class VerificationDecisionRecord(VerificationContract):
    verification_id: str
    run_id: str
    evidence_id: str
    evidence_fingerprint: str
    revision: int = Field(ge=1)
    action: VerificationAction
    reason_code: RejectReasonCode | None = None
    reason_note: str | None = None
    preflight_id: str
    created_at: str


class EffectiveEvidenceVerification(VerificationContract):
    run_id: str
    evidence_id: str
    evidence_fingerprint: str
    verification_status: Literal["verified", "unverified"]
    verification_state: VerificationState
    verification_origin: VerificationOrigin
    verification_revision: int = Field(ge=0)
    decision_id: str | None = None


class VerificationSnapshotRecord(VerificationContract):
    snapshot_id: str
    run_id: str
    revision: int = Field(ge=1)
    snapshot: tuple[EffectiveEvidenceVerification, ...]
    snapshot_hash: str
    created_at: str


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def preflight_id_for(payload: dict[str, Any]) -> str:
    return f"vpf_{canonical_hash(payload)}"


def snapshot_id_for(*, run_id: str, snapshot_hash: str) -> str:
    return f"vsnap_{canonical_hash({'run_id': run_id, 'hash': snapshot_hash})}"


def verification_request_hash(
    *,
    run_id: str,
    evidence_id: str,
    request: VerificationDecisionRequest,
) -> str:
    return canonical_hash(
        {
            "run_id": run_id,
            "evidence_id": evidence_id,
            "request": request.model_dump(mode="json"),
        }
    )
