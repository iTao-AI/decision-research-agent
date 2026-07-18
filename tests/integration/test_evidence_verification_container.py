from __future__ import annotations

import os
from pathlib import Path
import time
import uuid

import pytest

from tests.integration.test_durable_review_container import (
    DockerProject,
    _assert_secure_runtime_boundary,
    _create_isolated_compose_env,
    _create_isolated_docker_config,
    _create_test_bootstrap_override,
    _docker_daemon_available,
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
    project_name = f"dra_verification_{uuid.uuid4().hex[:10]}"
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
            "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION": "true",
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
    assert result["delivery_status"] == "ready"
    assert result["artifact"]["artifact_id"] == (
        "decision-brief.r2.reviewed.md"
    )
    content_hash = result["artifact"]["content_hash"]
    assert "content" in result["artifact"]

    project.restart("backend")
    restarted = _tool(
        project,
        "result",
        "--run-id",
        seeded["run_id"],
    )
    assert restarted["delivery_status"] == "ready"
    assert restarted["artifact"]["artifact_id"] == (
        "decision-brief.r2.reviewed.md"
    )
    assert restarted["artifact"]["content_hash"] == content_hash
