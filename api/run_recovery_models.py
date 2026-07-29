"""Strict public and private contracts for explicit run replacement."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    model_validator,
)


RUN_RECOVERY_SCHEMA_VERSION = "dra.run-recovery.v1"
RUN_RECOVERY_REQUEST_SCHEMA_VERSION = "dra.run-recovery-request.v1"
_RECOVERY_KEY_HASH_NAMESPACE = "dra.run-recovery-idempotency.v1\0"

_RecoveryKey = Annotated[str, StringConstraints(min_length=8, max_length=128)]
_RECOVERY_KEY_ADAPTER = TypeAdapter(_RecoveryKey)


class _StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RunRecoveryAcceptance(_StrictContract):
    schema_version: Literal["dra.run-recovery.v1"] = RUN_RECOVERY_SCHEMA_VERSION
    status: Literal["accepted"] = "accepted"
    reason: Literal["previous_boot_interrupted", "pre_v1_running_without_owner"]
    interrupted_phase: Literal["execution", "finalization"]
    source_run_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=256)
    segment_id: str = Field(min_length=1, max_length=160)
    recovery_attempt: Literal[1]
    idempotent_replay: bool

    @model_validator(mode="after")
    def _validate_replacement_identity(self) -> Self:
        if self.source_run_id == self.run_id:
            raise ValueError("run_recovery_response_invalid")
        if self.segment_id != f"{self.run_id}_seg_000":
            raise ValueError("run_recovery_response_invalid")
        return self


class RunRecoveryRequestFingerprint(_StrictContract):
    schema_version: Literal["dra.run-recovery-request.v1"] = (
        RUN_RECOVERY_REQUEST_SCHEMA_VERSION
    )
    source_run_id: str
    segment_id: str
    query: str
    thread_id: str
    profile_id: str
    profile_version: str
    scope: dict[str, Any]
    execution_status: Literal["failed"]
    review_status: Literal["not_required"]
    delivery_status: Literal["failed"]
    terminal_state_version: Literal[2]
    failure_phase: Literal["execution", "finalization"]
    failure_code: str
    recovery_reason: Literal[
        "previous_boot_interrupted", "pre_v1_running_without_owner"
    ]
    interrupted_phase: Literal["execution", "finalization"]
    recovery_attempt: Literal[1]


class RunRecoveryConflict(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def validate_recovery_key(value: str) -> str:
    try:
        validated = _RECOVERY_KEY_ADAPTER.validate_python(value, strict=True)
    except ValidationError as exc:
        raise ValueError("run_recovery_key_invalid") from exc
    if re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", validated, flags=re.ASCII
    ) is None:
        raise ValueError("run_recovery_key_invalid")
    return validated


def recovery_key_hash(value: str) -> str:
    validated = validate_recovery_key(value)
    return hashlib.sha256(
        f"{_RECOVERY_KEY_HASH_NAMESPACE}{validated}".encode("utf-8")
    ).hexdigest()


def run_recovery_request_hash(**values: Any) -> str:
    fingerprint = RunRecoveryRequestFingerprint(**values)
    encoded = json.dumps(
        fingerprint.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
