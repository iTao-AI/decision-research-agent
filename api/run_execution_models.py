"""Strict private contracts for crash-safe run execution ownership."""
from __future__ import annotations

from threading import Lock
from typing import Annotated
import uuid

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


RUN_EXECUTION_RECOVERY_MIGRATION_VERSION = "010_run_execution_recovery"
RUN_EXECUTION_RECOVERY_MIGRATION_CHECKSUM = "run-execution-recovery-v1"
RUN_EXECUTION_OWNER_STATUSES = frozenset({"active", "closed", "interrupted"})
RUN_EXECUTION_PHASES = frozenset({"execution", "finalization"})
RUN_EXECUTION_RECOVERY_REASONS = frozenset(
    {"previous_boot_interrupted", "pre_v1_running_without_owner"}
)

BootId = Annotated[str, StringConstraints(pattern=r"^boot_[0-9a-f]{32}$")]
OwnerId = Annotated[str, StringConstraints(pattern=r"^owner_[0-9a-f]{32}$")]


class _StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RunExecutionOwnerHandle(_StrictContract):
    run_id: str = Field(min_length=1, max_length=128)
    segment_id: str = Field(min_length=1, max_length=160)
    boot_id: BootId
    owner_id: OwnerId


class RunExecutionConflict(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class RunExecutionOwnerBox:
    """One-assignment handoff for a committed private execution capability."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._handle: RunExecutionOwnerHandle | None = None

    def assign(self, handle: RunExecutionOwnerHandle) -> None:
        if not isinstance(handle, RunExecutionOwnerHandle):
            raise RunExecutionConflict("run_execution_owner_invalid")
        with self._lock:
            if self._handle is not None:
                raise RunExecutionConflict("run_execution_owner_already_assigned")
            self._handle = handle

    def get(self) -> RunExecutionOwnerHandle | None:
        with self._lock:
            return self._handle

    def require(self) -> RunExecutionOwnerHandle:
        handle = self.get()
        if handle is None:
            raise RunExecutionConflict("run_execution_owner_unavailable")
        return handle


def new_boot_id() -> str:
    return f"boot_{uuid.uuid4().hex}"


def new_owner_id() -> str:
    return f"owner_{uuid.uuid4().hex}"
