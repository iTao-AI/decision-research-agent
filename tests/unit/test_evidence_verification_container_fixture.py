from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

import pytest
import yaml

from api.run_dispatch_repository import (
    claim_run_dispatch,
    start_run_dispatch,
)
from api.run_dispatch_worker import RunDispatchWorker
from api.run_repository import (
    create_run,
    finalize_run_transaction,
    get_run,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_FLAG = "DECISION_RESEARCH_AGENT_EVIDENCE_VERIFICATION_FIXTURE"
FIXTURE_OVERRIDE = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "evidence-verification-v1"
    / "docker-compose.fixture.yml"
)


def _create_pending_run(db_path: str) -> dict:
    return create_run(
        db_path=db_path,
        thread_id="verification-fixture-thread",
        query="verification fixture query",
    )


def test_production_dispatch_can_invalidate_the_old_fixture_fence(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "dispatch-race.db")
    created = _create_pending_run(db_path)
    worker = RunDispatchWorker(
        db_path=db_path,
        worker_id="dispatch_worker_" + "a" * 32,
        scheduler=lambda claim: start_run_dispatch(
            db_path=db_path,
            claim=claim,
        ),
    )

    assert asyncio.run(worker.run_once(run_id=created["run_id"])) is True
    raced = get_run(db_path=db_path, run_id=created["run_id"])
    assert raced is not None
    assert raced["execution_status"] == "running"
    assert raced["state_version"] == 1
    assert finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        review_status="not_required",
        delivery_status="ready",
        evidence_entries=[],
    ) is False


def test_test_only_worker_leaves_fixture_dispatch_unclaimed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(FIXTURE_FLAG, "true")
    fixture = importlib.import_module(
        "scripts.evidence_verification_container_fixture"
    )
    assert hasattr(fixture, "create_fixture_worker")
    db_path = str(tmp_path / "idle-worker.db")
    created = _create_pending_run(db_path)

    worker = fixture.create_fixture_worker(db_path)

    assert asyncio.run(worker.run_once(run_id=created["run_id"])) is False
    pending = get_run(db_path=db_path, run_id=created["run_id"])
    assert pending is not None
    assert pending["execution_status"] == "pending"
    assert pending["state_version"] == 0
    assert claim_run_dispatch(
        db_path=db_path,
        worker_id="dispatch_worker_" + "b" * 32,
        lease_seconds=30,
        run_id=created["run_id"],
    ) is not None


def test_test_only_server_wrapper_installs_idle_dispatch_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(FIXTURE_FLAG, "true")
    fixture = importlib.import_module(
        "scripts.evidence_verification_container_fixture"
    )
    server = importlib.import_module("api.server")
    uvicorn = importlib.import_module("uvicorn")
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(server, "create_run_dispatch_worker", object())
    monkeypatch.setattr(server, "run_deep_agent", object())
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda app, **kwargs: calls.append({"app": app, **kwargs}),
    )

    assert fixture.serve() == 0
    assert server.create_run_dispatch_worker is fixture.create_fixture_worker
    assert server.run_deep_agent is fixture._forbid_agent_path
    assert calls == [
        {
            "app": server.app,
            "host": "0.0.0.0",
            "port": 8000,
            "log_level": "warning",
            "access_log": False,
        }
    ]


def test_fixture_cli_requires_explicit_enabled_serve_or_seed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = importlib.import_module(
        "scripts.evidence_verification_container_fixture"
    )

    assert fixture.main([]) == 1
    invalid = capsys.readouterr()
    assert invalid.out == ""
    assert invalid.err == '{"code":"fixture_command_invalid"}\n'

    assert fixture.main(["serve"]) == 1
    disabled = capsys.readouterr()
    assert disabled.out == ""
    assert disabled.err == '{"code":"fixture_disabled"}\n'

    monkeypatch.setenv(FIXTURE_FLAG, "true")
    monkeypatch.setattr(
        fixture,
        "seed",
        lambda: {"run_id": "run-fixture", "evidence_id": "ev-fixture"},
    )
    assert fixture.main(["seed"]) == 0
    seeded = capsys.readouterr()
    assert seeded.err == ""
    assert seeded.out == (
        '{"evidence_id": "ev-fixture", "run_id": "run-fixture"}\n'
    )


def test_evidence_verification_compose_override_is_explicit_and_test_only() -> None:
    assert FIXTURE_OVERRIDE.is_file()
    override = yaml.safe_load(FIXTURE_OVERRIDE.read_text(encoding="utf-8"))
    backend = override["services"]["backend"]

    assert backend["command"] == [
        "python",
        "scripts/evidence_verification_container_fixture.py",
        "serve",
    ]
    assert backend["environment"] == {FIXTURE_FLAG: "true"}
