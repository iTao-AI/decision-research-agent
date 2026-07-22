"""Bounded source, credential, subprocess, and Compose lifecycle controls."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from types import MappingProxyType
from typing import Callable, Iterator, Mapping, Sequence
from urllib.parse import urlsplit

from scripts.bounded_live_producer_contracts import (
    CleanupStatus,
    EvaluationError,
    FailureCode,
    FailurePhase,
)


_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
_VERSION_RE = re.compile(r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){2}\Z", re.ASCII)
_PROJECT_RE = re.compile(r"dra-proof-[0-9a-f]{32}\Z", re.ASCII)
_DOCKER_FULL_ID_RE = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_PUBLIC_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_PUBLIC_DNS_RE = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?\Z",
    re.ASCII,
)
_CURRENCY_RE = re.compile(r"[A-Z]{3}\Z", re.ASCII)
_ENV_KEY_RE = re.compile(r"[A-Z][A-Z0-9_]*\Z", re.ASCII)
_MAX_ENV_BYTES = 64 * 1024
_DEFAULT_ARCHIVE_BYTES_MAX = 64 * 1024 * 1024
_DEFAULT_ARCHIVE_MEMBERS_MAX = 4096
_DEFAULT_ARCHIVE_MEMBER_BYTES_MAX = 16 * 1024 * 1024
_DEFAULT_STREAM_BYTES_MAX = 1024 * 1024
LIMITER_DIAGNOSTICS_ENV = (
    "DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_LIMITER_DIAGNOSTICS"
)

_LIVE_ENV_NAMES = frozenset(
    {
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "LLM_MODEL",
        "LLM_FALLBACK_MODEL",
        "API_SECRET",
        "TAVILY_API_KEY",
        "MYSQL_ROOT_PASSWORD",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
        "MYSQL_DATABASE",
        "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES",
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL",
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION",
        LIMITER_DIAGNOSTICS_ENV,
        "LANGSMITH_TRACING",
        "LANGSMITH_API_KEY",
        "LANGSMITH_HIDE_INPUTS",
        "LANGSMITH_HIDE_OUTPUTS",
        "RAGFLOW_API_KEY",
        "TOKEN_PRICING_JSON",
        "TOKEN_PRICING_BASIS",
        "TOKEN_PRICING_CURRENCY",
    }
)
_REQUIRED_NONEMPTY_ENV = frozenset(
    {
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "LLM_MODEL",
        "LLM_FALLBACK_MODEL",
        "API_SECRET",
        "TAVILY_API_KEY",
        "MYSQL_ROOT_PASSWORD",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
        "MYSQL_DATABASE",
    }
)
_FALSE_ENV = frozenset(
    {
        "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES",
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL",
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION",
        "LANGSMITH_TRACING",
    }
)
_TRUE_ENV = frozenset({"LANGSMITH_HIDE_INPUTS", "LANGSMITH_HIDE_OUTPUTS"})
_EMPTY_ENV = frozenset({"LANGSMITH_API_KEY", "RAGFLOW_API_KEY"})
_PRICING_ENV = frozenset(
    {"TOKEN_PRICING_JSON", "TOKEN_PRICING_BASIS", "TOKEN_PRICING_CURRENCY"}
)
_DOCKER_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "TMPDIR",
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DOCKER_CONFIG",
    "DOCKER_CERT_PATH",
    "DOCKER_TLS_VERIFY",
    "XDG_CONFIG_HOME",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "PYTHON_DOTENV_DISABLED",
    "DECISION_RESEARCH_AGENT_BACKEND_HOST_PORT",
    "DECISION_RESEARCH_AGENT_MYSQL_HOST_PORT",
    "DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE",
)
_BACKEND_FIXED_ENV = frozenset(
    {
        "MYSQL_HOST",
        "MYSQL_PORT",
        "DECISION_RESEARCH_AGENT_DB_PATH",
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
    }
)
_SECRET_ENV = frozenset(
    {
        "OPENAI_API_KEY",
        "API_SECRET",
        "TAVILY_API_KEY",
        "MYSQL_ROOT_PASSWORD",
        "MYSQL_PASSWORD",
        "LANGSMITH_API_KEY",
        "RAGFLOW_API_KEY",
        "TOKEN_PRICING_JSON",
    }
)
_PATH_ENV = frozenset(
    {
        "DECISION_RESEARCH_AGENT_DB_PATH",
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
    }
)


@dataclass(frozen=True)
class LifecycleBudget:
    docker_probe_seconds: int
    active_seconds: int
    build_start_seconds: int
    research_seconds: int
    restart_replay_seconds: int
    cleanup_seconds: int
    total_wall_seconds: int

    def __post_init__(self) -> None:
        values = tuple(self.__dict__.values())
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("lifecycle_budget_invalid")
        if self.total_wall_seconds != (
            self.docker_probe_seconds + self.active_seconds + self.cleanup_seconds
        ):
            raise ValueError("lifecycle_budget_invalid")
        if any(
            bound > self.active_seconds
            for bound in (
                self.build_start_seconds,
                self.research_seconds,
                self.restart_replay_seconds,
            )
        ):
            raise ValueError("lifecycle_budget_invalid")


LIVE_BUDGET = LifecycleBudget(30, 3300, 1200, 1800, 300, 120, 3450)


class ActiveDeadline:
    """One monotonic deadline that can only be narrowed, never refreshed."""

    def __init__(
        self,
        seconds: float,
        *,
        code: FailureCode,
        phase: FailurePhase,
        monotonic: Callable[[], float] = time.monotonic,
        _absolute: float | None = None,
    ) -> None:
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or seconds <= 0:
            raise ValueError("deadline_invalid")
        self._monotonic = monotonic
        now = monotonic()
        candidate = now + float(seconds)
        self._deadline = min(candidate, _absolute) if _absolute is not None else candidate
        self.code = FailureCode(code)
        self.phase = FailurePhase(phase)

    def remaining(self, requested: float) -> float:
        if not isinstance(requested, (int, float)) or isinstance(requested, bool) or requested <= 0:
            raise ValueError("deadline_invalid")
        value = self._deadline - self._monotonic()
        if value <= 0:
            raise EvaluationError(self.code, self.phase, False)
        return min(float(requested), value)

    def child(
        self,
        seconds: float,
        *,
        code: FailureCode,
        phase: FailurePhase,
    ) -> "ActiveDeadline":
        return ActiveDeadline(
            seconds,
            code=code,
            phase=phase,
            monotonic=self._monotonic,
            _absolute=self._deadline,
        )


@dataclass(frozen=True)
class SourceSnapshot:
    root: Path
    archive_path: Path
    commit: str
    tree: str
    version: str
    archive_sha256: str
    members: tuple[str, ...]
    secure_runtime_checked: bool


def _public_provider_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.port not in {None, 443}
            or parsed.path not in {"", "/v1"}
        ):
            return False
    except ValueError:
        return False
    host = parsed.hostname.lower().rstrip(".")
    if not host.isascii():
        return False
    if host.endswith((".local", ".internal", ".localhost")) or host in {
        "local",
        "internal",
        "localhost",
    }:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        try:
            socket.inet_aton(host)
        except OSError:
            return _PUBLIC_DNS_RE.fullmatch(host) is not None
        return False
    return address.is_global


@dataclass(frozen=True)
class CredentialDeclaration:
    provider_id: str
    provider_base_url: str
    primary_model: str
    fallback_model: str
    pricing_basis: str | None = None
    pricing_currency: str | None = None

    def __post_init__(self) -> None:
        identifiers = (self.provider_id, self.primary_model, self.fallback_model)
        if any(type(value) is not str or not _PUBLIC_ID_RE.fullmatch(value) for value in identifiers):
            raise ValueError("credential_declaration_invalid")
        if not _public_provider_url(self.provider_base_url):
            raise ValueError("credential_declaration_invalid")
        if (self.pricing_basis is None) != (self.pricing_currency is None):
            raise ValueError("credential_declaration_invalid")
        if self.pricing_basis is not None and (
            not _PUBLIC_ID_RE.fullmatch(self.pricing_basis)
            or not _CURRENCY_RE.fullmatch(self.pricing_currency or "")
        ):
            raise ValueError("credential_declaration_invalid")


def _evaluation_error(code: FailureCode, phase: FailurePhase) -> EvaluationError:
    return EvaluationError(code, phase, False)


def _git_output(root: Path, *arguments: str, timeout: float = 30.0) -> str:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "TMPDIR", "SYSTEMROOT"}
    }
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _evaluation_error(
            FailureCode.SOURCE_IDENTITY_INVALID, FailurePhase.INPUT
        ) from exc
    return result.stdout.rstrip("\n")


def _safe_archive_name(name: str) -> bool:
    if not name or "\x00" in name or "\\" in name or name.startswith("/"):
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def _validate_and_extract_archive(
    archive_path: Path,
    destination: Path,
    *,
    expected_members: Sequence[str],
    archive_bytes_max: int,
    archive_members_max: int,
    archive_member_bytes_max: int,
) -> tuple[str, ...]:
    try:
        before = archive_path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > archive_bytes_max:
            raise ValueError
        expected = tuple(expected_members)
        if (
            len(expected) > archive_members_max
            or len(expected) != len(set(expected))
            or any(not _safe_archive_name(name) for name in expected)
        ):
            raise ValueError
        if destination.exists():
            raise ValueError
        destination.mkdir(parents=False)
        extracted_files: list[str] = []
        seen_casefolded: set[str] = set()
        member_count = 0
        total_size = 0
        with tarfile.open(archive_path, mode="r:") as archive:
            for member in archive:
                member_count += 1
                if member_count > archive_members_max or not _safe_archive_name(member.name):
                    raise ValueError
                folded = member.name.casefold().rstrip("/")
                if folded in seen_casefolded:
                    raise ValueError
                seen_casefolded.add(folded)
                if member.pax_headers and any(
                    key.lower().startswith("gnu.sparse") for key in member.pax_headers
                ):
                    raise ValueError
                target = destination.joinpath(*PurePosixPath(member.name).parts)
                resolved_parent = target.parent.resolve()
                if destination.resolve() not in (resolved_parent, *resolved_parent.parents):
                    raise ValueError
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=False)
                    continue
                if not member.isreg() or member.size < 0 or member.size > archive_member_bytes_max:
                    raise ValueError
                total_size += member.size
                if total_size > archive_bytes_max:
                    raise ValueError
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError
                with target.open("xb") as output:
                    remaining = member.size
                    while remaining:
                        chunk = stream.read(min(64 * 1024, remaining))
                        if not chunk:
                            raise ValueError
                        output.write(chunk)
                        remaining -= len(chunk)
                    if stream.read(1):
                        raise ValueError
                target.chmod(member.mode & 0o755)
                extracted_files.append(member.name)
        if tuple(extracted_files) != expected:
            raise ValueError
        return tuple(extracted_files)
    except EvaluationError:
        raise
    except (OSError, tarfile.TarError, ValueError) as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise _evaluation_error(
            FailureCode.SOURCE_ARCHIVE_INVALID, FailurePhase.DOCKER
        ) from exc


def prepare_source_snapshot(
    checkout_root: Path,
    task_temp_parent: Path,
    *,
    required_paths: Sequence[str],
    deadline: ActiveDeadline | None = None,
    archive_bytes_max: int = _DEFAULT_ARCHIVE_BYTES_MAX,
    archive_members_max: int = _DEFAULT_ARCHIVE_MEMBERS_MAX,
    archive_member_bytes_max: int = _DEFAULT_ARCHIVE_MEMBER_BYTES_MAX,
    verify_secure_runtime: bool = True,
) -> SourceSnapshot:
    root = checkout_root.resolve()

    def remaining(requested: float) -> float:
        return deadline.remaining(requested) if deadline is not None else requested

    def git_output(*arguments: str) -> str:
        return _git_output(root, *arguments, timeout=remaining(30.0))

    try:
        remaining(1.0)
        if type(verify_secure_runtime) is not bool:
            raise ValueError
        commit = git_output("rev-parse", "--verify", "HEAD")
        tree = git_output("rev-parse", "--verify", f"{commit}^{{tree}}")
        if not _COMMIT_RE.fullmatch(commit) or not _COMMIT_RE.fullmatch(tree):
            raise ValueError
        if git_output("status", "--porcelain=v1", "--untracked-files=all"):
            raise _evaluation_error(FailureCode.SOURCE_DIRTY, FailurePhase.INPUT)
        tracked = tuple(
            git_output("ls-tree", "-r", "--name-only", commit).splitlines()
        )
        if not tracked or any(path not in tracked for path in required_paths):
            raise ValueError
        if (
            git_output("rev-parse", "--verify", "HEAD") != commit
            or git_output("status", "--porcelain=v1", "--untracked-files=all")
        ):
            raise _evaluation_error(
                FailureCode.SOURCE_IDENTITY_INVALID,
                FailurePhase.INPUT,
            )
        remaining(1.0)
    except EvaluationError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise _evaluation_error(
            FailureCode.SOURCE_IDENTITY_INVALID, FailurePhase.INPUT
        ) from exc

    try:
        task_temp_parent.mkdir(parents=True, exist_ok=False)
        task_root = Path(tempfile.mkdtemp(prefix="snapshot-", dir=task_temp_parent))
        archive_path = task_root / "source.tar"
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "HOME", "TMPDIR", "SYSTEMROOT"}
        }
        subprocess.run(
            ["git", "archive", "--format=tar", f"--output={archive_path}", commit],
            cwd=root,
            env=environment,
            check=True,
            capture_output=True,
            timeout=remaining(30.0),
        )
        snapshot_root = task_root / "snapshot"
        members = _validate_and_extract_archive(
            archive_path,
            snapshot_root,
            expected_members=tracked,
            archive_bytes_max=archive_bytes_max,
            archive_members_max=archive_members_max,
            archive_member_bytes_max=archive_member_bytes_max,
        )
        remaining(1.0)
        if any(not (snapshot_root / path).is_file() for path in required_paths):
            raise ValueError
        version_bytes = (snapshot_root / "VERSION").read_bytes()
        if not version_bytes.endswith(b"\n") or version_bytes.count(b"\n") != 1:
            raise ValueError
        version = version_bytes[:-1].decode("ascii")
        if not _VERSION_RE.fullmatch(version):
            raise ValueError
        if verify_secure_runtime:
            secure_check = subprocess.run(
                [sys.executable, "scripts/secure_local_runtime_proof.py", "check"],
                cwd=snapshot_root,
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "PYTHON_DOTENV_DISABLED": "1",
                },
                check=False,
                capture_output=True,
                timeout=remaining(30.0),
            )
            if secure_check.returncode != 0:
                raise ValueError
        archive_sha256 = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        remaining(1.0)
        if (
            git_output("rev-parse", "--verify", "HEAD") != commit
            or git_output("status", "--porcelain=v1", "--untracked-files=all")
        ):
            raise _evaluation_error(
                FailureCode.SOURCE_IDENTITY_INVALID,
                FailurePhase.INPUT,
            )
    except EvaluationError:
        shutil.rmtree(task_temp_parent, ignore_errors=True)
        raise
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        shutil.rmtree(task_temp_parent, ignore_errors=True)
        raise _evaluation_error(
            FailureCode.SOURCE_ARCHIVE_INVALID, FailurePhase.DOCKER
        ) from exc
    return SourceSnapshot(
        root=snapshot_root,
        archive_path=archive_path,
        commit=commit,
        tree=tree,
        version=version,
        archive_sha256=archive_sha256,
        members=members,
        secure_runtime_checked=verify_secure_runtime,
    )


@dataclass(eq=False)
class _CredentialSnapshot:
    parent_path: Path
    directory_path: Path
    parent_fd: int
    directory_fd: int
    directory_identity: os.stat_result
    reader_fd: int = -1
    source_identity: os.stat_result | None = None


class LiveConfiguration:
    """Validated values materialized only for one exact Compose invocation."""

    def __init__(
        self,
        values: Mapping[str, str],
        raw: bytes,
        *,
        repository_root: Path,
    ) -> None:
        self._value_store = dict(values)
        self._values = MappingProxyType(self._value_store)
        self._raw = bytearray(raw)
        self._repository_root = repository_root.resolve()
        self._active_snapshots: set[_CredentialSnapshot] = set()
        self._closed = False

    def __getitem__(self, key: str) -> str:
        return self._values[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._values.get(key, default)

    @staticmethod
    def _clear_directory_fd(
        directory_fd: int,
        *,
        remaining_entries: list[int],
        depth: int = 0,
    ) -> None:
        if depth > 8:
            raise OSError("credential_cleanup_depth_invalid")
        names = os.listdir(directory_fd)
        remaining_entries[0] -= len(names)
        if remaining_entries[0] < 0:
            raise OSError("credential_cleanup_entries_invalid")
        for name in names:
            metadata = os.stat(
                name,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
            if stat.S_ISDIR(metadata.st_mode):
                child_fd = os.open(
                    name,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_fd,
                )
                try:
                    LiveConfiguration._clear_directory_fd(
                        child_fd,
                        remaining_entries=remaining_entries,
                        depth=depth + 1,
                    )
                finally:
                    os.close(child_fd)
                os.rmdir(name, dir_fd=directory_fd)
            else:
                os.unlink(name, dir_fd=directory_fd)

    def _cleanup_snapshot(self, snapshot: _CredentialSnapshot) -> None:
        directory_cleared = False
        try:
            self._clear_directory_fd(
                snapshot.directory_fd,
                remaining_entries=[256],
            )
            directory_cleared = True
        finally:
            if directory_cleared and snapshot.reader_fd >= 0:
                reader_fd = snapshot.reader_fd
                snapshot.reader_fd = -1
                os.close(reader_fd)
        matching_names: list[str] = []
        for name in os.listdir(snapshot.parent_fd):
            try:
                metadata = os.stat(
                    name,
                    dir_fd=snapshot.parent_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                continue
            if (
                stat.S_ISDIR(metadata.st_mode)
                and (metadata.st_dev, metadata.st_ino)
                == (
                    snapshot.directory_identity.st_dev,
                    snapshot.directory_identity.st_ino,
                )
            ):
                matching_names.append(name)
        if len(matching_names) != 1:
            raise OSError("credential_directory_identity_invalid")
        directory_name = matching_names[0]
        original_name = snapshot.directory_path.name
        if original_name != directory_name:
            try:
                replacement = os.stat(
                    original_name,
                    dir_fd=snapshot.parent_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                pass
            else:
                if stat.S_ISDIR(replacement.st_mode):
                    raise OSError("credential_directory_replacement_invalid")
                os.unlink(original_name, dir_fd=snapshot.parent_fd)
        os.rmdir(directory_name, dir_fd=snapshot.parent_fd)
        os.close(snapshot.directory_fd)
        snapshot.directory_fd = -1
        os.close(snapshot.parent_fd)
        snapshot.parent_fd = -1
        self._active_snapshots.discard(snapshot)

    @contextmanager
    def materialized(
        self,
        *,
        forbidden_roots: Sequence[Path] = (),
    ) -> Iterator[Path]:
        if self._closed:
            raise _evaluation_error(
                FailureCode.CREDENTIAL_SOURCE_INVALID,
                FailurePhase.INPUT,
            )
        raw = bytes(self._raw)
        writer_fd = -1
        parent_fd = -1
        directory_fd = -1
        directory_path: Path | None = None
        snapshot: _CredentialSnapshot | None = None
        primary_error: BaseException | None = None
        secondary_error: BaseException | None = None
        validation_failed = False
        try:
            parent_path = Path(tempfile.gettempdir()).resolve()
            parent_fd = os.open(
                parent_path,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            directory_path = Path(
                tempfile.mkdtemp(
                    prefix="dra-bounded-credential-",
                    dir=parent_path,
                )
            ).resolve()
            for root in (self._repository_root, *forbidden_roots):
                try:
                    directory_path.relative_to(root.resolve())
                except ValueError:
                    continue
                raise OSError("credential_directory_scope_invalid")
            os.chmod(directory_path, 0o700)
            directory_fd = os.open(
                directory_path,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            directory_identity = os.fstat(directory_fd)
            if (
                not stat.S_ISDIR(directory_identity.st_mode)
                or stat.S_IMODE(directory_identity.st_mode) != 0o700
                or directory_identity.st_nlink < 1
            ):
                raise OSError("credential_directory_identity_invalid")
            snapshot = _CredentialSnapshot(
                parent_path=parent_path,
                directory_path=directory_path,
                parent_fd=parent_fd,
                directory_fd=directory_fd,
                directory_identity=directory_identity,
            )
            self._active_snapshots.add(snapshot)
            parent_fd = -1
            directory_fd = -1
            writer_fd = os.open(
                "live.env",
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=snapshot.directory_fd,
            )
            view = memoryview(raw)
            written = 0
            while written < len(view):
                written += os.write(writer_fd, view[written:])
            os.fsync(writer_fd)
            os.fchmod(writer_fd, 0o400)
            source = os.fstat(writer_fd)
            os.close(writer_fd)
            writer_fd = -1
            snapshot.reader_fd = os.open(
                "live.env",
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=snapshot.directory_fd,
            )
            snapshot.source_identity = os.fstat(snapshot.reader_fd)
            directory_path_identity = os.stat(
                snapshot.directory_path.name,
                dir_fd=snapshot.parent_fd,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISDIR(directory_path_identity.st_mode)
                or (directory_path_identity.st_dev, directory_path_identity.st_ino)
                != (
                    snapshot.directory_identity.st_dev,
                    snapshot.directory_identity.st_ino,
                )
                or not stat.S_ISREG(source.st_mode)
                or stat.S_IMODE(source.st_mode) != 0o400
                or source.st_nlink != 1
                or source.st_size != len(raw)
                or (source.st_dev, source.st_ino, source.st_size)
                != (
                    snapshot.source_identity.st_dev,
                    snapshot.source_identity.st_ino,
                    snapshot.source_identity.st_size,
                )
            ):
                raise OSError("credential_snapshot_invalid")
            try:
                yield directory_path / "live.env"
            except BaseException as exc:
                primary_error = exc
            try:
                directory_after = os.fstat(snapshot.directory_fd)
                directory_path_after = os.stat(
                    snapshot.directory_path.name,
                    dir_fd=snapshot.parent_fd,
                    follow_symlinks=False,
                )
                path_after = os.stat(
                    "live.env",
                    dir_fd=snapshot.directory_fd,
                    follow_symlinks=False,
                )
                source_after = os.fstat(snapshot.reader_fd)
                os.lseek(snapshot.reader_fd, 0, os.SEEK_SET)
                captured = os.read(snapshot.reader_fd, _MAX_ENV_BYTES + 1)
                trailing = os.read(snapshot.reader_fd, 1)
                if (
                    stat.S_IMODE(directory_after.st_mode) != 0o700
                    or (directory_after.st_dev, directory_after.st_ino)
                    != (
                        snapshot.directory_identity.st_dev,
                        snapshot.directory_identity.st_ino,
                    )
                    or not stat.S_ISDIR(directory_path_after.st_mode)
                    or (
                        directory_path_after.st_dev,
                        directory_path_after.st_ino,
                    )
                    != (
                        snapshot.directory_identity.st_dev,
                        snapshot.directory_identity.st_ino,
                    )
                    or not stat.S_ISREG(path_after.st_mode)
                    or stat.S_IMODE(path_after.st_mode) != 0o400
                    or path_after.st_nlink != 1
                    or (path_after.st_dev, path_after.st_ino, path_after.st_size)
                    != (
                        snapshot.source_identity.st_dev,
                        snapshot.source_identity.st_ino,
                        snapshot.source_identity.st_size,
                    )
                    or (source_after.st_dev, source_after.st_ino, source_after.st_size)
                    != (
                        snapshot.source_identity.st_dev,
                        snapshot.source_identity.st_ino,
                        snapshot.source_identity.st_size,
                    )
                    or source_after.st_nlink != 1
                    or trailing
                    or captured != raw
                ):
                    validation_failed = True
            except BaseException as exc:
                validation_failed = True
                secondary_error = exc
        except BaseException as exc:
            validation_failed = True
            secondary_error = exc
        finally:
            if writer_fd >= 0:
                try:
                    os.close(writer_fd)
                except BaseException as exc:
                    secondary_error = secondary_error or exc
                    validation_failed = True
            if snapshot is not None:
                try:
                    self._cleanup_snapshot(snapshot)
                except BaseException as exc:
                    secondary_error = secondary_error or exc
                    validation_failed = True
            else:
                if directory_fd >= 0:
                    try:
                        os.close(directory_fd)
                    except BaseException as exc:
                        secondary_error = secondary_error or exc
                        validation_failed = True
                if parent_fd >= 0:
                    try:
                        os.close(parent_fd)
                    except BaseException as exc:
                        secondary_error = secondary_error or exc
                        validation_failed = True
                if directory_path is not None:
                    try:
                        shutil.rmtree(directory_path)
                    except BaseException as exc:
                        secondary_error = secondary_error or exc
                        validation_failed = True
        materialization_error = _evaluation_error(
            FailureCode.CREDENTIAL_SOURCE_INVALID,
            FailurePhase.INPUT,
        )
        if primary_error is not None and validation_failed:
            raise BaseExceptionGroup(
                "credential invocation and snapshot validation failed",
                [primary_error, materialization_error],
            ) from secondary_error
        if primary_error is not None:
            raise primary_error
        if validation_failed:
            raise materialization_error from secondary_error

    def close(self) -> None:
        if self._closed:
            return
        cleanup_error: BaseException | None = None
        for snapshot in tuple(self._active_snapshots):
            try:
                self._cleanup_snapshot(snapshot)
            except BaseException as exc:
                cleanup_error = cleanup_error or exc
        if self._active_snapshots:
            raise _evaluation_error(
                FailureCode.CREDENTIAL_SOURCE_INVALID,
                FailurePhase.INPUT,
            ) from cleanup_error
        for index in range(len(self._raw)):
            self._raw[index] = 0
        self._value_store.clear()
        self._closed = True

    def __del__(self) -> None:
        try:
            self.close()
        except (AttributeError, EvaluationError, OSError):
            pass


def _read_env_file(path: Path) -> tuple[dict[str, str], bytes]:
    descriptor = -1
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) not in {0o400, 0o600}
            or before.st_size > _MAX_ENV_BYTES
        ):
            raise ValueError
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise ValueError
        raw = os.read(descriptor, _MAX_ENV_BYTES + 1)
        if len(raw) > _MAX_ENV_BYTES or os.read(descriptor, 1):
            raise ValueError
        after = path.lstat()
        if (after.st_dev, after.st_ino, after.st_size, after.st_nlink) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            1,
        ):
            raise ValueError
        text = raw.decode("utf-8")
        values: dict[str, str] = {}
        for raw_line in text.splitlines():
            if not raw_line or raw_line.startswith("#"):
                continue
            if "=" not in raw_line:
                raise ValueError
            key, value = raw_line.split("=", 1)
            if not _ENV_KEY_RE.fullmatch(key) or key in values:
                raise ValueError
            values[key] = value
        return values, raw
    except (OSError, UnicodeError, ValueError) as exc:
        raise _evaluation_error(
            FailureCode.CREDENTIAL_SOURCE_INVALID, FailurePhase.INPUT
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _git_common_directory(root: Path) -> Path | None:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "TMPDIR", "SYSTEMROOT"}
    }
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    if result.returncode != 0 or not value:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def _validate_pricing(values: Mapping[str, str], declaration: CredentialDeclaration) -> None:
    present = {key for key in _PRICING_ENV if key in values}
    if present and present != _PRICING_ENV:
        raise ValueError
    if not present:
        if declaration.pricing_basis is not None:
            raise ValueError
        return
    if (
        values["TOKEN_PRICING_BASIS"] != declaration.pricing_basis
        or values["TOKEN_PRICING_CURRENCY"] != declaration.pricing_currency
    ):
        raise ValueError
    raw = values["TOKEN_PRICING_JSON"]
    payload = json.loads(raw)
    if type(payload) is not dict or not payload:
        raise ValueError
    if json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) != raw:
        raise ValueError
    if not {declaration.primary_model, declaration.fallback_model}.issubset(payload):
        raise ValueError
    for key, value in payload.items():
        if (
            type(key) is not str
            or not _PUBLIC_ID_RE.fullmatch(key)
            or type(value) is not dict
            or set(value) != {"prompt", "completion"}
        ):
            raise ValueError
        if any(
            type(amount) not in {int, float}
            or not math.isfinite(amount)
            or amount < 0
            for amount in value.values()
        ):
            raise ValueError


def load_live_configuration(
    env_file: Path,
    declaration: CredentialDeclaration,
    *,
    process_api_key: str,
    repository_root: Path,
) -> LiveConfiguration:
    raw = b""
    try:
        credential_path = env_file.resolve(strict=True)
        repository_path = repository_root.resolve()
        try:
            credential_path.relative_to(repository_path)
        except ValueError:
            pass
        else:
            raise ValueError
        repository_common = _git_common_directory(repository_path)
        credential_common = _git_common_directory(credential_path.parent)
        if repository_common is not None and credential_common == repository_common:
            raise ValueError
        values, raw = _read_env_file(env_file)
        if not set(values).issubset(_LIVE_ENV_NAMES):
            raise ValueError
        if any(not values.get(key) for key in _REQUIRED_NONEMPTY_ENV):
            raise ValueError
        if any(values.get(key) != "false" for key in _FALSE_ENV):
            raise ValueError
        if any(values.get(key) != "true" for key in _TRUE_ENV):
            raise ValueError
        if any(values.get(key) != "" for key in _EMPTY_ENV):
            raise ValueError
        if (
            LIMITER_DIAGNOSTICS_ENV in values
            and values[LIMITER_DIAGNOSTICS_ENV] != "true"
        ):
            raise ValueError
        if not process_api_key or values["API_SECRET"] != process_api_key:
            raise ValueError
        if (
            values["OPENAI_BASE_URL"] != declaration.provider_base_url
            or values["LLM_MODEL"] != declaration.primary_model
            or values["LLM_FALLBACK_MODEL"] != declaration.fallback_model
        ):
            raise ValueError
        _validate_pricing(values, declaration)
    except EvaluationError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise _evaluation_error(
            FailureCode.CREDENTIAL_SOURCE_INVALID, FailurePhase.INPUT
        ) from exc
    try:
        return LiveConfiguration(
            values,
            raw,
            repository_root=repository_path,
        )
    except OSError as exc:
        raise _evaluation_error(
            FailureCode.CREDENTIAL_SOURCE_INVALID, FailurePhase.INPUT
        ) from exc


def _compose_error() -> EvaluationError:
    return _evaluation_error(FailureCode.COMPOSE_CONFIG_INVALID, FailurePhase.DOCKER)


def _sanitize_port(value: object, target: int) -> dict[str, object]:
    if type(value) is not dict or set(value) - {"target", "published", "host_ip", "protocol", "mode"}:
        raise ValueError
    try:
        published = int(value.get("published", -1))
    except (TypeError, ValueError) as exc:
        raise ValueError from exc
    if (
        value.get("target") != target
        or published != 0
        or value.get("host_ip") != "127.0.0.1"
        or value.get("protocol", "tcp") != "tcp"
        or value.get("mode", "ingress") not in {"ingress", None}
    ):
        raise ValueError
    return {"target": target, "published": 0, "host_ip": "127.0.0.1", "protocol": "tcp"}


def _sanitize_volumes(
    value: object,
    expected_targets: Sequence[str],
    expected_sources: Sequence[str],
) -> list[dict[str, str]]:
    if type(value) is not list or len(value) != len(expected_targets):
        raise ValueError
    output: list[dict[str, str]] = []
    for role, (item, target, source) in enumerate(
        zip(value, expected_targets, expected_sources, strict=True)
    ):
        if (
            type(item) is not dict
            or item.get("type") != "volume"
            or item.get("source") != source
            or item.get("target") != target
        ):
            raise ValueError
        if set(item) - {"type", "source", "target", "read_only", "volume"}:
            raise ValueError
        if item.get("read_only") not in (None, False) or item.get("volume") not in (
            None,
            {},
        ):
            raise ValueError
        output.append({"type": "volume", "source": f"<task-volume:{role}>", "target": target})
    return output


def sanitize_compose_projection(
    payload: object,
    *,
    fixture_mode: bool = False,
) -> dict[str, object]:
    """Validate the approved resolved Compose shape and return a secret-free projection."""
    try:
        if type(fixture_mode) is not bool:
            raise ValueError
        if type(payload) is not dict or set(payload) - {"name", "services", "volumes", "networks"}:
            raise ValueError
        project_name = payload.get("name")
        if type(project_name) is not str or not _PROJECT_RE.fullmatch(project_name):
            raise ValueError
        services = payload.get("services")
        if type(services) is not dict or set(services) != {"backend", "mysql"}:
            raise ValueError
        sanitized_services: dict[str, object] = {}
        specifications = {
            "backend": (
                8000,
                ("/app/data", "/app/output"),
                {
                    "build",
                    "ports",
                    "env_file",
                    "environment",
                    "volumes",
                    "depends_on",
                    "cap_drop",
                    "security_opt",
                    "networks",
                    "command",
                    "entrypoint",
                },
            ),
            "mysql": (
                3306,
                ("/var/lib/mysql",),
                {
                    "image",
                    "ports",
                    "environment",
                    "healthcheck",
                    "volumes",
                    "networks",
                    "command",
                    "entrypoint",
                },
            ),
        }
        for service_name, (port, volume_targets, allowed_keys) in specifications.items():
            service = services[service_name]
            if type(service) is not dict or set(service) - allowed_keys:
                raise ValueError
            ports = service.get("ports")
            if type(ports) is not list or len(ports) != 1:
                raise ValueError
            environment = service.get("environment")
            if type(environment) is not dict:
                raise ValueError
            allowed_environment = _LIVE_ENV_NAMES | _BACKEND_FIXED_ENV
            if service_name == "backend" and fixture_mode:
                allowed_environment = allowed_environment | {
                    "DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_FIXTURE"
                }
            if set(environment) - allowed_environment:
                raise ValueError
            safe_environment: dict[str, str] = {}
            for key in sorted(environment):
                value = environment[key]
                if type(value) not in {str, type(None)}:
                    raise ValueError
                if key in _SECRET_ENV:
                    safe_environment[key] = "<secret>"
                elif key in _PATH_ENV:
                    safe_environment[key] = "<container-path>"
                elif key == "DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_FIXTURE":
                    if value != "true":
                        raise ValueError
                    safe_environment[key] = "<fixture-gate>"
                else:
                    safe_environment[key] = "" if value is None else value
            safe_service: dict[str, object] = {
                "ports": [_sanitize_port(ports[0], port)],
                "environment": safe_environment,
                "volumes": _sanitize_volumes(
                    service.get("volumes"),
                    volume_targets,
                    (
                        ("backend_data", "backend_output")
                        if service_name == "backend"
                        else ("mysql_data",)
                    ),
                ),
                "networks": ["app-network"],
            }
            networks = service.get("networks")
            if not (
                networks == ["app-network"]
                or (
                    type(networks) is dict
                    and set(networks) == {"app-network"}
                    and networks["app-network"] in (None, {})
                )
            ):
                raise ValueError
            if service.get("entrypoint") is not None:
                raise ValueError
            if service_name == "backend":
                expected_command = [
                    "python",
                    "scripts/bounded_live_producer_container_fixture.py",
                    "serve",
                ]
                if fixture_mode:
                    if service.get("command") != expected_command:
                        raise ValueError
                    safe_service["command"] = "<fixture-command>"
                elif service.get("command") is not None:
                    raise ValueError
                build = service.get("build")
                if type(build) is not dict or set(build) != {"context", "dockerfile"}:
                    raise ValueError
                if build.get("dockerfile") != "Dockerfile.backend":
                    raise ValueError
                safe_service["build"] = {
                    "context": "<tracked-snapshot>",
                    "dockerfile": "Dockerfile.backend",
                }
                if "env_file" in service:
                    env_files = service["env_file"]
                    if (
                        type(env_files) is not list
                        or len(env_files) != 1
                        or type(env_files[0]) is not str
                        or not env_files[0]
                    ):
                        raise ValueError
                safe_service["env_file"] = ["<credential-source>"]
                if service.get("cap_drop") != ["ALL"] or service.get("security_opt") != [
                    "no-new-privileges:true"
                ]:
                    raise ValueError
                safe_service["cap_drop"] = ["ALL"]
                safe_service["security_opt"] = ["no-new-privileges:true"]
                depends_on = service.get("depends_on")
                if depends_on not in (
                    {"mysql": {"condition": "service_healthy", "required": True}},
                    {"mysql": {"condition": "service_healthy"}},
                ):
                    raise ValueError
                safe_service["depends_on"] = {"mysql": "service_healthy"}
            else:
                if service.get("command") is not None:
                    raise ValueError
                if service.get("image") != "mysql:8.0":
                    raise ValueError
                healthcheck = service.get("healthcheck")
                if healthcheck != {
                    "test": [
                        "CMD-SHELL",
                        'mysqladmin ping -h 127.0.0.1 -uroot -p"$${MYSQL_ROOT_PASSWORD}" --silent',
                    ],
                    "interval": "5s",
                    "timeout": "3s",
                    "retries": 12,
                    "start_period": "20s",
                }:
                    raise ValueError
                safe_service["image"] = "mysql:8.0"
                safe_service["healthcheck"] = "<approved-healthcheck>"
            sanitized_services[service_name] = safe_service
        volumes = payload.get("volumes")
        networks = payload.get("networks")
        if type(volumes) is not dict or set(volumes) != {
            "backend_data",
            "backend_output",
            "mysql_data",
        }:
            raise ValueError
        if type(networks) is not dict or set(networks) != {"app-network"}:
            raise ValueError
        expected_volumes = {
            logical_name: {"name": f"{project_name}_{logical_name}"}
            for logical_name in ("backend_data", "backend_output", "mysql_data")
        }
        if volumes != expected_volumes:
            raise ValueError
        expected_network = {
            "name": f"{project_name}_app-network",
            "driver": "bridge",
            "ipam": {},
        }
        if networks["app-network"] not in (
            {"driver": "bridge"},
            expected_network,
        ):
            raise ValueError
        return {
            "name": "<task-project>",
            "services": sanitized_services,
            "volumes": ["backend_data", "backend_output", "mysql_data"],
            "networks": {"app-network": {"driver": "bridge"}},
        }
    except EvaluationError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise _compose_error() from exc


def run_bounded_subprocess(
    arguments: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    deadline: ActiveDeadline,
    allowed_environment: Sequence[str],
    stream_bytes_max: int = _DEFAULT_STREAM_BYTES_MAX,
    allow_stream_overflow: bool = False,
    pass_fds: Sequence[int] = (),
    allow_nonzero: bool = False,
) -> subprocess.CompletedProcess[str]:
    inherited_descriptors = tuple(pass_fds)
    if (
        not arguments
        or any(type(item) is not str or "\x00" in item for item in arguments)
        or not cwd.is_dir()
        or stream_bytes_max <= 0
        or (allow_stream_overflow and not any(item in {"--quiet", "-q"} for item in arguments))
        or any(type(item) is not int or item < 0 for item in inherited_descriptors)
        or len(set(inherited_descriptors)) != len(inherited_descriptors)
        or (inherited_descriptors and os.name != "posix")
        or type(allow_nonzero) is not bool
    ):
        raise ValueError("subprocess_invocation_invalid")
    allowed = frozenset(allowed_environment)
    process_environment = {key: value for key, value in env.items() if key in allowed}
    process_environment["PYTHON_DOTENV_DISABLED"] = "1"
    window_started = time.monotonic()
    timeout = deadline.remaining(24 * 60 * 60)
    window_ends = window_started + timeout
    teardown_reserve = min(0.25, max(0.01, timeout * 0.05))
    execution_ends = max(window_started, window_ends - teardown_reserve)
    try:
        process = subprocess.Popen(
            list(arguments),
            cwd=cwd,
            env=process_environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name == "posix",
            pass_fds=inherited_descriptors,
        )
    except OSError as exc:
        raise EvaluationError(deadline.code, deadline.phase, False) from exc

    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    overflows = {"stdout": False, "stderr": False}

    def drain(name: str, stream: object) -> None:
        reader = stream
        try:
            while True:
                chunk = reader.read(64 * 1024)  # type: ignore[attr-defined]
                if not chunk:
                    return
                remaining = stream_bytes_max + 1 - len(buffers[name])
                if remaining > 0:
                    buffers[name].extend(chunk[:remaining])
                if len(chunk) > remaining or len(buffers[name]) > stream_bytes_max:
                    overflows[name] = True
        except (OSError, ValueError):
            return

    threads = [
        threading.Thread(target=drain, args=("stdout", process.stdout), daemon=True),
        threading.Thread(target=drain, args=("stderr", process.stderr), daemon=True),
    ]

    def remaining_until(boundary: float) -> float:
        return max(0.0, boundary - time.monotonic())

    def terminate_group() -> None:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
        elif process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass

    def teardown() -> None:
        terminate_group()
        try:
            process.wait(timeout=remaining_until(window_ends))
        except BaseException:
            pass
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except BaseException:
                    pass
        for thread in threads:
            try:
                thread.join(remaining_until(window_ends))
            except BaseException:
                pass

    try:
        for thread in threads:
            thread.start()
        try:
            process.wait(timeout=remaining_until(execution_ends))
        except subprocess.TimeoutExpired as exc:
            raise EvaluationError(deadline.code, deadline.phase, False) from exc
        for thread in threads:
            thread.join(remaining_until(execution_ends))
            if thread.is_alive():
                raise EvaluationError(deadline.code, deadline.phase, False)
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        if any(overflows.values()) and not allow_stream_overflow:
            raise EvaluationError(deadline.code, deadline.phase, False)
        try:
            stdout = bytes(buffers["stdout"][:stream_bytes_max]).decode("utf-8")
            stderr = bytes(buffers["stderr"][:stream_bytes_max]).decode("utf-8")
        except UnicodeError as exc:
            raise EvaluationError(deadline.code, deadline.phase, False) from exc
        result = subprocess.CompletedProcess(
            tuple(arguments), process.returncode, stdout, stderr
        )
        if process.returncode != 0 and not allow_nonzero:
            raise EvaluationError(deadline.code, deadline.phase, False)
        return result
    except BaseException:
        teardown()
        raise


Runner = Callable[..., subprocess.CompletedProcess[str]]


class ManagedComposeProject:
    """One exact task-owned Compose project and its immutable cleanup receipt."""

    def __init__(
        self,
        *,
        root: Path,
        compose_paths: Sequence[Path],
        env_file: Path | LiveConfiguration,
        project_name: str,
        environment: Mapping[str, str],
        runner: Runner = run_bounded_subprocess,
        retain_image: bool = False,
    ) -> None:
        self.root = root.resolve()
        if not self.root.is_dir() or not _PROJECT_RE.fullmatch(project_name):
            raise ValueError("managed_compose_project_invalid")
        resolved_paths = tuple(path.resolve() for path in compose_paths)
        try:
            relatives = tuple(path.relative_to(self.root) for path in resolved_paths)
        except ValueError as exc:
            raise ValueError("managed_compose_project_invalid") from exc
        approved_relatives = (
            (Path("docker-compose.yml"),),
            (
                Path("docker-compose.yml"),
                Path("tests/fixtures/bounded-live-producer-v1/docker-compose.fixture.yml"),
            ),
        )
        if (
            relatives not in approved_relatives
            or any(not path.is_file() for path in resolved_paths)
            or len(set(resolved_paths)) != len(resolved_paths)
        ):
            raise ValueError("managed_compose_project_invalid")
        self.compose_paths = resolved_paths
        self.fixture_mode = len(relatives) == 2
        self._snapshot_secure_checked = False
        if isinstance(env_file, LiveConfiguration):
            self._credential_configuration: LiveConfiguration | None = env_file
            self.env_file = Path(os.devnull)
            self.service_env_file = Path(os.devnull)
        else:
            self._credential_configuration = None
            self.env_file = env_file.resolve()
            self.service_env_file = self.env_file
        self.project_name = project_name
        self.environment = dict(environment)
        self.port_overrides = {
            "DECISION_RESEARCH_AGENT_BACKEND_HOST_PORT": "0",
            "DECISION_RESEARCH_AGENT_MYSQL_HOST_PORT": "0",
        }
        self._runner = runner
        self._retain_image = retain_image
        self._containers: tuple[str, ...] = ()
        self._standalone_containers: tuple[str, ...] = ()
        self._volumes: tuple[str, ...] = ()
        self._networks: tuple[str, ...] = ()
        self._image_tag: str | None = None
        self._image_id: str | None = None
        self._temp_paths: tuple[Path, ...] = ()
        self._project_claimed = False

    def track_temp_paths(self, temp_paths: Sequence[Path]) -> None:
        resolved = tuple(path.resolve() for path in temp_paths)
        expected_root = self.root.parent.parent
        if (
            self._temp_paths
            or resolved != (expected_root,)
            or expected_root == Path(expected_root.anchor)
            or not expected_root.is_dir()
        ):
            raise ValueError("ownership_receipt_invalid")
        self._temp_paths = resolved

    def _compose_prefix(self, env_file: Path | None = None) -> tuple[str, ...]:
        credential_path = self.env_file if env_file is None else env_file
        command = ["docker", "compose", "--env-file", str(credential_path)]
        for path in self.compose_paths:
            command.extend(("-f", str(path)))
        command.extend(("--project-name", self.project_name))
        return tuple(command)

    def _invoke(
        self,
        arguments: Sequence[str],
        deadline: ActiveDeadline,
        *,
        compose: bool = False,
        allow_failure: bool = False,
        stream_bytes_max: int = _DEFAULT_STREAM_BYTES_MAX,
    ) -> subprocess.CompletedProcess[str]:
        if self.root.is_dir():
            invocation_root = self.root
        elif self.env_file.parent.is_dir():
            invocation_root = self.env_file.parent
        else:
            invocation_root = Path(tempfile.gettempdir()).resolve()

        def invoke(
            env_file: Path,
            service_env_file: Path,
        ) -> subprocess.CompletedProcess[str]:
            command = (
                (*self._compose_prefix(env_file), *arguments)
                if compose
                else tuple(arguments)
            )
            environment = {
                **self.environment,
                **self.port_overrides,
                "DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE": str(service_env_file),
            }
            return self._runner(
                command,
                cwd=invocation_root,
                env=environment,
                deadline=deadline,
                allowed_environment=_DOCKER_ENV_ALLOWLIST,
                stream_bytes_max=stream_bytes_max,
                allow_nonzero=allow_failure,
            )

        try:
            if self._credential_configuration is not None and compose:
                with self._credential_configuration.materialized(
                    forbidden_roots=(self.root, self.root.parent.parent),
                ) as credential_path:
                    result = invoke(credential_path, credential_path)
            else:
                result = invoke(self.env_file, self.service_env_file)
        except EvaluationError:
            raise
        if result.returncode != 0 and not allow_failure:
            raise EvaluationError(deadline.code, deadline.phase, False)
        return result

    def _call_budget_sidecar_authority(
        self,
        deadline: ActiveDeadline,
    ) -> tuple[str, str] | None:
        container_result = self._invoke(
            ("ps", "-q", "backend"),
            deadline,
            compose=True,
            allow_failure=True,
            stream_bytes_max=4096,
        )
        container_ids = tuple(container_result.stdout.splitlines())
        if (
            container_result.returncode != 0
            or len(container_ids) != 1
            or _DOCKER_FULL_ID_RE.fullmatch(container_ids[0]) is None
            or container_ids[0] not in self._containers
        ):
            return None
        container_id = container_ids[0]
        volume_name = f"{self.project_name}_backend_output"
        if volume_name not in self._volumes:
            return None
        volume_result = self._invoke(
            (
                "docker",
                "volume",
                "ls",
                "-q",
                "--filter",
                f"label=com.docker.compose.project={self.project_name}",
            ),
            deadline,
            allow_failure=True,
            stream_bytes_max=4096,
        )
        if (
            volume_result.returncode != 0
            or volume_name not in volume_result.stdout.splitlines()
        ):
            return None
        mount_result = self._invoke(
            (
                "docker",
                "inspect",
                "--format",
                "{{json .Mounts}}",
                container_id,
            ),
            deadline,
            allow_failure=True,
            stream_bytes_max=4096,
        )
        try:
            mounts = json.loads(mount_result.stdout)
        except (TypeError, json.JSONDecodeError):
            return None
        output_mounts = [
            mount
            for mount in mounts
            if isinstance(mount, dict) and mount.get("Destination") == "/app/output"
        ] if isinstance(mounts, list) else []
        if (
            mount_result.returncode != 0
            or len(output_mounts) != 1
            or output_mounts[0].get("Type") != "volume"
            or output_mounts[0].get("Name") != volume_name
        ):
            return None
        return container_id, volume_name

    def read_call_budget_sidecar(
        self,
        run_id: str,
        deadline: ActiveDeadline,
    ) -> object | None:
        from scripts.bounded_live_producer_runtime_diagnostics import (
            CallBudgetOriginSidecar,
            parse_call_budget_sidecar,
            serialize_call_budget_sidecar,
        )

        try:
            if (
                type(run_id) is not str
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id) is None
            ):
                return None
            before = self._call_budget_sidecar_authority(deadline)
            if before is None:
                return None
            result = self._invoke(
                (
                    "docker",
                    "exec",
                    before[0],
                    "python",
                    "/app/scripts/bounded_live_producer_runtime_diagnostics.py",
                    "read",
                    "--run-id",
                    run_id,
                ),
                deadline,
                allow_failure=True,
                stream_bytes_max=4096,
            )
            if result.returncode != 0 or result.stderr:
                return None
            parsed: CallBudgetOriginSidecar = parse_call_budget_sidecar(
                result.stdout.encode("utf-8")
            )
            if serialize_call_budget_sidecar(parsed) != result.stdout.encode("utf-8"):
                return None
            after = self._call_budget_sidecar_authority(deadline)
            if after != before:
                return None
            return parsed
        except Exception:
            return None

    def assert_unclaimed(self, deadline: ActiveDeadline) -> None:
        if self._project_claimed:
            raise ValueError("ownership_receipt_invalid")
        for resource in ("container", "volume", "network"):
            list_options = ("ls", "-a", "-q") if resource == "container" else ("ls", "-q")
            result = self._invoke(
                (
                    "docker",
                    resource,
                    *list_options,
                    "--filter",
                    f"label=com.docker.compose.project={self.project_name}",
                ),
                deadline,
            )
            if result.stdout.strip():
                raise _compose_error()
        self._project_claimed = True

    def build_backend(self, deadline: ActiveDeadline) -> None:
        image_tag = f"{self.project_name}-backend"
        if self._image_tag is None:
            existing = self._invoke(
                (
                    "docker",
                    "image",
                    "ls",
                    "-q",
                    "--filter",
                    f"reference={image_tag}",
                ),
                deadline,
            )
            if existing.stdout.strip():
                raise _compose_error()
            self._image_tag = image_tag
        self._invoke(("build", "backend"), deadline, compose=True)
        self._snapshot_secure_checked = False

    def verify_snapshot_secure_runtime(self, deadline: ActiveDeadline) -> None:
        secure_deadline = deadline.child(
            LIVE_BUDGET.build_start_seconds,
            code=FailureCode.SOURCE_ARCHIVE_INVALID,
            phase=FailurePhase.DOCKER,
        )
        image_tag = f"{self.project_name}-backend"
        image_result = self._invoke(
            ("docker", "image", "inspect", "--format", "{{.Id}}", image_tag),
            secure_deadline,
        )
        image_id = image_result.stdout.strip()
        if re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None:
            raise EvaluationError(
                FailureCode.SOURCE_ARCHIVE_INVALID,
                FailurePhase.DOCKER,
                False,
            )
        self._image_tag = image_tag
        self._image_id = image_id
        secure_check_name = f"{self.project_name}-secure-check"
        existing = self._invoke(
            (
                "docker",
                "container",
                "ls",
                "-a",
                "--format",
                "{{.Names}}",
                "--filter",
                f"name=^{secure_check_name}$",
            ),
            secure_deadline,
        )
        if existing.stdout.strip():
            raise EvaluationError(
                FailureCode.SOURCE_ARCHIVE_INVALID,
                FailurePhase.DOCKER,
                False,
            )
        self._standalone_containers = (secure_check_name,)
        try:
            for state_directory in ("data", "output"):
                (self.root / state_directory).mkdir(mode=0o700)
        except OSError as exc:
            raise EvaluationError(
                FailureCode.SOURCE_ARCHIVE_INVALID,
                FailurePhase.DOCKER,
                False,
            ) from exc
        result = self._invoke(
            (
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--label",
                f"com.docker.compose.project={self.project_name}",
                "--name",
                secure_check_name,
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--env",
                "PYTHON_DOTENV_DISABLED=1",
                "--tmpfs",
                "/proof/data:rw,nosuid,nodev,noexec,size=16m",
                "--tmpfs",
                "/proof/output:rw,nosuid,nodev,noexec,size=16m",
                "--volume",
                f"{self.root}:/proof:ro",
                "--workdir",
                "/proof",
                "--entrypoint",
                "python",
                image_tag,
                "scripts/secure_local_runtime_proof.py",
                "check",
            ),
            secure_deadline,
        )
        if result.stdout != '{"status":"valid","match":true}\n' or result.stderr:
            raise EvaluationError(
                FailureCode.SOURCE_ARCHIVE_INVALID,
                FailurePhase.DOCKER,
                False,
            )
        self._snapshot_secure_checked = True

    def start_mysql(self, deadline: ActiveDeadline) -> None:
        if not self._snapshot_secure_checked:
            message = (
                "fixture_secure_check_required"
                if self.fixture_mode
                else "snapshot_secure_check_required"
            )
            raise ValueError(message)
        self._invoke(("up", "-d", "mysql"), deadline, compose=True)

    def start_backend(self, deadline: ActiveDeadline) -> None:
        if self.fixture_mode:
            raise ValueError("fixture_backend_requires_explicit_start")
        if not self._snapshot_secure_checked:
            raise ValueError("snapshot_secure_check_required")
        self._invoke(("up", "-d", "backend"), deadline, compose=True)

    def start_fixture_backend(self, deadline: ActiveDeadline) -> None:
        if not self.fixture_mode:
            raise ValueError("fixture_backend_unavailable")
        if not self._snapshot_secure_checked:
            raise ValueError("fixture_secure_check_required")
        self._invoke(("up", "-d", "backend"), deadline, compose=True)

    def restart_backend(self, deadline: ActiveDeadline) -> None:
        self._invoke(("restart", "backend"), deadline, compose=True)

    def record_ownership(
        self,
        *,
        container_ids: Sequence[str],
        volume_ids: Sequence[str],
        network_ids: Sequence[str],
        image_tag: str,
        image_id: str,
        temp_paths: Sequence[Path],
    ) -> None:
        values = (*container_ids, *volume_ids, *network_ids)
        if (
            not values
            or any(
                type(value) is not str
                or not value
                or any(character.isspace() for character in value)
                for value in values
            )
            or any(_DOCKER_FULL_ID_RE.fullmatch(value) is None for value in container_ids)
            or any(_DOCKER_FULL_ID_RE.fullmatch(value) is None for value in network_ids)
            or not image_tag
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id)
            or self._containers
            or self._volumes
            or self._networks
        ):
            raise ValueError("ownership_receipt_invalid")
        resolved_temp = tuple(path.resolve() for path in temp_paths)
        if any(path == Path(path.anchor) or not path.exists() for path in resolved_temp):
            raise ValueError("ownership_receipt_invalid")
        if self._temp_paths and resolved_temp != self._temp_paths:
            raise ValueError("ownership_receipt_invalid")
        self._containers = tuple(container_ids)
        self._volumes = tuple(volume_ids)
        self._networks = tuple(network_ids)
        self._image_tag = image_tag
        self._image_id = image_id
        if not self._temp_paths:
            self._temp_paths = resolved_temp
        self._project_claimed = True

    def merge_resource_ownership(
        self,
        *,
        container_ids: Sequence[str],
        volume_ids: Sequence[str],
        network_ids: Sequence[str],
    ) -> None:
        if (
            any(_DOCKER_FULL_ID_RE.fullmatch(value) is None for value in container_ids)
            or any(_DOCKER_FULL_ID_RE.fullmatch(value) is None for value in network_ids)
            or any(
                type(value) is not str
                or not value
                or any(character.isspace() for character in value)
                for value in volume_ids
            )
        ):
            raise ValueError("ownership_receipt_invalid")

        def merged(existing: tuple[str, ...], additions: Sequence[str]) -> tuple[str, ...]:
            return (*existing, *(value for value in additions if value not in existing))

        self._containers = merged(self._containers, container_ids)
        self._volumes = merged(self._volumes, volume_ids)
        self._networks = merged(self._networks, network_ids)


def cleanup_receipt(
    project: ManagedComposeProject,
    deadline: ActiveDeadline,
    *,
    primary_error: BaseException | None = None,
) -> dict[str, bool]:
    failures: list[BaseException] = []

    def attempt(
        arguments: Sequence[str],
        *,
        compose: bool = False,
        required: bool = True,
    ) -> None:
        try:
            result = project._invoke(
                arguments,
                deadline,
                compose=compose,
                allow_failure=True,
            )
            if required and result.returncode != 0:
                failures.append(
                    EvaluationError(
                        FailureCode.CLEANUP_FAILED,
                        FailurePhase.CLEANUP,
                        False,
                        CleanupStatus.FAILED,
                    )
                )
        except BaseException:
            if not required:
                return
            failures.append(
                EvaluationError(
                    FailureCode.CLEANUP_FAILED,
                    FailurePhase.CLEANUP,
                    False,
                    CleanupStatus.FAILED,
                )
            )

    if project._project_claimed:
        attempt(("down", "-v", "--remove-orphans"), compose=True)
    for identifier in project._standalone_containers:
        attempt(("docker", "container", "rm", "-f", identifier), required=False)
    for identifier in project._containers:
        attempt(("docker", "container", "rm", "-f", identifier), required=False)
    for identifier in project._volumes:
        attempt(("docker", "volume", "rm", identifier), required=False)
    for identifier in project._networks:
        attempt(("docker", "network", "rm", identifier), required=False)
    for path in project._temp_paths:
        try:
            shutil.rmtree(path)
        except OSError:
            failures.append(
                EvaluationError(
                    FailureCode.CLEANUP_FAILED,
                    FailurePhase.CLEANUP,
                    False,
                    CleanupStatus.FAILED,
                )
            )
    if project._image_tag and not project._retain_image:
        attempt(("docker", "image", "rm", project._image_tag), required=False)

    def inventory(arguments: Sequence[str]) -> frozenset[str] | None:
        try:
            result = project._invoke(
                arguments,
                deadline,
                allow_failure=True,
            )
        except BaseException:
            failures.append(
                EvaluationError(
                    FailureCode.CLEANUP_FAILED,
                    FailurePhase.CLEANUP,
                    False,
                    CleanupStatus.FAILED,
                )
            )
            return None
        if result.returncode != 0:
            failures.append(
                EvaluationError(
                    FailureCode.CLEANUP_FAILED,
                    FailurePhase.CLEANUP,
                    False,
                    CleanupStatus.FAILED,
                )
            )
            return None
        return frozenset(value for value in result.stdout.splitlines() if value)

    if project._standalone_containers or project._containers:
        container_ids = inventory(
            ("docker", "container", "ls", "-a", "-q", "--no-trunc")
        )
        container_names = inventory(
            ("docker", "container", "ls", "-a", "--format", "{{.Names}}")
        )
        if (
            container_ids is not None
            and any(identifier in container_ids for identifier in project._containers)
        ) or (
            container_names is not None
            and any(
                identifier in container_names
                for identifier in project._standalone_containers
            )
        ):
            failures.append(
                EvaluationError(
                    FailureCode.CLEANUP_FAILED,
                    FailurePhase.CLEANUP,
                    False,
                    CleanupStatus.FAILED,
                )
            )
    if project._volumes:
        volume_names = inventory(("docker", "volume", "ls", "-q"))
        if volume_names is not None and any(
            identifier in volume_names for identifier in project._volumes
        ):
            failures.append(
                EvaluationError(
                    FailureCode.CLEANUP_FAILED,
                    FailurePhase.CLEANUP,
                    False,
                    CleanupStatus.FAILED,
                )
            )
    if project._networks:
        network_ids = inventory(
            ("docker", "network", "ls", "-q", "--no-trunc")
        )
        if network_ids is not None and any(
            identifier in network_ids for identifier in project._networks
        ):
            failures.append(
                EvaluationError(
                    FailureCode.CLEANUP_FAILED,
                    FailurePhase.CLEANUP,
                    False,
                    CleanupStatus.FAILED,
                )
            )
    if project._image_tag and not project._retain_image:
        image_ids = inventory(
            (
                "docker",
                "image",
                "ls",
                "-q",
                "--no-trunc",
                project._image_tag,
            )
        )
        if image_ids:
            failures.append(
                EvaluationError(
                    FailureCode.CLEANUP_FAILED,
                    FailurePhase.CLEANUP,
                    False,
                    CleanupStatus.FAILED,
                )
            )
    for path in project._temp_paths:
        if path.exists():
            failures.append(
                EvaluationError(
                    FailureCode.CLEANUP_FAILED,
                    FailurePhase.CLEANUP,
                    False,
                    CleanupStatus.FAILED,
                )
            )
    if project._project_claimed:
        for resource in ("container", "volume", "network"):
            list_options = ("ls", "-a", "-q") if resource == "container" else ("ls", "-q")
            try:
                result = project._invoke(
                    (
                        "docker",
                        resource,
                        *list_options,
                        "--filter",
                        f"label=com.docker.compose.project={project.project_name}",
                    ),
                    deadline,
                    allow_failure=True,
                )
            except BaseException:
                result = subprocess.CompletedProcess((), 1, "", "")
            if result.returncode != 0 or result.stdout.strip():
                failures.append(
                    EvaluationError(
                        FailureCode.CLEANUP_FAILED,
                        FailurePhase.CLEANUP,
                        False,
                        CleanupStatus.FAILED,
                    )
                )

    if failures:
        cleanup_failure = EvaluationError(
            FailureCode.CLEANUP_FAILED,
            FailurePhase.CLEANUP,
            False,
            CleanupStatus.FAILED,
        )
        if primary_error is not None:
            raise BaseExceptionGroup(
                "bounded lifecycle and cleanup failed",
                [primary_error, cleanup_failure],
            )
        raise cleanup_failure
    if primary_error is not None:
        raise primary_error
    return {
        "attempted": True,
        "succeeded": True,
        "zero_unapproved_containers": True,
        "zero_unapproved_volumes": True,
        "zero_unapproved_networks": True,
        "zero_temp_residue": True,
    }
