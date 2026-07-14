"""Typed contracts for durable run-creation idempotency."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, TypeAdapter, ValidationError


RUN_CREATE_REQUEST_SCHEMA_VERSION = "dra.run-create-request.v1"
RUN_CREATE_IDEMPOTENCY_MIGRATION_VERSION = "007_run_create_idempotency"
RUN_CREATE_IDEMPOTENCY_MIGRATION_CHECKSUM = "run-create-idempotency-v1"
_KEY_HASH_NAMESPACE = "dra.run-create-idempotency.v1\0"

IdempotencyKey = Annotated[
    str,
    StringConstraints(
        min_length=8,
        max_length=128,
    ),
]
_IDEMPOTENCY_KEY_ADAPTER = TypeAdapter(IdempotencyKey)


class _StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RunCreateRequestFingerprint(_StrictContract):
    schema_version: Literal["dra.run-create-request.v1"] = (
        RUN_CREATE_REQUEST_SCHEMA_VERSION
    )
    query: str
    thread_id: str | None
    profile_id: str
    scope: dict[str, Any]


class RunCreationAcceptance(_StrictContract):
    run_id: str
    thread_id: str
    segment_id: str
    idempotent_replay: bool


def validate_idempotency_key(value: str) -> str:
    try:
        validated = _IDEMPOTENCY_KEY_ADAPTER.validate_python(value, strict=True)
    except ValidationError as exc:
        raise ValueError("run_idempotency_key_invalid") from exc
    if re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}",
        validated,
        flags=re.ASCII,
    ) is None:
        raise ValueError("run_idempotency_key_invalid")
    return validated


def idempotency_key_hash(value: str) -> str:
    validated = validate_idempotency_key(value)
    return hashlib.sha256(
        f"{_KEY_HASH_NAMESPACE}{validated}".encode("utf-8")
    ).hexdigest()


def run_create_request_hash(
    *,
    query: str,
    thread_id: str | None,
    profile_id: str,
    scope: dict[str, Any],
) -> str:
    fingerprint = RunCreateRequestFingerprint(
        query=query,
        thread_id=thread_id,
        profile_id=profile_id,
        scope=scope,
    )
    encoded = json.dumps(
        fingerprint.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
