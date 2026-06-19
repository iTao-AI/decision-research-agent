import subprocess

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
