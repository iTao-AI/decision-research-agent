from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

import pytest


pytestmark = pytest.mark.docker


@contextmanager
def _ensure_compose_env_file(root: Path):
    env_path = root / ".env"
    created = False
    try:
        if not env_path.exists():
            try:
                with env_path.open("x", encoding="utf-8") as env_file:
                    env_file.write(
                        "# Created temporarily by the Docker integration test.\n"
                        "OPENAI_API_KEY=durable-hitl-container-test-only\n"
                        "LANGSMITH_TRACING=false\n"
                    )
                created = True
            except FileExistsError:
                pass
        yield
    finally:
        if created:
            env_path.unlink(missing_ok=True)


class DockerProject:
    def __init__(self, *, root: Path, project_name: str, env: dict[str, str]):
        self.root = root
        self.project_name = project_name
        self.env = env

    def _compose(
        self,
        *args: str,
        timeout: int = 600,
        input_text: str | None = None,
    ):
        return subprocess.run(
            [
                "docker",
                "compose",
                "-p",
                self.project_name,
                *args,
            ],
            cwd=self.root,
            env=self.env,
            text=True,
            capture_output=True,
            check=True,
            timeout=timeout,
            input=input_text,
        )

    def exec_json(
        self,
        command: list[str],
        *,
        input_text: str | None = None,
        environment: dict[str, str] | None = None,
    ) -> dict:
        args = ["exec", "-T"]
        for key, value in sorted((environment or {}).items()):
            args.extend(["-e", f"{key}={value}"])
        args.extend(["backend", *command])
        completed = self._compose(
            *args,
            timeout=120,
            input_text=input_text,
        )
        return json.loads(completed.stdout)

    def wait_until_ready(
        self,
        *,
        timeout_seconds: float = 30,
        poll_seconds: float = 0.25,
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                self._compose(
                    "exec",
                    "-T",
                    "backend",
                    "python",
                    "-c",
                    (
                        "from urllib.request import urlopen;"
                        "urlopen('http://127.0.0.1:8000/health', timeout=2).read()"
                    ),
                    timeout=15,
                )
                return
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                last_error = exc
                time.sleep(poll_seconds)
        raise RuntimeError("backend_container_readiness_timeout") from last_error

    def restart(self, service: str) -> None:
        self._compose("restart", service, timeout=120)
        if service == "backend":
            self.wait_until_ready()


@pytest.fixture
def docker_project(tmp_path):
    root = Path(__file__).resolve().parents[2]
    required = (
        os.getenv("DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS", "false")
        .strip()
        .lower()
        == "true"
    )
    try:
        available = subprocess.run(
            ["docker", "info"],
            text=True,
            capture_output=True,
            check=False,
        ).returncode == 0
    except FileNotFoundError:
        available = False
    if not available:
        if required:
            pytest.fail("docker_required_but_unavailable")
        pytest.skip("Docker daemon is unavailable")

    project_name = f"dra_hitl_{uuid.uuid4().hex[:10]}"
    env = os.environ.copy()
    docker_config = tmp_path / "docker-config"
    docker_config.mkdir()
    (docker_config / "config.json").write_text(
        json.dumps(
            {
                "auths": {},
                "cliPluginsExtraDirs": [
                    str(Path.home() / ".docker" / "cli-plugins")
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env["DOCKER_CONFIG"] = str(docker_config)
    env["DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL"] = "true"
    env["API_SECRET"] = "durable-hitl-container-test-only"
    project = DockerProject(root=root, project_name=project_name, env=env)
    with _ensure_compose_env_file(root):
        try:
            project._compose(
                "up",
                "-d",
                "--build",
                "backend",
                timeout=1800,
            )
            project.wait_until_ready()
            yield project
        finally:
            project._compose(
                "down",
                "-v",
                "--remove-orphans",
                timeout=180,
            )


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
        environment={
            "DECISION_RESEARCH_AGENT_API_KEY":
                "durable-hitl-container-test-only",
        },
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
        environment={
            "DECISION_RESEARCH_AGENT_API_KEY":
                "durable-hitl-container-test-only",
        },
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
        environment={
            "DECISION_RESEARCH_AGENT_API_KEY":
                "durable-hitl-container-test-only",
        },
    )
    assert rejected["workflow"]["status"] == "rejected"
    assert rejected["delivery_status"] == "blocked"
    assert not any(
        artifact_id.startswith("decision-brief.reviewed")
        for artifact_id in rejected["resolution"]["artifact_ids"]
    )
