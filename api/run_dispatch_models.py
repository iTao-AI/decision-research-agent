"""Strict application-owned contracts for durable run dispatch."""
from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


RUN_DISPATCH_MIGRATION_VERSION = "008_run_dispatch_reconciliation"
RUN_DISPATCH_MIGRATION_CHECKSUM = "run-dispatch-reconciliation-v1"
RUN_DISPATCH_STATUSES = frozenset({"pending", "leased", "started", "failed"})
MAX_RUN_DISPATCH_ATTEMPTS = 3


class RunDispatchConflict(RuntimeError):
    """Bounded internal dispatch conflict without raw exception details."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class RunDispatchClaim(BaseModel):
    """Immutable lease claim used to fence one execution start attempt."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    run_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=256)
    segment_id: str = Field(min_length=1, max_length=160)
    query: str
    profile_id: str = Field(min_length=1, max_length=128)
    profile_version: str = Field(min_length=1, max_length=64)
    scope_json: str = Field(min_length=2)
    lease_owner: str = Field(pattern=r"^dispatch_worker_[0-9a-f]{32}$")
    attempt_count: int = Field(ge=1)
    lease_expires_at: datetime

    @field_validator("lease_expires_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("run_dispatch_lease_invalid")
        return value

    @field_validator("scope_json")
    @classmethod
    def require_canonical_scope(cls, value: str) -> str:
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("run_dispatch_scope_invalid") from exc
        if not isinstance(payload, dict):
            raise ValueError("run_dispatch_scope_invalid")
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if canonical != value:
            raise ValueError("run_dispatch_scope_invalid")
        return value

    @property
    def scope(self) -> dict[str, Any]:
        return json.loads(self.scope_json)
