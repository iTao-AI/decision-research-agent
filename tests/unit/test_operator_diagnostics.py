from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import stat

import pytest

from agent.harness_contracts import CallBudgetDiagnostic


def _diagnostic() -> CallBudgetDiagnostic:
    return CallBudgetDiagnostic(
        limiter_kind="model",
        tool_scope="not_applicable",
        run_count=40,
        run_limit=40,
        thread_count=40,
        thread_limit=None,
        agent_role="not_observed",
    )


def test_call_budget_operator_diagnostic_is_absent_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.operator_diagnostics import (
        call_budget_diagnostic_writer_from_environment,
    )

    monkeypatch.delenv(
        "DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_LIMITER_DIAGNOSTICS",
        raising=False,
    )

    assert call_budget_diagnostic_writer_from_environment(output_root=tmp_path) is None
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("value", ["", "TRUE", "1", " true", "true ", "false"])
def test_call_budget_operator_diagnostic_rejects_every_non_exact_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    from api.operator_diagnostics import (
        OperatorDiagnosticConfigurationError,
        call_budget_diagnostic_writer_from_environment,
    )

    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_LIMITER_DIAGNOSTICS",
        value,
    )

    with pytest.raises(
        OperatorDiagnosticConfigurationError,
        match="operator_diagnostics_configuration_invalid",
    ):
        call_budget_diagnostic_writer_from_environment(output_root=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_call_budget_operator_diagnostic_writes_exact_canonical_owner_only_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.operator_diagnostics import (
        CALL_BUDGET_SIDECAR_DIRECTORY,
        CALL_BUDGET_SIDECAR_FILENAME,
        CALL_BUDGET_SIDECAR_SCHEMA_VERSION,
        call_budget_diagnostic_writer_from_environment,
    )

    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_LIMITER_DIAGNOSTICS",
        "true",
    )
    tmp_path.chmod(0o755)
    writer = call_budget_diagnostic_writer_from_environment(output_root=tmp_path)
    assert writer is not None

    writer("run-1", _diagnostic())

    sidecar = (
        tmp_path
        / CALL_BUDGET_SIDECAR_DIRECTORY
        / "run-1"
        / CALL_BUDGET_SIDECAR_FILENAME
    )
    expected = (
        b'{"limiter":{"agent_role":"not_observed","limiter_kind":"model",'
        b'"run_count":40,"run_limit":40,"thread_count":40,'
        b'"thread_limit":null,"tool_scope":"not_applicable"},'
        b'"schema_version":"dra.call-budget-origin-sidecar.v1"}\n'
    )
    assert CALL_BUDGET_SIDECAR_SCHEMA_VERSION.encode() in expected
    assert sidecar.read_bytes() == expected
    assert len(expected) <= 4096
    assert stat.S_ISREG(sidecar.stat().st_mode)
    assert stat.S_IMODE(sidecar.stat().st_mode) == 0o600
    assert sidecar.stat().st_uid == os.geteuid()
    assert stat.S_IMODE(sidecar.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(sidecar.parent.parent.stat().st_mode) == 0o700
    assert json.loads(expected) == {
        "schema_version": CALL_BUDGET_SIDECAR_SCHEMA_VERSION,
        "limiter": {
            "limiter_kind": "model",
            "tool_scope": "not_applicable",
            "run_count": 40,
            "run_limit": 40,
            "thread_count": 40,
            "thread_limit": None,
            "agent_role": "not_observed",
        },
    }


def test_call_budget_operator_diagnostic_rejects_bad_ids_symlinks_and_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.operator_diagnostics import (
        CALL_BUDGET_SIDECAR_DIRECTORY,
        OperatorDiagnosticWriteError,
        call_budget_diagnostic_writer_from_environment,
    )

    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_LIMITER_DIAGNOSTICS",
        "true",
    )
    writer = call_budget_diagnostic_writer_from_environment(output_root=tmp_path)
    assert writer is not None
    for invalid in ("../run", "/run", "", "run:1"):
        with pytest.raises(OperatorDiagnosticWriteError):
            writer(invalid, _diagnostic())

    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / CALL_BUDGET_SIDECAR_DIRECTORY).symlink_to(
        outside,
        target_is_directory=True,
    )
    with pytest.raises(OperatorDiagnosticWriteError):
        writer("run-1", _diagnostic())
    assert list(outside.iterdir()) == []

    (tmp_path / CALL_BUDGET_SIDECAR_DIRECTORY).unlink()
    writer("run-1", _diagnostic())
    with pytest.raises(OperatorDiagnosticWriteError):
        writer("run-1", _diagnostic())


def test_call_budget_operator_diagnostic_concurrent_publication_has_one_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.operator_diagnostics import (
        CALL_BUDGET_SIDECAR_DIRECTORY,
        CALL_BUDGET_SIDECAR_FILENAME,
        call_budget_diagnostic_writer_from_environment,
    )

    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_LIMITER_DIAGNOSTICS",
        "true",
    )
    writer = call_budget_diagnostic_writer_from_environment(output_root=tmp_path)
    assert writer is not None

    def publish() -> str:
        try:
            writer("run-concurrent", _diagnostic())
        except Exception as exc:  # private stable error is the expected loser
            return str(exc)
        return "published"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: publish(), range(2)))

    assert sorted(results) == ["operator_diagnostic_write_invalid", "published"]
    sidecar = (
        tmp_path
        / CALL_BUDGET_SIDECAR_DIRECTORY
        / "run-concurrent"
        / CALL_BUDGET_SIDECAR_FILENAME
    )
    assert sidecar.is_file()


@pytest.mark.parametrize("failure", ["write", "link", "fsync"])
def test_call_budget_operator_diagnostic_maps_publication_failure_to_stable_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    import api.operator_diagnostics as module

    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_LIMITER_DIAGNOSTICS",
        "true",
    )
    writer = module.call_budget_diagnostic_writer_from_environment(
        output_root=tmp_path
    )
    assert writer is not None
    marker = tmp_path / "pre-existing"
    marker.write_bytes(b"operator-owned")
    if failure == "write":
        monkeypatch.setattr(
            module.os,
            "write",
            lambda _fd, _raw: (_ for _ in ()).throw(OSError()),
        )
    elif failure == "link":
        monkeypatch.setattr(
            module.os,
            "link",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError()),
        )
    else:
        real_fsync = module.os.fsync

        def fail_file_fsync(descriptor: int) -> None:
            if stat.S_ISREG(module.os.fstat(descriptor).st_mode):
                raise OSError
            real_fsync(descriptor)

        monkeypatch.setattr(module.os, "fsync", fail_file_fsync)

    with pytest.raises(
        module.OperatorDiagnosticWriteError,
        match="operator_diagnostic_write_invalid",
    ):
        writer(f"run-{failure}", _diagnostic())

    final = (
        tmp_path
        / module.CALL_BUDGET_SIDECAR_DIRECTORY
        / f"run-{failure}"
        / module.CALL_BUDGET_SIDECAR_FILENAME
    )
    assert not final.exists()
    assert list(tmp_path.rglob("*.tmp")) == []
    assert marker.read_bytes() == b"operator-owned"
