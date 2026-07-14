from __future__ import annotations

import json
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet


PROJECT_ROOT = Path(__file__).resolve().parents[2]
V010_RELEASE_NOTES = PROJECT_ROOT / "docs" / "releases" / "v0.1.0.md"
V011_RELEASE_NOTES = PROJECT_ROOT / "docs" / "releases" / "v0.1.1.md"
PYTEST_FIXED_FLOOR = "9.0.3"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_current_release_version_is_consistent() -> None:
    package = json.loads(_read(PROJECT_ROOT / "frontend" / "package.json"))
    lock = json.loads(_read(PROJECT_ROOT / "frontend" / "package-lock.json"))

    assert _read(PROJECT_ROOT / "VERSION").strip() == "0.1.1"
    assert package["version"] == "0.1.1"
    assert lock["version"] == "0.1.1"
    assert lock["packages"][""]["version"] == "0.1.1"


def test_changelog_orders_unreleased_before_complete_v0_1_1_entry() -> None:
    changelog = _read(PROJECT_ROOT / "CHANGELOG.md")
    unreleased_heading = "## [Unreleased]"
    v0_1_1_heading = "## [0.1.1] - 2026-07-13"
    v0_1_0_heading = "## [0.1.0] - 2026-06-28"

    assert unreleased_heading in changelog
    assert v0_1_1_heading in changelog
    assert v0_1_0_heading in changelog
    assert changelog.index(unreleased_heading) < changelog.index(v0_1_1_heading)
    v0_1_1 = changelog.split(v0_1_1_heading, 1)[1].split(v0_1_0_heading, 1)[0]
    for phrase in (
        "structured Tool Client",
        "Agent Research Operations Console",
        "downstream consumer",
        "eight fixed cases",
        "six policy evaluators",
        "frontend and CI maintenance",
    ):
        assert phrase in v0_1_1


def test_changelog_contains_v0_1_0_release_entry() -> None:
    changelog = _read(PROJECT_ROOT / "CHANGELOG.md")

    assert "## [Unreleased]" in changelog
    assert "## [0.1.0]" in changelog
    assert "Backend-and-CLI release" in changelog
    assert "Breaking Changes" in changelog
    assert "Pre-v0.1.0 compatibility aliases and task/thread routes were removed" in changelog


def test_security_policy_matches_current_release_surface() -> None:
    security = _read(PROJECT_ROOT / "SECURITY.md")

    required = [
        "Decision Research Agent v0.1.1",
        "Agent Research Operations Console",
        "does not accept credentials",
        "not a publicly hosted service",
        "API keys must be provided through environment variables",
        "Do not disclose suspected vulnerabilities in public Issues or pull requests.",
        "LangSmith traces are privacy-first by default",
    ]
    for phrase in required:
        assert phrase in security


def test_release_notes_document_breaking_migration_and_rollback() -> None:
    notes = _read(V010_RELEASE_NOTES)

    required = [
        "# Decision Research Agent v0.1.0",
        "## Supported Surface",
        "backend-and-CLI release",
        "## Breaking Changes",
        "Pre-v0.1.0 compatibility aliases and task/thread routes were removed",
        "No frontend service is shipped",
        "Markdown-only delivery",
        "## Migration",
        "cp .env.example .env",
        "python scripts/run_identity_migration.py --db",
        "python scripts/retire_legacy_database.py --database",
        "DECISION_RESEARCH_AGENT_DB_PATH",
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL=false",
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION=false",
        "## Rollback",
        "restore the application database, checkpoint database, and output storage together",
        "## Verification",
    ]
    for phrase in required:
        assert phrase in notes


def test_release_notes_do_not_claim_unrun_final_gate() -> None:
    notes = _read(V010_RELEASE_NOTES)

    forbidden = [
        "release tag created",
        "GitHub Release published",
        "Docker gate passed",
        "deployment completed",
    ]
    for phrase in forbidden:
        assert phrase not in notes


def test_v0_1_1_release_notes_cover_surface_compatibility_and_limits() -> None:
    notes = _read(V011_RELEASE_NOTES)

    required = [
        "# Decision Research Agent v0.1.1",
        "## Supported Surface",
        "## Changes",
        "structured Tool Client",
        "Agent Research Operations Console",
        "Static Demo",
        "loopback-only",
        "downstream consumer",
        "eight fixed cases",
        "six evaluators",
        "## Compatibility And Migration",
        "No runtime API, schema, or database migration",
        "## Rollback",
        "## Required Verification",
        "## Known Limits",
        "does not accept credentials",
        "does not own review, verification, or publication authority",
        "not a live-provider run",
        "not production SLA",
        "not answer-quality accuracy",
        "not provider measurements",
    ]
    for phrase in required:
        assert phrase in notes


def test_v0_1_1_release_is_discoverable_without_claiming_publication() -> None:
    readme = _read(PROJECT_ROOT / "README.md")
    readme_cn = _read(PROJECT_ROOT / "README_CN.md")
    docs_index = _read(PROJECT_ROOT / "docs" / "README.md")
    combined = "\n".join((readme, readme_cn, docs_index, _read(V011_RELEASE_NOTES)))

    assert "[v0.1.1 Release Notes](docs/releases/v0.1.1.md)" in readme
    assert "[v0.1.1 Release Notes](docs/releases/v0.1.1.md)" in readme_cn
    assert "[v0.1.1 Release Notes](releases/v0.1.1.md)" in docs_index
    assert "[v0.1.0 Release Notes](docs/releases/v0.1.0.md)" in readme
    assert "[v0.1.0 Release Notes](docs/releases/v0.1.0.md)" in readme_cn
    assert "[v0.1.0 Release Notes](releases/v0.1.0.md)" in docs_index
    for forbidden in (
        "v0.1.1 is published",
        "release tag created",
        "GitHub Release published",
        "deployment completed",
    ):
        assert forbidden not in combined


def test_pytest_dependency_declaration_uses_security_fixed_floor() -> None:
    pytest_requirements = []
    for raw_line in _read(PROJECT_ROOT / "requirements.txt").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        requirement = Requirement(line)
        if requirement.name == "pytest":
            pytest_requirements.append(requirement)

    assert pytest_requirements
    for python_version in ("3.11", "3.12", "3.13"):
        environment = default_environment()
        environment["python_version"] = python_version
        applicable = [
            requirement
            for requirement in pytest_requirements
            if requirement.marker is None or requirement.marker.evaluate(environment)
        ]
        assert len(applicable) == 1, python_version
        assert PYTEST_FIXED_FLOOR in applicable[0].specifier


def test_python_3_11_release_constraints_pin_security_fixed_pytest() -> None:
    constraints = {}
    for raw_line in _read(PROJECT_ROOT / "constraints.txt").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        requirement = Requirement(line)
        pins = [
            specifier.version
            for specifier in requirement.specifier
            if specifier.operator == "=="
        ]
        if pins:
            constraints[requirement.name] = pins[-1]

    assert constraints["pytest"] == PYTEST_FIXED_FLOOR
    assert PYTEST_FIXED_FLOOR in SpecifierSet(f"=={constraints['pytest']}")
