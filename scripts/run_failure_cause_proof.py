#!/usr/bin/env python3
"""Build or check the deterministic durable run-failure-cause proof."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import stat
import subprocess
import sys
import tempfile
from tempfile import TemporaryDirectory
import threading
from types import ModuleType
from typing import Any
from unittest.mock import patch


REPORT_SCHEMA_VERSION = "dra.run-failure-cause-proof.v1"
FIXED_TIME = "2026-07-16T00:00:00+00:00"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BASELINE_JSON_PATH = PROJECT_ROOT / "docs/evidence/run-failure-cause-v1.json"
BASELINE_MARKDOWN_PATH = PROJECT_ROOT / "docs/evidence/run-failure-cause-v1.md"
MAX_BASELINE_BYTES = 1_000_000
_INVALID_CODE = "run_failure_cause_proof_invalid"

EXPECTED_CASE_IDS = (
    "completed_null",
    "historical_not_observed",
    "dispatch_schedule_failed",
    "dispatch_start_failed",
    "dispatch_start_timeout",
    "dispatch_lease_expired",
    "execution_call_budget_exceeded",
    "execution_recursion_limit_exceeded",
    "execution_invalid_research_packet",
    "execution_missing_research_packet",
    "execution_timeout",
    "finalization_timeout",
    "execution_cancelled",
    "finalization_cancelled",
    "execution_error",
    "finalization_failed",
)

EXPECTED_INVARIANT_IDS = (
    "retry_attempts_have_no_cause",
    "dispatch_codes_match",
    "terminal_insert_fault_rolls_back",
    "terminal_guards_fail_closed",
    "first_cause_is_immutable",
    "restart_projection_is_identical",
    "termination_ownership_is_distinct",
    "prestart_cancellation_is_infrastructure_only",
    "inner_self_cancel_is_bounded",
    "launched_terminal_task_settles",
    "public_failure_surface_is_redacted",
    "bounded_cli_inputs_fail_closed",
    "fresh_outputs_are_byte_identical",
)

BOUNDARIES = {
    "application_database_terminal_authority": "proven",
    "production_scheduler_timeout_cancellation": "proven",
    "framework_native_signal_mapping": "proven",
    "status_projection_after_restart": "proven",
    "result_and_downstream_v1_compatibility": "separate_gate",
    "live_provider_result": "not_observed",
    "external_side_effect_exactly_once": "not_claimed",
}

LIMITS = [
    "Deterministic local production-path contract proof, not a live-provider measurement.",
    "SQLite single-node terminal authority is proven; multi-instance operation is not claimed.",
    "Result and downstream v1 compatibility remain owned by their separate regression gates.",
]


def _common(
    *,
    run_status: str,
    segment_status: str,
    dispatch_status: str,
    state_version: int,
    projection_status: str,
    phase: str | None,
    code: str | None,
    recorded_at: str | None,
    evidence_count: int = 0,
    artifact_count: int = 0,
) -> dict[str, Any]:
    return {
        "run_status": run_status,
        "segment_status": segment_status,
        "dispatch_status": dispatch_status,
        "state_version": state_version,
        "projection_status": projection_status,
        "phase": phase,
        "code": code,
        "recorded_at": recorded_at,
        "timestamp_aligned": True,
        "evidence_count": evidence_count,
        "artifact_count": artifact_count,
    }


_OBSERVED_AT = "2026-07-16T00:00:00Z"
EXPECTED_OBSERVATIONS: dict[str, dict[str, Any]] = {
    "completed_null": _common(
        run_status="completed",
        segment_status="completed",
        dispatch_status="started",
        state_version=2,
        projection_status="null",
        phase=None,
        code=None,
        recorded_at=None,
        artifact_count=1,
    ),
    "historical_not_observed": _common(
        run_status="failed",
        segment_status="failed",
        dispatch_status="absent",
        state_version=3,
        projection_status="not_observed",
        phase=None,
        code=None,
        recorded_at=None,
    ),
}

for _case_id, _code in (
    ("dispatch_schedule_failed", "run_dispatch_schedule_failed"),
    ("dispatch_start_failed", "run_dispatch_start_failed"),
    ("dispatch_start_timeout", "run_dispatch_start_timeout"),
    ("dispatch_lease_expired", "run_dispatch_lease_expired"),
):
    EXPECTED_OBSERVATIONS[_case_id] = {
        **_common(
            run_status="failed",
            segment_status="failed",
            dispatch_status="failed",
            state_version=1,
            projection_status="observed",
            phase="dispatch",
            code=_code,
            recorded_at=_OBSERVED_AT,
        ),
        "attempt_count": 3,
        "last_error_matches_cause": True,
    }
EXPECTED_OBSERVATIONS["dispatch_start_timeout"]["callback_count"] = 3
EXPECTED_OBSERVATIONS["dispatch_lease_expired"]["recorded_at"] = (
    "2026-07-16T00:01:33Z"
)
EXPECTED_OBSERVATIONS["dispatch_lease_expired"]["lease_expires_at"] = None

for _case_id, _phase, _code in (
    ("execution_call_budget_exceeded", "execution", "call_budget_exceeded"),
    (
        "execution_recursion_limit_exceeded",
        "execution",
        "recursion_limit_exceeded",
    ),
    (
        "execution_invalid_research_packet",
        "execution",
        "invalid_research_packet",
    ),
    (
        "execution_missing_research_packet",
        "execution",
        "missing_research_packet",
    ),
    ("execution_timeout", "execution", "run_timeout"),
    ("finalization_timeout", "finalization", "run_timeout"),
    ("execution_cancelled", "execution", "cancelled"),
    ("finalization_cancelled", "finalization", "cancelled"),
    ("execution_error", "execution", "execution_error"),
    ("finalization_failed", "finalization", "run_finalization_failed"),
):
    EXPECTED_OBSERVATIONS[_case_id] = _common(
        run_status="failed",
        segment_status="failed",
        dispatch_status="started",
        state_version=2,
        projection_status="observed",
        phase=_phase,
        code=_code,
        recorded_at=_OBSERVED_AT,
        evidence_count=(1 if _case_id in {
            "execution_timeout",
            "execution_cancelled",
            "execution_error",
        } else 0),
    )

EXPECTED_OBSERVATIONS["execution_call_budget_exceeded"]["framework_signal_count"] = 2
EXPECTED_OBSERVATIONS["execution_recursion_limit_exceeded"][
    "framework_signal_count"
] = 1
EXPECTED_OBSERVATIONS["execution_invalid_research_packet"][
    "packet_resolution"
] = "invalid"
EXPECTED_OBSERVATIONS["execution_missing_research_packet"][
    "packet_resolution"
] = "missing"
for _case_id, _origin in (
    ("execution_timeout", "timeout"),
    ("finalization_timeout", "timeout"),
    ("execution_cancelled", "cancelled"),
    ("finalization_cancelled", "cancelled"),
):
    EXPECTED_OBSERVATIONS[_case_id].update(
        termination_origin=_origin,
        callback_count=1,
        tracker_settled=True,
    )


CLOCK_PATCH_TARGETS = (
    "api.run_repository._now",
    "api.run_dispatch_repository._now",
    "api.run_dispatch_worker.claim_run_dispatch",
)


@dataclass(frozen=True)
class _ProductionModules:
    repository: ModuleType
    migrations: ModuleType
    dispatch: ModuleType
    worker: ModuleType
    tracker: ModuleType
    server: ModuleType


def _load_production_modules() -> _ProductionModules:
    """Load production owners lazily without initializing a provider model."""

    repository = importlib.import_module("api.run_repository")
    migrations = importlib.import_module("api.run_migrations")
    dispatch = importlib.import_module("api.run_dispatch_repository")
    worker = importlib.import_module("api.run_dispatch_worker")
    tracker = importlib.import_module("api.task_tracker")

    stub_created = "agent.main_agent" not in sys.modules
    if stub_created:
        main_agent_stub = ModuleType("agent.main_agent")

        async def _proof_agent_port(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("run_failure_cause_proof_agent_port_unconfigured")

        main_agent_stub.run_deep_agent = _proof_agent_port  # type: ignore[attr-defined]
        sys.modules["agent.main_agent"] = main_agent_stub
    try:
        server = importlib.import_module("api.server")
    finally:
        if stub_created:
            sys.modules.pop("agent.main_agent", None)
    return _ProductionModules(
        repository=repository,
        migrations=migrations,
        dispatch=dispatch,
        worker=worker,
        tracker=tracker,
        server=server,
    )


class _ClaimClock:
    def __init__(self, real_claim: Any) -> None:
        self._real_claim = real_claim
        self._counts: dict[str, int] = {}
        self._base = datetime.fromisoformat(FIXED_TIME)

    def __call__(self, **kwargs: Any) -> Any:
        run_id = kwargs["run_id"]
        offset = self._counts.get(run_id, 0)
        self._counts[run_id] = offset + 1
        return self._real_claim(
            **kwargs,
            now=self._base + timedelta(seconds=31 * offset),
        )


@contextmanager
def _fixed_production_clocks(modules: _ProductionModules):
    with ExitStack() as stack:
        if "api.run_repository._now" in CLOCK_PATCH_TARGETS:
            stack.enter_context(
                patch.object(modules.repository, "_now", lambda: FIXED_TIME)
            )
        if "api.run_dispatch_repository._now" in CLOCK_PATCH_TARGETS:
            stack.enter_context(
                patch.object(modules.dispatch, "_now", lambda: FIXED_TIME)
            )
        if "api.run_dispatch_worker.claim_run_dispatch" in CLOCK_PATCH_TARGETS:
            stack.enter_context(
                patch.object(
                    modules.worker,
                    "claim_run_dispatch",
                    _ClaimClock(modules.dispatch.claim_run_dispatch),
                )
            )
        yield


def _raw_snapshot(
    modules: _ProductionModules,
    *,
    db_path: str,
    run_id: str,
) -> dict[str, Any]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        run = connection.execute(
            """
            SELECT execution_status, state_version, updated_at
            FROM research_runs_v2 WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        segment = connection.execute(
            """
            SELECT status, updated_at FROM run_segments
            WHERE run_id = ? AND kind = 'initial'
            """,
            (run_id,),
        ).fetchone()
        dispatch = connection.execute(
            """
            SELECT status, attempt_count, last_error_code, updated_at,
                   lease_expires_at
            FROM run_dispatches_v1 WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        cause = connection.execute(
            """
            SELECT observation_status, terminal_state_version, phase, code,
                   recorded_at
            FROM run_failure_causes_v1 WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        evidence_count = connection.execute(
            "SELECT COUNT(*) FROM evidence_entries_v2 WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]
        artifact_count = connection.execute(
            "SELECT COUNT(*) FROM run_artifacts_v2 WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]
    finally:
        connection.close()
    if run is None or segment is None:
        raise ValueError("run_failure_cause_proof_authority_missing")
    public = modules.repository.get_run(db_path=db_path, run_id=run_id)
    if public is None:
        raise ValueError("run_failure_cause_proof_projection_missing")
    return {
        "run": dict(run),
        "segment": dict(segment),
        "dispatch": dict(dispatch) if dispatch is not None else None,
        "cause": dict(cause) if cause is not None else None,
        "evidence_count": int(evidence_count),
        "artifact_count": int(artifact_count),
        "public": public,
    }


def _case_from_snapshot(
    case_id: str,
    snapshot: dict[str, Any],
    **extra: Any,
) -> dict[str, Any]:
    raw_cause = snapshot["cause"]
    public_cause = snapshot["public"]["failure_cause"]
    if raw_cause is None:
        if public_cause is not None:
            raise ValueError("run_failure_cause_proof_projection_mismatch")
        projection_status = "null"
        phase = code = recorded_at = None
        timestamp_aligned = True
    elif raw_cause["observation_status"] == "not_observed":
        if public_cause != {
            "schema_version": "dra.run-failure-cause.v1",
            "observation_status": "not_observed",
        } or any(
            raw_cause[key] is not None
            for key in ("terminal_state_version", "phase", "code", "recorded_at")
        ):
            raise ValueError("run_failure_cause_proof_historical_mismatch")
        projection_status = "not_observed"
        phase = code = recorded_at = None
        timestamp_aligned = True
    else:
        if (
            raw_cause["terminal_state_version"]
            != snapshot["run"]["state_version"]
            or raw_cause["recorded_at"] != snapshot["run"]["updated_at"]
            or raw_cause["recorded_at"] != snapshot["segment"]["updated_at"]
            or public_cause is None
            or public_cause["phase"] != raw_cause["phase"]
            or public_cause["code"] != raw_cause["code"]
        ):
            raise ValueError("run_failure_cause_proof_authority_mismatch")
        projection_status = "observed"
        phase = public_cause["phase"]
        code = public_cause["code"]
        recorded_at = public_cause["recorded_at"]
        timestamp_aligned = True

    observations = {
        "run_status": snapshot["run"]["execution_status"],
        "segment_status": snapshot["segment"]["status"],
        "dispatch_status": (
            snapshot["dispatch"]["status"]
            if snapshot["dispatch"] is not None
            else "absent"
        ),
        "state_version": snapshot["run"]["state_version"],
        "projection_status": projection_status,
        "phase": phase,
        "code": code,
        "recorded_at": recorded_at,
        "timestamp_aligned": timestamp_aligned,
        "evidence_count": snapshot["evidence_count"],
        "artifact_count": snapshot["artifact_count"],
        **extra,
    }
    return _case(case_id, observations)


async def _dispatch_and_get_task(
    modules: _ProductionModules,
    worker: Any,
    run_id: str,
) -> asyncio.Task[Any]:
    if not await worker.dispatch_run(run_id):
        raise ValueError("run_failure_cause_proof_dispatch_missing")
    dispatch = modules.dispatch.get_run_dispatch(db_path=worker.db_path, run_id=run_id)
    task_id = f"{run_id}:dispatch:{dispatch['attempt_count']}"
    task = modules.tracker.get_active_task(task_id)
    if task is None:
        raise ValueError("run_failure_cause_proof_tracked_task_missing")
    return task


async def _await_tracked(
    modules: _ProductionModules,
    *,
    task: asyncio.Task[Any],
    task_id: str,
    cancellation: bool = False,
) -> None:
    if cancellation:
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise ValueError("run_failure_cause_proof_cancellation_missing")
    else:
        await task
    await asyncio.sleep(0)
    if modules.tracker.get_active_task(task_id) is not None:
        raise ValueError("run_failure_cause_proof_task_residue")


def _scheduled_worker(
    modules: _ProductionModules,
    db_path: str,
    *,
    suffix: str,
    scheduler: Any | None = None,
) -> Any:
    if scheduler is None:
        scheduler = lambda claim: modules.server._schedule_run_dispatch(
            claim,
            db_path=db_path,
        )
    return modules.worker.RunDispatchWorker(
        db_path=db_path,
        scheduler=scheduler,
        worker_id=f"dispatch_worker_{suffix * 32}",
        lease_seconds=30,
        poll_seconds=0.01,
    )


def _assert_retry_without_cause(
    modules: _ProductionModules,
    *,
    db_path: str,
    run_id: str,
    attempt_count: int,
) -> None:
    snapshot = _raw_snapshot(
        modules,
        db_path=db_path,
        run_id=run_id,
    )
    if (
        snapshot["run"]["execution_status"] != "pending"
        or snapshot["run"]["state_version"] != 0
        or snapshot["segment"]["status"] != "pending"
        or snapshot["cause"] is not None
        or snapshot["public"]["failure_cause"] is not None
        or snapshot["dispatch"] is None
        or snapshot["dispatch"]["attempt_count"] != attempt_count
        or snapshot["dispatch"]["status"] != "pending"
    ):
        raise ValueError("run_failure_cause_proof_retry_cause_invalid")


async def _completed_case(
    modules: _ProductionModules,
    root: Path,
) -> dict[str, Any]:
    from agent.harness_contracts import ReportCandidate
    from agent.run_result import AgentRunResult

    db_path = str(root / "completed.db")
    created = modules.repository.create_run(
        db_path=db_path,
        thread_id="proof-completed-thread",
        query="proof completed query",
    )

    async def completed(*_args: Any, **_kwargs: Any) -> AgentRunResult:
        return AgentRunResult(
            thread_id=created["thread_id"],
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            query="proof completed query",
            session_dir=PurePosixPath("/workspace/proof"),
            report_candidate=ReportCandidate(
                path=PurePosixPath("/workspace/research-report.md"),
                content="# Deterministic result",
            ),
            started_at=datetime.fromisoformat(FIXED_TIME),
        )

    worker = _scheduled_worker(modules, db_path, suffix="1")
    with patch.object(modules.server, "run_deep_agent", completed):
        task = await _dispatch_and_get_task(
            modules,
            worker,
            created["run_id"],
        )
        await _await_tracked(
            modules,
            task=task,
            task_id=f"{created['run_id']}:dispatch:1",
        )
    return _case_from_snapshot(
        "completed_null",
        _raw_snapshot(modules, db_path=db_path, run_id=created["run_id"]),
    )


def _historical_case(
    modules: _ProductionModules,
    root: Path,
) -> dict[str, Any]:
    db_path = str(root / "historical.db")
    modules.repository.init_run_schema(db_path)
    run_id = "run_historical_failed_0"
    recorded_at = "2026-07-15T00:00:00+00:00"
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute("DROP TABLE run_failure_causes_v1")
            connection.execute(
                "DELETE FROM schema_migrations WHERE version = ?",
                ("009_run_failure_cause_v1",),
            )
            connection.execute(
                """
                INSERT INTO research_runs_v2 (
                    run_id, thread_id, query, profile_id, profile_version,
                    scope_json, execution_status, review_status,
                    delivery_status, state_version, created_at, updated_at
                ) VALUES (?, 'proof-historical-thread', 'proof historical query',
                          'generic', '1', '{}', 'failed', 'not_required',
                          'failed', 3, ?, ?)
                """,
                (run_id, recorded_at, recorded_at),
            )
            connection.execute(
                """
                INSERT INTO run_segments (
                    segment_id, run_id, kind, sequence, attempt, status,
                    created_at, updated_at
                ) VALUES (?, ?, 'initial', 0, 1, 'failed', ?, ?)
                """,
                (f"{run_id}_seg_000", run_id, recorded_at, recorded_at),
            )
    finally:
        connection.close()
    Path(f"{db_path}.pre-run-failure-cause.bak").unlink(missing_ok=True)
    modules.migrations.migrate_with_backup(
        db_path=db_path,
        backup_path=str(root / "historical-pre-009.bak"),
    )
    modules.migrations.verify_run_schema(
        db_path=db_path,
        include_evidence_verification=True,
        include_publication=True,
    )
    return _case_from_snapshot(
        "historical_not_observed",
        _raw_snapshot(modules, db_path=db_path, run_id=run_id),
    )


async def _schedule_failure_case(
    modules: _ProductionModules,
    root: Path,
) -> dict[str, Any]:
    db_path = str(root / "schedule-failed.db")
    created = modules.repository.create_run(
        db_path=db_path,
        thread_id="proof-schedule-failed-thread",
        query="proof schedule failure query",
    )

    def fail_schedule(_claim: Any) -> None:
        raise RuntimeError("synthetic scheduler failure")

    worker = _scheduled_worker(
        modules,
        db_path,
        suffix="2",
        scheduler=fail_schedule,
    )
    with patch.object(modules.worker.logging, "error"):
        for attempt in (1, 2, 3):
            if not await worker.dispatch_run(created["run_id"]):
                raise ValueError("run_failure_cause_proof_schedule_attempt_missing")
            if attempt < 3:
                _assert_retry_without_cause(
                    modules,
                    db_path=db_path,
                    run_id=created["run_id"],
                    attempt_count=attempt,
                )
    snapshot = _raw_snapshot(
        modules,
        db_path=db_path,
        run_id=created["run_id"],
    )
    return _case_from_snapshot(
        "dispatch_schedule_failed",
        snapshot,
        attempt_count=snapshot["dispatch"]["attempt_count"],
        last_error_matches_cause=(
            snapshot["dispatch"]["last_error_code"]
            == snapshot["cause"]["code"]
        ),
    )


async def _start_failure_case(
    modules: _ProductionModules,
    root: Path,
) -> dict[str, Any]:
    db_path = str(root / "start-failed.db")
    created = modules.repository.create_run(
        db_path=db_path,
        thread_id="proof-start-failed-thread",
        query="proof start failure query",
    )
    worker = _scheduled_worker(modules, db_path, suffix="3")

    def fail_start(**_kwargs: Any) -> bool:
        raise RuntimeError("synthetic start failure")

    with patch.object(modules.server, "start_run_dispatch", fail_start):
        for attempt in (1, 2, 3):
            task = await _dispatch_and_get_task(
                modules,
                worker,
                created["run_id"],
            )
            await _await_tracked(
                modules,
                task=task,
                task_id=f"{created['run_id']}:dispatch:{attempt}",
            )
            if attempt < 3:
                _assert_retry_without_cause(
                    modules,
                    db_path=db_path,
                    run_id=created["run_id"],
                    attempt_count=attempt,
                )
    snapshot = _raw_snapshot(
        modules,
        db_path=db_path,
        run_id=created["run_id"],
    )
    return _case_from_snapshot(
        "dispatch_start_failed",
        snapshot,
        attempt_count=snapshot["dispatch"]["attempt_count"],
        last_error_matches_cause=(
            snapshot["dispatch"]["last_error_code"]
            == snapshot["cause"]["code"]
        ),
    )


async def _start_timeout_case(
    modules: _ProductionModules,
    root: Path,
) -> dict[str, Any]:
    db_path = str(root / "start-timeout.db")
    created = modules.repository.create_run(
        db_path=db_path,
        thread_id="proof-start-timeout-thread",
        query="proof start timeout query",
    )
    worker = _scheduled_worker(modules, db_path, suffix="4")
    callback_calls: list[int] = []
    origins: list[Any] = []
    real_create = modules.server.create_tracked_task
    real_origin_type = modules.server.TerminationOrigin
    real_reconcile = modules.server.reconcile_run_dispatch_timeout

    def create_with_deadline(coroutine: Any, task_id: str, **kwargs: Any) -> Any:
        kwargs["timeout_seconds"] = 10
        return real_create(coroutine, task_id, **kwargs)

    class ObservableOrigin(real_origin_type):
        def __init__(self) -> None:
            super().__init__()
            origins.append(self)

    def count_reconcile(**kwargs: Any) -> Any:
        callback_calls.append(1)
        return real_reconcile(**kwargs)

    loop = asyncio.get_running_loop()
    real_loop_time = loop.time
    offset = [0.0]
    with (
        patch.object(loop, "time", lambda: real_loop_time() + offset[0]),
        patch.object(modules.server, "create_tracked_task", create_with_deadline),
        patch.object(modules.server, "TerminationOrigin", ObservableOrigin),
        patch.object(
            modules.server,
            "reconcile_run_dispatch_timeout",
            count_reconcile,
        ),
    ):
        for attempt in (1, 2, 3):
            entered = threading.Event()
            release = threading.Event()

            def held_start(**_kwargs: Any) -> bool:
                entered.set()
                if not release.wait(timeout=3):
                    raise RuntimeError("run_failure_cause_proof_start_barrier_timeout")
                return False

            task: asyncio.Task[Any] | None = None
            try:
                with patch.object(modules.server, "start_run_dispatch", held_start):
                    task = await _dispatch_and_get_task(
                        modules,
                        worker,
                        created["run_id"],
                    )
                    if not await asyncio.to_thread(entered.wait, 1):
                        raise ValueError("run_failure_cause_proof_start_barrier_missing")
                    offset[0] += 100.0
                    for _ in range(100):
                        if origins and origins[-1].value == "timeout":
                            break
                        await asyncio.sleep(0)
                    if not origins or origins[-1].value != "timeout":
                        raise ValueError("run_failure_cause_proof_timeout_origin_missing")
                    release.set()
                    await _await_tracked(
                        modules,
                        task=task,
                        task_id=f"{created['run_id']}:dispatch:{attempt}",
                    )
            finally:
                release.set()
                if task is not None and not task.done():
                    task.cancel()
                    try:
                        await task
                    except BaseException:
                        pass
            if attempt < 3:
                _assert_retry_without_cause(
                    modules,
                    db_path=db_path,
                    run_id=created["run_id"],
                    attempt_count=attempt,
                )
    snapshot = _raw_snapshot(
        modules,
        db_path=db_path,
        run_id=created["run_id"],
    )
    return _case_from_snapshot(
        "dispatch_start_timeout",
        snapshot,
        attempt_count=snapshot["dispatch"]["attempt_count"],
        last_error_matches_cause=(
            snapshot["dispatch"]["last_error_code"]
            == snapshot["cause"]["code"]
        ),
        callback_count=len(callback_calls),
    )


async def _lease_expired_case(
    modules: _ProductionModules,
    root: Path,
) -> dict[str, Any]:
    db_path = str(root / "lease-expired.db")
    created = modules.repository.create_run(
        db_path=db_path,
        thread_id="proof-lease-expired-thread",
        query="proof lease expiry query",
    )
    scheduled: list[Any] = []
    worker = _scheduled_worker(
        modules,
        db_path,
        suffix="5",
        scheduler=scheduled.append,
    )
    for _ in range(3):
        if not await worker.dispatch_run(created["run_id"]):
            raise ValueError("run_failure_cause_proof_lease_claim_missing")
    if await worker.dispatch_run(created["run_id"]):
        raise ValueError("run_failure_cause_proof_fourth_attempt_created")
    if len(scheduled) != 3:
        raise ValueError("run_failure_cause_proof_lease_schedule_count_invalid")
    snapshot = _raw_snapshot(
        modules,
        db_path=db_path,
        run_id=created["run_id"],
    )
    return _case_from_snapshot(
        "dispatch_lease_expired",
        snapshot,
        attempt_count=snapshot["dispatch"]["attempt_count"],
        last_error_matches_cause=(
            snapshot["dispatch"]["last_error_code"]
            == snapshot["cause"]["code"]
        ),
        lease_expires_at=snapshot["dispatch"]["lease_expires_at"],
    )


async def _service_case_snapshot(
    modules: _ProductionModules,
    root: Path,
    *,
    filename: str,
    thread_id: str,
    harness: Any,
    profile_id: str = "generic",
    scope: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], Any]:
    from api.research_execution_service import ResearchExecutionService

    db_path = str(root / filename)
    created = modules.repository.create_run(
        db_path=db_path,
        thread_id=thread_id,
        query="proof agent query",
        profile_id=profile_id,
        scope=scope or {},
    )
    service = ResearchExecutionService(
        harness=harness,
        project_root=root,
        clear_run_cache=lambda _run_id: None,
    )
    outcomes: list[Any] = []

    async def service_port(query: str, request_thread_id: str, **kwargs: Any) -> Any:
        outcome = await service.execute(query, request_thread_id, **kwargs)
        outcomes.append(outcome)
        return outcome

    worker = _scheduled_worker(modules, db_path, suffix="6")
    with patch.object(modules.server, "run_deep_agent", service_port):
        task = await _dispatch_and_get_task(
            modules,
            worker,
            created["run_id"],
        )
        await _await_tracked(
            modules,
            task=task,
            task_id=f"{created['run_id']}:dispatch:1",
        )
    if len(outcomes) != 1:
        raise ValueError("run_failure_cause_proof_service_outcome_missing")
    return (
        _raw_snapshot(
            modules,
            db_path=db_path,
            run_id=created["run_id"],
        ),
        outcomes[0],
    )


def _failure_signature(snapshot: dict[str, Any]) -> tuple[Any, ...]:
    return (
        snapshot["run"]["execution_status"],
        snapshot["run"]["state_version"],
        snapshot["segment"]["status"],
        snapshot["dispatch"]["status"],
        snapshot["cause"]["observation_status"],
        snapshot["cause"]["terminal_state_version"],
        snapshot["cause"]["phase"],
        snapshot["cause"]["code"],
        snapshot["cause"]["recorded_at"],
        snapshot["public"]["failure_cause"],
    )


async def _native_signal_snapshot(
    modules: _ProductionModules,
    root: Path,
    *,
    filename: str,
    thread_id: str,
    native_exception: BaseException,
) -> dict[str, Any]:
    from agent.deepagents_harness import DeepAgentsHarness

    class RaisingGraph:
        async def astream(self, _input: Any, *, config: Any, context: Any):
            del config, context
            if False:
                yield {}
            raise native_exception

    graph = RaisingGraph()
    harness = DeepAgentsHarness(
        graph=graph,
        backend=object(),
        permissions=(),
        skills=(),
        profile_graphs={"generic": graph},
    )
    snapshot, _ = await _service_case_snapshot(
        modules,
        root,
        filename=filename,
        thread_id=thread_id,
        harness=harness,
    )
    return snapshot


async def _call_budget_case(
    modules: _ProductionModules,
    root: Path,
) -> dict[str, Any]:
    from langchain.agents.middleware.model_call_limit import (
        ModelCallLimitExceededError,
    )
    from langchain.agents.middleware.tool_call_limit import (
        ToolCallLimitExceededError,
    )

    model_exception = ModelCallLimitExceededError(1, 1, 1, 1)
    tool_exception = ToolCallLimitExceededError(
        1,
        1,
        1,
        1,
        tool_name="search",
    )
    model_snapshot = await _native_signal_snapshot(
        modules,
        root,
        filename="native-model-limit.db",
        thread_id="proof-native-model-limit-thread",
        native_exception=model_exception,
    )
    tool_snapshot = await _native_signal_snapshot(
        modules,
        root,
        filename="native-tool-limit.db",
        thread_id="proof-native-tool-limit-thread",
        native_exception=tool_exception,
    )
    if _failure_signature(model_snapshot) != _failure_signature(tool_snapshot):
        raise ValueError("run_failure_cause_proof_native_limit_mismatch")
    return _case_from_snapshot(
        "execution_call_budget_exceeded",
        model_snapshot,
        framework_signal_count=2,
    )


async def _recursion_case(
    modules: _ProductionModules,
    root: Path,
) -> dict[str, Any]:
    from langgraph.errors import GraphRecursionError

    snapshot = await _native_signal_snapshot(
        modules,
        root,
        filename="native-recursion.db",
        thread_id="proof-native-recursion-thread",
        native_exception=GraphRecursionError("synthetic bounded recursion"),
    )
    return _case_from_snapshot(
        "execution_recursion_limit_exceeded",
        snapshot,
        framework_signal_count=1,
    )


async def _packet_case(
    modules: _ProductionModules,
    root: Path,
    *,
    case_id: str,
    packet_content: str | None,
    resolution: str,
) -> dict[str, Any]:
    from langchain_core.messages import ToolMessage

    class PacketHarness:
        async def execute(
            self,
            request: Any,
            *,
            runtime_context: Any,
            observer: Any,
        ) -> Any:
            del request, runtime_context
            if packet_content is not None:
                observer.on_stream_chunk(
                    {
                        "tools": {
                            "messages": [
                                ToolMessage(
                                    content=packet_content,
                                    tool_call_id="call-task",
                                    name="task",
                                )
                            ]
                        }
                    }
                )
            return observer.snapshot_outcome()

    snapshot, outcome = await _service_case_snapshot(
        modules,
        root,
        filename=f"{resolution}-packet.db",
        thread_id=f"proof-{resolution}-packet-thread",
        harness=PacketHarness(),
        profile_id="talent-hiring-signal",
        scope={},
    )
    expected_code = EXPECTED_OBSERVATIONS[case_id]["code"]
    if outcome.failure_kind != expected_code:
        raise ValueError("run_failure_cause_proof_packet_resolution_mismatch")
    invalid_diagnostics = [
        value
        for value in outcome.diagnostics
        if value.startswith("invalid_research_packet:")
    ]
    if bool(invalid_diagnostics) is (packet_content is None):
        raise ValueError("run_failure_cause_proof_packet_diagnostic_mismatch")
    return _case_from_snapshot(
        case_id,
        snapshot,
        packet_resolution=resolution,
    )


def _proof_evidence(created: dict[str, Any], *, fingerprint: str) -> Any:
    from agent.research import EvidenceEntry

    return EvidenceEntry(
        thread_id=created["thread_id"],
        query_text="synthetic proof query",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url="https://example.invalid/proof-source",
        source_identity="https://example.invalid/proof-source",
        snippet="bounded partial evidence",
        evidence_fingerprint=fingerprint,
    )


def _proof_result(
    created: dict[str, Any],
    root: Path,
    *,
    evidence_entries: list[Any] | None = None,
    with_report: bool = False,
) -> Any:
    from agent.harness_contracts import ReportCandidate
    from agent.run_result import AgentRunResult

    return AgentRunResult(
        thread_id=created["thread_id"],
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        query="synthetic proof query",
        session_dir=root,
        evidence_entries=evidence_entries or [],
        report_candidate=(
            ReportCandidate(
                path=PurePosixPath("/workspace/research-report.md"),
                content="# Deterministic result",
            )
            if with_report
            else None
        ),
        started_at=datetime.fromisoformat(FIXED_TIME),
    )


async def _wait_for_origin(origin: Any, value: str) -> None:
    for _ in range(200):
        if origin.value == value:
            return
        await asyncio.sleep(0)
    raise ValueError("run_failure_cause_proof_termination_origin_missing")


async def _execution_timeout_case(
    modules: _ProductionModules,
    root: Path,
) -> dict[str, Any]:
    db_path = str(root / "execution-timeout.db")
    created = modules.repository.create_run(
        db_path=db_path,
        thread_id="proof-execution-timeout-thread",
        query="synthetic proof query",
    )
    evidence = _proof_evidence(created, fingerprint="proof-execution-timeout")
    entered = asyncio.Event()
    origins: list[Any] = []
    callback_calls: list[int] = []
    real_create = modules.server.create_tracked_task
    real_origin_type = modules.server.TerminationOrigin
    real_reconcile = modules.server.reconcile_run_dispatch_timeout

    async def held_execution(*_args: Any, **kwargs: Any) -> Any:
        kwargs["outcome_box"].publish(
            _proof_result(created, root, evidence_entries=[evidence])
        )
        entered.set()
        await asyncio.Event().wait()

    def create_with_deadline(coroutine: Any, task_id: str, **kwargs: Any) -> Any:
        kwargs["timeout_seconds"] = 10
        return real_create(coroutine, task_id, **kwargs)

    class ObservableOrigin(real_origin_type):
        def __init__(self) -> None:
            super().__init__()
            origins.append(self)

    def count_reconcile(**kwargs: Any) -> Any:
        callback_calls.append(1)
        return real_reconcile(**kwargs)

    loop = asyncio.get_running_loop()
    real_loop_time = loop.time
    offset = [0.0]
    worker = _scheduled_worker(modules, db_path, suffix="7")
    task: asyncio.Task[Any] | None = None
    with (
        patch.object(loop, "time", lambda: real_loop_time() + offset[0]),
        patch.object(modules.server, "run_deep_agent", held_execution),
        patch.object(modules.server, "create_tracked_task", create_with_deadline),
        patch.object(modules.server, "TerminationOrigin", ObservableOrigin),
        patch.object(
            modules.server,
            "reconcile_run_dispatch_timeout",
            count_reconcile,
        ),
    ):
        try:
            task = await _dispatch_and_get_task(modules, worker, created["run_id"])
            await asyncio.wait_for(entered.wait(), timeout=1)
            if len(origins) != 1:
                raise ValueError("run_failure_cause_proof_origin_count_invalid")
            offset[0] = 100.0
            await _wait_for_origin(origins[0], "timeout")
            await _await_tracked(
                modules,
                task=task,
                task_id=f"{created['run_id']}:dispatch:1",
            )
        finally:
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except BaseException:
                    pass
    snapshot = _raw_snapshot(
        modules,
        db_path=db_path,
        run_id=created["run_id"],
    )
    return _case_from_snapshot(
        "execution_timeout",
        snapshot,
        termination_origin=origins[0].value,
        callback_count=len(callback_calls),
        tracker_settled=(
            modules.tracker.get_active_task(
                f"{created['run_id']}:dispatch:1"
            )
            is None
        ),
    )


class _CheckpointCapture:
    def __init__(self) -> None:
        self.instances: list[Any] = []

    def type_for(self, base_type: type) -> type:
        capture = self

        class GatedCheckpoint(base_type):
            def __init__(self) -> None:
                super().__init__()
                self.tracker_waiting = asyncio.Event()
                self.release_tracker = asyncio.Event()
                capture.instances.append(self)

            async def wait_requested(self) -> None:
                await super().wait_requested()
                self.tracker_waiting.set()
                await self.release_tracker.wait()

        return GatedCheckpoint


async def _finalization_termination_case(
    modules: _ProductionModules,
    root: Path,
    *,
    case_id: str,
    termination_kind: str,
) -> dict[str, Any]:
    db_path = str(root / f"{case_id}.db")
    created = modules.repository.create_run(
        db_path=db_path,
        thread_id=f"proof-{case_id}-thread",
        query="synthetic proof query",
    )
    checkpoints = _CheckpointCapture()
    checkpoint_type = checkpoints.type_for(modules.server.FinalizationCheckpoint)
    origins: list[Any] = []
    callback_calls: list[int] = []
    real_origin_type = modules.server.TerminationOrigin
    real_create = modules.server.create_tracked_task
    real_timeout_reconcile = modules.server.reconcile_run_dispatch_timeout
    real_cancel_reconcile = modules.server.reconcile_run_dispatch_cancellation

    async def completed(*_args: Any, **_kwargs: Any) -> Any:
        return _proof_result(created, root, with_report=True)

    class ObservableOrigin(real_origin_type):
        def __init__(self) -> None:
            super().__init__()
            origins.append(self)

    def create_with_deadline(coroutine: Any, task_id: str, **kwargs: Any) -> Any:
        kwargs["timeout_seconds"] = 10
        return real_create(coroutine, task_id, **kwargs)

    def count_timeout(**kwargs: Any) -> Any:
        callback_calls.append(1)
        return real_timeout_reconcile(**kwargs)

    def count_cancel(**kwargs: Any) -> Any:
        callback_calls.append(1)
        return real_cancel_reconcile(**kwargs)

    loop = asyncio.get_running_loop()
    real_loop_time = loop.time
    offset = [0.0]
    worker = _scheduled_worker(modules, db_path, suffix="8")
    task: asyncio.Task[Any] | None = None
    with (
        patch.object(loop, "time", lambda: real_loop_time() + offset[0]),
        patch.object(modules.server, "run_deep_agent", completed),
        patch.object(modules.server, "FinalizationCheckpoint", checkpoint_type),
        patch.object(modules.server, "TerminationOrigin", ObservableOrigin),
        patch.object(modules.server, "create_tracked_task", create_with_deadline),
        patch.object(
            modules.server,
            "reconcile_run_dispatch_timeout",
            count_timeout,
        ),
        patch.object(
            modules.server,
            "reconcile_run_dispatch_cancellation",
            count_cancel,
        ),
    ):
        try:
            task = await _dispatch_and_get_task(modules, worker, created["run_id"])
            for _ in range(100):
                if checkpoints.instances:
                    break
                await asyncio.sleep(0)
            if len(checkpoints.instances) != 1 or len(origins) != 1:
                raise ValueError("run_failure_cause_proof_checkpoint_missing")
            checkpoint = checkpoints.instances[0]
            await asyncio.wait_for(checkpoint.tracker_waiting.wait(), timeout=1)
            if termination_kind == "timeout":
                offset[0] = 100.0
                checkpoint.release_tracker.set()
                await _wait_for_origin(origins[0], "timeout")
                await _await_tracked(
                    modules,
                    task=task,
                    task_id=f"{created['run_id']}:dispatch:1",
                )
            else:
                task.cancel()
                await _wait_for_origin(origins[0], "cancelled")
                checkpoint.release_tracker.set()
                await _await_tracked(
                    modules,
                    task=task,
                    task_id=f"{created['run_id']}:dispatch:1",
                    cancellation=True,
                )
        finally:
            for checkpoint in checkpoints.instances:
                checkpoint.release_tracker.set()
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except BaseException:
                    pass
    snapshot = _raw_snapshot(
        modules,
        db_path=db_path,
        run_id=created["run_id"],
    )
    return _case_from_snapshot(
        case_id,
        snapshot,
        termination_origin=origins[0].value,
        callback_count=len(callback_calls),
        tracker_settled=(
            modules.tracker.get_active_task(
                f"{created['run_id']}:dispatch:1"
            )
            is None
        ),
    )


async def _execution_cancelled_case(
    modules: _ProductionModules,
    root: Path,
) -> dict[str, Any]:
    db_path = str(root / "execution-cancelled.db")
    created = modules.repository.create_run(
        db_path=db_path,
        thread_id="proof-execution-cancelled-thread",
        query="synthetic proof query",
    )
    evidence = _proof_evidence(created, fingerprint="proof-execution-cancelled")
    entered = asyncio.Event()
    origins: list[Any] = []
    callback_calls: list[int] = []
    real_origin_type = modules.server.TerminationOrigin
    real_reconcile = modules.server.reconcile_run_dispatch_cancellation

    async def held_execution(*_args: Any, **kwargs: Any) -> Any:
        kwargs["outcome_box"].publish(
            _proof_result(created, root, evidence_entries=[evidence])
        )
        entered.set()
        await asyncio.Event().wait()

    class ObservableOrigin(real_origin_type):
        def __init__(self) -> None:
            super().__init__()
            origins.append(self)

    def count_reconcile(**kwargs: Any) -> Any:
        callback_calls.append(1)
        return real_reconcile(**kwargs)

    worker = _scheduled_worker(modules, db_path, suffix="9")
    task: asyncio.Task[Any] | None = None
    with (
        patch.object(modules.server, "run_deep_agent", held_execution),
        patch.object(modules.server, "TerminationOrigin", ObservableOrigin),
        patch.object(
            modules.server,
            "reconcile_run_dispatch_cancellation",
            count_reconcile,
        ),
    ):
        try:
            task = await _dispatch_and_get_task(modules, worker, created["run_id"])
            await asyncio.wait_for(entered.wait(), timeout=1)
            task.cancel()
            await _wait_for_origin(origins[0], "cancelled")
            await _await_tracked(
                modules,
                task=task,
                task_id=f"{created['run_id']}:dispatch:1",
                cancellation=True,
            )
        finally:
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except BaseException:
                    pass
    snapshot = _raw_snapshot(
        modules,
        db_path=db_path,
        run_id=created["run_id"],
    )
    return _case_from_snapshot(
        "execution_cancelled",
        snapshot,
        termination_origin=origins[0].value,
        callback_count=len(callback_calls),
        tracker_settled=(
            modules.tracker.get_active_task(
                f"{created['run_id']}:dispatch:1"
            )
            is None
        ),
    )


_RAW_EXCEPTION_MARKER = "Traceback" + " synthetic proof exception"
_RAW_CREDENTIAL_MARKER = "sk-" + "SyntheticProofMarker000000"
_RAW_UNIX_PATH_MARKER = "/private/" + "dra-proof-secret"
_RAW_WINDOWS_PATH_MARKER = "C:" + "\\Users\\proof\\secret"
_RAW_HOST_MARKER = "internal." + "proof.invalid"
_RAW_PROVIDER_MARKER = "provider-" + "payload-proof"
_RAW_QUERY_MARKER = "synthetic raw query marker"


async def _raised_task_case(
    modules: _ProductionModules,
    root: Path,
    *,
    case_id: str,
    finalization_failure: bool,
) -> dict[str, Any]:
    db_path = str(root / f"{case_id}.db")
    created = modules.repository.create_run(
        db_path=db_path,
        thread_id=f"proof-{case_id}-thread",
        query=_RAW_QUERY_MARKER,
    )
    evidence = _proof_evidence(created, fingerprint="proof-execution-error")

    async def execution_error(*_args: Any, **kwargs: Any) -> Any:
        kwargs["outcome_box"].publish(
            _proof_result(created, root, evidence_entries=[evidence])
        )
        raise RuntimeError(
            " ".join(
                (
                    _RAW_EXCEPTION_MARKER,
                    _RAW_CREDENTIAL_MARKER,
                    _RAW_UNIX_PATH_MARKER,
                    _RAW_WINDOWS_PATH_MARKER,
                    _RAW_HOST_MARKER,
                    _RAW_PROVIDER_MARKER,
                    _RAW_QUERY_MARKER,
                )
            )
        )

    async def completed(*_args: Any, **_kwargs: Any) -> Any:
        return _proof_result(created, root, with_report=True)

    def fail_artifact(_result: Any) -> Any:
        raise RuntimeError(
            f"{_RAW_EXCEPTION_MARKER} {_RAW_UNIX_PATH_MARKER} "
            f"{_RAW_CREDENTIAL_MARKER} {_RAW_PROVIDER_MARKER}"
        )

    worker = _scheduled_worker(modules, db_path, suffix="a")
    task: asyncio.Task[Any] | None = None
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(
                modules.server,
                "run_deep_agent",
                completed if finalization_failure else execution_error,
            )
        )
        if finalization_failure:
            stack.enter_context(
                patch.object(
                    modules.server,
                    "build_generic_result_artifact",
                    fail_artifact,
                )
            )
        try:
            task = await _dispatch_and_get_task(modules, worker, created["run_id"])
            try:
                await task
            except RuntimeError:
                pass
            else:
                raise ValueError("run_failure_cause_proof_expected_error_missing")
            await asyncio.sleep(0)
            if modules.tracker.get_active_task(
                f"{created['run_id']}:dispatch:1"
            ) is not None:
                raise ValueError("run_failure_cause_proof_task_residue")
        finally:
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except BaseException:
                    pass
    snapshot = _raw_snapshot(
        modules,
        db_path=db_path,
        run_id=created["run_id"],
    )
    return _case_from_snapshot(case_id, snapshot)


def _start_invariant_run(
    modules: _ProductionModules,
    *,
    db_path: str,
    thread_id: str,
) -> tuple[dict[str, Any], Any]:
    created = modules.repository.create_run(
        db_path=db_path,
        thread_id=thread_id,
        query="synthetic invariant query",
    )
    claim = modules.dispatch.claim_run_dispatch(
        db_path=db_path,
        worker_id="dispatch_worker_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        lease_seconds=30,
        run_id=created["run_id"],
        now=datetime.fromisoformat(FIXED_TIME),
    )
    if claim is None or not modules.dispatch.start_run_dispatch(
        db_path=db_path,
        claim=claim,
    ):
        raise ValueError("run_failure_cause_proof_invariant_start_missing")
    return created, claim


def _prove_transaction_rollback(
    modules: _ProductionModules,
    root: Path,
) -> None:
    from api.run_failure_cause_models import RunFailureCauseWrite

    db_path = str(root / "invariant-rollback.db")
    created, _ = _start_invariant_run(
        modules,
        db_path=db_path,
        thread_id="proof-invariant-rollback-thread",
    )
    evidence = _proof_evidence(created, fingerprint="proof-rollback-evidence")
    artifact = modules.server.build_generic_result_artifact(
        _proof_result(created, root, with_report=True)
    )
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                """
                CREATE TRIGGER proof_reject_cause_insert
                BEFORE INSERT ON run_failure_causes_v1
                BEGIN
                    SELECT RAISE(ABORT, 'proof cause insert fault');
                END
                """
            )
    finally:
        connection.close()
    failed = False
    try:
        modules.repository.finalize_run_transaction(
            db_path=db_path,
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            expected_state_version=1,
            allowed_previous_statuses={"running"},
            execution_status="failed",
            delivery_status="failed",
            evidence_entries=[evidence],
            artifacts=[artifact],
            failure_cause=RunFailureCauseWrite(
                phase="execution",
                code="execution_error",
            ),
        )
    except Exception:
        failed = True
    if not failed:
        raise ValueError("run_failure_cause_proof_insert_fault_accepted")
    snapshot = _raw_snapshot(
        modules,
        db_path=db_path,
        run_id=created["run_id"],
    )
    connection = sqlite3.connect(db_path)
    try:
        packet_count = connection.execute(
            "SELECT COUNT(*) FROM research_packets_v2 WHERE run_id = ?",
            (created["run_id"],),
        ).fetchone()[0]
        review_count = connection.execute(
            "SELECT COUNT(*) FROM review_bundles_v2 WHERE run_id = ?",
            (created["run_id"],),
        ).fetchone()[0]
    finally:
        connection.close()
    if (
        snapshot["run"]["execution_status"] != "running"
        or snapshot["run"]["state_version"] != 1
        or snapshot["segment"]["status"] != "running"
        or snapshot["cause"] is not None
        or snapshot["evidence_count"] != 0
        or snapshot["artifact_count"] != 0
        or packet_count != 0
        or review_count != 0
    ):
        raise ValueError("run_failure_cause_proof_insert_fault_not_atomic")


def _prove_terminal_guards(
    modules: _ProductionModules,
    root: Path,
) -> None:
    from api.run_failure_cause_models import RunFailureCauseWrite

    db_path = str(root / "invariant-guards.db")
    created = modules.repository.create_run(
        db_path=db_path,
        thread_id="proof-invariant-guards-thread",
        query="synthetic invariant query",
    )
    rejected = 0
    for execution_status, cause in (
        (
            "completed",
            RunFailureCauseWrite(phase="execution", code="execution_error"),
        ),
        ("failed", None),
    ):
        try:
            modules.repository.finalize_run_transaction(
                db_path=db_path,
                run_id=created["run_id"],
                segment_id=created["segment_id"],
                expected_state_version=0,
                allowed_previous_statuses={"pending"},
                execution_status=execution_status,
                delivery_status=(
                    "ready" if execution_status == "completed" else "failed"
                ),
                evidence_entries=[],
                failure_cause=cause,
            )
        except Exception:
            rejected += 1
    run = modules.repository.get_run(db_path=db_path, run_id=created["run_id"])
    if (
        rejected != 2
        or run is None
        or run["execution_status"] != "pending"
        or run["state_version"] != 0
        or run["failure_cause"] is not None
    ):
        raise ValueError("run_failure_cause_proof_terminal_guard_invalid")


def _prove_immutable_winner_and_restart(
    modules: _ProductionModules,
    root: Path,
) -> None:
    from api.run_failure_cause_models import RunFailureCauseWrite

    db_path = str(root / "invariant-immutable.db")
    created, _ = _start_invariant_run(
        modules,
        db_path=db_path,
        thread_id="proof-invariant-immutable-thread",
    )
    cause = RunFailureCauseWrite(phase="execution", code="execution_error")
    if not modules.repository.finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=1,
        allowed_previous_statuses={"running"},
        execution_status="failed",
        delivery_status="failed",
        evidence_entries=[],
        failure_cause=cause,
    ):
        raise ValueError("run_failure_cause_proof_winner_missing")
    first = _raw_snapshot(
        modules,
        db_path=db_path,
        run_id=created["run_id"],
    )
    duplicate = modules.repository.finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=1,
        allowed_previous_statuses={"running"},
        execution_status="failed",
        delivery_status="failed",
        evidence_entries=[],
        failure_cause=RunFailureCauseWrite(
            phase="execution",
            code="run_timeout",
        ),
    )
    second = _raw_snapshot(
        modules,
        db_path=db_path,
        run_id=created["run_id"],
    )
    if duplicate is not False or _failure_signature(first) != _failure_signature(
        second
    ):
        raise ValueError("run_failure_cause_proof_winner_replaced")

    code = (
        "import json,sys; from api.run_repository import get_run; "
        "value=get_run(db_path=sys.argv[1], run_id=sys.argv[2]); "
        "print(json.dumps(value['failure_cause'], sort_keys=True, separators=(',', ':')))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code, db_path, created["run_id"]],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"},
    )
    restarted = json.loads(completed.stdout)
    if restarted != first["public"]["failure_cause"] or completed.stderr:
        raise ValueError("run_failure_cause_proof_restart_mismatch")


async def _prove_prestart_cancellation(
    modules: _ProductionModules,
    root: Path,
) -> None:
    db_path = str(root / "invariant-prestart-cancel.db")
    created = modules.repository.create_run(
        db_path=db_path,
        thread_id="proof-invariant-prestart-cancel-thread",
        query="synthetic invariant query",
    )
    worker = _scheduled_worker(modules, db_path, suffix="c")
    origins: list[Any] = []
    real_origin_type = modules.server.TerminationOrigin

    class ObservableOrigin(real_origin_type):
        def __init__(self) -> None:
            super().__init__()
            origins.append(self)

    with patch.object(modules.server, "TerminationOrigin", ObservableOrigin):
        for attempt in (1, 2, 3):
            entered = threading.Event()
            release = threading.Event()

            def held_start(**_kwargs: Any) -> bool:
                entered.set()
                if not release.wait(timeout=3):
                    raise RuntimeError("run_failure_cause_proof_cancel_barrier_timeout")
                return False

            task: asyncio.Task[Any] | None = None
            try:
                with patch.object(modules.server, "start_run_dispatch", held_start):
                    task = await _dispatch_and_get_task(
                        modules,
                        worker,
                        created["run_id"],
                    )
                    if not await asyncio.to_thread(entered.wait, 1):
                        raise ValueError(
                            "run_failure_cause_proof_cancel_barrier_missing"
                        )
                    task.cancel()
                    await _wait_for_origin(origins[-1], "cancelled")
                    if task.done():
                        raise ValueError(
                            "run_failure_cause_proof_late_start_not_settled"
                        )
                    release.set()
                    await _await_tracked(
                        modules,
                        task=task,
                        task_id=f"{created['run_id']}:dispatch:{attempt}",
                        cancellation=True,
                    )
            finally:
                release.set()
                if task is not None and not task.done():
                    task.cancel()
                    try:
                        await task
                    except BaseException:
                        pass
            snapshot = _raw_snapshot(
                modules,
                db_path=db_path,
                run_id=created["run_id"],
            )
            expected_status = "pending" if attempt < 3 else "leased"
            if (
                snapshot["dispatch"]["status"] != expected_status
                or snapshot["dispatch"]["attempt_count"] != attempt
                or snapshot["run"]["execution_status"] != "pending"
                or snapshot["cause"] is not None
                or snapshot["public"]["failure_cause"] is not None
            ):
                raise ValueError(
                    "run_failure_cause_proof_prestart_cancellation_invalid"
                )


async def _prove_inner_self_cancellation(
    modules: _ProductionModules,
    root: Path,
) -> None:
    db_path = str(root / "invariant-inner-self-cancel.db")
    created = modules.repository.create_run(
        db_path=db_path,
        thread_id="proof-invariant-inner-self-cancel-thread",
        query="synthetic invariant query",
    )
    origins: list[Any] = []
    callbacks: list[str] = []
    real_origin_type = modules.server.TerminationOrigin
    real_timeout = modules.server.reconcile_run_dispatch_timeout
    real_cancel = modules.server.reconcile_run_dispatch_cancellation

    class ObservableOrigin(real_origin_type):
        def __init__(self) -> None:
            super().__init__()
            origins.append(self)

    async def self_cancel(*_args: Any, **_kwargs: Any) -> Any:
        raise asyncio.CancelledError

    def count_timeout(**kwargs: Any) -> Any:
        callbacks.append("timeout")
        return real_timeout(**kwargs)

    def count_cancel(**kwargs: Any) -> Any:
        callbacks.append("cancelled")
        return real_cancel(**kwargs)

    worker = _scheduled_worker(modules, db_path, suffix="d")
    with (
        patch.object(modules.server, "run_deep_agent", self_cancel),
        patch.object(modules.server, "TerminationOrigin", ObservableOrigin),
        patch.object(
            modules.server,
            "reconcile_run_dispatch_timeout",
            count_timeout,
        ),
        patch.object(
            modules.server,
            "reconcile_run_dispatch_cancellation",
            count_cancel,
        ),
    ):
        task = await _dispatch_and_get_task(modules, worker, created["run_id"])
        await _await_tracked(
            modules,
            task=task,
            task_id=f"{created['run_id']}:dispatch:1",
            cancellation=True,
        )
    snapshot = _raw_snapshot(
        modules,
        db_path=db_path,
        run_id=created["run_id"],
    )
    if (
        len(origins) != 1
        or origins[0].value != "unset"
        or callbacks
        or snapshot["run"]["execution_status"] != "failed"
        or snapshot["cause"]["phase"] != "execution"
        or snapshot["cause"]["code"] != "execution_error"
    ):
        raise ValueError("run_failure_cause_proof_inner_cancel_invalid")


async def _prove_terminal_settlement(
    modules: _ProductionModules,
    root: Path,
) -> None:
    target_entered = asyncio.Event()
    release_target = asyncio.Event()

    async def settlement_target() -> str:
        target_entered.set()
        await release_target.wait()
        return "settled"

    async def settlement_owner() -> tuple[Any, BaseException | None, int]:
        target = asyncio.create_task(settlement_target())
        return await modules.server.settle_shielded_task(target)

    owner = asyncio.create_task(settlement_owner())
    try:
        await asyncio.wait_for(target_entered.wait(), timeout=1)
        owner.cancel()
        await asyncio.sleep(0)
        if owner.done():
            raise ValueError("run_failure_cause_proof_settlement_abandoned")
        release_target.set()
        result, exception, cancellation_requests = await asyncio.wait_for(
            owner,
            timeout=1,
        )
        if (
            result != "settled"
            or exception is not None
            or cancellation_requests < 1
        ):
            raise ValueError("run_failure_cause_proof_settlement_invalid")
    finally:
        release_target.set()
        if not owner.done():
            owner.cancel()
            try:
                await owner
            except BaseException:
                pass

    db_path = str(root / "invariant-terminal-settlement.db")
    created = modules.repository.create_run(
        db_path=db_path,
        thread_id="proof-invariant-terminal-settlement-thread",
        query="synthetic invariant query",
    )
    committed = threading.Event()
    release = threading.Event()
    real_finalize = modules.server.finalize_run_transaction

    async def completed(*_args: Any, **_kwargs: Any) -> Any:
        return _proof_result(created, root, with_report=True)

    def commit_then_hold(**kwargs: Any) -> Any:
        result = real_finalize(**kwargs)
        committed.set()
        if not release.wait(timeout=3):
            raise RuntimeError("run_failure_cause_proof_terminal_barrier_timeout")
        return result

    worker = _scheduled_worker(modules, db_path, suffix="e")
    task: asyncio.Task[Any] | None = None
    with (
        patch.object(modules.server, "run_deep_agent", completed),
        patch.object(
            modules.server,
            "finalize_run_transaction",
            commit_then_hold,
        ),
    ):
        try:
            task = await _dispatch_and_get_task(modules, worker, created["run_id"])
            if not await asyncio.to_thread(committed.wait, 1):
                raise ValueError("run_failure_cause_proof_terminal_not_launched")
            task.cancel()
            await asyncio.sleep(0)
            if task.done():
                raise ValueError("run_failure_cause_proof_terminal_abandoned")
            release.set()
            await _await_tracked(
                modules,
                task=task,
                task_id=f"{created['run_id']}:dispatch:1",
                cancellation=True,
            )
        finally:
            release.set()
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except BaseException:
                    pass
    snapshot = _raw_snapshot(
        modules,
        db_path=db_path,
        run_id=created["run_id"],
    )
    if (
        snapshot["run"]["execution_status"] != "completed"
        or snapshot["cause"] is not None
        or snapshot["artifact_count"] != 1
    ):
        raise ValueError("run_failure_cause_proof_terminal_winner_invalid")


def _prove_public_safety(root: Path, cases: list[dict[str, Any]]) -> None:
    raw_values: list[str] = []
    for db_path in sorted(root.glob("*.db")):
        connection = sqlite3.connect(db_path)
        try:
            has_table = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'run_failure_causes_v1'
                """
            ).fetchone()
            if has_table is None:
                continue
            rows = connection.execute(
                """
                SELECT observation_status, terminal_state_version, phase, code,
                       recorded_at
                FROM run_failure_causes_v1 ORDER BY run_id
                """
            ).fetchall()
            raw_values.extend(str(value) for row in rows for value in row)
        finally:
            connection.close()
    bounded = json.dumps(cases, ensure_ascii=False, sort_keys=True)
    combined = "\n".join([*raw_values, bounded])
    for marker in (
        _RAW_EXCEPTION_MARKER,
        _RAW_CREDENTIAL_MARKER,
        _RAW_UNIX_PATH_MARKER,
        _RAW_WINDOWS_PATH_MARKER,
        _RAW_HOST_MARKER,
        _RAW_PROVIDER_MARKER,
        _RAW_QUERY_MARKER,
    ):
        if marker in combined:
            raise ValueError("run_failure_cause_proof_public_marker_leaked")


async def _prove_invariants(
    modules: _ProductionModules,
    root: Path,
    cases: list[dict[str, Any]],
) -> list[dict[str, str]]:
    dispatch_cases = cases[2:6]
    if any(
        not case["observations"]["last_error_matches_cause"]
        for case in dispatch_cases
    ):
        raise ValueError("run_failure_cause_proof_dispatch_code_mismatch")
    timeout_cancel_pairs = {
        (
            cases[index]["observations"]["phase"],
            cases[index]["observations"]["code"],
            cases[index]["observations"]["termination_origin"],
        )
        for index in (10, 11, 12, 13)
    }
    if len(timeout_cancel_pairs) != 4:
        raise ValueError("run_failure_cause_proof_termination_cases_collapsed")
    _prove_transaction_rollback(modules, root)
    _prove_terminal_guards(modules, root)
    _prove_immutable_winner_and_restart(modules, root)
    await _prove_prestart_cancellation(modules, root)
    await _prove_inner_self_cancellation(modules, root)
    await _prove_terminal_settlement(modules, root)
    _prove_public_safety(root, cases)
    return [
        {"invariant_id": invariant_id, "status": "passed"}
        for invariant_id in EXPECTED_INVARIANT_IDS
    ]


async def _build_production_cases(
    modules: _ProductionModules,
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    cases = [
        await _completed_case(modules, root),
        _historical_case(modules, root),
        await _schedule_failure_case(modules, root),
        await _start_failure_case(modules, root),
        await _start_timeout_case(modules, root),
        await _lease_expired_case(modules, root),
        await _call_budget_case(modules, root),
        await _recursion_case(modules, root),
        await _packet_case(
            modules,
            root,
            case_id="execution_invalid_research_packet",
            packet_content='{"packet_id":"synthetic-invalid-packet"}',
            resolution="invalid",
        ),
        await _packet_case(
            modules,
            root,
            case_id="execution_missing_research_packet",
            packet_content=None,
            resolution="missing",
        ),
        await _execution_timeout_case(modules, root),
        await _finalization_termination_case(
            modules,
            root,
            case_id="finalization_timeout",
            termination_kind="timeout",
        ),
        await _execution_cancelled_case(modules, root),
        await _finalization_termination_case(
            modules,
            root,
            case_id="finalization_cancelled",
            termination_kind="cancelled",
        ),
        await _raised_task_case(
            modules,
            root,
            case_id="execution_error",
            finalization_failure=False,
        ),
        await _raised_task_case(
            modules,
            root,
            case_id="finalization_failed",
            finalization_failure=True,
        ),
    ]
    invariants = await _prove_invariants(modules, root, cases)
    return cases, invariants


def _invalid_report() -> None:
    raise ValueError("run_failure_cause_proof_report_invalid")


def _strict_equal(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(
            _strict_equal(actual[key], expected[key]) for key in expected
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _strict_equal(actual_item, expected_item)
            for actual_item, expected_item in zip(actual, expected, strict=True)
        )
    return bool(actual == expected)


def _case(case_id: str, observations: dict[str, Any]) -> dict[str, Any]:
    expected = EXPECTED_OBSERVATIONS.get(case_id)
    if expected is None or not _strict_equal(observations, expected):
        _invalid_report()
    return {
        "case_id": case_id,
        "status": "passed",
        "observations": observations,
    }


def validate_report(report: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(report, dict) or set(report) != {
        "schema_version",
        "status",
        "source",
        "fixed_time",
        "cases",
        "invariants",
        "boundaries",
        "limits",
    }:
        _invalid_report()
    if (
        report["schema_version"] != REPORT_SCHEMA_VERSION
        or report["status"] != "valid"
        or report["source"] != "production_path_deterministic_local"
        or report["fixed_time"] != FIXED_TIME
        or not _strict_equal(report["boundaries"], BOUNDARIES)
        or not _strict_equal(report["limits"], LIMITS)
    ):
        _invalid_report()
    cases = report["cases"]
    if not isinstance(cases, list) or len(cases) != len(EXPECTED_CASE_IDS):
        _invalid_report()
    for case_id, item in zip(EXPECTED_CASE_IDS, cases, strict=True):
        if not isinstance(item, dict) or set(item) != {
            "case_id",
            "status",
            "observations",
        }:
            _invalid_report()
        if (
            item["case_id"] != case_id
            or item["status"] != "passed"
            or not _strict_equal(
                item["observations"],
                EXPECTED_OBSERVATIONS[case_id],
            )
        ):
            _invalid_report()
    invariants = report["invariants"]
    if not isinstance(invariants, list) or len(invariants) != len(
        EXPECTED_INVARIANT_IDS
    ):
        _invalid_report()
    for invariant_id, item in zip(EXPECTED_INVARIANT_IDS, invariants, strict=True):
        if item != {"invariant_id": invariant_id, "status": "passed"}:
            _invalid_report()
    return report


def build_report() -> dict[str, Any]:
    modules = _load_production_modules()
    with TemporaryDirectory(prefix="dra-failure-cause-proof-") as directory:
        root = Path(directory)
        with (
            _fixed_production_clocks(modules),
            patch.object(modules.tracker.logger, "error"),
            patch.object(modules.tracker.logger, "warning"),
            patch.object(modules.server.logging, "error"),
            patch.object(modules.server.monitor, "_emit"),
        ):
            production_cases, invariants = asyncio.run(
                _build_production_cases(modules, root)
            )
    cases = list(production_cases)
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": "valid",
        "source": "production_path_deterministic_local",
        "fixed_time": FIXED_TIME,
        "cases": cases,
        "invariants": invariants,
        "boundaries": dict(BOUNDARIES),
        "limits": list(LIMITS),
    }
    return validate_report(report)


def serialize_report(report: dict[str, Any]) -> bytes:
    validate_report(report)
    return (
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def render_markdown(report: dict[str, Any]) -> str:
    validate_report(report)
    lines = [
        "# Durable Run Failure Cause v1 Proof",
        "",
        "Status: valid deterministic local production-path contract proof.",
        "",
        "## Cases",
        "",
        "| Case | Phase | Code | Status |",
        "|---|---|---|---|",
    ]
    for item in report["cases"]:
        observations = item["observations"]
        lines.append(
            f"| `{item['case_id']}` | `{observations['phase'] or 'none'}` | "
            f"`{observations['code'] or 'none'}` | {item['status']} |"
        )
    lines.extend(["", "## Invariants", ""])
    lines.extend(
        f"- `{item['invariant_id']}`: {item['status']}"
        for item in report["invariants"]
    )
    lines.extend(["", "## Boundaries", ""])
    lines.extend(
        f"- `{key}: {report['boundaries'][key]}`" for key in BOUNDARIES
    )
    lines.extend(["", "## Limits", ""])
    lines.extend(f"- {value}" for value in report["limits"])
    return "\n".join(lines) + "\n"


class _ProofError(ValueError):
    """A deliberately detail-free CLI validation failure."""


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        raise _ProofError(_INVALID_CODE)


def _bounded_read(path: Path) -> bytes:
    """Read one regular baseline without following links or unbounded input."""

    descriptor: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_BASELINE_BYTES:
            raise _ProofError(_INVALID_CODE)
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            value = handle.read(MAX_BASELINE_BYTES + 1)
        if len(value) > MAX_BASELINE_BYTES:
            raise _ProofError(_INVALID_CODE)
        return value
    except _ProofError:
        raise
    except (OSError, ValueError) as error:
        raise _ProofError(_INVALID_CODE) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _validated_baselines(
    json_path: Path,
    markdown_path: Path,
) -> tuple[bytes, bytes]:
    json_bytes = _bounded_read(json_path)
    markdown_bytes = _bounded_read(markdown_path)
    try:
        parsed = json.loads(json_bytes.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise _ProofError(_INVALID_CODE)
        report = validate_report(parsed)
        canonical_json = serialize_report(report)
        canonical_markdown = render_markdown(report).encode("utf-8")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise _ProofError(_INVALID_CODE) from error
    if json_bytes != canonical_json or markdown_bytes != canonical_markdown:
        raise _ProofError(_INVALID_CODE)
    return json_bytes, markdown_bytes


def _validate_output_path(path: Path) -> Path:
    try:
        parent = path.parent.resolve(strict=True)
        metadata = parent.stat()
        if not stat.S_ISDIR(metadata.st_mode):
            raise _ProofError(_INVALID_CODE)
        if metadata.st_mode & 0o222 == 0 or not os.access(parent, os.W_OK):
            raise _ProofError(_INVALID_CODE)
        candidate = parent / path.name
        try:
            target_metadata = candidate.lstat()
        except FileNotFoundError:
            pass
        else:
            if stat.S_ISLNK(target_metadata.st_mode) or not stat.S_ISREG(
                target_metadata.st_mode
            ):
                raise _ProofError(_INVALID_CODE)
        return candidate
    except _ProofError:
        raise
    except (OSError, RuntimeError) as error:
        raise _ProofError(_INVALID_CODE) from error


def _validated_output_paths(
    json_path: Path,
    markdown_path: Path,
) -> tuple[Path, Path]:
    json_target = _validate_output_path(json_path)
    markdown_target = _validate_output_path(markdown_path)
    try:
        resolved_alias = json_target.resolve(strict=False) == markdown_target.resolve(
            strict=False
        )
        inode_alias = (
            json_target.exists()
            and markdown_target.exists()
            and os.path.samefile(json_target, markdown_target)
        )
        if resolved_alias or inode_alias:
            raise _ProofError(_INVALID_CODE)
    except (OSError, RuntimeError) as error:
        raise _ProofError(_INVALID_CODE) from error
    return json_target, markdown_target


def _stage_output(target: Path, content: bytes) -> Path:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w+b",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        return temporary_path
    except Exception as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise _ProofError(_INVALID_CODE) from error


def _write_outputs(
    json_path: Path,
    markdown_path: Path,
    json_content: bytes,
    markdown_content: bytes,
) -> None:
    json_target, markdown_target = _validated_output_paths(
        json_path,
        markdown_path,
    )
    staged: list[Path] = []
    try:
        json_temporary = _stage_output(json_target, json_content)
        staged.append(json_temporary)
        markdown_temporary = _stage_output(markdown_target, markdown_content)
        staged.append(markdown_temporary)
        os.replace(json_temporary, json_target)
        staged.remove(json_temporary)
        os.replace(markdown_temporary, markdown_target)
        staged.remove(markdown_temporary)
    except _ProofError:
        raise
    except OSError as error:
        raise _ProofError(_INVALID_CODE) from error
    finally:
        for temporary_path in staged:
            temporary_path.unlink(missing_ok=True)


def _parser() -> _ArgumentParser:
    parser = _ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--json-output", required=True)
    build.add_argument("--markdown-output", required=True)
    check = subparsers.add_parser("check")
    check.add_argument("--json-baseline", default=str(BASELINE_JSON_PATH))
    check.add_argument(
        "--markdown-baseline",
        default=str(BASELINE_MARKDOWN_PATH),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.command == "build":
            json_path, markdown_path = _validated_output_paths(
                Path(args.json_output),
                Path(args.markdown_output),
            )
            report = build_report()
            _write_outputs(
                json_path,
                markdown_path,
                serialize_report(report),
                render_markdown(report).encode("utf-8"),
            )
            print('{"status":"built"}')
        else:
            json_path = Path(args.json_baseline)
            markdown_path = Path(args.markdown_baseline)
            baseline_json, baseline_markdown = _validated_baselines(
                json_path,
                markdown_path,
            )
            report = build_report()
            if (
                serialize_report(report) != baseline_json
                or render_markdown(report).encode("utf-8") != baseline_markdown
            ):
                raise _ProofError(_INVALID_CODE)
            print('{"status":"valid","match":true}')
        return 0
    except Exception:
        print(
            '{"status":"invalid","code":"run_failure_cause_proof_invalid"}',
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
