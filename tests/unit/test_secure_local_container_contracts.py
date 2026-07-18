from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = PROJECT_ROOT / "docker-compose.yml"

REQUIRED_COMPOSE_VALUES = {
    "API_SECRET": "compose-test-only",
    "MYSQL_ROOT_PASSWORD": "root-test-only",
    "MYSQL_PASSWORD": "app-test-only",
}


def _parse_env_template(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        assert separator == "=", f"invalid env template line for {key!r}"
        assert key not in values, f"duplicate env template key: {key}"
        values[key] = value
    return values


def _write_compose_env(path: Path, values: dict[str, str]) -> None:
    path.write_text(
        "".join(f"{key}={value}\n" for key, value in sorted(values.items())),
        encoding="utf-8",
    )
    path.chmod(0o600)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def _run_compose_config(env_file: Path) -> subprocess.CompletedProcess[str]:
    scrubbed_env = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ["HOME"],
        "DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE": str(env_file),
    }
    return subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "config",
            "--quiet",
        ],
        cwd=PROJECT_ROOT,
        env=scrubbed_env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def test_compose_declares_secure_local_container_boundary() -> None:
    compose_text = COMPOSE_PATH.read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_text)
    backend = compose["services"]["backend"]
    mysql = compose["services"]["mysql"]

    assert backend["ports"] == ["127.0.0.1:8000:8000"]
    assert backend["env_file"] == [
        "${DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE:-.env}"
    ]
    assert backend["environment"]["API_SECRET"] == (
        "${API_SECRET:?Set API_SECRET for local Compose}"
    )
    assert backend["environment"]["MYSQL_HOST"] == "mysql"
    assert backend["depends_on"]["mysql"]["condition"] == "service_healthy"
    assert backend["cap_drop"] == ["ALL"]
    assert backend["security_opt"] == ["no-new-privileges:true"]

    assert mysql["environment"] == {
        "MYSQL_ROOT_PASSWORD": (
            "${MYSQL_ROOT_PASSWORD:?Set MYSQL_ROOT_PASSWORD}"
        ),
        "MYSQL_DATABASE": "${MYSQL_DATABASE:-decision_research}",
        "MYSQL_USER": "${MYSQL_USER:-decision_research}",
        "MYSQL_PASSWORD": "${MYSQL_PASSWORD:?Set MYSQL_PASSWORD}",
    }
    assert mysql["healthcheck"] == {
        "test": [
            "CMD-SHELL",
            (
                "mysqladmin ping -h 127.0.0.1 -uroot "
                '-p"$${MYSQL_ROOT_PASSWORD}" --silent'
            ),
        ],
        "interval": "5s",
        "timeout": "3s",
        "retries": 12,
        "start_period": "20s",
    }

    for variable in REQUIRED_COMPOSE_VALUES:
        assert f"${{{variable}:?" in compose_text
    assert "$${MYSQL_ROOT_PASSWORD}" in compose_text
    assert "rootpassword" not in compose_text
    assert "decision_research_password" not in compose_text


def test_environment_template_is_safe_and_non_operational() -> None:
    template = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    values = _parse_env_template(template)
    safe_values = {
        "API_SECRET": "",
        "OPENAI_API_KEY": "",
        "TAVILY_API_KEY": "",
        "LANGSMITH_TRACING": "false",
        "LANGSMITH_API_KEY": "",
        "LANGSMITH_HIDE_INPUTS": "true",
        "LANGSMITH_HIDE_OUTPUTS": "true",
        "MYSQL_ROOT_PASSWORD": "",
        "MYSQL_USER": "decision_research",
        "MYSQL_PASSWORD": "",
        "MYSQL_DATABASE": "decision_research",
        "RAGFLOW_API_KEY": "",
    }

    assert safe_values.keys() <= values.keys()
    assert {key: values[key] for key in safe_values} == safe_values
    assert {
        key: values[key]
        for key in (
            "OPENAI_BASE_URL",
            "LLM_MODEL",
            "LLM_FALLBACK_MODEL",
            "LLM_REASONING_EFFORT",
            "LLM_THINKING_MODE",
            "MYSQL_HOST",
            "MYSQL_PORT",
            "RAGFLOW_API_URL",
        )
    } == {
        "OPENAI_BASE_URL": "https://api.deepseek.com",
        "LLM_MODEL": "deepseek-v4-pro",
        "LLM_FALLBACK_MODEL": "deepseek-v4-flash",
        "LLM_REASONING_EFFORT": "max",
        "LLM_THINKING_MODE": "enabled",
        "MYSQL_HOST": "localhost",
        "MYSQL_PORT": "3306",
        "RAGFLOW_API_URL": "http://localhost:8080",
    }
    assert "your-" not in template.lower()


def test_backend_image_declares_exact_health_and_transport_contract() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile.backend").read_text(encoding="utf-8")
    expected_healthcheck = (
        "HEALTHCHECK --interval=5s --timeout=3s --start-period=20s --retries=12 \\\n"
        "  CMD [\"python\", \"-c\", \"import json; from urllib.request import "
        "urlopen; r=urlopen('http://127.0.0.1:8000/health', timeout=2); assert "
        "r.status == 200; assert json.load(r) == "
        "{'status':'ok','service':'decision-research-agent'}\"]"
    )

    assert expected_healthcheck in dockerfile
    command = json.loads(
        next(
            line.removeprefix("CMD ")
            for line in dockerfile.splitlines()
            if line.startswith("CMD [")
        )
    )
    assert command == [
        "uvicorn",
        "api.server:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--log-level",
        "warning",
    ]
    assert not any(line.strip().startswith("USER ") for line in dockerfile.splitlines())


def test_dockerignore_keeps_a_narrow_runtime_build_context() -> None:
    rules = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert set(
        (
            "data/",
            ".worktrees/",
            "frontend/",
            ".pytest_cache/",
            ".mypy_cache/",
            ".pyright/",
            ".ruff_cache/",
            ".coverage",
            ".coverage.*",
            "htmlcov/",
            ".tox/",
            ".nox/",
            ".hypothesis/",
            ".cache/",
        )
    ).issubset(rules)
    durable_hitl_allowlist = [
        "docs/*",
        "!docs/evidence/",
        "docs/evidence/*",
        "!docs/evidence/durable-hitl-gate-report.json",
    ]
    assert [rules.index(rule) for rule in durable_hitl_allowlist] == sorted(
        rules.index(rule) for rule in durable_hitl_allowlist
    )


@pytest.mark.parametrize("required_key", tuple(REQUIRED_COMPOSE_VALUES))
@pytest.mark.parametrize("missing_mode", ("missing", "empty"))
def test_compose_config_rejects_missing_or_empty_required_values(
    tmp_path: Path,
    required_key: str,
    missing_mode: str,
) -> None:
    values = {
        **REQUIRED_COMPOSE_VALUES,
        "OPENAI_API_KEY": "provider-disabled-test-only",
        "LANGSMITH_TRACING": "false",
    }
    if missing_mode == "missing":
        del values[required_key]
    else:
        values[required_key] = ""
    env_file = tmp_path / "negative.env"
    _write_compose_env(env_file, values)

    completed = _run_compose_config(env_file)
    output = completed.stdout + completed.stderr

    assert completed.returncode != 0
    assert required_key in output
    for value in values.values():
        if value:
            assert value not in output


def test_compose_config_accepts_explicit_values_in_a_scrubbed_environment(
    tmp_path: Path,
) -> None:
    values = {
        **REQUIRED_COMPOSE_VALUES,
        "OPENAI_API_KEY": "provider-disabled-test-only",
        "LANGSMITH_TRACING": "false",
    }
    env_file = tmp_path / "positive.env"
    _write_compose_env(env_file, values)

    completed = _run_compose_config(env_file)
    output = completed.stdout + completed.stderr

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    for value in values.values():
        assert value not in output


def test_container_helper_declares_isolated_bounded_lifecycles() -> None:
    durable = (
        PROJECT_ROOT / "tests" / "integration" / "test_durable_review_container.py"
    ).read_text(encoding="utf-8")
    verification = (
        PROJECT_ROOT
        / "tests"
        / "integration"
        / "test_evidence_verification_container.py"
    ).read_text(encoding="utf-8")
    combined = durable + verification

    assert "_create_isolated_compose_env" in durable
    assert "build_compose_subprocess_env" in durable
    assert '"--env-file"' in durable
    assert "DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE" in durable
    assert "COMPOSE_UP_TIMEOUT_SECONDS = 480" in durable
    assert "HEALTH_TIMEOUT_SECONDS = 60" in durable
    assert "DIAGNOSTIC_TIMEOUT_SECONDS = 30" in durable
    assert "COMPOSE_CLEANUP_TIMEOUT_SECONDS = 120" in durable
    assert "MAX_COMPOSE_LIFECYCLE_SECONDS = 690" in durable
    assert "down" in combined
    assert '"--rmi"' in combined
    assert '"local"' in combined
    assert "_ensure_compose_env_file" not in combined
    assert "os.environ.copy()" not in combined
    assert 'args.extend(["-e"' not in combined
    assert "durable-hitl-container-test-only" not in combined
    assert "verification-container-test-only" not in combined
    assert "docker system prune" not in combined
    assert "docker image prune" not in combined

    assert combined.count("def test_backend_container_restart_preserves_review_state") == 1
    assert combined.count("def test_controlled_review_cli_approve_and_reject_canary") == 1
    assert combined.count("def test_verification_to_approval_survives_container_restart") == 1
