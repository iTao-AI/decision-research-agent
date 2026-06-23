from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter


BoundedPublicationId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]
PublicationStatus = Literal["review_required", "ready", "blocked", "stale"]


class PublicationContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VerificationFinalizationRequest(PublicationContract):
    expected_state_version: int = Field(ge=0)


class PublicationRecord(PublicationContract):
    publication_id: BoundedPublicationId
    run_id: BoundedPublicationId
    revision: int = Field(ge=1)
    verification_snapshot_id: BoundedPublicationId
    review_id: BoundedPublicationId
    status: PublicationStatus
    is_current: bool
    artifact_ids: tuple[BoundedPublicationId, ...]
    content_hash: str = Field(min_length=64, max_length=64)
    supersedes_publication_id: BoundedPublicationId | None = None
    created_at: str
    resolved_at: str | None = None
    staled_at: str | None = None


_BOUNDED_ID_ADAPTER = TypeAdapter(BoundedPublicationId)


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def publication_id_for(
    *,
    run_id: str,
    revision: int,
    verification_snapshot_id: str,
) -> str:
    _BOUNDED_ID_ADAPTER.validate_python(run_id)
    _BOUNDED_ID_ADAPTER.validate_python(verification_snapshot_id)
    if revision < 1:
        raise ValueError("revision must be at least 1")
    payload = {
        'run_id': run_id,
        'revision': revision,
        'verification_snapshot_id': verification_snapshot_id,
    }
    return f"publication_{_canonical_hash(payload)}"


def encode_evidence_cursor(*, evidence_id: str) -> str:
    _BOUNDED_ID_ADAPTER.validate_python(evidence_id)
    raw = json.dumps(
        [evidence_id],
        separators=(",", ":"),
    ).encode("utf-8")
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_evidence_cursor(cursor: str) -> str:
    try:
        if not cursor:
            raise ValueError
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(urlsafe_b64decode(padded).decode("utf-8"))
        if not isinstance(value, list) or len(value) != 1:
            raise ValueError
        evidence_id = _BOUNDED_ID_ADAPTER.validate_python(value[0])
    except Exception as exc:
        raise ValueError("invalid_evidence_cursor") from exc
    return evidence_id
