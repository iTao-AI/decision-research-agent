from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
import subprocess
import time
import uuid

import pytest

from scripts.durable_hitl_gate_runner import GATE_TESTS, build_report


pytestmark = pytest.mark.docker


COMPOSE_UP_TIMEOUT_SECONDS = 480
HEALTH_TIMEOUT_SECONDS = 60
DIAGNOSTIC_TIMEOUT_SECONDS = 30
COMPOSE_CLEANUP_TIMEOUT_SECONDS = 120
LIFECYCLE_TIMEOUT_SECONDS = 840
MAX_COMPOSE_LIFECYCLE_SECONDS = 960
REQUIRED_DOCKER_LIFECYCLE_COUNT = 3
MAX_DIAGNOSTIC_CHARACTERS = 12_000

DOCKER_HOST_ENV_KEYS = (
    "PATH",
    "HOME",
    "TMPDIR",
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DOCKER_TLS_VERIFY",
    "DOCKER_CERT_PATH",
    "XDG_CONFIG_HOME",
)
_ALLOWED_FEATURE_FLAGS = frozenset(
    {
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL",
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION",
    }
)
_TEST_HOST_PORTS = {
    "DECISION_RESEARCH_AGENT_BACKEND_HOST_PORT": "0",
    "DECISION_RESEARCH_AGENT_MYSQL_HOST_PORT": "0",
}
CONTAINER_API_SECRET = "secure-local-runtime-test-only"
ISOLATED_COMPOSE_VALUES = {
    "API_SECRET": CONTAINER_API_SECRET,
    "MYSQL_ROOT_PASSWORD": "secure-local-runtime-root-test-only",
    "MYSQL_PASSWORD": "secure-local-runtime-db-test-only",
    "OPENAI_API_KEY": "provider-disabled-test-only",
    "OPENAI_BASE_URL": "http://127.0.0.1:9/v1",
    "TAVILY_API_KEY": "provider-disabled-search-test-only",
    "LANGSMITH_TRACING": "false",
}
_DATA_SENTINEL = "/app/data/.secure-local-runtime-test-sentinel"
_OUTPUT_SENTINEL = "/app/output/.secure-local-runtime-test-sentinel"
_SENTINEL_CONTENT = "secure-local-runtime-persistence"


@dataclass(frozen=True)
class BootstrapOverride:
    report_path: Path
    compose_path: Path


def _create_test_bootstrap_override(tmp_path: Path) -> BootstrapOverride:
    bootstrap_dir = tmp_path / "test-bootstrap"
    bootstrap_dir.mkdir()
    report_path = bootstrap_dir / "durable-hitl-bootstrap-report.json"
    report = build_report({gate_name: True for gate_name in GATE_TESTS})
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    compose_path = bootstrap_dir / "docker-compose.test-bootstrap.yml"
    compose_path.write_text(
        json.dumps(
            {
                "services": {
                    "backend": {
                        "environment": {
                            "DECISION_RESEARCH_AGENT_API_KEY": "${API_SECRET}",
                        },
                        "volumes": [
                            {
                                "type": "bind",
                                "source": str(report_path),
                                "target": (
                                    "/app/docs/evidence/"
                                    "durable-hitl-gate-report.json"
                                ),
                                "read_only": True,
                            }
                        ]
                    }
                }
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return BootstrapOverride(
        report_path=report_path,
        compose_path=compose_path,
    )


def _parse_test_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if not separator or not key or key in values:
            raise ValueError("container_test_env_invalid")
        values[key] = value
    return values


def _create_isolated_compose_env(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    env_path = directory / "secure-local-runtime.env"
    descriptor = os.open(
        env_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as env_file:
            descriptor = -1
            for key, value in ISOLATED_COMPOSE_VALUES.items():
                env_file.write(f"{key}={value}\n")
    finally:
        if descriptor != -1:
            os.close(descriptor)
    if stat.S_IMODE(env_path.stat().st_mode) != 0o600:
        env_path.unlink(missing_ok=True)
        raise RuntimeError("container_test_env_permissions_invalid")
    return env_path


def _create_isolated_docker_config(directory: Path) -> Path:
    docker_config = directory / "docker-config"
    docker_config.mkdir()
    (docker_config / "config.json").write_text(
        json.dumps(
            {
                "auths": {},
                "cliPluginsExtraDirs": [
                    str(Path.home() / ".docker" / "cli-plugins")
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return docker_config


def build_compose_subprocess_env(
    *,
    env_file: Path,
    docker_config: Path,
    feature_flags: dict[str, str],
) -> dict[str, str]:
    if set(feature_flags) - _ALLOWED_FEATURE_FLAGS:
        raise ValueError("container_feature_flag_invalid")
    env = {
        key: os.environ[key]
        for key in DOCKER_HOST_ENV_KEYS
        if key in os.environ
    }
    env.update(feature_flags)
    env.update(_TEST_HOST_PORTS)
    env["DOCKER_CONFIG"] = str(docker_config)
    env["DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE"] = str(env_file)
    return env


def _docker_daemon_available(env: dict[str, str]) -> bool:
    try:
        completed = subprocess.run(
            ["docker", "info"],
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=DIAGNOSTIC_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


class DockerProject:
    def __init__(
        self,
        *,
        root: Path,
        project_name: str,
        env_file: Path,
        docker_config: Path,
        feature_flags: dict[str, str],
        compose_files: tuple[Path, ...] = (),
        monotonic=None,
        sleep=None,
    ):
        self.root = root
        self.project_name = project_name
        self.env_file = env_file
        self.docker_config = docker_config
        self.env = build_compose_subprocess_env(
            env_file=env_file,
            docker_config=docker_config,
            feature_flags=feature_flags,
        )
        self.compose_files = compose_files
        self.last_diagnostics = ""
        self._shared_mysql_image_id: str | None = None
        self._monotonic = monotonic or time.monotonic
        self._sleep = sleep or time.sleep
        self._lifecycle_deadline: float | None = None
        self._cleanup_deadline: float | None = None

    def _bounded_timeout(self, requested: float) -> float:
        if self._cleanup_deadline is not None:
            deadline = self._cleanup_deadline
            code = "container_cleanup_deadline_exceeded"
        elif self._lifecycle_deadline is not None:
            deadline = self._lifecycle_deadline
            code = "container_lifecycle_deadline_exceeded"
        else:
            return requested
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            raise TimeoutError(code)
        return min(requested, remaining)

    def _compose(
        self,
        *args: str,
        timeout: int = 600,
        input_text: str | None = None,
        check: bool = True,
    ):
        compose_file_args = [
            item
            for compose_file in self.compose_files
            for item in ("-f", str(compose_file))
        ]
        return subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                str(self.env_file),
                *compose_file_args,
                "-p",
                self.project_name,
                *args,
            ],
            cwd=self.root,
            env=self.env,
            text=True,
            capture_output=True,
            check=check,
            timeout=self._bounded_timeout(timeout),
            input=input_text,
        )

    def _docker(
        self,
        *args: str,
        timeout: int = DIAGNOSTIC_TIMEOUT_SECONDS,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", *args],
            cwd=self.root,
            env=self.env,
            text=True,
            capture_output=True,
            check=check,
            timeout=self._bounded_timeout(timeout),
        )

    def exec_json(
        self,
        command: list[str],
        *,
        input_text: str | None = None,
    ) -> dict:
        args = ["exec", "-T"]
        args.extend(["backend", *command])
        completed = self._compose(
            *args,
            timeout=120,
            input_text=input_text,
        )
        return json.loads(completed.stdout)

    def _inspect_service(self, service: str) -> dict:
        completed = self._compose(
            "ps",
            "-q",
            service,
            timeout=DIAGNOSTIC_TIMEOUT_SECONDS,
        )
        container_id = completed.stdout.strip()
        if not container_id:
            raise RuntimeError("container_service_missing")
        inspected = self._docker("inspect", container_id)
        payload = json.loads(inspected.stdout)
        if not isinstance(payload, list) or len(payload) != 1:
            raise RuntimeError("container_inspect_invalid")
        return payload[0]

    def health_states(self, services: tuple[str, ...]) -> dict[str, str]:
        states: dict[str, str] = {}
        for service in services:
            try:
                inspected = self._inspect_service(service)
                states[service] = inspected["State"]["Health"]["Status"]
            except (KeyError, TypeError, ValueError, RuntimeError):
                states[service] = "missing"
        return states

    def wait_until_healthy(
        self,
        *,
        services: tuple[str, ...],
        timeout_seconds: float = HEALTH_TIMEOUT_SECONDS,
        poll_seconds: float = 0.25,
    ) -> bool:
        deadline = self._monotonic() + timeout_seconds
        if self._lifecycle_deadline is not None:
            deadline = min(deadline, self._lifecycle_deadline)
        while self._monotonic() < deadline:
            states = self.health_states(services)
            if all(states.get(service) == "healthy" for service in services):
                return True
            if any(states.get(service) == "unhealthy" for service in services):
                raise RuntimeError("container_health_unhealthy")
            if any(
                states.get(service) not in {"missing", "starting", "healthy"}
                for service in services
            ):
                raise RuntimeError("container_health_state_invalid")
            remaining = deadline - self._monotonic()
            self._sleep(min(poll_seconds, remaining))
        if (
            self._lifecycle_deadline is not None
            and self._monotonic() >= self._lifecycle_deadline
        ):
            raise TimeoutError("container_lifecycle_deadline_exceeded")
        raise RuntimeError("container_health_timeout")

    def wait_until_ready(self) -> None:
        self.wait_until_healthy(services=("backend",))

    def get_health(self) -> dict:
        return self.exec_json(
            [
                "python",
                "-c",
                (
                    "import json; from urllib.request import urlopen; "
                    "r=urlopen('http://127.0.0.1:8000/health', timeout=2); "
                    "print(json.dumps(json.load(r), sort_keys=True))"
                ),
            ]
        )

    def inspect_backend(self) -> dict:
        return self._inspect_service("backend")

    def inspect_mysql(self) -> dict:
        return self._inspect_service("mysql")

    def published_bindings(self, service: str, port: str) -> list[dict[str, str]]:
        inspected = self._inspect_service(service)
        bindings = inspected["NetworkSettings"]["Ports"].get(port)
        return [] if bindings is None else bindings

    def _sentinel_command(self, operation: str) -> None:
        paths = (_DATA_SENTINEL, _OUTPUT_SENTINEL)
        if operation == "write":
            expression = "; ".join(
                f"Path({path!r}).write_text({_SENTINEL_CONTENT!r}, encoding='utf-8')"
                for path in paths
            )
        elif operation == "assert":
            expression = "; ".join(
                f"assert Path({path!r}).read_text(encoding='utf-8') == {_SENTINEL_CONTENT!r}"
                for path in paths
            )
        elif operation == "remove":
            expression = "; ".join(
                f"Path({path!r}).unlink(missing_ok=True)" for path in paths
            )
        else:
            raise ValueError("container_sentinel_operation_invalid")
        self._compose(
            "exec",
            "-T",
            "backend",
            "python",
            "-c",
            f"from pathlib import Path; {expression}",
            timeout=DIAGNOSTIC_TIMEOUT_SECONDS,
        )

    def write_persistence_sentinels(self) -> None:
        self._sentinel_command("write")

    def assert_persistence_sentinels(self) -> None:
        self._sentinel_command("assert")

    def remove_persistence_sentinels(self) -> None:
        self._sentinel_command("remove")

    def _redact(self, value: str) -> str:
        redacted = value
        for secret in ISOLATED_COMPOSE_VALUES.values():
            if secret:
                redacted = redacted.replace(secret, "[redacted]")
        for path in (self.root, self.env_file, self.docker_config):
            redacted = redacted.replace(str(path), "[path]")
        return redacted[-MAX_DIAGNOSTIC_CHARACTERS:]

    def collect_bounded_diagnostics(self) -> str:
        try:
            completed = self._compose(
                "logs",
                "--no-color",
                "--tail",
                "200",
                "backend",
                "mysql",
                timeout=DIAGNOSTIC_TIMEOUT_SECONDS,
                check=False,
            )
            raw = f"{completed.stdout or ''}{completed.stderr or ''}"
        except (OSError, subprocess.TimeoutExpired):
            raw = "container_diagnostics_unavailable"
        self.last_diagnostics = self._redact(raw)
        return self.last_diagnostics

    def assert_no_provider_calls(self) -> None:
        completed = self._compose(
            "logs",
            "--no-color",
            "--tail",
            "200",
            "backend",
            timeout=DIAGNOSTIC_TIMEOUT_SECONDS,
            check=False,
        )
        raw = f"{completed.stdout or ''}{completed.stderr or ''}"
        markers = (
            "127.0.0.1:9",
            "provider-disabled-test-only",
            "provider-disabled-search-test-only",
        )
        if any(marker in raw for marker in markers):
            raise AssertionError("provider_call_observed")

    def record_backend_image_ids(self) -> set[str]:
        completed = self._compose(
            "images",
            "-q",
            "backend",
            timeout=DIAGNOSTIC_TIMEOUT_SECONDS,
            check=False,
        )
        return {line for line in completed.stdout.splitlines() if line}

    def _mysql_image_id(self) -> str | None:
        completed = self._docker(
            "image",
            "inspect",
            "mysql:8.0",
            "--format",
            "{{.Id}}",
            check=False,
        )
        value = completed.stdout.strip()
        return value if completed.returncode == 0 and value else None

    def task_inventory(self) -> dict[str, tuple[str, ...]]:
        label = f"label=com.docker.compose.project={self.project_name}"
        commands = {
            "containers": ("ps", "-aq", "--filter", label),
            "volumes": ("volume", "ls", "-q", "--filter", label),
            "networks": ("network", "ls", "-q", "--filter", label),
        }
        inventory: dict[str, tuple[str, ...]] = {}
        for kind, command in commands.items():
            completed = self._docker(*command, check=False)
            inventory[kind] = tuple(
                line for line in completed.stdout.splitlines() if line
            )
        return inventory

    def cleanup(self) -> None:
        backend_image_ids = self.record_backend_image_ids()
        completed = self._compose(
            "down",
            "--rmi",
            "local",
            "-v",
            "--remove-orphans",
            timeout=COMPOSE_CLEANUP_TIMEOUT_SECONDS,
            check=False,
        )
        inventory = self.task_inventory()
        for image_id in backend_image_ids:
            inspected = self._docker(
                "image",
                "inspect",
                image_id,
                check=False,
            )
            if inspected.returncode == 0:
                raise RuntimeError("container_backend_image_cleanup_failed")
        if any(inventory.values()):
            raise RuntimeError("container_task_inventory_not_empty")
        if self._shared_mysql_image_id is not None:
            if self._mysql_image_id() != self._shared_mysql_image_id:
                raise RuntimeError("container_shared_mysql_image_changed")
        if completed.returncode != 0:
            raise RuntimeError("container_cleanup_failed")

    @contextmanager
    def running_backend(self):
        failure: BaseException | None = None
        self._lifecycle_deadline = (
            self._monotonic() + LIFECYCLE_TIMEOUT_SECONDS
        )
        try:
            self._shared_mysql_image_id = self._mysql_image_id()
            self._compose(
                "up",
                "-d",
                "--build",
                "backend",
                timeout=COMPOSE_UP_TIMEOUT_SECONDS,
            )
            if self._shared_mysql_image_id is None:
                self._shared_mysql_image_id = self._mysql_image_id()
            self.wait_until_healthy(services=("mysql", "backend"))
            yield self
        except BaseException as exc:
            failure = exc
            try:
                self.collect_bounded_diagnostics()
            except BaseException:
                pass
            raise
        finally:
            self._lifecycle_deadline = None
            self._cleanup_deadline = (
                self._monotonic() + COMPOSE_CLEANUP_TIMEOUT_SECONDS
            )
            try:
                self.cleanup()
            except BaseException as cleanup_failure:
                if failure is None:
                    raise
                raise BaseExceptionGroup(
                    "container_lifecycle_and_cleanup_failed",
                    [failure, cleanup_failure],
                )
            finally:
                self._cleanup_deadline = None

    def restart(self, service: str) -> None:
        self._compose("restart", service, timeout=120)
        if service == "backend":
            self.wait_until_ready()


def _assert_secure_runtime_boundary(project: DockerProject) -> None:
    assert project.wait_until_healthy(services=("mysql", "backend")) is True
    assert project.get_health() == {
        "status": "ok",
        "service": "decision-research-agent",
    }
    inspect = project.inspect_backend()
    assert inspect["HostConfig"]["CapDrop"] == ["ALL"]
    assert "no-new-privileges:true" in inspect["HostConfig"]["SecurityOpt"]
    backend_environment = dict(
        entry.partition("=")[::2] for entry in inspect["Config"]["Env"]
    )
    mysql_environment = dict(
        entry.partition("=")[::2]
        for entry in project.inspect_mysql()["Config"]["Env"]
    )
    assert backend_environment.get("MYSQL_ROOT_PASSWORD") in {None, ""}
    assert mysql_environment.get("MYSQL_ROOT_PASSWORD")

    backend_bindings = project.published_bindings("backend", "8000/tcp")
    mysql_bindings = project.published_bindings("mysql", "3306/tcp")
    assert backend_bindings
    assert mysql_bindings
    assert {binding["HostIp"] for binding in backend_bindings} == {"127.0.0.1"}
    assert {binding["HostIp"] for binding in mysql_bindings} == {"127.0.0.1"}
    published_host_ports = {
        binding["HostPort"] for binding in backend_bindings + mysql_bindings
    }
    assert len(published_host_ports) == 2
    assert all(port.isdigit() and int(port) > 0 for port in published_host_ports)

    project.write_persistence_sentinels()
    project.restart("backend")
    project.assert_persistence_sentinels()
    project.remove_persistence_sentinels()


@pytest.fixture
def docker_project(tmp_path):
    root = Path(__file__).resolve().parents[2]
    required = (
        os.getenv("DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS", "false")
        .strip()
        .lower()
        == "true"
    )
    project_name = f"dra_hitl_{uuid.uuid4().hex[:10]}"
    env_file = _create_isolated_compose_env(tmp_path / "runtime")
    docker_config = _create_isolated_docker_config(tmp_path)
    bootstrap = _create_test_bootstrap_override(tmp_path)
    project = DockerProject(
        root=root,
        project_name=project_name,
        env_file=env_file,
        docker_config=docker_config,
        feature_flags={
            "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL": "true",
        },
        compose_files=(root / "docker-compose.yml", bootstrap.compose_path),
    )
    if not _docker_daemon_available(project.env):
        if required:
            pytest.fail("docker_required_but_unavailable")
        pytest.skip("Docker daemon is unavailable")

    with project.running_backend():
        _assert_secure_runtime_boundary(project)
        yield project
        project.assert_no_provider_calls()


def test_backend_container_restart_preserves_review_state(docker_project):
    seeded = docker_project.exec_json(
        ["python", "scripts/durable_hitl_container_fixture.py", "seed"]
    )
    accepted = docker_project.exec_json(
        [
            "python",
            "tools/decision_research_agent_tool.py",
            "review",
            "approve",
            "--run-id",
            seeded["run_id"],
        ],
    )
    assert accepted["status"] == "resume_pending"
    docker_project.restart("backend")
    recovered = docker_project.exec_json(
        [
            "python",
            "scripts/durable_hitl_container_fixture.py",
            "recover",
            "--run-id",
            seeded["run_id"],
            "--timeout-seconds",
            "20",
        ]
    )

    assert recovered["application_db_preserved"] is True
    assert recovered["checkpoint_db_preserved"] is True
    assert recovered["decision_preserved"] is True
    assert recovered["reviewed_artifact_preserved"] is True


def test_controlled_review_cli_approve_and_reject_canary(docker_project):
    approve = docker_project.exec_json(
        ["python", "scripts/durable_hitl_container_fixture.py", "seed"]
    )
    approved = docker_project.exec_json(
        [
            "python",
            "tools/decision_research_agent_tool.py",
            "review",
            "approve",
            "--run-id",
            approve["run_id"],
            "--wait",
        ],
    )
    assert approved["workflow"]["status"] == "approved"
    assert approved["delivery_status"] == "ready"

    reject = docker_project.exec_json(
        ["python", "scripts/durable_hitl_container_fixture.py", "seed"]
    )
    rejected = docker_project.exec_json(
        [
            "python",
            "tools/decision_research_agent_tool.py",
            "review",
            "reject",
            "--run-id",
            reject["run_id"],
            "--reason-stdin",
            "--wait",
        ],
        input_text="Evidence boundary was not accepted.\n",
    )
    assert rejected["workflow"]["status"] == "rejected"
    assert rejected["delivery_status"] == "blocked"
    assert not any(
        artifact_id.startswith("decision-brief.reviewed")
        for artifact_id in rejected["resolution"]["artifact_ids"]
    )
