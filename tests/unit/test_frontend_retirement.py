import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_frontend_package_declares_maintained_lts_node_contract():
    package = json.loads((ROOT / "frontend" / "package.json").read_text())

    assert package["engines"] == {
        "node": "^22.22.2 || ^24.15.0",
    }
    assert {
        name: package["devDependencies"][name]
        for name in (
            "jsdom",
            "@testing-library/jest-dom",
            "@testing-library/dom",
        )
    } == {
        "jsdom": "^30.0.1",
        "@testing-library/jest-dom": "^7.0.0",
        "@testing-library/dom": "^10.4.1",
    }


def test_frontend_lock_preserves_identity_and_testing_target_closure():
    package = json.loads((ROOT / "frontend" / "package.json").read_text())
    lock = json.loads((ROOT / "frontend" / "package-lock.json").read_text())
    root_package = lock["packages"][""]

    assert lock["name"] == package["name"] == "decision-research-agent-demo-console"
    assert lock["version"] == package["version"] == "0.1.9"
    assert root_package["name"] == package["name"]
    assert root_package["version"] == package["version"]
    assert root_package["engines"] == package["engines"]
    assert {
        name: root_package["devDependencies"][name]
        for name in (
            "jsdom",
            "@testing-library/jest-dom",
            "@testing-library/dom",
        )
    } == {
        "jsdom": "^30.0.1",
        "@testing-library/jest-dom": "^7.0.0",
        "@testing-library/dom": "^10.4.1",
    }

    assert lock["packages"]["node_modules/jsdom"]["version"] == "30.0.1"
    assert (
        lock["packages"]["node_modules/@testing-library/jest-dom"]["version"]
        == "7.0.0"
    )
    assert lock["packages"]["node_modules/@testing-library/dom"]["version"] == "10.4.1"
    assert lock["packages"]["node_modules/@testing-library/jest-dom"][
        "peerDependencies"
    ] == {"@testing-library/dom": ">=10 <11"}


def test_legacy_vue_frontend_assets_are_retired():
    assert not (ROOT / "frontend" / "vue.config.js").exists()
    assert not (ROOT / "frontend" / "src" / "main.js").exists()
    assert not (ROOT / "Dockerfile.frontend").exists()
    assert not (ROOT / "nginx.conf").exists()


def test_compose_is_backend_only():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())

    assert "frontend" not in compose["services"]
    assert compose["services"]["backend"]["build"]["dockerfile"] == "Dockerfile.backend"


def test_ci_has_frontend_demo_console_job():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())

    frontend = workflow["jobs"]["frontend"]
    assert frontend["name"] == "Frontend Demo Console (Node ${{ matrix.node-version }})"
    assert frontend["strategy"] == {
        "fail-fast": False,
        "matrix": {"node-version": ["22.22.2", "24.15.0"]},
    }

    setup_node = next(
        step for step in frontend["steps"] if step["uses"].startswith("actions/setup-node@")
    )
    assert setup_node["with"]["node-version"] == "${{ matrix.node-version }}"

    frontend_commands = [
        (step["working-directory"], step["run"])
        for step in frontend["steps"]
        if "run" in step and step.get("working-directory") == "frontend"
    ]
    assert frontend_commands == [
        ("frontend", "npm ci"),
        ("frontend", "npm run test"),
        ("frontend", "npm run lint"),
        ("frontend", "npm run build"),
    ]


def test_dependabot_tracks_frontend_npm():
    config = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text())

    updates = config["updates"]
    frontend_npm = [
        entry for entry in updates
        if entry.get("package-ecosystem") == "npm"
        and entry.get("directory") == "/frontend"
    ]

    assert frontend_npm == [
        {
            "package-ecosystem": "npm",
            "directory": "/frontend",
            "schedule": {"interval": "weekly"},
            "open-pull-requests-limit": 2,
        }
    ]
