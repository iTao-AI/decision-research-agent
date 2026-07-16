#!/usr/bin/env python3
"""Deterministic proof for durable pre-execution run dispatch reconciliation."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPORT_SCHEMA_VERSION = "dra.run-dispatch-reconciliation-proof.v1"
BASELINE_JSON_PATH = PROJECT_ROOT / "docs/evidence/run-dispatch-reconciliation-v1.json"
BASELINE_MARKDOWN_PATH = PROJECT_ROOT / "docs/evidence/run-dispatch-reconciliation-v1.md"
MAX_BASELINE_BYTES = 1_000_000
EXPECTED_CASE_IDS = (
    "atomic_create",
    "commit_before_schedule_recovery",
    "handler_cancellation_recovery",
    "worker_restart_recovery",
    "expired_lease_reclaim",
    "concurrent_dispatch_fence",
    "stale_task_blocked",
    "scheduler_exhaustion",
    "keyed_replay_single_agent_entry",
    "unkeyed_compatibility",
    "contract_compatibility",
    "migration_safety",
)
BOUNDARIES = {
    "commit_before_execution_start_recovery": "proven",
    "crash_before_schedule_recovery": "proven",
    "single_node_sqlite_dispatch_reconciliation": "proven",
    "exactly_once_execution": "not_claimed",
    "running_execution_recovery": "not_proven",
    "provider_tool_side_effect_exactly_once": "not_claimed",
    "multi_instance_high_availability": "not_proven",
    "live_provider_result": "not_observed",
}
LIMITS = [
    "Deterministic single-node SQLite contract proof, not a provider or production measurement.",
    "Recovery is proven only before application-owned execution start.",
    "Agent, provider, and tool side effects remain outside an exactly-once guarantee.",
]
EXPECTED_OBSERVATIONS: dict[str, dict[str, bool | int]] = {
    "atomic_create": {
        "run_pending": True,
        "segment_pending": True,
        "dispatch_pending": True,
    },
    "commit_before_schedule_recovery": {
        "lifespan_worker_recovered": True,
        "agent_entries": 1,
    },
    "handler_cancellation_recovery": {
        "committed_identity_recovered": True,
        "handler_cancelled_after_commit": True,
        "agent_entries": 1,
    },
    "worker_restart_recovery": {
        "second_worker_reclaimed": True,
        "fresh_worker_recovered": True,
        "agent_entries": 1,
    },
    "expired_lease_reclaim": {
        "attempt_count": 2,
        "stale_start_blocked": True,
        "fresh_start_won": True,
    },
    "concurrent_dispatch_fence": {
        "winning_starts": 1,
        "agent_entries": 1,
    },
    "stale_task_blocked": {
        "stale_agent_entries": 0,
        "fresh_agent_entries": 1,
    },
    "scheduler_exhaustion": {
        "attempt_count": 3,
        "attempt_count_capped": True,
        "dispatch_failed": True,
        "expired_third_lease_failed": True,
        "run_failed": True,
        "segment_failed": True,
    },
    "keyed_replay_single_agent_entry": {
        "same_identity": True,
        "replay_marked": True,
        "agent_entries": 1,
    },
    "unkeyed_compatibility": {
        "distinct_runs": True,
        "dispatch_rows": 2,
    },
    "contract_compatibility": {
        "status_shape_preserved": True,
        "result_shape_preserved": True,
        "downstream_fixture_valid": True,
        "agent_entries": 1,
    },
    "migration_safety": {
        "exact_verification": True,
        "repeat_apply_safe": True,
        "no_backfill": True,
        "restore_on_failure": True,
        "existing_backup_protected": True,
    },
}


def _invalid_report() -> None:
    raise ValueError("run_dispatch_proof_report_invalid")


def _case(case_id: str, **observations: bool | int) -> dict[str, Any]:
    expected = EXPECTED_OBSERVATIONS.get(case_id)
    if expected is None or set(observations) != set(expected):
        _invalid_report()
    if any(
        type(observations[key]) is not type(value) or observations[key] != value
        for key, value in expected.items()
    ):
        _invalid_report()
    return {"case_id": case_id, "status": "passed", "observations": observations}


def validate_report(report: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(report, dict) or set(report) != {
        "schema_version",
        "status",
        "source",
        "cases",
        "boundaries",
        "limits",
    }:
        _invalid_report()
    if (
        report["schema_version"] != REPORT_SCHEMA_VERSION
        or report["status"] != "valid"
        or report["source"] != "deterministic_local"
        or report["boundaries"] != BOUNDARIES
        or report["limits"] != LIMITS
    ):
        _invalid_report()
    cases = report["cases"]
    if not isinstance(cases, list) or len(cases) != len(EXPECTED_CASE_IDS):
        _invalid_report()
    for expected_id, case in zip(EXPECTED_CASE_IDS, cases, strict=True):
        if not isinstance(case, dict) or set(case) != {
            "case_id",
            "status",
            "observations",
        }:
            _invalid_report()
        if case["case_id"] != expected_id or case["status"] != "passed":
            _invalid_report()
        expected = EXPECTED_OBSERVATIONS[expected_id]
        observations = case["observations"]
        if not isinstance(observations, dict) or set(observations) != set(expected):
            _invalid_report()
        if any(
            type(observations[key]) is not type(value)
            or observations[key] != value
            for key, value in expected.items()
        ):
            _invalid_report()
    return report


def _row(db_path: str, sql: str, params: tuple = ()) -> sqlite3.Row | None:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(sql, params).fetchone()
    finally:
        connection.close()


def _count(db_path: str, table: str) -> int:
    row = _row(db_path, f"SELECT COUNT(*) AS value FROM {table}")
    return int(row["value"])


def _expire(db_path: str, run_id: str) -> None:
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                "UPDATE run_dispatches_v1 SET lease_expires_at = ? WHERE run_id = ?",
                ("2000-01-01T00:00:00+00:00", run_id),
            )
    finally:
        connection.close()


def _claim(db_path: str, run_id: str, worker_suffix: str):
    from api.run_dispatch_repository import claim_run_dispatch

    return claim_run_dispatch(
        db_path=db_path,
        worker_id=f"dispatch_worker_{worker_suffix * 32}",
        lease_seconds=30,
        run_id=run_id,
    )


def _start_and_enter(db_path: str, claim, counter: list[int]) -> bool:
    from api.run_dispatch_repository import start_run_dispatch

    started = start_run_dispatch(db_path=db_path, claim=claim)
    if started:
        counter.append(1)
    return started


def _atomic_create_case(root: Path) -> dict[str, Any]:
    from api.run_repository import create_run

    db_path = str(root / "atomic.db")
    created = create_run(db_path=db_path, thread_id="proof-thread", query="proof")
    run = _row(
        db_path,
        "SELECT execution_status FROM research_runs_v2 WHERE run_id = ?",
        (created["run_id"],),
    )
    segment = _row(
        db_path,
        "SELECT status FROM run_segments WHERE run_id = ?",
        (created["run_id"],),
    )
    dispatch = _row(
        db_path,
        "SELECT status FROM run_dispatches_v1 WHERE run_id = ?",
        (created["run_id"],),
    )
    return _case(
        "atomic_create",
        run_pending=run["execution_status"] == "pending",
        segment_pending=segment["status"] == "pending",
        dispatch_pending=dispatch["status"] == "pending",
    )


def _proof_environment(db_path: str) -> dict[str, str]:
    return {
        "DECISION_RESEARCH_AGENT_DB_PATH": db_path,
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL": "false",
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION": "false",
        "API_SECRET": "proof-only-api-secret",
        "OPENAI_API_KEY": "proof-local-placeholder",
    }


def _fake_agent(created: dict[str, str], entries: list[int]):
    from agent.harness_contracts import ReportCandidate
    from agent.run_result import AgentRunResult

    async def run(*_args, **_kwargs):
        entries.append(1)
        return AgentRunResult(
            thread_id=created["thread_id"],
            query="proof",
            session_dir=Path("/workspace/proof"),
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            report_candidate=ReportCandidate(
                path=Path("/workspace/research-report.md"),
                content="# Deterministic result",
            ),
        )

    return run


async def _wait_for_completed(db_path: str, run_id: str) -> bool:
    from api.run_repository import get_run

    for _ in range(200):
        run = await asyncio.to_thread(get_run, db_path=db_path, run_id=run_id)
        if run is not None and run["execution_status"] == "completed":
            return True
        if run is not None and run["execution_status"] == "failed":
            raise ValueError("run_dispatch_proof_recovery_failed")
        await asyncio.sleep(0.01)
    raise TimeoutError("run_dispatch_proof_recovery_timeout")


async def _run_fresh_worker_until_completed(server, db_path: str, run_id: str) -> bool:
    worker = server.create_run_dispatch_worker(db_path)
    worker_task = asyncio.create_task(worker.run_forever())
    worker.wake()
    try:
        return await _wait_for_completed(db_path, run_id)
    finally:
        worker.stop()
        await worker_task


def _recovery_cases(root: Path) -> list[dict[str, Any]]:
    from api.run_dispatch_repository import get_run_dispatch
    from api.run_repository import create_run

    commit_db = str(root / "commit.db")
    with patch.dict(os.environ, _proof_environment(commit_db), clear=False):
        import api.server as server

        committed = create_run(
            db_path=commit_db,
            thread_id="proof-thread",
            query="proof",
        )
        commit_entries: list[int] = []

        async def recover_from_lifespan():
            with patch.object(
                server,
                "run_deep_agent",
                _fake_agent(committed, commit_entries),
            ):
                async with server.lifespan(server.app):
                    return await _wait_for_completed(commit_db, committed["run_id"])

        lifespan_recovered = asyncio.run(recover_from_lifespan())

    cancel_db = str(root / "cancel.db")
    with patch.dict(os.environ, _proof_environment(cancel_db), clear=False):
        cancel_entries: list[int] = []

        async def recover_after_handler_cancellation():
            class BlockingDispatch:
                def __init__(self):
                    self.entered = asyncio.Event()

                async def dispatch_run(self, _run_id):
                    self.entered.set()
                    await asyncio.Event().wait()

                def wake(self):
                    pass

            blocking = BlockingDispatch()
            server.app.state.run_dispatch_worker = blocking
            handler = asyncio.create_task(
                server.create_research_run(
                    server.RunRequest(
                        query="proof",
                        thread_id="proof-thread",
                    )
                )
            )
            await blocking.entered.wait()
            row = _row(
                cancel_db,
                """
                SELECT run.run_id, run.thread_id, segment.segment_id
                FROM research_runs_v2 AS run
                JOIN run_segments AS segment ON segment.run_id = run.run_id
                """,
            )
            created = dict(row)
            handler.cancel()
            cancelled = False
            try:
                await handler
            except asyncio.CancelledError:
                cancelled = True
            with patch.object(
                server,
                "run_deep_agent",
                _fake_agent(created, cancel_entries),
            ):
                recovered = await _run_fresh_worker_until_completed(
                    server,
                    cancel_db,
                    created["run_id"],
                )
            return created, cancelled, recovered

        cancelled_created, handler_cancelled, cancellation_recovered = asyncio.run(
            recover_after_handler_cancellation()
        )

    restart_db = str(root / "restart.db")
    with patch.dict(os.environ, _proof_environment(restart_db), clear=False):
        restarted = create_run(
            db_path=restart_db,
            thread_id="proof-thread",
            query="proof",
        )
        abandoned: list[Any] = []

        async def abandon_then_restart():
            def capture_abandoned(claim, *, db_path):
                del db_path
                abandoned.append(claim)

            with patch.object(server, "_schedule_run_dispatch", capture_abandoned):
                first_worker = server.create_run_dispatch_worker(restart_db)
                if not await first_worker.run_once(run_id=restarted["run_id"]):
                    raise ValueError("run_dispatch_proof_recovery_failed")
            _expire(restart_db, restarted["run_id"])
            restart_entries: list[int] = []
            with patch.object(
                server,
                "run_deep_agent",
                _fake_agent(restarted, restart_entries),
            ):
                recovered = await _run_fresh_worker_until_completed(
                    server,
                    restart_db,
                    restarted["run_id"],
                )
            return recovered, restart_entries

        restart_recovered, restart_entries = asyncio.run(abandon_then_restart())
        restarted_dispatch = get_run_dispatch(
            db_path=restart_db,
            run_id=restarted["run_id"],
        )

    return [
        _case(
            "commit_before_schedule_recovery",
            lifespan_worker_recovered=lifespan_recovered,
            agent_entries=len(commit_entries),
        ),
        _case(
            "handler_cancellation_recovery",
            committed_identity_recovered=(
                cancelled_created["run_id"] is not None and cancellation_recovered
            ),
            handler_cancelled_after_commit=handler_cancelled,
            agent_entries=len(cancel_entries),
        ),
        _case(
            "worker_restart_recovery",
            second_worker_reclaimed=(
                len(abandoned) == 1 and restarted_dispatch["attempt_count"] == 2
            ),
            fresh_worker_recovered=restart_recovered,
            agent_entries=len(restart_entries),
        ),
    ]


def _fence_cases(root: Path) -> list[dict[str, Any]]:
    from api.run_repository import create_run

    def stale_and_fresh(filename: str):
        db_path = str(root / filename)
        created = create_run(db_path=db_path, thread_id="proof-thread", query="proof")
        stale = _claim(db_path, created["run_id"], "1")
        _expire(db_path, created["run_id"])
        fresh = _claim(db_path, created["run_id"], "2")
        return db_path, stale, fresh

    db_path, stale, fresh = stale_and_fresh("reclaim.db")
    stale_result = _start_and_enter(db_path, stale, [])
    fresh_entries: list[int] = []
    fresh_result = _start_and_enter(db_path, fresh, fresh_entries)
    reclaim = _case(
        "expired_lease_reclaim",
        attempt_count=fresh.attempt_count,
        stale_start_blocked=not stale_result,
        fresh_start_won=fresh_result,
    )

    db_path, stale, fresh = stale_and_fresh("concurrent.db")
    entries = []
    results = [_start_and_enter(db_path, claim, entries) for claim in (stale, fresh)]
    concurrent = _case(
        "concurrent_dispatch_fence",
        winning_starts=sum(results),
        agent_entries=len(entries),
    )

    db_path, stale, fresh = stale_and_fresh("stale.db")
    stale_entries: list[int] = []
    fresh_entries = []
    _start_and_enter(db_path, stale, stale_entries)
    _start_and_enter(db_path, fresh, fresh_entries)
    stale_case = _case(
        "stale_task_blocked",
        stale_agent_entries=len(stale_entries),
        fresh_agent_entries=len(fresh_entries),
    )
    return [reclaim, concurrent, stale_case]


def _scheduler_exhaustion_case(root: Path) -> dict[str, Any]:
    from api.run_dispatch_worker import RunDispatchWorker
    from api.run_dispatch_repository import get_run_dispatch
    from api.run_repository import create_run, get_run

    db_path = str(root / "exhaust.db")
    created = create_run(db_path=db_path, thread_id="proof-thread", query="proof")

    def fail(_claim):
        raise RuntimeError("bounded")

    worker = RunDispatchWorker(
        db_path=db_path,
        scheduler=fail,
        worker_id="dispatch_worker_33333333333333333333333333333333",
    )
    with patch("api.run_dispatch_worker.logging.error"):
        for _ in range(3):
            asyncio.run(worker.dispatch_run(created["run_id"]))
    dispatch = get_run_dispatch(db_path=db_path, run_id=created["run_id"])
    run = get_run(db_path=db_path, run_id=created["run_id"])
    segment = _row(
        db_path,
        "SELECT status FROM run_segments WHERE run_id = ?",
        (created["run_id"],),
    )

    expired_db = str(root / "expired-exhaust.db")
    expired = create_run(
        db_path=expired_db,
        thread_id="proof-thread",
        query="proof",
    )
    abandoned: list[Any] = []
    expiring_worker = RunDispatchWorker(
        db_path=expired_db,
        scheduler=abandoned.append,
        worker_id="dispatch_worker_66666666666666666666666666666666",
    )
    for _ in range(3):
        asyncio.run(expiring_worker.dispatch_run(expired["run_id"]))
        _expire(expired_db, expired["run_id"])
    fourth_scheduled = asyncio.run(
        expiring_worker.dispatch_run(expired["run_id"])
    )
    expired_dispatch = get_run_dispatch(
        db_path=expired_db,
        run_id=expired["run_id"],
    )
    return _case(
        "scheduler_exhaustion",
        attempt_count=dispatch["attempt_count"],
        attempt_count_capped=(
            expired_dispatch["attempt_count"] == 3 and len(abandoned) == 3
        ),
        dispatch_failed=dispatch["status"] == "failed",
        expired_third_lease_failed=(
            fourth_scheduled is False
            and expired_dispatch["status"] == "failed"
            and expired_dispatch["last_error_code"]
            == "run_dispatch_lease_expired"
        ),
        run_failed=run["execution_status"] == "failed",
        segment_failed=segment["status"] == "failed",
    )


def _compatibility_cases(root: Path) -> list[dict[str, Any]]:
    from api.run_repository import create_or_replay_run, create_run

    keyed_db = str(root / "keyed.db")
    kwargs = {
        "db_path": keyed_db,
        "idempotency_key": "proof-dispatch-key-0001",
        "thread_id": None,
        "query": "proof",
        "scope": {},
    }
    first = create_or_replay_run(**kwargs)
    replay = create_or_replay_run(**kwargs)
    claim = _claim(keyed_db, first.run_id, "4")
    entries: list[int] = []
    _start_and_enter(keyed_db, claim, entries)
    keyed = _case(
        "keyed_replay_single_agent_entry",
        same_identity=first.run_id == replay.run_id,
        replay_marked=replay.idempotent_replay,
        agent_entries=len(entries),
    )

    unkeyed_db = str(root / "unkeyed.db")
    first_unkeyed = create_run(
        db_path=unkeyed_db, thread_id="proof-thread", query="proof"
    )
    second_unkeyed = create_run(
        db_path=unkeyed_db, thread_id="proof-thread", query="proof"
    )
    unkeyed = _case(
        "unkeyed_compatibility",
        distinct_runs=first_unkeyed["run_id"] != second_unkeyed["run_id"],
        dispatch_rows=_count(unkeyed_db, "run_dispatches_v1"),
    )
    return [keyed, unkeyed]


def _contract_case(root: Path) -> dict[str, Any]:
    from agent.harness_contracts import ReportCandidate
    from agent.run_result import AgentRunResult
    from api.run_dispatch_repository import claim_run_dispatch
    from api.run_repository import create_run
    from scripts.downstream_consumer_contract import validate_fixture_bundle
    from fastapi.testclient import TestClient

    environment = {
        "DECISION_RESEARCH_AGENT_DB_PATH": str(root / "contract.db"),
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL": "false",
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION": "false",
        "API_SECRET": "proof-only-api-secret",
        "OPENAI_API_KEY": "proof-local-placeholder",
    }
    with patch.dict(os.environ, environment, clear=False):
        import api.server as server

        created = create_run(thread_id="proof-thread", query="proof")
        claim = claim_run_dispatch(
            db_path=environment["DECISION_RESEARCH_AGENT_DB_PATH"],
            worker_id="dispatch_worker_55555555555555555555555555555555",
            lease_seconds=30,
            run_id=created["run_id"],
        )
        entries: list[int] = []

        async def fake_agent(*_args, **_kwargs):
            entries.append(1)
            return AgentRunResult(
                thread_id="proof-thread",
                query="proof",
                session_dir=Path("/workspace/proof"),
                run_id=created["run_id"],
                segment_id=created["segment_id"],
                report_candidate=ReportCandidate(
                    path=Path("/workspace/research-report.md"),
                    content="# Deterministic result",
                ),
            )

        async def run_tracked_claim() -> None:
            stage = server._RunStage()
            termination_origin = server.TerminationOrigin()
            finalization_checkpoint = server.FinalizationCheckpoint()
            coroutine = server._run_dispatched_with_persistence(
                claim,
                db_path=environment["DECISION_RESEARCH_AGENT_DB_PATH"],
                outcome_box=server.OutcomeBox(),
                stage=stage,
                termination_origin=termination_origin,
                finalization_checkpoint=finalization_checkpoint,
            )
            task = server.create_tracked_task(
                coroutine,
                f"{claim.run_id}:dispatch:{claim.attempt_count}",
                termination_origin=termination_origin,
                finalization_checkpoint=finalization_checkpoint,
            )
            await task

        with patch.object(server, "run_deep_agent", fake_agent):
            asyncio.run(run_tracked_claim())
        client = TestClient(server.app)
        headers = {"X-API-Key": "proof-only-api-secret"}
        status = client.get(f"/api/runs/{created['run_id']}", headers=headers)
        result = client.get(f"/api/runs/{created['run_id']}/result", headers=headers)
        fixture = json.loads(
            (PROJECT_ROOT / "docs/evidence/downstream-consumer-contract-v1.json").read_text(
                encoding="utf-8"
            )
        )
        fixture_valid = validate_fixture_bundle(fixture) is fixture
    return _case(
        "contract_compatibility",
        status_shape_preserved=(
            status.status_code == 200
            and status.json()["execution_status"] == "completed"
            and status.json()["delivery_status"] == "ready"
            and status.json()["review_status"] == "not_required"
        ),
        result_shape_preserved=(
            result.status_code == 200
            and set(result.json())
            == {"run_id", "execution_status", "delivery_status", "artifact"}
        ),
        downstream_fixture_valid=fixture_valid,
        agent_entries=len(entries),
    )


def _remove_dispatch_schema(db_path: str) -> None:
    from api.run_dispatch_models import RUN_DISPATCH_MIGRATION_VERSION

    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute("DROP TABLE run_dispatches_v1")
            connection.execute(
                "DELETE FROM schema_migrations WHERE version = ?",
                (RUN_DISPATCH_MIGRATION_VERSION,),
            )
    finally:
        connection.close()


def _migration_case(root: Path) -> dict[str, Any]:
    from api.run_migrations import migrate_with_backup, verify_run_schema
    from api.run_repository import create_run

    db_path = str(root / "migration.db")
    migrate_with_backup(db_path=db_path, backup_path=str(root / "initial.bak"))
    created = create_run(db_path=db_path, thread_id="legacy-thread", query="proof")
    _remove_dispatch_schema(db_path)
    dispatch_backup = str(root / "dispatch.bak")
    migrated = migrate_with_backup(db_path=db_path, backup_path=dispatch_backup)
    exact = verify_run_schema(
        db_path=db_path,
        include_evidence_verification=True,
        include_publication=True,
    )
    repeated = migrate_with_backup(db_path=db_path, backup_path=dispatch_backup)
    no_backfill = _count(db_path, "run_dispatches_v1") == 0

    restore_db = str(root / "restore.db")
    migrate_with_backup(
        db_path=restore_db,
        backup_path=str(root / "restore-initial.bak"),
    )
    restored_identity = create_run(
        db_path=restore_db, thread_id="legacy-thread", query="proof"
    )
    _remove_dispatch_schema(restore_db)
    with patch(
        "api.run_migrations.verify_run_schema",
        side_effect=RuntimeError("injected"),
    ):
        try:
            migrate_with_backup(
                db_path=restore_db,
                backup_path=str(root / "restore-dispatch.bak"),
            )
        except RuntimeError:
            pass
    restored_table = _row(
        restore_db,
        "SELECT name FROM sqlite_master WHERE type='table' AND name='run_dispatches_v1'",
    )
    restored_run = _row(
        restore_db,
        "SELECT run_id FROM research_runs_v2 WHERE run_id = ?",
        (restored_identity["run_id"],),
    )

    protected_db = str(root / "protected.db")
    migrate_with_backup(
        db_path=protected_db,
        backup_path=str(root / "protected-initial.bak"),
    )
    _remove_dispatch_schema(protected_db)
    existing_backup = root / "protected-dispatch.bak"
    existing_backup.write_bytes(b"preserve")
    protected = False
    try:
        migrate_with_backup(db_path=protected_db, backup_path=str(existing_backup))
    except RuntimeError as exc:
        protected = (
            str(exc) == "run_dispatch_migration_backup_already_exists"
            and existing_backup.read_bytes() == b"preserve"
        )
    return _case(
        "migration_safety",
        exact_verification=bool(migrated) and bool(exact),
        repeat_apply_safe=bool(repeated),
        no_backfill=no_backfill and created["run_id"] is not None,
        restore_on_failure=restored_table is None and restored_run is not None,
        existing_backup_protected=protected,
    )


def build_report() -> dict[str, Any]:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        cases = [
            _atomic_create_case(root),
            *_recovery_cases(root),
            *_fence_cases(root),
            _scheduler_exhaustion_case(root),
            *_compatibility_cases(root),
            _contract_case(root),
            _migration_case(root),
        ]
    if [case["case_id"] for case in cases] != list(EXPECTED_CASE_IDS):
        raise ValueError("run_dispatch_proof_case_order_invalid")
    return validate_report(
        {
            "schema_version": REPORT_SCHEMA_VERSION,
            "status": "valid",
            "source": "deterministic_local",
            "cases": cases,
            "boundaries": dict(BOUNDARIES),
            "limits": list(LIMITS),
        }
    )


def serialize_report(report: dict[str, Any]) -> bytes:
    validate_report(report)
    return (
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def render_markdown(report: dict[str, Any]) -> str:
    validate_report(report)
    lines = [
        "# Run Dispatch Reconciliation v1 Proof",
        "",
        "Status: valid deterministic local contract proof.",
        "Recovery cases exercise the production lifespan, worker, scheduler, and handler-cancellation boundaries.",
        "",
        "| Case | Status |",
        "|---|---|",
    ]
    lines.extend(f"| `{case['case_id']}` | {case['status']} |" for case in report["cases"])
    lines.extend(["", "## Boundaries", ""])
    lines.extend(f"- `{key}: {value}`" for key, value in report["boundaries"].items())
    lines.extend(["", "## Limits", ""])
    lines.extend(f"- {value}" for value in report["limits"])
    return "\n".join(lines) + "\n"


def _bounded_read(path: Path) -> bytes:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("run_dispatch_proof_baseline_invalid")
    if metadata.st_size > MAX_BASELINE_BYTES:
        raise ValueError("run_dispatch_proof_baseline_invalid")
    with path.open("rb") as handle:
        value = handle.read(MAX_BASELINE_BYTES + 1)
    if len(value) > MAX_BASELINE_BYTES:
        raise ValueError("run_dispatch_proof_baseline_invalid")
    return value


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        raise ValueError("run_dispatch_proof_baseline_invalid")


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _ArgumentParser(description=__doc__)
        parser.add_argument("command", choices=("json", "markdown", "check"))
        args = parser.parse_args(argv)
        report = build_report()
        if args.command == "json":
            sys.stdout.buffer.write(serialize_report(report))
        elif args.command == "markdown":
            sys.stdout.write(render_markdown(report))
        else:
            if not (
                _bounded_read(BASELINE_JSON_PATH) == serialize_report(report)
                and _bounded_read(BASELINE_MARKDOWN_PATH)
                == render_markdown(report).encode("utf-8")
            ):
                raise ValueError("run_dispatch_proof_baseline_invalid")
            print(json.dumps({"status": "valid", "match": True}, separators=(",", ":")))
        return 0
    except (OSError, RuntimeError, TimeoutError, ValueError, json.JSONDecodeError):
        print(
            json.dumps(
                {"status": "invalid", "code": "run_dispatch_proof_baseline_invalid"},
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
