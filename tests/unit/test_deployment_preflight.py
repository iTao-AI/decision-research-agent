from pathlib import Path
import inspect

from packaging.requirements import Requirement
import yaml


PROJECT_ROOT = Path(__file__).parents[2]


def test_verified_constraints_are_used_by_docker_and_ci():
    constraints = (PROJECT_ROOT / "constraints.txt").read_text(encoding="utf-8")
    dockerfile = (PROJECT_ROOT / "Dockerfile.backend").read_text(encoding="utf-8")
    ci = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "deepagents==0.6.11" in constraints
    assert "langgraph==1.2.6" in constraints
    assert "langsmith==0.8.18" in constraints
    assert "COPY requirements.txt constraints.txt ./" in dockerfile
    assert "python -m pip install --no-cache-dir --default-timeout=60 --retries=5 --upgrade pip" in dockerfile
    assert "--no-deps --no-cache-dir --default-timeout=60 --retries=5" in dockerfile
    assert "for i in $(seq 1 3)" in dockerfile
    assert "-r constraints.txt" in dockerfile
    assert "pip install --no-deps -r constraints.txt" in ci


def test_backend_image_packages_durable_hitl_gate_report():
    dockerfile = (PROJECT_ROOT / "Dockerfile.backend").read_text(encoding="utf-8")
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
    ignore_rules = dockerignore.splitlines()
    required_ignore_rules = [
        "docs/*",
        "!docs/evidence/",
        "docs/evidence/*",
        "!docs/evidence/durable-hitl-gate-report.json",
    ]

    assert all(rule in ignore_rules for rule in required_ignore_rules)
    rule_positions = [ignore_rules.index(rule) for rule in required_ignore_rules]

    assert rule_positions == sorted(rule_positions)
    assert (
        "COPY docs/evidence/durable-hitl-gate-report.json "
        "docs/evidence/durable-hitl-gate-report.json"
    ) in dockerfile
    assert "DURABLE_HITL_GATE_REPORT" not in dockerfile


def test_deepagents_compatibility_baseline_exposes_selected_capability_surface():
    from deepagents import create_deep_agent

    parameters = inspect.signature(create_deep_agent).parameters

    assert "skills" in parameters
    assert "subagents" in parameters
    assert "interrupt_on" in parameters
    assert "profile" not in parameters


def test_python_version_constraints_match_supported_dependency_sets():
    constraints = (PROJECT_ROOT / "constraints.txt").read_text(encoding="utf-8")
    requirements_text = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    requirements = {
        package: [
            Requirement(line.split("#", 1)[0].strip())
            for line in requirements_text.splitlines()
            if line.startswith(package)
        ]
        for package in ("ragflow-sdk", "pytest")
    }

    def active_versions(package: str, python_version: str) -> list[str]:
        return [
            str(requirement.specifier)
            for requirement in requirements[package]
            if requirement.marker
            and requirement.marker.evaluate({"python_version": python_version})
        ]

    assert active_versions("ragflow-sdk", "3.11") == [">=0.13.0"]
    assert active_versions("ragflow-sdk", "3.12") == [">=0.26.0"]
    assert active_versions("ragflow-sdk", "3.13") == [">=0.26.0"]
    assert active_versions("pytest", "3.11") == [">=9.0.3"]
    assert active_versions("pytest", "3.12") == [">=9.0.3"]
    assert active_versions("pytest", "3.13") == [">=9.0.3"]
    assert "ragflow-sdk==0.13.0" in constraints
    assert "pytest==9.0.3" in constraints


def test_backend_data_and_output_use_named_volumes():
    compose = yaml.safe_load((PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    assert "backend_data:/app/data" in compose["services"]["backend"]["volumes"]
    assert "backend_output:/app/output" in compose["services"]["backend"]["volumes"]
    assert "backend_data" in compose["volumes"]
    assert "backend_output" in compose["volumes"]
