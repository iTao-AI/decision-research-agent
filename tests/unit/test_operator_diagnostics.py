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


def test_call_budget_operator_diagnostic_cleanup_replacement_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    replacement = b"operator replacement"
    observed_temporary: str | None = None
    race_fired = False
    real_stat = module.os.stat
    real_unlink = module.os.unlink
    real_rename = module.os.rename

    def is_temporary(name: object) -> bool:
        return (
            isinstance(name, str)
            and name.startswith(f".{module.CALL_BUDGET_SIDECAR_FILENAME}.")
            and name.endswith(".tmp")
        )

    def create_replacement(name: str, *, directory: int) -> None:
        descriptor = module.os.open(
            name,
            module.os.O_WRONLY | module.os.O_CREAT | module.os.O_EXCL,
            0o600,
            dir_fd=directory,
        )
        try:
            assert module.os.write(descriptor, replacement) == len(replacement)
        finally:
            module.os.close(descriptor)

    def observe_temporary(name: object, *args: object, **kwargs: object):
        nonlocal observed_temporary
        observed = real_stat(name, *args, **kwargs)
        if is_temporary(name):
            observed_temporary = name
        return observed

    def replace_between_stat_and_unlink(
        name: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        nonlocal race_fired
        if name == observed_temporary and not race_fired:
            assert isinstance(name, str)
            directory = kwargs.get("dir_fd")
            assert isinstance(directory, int)
            real_unlink(name, *args, **kwargs)
            create_replacement(name, directory=directory)
            race_fired = True
        real_unlink(name, *args, **kwargs)

    def replace_after_quarantine_rename(
        source: object,
        destination: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        nonlocal race_fired
        real_rename(source, destination, *args, **kwargs)
        if is_temporary(source) and not race_fired:
            assert isinstance(source, str)
            directory = kwargs.get("src_dir_fd")
            assert isinstance(directory, int)
            create_replacement(source, directory=directory)
            race_fired = True

    monkeypatch.setattr(module.os, "stat", observe_temporary)
    monkeypatch.setattr(module.os, "unlink", replace_between_stat_and_unlink)
    monkeypatch.setattr(module.os, "rename", replace_after_quarantine_rename)

    with pytest.raises(
        module.OperatorDiagnosticWriteError,
        match="operator_diagnostic_write_invalid",
    ):
        writer("run-cleanup-race", _diagnostic())

    assert race_fired
    run_directory = (
        tmp_path / module.CALL_BUDGET_SIDECAR_DIRECTORY / "run-cleanup-race"
    )
    assert any(path.read_bytes() == replacement for path in run_directory.iterdir())


def test_call_budget_operator_diagnostic_rejects_final_identity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    replacement = module._canonical_sidecar_bytes(_diagnostic())
    final_stat_calls = 0
    original_identity: tuple[int, int] | None = None
    race_fired = False
    real_stat = module.os.stat
    real_unlink = module.os.unlink

    def replace_before_final_validation(
        name: object,
        *args: object,
        **kwargs: object,
    ):
        nonlocal final_stat_calls, original_identity, race_fired
        if name == module.CALL_BUDGET_SIDECAR_FILENAME:
            final_stat_calls += 1
            if final_stat_calls == 2:
                directory = kwargs.get("dir_fd")
                assert isinstance(directory, int)
                real_unlink(name, dir_fd=directory)
                descriptor = module.os.open(
                    name,
                    module.os.O_WRONLY | module.os.O_CREAT | module.os.O_EXCL,
                    0o600,
                    dir_fd=directory,
                )
                try:
                    assert module.os.write(descriptor, replacement) == len(replacement)
                finally:
                    module.os.close(descriptor)
                race_fired = True
        observed = real_stat(name, *args, **kwargs)
        if name == module.CALL_BUDGET_SIDECAR_FILENAME and final_stat_calls == 1:
            original_identity = (observed.st_dev, observed.st_ino)
        return observed

    monkeypatch.setattr(module.os, "stat", replace_before_final_validation)

    with pytest.raises(
        module.OperatorDiagnosticWriteError,
        match="operator_diagnostic_write_invalid",
    ):
        writer("run-final-race", _diagnostic())

    assert race_fired
    assert original_identity is not None
    final = (
        tmp_path
        / module.CALL_BUDGET_SIDECAR_DIRECTORY
        / "run-final-race"
        / module.CALL_BUDGET_SIDECAR_FILENAME
    )
    assert final.read_bytes() == replacement
    assert (final.stat().st_dev, final.stat().st_ino) != original_identity


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
