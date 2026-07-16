"""Strict contracts for durable ResearchRun failure causes."""
from __future__ import annotations

from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)


RUN_FAILURE_CAUSE_SCHEMA_VERSION = "dra.run-failure-cause.v1"
RUN_FAILURE_CAUSE_MIGRATION_VERSION = "009_run_failure_cause_v1"
RUN_FAILURE_CAUSE_MIGRATION_CHECKSUM = "run-failure-cause-v1"

RunFailurePhase = Literal["dispatch", "execution", "finalization"]
RUN_FAILURE_CAUSE_CODES = MappingProxyType(
    {
        "dispatch": frozenset(
            {
                "run_dispatch_schedule_failed",
                "run_dispatch_start_failed",
                "run_dispatch_start_timeout",
                "run_dispatch_lease_expired",
            }
        ),
        "execution": frozenset(
            {
                "call_budget_exceeded",
                "recursion_limit_exceeded",
                "invalid_research_packet",
                "missing_research_packet",
                "run_timeout",
                "cancelled",
                "execution_error",
            }
        ),
        "finalization": frozenset(
            {
                "run_timeout",
                "cancelled",
                "run_finalization_failed",
            }
        ),
    }
)


class _StrictContract(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")


class RunFailureCauseWrite(_StrictContract):
    phase: RunFailurePhase
    code: str

    @model_validator(mode="after")
    def require_exact_pair(self):
        if self.code not in RUN_FAILURE_CAUSE_CODES[self.phase]:
            raise ValueError("run_failure_cause_invalid")
        return self


class ObservedRunFailureCause(RunFailureCauseWrite):
    schema_version: Literal["dra.run-failure-cause.v1"] = (
        RUN_FAILURE_CAUSE_SCHEMA_VERSION
    )
    observation_status: Literal["observed"] = "observed"
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("run_failure_cause_timestamp_invalid")
        return value


class NotObservedRunFailureCause(_StrictContract):
    schema_version: Literal["dra.run-failure-cause.v1"] = (
        RUN_FAILURE_CAUSE_SCHEMA_VERSION
    )
    observation_status: Literal["not_observed"] = "not_observed"


RunFailureCauseProjection = Annotated[
    ObservedRunFailureCause | NotObservedRunFailureCause,
    Field(discriminator="observation_status"),
]
RunFailureCauseProjectionAdapter = TypeAdapter(RunFailureCauseProjection)


class RunStatusFailureCauseOpenAPI(BaseModel):
    model_config = ConfigDict(extra="allow")

    failure_cause: RunFailureCauseProjection | None


class RunFailureCauseConflict(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
