from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess

import pytest
import yaml

from scripts.durable_hitl_gate_runner import GATE_TESTS, build_report
import tests.integration.test_durable_review_container as container_support


def _project(
    tmp_path: Path,
    *,
    feature_flags: dict[str, str] | None = None,
    monotonic=None,
    sleep=None,
    project_name: str = "test",
) -> container_support.DockerProject:
    env_file = container_support._create_isolated_compose_env(tmp_path)
    docker_config = container_support._create_isolated_docker_config(tmp_path)
    base = tmp_path / "docker-compose.yml"
    override = tmp_path / "docker-compose.test-bootstrap.yml"
    base.write_text("services: {}\n", encoding="utf-8")
    override.write_text("services: {}\n", encoding="utf-8")
    return container_support.DockerProject(
        root=tmp_path,
        project_name=project_name,
        env_file=env_file,
        docker_config=docker_config,
        feature_flags=feature_flags or {},
        compose_files=(base, override),
        monotonic=monotonic,
        sleep=sleep,
    )


def test_isolated_compose_env_is_mode_0600_and_never_reads_repo_env(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    repo_env = project_root / ".env"
    repo_env.write_text("API_SECRET=host-value-must-not-be-read\n", encoding="utf-8")
    before = repo_env.read_bytes()

    isolated = container_support._create_isolated_compose_env(tmp_path / "runtime")

    assert isolated.parent == tmp_path / "runtime"
    assert isolated.name != ".env"
    assert stat.S_IMODE(isolated.stat().st_mode) == 0o600
    values = container_support._parse_test_env_file(isolated)
    assert values == container_support.ISOLATED_COMPOSE_VALUES
    assert values["OPENAI_BASE_URL"] == "http://127.0.0.1:9/v1"
    assert values["LANGSMITH_TRACING"] == "false"
    assert repo_env.read_bytes() == before


def test_compose_subprocess_env_is_an_exact_scrubbed_allowlist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    poisoned = {
        "API_SECRET": "host-api-secret",
        "MYSQL_PASSWORD": "host-db-secret",
        "OPENAI_API_KEY": "host-provider-secret",
        "COMPOSE_PROJECT_NAME": "host-project",
        "COMPOSE_FILE": "host-compose-file",
        "DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE": "host-env-file",
        "DECISION_RESEARCH_AGENT_BACKEND_HOST_PORT": "8000",
        "DECISION_RESEARCH_AGENT_MYSQL_HOST_PORT": "3306",
    }
    for key, value in poisoned.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("PATH", os.environ["PATH"])
    monkeypatch.setenv("HOME", os.environ["HOME"])

    env_file = container_support._create_isolated_compose_env(tmp_path / "runtime")
    docker_config = container_support._create_isolated_docker_config(tmp_path)
    env = container_support.build_compose_subprocess_env(
        env_file=env_file,
        docker_config=docker_config,
        feature_flags={
            "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL": "true",
        },
    )

    expected_host_keys = {
        key
        for key in container_support.DOCKER_HOST_ENV_KEYS
        if key in os.environ
    }
    assert set(env) == expected_host_keys | {
        "DOCKER_CONFIG",
        "DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE",
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL",
        "DECISION_RESEARCH_AGENT_BACKEND_HOST_PORT",
        "DECISION_RESEARCH_AGENT_MYSQL_HOST_PORT",
    }
    assert env["DOCKER_CONFIG"] == str(docker_config)
    assert env["DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE"] == str(env_file)
    controlled_keys = {
        "DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE",
        "DECISION_RESEARCH_AGENT_BACKEND_HOST_PORT",
        "DECISION_RESEARCH_AGENT_MYSQL_HOST_PORT",
    }
    assert not (set(poisoned) - controlled_keys) & set(env)
    assert all(value not in env.values() for value in poisoned.values())
    assert env["DECISION_RESEARCH_AGENT_BACKEND_HOST_PORT"] == "0"
    assert env["DECISION_RESEARCH_AGENT_MYSQL_HOST_PORT"] == "0"


def test_compose_subprocess_env_rejects_unknown_feature_flag(tmp_path: Path) -> None:
    env_file = container_support._create_isolated_compose_env(tmp_path / "runtime")
    docker_config = container_support._create_isolated_docker_config(tmp_path)

    with pytest.raises(ValueError, match="container_feature_flag_invalid"):
        container_support.build_compose_subprocess_env(
            env_file=env_file,
            docker_config=docker_config,
            feature_flags={"API_SECRET": "not-an-approved-feature-flag"},
        )


def test_two_test_projects_request_distinct_engine_assigned_loopback_ports(
    tmp_path: Path,
) -> None:
    first = _project(tmp_path / "first", project_name="first")
    second = _project(tmp_path / "second", project_name="second")

    assert first.project_name != second.project_name
    expected_dynamic_ports = {
        "DECISION_RESEARCH_AGENT_BACKEND_HOST_PORT": "0",
        "DECISION_RESEARCH_AGENT_MYSQL_HOST_PORT": "0",
    }
    assert {
        key: first.env[key] for key in expected_dynamic_ports
    } == expected_dynamic_ports
    assert {
        key: second.env[key] for key in expected_dynamic_ports
    } == expected_dynamic_ports


def test_docker_availability_probe_uses_the_scrubbed_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(container_support.subprocess, "run", fake_run)

    assert container_support._docker_daemon_available(project.env) is True
    assert captured["command"] == ["docker", "info"]
    assert captured["kwargs"]["env"] == project.env
    assert captured["kwargs"]["check"] is False


def test_backend_health_polling_requires_both_services_healthy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    states = iter(
        (
            {"mysql": "starting", "backend": "starting"},
            {"mysql": "healthy", "backend": "starting"},
            {"mysql": "healthy", "backend": "healthy"},
        )
    )
    monkeypatch.setattr(project, "health_states", lambda services: next(states))
    monkeypatch.setattr(container_support.time, "sleep", lambda _seconds: None)

    assert project.wait_until_healthy(
        services=("mysql", "backend"),
        timeout_seconds=1,
        poll_seconds=0,
    ) is True


def test_backend_health_polling_fails_closed_on_unhealthy_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    monkeypatch.setattr(
        project,
        "health_states",
        lambda _services: {"mysql": "healthy", "backend": "unhealthy"},
    )

    with pytest.raises(RuntimeError, match="container_health_unhealthy"):
        project.wait_until_healthy(
            services=("mysql", "backend"),
            timeout_seconds=1,
            poll_seconds=0,
        )


def test_bootstrap_report_is_test_only_complete_and_does_not_touch_tracked_report(
    tmp_path: Path,
) -> None:
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


def test_bootstrap_compose_override_mounts_report_read_only(tmp_path: Path) -> None:
    bootstrap = container_support._create_test_bootstrap_override(tmp_path)

    override = yaml.safe_load(bootstrap.compose_path.read_text(encoding="utf-8"))
    backend = override["services"]["backend"]
    mounts = backend["volumes"]

    assert mounts == [
        {
            "type": "bind",
            "source": str(bootstrap.report_path),
            "target": "/app/docs/evidence/durable-hitl-gate-report.json",
            "read_only": True,
        }
    ]
    assert backend["environment"] == {
        "DECISION_RESEARCH_AGENT_API_KEY": "${API_SECRET}",
    }


def test_docker_project_uses_explicit_env_file_before_compose_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(container_support.subprocess, "run", fake_run)

    project._compose("config")

    assert captured["command"] == [
        "docker",
        "compose",
        "--env-file",
        str(project.env_file),
        "-f",
        str(project.compose_files[0]),
        "-f",
        str(project.compose_files[1]),
        "-p",
        "test",
        "config",
    ]
    assert captured["kwargs"]["env"] == project.env
    assert captured["kwargs"]["cwd"] == tmp_path


def test_diagnostics_are_tail_bounded_and_redact_every_fake_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    fake_values = tuple(container_support.ISOLATED_COMPOSE_VALUES.values())
    leaked = " ".join(value for value in fake_values if value)
    raw = "x" * (container_support.MAX_DIAGNOSTIC_CHARACTERS * 2) + leaked

    monkeypatch.setattr(
        project,
        "_compose",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["docker", "compose"],
            0,
            stdout=raw,
            stderr="",
        ),
    )

    diagnostics = project.collect_bounded_diagnostics()

    assert len(diagnostics) <= container_support.MAX_DIAGNOSTIC_CHARACTERS
    assert all(value not in diagnostics for value in fake_values if value)
    assert "[redacted]" in diagnostics


@pytest.mark.parametrize("failure_point", ("up", "readiness", "assertion"))
def test_lifecycle_failure_always_collects_logs_and_cleans_exact_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    project = _project(tmp_path)
    events: list[object] = []

    def fake_compose(*args, **kwargs):
        events.append((args, kwargs))
        if args and args[0] == "up" and failure_point == "up":
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(project, "_compose", fake_compose)
    monkeypatch.setattr(
        project,
        "wait_until_healthy",
        lambda **_kwargs: (
            (_ for _ in ()).throw(RuntimeError("container_health_timeout"))
            if failure_point == "readiness"
            else True
        ),
    )
    monkeypatch.setattr(
        project,
        "collect_bounded_diagnostics",
        lambda: events.append("diagnostics") or "bounded",
    )
    monkeypatch.setattr(
        project,
        "cleanup",
        lambda: events.append("cleanup"),
    )

    with pytest.raises((subprocess.CalledProcessError, RuntimeError, AssertionError)):
        with project.running_backend():
            if failure_point == "assertion":
                raise AssertionError("injected assertion")

    assert "diagnostics" in events
    assert "cleanup" in events


def test_lifecycle_preserves_primary_and_cleanup_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    events: list[str] = []

    monkeypatch.setattr(project, "_mysql_image_id", lambda: None)
    monkeypatch.setattr(
        project,
        "_compose",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["docker", "compose"], 0, stdout="", stderr=""
        ),
    )
    monkeypatch.setattr(project, "wait_until_healthy", lambda **_kwargs: True)
    monkeypatch.setattr(
        project,
        "collect_bounded_diagnostics",
        lambda: events.append("diagnostics") or "bounded",
    )

    def cleanup_failure() -> None:
        events.append("cleanup")
        raise RuntimeError("injected cleanup failure")

    monkeypatch.setattr(project, "cleanup", cleanup_failure)

    with pytest.raises(BaseExceptionGroup) as caught:
        with project.running_backend():
            raise AssertionError("injected primary failure")

    assert caught.value.message == "container_lifecycle_and_cleanup_failed"
    assert [type(item) for item in caught.value.exceptions] == [
        AssertionError,
        RuntimeError,
    ]
    assert [str(item) for item in caught.value.exceptions] == [
        "injected primary failure",
        "injected cleanup failure",
    ]
    assert events == ["diagnostics", "cleanup"]


def test_cleanup_uses_rmi_local_and_checks_recorded_image_and_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    compose_calls: list[tuple[str, ...]] = []
    docker_calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        project,
        "record_backend_image_ids",
        lambda: {"sha256:task-owned-backend"},
    )

    def fake_compose(*args, **_kwargs):
        compose_calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    def fake_docker(*args, **_kwargs):
        docker_calls.append(args)
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="")

    monkeypatch.setattr(project, "_compose", fake_compose)
    monkeypatch.setattr(project, "_docker", fake_docker)
    monkeypatch.setattr(project, "task_inventory", lambda: {
        "containers": (),
        "volumes": (),
        "networks": (),
    })

    project.cleanup()

    assert (
        "down",
        "--rmi",
        "local",
        "-v",
        "--remove-orphans",
    ) in compose_calls
    assert (
        "image",
        "inspect",
        "sha256:task-owned-backend",
    ) in docker_calls


def test_lifecycle_deadline_caps_subprocesses_and_cleanup_has_its_own_reserve(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [100.0]
    timeouts: list[float] = []

    def monotonic() -> float:
        return now[0]

    def fake_run(command, **kwargs):
        timeouts.append(kwargs["timeout"])
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    project = _project(
        tmp_path,
        monotonic=monotonic,
        sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    monkeypatch.setattr(container_support.subprocess, "run", fake_run)
    monkeypatch.setattr(project, "_mysql_image_id", lambda: None)
    monkeypatch.setattr(project, "wait_until_healthy", lambda **_kwargs: True)
    monkeypatch.setattr(project, "collect_bounded_diagnostics", lambda: "bounded")

    def cleanup() -> None:
        project._compose("down", timeout=999)

    monkeypatch.setattr(project, "cleanup", cleanup)

    with pytest.raises(
        TimeoutError,
        match="container_lifecycle_deadline_exceeded",
    ):
        with project.running_backend():
            now[0] += container_support.LIFECYCLE_TIMEOUT_SECONDS - 5
            project._compose("exec", timeout=120)
            assert timeouts[-1] == pytest.approx(5)
            now[0] += 6
            project._compose("exec", timeout=120)

    assert timeouts[-1] == container_support.COMPOSE_CLEANUP_TIMEOUT_SECONDS


def test_health_wait_cannot_outlive_the_active_lifecycle_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [10.0]

    project = _project(
        tmp_path,
        monotonic=lambda: now[0],
        sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    monkeypatch.setattr(project, "_mysql_image_id", lambda: None)
    monkeypatch.setattr(project, "_compose", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(project, "cleanup", lambda: None)
    real_wait_until_healthy = project.wait_until_healthy
    monkeypatch.setattr(project, "wait_until_healthy", lambda **_kwargs: True)
    monkeypatch.setattr(
        project,
        "health_states",
        lambda _services: {"backend": "starting"},
    )

    with project.running_backend():
        now[0] += container_support.LIFECYCLE_TIMEOUT_SECONDS - 3
        with pytest.raises(
            TimeoutError,
            match="container_lifecycle_deadline_exceeded",
        ):
            real_wait_until_healthy(
                services=("backend",),
                timeout_seconds=60,
                poll_seconds=2,
            )
        assert now[0] == pytest.approx(
            10.0 + container_support.LIFECYCLE_TIMEOUT_SECONDS
        )


def test_task7_enforced_timeout_budget_fits_required_ci_lane() -> None:
    assert container_support.COMPOSE_UP_TIMEOUT_SECONDS == 480
    assert container_support.HEALTH_TIMEOUT_SECONDS == 60
    assert container_support.DIAGNOSTIC_TIMEOUT_SECONDS == 30
    assert container_support.COMPOSE_CLEANUP_TIMEOUT_SECONDS == 120
    assert container_support.LIFECYCLE_TIMEOUT_SECONDS == 840
    assert container_support.MAX_COMPOSE_LIFECYCLE_SECONDS == 960
    assert container_support.REQUIRED_DOCKER_LIFECYCLE_COUNT == 3
    assert container_support.MAX_COMPOSE_LIFECYCLE_SECONDS == (
        container_support.LIFECYCLE_TIMEOUT_SECONDS
        + container_support.COMPOSE_CLEANUP_TIMEOUT_SECONDS
    )
    assert container_support.MAX_COMPOSE_LIFECYCLE_SECONDS * 3 == 2880
    assert 60 * 60 - container_support.MAX_COMPOSE_LIFECYCLE_SECONDS * 3 == 720
