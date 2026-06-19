from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import uuid

import pytest


pytestmark = pytest.mark.docker


class DockerProject:
    def __init__(self, *, root: Path, project_name: str, env: dict[str, str]):
        self.root = root
        self.project_name = project_name
        self.env = env

    def _compose(self, *args: str, timeout: int = 600):
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
        )

    def exec_json(self, command: list[str]) -> dict:
        completed = self._compose(
            "exec",
            "-T",
            "backend",
            *command,
            timeout=120,
        )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        return json.loads(lines[-1])

    def restart(self, service: str) -> None:
        self._compose("restart", service, timeout=120)


@pytest.fixture
def docker_project(tmp_path):
    root = Path(__file__).resolve().parents[2]
    required = (
        os.getenv("DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS", "false")
        .strip()
        .lower()
        == "true"
    )
    available = subprocess.run(
        ["docker", "info"],
        text=True,
        capture_output=True,
        check=False,
    ).returncode == 0
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
    try:
        project._compose("up", "-d", "--build", "backend")
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
