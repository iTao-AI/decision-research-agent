from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_vue_frontend_assets_are_retired():
    assert not (ROOT / "frontend").exists()
    assert not (ROOT / "Dockerfile.frontend").exists()
    assert not (ROOT / "nginx.conf").exists()


def test_compose_is_backend_only():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())

    assert "frontend" not in compose["services"]
    assert compose["services"]["backend"]["build"]["dockerfile"] == "Dockerfile.backend"


def test_ci_has_no_frontend_job_or_node_build():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())

    assert "retired-ui" not in workflow["jobs"]
    assert all(
        job.get("name") != "Frontend Build"
        for job in workflow["jobs"].values()
    )
    serialized = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "setup-node" not in serialized
    assert "npm " not in serialized


def test_dependabot_no_longer_tracks_frontend_npm():
    config = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text())

    updates = config["updates"]
    assert all(entry.get("package-ecosystem") != "npm" for entry in updates)
    assert all(entry.get("directory") != "/frontend" for entry in updates)
