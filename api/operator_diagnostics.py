"""Private, opt-in runtime publication for bounded operator diagnostics."""
from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import stat
from typing import Callable

from agent.harness_contracts import CallBudgetDiagnostic
from api.thread_ids import validate_thread_id


CALL_BUDGET_DIAGNOSTICS_ENV = (
    "DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_LIMITER_DIAGNOSTICS"
)
CALL_BUDGET_SIDECAR_SCHEMA_VERSION = "dra.call-budget-origin-sidecar.v1"
CALL_BUDGET_SIDECAR_DIRECTORY = PurePosixPath("operator-diagnostics")
CALL_BUDGET_SIDECAR_FILENAME = "call-budget-v1.json"
MAX_CALL_BUDGET_SIDECAR_BYTES = 4096


class OperatorDiagnosticConfigurationError(RuntimeError):
    """Stable private failure for an invalid proof-owned mode."""

    def __init__(self) -> None:
        super().__init__("operator_diagnostics_configuration_invalid")


class OperatorDiagnosticWriteError(RuntimeError):
    """Stable private failure without filesystem or payload details."""

    def __init__(self) -> None:
        super().__init__("operator_diagnostic_write_invalid")


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | os.O_DIRECTORY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )


def _open_directory_no_symlinks(path: Path) -> int:
    if not path.is_absolute():
        raise OperatorDiagnosticWriteError
    descriptor = os.open(path.anchor, _directory_flags())
    try:
        for component in path.parts[1:]:
            if component in {"", ".", ".."}:
                raise OperatorDiagnosticWriteError
            child = os.open(component, _directory_flags(), dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _require_private_directory(descriptor: int) -> os.stat_result:
    observed = os.fstat(descriptor)
    permissions = stat.S_IMODE(observed.st_mode)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.geteuid()
        or permissions & 0o077
        or permissions & 0o700 != 0o700
    ):
        raise OperatorDiagnosticWriteError
    return observed


def _require_owned_output_root(descriptor: int) -> os.stat_result:
    observed = os.fstat(descriptor)
    permissions = stat.S_IMODE(observed.st_mode)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.geteuid()
        or permissions & 0o700 != 0o700
    ):
        raise OperatorDiagnosticWriteError
    return observed


def _open_or_create_private_directory(parent: int, name: str) -> int:
    try:
        os.mkdir(name, 0o700, dir_fd=parent)
    except FileExistsError:
        pass
    child = os.open(name, _directory_flags(), dir_fd=parent)
    try:
        _require_private_directory(child)
        return child
    except BaseException:
        os.close(child)
        raise


def _canonical_sidecar_bytes(diagnostic: CallBudgetDiagnostic) -> bytes:
    if type(diagnostic) is not CallBudgetDiagnostic:
        raise OperatorDiagnosticWriteError
    payload = {
        "schema_version": CALL_BUDGET_SIDECAR_SCHEMA_VERSION,
        "limiter": asdict(diagnostic),
    }
    raw = (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    if len(raw) > MAX_CALL_BUDGET_SIDECAR_BYTES:
        raise OperatorDiagnosticWriteError
    try:
        decoded = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise OperatorDiagnosticWriteError from exc
    if decoded != payload:
        raise OperatorDiagnosticWriteError
    return raw


def _unlink_owned_temporary(
    directory: int,
    name: str,
    identity: tuple[int, int],
) -> bool:
    quarantine = (
        f".{CALL_BUDGET_SIDECAR_FILENAME}."
        f"{secrets.token_hex(16)}.cleanup"
    )
    try:
        os.rename(
            name,
            quarantine,
            src_dir_fd=directory,
            dst_dir_fd=directory,
        )
    except FileNotFoundError:
        return False
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    cleanup_descriptor = os.open(quarantine, flags, dir_fd=directory)
    try:
        observed = os.fstat(cleanup_descriptor)
        if (
            (observed.st_dev, observed.st_ino) != identity
            or not stat.S_ISREG(observed.st_mode)
            or observed.st_uid != os.geteuid()
            or stat.S_IMODE(observed.st_mode) != 0o600
        ):
            return False
        os.unlink(quarantine, dir_fd=directory)
        try:
            os.stat(name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            return True
        return False
    finally:
        os.close(cleanup_descriptor)


def _write_call_budget_sidecar(
    output_root: Path,
    run_id: str,
    diagnostic: CallBudgetDiagnostic,
) -> None:
    try:
        validated_run_id = validate_thread_id(run_id)
        raw = _canonical_sidecar_bytes(diagnostic)
        root = _open_directory_no_symlinks(output_root)
        diagnostics_directory: int | None = None
        run_directory: int | None = None
        temporary_name: str | None = None
        temporary_identity: tuple[int, int] | None = None
        try:
            _require_owned_output_root(root)
            diagnostics_directory = _open_or_create_private_directory(
                root,
                CALL_BUDGET_SIDECAR_DIRECTORY.as_posix(),
            )
            os.fsync(root)
            run_directory = _open_or_create_private_directory(
                diagnostics_directory,
                validated_run_id,
            )
            os.fsync(diagnostics_directory)
            temporary_name = (
                f".{CALL_BUDGET_SIDECAR_FILENAME}."
                f"{secrets.token_hex(16)}.tmp"
            )
            flags = (
                os.O_RDWR
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0)
            )
            file_descriptor = os.open(
                temporary_name,
                flags,
                0o600,
                dir_fd=run_directory,
            )
            try:
                os.fchmod(file_descriptor, 0o600)
                opened = os.fstat(file_descriptor)
                temporary_identity = (opened.st_dev, opened.st_ino)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or opened.st_nlink != 1
                    or opened.st_uid != os.geteuid()
                    or stat.S_IMODE(opened.st_mode) != 0o600
                ):
                    raise OperatorDiagnosticWriteError
                view = memoryview(raw)
                while view:
                    written = os.write(file_descriptor, view)
                    if type(written) is not int or written <= 0 or written > len(view):
                        raise OperatorDiagnosticWriteError
                    view = view[written:]
                os.fsync(file_descriptor)
                os.link(
                    temporary_name,
                    CALL_BUDGET_SIDECAR_FILENAME,
                    src_dir_fd=run_directory,
                    dst_dir_fd=run_directory,
                    follow_symlinks=False,
                )
                linked = os.stat(
                    CALL_BUDGET_SIDECAR_FILENAME,
                    dir_fd=run_directory,
                    follow_symlinks=False,
                )
                observed_raw = os.pread(file_descriptor, len(raw) + 1, 0)
                opened = os.fstat(file_descriptor)
                if (
                    temporary_identity is None
                    or (linked.st_dev, linked.st_ino) != temporary_identity
                    or (opened.st_dev, opened.st_ino) != temporary_identity
                    or not stat.S_ISREG(linked.st_mode)
                    or linked.st_uid != os.geteuid()
                    or stat.S_IMODE(linked.st_mode) != 0o600
                    or linked.st_size != len(raw)
                    or opened.st_size != len(raw)
                    or observed_raw != raw
                    or json.loads(observed_raw) != json.loads(raw)
                ):
                    raise OperatorDiagnosticWriteError
                removed = _unlink_owned_temporary(
                    run_directory,
                    temporary_name,
                    temporary_identity,
                )
                temporary_name = None
                if not removed:
                    raise OperatorDiagnosticWriteError
                final = os.stat(
                    CALL_BUDGET_SIDECAR_FILENAME,
                    dir_fd=run_directory,
                    follow_symlinks=False,
                )
                opened = os.fstat(file_descriptor)
                observed_raw = os.pread(file_descriptor, len(raw) + 1, 0)
                if (
                    (final.st_dev, final.st_ino) != temporary_identity
                    or (opened.st_dev, opened.st_ino) != temporary_identity
                    or not stat.S_ISREG(final.st_mode)
                    or not stat.S_ISREG(opened.st_mode)
                    or final.st_nlink != 1
                    or opened.st_nlink != 1
                    or final.st_uid != os.geteuid()
                    or opened.st_uid != os.geteuid()
                    or stat.S_IMODE(final.st_mode) != 0o600
                    or stat.S_IMODE(opened.st_mode) != 0o600
                    or final.st_size != len(raw)
                    or opened.st_size != len(raw)
                    or observed_raw != raw
                ):
                    raise OperatorDiagnosticWriteError
                os.fsync(run_directory)
            finally:
                os.close(file_descriptor)
        finally:
            if (
                run_directory is not None
                and temporary_name is not None
                and temporary_identity is not None
            ):
                try:
                    _unlink_owned_temporary(
                        run_directory,
                        temporary_name,
                        temporary_identity,
                    )
                except OSError:
                    pass
            if run_directory is not None:
                os.close(run_directory)
            if diagnostics_directory is not None:
                os.close(diagnostics_directory)
            os.close(root)
    except OperatorDiagnosticWriteError:
        raise
    except Exception as exc:
        raise OperatorDiagnosticWriteError from exc


def call_budget_diagnostic_writer_from_environment(
    *,
    output_root: Path,
) -> Callable[[str, CallBudgetDiagnostic], None] | None:
    value = os.environ.get(CALL_BUDGET_DIAGNOSTICS_ENV)
    if value is None:
        return None
    if value != "true":
        raise OperatorDiagnosticConfigurationError
    if not isinstance(output_root, Path) or not output_root.is_absolute():
        raise OperatorDiagnosticConfigurationError

    def write(run_id: str, diagnostic: CallBudgetDiagnostic) -> None:
        _write_call_budget_sidecar(output_root, run_id, diagnostic)

    return write
