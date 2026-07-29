from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from api.run_execution_models import RunExecutionConflict
from api.run_execution_writer_lock import acquire_run_execution_writer


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _python_tree(relative_path: str) -> ast.Module:
    return ast.parse(
        (PROJECT_ROOT / relative_path).read_text(encoding="utf-8"),
        filename=relative_path,
    )


def _calls_named(tree: ast.AST, name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Name)
            and node.func.id == name
            or isinstance(node.func, ast.Attribute)
            and node.func.attr == name
        )
    ]


def test_production_cannot_transition_directly_into_running():
    transition_calls = []
    for path in sorted((PROJECT_ROOT / "api").glob("*.py")):
        transition_calls.extend(
            (path.name, call)
            for call in _calls_named(
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path)),
                "transition_run",
            )
        )
    assert transition_calls == []


def test_every_running_finalize_call_supplies_owner_handle():
    tree = _python_tree("api/server.py")
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "to_thread"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "finalize_run_transaction"
    ]
    assert calls
    for call in calls:
        assert "owner_handle" in {
            keyword.arg for keyword in call.keywords if keyword.arg is not None
        }


def test_negative_corruption_fixtures_are_not_imported_by_production():
    imported_modules = set()
    for path in sorted((PROJECT_ROOT / "api").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.add(node.module)
    assert not any(
        module == "tests" or module.startswith("tests.")
        for module in imported_modules
    )

    helper = _python_tree("tests/run_execution_helpers.py")
    assert not any(
        isinstance(node, ast.Import)
        and any(alias.name == "sqlite3" for alias in node.names)
        for node in ast.walk(helper)
    )


def test_evaluation_replay_uses_boot_owner_and_drains_task_admission():
    tree = _python_tree("scripts/agent_evaluation_replay.py")
    assert _calls_named(tree, "activate_run_execution_boot")
    assert _calls_named(tree, "open_tracked_task_admission")
    assert _calls_named(tree, "close_tracked_task_admission")
    assert _calls_named(tree, "drain_tracked_tasks")
    dispatch_calls = _calls_named(tree, "_run_dispatched_with_persistence")
    assert dispatch_calls
    assert all(
        "owner_box"
        in {keyword.arg for keyword in call.keywords if keyword.arg is not None}
        for call in dispatch_calls
    )


def _configure_runtime(monkeypatch, tmp_path):
    import api.server as server

    db = tmp_path / "nested" / "application" / "runs.db"
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(db))
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "false")
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION",
        "false",
    )
    monkeypatch.setattr(server, "output_dir", tmp_path / "output")
    return server, db


def _instrument_lifespan(monkeypatch, tmp_path, events, *, drain=None):
    server, db = _configure_runtime(monkeypatch, tmp_path)

    class Writer:
        def release(self):
            events.append("writer_release")

    class Worker:
        def __init__(self):
            self.stopped = asyncio.Event()

        async def run_forever(self):
            events.append("worker_start")
            await self.stopped.wait()

        def stop(self):
            events.append("worker_stop")
            self.stopped.set()

    runtime = SimpleNamespace(
        enabled=False,
        application_db_path=db,
        checkpoint_db_path=tmp_path / "checkpoint.db",
    )
    monkeypatch.setattr(
        server,
        "acquire_run_execution_writer",
        lambda **kwargs: events.append("writer_acquire") or Writer(),
    )
    monkeypatch.setattr(
        server,
        "validate_review_runtime",
        lambda **kwargs: events.append("review_probe") or runtime,
    )
    monkeypatch.setattr(
        server,
        "validate_evidence_verification_runtime",
        lambda **kwargs: runtime,
    )
    monkeypatch.setattr(
        server,
        "migrate_with_backup",
        lambda **kwargs: events.append("migration") or {},
    )
    monkeypatch.setattr(
        server,
        "activate_run_execution_boot",
        lambda **kwargs: events.append("boot") or SimpleNamespace(
            interrupted_execution_count=0,
            interrupted_finalization_count=0,
        ),
    )
    monkeypatch.setattr(
        server,
        "open_tracked_task_admission",
        lambda: events.append("admission_open"),
    )
    monkeypatch.setattr(
        server,
        "close_tracked_task_admission",
        lambda: events.append("admission_close"),
    )

    async def default_drain():
        events.append("drain")

    monkeypatch.setattr(server, "drain_tracked_tasks", drain or default_drain)
    monkeypatch.setattr(
        server,
        "tracked_task_registry_is_empty",
        lambda: True,
    )
    monkeypatch.setattr(
        server,
        "create_run_dispatch_worker",
        lambda *args, **kwargs: events.append("worker_construct") or Worker(),
    )
    return server, db


@pytest.mark.asyncio
async def test_lifespan_bootstraps_missing_nested_db_parent_before_writer_acquire(
    tmp_path,
    monkeypatch,
):
    server, db = _configure_runtime(monkeypatch, tmp_path)
    assert not db.parent.exists()
    async with server.lifespan(server.app):
        assert db.parent.is_dir()
        assert db.exists()


@pytest.mark.asyncio
async def test_lifespan_acquires_writer_before_any_migration_backup_or_boot_write(
    tmp_path,
    monkeypatch,
):
    events = []
    server, _ = _instrument_lifespan(monkeypatch, tmp_path, events)
    async with server.lifespan(server.app):
        pass
    assert events.index("writer_acquire") < events.index("migration") < events.index("boot")


@pytest.mark.asyncio
async def test_lifespan_writer_contention_fails_before_database_and_workers(
    tmp_path,
    monkeypatch,
):
    server, db = _configure_runtime(monkeypatch, tmp_path)
    first = acquire_run_execution_writer(db_path=db)
    try:
        with pytest.raises(
            RunExecutionConflict,
            match="run_execution_writer_already_active",
        ):
            async with server.lifespan(server.app):
                pass
        assert not db.exists()
        assert server.app.state.run_dispatch_worker is None
    finally:
        first.release()


def test_server_import_does_not_create_output_directory():
    source = (
        Path(__file__).resolve().parents[2] / "api" / "server.py"
    ).read_text(encoding="utf-8")
    module_prefix = source.split("@asynccontextmanager", 1)[0]
    assert "output_dir.mkdir" not in module_prefix


@pytest.mark.asyncio
async def test_review_writability_probes_run_only_after_writer_acquire(
    tmp_path,
    monkeypatch,
):
    events = []
    server, _ = _instrument_lifespan(monkeypatch, tmp_path, events)
    async with server.lifespan(server.app):
        pass
    assert events.index("writer_acquire") < events.index("review_probe")


@pytest.mark.asyncio
async def test_lifespan_applies_010_and_activates_boot_before_dispatch_worker(
    tmp_path,
    monkeypatch,
):
    events = []
    server, _ = _instrument_lifespan(monkeypatch, tmp_path, events)
    async with server.lifespan(server.app):
        pass
    assert events.index("migration") < events.index("boot") < events.index(
        "worker_construct"
    )


@pytest.mark.asyncio
async def test_lifespan_fails_before_workers_when_010_or_convergence_is_invalid(
    tmp_path,
    monkeypatch,
):
    events = []
    server, _ = _instrument_lifespan(monkeypatch, tmp_path, events)

    def fail_migration(**kwargs):
        events.append("migration_failed")
        raise RunExecutionConflict("run_execution_recovery_unavailable")

    monkeypatch.setattr(server, "migrate_with_backup", fail_migration)
    with pytest.raises(RunExecutionConflict):
        async with server.lifespan(server.app):
            pass
    assert "worker_construct" not in events


def test_testclient_context_runs_activation_and_shutdown(tmp_path, monkeypatch):
    events = []
    server, _ = _instrument_lifespan(monkeypatch, tmp_path, events)
    with TestClient(server.app) as client:
        assert client.get("/health").status_code == 200
    assert "boot" in events and "writer_release" in events


@pytest.mark.asyncio
async def test_lifespan_clears_private_boot_state_on_shutdown(tmp_path, monkeypatch):
    events = []
    server, _ = _instrument_lifespan(monkeypatch, tmp_path, events)
    async with server.lifespan(server.app):
        assert server.app.state.run_execution_boot_id is not None
    assert server.app.state.run_execution_boot_id is None


def test_no_periodic_recovery_worker_or_heartbeat_task_is_started():
    source = (
        Path(__file__).resolve().parents[2] / "api" / "server.py"
    ).read_text(encoding="utf-8")
    assert "heartbeat" not in source
    assert "periodic_recovery" not in source


@pytest.mark.asyncio
async def test_shutdown_closes_task_admission_before_worker_stop(
    tmp_path,
    monkeypatch,
):
    events = []
    server, _ = _instrument_lifespan(monkeypatch, tmp_path, events)
    async with server.lifespan(server.app):
        pass
    assert events.index("admission_close") < events.index("worker_stop")


@pytest.mark.asyncio
async def test_shutdown_drains_tracked_runs_and_callbacks_before_writer_release(
    tmp_path,
    monkeypatch,
):
    events = []
    server, _ = _instrument_lifespan(monkeypatch, tmp_path, events)
    async with server.lifespan(server.app):
        pass
    assert events.index("drain") < events.index("writer_release")


@pytest.mark.asyncio
async def test_shutdown_does_not_release_writer_while_owner_finalizer_is_unsettled(
    tmp_path,
    monkeypatch,
):
    events = []
    release = asyncio.Event()

    async def held_drain():
        events.append("drain_started")
        await release.wait()
        events.append("drain_finished")

    server, _ = _instrument_lifespan(
        monkeypatch,
        tmp_path,
        events,
        drain=held_drain,
    )
    context = server.lifespan(server.app)
    await context.__aenter__()
    closing = asyncio.create_task(context.__aexit__(None, None, None))
    await asyncio.sleep(0)
    assert "writer_release" not in events
    release.set()
    await closing
    assert events.index("drain_finished") < events.index("writer_release")


@pytest.mark.asyncio
async def test_shutdown_cancellation_settles_drain_before_writer_release(
    tmp_path,
    monkeypatch,
):
    events = []
    release = asyncio.Event()

    async def held_drain():
        events.append("drain_started")
        await release.wait()
        events.append("drain_finished")

    server, _ = _instrument_lifespan(
        monkeypatch,
        tmp_path,
        events,
        drain=held_drain,
    )
    context = server.lifespan(server.app)
    await context.__aenter__()
    closing = asyncio.create_task(context.__aexit__(None, None, None))
    await asyncio.sleep(0)
    closing.cancel()
    await asyncio.sleep(0)
    assert "writer_release" not in events
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await closing
    assert events.index("drain_finished") < events.index("writer_release")


@pytest.mark.asyncio
async def test_drain_failure_never_calls_writer_release(tmp_path, monkeypatch):
    events = []

    async def failed_drain():
        events.append("drain_failed")
        raise RuntimeError("private drain failure")

    server, _ = _instrument_lifespan(
        monkeypatch,
        tmp_path,
        events,
        drain=failed_drain,
    )
    with pytest.raises(RuntimeError, match="run_execution_shutdown_unavailable"):
        async with server.lifespan(server.app):
            pass
    assert "writer_release" not in events
