import json
import subprocess

import yaml

from scripts.durable_hitl_gate_runner import GATE_TESTS, build_report
import tests.integration.test_durable_review_container as container_support

from tests.integration.test_durable_review_container import (
    DockerProject,
    _ensure_compose_env_file,
)


def test_compose_env_file_is_created_and_removed_when_missing(tmp_path):
    env_path = tmp_path / ".env"

    with _ensure_compose_env_file(tmp_path):
        content = env_path.read_text(encoding="utf-8")
        assert content.startswith("# Created temporarily")
        assert "OPENAI_API_KEY=durable-hitl-container-test-only" in content
        assert "LANGSMITH_TRACING=false" in content

    assert not env_path.exists()


def test_compose_env_file_preserves_existing_content(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("API_SECRET=existing\n", encoding="utf-8")

    with _ensure_compose_env_file(tmp_path):
        assert env_path.read_text(encoding="utf-8") == "API_SECRET=existing\n"

    assert env_path.read_text(encoding="utf-8") == "API_SECRET=existing\n"


def test_backend_readiness_retries_until_healthcheck_succeeds(
    tmp_path,
    monkeypatch,
):
    project = DockerProject(root=tmp_path, project_name="test", env={})
    attempts = []

    def fake_compose(*args, timeout):
        attempts.append((args, timeout))
        if len(attempts) < 3:
            raise subprocess.CalledProcessError(137, args)

    monkeypatch.setattr(project, "_compose", fake_compose)
    monkeypatch.setattr(
        "tests.integration.test_durable_review_container.time.sleep",
        lambda _: None,
    )

    project.wait_until_ready(timeout_seconds=1, poll_seconds=0)

    assert len(attempts) == 3
    assert attempts[-1][0][:3] == ("exec", "-T", "backend")


def test_bootstrap_report_is_test_only_complete_and_does_not_touch_tracked_report(
    tmp_path,
):
    tracked_report = tmp_path / "docs" / "evidence" / "durable-hitl-gate-report.json"
    tracked_report.parent.mkdir(parents=True)
    tracked_report.write_bytes(b'{"status":"NO_GO"}\n')
    before = tracked_report.read_bytes()

    bootstrap = container_support._create_test_bootstrap_override(tmp_path)

    expected = build_report({gate_name: True for gate_name in GATE_TESTS})
    assert json.loads(bootstrap.report_path.read_text(encoding="utf-8")) == expected
    assert bootstrap.report_path.is_relative_to(tmp_path)
    assert "test-bootstrap" in bootstrap.report_path.parts
    assert bootstrap.report_path != tracked_report
    assert tracked_report.read_bytes() == before


def test_bootstrap_compose_override_mounts_report_read_only(tmp_path):
    bootstrap = container_support._create_test_bootstrap_override(tmp_path)

    override = yaml.safe_load(
        bootstrap.compose_path.read_text(encoding="utf-8")
    )
    mounts = override["services"]["backend"]["volumes"]

    assert mounts == [
        {
            "type": "bind",
            "source": str(bootstrap.report_path),
            "target": "/app/docs/evidence/durable-hitl-gate-report.json",
            "read_only": True,
        }
    ]


def test_docker_project_uses_explicit_compose_override(tmp_path, monkeypatch):
    base = tmp_path / "docker-compose.yml"
    override = tmp_path / "docker-compose.test-bootstrap.yml"
    base.write_text("services: {}\n", encoding="utf-8")
    override.write_text("services: {}\n", encoding="utf-8")
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(container_support.subprocess, "run", fake_run)
    project = DockerProject(
        root=tmp_path,
        project_name="test",
        env={},
        compose_files=(base, override),
    )

    project._compose("config")

    assert captured["command"] == [
        "docker",
        "compose",
        "-f",
        str(base),
        "-f",
        str(override),
        "-p",
        "test",
        "config",
    ]
