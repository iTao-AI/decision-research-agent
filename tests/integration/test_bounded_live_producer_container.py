from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
from typing import Any

import pytest

from scripts.bounded_live_producer_contracts import FailureCode, FailurePhase
from scripts.bounded_live_producer_http import ProofHttpClient
from scripts.bounded_live_producer_lifecycle import (
    ActiveDeadline,
    ManagedComposeProject,
    cleanup_receipt,
    prepare_source_snapshot,
    run_bounded_subprocess,
    sanitize_compose_projection,
)
from scripts.bounded_live_producer_proof import (
    compare_restart,
    observe_terminal,
    reconcile_create,
    validate_replay,
)


pytestmark = pytest.mark.docker
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SCRIPT = PROJECT_ROOT / "scripts/bounded_live_producer_container_fixture.py"
FIXTURE_OVERRIDE = (
    PROJECT_ROOT
    / "tests/fixtures/bounded-live-producer-v1/docker-compose.fixture.yml"
)
DOCKER_TEST_ACTIVE_SECONDS = 720
DOCKER_TEST_CLEANUP_SECONDS = 120
_DOCKER_ENV_NAMES = (
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
)


def _docker_environment() -> dict[str, str]:
    result = {key: os.environ[key] for key in _DOCKER_ENV_NAMES if key in os.environ}
    result["PYTHON_DOTENV_DISABLED"] = "1"
    return result


def _required_docker() -> bool:
    return os.environ.get("DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS") == "true"


def _probe_docker(environment: dict[str, str]) -> None:
    try:
        run_bounded_subprocess(
            ("docker", "info", "--format", "{{json .ServerVersion}}"),
            cwd=PROJECT_ROOT,
            env=environment,
            deadline=ActiveDeadline(
                30,
                code=FailureCode.DOCKER_UNAVAILABLE,
                phase=FailurePhase.DOCKER,
            ),
            allowed_environment=tuple(environment),
        )
    except Exception:
        if _required_docker():
            pytest.fail("docker_required_but_unavailable")
        pytest.skip("docker_unavailable")


def _write_fixture_env(path: Path) -> str:
    api_secret = "bounded-container-api-secret"
    values = {
        "OPENAI_BASE_URL": "https://provider.invalid/v1",
        "OPENAI_API_KEY": "provider-disabled-container-only",
        "LLM_MODEL": "fixture-model",
        "LLM_FALLBACK_MODEL": "fixture-model",
        "API_SECRET": api_secret,
        "TAVILY_API_KEY": "search-disabled-container-only",
        "MYSQL_ROOT_PASSWORD": "root-container-only",
        "MYSQL_USER": "decision_research",
        "MYSQL_PASSWORD": "mysql-container-only",
        "MYSQL_DATABASE": "decision_research",
        "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES": "false",
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL": "false",
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION": "false",
        "LANGSMITH_TRACING": "false",
        "LANGSMITH_API_KEY": "",
        "LANGSMITH_HIDE_INPUTS": "true",
        "LANGSMITH_HIDE_OUTPUTS": "true",
        "RAGFLOW_API_KEY": "",
    }
    path.write_text(
        "".join(f"{key}={value}\n" for key, value in values.items()),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return api_secret


def _project_output(
    project: ManagedComposeProject,
    arguments: tuple[str, ...],
    deadline: ActiveDeadline,
    *,
    compose: bool = False,
) -> str:
    return project._invoke(arguments, deadline, compose=compose).stdout.strip()


def _container_id(
    project: ManagedComposeProject,
    service: str,
    deadline: ActiveDeadline,
) -> str:
    values = _project_output(project, ("ps", "-q", service), deadline, compose=True).splitlines()
    assert len(values) == 1 and values[0]
    return values[0]


def _loopback_port(
    project: ManagedComposeProject,
    service: str,
    target: int,
    deadline: ActiveDeadline,
) -> int:
    container = _container_id(project, service, deadline)
    raw = _project_output(
        project,
        (
            "docker",
            "inspect",
            "--format",
            "{{json .NetworkSettings.Ports}}",
            container,
        ),
        deadline,
    )
    bindings = json.loads(raw)[f"{target}/tcp"]
    assert len(bindings) == 1
    assert bindings[0]["HostIp"] == "127.0.0.1"
    return int(bindings[0]["HostPort"])


def _refresh_ownership(
    project: ManagedComposeProject,
    deadline: ActiveDeadline,
    *,
    task_root: Path,
) -> None:
    label = f"label=com.docker.compose.project={project.project_name}"
    containers = tuple(
        _project_output(
            project,
            ("docker", "container", "ls", "-a", "-q", "--filter", label),
            deadline,
        ).splitlines()
    )
    volumes = tuple(
        _project_output(
            project,
            ("docker", "volume", "ls", "-q", "--filter", label),
            deadline,
        ).splitlines()
    )
    networks = tuple(
        _project_output(
            project,
            ("docker", "network", "ls", "-q", "--filter", label),
            deadline,
        ).splitlines()
    )
    image_tag = f"{project.project_name}-backend"
    image_id = _project_output(
        project,
        ("docker", "image", "inspect", "--format", "{{.Id}}", image_tag),
        deadline,
    )
    project.record_ownership(
        container_ids=containers,
        volume_ids=volumes,
        network_ids=networks,
        image_tag=image_tag,
        image_id=image_id,
        temp_paths=(task_root,),
    )


def _wait_health(client: ProofHttpClient, deadline: ActiveDeadline) -> None:
    while True:
        try:
            client.health(timeout_seconds=15)
            return
        except Exception:
            time.sleep(deadline.remaining(1))


def test_provider_free_bounded_producer_container_lifecycle(tmp_path: Path) -> None:
    assert subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout == ""
    assert FIXTURE_SCRIPT.is_file(), "bounded_fixture_script_missing"
    assert FIXTURE_OVERRIDE.is_file(), "bounded_fixture_override_missing"

    docker_environment = _docker_environment()
    _probe_docker(docker_environment)
    task_root = tmp_path / "archive-task"
    snapshot = prepare_source_snapshot(
        PROJECT_ROOT,
        task_root,
        required_paths=(
            "VERSION",
            "Dockerfile.backend",
            "docker-compose.yml",
            "scripts/secure_local_runtime_proof.py",
            "scripts/bounded_live_producer_container_fixture.py",
            "scripts/bounded_live_producer_contracts.py",
            "scripts/bounded_live_producer_http.py",
            "scripts/bounded_live_producer_lifecycle.py",
            "scripts/bounded_live_producer_proof.py",
            "tests/fixtures/bounded-live-producer-v1/docker-compose.fixture.yml",
        ),
    )
    env_file = tmp_path / "fixture.env"
    api_secret = _write_fixture_env(env_file)
    project = ManagedComposeProject(
        root=snapshot.root,
        compose_paths=(
            snapshot.root / "docker-compose.yml",
            snapshot.root
            / "tests/fixtures/bounded-live-producer-v1/docker-compose.fixture.yml",
        ),
        env_file=env_file,
        project_name=f"dra-proof-{secrets.token_hex(16)}",
        environment=docker_environment,
    )
    active = ActiveDeadline(
        DOCKER_TEST_ACTIVE_SECONDS,
        code=FailureCode.SERVICE_START_FAILED,
        phase=FailurePhase.DOCKER,
    )
    primary_error: BaseException | None = None
    try:
        project.assert_unclaimed(active)
        config = json.loads(
            _project_output(project, ("config", "--format", "json"), active, compose=True)
        )
        sanitize_compose_projection(config, fixture_mode=True)
        project.build_backend(active)
        project.start_mysql(active)
        project.start_fixture_backend(active)
        _refresh_ownership(project, active, task_root=task_root)
        backend_port = _loopback_port(project, "backend", 8000, active)
        _loopback_port(project, "mysql", 3306, active)
        client = ProofHttpClient(
            port=backend_port,
            api_key=api_secret,
            remaining_seconds=active.remaining,
        )
        _wait_health(client, active)
        thread_id = "fixture-thread-" + secrets.token_hex(16)
        request_bytes = json.dumps(
            {
                "profile_id": "generic",
                "query": "bounded container fixture query",
                "scope": {},
                "thread_id": thread_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        key = "fixture-key-" + secrets.token_hex(16)
        accepted = reconcile_create(client, request_bytes=request_bytes, key=key)
        assert accepted["idempotent_replay"] is False
        before, status, _result = observe_terminal(
            client,
            accepted=accepted,
            required_cited_domains=("docs.python.org", "peps.python.org"),
            remaining_seconds=active.remaining,
        )
        assert status["state_version"] == 2
        project.restart_backend(active)
        _wait_health(client, active)
        after_restart, _status, _result = observe_terminal(
            client,
            accepted=accepted,
            required_cited_domains=("docs.python.org", "peps.python.org"),
            remaining_seconds=active.remaining,
        )
        compare_restart(before, after_restart)
        replayed = client.create(request_bytes=request_bytes, idempotency_key=key)
        after_replay, _status, _result = observe_terminal(
            client,
            accepted=accepted,
            required_cited_domains=("docs.python.org", "peps.python.org"),
            remaining_seconds=active.remaining,
        )
        validate_replay(replayed, before=after_restart, after=after_replay)

        backend_id = _container_id(project, "backend", active)
        inspection = json.loads(
            _project_output(project, ("docker", "inspect", backend_id), active)
        )[0]
        assert "ALL" in inspection["HostConfig"]["CapDrop"]
        assert "no-new-privileges" in " ".join(inspection["HostConfig"]["SecurityOpt"])
        backend_env = dict(item.split("=", 1) for item in inspection["Config"]["Env"] if "=" in item)
        assert backend_env.get("MYSQL_ROOT_PASSWORD", "") == ""
        assert backend_env["OPENAI_API_KEY"] == "provider-disabled-container-only"
        assert backend_env["TAVILY_API_KEY"] == "search-disabled-container-only"
    except BaseException as exc:
        primary_error = exc
    cleanup_deadline = ActiveDeadline(
        DOCKER_TEST_CLEANUP_SECONDS,
        code=FailureCode.CLEANUP_FAILED,
        phase=FailurePhase.CLEANUP,
    )
    cleanup = cleanup_receipt(
        project,
        cleanup_deadline,
        primary_error=primary_error,
    )
    assert cleanup == {
        "attempted": True,
        "succeeded": True,
        "zero_unapproved_containers": True,
        "zero_unapproved_volumes": True,
        "zero_unapproved_networks": True,
        "zero_temp_residue": True,
    }
    assert not task_root.exists()
