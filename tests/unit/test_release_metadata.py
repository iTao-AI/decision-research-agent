from __future__ import annotations

from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RELEASE_NOTES = PROJECT_ROOT / "docs" / "releases" / "v0.1.0.md"
PYTEST_FIXED_FLOOR = "9.0.3"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_version_is_v0_1_0() -> None:
    assert _read(PROJECT_ROOT / "VERSION").strip() == "0.1.0"


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
        "Decision Research Agent v0.1.0",
        "backend-and-CLI release",
        "API keys must be provided through environment variables",
        "Do not disclose suspected vulnerabilities in public Issues or pull requests.",
        "LangSmith traces are privacy-first by default",
    ]
    for phrase in required:
        assert phrase in security


def test_release_notes_document_breaking_migration_and_rollback() -> None:
    notes = _read(RELEASE_NOTES)

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
    notes = _read(RELEASE_NOTES)

    forbidden = [
        "release tag created",
        "GitHub Release published",
        "Docker gate passed",
        "deployment completed",
    ]
    for phrase in forbidden:
        assert phrase not in notes


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
