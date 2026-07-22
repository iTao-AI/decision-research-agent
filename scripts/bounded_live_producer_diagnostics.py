"""Safe operator-owned sink for bounded diagnostic receipts."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import stat
from typing import Callable

from scripts.bounded_live_producer_contracts import (
    CallBudgetLimiter,
    EvaluationError,
    MAX_DIAGNOSTIC_BYTES,
    serialize_result_diagnostic,
    serialize_call_budget_diagnostic,
    serialize_run_failure_diagnostic,
)


RESULT_DIAGNOSTIC_FILENAME = "bounded-live-producer-result-diagnostic-v1.json"
RUN_FAILURE_DIAGNOSTIC_FILENAME = (
    "bounded-live-producer-run-failure-diagnostic-v1.json"
)
CALL_BUDGET_DIAGNOSTIC_FILENAME = (
    "bounded-live-producer-call-budget-diagnostic-v1.json"
)
DIAGNOSTIC_FILENAME = RESULT_DIAGNOSTIC_FILENAME
_DIAGNOSTIC_SERIALIZERS: dict[str, Callable[..., bytes]] = {
    RESULT_DIAGNOSTIC_FILENAME: lambda error: serialize_result_diagnostic(error),
    RUN_FAILURE_DIAGNOSTIC_FILENAME: lambda error: serialize_run_failure_diagnostic(
        error
    ),
    CALL_BUDGET_DIAGNOSTIC_FILENAME: serialize_call_budget_diagnostic,
}


@dataclass(frozen=True, slots=True)
class DiagnosticSink:
    path: Path
    device: int
    inode: int
    uid: int
    permission_bits: int


class DiagnosticOutputError(Exception):
    """Stable private sink failure without filesystem or payload details."""

    def __init__(self) -> None:
        super().__init__("diagnostic_output_invalid")


def _open_directory_no_symlinks(path: Path) -> int:
    flags = (
        os.O_RDONLY
        | os.O_DIRECTORY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = os.open(path.anchor, flags)
    try:
        for component in path.parts[1:]:
            if component in {"", ".", ".."}:
                raise DiagnosticOutputError
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _preflight_diagnostic_dir(
    path: Path,
    *,
    repository_root: Path,
) -> DiagnosticSink:
    if not isinstance(path, Path) or not path.is_absolute():
        raise DiagnosticOutputError
    descriptor = _open_directory_no_symlinks(path)
    try:
        observed = os.fstat(descriptor)
        resolved = path.resolve(strict=True)
        repository = repository_root.resolve(strict=True)
        permissions = stat.S_IMODE(observed.st_mode)
        if (
            resolved == repository
            or repository in resolved.parents
            or not stat.S_ISDIR(observed.st_mode)
            or observed.st_uid != os.geteuid()
            or permissions & 0o077
            or permissions & 0o300 != 0o300
        ):
            raise DiagnosticOutputError
        for filename in _DIAGNOSTIC_SERIALIZERS:
            try:
                os.stat(filename, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise DiagnosticOutputError
        return DiagnosticSink(
            path=resolved,
            device=observed.st_dev,
            inode=observed.st_ino,
            uid=observed.st_uid,
            permission_bits=permissions,
        )
    finally:
        os.close(descriptor)


def preflight_diagnostic_dir(
    path: Path,
    *,
    repository_root: Path,
) -> DiagnosticSink:
    try:
        return _preflight_diagnostic_dir(path, repository_root=repository_root)
    except DiagnosticOutputError:
        raise
    except Exception as exc:
        raise DiagnosticOutputError from exc


def _identity_matches(sink: DiagnosticSink, observed: os.stat_result) -> bool:
    return (
        observed.st_dev,
        observed.st_ino,
        observed.st_uid,
        stat.S_IMODE(observed.st_mode),
    ) == (
        sink.device,
        sink.inode,
        sink.uid,
        sink.permission_bits,
    )


def _unlink_if_owned(
    descriptor: int,
    name: str,
    *,
    expected_identity: tuple[int, int],
) -> bool:
    quarantine = f".{DIAGNOSTIC_FILENAME}.{secrets.token_hex(16)}.cleanup"
    try:
        os.rename(
            name,
            quarantine,
            src_dir_fd=descriptor,
            dst_dir_fd=descriptor,
        )
    except FileNotFoundError:
        return False
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    cleanup_descriptor = os.open(quarantine, flags, dir_fd=descriptor)
    try:
        observed = os.fstat(cleanup_descriptor)
        if (observed.st_dev, observed.st_ino) != expected_identity:
            return False
        os.unlink(quarantine, dir_fd=descriptor)
        return True
    finally:
        os.close(cleanup_descriptor)


def _publish_diagnostic(
    sink: DiagnosticSink,
    error: EvaluationError,
    *,
    filename: str,
    remaining_seconds: Callable[[float], float],
    limiter: CallBudgetLimiter | None = None,
) -> Path:
    serializer = _DIAGNOSTIC_SERIALIZERS.get(filename)
    if serializer is None:
        raise DiagnosticOutputError
    raw = serializer(error, limiter) if limiter is not None else serializer(error)
    if len(raw) > MAX_DIAGNOSTIC_BYTES:
        raise DiagnosticOutputError
    remaining_seconds(1.0)
    descriptor = _open_directory_no_symlinks(sink.path)
    temporary = f".{filename}.{secrets.token_hex(16)}.tmp"
    temporary_created = False
    temporary_identity: tuple[int, int] | None = None
    try:
        observed = os.fstat(descriptor)
        if not _identity_matches(sink, observed):
            raise DiagnosticOutputError
        try:
            os.stat(filename, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise DiagnosticOutputError

        flags = (
            os.O_RDWR
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        file_descriptor = os.open(temporary, flags, 0o600, dir_fd=descriptor)
        temporary_created = True
        try:
            os.fchmod(file_descriptor, 0o600)
            opened = os.fstat(file_descriptor)
            temporary_identity = (opened.st_dev, opened.st_ino)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or stat.S_IMODE(opened.st_mode) != 0o600
            ):
                raise DiagnosticOutputError
            view = memoryview(raw)
            while view:
                remaining_seconds(1.0)
                written = os.write(file_descriptor, view)
                if type(written) is not int or written <= 0 or written > len(view):
                    raise DiagnosticOutputError
                view = view[written:]
            remaining_seconds(1.0)
            os.fsync(file_descriptor)
            remaining_seconds(1.0)
            os.link(
                temporary,
                filename,
                src_dir_fd=descriptor,
                dst_dir_fd=descriptor,
                follow_symlinks=False,
            )
            linked = os.stat(
                filename,
                dir_fd=descriptor,
                follow_symlinks=False,
            )
            opened = os.fstat(file_descriptor)
            remaining_seconds(1.0)
            observed_raw = os.pread(file_descriptor, len(raw) + 1, 0)
            if (
                temporary_identity is None
                or (linked.st_dev, linked.st_ino) != temporary_identity
                or (opened.st_dev, opened.st_ino) != temporary_identity
                or not stat.S_ISREG(linked.st_mode)
                or stat.S_IMODE(linked.st_mode) != 0o600
                or linked.st_size != len(raw)
                or opened.st_size != len(raw)
                or observed_raw != raw
            ):
                raise DiagnosticOutputError
            remaining_seconds(1.0)
            os.fsync(descriptor)
            remaining_seconds(1.0)
            removed = _unlink_if_owned(
                descriptor,
                temporary,
                expected_identity=temporary_identity,
            )
            temporary_created = False
            if not removed:
                raise DiagnosticOutputError
            remaining_seconds(1.0)
            os.fsync(descriptor)
            return sink.path / filename
        finally:
            os.close(file_descriptor)
    finally:
        if temporary_created and temporary_identity is not None:
            try:
                _unlink_if_owned(
                    descriptor,
                    temporary,
                    expected_identity=temporary_identity,
                )
            except OSError:
                pass
        os.close(descriptor)


def publish_result_diagnostic(
    sink: DiagnosticSink,
    error: EvaluationError,
    *,
    remaining_seconds: Callable[[float], float],
) -> Path:
    try:
        return _publish_diagnostic(
            sink,
            error,
            filename=RESULT_DIAGNOSTIC_FILENAME,
            remaining_seconds=remaining_seconds,
        )
    except DiagnosticOutputError:
        raise
    except Exception as exc:
        raise DiagnosticOutputError from exc


def publish_run_failure_diagnostic(
    sink: DiagnosticSink,
    error: EvaluationError,
    *,
    remaining_seconds: Callable[[float], float],
) -> Path:
    try:
        return _publish_diagnostic(
            sink,
            error,
            filename=RUN_FAILURE_DIAGNOSTIC_FILENAME,
            remaining_seconds=remaining_seconds,
        )
    except DiagnosticOutputError:
        raise
    except Exception as exc:
        raise DiagnosticOutputError from exc


def publish_call_budget_diagnostic(
    sink: DiagnosticSink,
    error: EvaluationError,
    limiter: CallBudgetLimiter,
    *,
    remaining_seconds: Callable[[float], float],
) -> Path:
    try:
        return _publish_diagnostic(
            sink,
            error,
            filename=CALL_BUDGET_DIAGNOSTIC_FILENAME,
            remaining_seconds=remaining_seconds,
            limiter=limiter,
        )
    except DiagnosticOutputError:
        raise
    except Exception as exc:
        raise DiagnosticOutputError from exc
