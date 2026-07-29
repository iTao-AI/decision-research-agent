#!/usr/bin/env python3
"""Deterministic provider-free proof for crash-safe startup convergence."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from api.run_dispatch_repository import claim_run_dispatch, start_run_dispatch
from api.run_execution_migrations import (
    migrate_run_execution_recovery_with_backup,
)
from api.run_execution_models import new_boot_id
from api.run_execution_repository import (
    activate_run_execution_boot,
    advance_run_execution_phase,
    run_execution_owner_fence_is_current,
)
from api.run_failure_cause_models import RunFailureCauseWrite
from api.run_recovery_repository import create_or_replay_run_recovery
from api.run_repository import (
    _connect,
    _init_run_schema_unlocked,
    create_run,
    finalize_run_transaction,
    init_run_schema,
)


WORKER = ROOT / "scripts" / "run_execution_recovery_crash_worker.py"
ROLLBACK_REVISION = "bfd744a5611c7673d9385a45bed0131d6cb47655"
ERROR_CODES = {
    "writer": "run_execution_recovery_proof_writer_lock_failed",
    "migration": "run_execution_recovery_proof_migration_failed",
    "execution": "run_execution_recovery_proof_execution_sigkill_failed",
    "finalization": "run_execution_recovery_proof_finalization_sigkill_failed",
    "stale": "run_execution_recovery_proof_stale_generation_failed",
    "replacement": "run_execution_recovery_proof_replacement_failed",
    "rollback_revision": (
        "run_execution_recovery_proof_rollback_revision_unavailable"
    ),
    "rollback_import": "run_execution_recovery_proof_rollback_import_mismatch",
    "rollback_restore": "run_execution_recovery_proof_rollback_restore_failed",
    "rollback_verify": (
        "run_execution_recovery_proof_rollback_old_revision_verify_failed"
    ),
    "retained": "run_execution_recovery_proof_retained_contract_failed",
}
STALE_INJECTIONS = {
    "stale",
    "stale_start",
    "stale_phase",
    "stale_finalization_fence",
    "stale_normal",
    "stale_timeout",
    "stale_cancellation",
    "stale_fallback",
}
LIMITS = [
    "Provider-free contract proof, not a production reliability measurement.",
    "Startup convergence is single-node and startup-only.",
    "Replacement creation does not deduplicate provider or tool side effects.",
    "No exact resume, automatic release, or business impact is observed.",
]
BOUNDARIES = {
    "process_lifetime_single_writer_gate": "proven",
    "single_node_startup_convergence": "proven",
    "execution_phase_interruption_classification": "proven",
    "finalization_phase_interruption_classification": "proven",
    "explicit_one_hop_replacement": "proven",
    "provider_free_contract": "proven",
    "exact_resume": "not_claimed",
    "exactly_once_execution": "not_claimed",
    "external_side_effect_deduplication": "not_claimed",
    "multi_instance_high_availability": "not_claimed",
    "live_provider_result": "not_observed",
    "automatic_release_or_rollback": "not_claimed",
}


class ProofFailure(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class _ProofBoundaryGuard:
    def __init__(self) -> None:
        self.provider_calls = 0
        self.tool_calls = 0

    def reject_provider(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        self.provider_calls += 1
        raise RuntimeError("provider_boundary_reached")

    async def reject_provider_async(self, *args: Any, **kwargs: Any) -> None:
        self.reject_provider(*args, **kwargs)

    def reject_tool(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        self.tool_calls += 1
        raise RuntimeError("tool_boundary_reached")

    async def reject_tool_async(self, *args: Any, **kwargs: Any) -> None:
        self.reject_tool(*args, **kwargs)


@contextmanager
def _installed_boundary_guards(server: Any, guard: _ProofBoundaryGuard):
    import agent.research_agents as research_agents

    main_agent_module = sys.modules.get("agent.main_agent")
    if main_agent_module is None or not hasattr(main_agent_module, "model"):
        raise RuntimeError("provider_boundary_inventory_unavailable")
    pending_models = [main_agent_module.model]
    model_classes: list[type] = []
    seen_models: set[int] = set()
    while pending_models:
        model = pending_models.pop()
        if id(model) in seen_models:
            continue
        seen_models.add(id(model))
        model_type = type(model)
        if model_type not in model_classes:
            model_classes.append(model_type)
        for attribute in ("primary", "fallback", "wrapped"):
            nested = getattr(model, attribute, None)
            if nested is not None:
                pending_models.append(nested)
    old_route = server.run_deep_agent
    model_methods = tuple(
        (owner, name, replacement)
        for owner in model_classes
        for name, replacement in (
            ("_generate", guard.reject_provider),
            ("_agenerate", guard.reject_provider_async),
        )
        if hasattr(owner, name)
    )
    if not model_methods:
        raise RuntimeError("provider_boundary_inventory_unavailable")
    old_model_methods = [
        (owner, name, getattr(owner, name)) for owner, name, _ in model_methods
    ]
    tools = [
        tool
        for config in research_agents._RESEARCHER_CONFIG.values()
        for tool in config["tools"]
    ]
    old_tool_methods = [
        (tool, tool.func, tool.coroutine)
        for tool in tools
    ]
    try:
        server.run_deep_agent = guard.reject_provider_async
        for owner, name, replacement in model_methods:
            setattr(owner, name, replacement)
        for tool in tools:
            object.__setattr__(tool, "func", guard.reject_tool)
            object.__setattr__(tool, "coroutine", guard.reject_tool_async)
        yield {
            "server": server,
            "model_classes": tuple(model_classes),
            "tools": tuple(tools),
        }
    finally:
        server.run_deep_agent = old_route
        for owner, name, original in old_model_methods:
            setattr(owner, name, original)
        for tool, old_func, old_coroutine in old_tool_methods:
            object.__setattr__(tool, "func", old_func)
            object.__setattr__(tool, "coroutine", old_coroutine)

def _run_stage(
    name: str,
    operation: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    injected = os.environ.get("DRA_RECOVERY_PROOF_INJECT_FAILURE")
    matches = injected == name or (name == "stale" and injected in STALE_INJECTIONS)
    if matches:
        raise ProofFailure(ERROR_CODES[name])
    try:
        return operation()
    except ProofFailure:
        raise
    except Exception as exc:
        raise ProofFailure(ERROR_CODES[name]) from exc


def _child(
    db_path: Path,
    marker: Path,
    mode: str,
) -> subprocess.Popen[str]:
    environment = os.environ.copy()
    environment["PYTHON_DOTENV_DISABLED"] = "1"
    return subprocess.Popen(
        [
            sys.executable,
            str(WORKER),
            "--db",
            str(db_path),
            "--marker",
            str(marker),
            "--mode",
            mode,
        ],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_marker(process: subprocess.Popen[str], marker: Path, token: str) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if marker.exists() and marker.read_text(encoding="ascii") == token:
            return
        if process.poll() is not None:
            raise RuntimeError("child_exited_before_ready")
        time.sleep(0.01)
    raise RuntimeError("child_ready_timeout")


def _sigkill(process: subprocess.Popen[str]) -> None:
    os.kill(process.pid, signal.SIGKILL)
    stdout, stderr = process.communicate(timeout=10)
    if process.returncode != -signal.SIGKILL or stdout or stderr:
        raise RuntimeError("child_sigkill_failed")


def _writer_case(root: Path) -> dict[str, Any]:
    db_path = root / "writer.db"
    first_marker = root / "writer-a.ready"
    first = _child(db_path, first_marker, "writer")
    try:
        _wait_marker(first, first_marker, "writer")
        if db_path.exists():
            raise RuntimeError("writer_touched_database")
        before = time.monotonic()
        overlap = subprocess.run(
            [
                sys.executable,
                str(WORKER),
                "--db",
                str(db_path),
                "--marker",
                str(root / "writer-b.ready"),
                "--mode",
                "writer",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if (
            overlap.returncode != 3
            or overlap.stdout
            or overlap.stderr != "run_execution_writer_already_active\n"
            or time.monotonic() - before >= 5
            or db_path.exists()
        ):
            raise RuntimeError("overlap_not_rejected")
        _sigkill(first)
    finally:
        if first.poll() is None:
            _sigkill(first)
    third_marker = root / "writer-c.ready"
    third = _child(db_path, third_marker, "writer")
    try:
        _wait_marker(third, third_marker, "writer")
    finally:
        _sigkill(third)
    return {
        "overlap_rejected": True,
        "database_untouched": True,
        "os_released_after_sigkill": True,
    }


def _build_legacy_running(path: Path) -> None:
    _init_run_schema_unlocked(str(path))
    now = "2026-07-29T00:00:00+00:00"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO research_runs_v2 VALUES
            ('legacy-running','legacy-thread','legacy-query','generic','1','{}',
             'running','not_required','pending',1,?,?)
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO run_segments VALUES
            ('legacy-running_seg_000','legacy-running','initial',0,1,'running',?,?)
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO run_dispatches_v1 VALUES
            ('legacy-running','started',NULL,NULL,1,NULL,?,?,?)
            """,
            (now, now, now),
        )


def _migration_case(root: Path) -> dict[str, Any]:
    db_path = root / "migration.db"
    _build_legacy_running(db_path)
    migrate_run_execution_recovery_with_backup(db_path=str(db_path))
    backup = Path(f"{db_path}.pre-run-execution-recovery.bak")
    restored = root / "migration-restored.db"
    shutil.copy2(backup, restored)
    with sqlite3.connect(db_path) as connection:
        owner = connection.execute(
            "SELECT status,phase,recovery_reason FROM run_execution_owners_v1"
        ).fetchone()
        run = connection.execute(
            "SELECT execution_status FROM research_runs_v2"
        ).fetchone()
        invented = sum(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "evidence_entries_v2",
                "run_recovery_retries_v1",
            )
        )
    with sqlite3.connect(restored) as connection:
        marker = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version='010_run_execution_recovery'"
        ).fetchone()[0]
    if (
        owner
        != ("interrupted", "execution", "pre_v1_running_without_owner")
        or run != ("failed",)
        or invented != 0
        or marker != 0
    ):
        raise RuntimeError("migration_case_invalid")
    return {
        "backup_restored": True,
        "pre_v1_running_converged": True,
        "invented_business_rows": 0,
    }


def _fresh_converge(db_path: Path, phase: str) -> None:
    code = """
import sqlite3,sys
from api.run_execution_models import new_boot_id
from api.run_execution_repository import activate_run_execution_boot
from api.run_repository import init_run_schema
p=sys.argv[1]; expected=sys.argv[2]
init_run_schema(p)
a=activate_run_execution_boot(db_path=p,boot_id=new_boot_id())
assert (a.interrupted_execution_count,a.interrupted_finalization_count)==((1,0) if expected=='execution' else (0,1))
with sqlite3.connect(p) as c:
 r=c.execute('SELECT status,phase,recovery_reason FROM run_execution_owners_v1').fetchone()
 s=c.execute('SELECT execution_status,delivery_status,state_version,updated_at FROM research_runs_v2').fetchone()
 g=c.execute('SELECT status,updated_at FROM run_segments').fetchone()
 f=c.execute('SELECT phase,code,recorded_at FROM run_failure_causes_v1').fetchone()
 assert r==('interrupted',expected,'previous_boot_interrupted')
 assert s[:3]==('failed','failed',2) and g[0]=='failed'
 assert s[3]==g[1]==f[2]
 assert f[:2]==((expected,'execution_error') if expected=='execution' else (expected,'run_finalization_failed'))
 assert c.execute(\"SELECT COUNT(*) FROM run_execution_owners_v1 WHERE status='active'\").fetchone()[0]==0
 for table in ('evidence_entries_v2','run_recovery_retries_v1'):
  assert c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]==0
"""
    completed = subprocess.run(
        [sys.executable, "-c", code, str(db_path), phase],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
        env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"},
    )
    if completed.returncode or completed.stdout or completed.stderr:
        raise RuntimeError("fresh_convergence_failed")


def _sigkill_case(root: Path, phase: str) -> dict[str, Any]:
    db_path = root / f"{phase}.db"
    marker = root / f"{phase}.ready"
    child = _child(db_path, marker, phase)
    try:
        _wait_marker(child, marker, phase)
        _sigkill(child)
    finally:
        if child.poll() is None:
            _sigkill(child)
    _fresh_converge(db_path, phase)
    return {
        "real_sigkill": True,
        "cause_exact": True,
        "active_owners_after": 0,
    }


def _started_run(db_path: Path):
    init_run_schema(str(db_path))
    boot = new_boot_id()
    activate_run_execution_boot(db_path=str(db_path), boot_id=boot)
    created = create_run(
        db_path=str(db_path),
        thread_id="stale-thread",
        query="provider-free stale proof",
    )
    claim = claim_run_dispatch(
        db_path=str(db_path),
        worker_id="dispatch_worker_" + "c" * 32,
        boot_id=boot,
        lease_seconds=30,
        run_id=created["run_id"],
    )
    if claim is None:
        raise RuntimeError("claim_missing")
    handle = start_run_dispatch(db_path=str(db_path), claim=claim)
    if handle is None:
        raise RuntimeError("handle_missing")
    return created, claim, handle


def _business_counts(db_path: Path) -> tuple[int, ...]:
    tables = (
        "evidence_entries_v2",
        "research_packets_v2",
        "run_artifacts_v2",
        "review_bundles_v2",
        "review_workflows_v2",
        "review_decisions_v2",
        "review_resolutions_v2",
        "review_resume_attempts_v2",
        "evidence_verification_preflights_v2",
        "evidence_verification_decisions_v2",
        "evidence_verification_snapshots_v2",
        "run_publications_v2",
        "run_failure_causes_v1",
        "run_recovery_retries_v1",
    )
    with sqlite3.connect(db_path) as connection:
        existing = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        return tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if table in existing
            else 0
            for table in tables
        )


def _stale_case(root: Path) -> dict[str, Any]:
    db_path = root / "stale.db"
    created, claim, handle = _started_run(db_path)
    activate_run_execution_boot(db_path=str(db_path), boot_id=new_boot_id())
    before = _business_counts(db_path)
    phase_writes = int(
        advance_run_execution_phase(db_path=str(db_path), handle=handle)
    )
    with _connect(str(db_path)) as connection:
        fence = run_execution_owner_fence_is_current(
            connection,
            handle,
            expected_phase="execution",
        )
    outcomes = [
        finalize_run_transaction(
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            expected_state_version=1,
            allowed_previous_statuses={"running"},
            execution_status="completed",
            delivery_status="ready",
            evidence_entries=[],
            owner_handle=handle,
            db_path=str(db_path),
        ),
        finalize_run_transaction(
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
            owner_handle=handle,
            db_path=str(db_path),
        ),
        finalize_run_transaction(
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            expected_state_version=1,
            allowed_previous_statuses={"running"},
            execution_status="failed",
            delivery_status="failed",
            evidence_entries=[],
            failure_cause=RunFailureCauseWrite(
                phase="execution",
                code="cancelled",
            ),
            owner_handle=handle,
            db_path=str(db_path),
        ),
        finalize_run_transaction(
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            expected_state_version=1,
            allowed_previous_statuses={"running"},
            execution_status="completed_with_fallback",
            delivery_status="ready",
            evidence_entries=[],
            owner_handle=handle,
            db_path=str(db_path),
        ),
    ]
    stale_start = start_run_dispatch(db_path=str(db_path), claim=claim)
    after = _business_counts(db_path)
    if phase_writes or fence or any(outcomes) or stale_start is not None or before != after:
        raise RuntimeError("stale_writer_won")
    return {
        "phase_writes": 0,
        "business_writes": 0,
        "terminal_writes": 0,
    }


class _IdleWorker:
    def __init__(self) -> None:
        self._stopped = asyncio.Event()

    async def run_forever(self) -> None:
        await self._stopped.wait()

    def stop(self) -> None:
        self._stopped.set()

    async def dispatch_run(self, run_id: str) -> bool:
        del run_id
        return False

    def wake(self) -> None:
        return None


def _replacement_case(
    root: Path,
    guard: _ProofBoundaryGuard,
) -> dict[str, Any]:
    old_provider_key = os.environ.get("OPENAI_API_KEY")
    old_deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    old_fallback_model = os.environ.get("LLM_FALLBACK_MODEL")
    os.environ["OPENAI_API_KEY"] = "provider-disabled-local-proof"
    os.environ["DEEPSEEK_API_KEY"] = "provider-disabled-local-proof"
    os.environ["LLM_FALLBACK_MODEL"] = "none"
    try:
        import api.server as server
    except Exception:
        for key, value in (
            ("OPENAI_API_KEY", old_provider_key),
            ("DEEPSEEK_API_KEY", old_deepseek_key),
            ("LLM_FALLBACK_MODEL", old_fallback_model),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        raise

    db_path = root / "replacement.db"
    source, _, _ = _started_run(db_path)
    activate_run_execution_boot(db_path=str(db_path), boot_id=new_boot_id())
    old_db = os.environ.get("DECISION_RESEARCH_AGENT_DB_PATH")
    old_hitl = os.environ.get("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL")
    old_verification = os.environ.get(
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION"
    )
    old_output = server.output_dir
    old_factory = server.create_run_dispatch_worker
    try:
        os.environ["DECISION_RESEARCH_AGENT_DB_PATH"] = str(db_path)
        os.environ["DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL"] = "false"
        os.environ[
            "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION"
        ] = "false"
        server.output_dir = root / "output"
        server.create_run_dispatch_worker = lambda *args, **kwargs: _IdleWorker()
        server.app.state.runtime_access_policy = server.load_runtime_access_policy(
            {"API_SECRET": "proof-local-secret"}
        )
        with _installed_boundary_guards(server, guard):
            with TestClient(server.app) as client:
                headers = {
                    "X-API-Key": "proof-local-secret",
                    "Idempotency-Key": "proof-recovery-key-0123456789abcdef",
                }
                first = client.post(
                    f"/api/runs/{source['run_id']}/retries",
                    content=b"",
                    headers=headers,
                )
                replay = client.post(
                    f"/api/runs/{source['run_id']}/retries",
                    content=b"",
                    headers=headers,
                )
        one = first.json()
        two = replay.json()
    finally:
        server.output_dir = old_output
        server.create_run_dispatch_worker = old_factory
        for key, value in (
            ("OPENAI_API_KEY", old_provider_key),
            ("DEEPSEEK_API_KEY", old_deepseek_key),
            ("LLM_FALLBACK_MODEL", old_fallback_model),
            ("DECISION_RESEARCH_AGENT_DB_PATH", old_db),
            ("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", old_hitl),
            (
                "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION",
                old_verification,
            ),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    with sqlite3.connect(db_path) as connection:
        replacement_runs = connection.execute(
            "SELECT COUNT(*) FROM research_runs_v2"
        ).fetchone()[0] - 1
        lineage_rows = connection.execute(
            "SELECT COUNT(*) FROM run_recovery_retries_v1"
        ).fetchone()[0]
        source_state = connection.execute(
            "SELECT execution_status,state_version FROM research_runs_v2 WHERE run_id=?",
            (source["run_id"],),
        ).fetchone()
    if (
        first.status_code != 202
        or replay.status_code != 202
        or one["run_id"] != two["run_id"]
        or one["idempotent_replay"]
        or not two["idempotent_replay"]
        or replacement_runs != 1
        or lineage_rows != 1
        or source_state != ("failed", 2)
    ):
        raise RuntimeError("replacement_case_invalid")
    return {
        "replacement_runs": 1,
        "lineage_rows": 1,
        "same_replacement": True,
        "replay_marked": True,
    }


def _rollback_revision_available() -> None:
    for command in (
        ["git", "cat-file", "-e", f"{ROLLBACK_REVISION}^{{commit}}"],
        ["git", "archive", "--format=tar", ROLLBACK_REVISION, "-o", os.devnull],
    ):
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            timeout=20,
            check=False,
        )
        if completed.returncode:
            raise ProofFailure(ERROR_CODES["rollback_revision"])


def _rollback_case(root: Path) -> dict[str, Any]:
    _rollback_revision_available()
    archive = root / "old.tar"
    completed = subprocess.run(
        ["git", "archive", "--format=tar", "-o", str(archive), ROLLBACK_REVISION],
        cwd=ROOT,
        capture_output=True,
        timeout=20,
        check=False,
    )
    if completed.returncode:
        raise ProofFailure(ERROR_CODES["rollback_revision"])
    export = root / "old"
    export.mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(export, filter="data")
    (export / ".proof-revision").write_text(ROLLBACK_REVISION, encoding="ascii")
    current = root / "rollback-current.db"
    prepare_code = """
import pathlib,sqlite3,sys
root=pathlib.Path(sys.argv[1]).resolve(); db=sys.argv[2]
sys.path.insert(0,str(root))
try:
 import api.run_repository as repository
 import api.review_repository as review
 assert pathlib.Path(repository.__file__).resolve().is_relative_to(root)
 assert pathlib.Path(review.__file__).resolve().is_relative_to(root)
 review.init_review_schema(db)
except Exception:
 sys.exit(41)
now='2026-07-29T00:00:00+00:00'
try:
 with sqlite3.connect(db) as connection:
  connection.execute("INSERT INTO research_runs_v2 VALUES ('legacy-running','legacy-thread','legacy-query','generic','1','{}','running','not_required','pending',1,?,?)",(now,now))
  connection.execute("INSERT INTO run_segments VALUES ('legacy-running_seg_000','legacy-running','initial',0,1,'running',?,?)",(now,now))
  connection.execute("INSERT INTO run_dispatches_v1 VALUES ('legacy-running','started',NULL,NULL,1,NULL,?,?,?)",(now,now,now))
except Exception:
 sys.exit(42)
"""
    prepared = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            prepare_code,
            str(export),
            str(current),
        ],
        cwd=export,
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONNOUSERSITE": "1",
            "PYTHON_DOTENV_DISABLED": "1",
        },
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if prepared.returncode == 41:
        raise ProofFailure(ERROR_CODES["rollback_import"])
    if prepared.returncode or prepared.stdout or prepared.stderr:
        raise ProofFailure(ERROR_CODES["rollback_verify"])
    migrate_run_execution_recovery_with_backup(db_path=str(current))
    backup = Path(f"{current}.pre-run-execution-recovery.bak")
    restored = root / "rollback-restored.db"
    try:
        shutil.copy2(backup, restored)
    except Exception as exc:
        raise ProofFailure(ERROR_CODES["rollback_restore"]) from exc
    if os.environ.get("DRA_RECOVERY_PROOF_INJECT_FAILURE") == "rollback_corrupt_db":
        with sqlite3.connect(restored) as connection:
            connection.execute("DROP TABLE run_dispatches_v1")
    code = """
import pathlib,sys
root=pathlib.Path(sys.argv[1]).resolve(); db=sys.argv[2]
sys.path.insert(0,str(root))
for name in list(sys.modules):
 if name=='api' or name.startswith('api.'): del sys.modules[name]
try:
 import api.run_migrations as migrations
 import api.run_repository as repository
 assert pathlib.Path(migrations.__file__).resolve().is_relative_to(root)
 assert pathlib.Path(repository.__file__).resolve().is_relative_to(root)
 assert (root/'.proof-revision').read_text(encoding='ascii')==sys.argv[3]
except Exception:
 sys.exit(41)
try:
 migrations.verify_run_schema(db_path=db)
except Exception:
 sys.exit(42)
"""
    verified = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            code,
            str(export),
            str(restored),
            ROLLBACK_REVISION,
        ],
        cwd=export,
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONNOUSERSITE": "1",
            "PYTHON_DOTENV_DISABLED": "1",
        },
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if verified.returncode == 41:
        raise ProofFailure(ERROR_CODES["rollback_import"])
    if verified.returncode or verified.stdout or verified.stderr:
        raise ProofFailure(ERROR_CODES["rollback_verify"])
    return {"backup_restored": True, "old_revision_verified": True}


def _retained_case(guard: _ProofBoundaryGuard) -> dict[str, Any]:
    environment = {**os.environ, "PYTHON_DOTENV_DISABLED": "1"}
    for script in (
        "run_dispatch_reconciliation_proof.py",
        "run_failure_cause_proof.py",
    ):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script), "check"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if completed.returncode or completed.stderr:
            raise RuntimeError("retained_contract_failed")
        payload = json.loads(completed.stdout)
        if not (payload.get("valid") is True or payload.get("status") == "valid"):
            raise RuntimeError("retained_contract_invalid")
    return {
        "provider_calls": guard.provider_calls,
        "tool_calls": guard.tool_calls,
        "retained_checks_passed": True,
    }


def _case(case_id: str, observations: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "status": "passed",
        "observations": observations,
    }


def build_report() -> dict[str, Any]:
    guard = _ProofBoundaryGuard()
    with tempfile.TemporaryDirectory(prefix="dra-recovery-proof-") as temporary:
        root = Path(temporary)
        for stage_root in (
            "writer",
            "migration",
            "execution",
            "finalization",
            "stale",
            "replacement",
            "rollback",
        ):
            (root / stage_root).mkdir()
        cases = [
            _case(
                "exclusive_writer_fail_closed",
                _run_stage("writer", lambda: _writer_case(root / "writer")),
            ),
            _case(
                "migration_backfill_restore",
                _run_stage(
                    "migration",
                    lambda: _migration_case(root / "migration"),
                ),
            ),
            _case(
                "execution_phase_sigkill",
                _run_stage(
                    "execution",
                    lambda: _sigkill_case(root / "execution", "execution"),
                ),
            ),
            _case(
                "finalization_phase_sigkill",
                _run_stage(
                    "finalization",
                    lambda: _sigkill_case(
                        root / "finalization",
                        "finalization",
                    ),
                ),
            ),
            _case(
                "stale_generation_fenced",
                _run_stage("stale", lambda: _stale_case(root / "stale")),
            ),
            _case(
                "explicit_replacement_replay",
                _run_stage(
                    "replacement",
                    lambda: _replacement_case(root / "replacement", guard),
                ),
            ),
            _case(
                "old_revision_rollback",
                _run_stage(
                    "rollback_revision",
                    lambda: _run_stage(
                        "rollback_import",
                        lambda: _run_stage(
                            "rollback_restore",
                            lambda: _run_stage(
                                "rollback_verify",
                                lambda: _rollback_case(root / "rollback"),
                            ),
                        ),
                    ),
                ),
            ),
            _case(
                "retained_contracts",
                _run_stage("retained", lambda: _retained_case(guard)),
            ),
        ]
    return validate_report(
        {
            "schema_version": "dra.run-execution-recovery-proof.v1",
            "status": "valid",
            "source": "provider_free_real_process",
            "cases": cases,
            "boundaries": dict(BOUNDARIES),
            "limits": list(LIMITS),
        }
    )


def _expected_report() -> dict[str, Any]:
    return {
        "schema_version": "dra.run-execution-recovery-proof.v1",
        "status": "valid",
        "source": "provider_free_real_process",
        "cases": [
            _case(
                "exclusive_writer_fail_closed",
                {
                    "overlap_rejected": True,
                    "database_untouched": True,
                    "os_released_after_sigkill": True,
                },
            ),
            _case(
                "migration_backfill_restore",
                {
                    "backup_restored": True,
                    "pre_v1_running_converged": True,
                    "invented_business_rows": 0,
                },
            ),
            _case(
                "execution_phase_sigkill",
                {
                    "real_sigkill": True,
                    "cause_exact": True,
                    "active_owners_after": 0,
                },
            ),
            _case(
                "finalization_phase_sigkill",
                {
                    "real_sigkill": True,
                    "cause_exact": True,
                    "active_owners_after": 0,
                },
            ),
            _case(
                "stale_generation_fenced",
                {
                    "phase_writes": 0,
                    "business_writes": 0,
                    "terminal_writes": 0,
                },
            ),
            _case(
                "explicit_replacement_replay",
                {
                    "replacement_runs": 1,
                    "lineage_rows": 1,
                    "same_replacement": True,
                    "replay_marked": True,
                },
            ),
            _case(
                "old_revision_rollback",
                {"backup_restored": True, "old_revision_verified": True},
            ),
            _case(
                "retained_contracts",
                {
                    "provider_calls": 0,
                    "tool_calls": 0,
                    "retained_checks_passed": True,
                },
            ),
        ],
        "boundaries": dict(BOUNDARIES),
        "limits": list(LIMITS),
    }


def validate_report(report: dict[str, Any]) -> dict[str, Any]:
    if type(report) is not dict or report != _expected_report():
        raise ValueError("report_invalid")
    return report


def serialize_report(report: dict[str, Any]) -> str:
    return (
        json.dumps(
            validate_report(report),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("check",))
    return parser


def main(argv: list[str] | None = None) -> int:
    _parser().parse_args(argv)
    try:
        sys.stdout.write(serialize_report(build_report()))
        return 0
    except ProofFailure as exc:
        print(exc.code, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
