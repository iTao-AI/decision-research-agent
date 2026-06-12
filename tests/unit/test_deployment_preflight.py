from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).parents[2]


def test_verified_constraints_are_used_by_docker_and_ci():
    constraints = (PROJECT_ROOT / "constraints.txt").read_text(encoding="utf-8")
    dockerfile = (PROJECT_ROOT / "Dockerfile.backend").read_text(encoding="utf-8")
    ci = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "deepagents==0.5.8" in constraints
    assert "langgraph==1.2.2" in constraints
    assert "langsmith==0.8.3" in constraints
    assert "COPY requirements.txt constraints.txt ./" in dockerfile
    assert "pip install --no-cache-dir -r requirements.txt -c constraints.txt" in dockerfile
    assert "pip install -r requirements.txt -c constraints.txt" in ci


def test_backend_data_and_output_use_named_volumes():
    compose = yaml.safe_load((PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    assert "backend_data:/app/data" in compose["services"]["backend"]["volumes"]
    assert "backend_output:/app/output" in compose["services"]["backend"]["volumes"]
    assert "backend_data" in compose["volumes"]
    assert "backend_output" in compose["volumes"]
