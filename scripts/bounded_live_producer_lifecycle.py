"""Bounded source, credential, subprocess, and Compose lifecycle controls."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from types import MappingProxyType
from typing import Callable, Mapping, Sequence
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
_PUBLIC_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z", re.ASCII)
_CURRENCY_RE = re.compile(r"[A-Z]{3}\Z", re.ASCII)
_ENV_KEY_RE = re.compile(r"[A-Z][A-Z0-9_]*\Z", re.ASCII)
_MAX_ENV_BYTES = 64 * 1024
_DEFAULT_ARCHIVE_BYTES_MAX = 64 * 1024 * 1024
_DEFAULT_ARCHIVE_MEMBERS_MAX = 4096
_DEFAULT_ARCHIVE_MEMBER_BYTES_MAX = 16 * 1024 * 1024
_DEFAULT_STREAM_BYTES_MAX = 1024 * 1024

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
    if host.endswith((".local", ".internal", ".localhost")) or host in {
        "local",
        "internal",
        "localhost",
    }:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        labels = host.split(".")
        return len(labels) >= 2 and all(
            label
            and len(label) <= 63
            and label[0].isalnum()
            and label[-1].isalnum()
            and all(character.isalnum() or character == "-" for character in label)
            for label in labels
        )
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


def _git_output(root: Path, *arguments: str) -> str:
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
            timeout=30,
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
    archive_bytes_max: int = _DEFAULT_ARCHIVE_BYTES_MAX,
    archive_members_max: int = _DEFAULT_ARCHIVE_MEMBERS_MAX,
    archive_member_bytes_max: int = _DEFAULT_ARCHIVE_MEMBER_BYTES_MAX,
) -> SourceSnapshot:
    root = checkout_root.resolve()
    try:
        commit = _git_output(root, "rev-parse", "--verify", "HEAD")
        tree = _git_output(root, "rev-parse", "--verify", "HEAD^{tree}")
        if not _COMMIT_RE.fullmatch(commit) or not _COMMIT_RE.fullmatch(tree):
            raise ValueError
        if _git_output(root, "status", "--porcelain=v1", "--untracked-files=all"):
            raise _evaluation_error(FailureCode.SOURCE_DIRTY, FailurePhase.INPUT)
        tracked = tuple(
            _git_output(root, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
        )
        if not tracked or any(path not in tracked for path in required_paths):
            raise ValueError
        version_bytes = (root / "VERSION").read_bytes()
        if not version_bytes.endswith(b"\n") or version_bytes.count(b"\n") != 1:
            raise ValueError
        version = version_bytes[:-1].decode("ascii")
        if not _VERSION_RE.fullmatch(version):
            raise ValueError
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
            ["git", "archive", "--format=tar", f"--output={archive_path}", "HEAD"],
            cwd=root,
            env=environment,
            check=True,
            capture_output=True,
            timeout=30,
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
        if any(not (snapshot_root / path).is_file() for path in required_paths):
            raise ValueError
        secure_check = subprocess.run(
            [sys.executable, "scripts/secure_local_runtime_proof.py", "check"],
            cwd=snapshot_root,
            env={
                "PATH": os.environ.get("PATH", ""),
                "PYTHON_DOTENV_DISABLED": "1",
            },
            check=False,
            capture_output=True,
            timeout=30,
        )
        if secure_check.returncode != 0:
            raise ValueError
        archive_sha256 = hashlib.sha256(archive_path.read_bytes()).hexdigest()
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
    )


def _read_env_file(path: Path) -> dict[str, str]:
    descriptor = -1
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_mode & 0o077
            or not before.st_mode & stat.S_IRUSR
            or before.st_size > _MAX_ENV_BYTES
        ):
            raise ValueError
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise ValueError
        raw = os.read(descriptor, _MAX_ENV_BYTES + 1)
        if len(raw) > _MAX_ENV_BYTES or os.read(descriptor, 1):
            raise ValueError
        after = path.lstat()
        if (after.st_dev, after.st_ino, after.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
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
        return values
    except (OSError, UnicodeError, ValueError) as exc:
        raise _evaluation_error(
            FailureCode.CREDENTIAL_SOURCE_INVALID, FailurePhase.INPUT
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


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
    for key, value in payload.items():
        if type(key) is not str or not _PUBLIC_ID_RE.fullmatch(key) or type(value) is not str:
            raise ValueError
        try:
            amount = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError from exc
        if not amount.is_finite() or amount < 0:
            raise ValueError


def load_live_configuration(
    env_file: Path,
    declaration: CredentialDeclaration,
    *,
    process_api_key: str,
) -> Mapping[str, str]:
    try:
        values = _read_env_file(env_file)
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
    return MappingProxyType(dict(values))


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


def _sanitize_volumes(value: object, expected_targets: Sequence[str]) -> list[dict[str, str]]:
    if type(value) is not list or len(value) != len(expected_targets):
        raise ValueError
    output: list[dict[str, str]] = []
    for role, (item, target) in enumerate(zip(value, expected_targets, strict=True)):
        if type(item) is not dict or item.get("type") != "volume" or item.get("target") != target:
            raise ValueError
        if set(item) - {"type", "source", "target", "read_only", "volume"}:
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
                }
                | ({"command"} if fixture_mode else set()),
            ),
            "mysql": (
                3306,
                ("/var/lib/mysql",),
                {"image", "ports", "environment", "healthcheck", "volumes", "networks"},
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
                "volumes": _sanitize_volumes(service.get("volumes"), volume_targets),
                "networks": ["app-network"],
            }
            networks = service.get("networks")
            if not (
                networks == ["app-network"]
                or (type(networks) is dict and set(networks) == {"app-network"})
            ):
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
                build = service.get("build")
                if type(build) is not dict or set(build) != {"context", "dockerfile"}:
                    raise ValueError
                if build.get("dockerfile") != "Dockerfile.backend":
                    raise ValueError
                safe_service["build"] = {
                    "context": "<tracked-snapshot>",
                    "dockerfile": "Dockerfile.backend",
                }
                env_files = service.get("env_file")
                if type(env_files) is not list or len(env_files) != 1:
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
) -> subprocess.CompletedProcess[str]:
    if (
        not arguments
        or any(type(item) is not str or "\x00" in item for item in arguments)
        or not cwd.is_dir()
        or stream_bytes_max <= 0
        or (allow_stream_overflow and not any(item in {"--quiet", "-q"} for item in arguments))
    ):
        raise ValueError("subprocess_invocation_invalid")
    allowed = frozenset(allowed_environment)
    process_environment = {key: value for key, value in env.items() if key in allowed}
    process_environment["PYTHON_DOTENV_DISABLED"] = "1"
    timeout = deadline.remaining(24 * 60 * 60)
    try:
        process = subprocess.Popen(
            list(arguments),
            cwd=cwd,
            env=process_environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise EvaluationError(deadline.code, deadline.phase, False) from exc

    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    overflows = {"stdout": False, "stderr": False}

    def drain(name: str, stream: object) -> None:
        reader = stream
        while True:
            chunk = reader.read(64 * 1024)  # type: ignore[attr-defined]
            if not chunk:
                return
            remaining = stream_bytes_max + 1 - len(buffers[name])
            if remaining > 0:
                buffers[name].extend(chunk[:remaining])
            if len(chunk) > remaining or len(buffers[name]) > stream_bytes_max:
                overflows[name] = True

    threads = [
        threading.Thread(target=drain, args=("stdout", process.stdout), daemon=True),
        threading.Thread(target=drain, args=("stderr", process.stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait()
        for thread in threads:
            thread.join()
        raise EvaluationError(deadline.code, deadline.phase, False) from exc
    for thread in threads:
        thread.join()
    if any(overflows.values()) and not allow_stream_overflow:
        raise EvaluationError(deadline.code, deadline.phase, False)
    try:
        stdout = bytes(buffers["stdout"][:stream_bytes_max]).decode("utf-8")
        stderr = bytes(buffers["stderr"][:stream_bytes_max]).decode("utf-8")
    except UnicodeError as exc:
        raise EvaluationError(deadline.code, deadline.phase, False) from exc
    result = subprocess.CompletedProcess(tuple(arguments), process.returncode, stdout, stderr)
    if process.returncode != 0:
        raise EvaluationError(deadline.code, deadline.phase, False)
    return result


Runner = Callable[..., subprocess.CompletedProcess[str]]


class ManagedComposeProject:
    """One exact task-owned Compose project and its immutable cleanup receipt."""

    def __init__(
        self,
        *,
        root: Path,
        compose_paths: Sequence[Path],
        env_file: Path,
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
        self.env_file = env_file.resolve()
        self.project_name = project_name
        self.environment = dict(environment)
        self.port_overrides = {
            "DECISION_RESEARCH_AGENT_BACKEND_HOST_PORT": "0",
            "DECISION_RESEARCH_AGENT_MYSQL_HOST_PORT": "0",
        }
        self._runner = runner
        self._retain_image = retain_image
        self._containers: tuple[str, ...] = ()
        self._volumes: tuple[str, ...] = ()
        self._networks: tuple[str, ...] = ()
        self._image_tag: str | None = None
        self._image_id: str | None = None
        self._temp_paths: tuple[Path, ...] = ()

    def _compose_prefix(self) -> tuple[str, ...]:
        command = ["docker", "compose", "--env-file", str(self.env_file)]
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
    ) -> subprocess.CompletedProcess[str]:
        command = (*self._compose_prefix(), *arguments) if compose else tuple(arguments)
        environment = {
            **self.environment,
            **self.port_overrides,
            "DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE": str(self.env_file),
        }
        invocation_root = self.root if self.root.is_dir() else self.env_file.parent
        try:
            result = self._runner(
                command,
                cwd=invocation_root,
                env=environment,
                deadline=deadline,
                allowed_environment=_DOCKER_ENV_ALLOWLIST,
                stream_bytes_max=_DEFAULT_STREAM_BYTES_MAX,
            )
        except EvaluationError:
            if allow_failure:
                return subprocess.CompletedProcess(command, 1, "", "")
            raise
        if result.returncode != 0 and not allow_failure:
            raise EvaluationError(deadline.code, deadline.phase, False)
        return result

    def assert_unclaimed(self, deadline: ActiveDeadline) -> None:
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

    def build_backend(self, deadline: ActiveDeadline) -> None:
        self._invoke(("build", "backend"), deadline, compose=True)

    def start_mysql(self, deadline: ActiveDeadline) -> None:
        self._invoke(("up", "-d", "mysql"), deadline, compose=True)

    def start_backend(self, deadline: ActiveDeadline) -> None:
        if self.fixture_mode:
            raise ValueError("fixture_backend_requires_explicit_start")
        self._invoke(("up", "-d", "backend"), deadline, compose=True)

    def start_fixture_backend(self, deadline: ActiveDeadline) -> None:
        if not self.fixture_mode:
            raise ValueError("fixture_backend_unavailable")
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
            or any(type(value) is not str or not value or any(c.isspace() for c in value) for value in values)
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
        self._containers = tuple(container_ids)
        self._volumes = tuple(volume_ids)
        self._networks = tuple(network_ids)
        self._image_tag = image_tag
        self._image_id = image_id
        self._temp_paths = resolved_temp


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

    attempt(("down", "-v", "--remove-orphans"), compose=True)
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

    def verify_absent(resource: str, identifier: str) -> None:
        try:
            result = project._invoke(
                ("docker", resource, "inspect", identifier),
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
            return
        if result.returncode == 0:
            failures.append(
                EvaluationError(
                    FailureCode.CLEANUP_FAILED,
                    FailurePhase.CLEANUP,
                    False,
                    CleanupStatus.FAILED,
                )
            )

    for identifier in project._containers:
        verify_absent("container", identifier)
    for identifier in project._volumes:
        verify_absent("volume", identifier)
    for identifier in project._networks:
        verify_absent("network", identifier)
    if project._image_tag and not project._retain_image:
        verify_absent("image", project._image_tag)
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
            raise ExceptionGroup("bounded lifecycle and cleanup failed", [primary_error, cleanup_failure])
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
