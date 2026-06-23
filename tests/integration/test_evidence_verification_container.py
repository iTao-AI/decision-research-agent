from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
import uuid

import pytest

from tests.integration.test_durable_review_container import (
    DockerProject,
    _ensure_compose_env_file,
)


pytestmark = pytest.mark.docker


@pytest.fixture
def verification_docker_project(tmp_path):
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

    project_name = f"dra_verification_{uuid.uuid4().hex[:10]}"
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
    env["DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION"] = "true"
    env["API_SECRET"] = "verification-container-test-only"
    project = DockerProject(
        root=root,
        project_name=project_name,
        env=env,
    )
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


def _tool(
    project: DockerProject,
    *args: str,
    input_text: str | None = None,
) -> dict:
    return project.exec_json(
        [
            "python",
            "tools/decision_research_agent_tool.py",
            *args,
        ],
        input_text=input_text,
        environment={
            "DECISION_RESEARCH_AGENT_API_KEY":
                "verification-container-test-only",
        },
    )


def _wait_for_review_status(
    project: DockerProject,
    *,
    run_id: str,
    expected: str,
    timeout_seconds: float = 30,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last = None
    while time.monotonic() < deadline:
        last = _tool(project, "review", "show", "--run-id", run_id)
        if last["workflow"]["status"] == expected:
            return last
        time.sleep(0.25)
    raise AssertionError(
        f"review_status_timeout:{expected}:{last}"
    )


def test_verification_to_approval_survives_container_restart(
    verification_docker_project,
):
    project = verification_docker_project
    seeded = project.exec_json(
        [
            "python",
            "scripts/evidence_verification_container_fixture.py",
        ]
    )
    listed = _tool(
        project,
        "evidence",
        "list",
        "--run-id",
        seeded["run_id"],
    )
    assert listed["items"][0]["evidence_id"] == seeded["evidence_id"]

    shown = _tool(
        project,
        "evidence",
        "show",
        "--run-id",
        seeded["run_id"],
        "--evidence-id",
        seeded["evidence_id"],
    )
    assert shown["effective"]["verification_revision"] == 0

    verified = _tool(
        project,
        "evidence",
        "verify",
        "--run-id",
        seeded["run_id"],
        "--evidence-id",
        seeded["evidence_id"],
        "--confirm-source-match",
    )
    assert verified["idempotent_replay"] is False

    finalized = _tool(
        project,
        "evidence",
        "finalize",
        "--run-id",
        seeded["run_id"],
    )
    assert finalized["revision"] == 2
    _wait_for_review_status(
        project,
        run_id=seeded["run_id"],
        expected="waiting_decision",
    )

    approved = _tool(
        project,
        "review",
        "approve",
        "--run-id",
        seeded["run_id"],
        "--wait",
    )
    assert approved["workflow"]["status"] == "approved"
    result = _tool(
        project,
        "result",
        "--run-id",
        seeded["run_id"],
    )
    publication_id = result["current_publication"]["publication_id"]
    assert result["current_publication"]["status"] == "ready"
    artifact_ids = {
        item["artifact_id"]
        for item in result["artifacts"]
    }
    assert "decision-brief.json" in artifact_ids
    assert "decision-brief.r2.reviewed.json" in artifact_ids

    project.restart("backend")
    restarted = _tool(
        project,
        "result",
        "--run-id",
        seeded["run_id"],
    )
    assert restarted["current_publication"]["publication_id"] == (
        publication_id
    )
    assert restarted["current_publication"]["status"] == "ready"
