from __future__ import annotations

import os
from pathlib import Path
import stat

import pytest
from pydantic import ValidationError


def _payload(**limiter_changes: object) -> dict[str, object]:
    limiter: dict[str, object] = {
        "limiter_kind": "model",
        "tool_scope": "not_applicable",
        "run_count": 40,
        "run_limit": 40,
        "thread_count": 40,
        "thread_limit": None,
        "agent_role": "not_observed",
    }
    limiter.update(limiter_changes)
    return {
        "schema_version": "dra.call-budget-origin-sidecar.v1",
        "limiter": limiter,
    }


def _write_sidecar(root: Path, raw: bytes) -> Path:
    path = root / "operator-diagnostics" / "run-1" / "call-budget-v1.json"
    path.parent.mkdir(parents=True, mode=0o700)
    path.write_bytes(raw)
    path.chmod(0o600)
    return path


def test_runtime_diagnostic_reader_returns_exact_canonical_closed_bytes(
    tmp_path: Path,
) -> None:
    from scripts.bounded_live_producer_runtime_diagnostics import (
        parse_call_budget_sidecar,
        read_call_budget_sidecar,
        serialize_call_budget_sidecar,
    )

    expected = parse_call_budget_sidecar(_payload())
    raw = serialize_call_budget_sidecar(expected)
    path = _write_sidecar(tmp_path, raw)

    observed = read_call_budget_sidecar("run-1", output_root=tmp_path)

    assert observed == expected
    assert serialize_call_budget_sidecar(observed) == raw
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert len(raw) <= 4096


@pytest.mark.parametrize(
    "payload",
    [
        _payload(extra="forbidden"),
        _payload(limiter_kind="unknown"),
        _payload(tool_scope="task"),
        _payload(run_count=True),
        _payload(run_count=-1),
        _payload(run_count=1_000_001),
        _payload(run_limit=0),
        _payload(agent_role="coordinator"),
    ],
)
def test_runtime_diagnostic_contract_rejects_schema_and_bound_mutations(
    payload: dict[str, object],
) -> None:
    from scripts.bounded_live_producer_runtime_diagnostics import (
        parse_call_budget_sidecar,
    )

    with pytest.raises((ValidationError, ValueError)):
        parse_call_budget_sidecar(payload)


@pytest.mark.parametrize("run_id", ["", "../run", "/run", "run:1", "a" * 129])
def test_runtime_diagnostic_reader_rejects_invalid_run_id(
    tmp_path: Path,
    run_id: str,
) -> None:
    from scripts.bounded_live_producer_runtime_diagnostics import (
        RuntimeDiagnosticReadError,
        read_call_budget_sidecar,
    )

    with pytest.raises(RuntimeDiagnosticReadError):
        read_call_budget_sidecar(run_id, output_root=tmp_path)


@pytest.mark.parametrize("mutation", ["missing", "directory", "symlink", "mode", "oversized", "trailing"])
def test_runtime_diagnostic_reader_rejects_unsafe_file_shapes(
    tmp_path: Path,
    mutation: str,
) -> None:
    from scripts.bounded_live_producer_runtime_diagnostics import (
        RuntimeDiagnosticReadError,
        parse_call_budget_sidecar,
        read_call_budget_sidecar,
        serialize_call_budget_sidecar,
    )

    raw = serialize_call_budget_sidecar(parse_call_budget_sidecar(_payload()))
    path = tmp_path / "operator-diagnostics" / "run-1" / "call-budget-v1.json"
    if mutation != "missing":
        path.parent.mkdir(parents=True, mode=0o700)
        if mutation == "directory":
            path.mkdir()
        elif mutation == "symlink":
            target = tmp_path / "outside.json"
            target.write_bytes(raw)
            target.chmod(0o600)
            path.symlink_to(target)
        else:
            path.write_bytes(
                b"x" * 4097
                if mutation == "oversized"
                else raw + b" "
                if mutation == "trailing"
                else raw
            )
            path.chmod(0o644 if mutation == "mode" else 0o600)

    with pytest.raises(RuntimeDiagnosticReadError):
        read_call_budget_sidecar("run-1", output_root=tmp_path)


def test_runtime_diagnostic_reader_rejects_open_file_identity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.bounded_live_producer_runtime_diagnostics as module

    raw = module.serialize_call_budget_sidecar(
        module.parse_call_budget_sidecar(_payload())
    )
    _write_sidecar(tmp_path, raw)
    real_fstat = module.os.fstat
    calls = 0

    def drift(descriptor: int):
        nonlocal calls
        observed = real_fstat(descriptor)
        if stat.S_ISREG(observed.st_mode):
            calls += 1
            if calls >= 2:
                values = list(observed)
                values[6] += 1
                return os.stat_result(values)
        return observed

    monkeypatch.setattr(module.os, "fstat", drift)
    with pytest.raises(module.RuntimeDiagnosticReadError):
        module.read_call_budget_sidecar("run-1", output_root=tmp_path)

