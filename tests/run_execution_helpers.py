"""Production-only helpers for protected started-run test fixtures."""
from __future__ import annotations

from dataclasses import dataclass
import uuid

from api.run_dispatch_models import RunDispatchClaim
from api.run_dispatch_repository import claim_run_dispatch, start_run_dispatch
from api.run_execution_migrations import migrate_run_execution_recovery_with_backup
from api.run_execution_models import (
    RunExecutionOwnerHandle,
    new_boot_id,
)
from api.run_execution_repository import activate_run_execution_boot


@dataclass(frozen=True)
class StartedRun:
    boot_id: str
    claim: RunDispatchClaim
    handle: RunExecutionOwnerHandle


def activate_run_execution(*, db_path: str) -> str:
    migrate_run_execution_recovery_with_backup(db_path=db_path)
    boot_id = new_boot_id()
    activate_run_execution_boot(db_path=db_path, boot_id=boot_id)
    return boot_id


def activate_and_start_created_run(
    *,
    db_path: str,
    run_id: str,
) -> StartedRun:
    boot_id = activate_run_execution(db_path=db_path)
    claim = claim_run_dispatch(
        db_path=db_path,
        worker_id=f"dispatch_worker_{uuid.uuid4().hex}",
        boot_id=boot_id,
        lease_seconds=30,
        run_id=run_id,
    )
    if claim is None:
        raise AssertionError("expected exact pending dispatch claim")
    handle = start_run_dispatch(db_path=db_path, claim=claim)
    if handle is None:
        raise AssertionError("expected exact protected start")
    return StartedRun(boot_id=boot_id, claim=claim, handle=handle)
