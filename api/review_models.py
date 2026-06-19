from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from typing import Annotated, Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


BoundedId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]
BoundedReason = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
]
ReviewAction = Literal["approve", "reject"]
WorkflowStatus = Literal[
    "checkpoint_pending",
    "waiting_decision",
    "resume_pending",
    "resuming",
    "resolution_pending",
    "approved",
    "rejected",
    "manual_recovery",
]


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReviewDecisionRequest(FrozenModel):
    decision_id: BoundedId
    review_revision: int = Field(ge=1)
    action: ReviewAction
    reason: BoundedReason | None = None
    expected_state_version: int = Field(ge=0)

    @model_validator(mode="after")
    def require_reject_reason(self):
        if self.action == "reject" and self.reason is None:
            raise ValueError("reason is required for reject")
        return self


class ReviewDecisionRecord(FrozenModel):
    decision_id: BoundedId
    run_id: BoundedId
    review_id: BoundedId
    review_revision: int = Field(ge=1)
    action: ReviewAction
    reason: BoundedReason | None
    actor_fingerprint: str
    request_hash: str
    accepted_state_version: int = Field(ge=0)
    created_at: datetime


def durable_hitl_enabled() -> bool:
    return os.getenv(
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL",
        "false",
    ).strip().lower() == "true"


def review_workflow_id(run_id: str, review_id: str, revision: int) -> str:
    value = f"{run_id}\n{review_id}\n{revision}"
    return f"rwf_{uuid.uuid5(uuid.NAMESPACE_URL, value).hex}"


def checkpoint_thread_id(workflow_id: str) -> str:
    return f"review_{workflow_id}"


def post_review_segment_id(run_id: str, review_id: str, revision: int) -> str:
    value = f"{run_id}\n{review_id}\n{revision}\npost_review"
    suffix = uuid.uuid5(uuid.NAMESPACE_URL, value).hex[:16]
    return f"{run_id}_seg_review_{suffix}"


def review_resolution_id(decision_id: str) -> str:
    return f"resolution_{uuid.uuid5(uuid.NAMESPACE_URL, decision_id).hex}"


def decision_request_hash(
    *,
    run_id: str,
    review_id: str,
    request: ReviewDecisionRequest,
) -> str:
    payload = {
        "run_id": run_id,
        "review_id": review_id,
        "decision_id": request.decision_id,
        "review_revision": request.review_revision,
        "action": request.action,
        "reason": request.reason,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
