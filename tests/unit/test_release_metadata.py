from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
V010_RELEASE_NOTES = PROJECT_ROOT / "docs" / "releases" / "v0.1.0.md"
V011_RELEASE_NOTES = PROJECT_ROOT / "docs" / "releases" / "v0.1.1.md"
V012_RELEASE_NOTES = PROJECT_ROOT / "docs" / "releases" / "v0.1.2.md"
V013_RELEASE_NOTES = PROJECT_ROOT / "docs" / "releases" / "v0.1.3.md"
V014_RELEASE_NOTES = PROJECT_ROOT / "docs" / "releases" / "v0.1.4.md"
V015_RELEASE_NOTES = PROJECT_ROOT / "docs" / "releases" / "v0.1.5.md"
V015_RELEASE_NOTES_SHA256 = (
    "61cbac951a6513a3eb8f160647b9f16b95ca6ed96a4cca8bea80786462a90b6b"
)
PYTEST_FIXED_FLOOR = "9.0.3"
V015_H2_ORDER = (
    "Supported Surface",
    "Changes",
    "Compatibility And Migration",
    "Rollback",
    "Required Verification",
    "Known Limits",
)
V015_PUBLIC_RELEASE_CORPUS = (
    PROJECT_ROOT / "CHANGELOG.md",
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "README_CN.md",
    PROJECT_ROOT / "SECURITY.md",
    PROJECT_ROOT / "docs" / "README.md",
    V015_RELEASE_NOTES,
)
V015_PREMATURE_CLAIM_PATTERNS = (
    r"\bv0\.1\.5 is published\b",
    r"\b(?:v0\.1\.5|release) tag (?:has been |was )?(?:created|published)\b",
    r"\bgithub release (?:has been |was )?published\b",
    r"\barchive smoke (?:has |was )?(?:passed|completed)\b",
    r"\bdeployment (?:has been |was )?completed\b",
    r"\blive-provider research (?:has been |was )?completed\b",
    r"\bthe live-provider research and provider-quality claims are made\b",
    r"\bthis release provides tls\b",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _collapsed(text: str) -> str:
    return " ".join(text.split())


def _v0_1_5_h2_sections(notes: str) -> dict[str, str]:
    matches = list(re.finditer(r"^## (.+)$", notes, re.MULTILINE))
    headings = tuple(match.group(1) for match in matches)
    assert headings == V015_H2_ORDER

    return {
        match.group(1): notes[
            match.end() : matches[index + 1].start()
            if index + 1 < len(matches)
            else len(notes)
        ]
        for index, match in enumerate(matches)
    }


def _assert_v0_1_5_release_notes_contract() -> None:
    notes = _read(V015_RELEASE_NOTES)
    sections = _v0_1_5_h2_sections(notes)
    normalized_sections = {
        heading: _collapsed(body) for heading, body in sections.items()
    }
    verification = normalized_sections["Required Verification"]
    known_limits = normalized_sections["Known Limits"]

    for command in (
        "python scripts/secure_local_runtime_proof.py check",
        "python scripts/agent_evaluation_gate.py check",
        'python -m pytest -q -m "not docker"',
        "npm audit --audit-level=moderate",
    ):
        assert command in verification
        for heading, body in normalized_sections.items():
            if heading != "Required Verification":
                assert command not in body

    evidence_boundary = (
        "The deterministic proof, required Docker lane, and post-publication "
        "archive smoke are separate evidence boundaries."
    )
    assert evidence_boundary in verification
    for heading, body in normalized_sections.items():
        if heading != "Required Verification":
            assert evidence_boundary not in body

    for complete_non_claim in (
        "This preparation document does not claim that a `v0.1.5` tag, GitHub "
        "Release, post-publication archive smoke, deployment, or live research "
        "has completed.",
        "This release does not provide TLS, caller identity, per-user "
        "authorization, RBAC, rate limiting, trusted-proxy handling, hosted "
        "production, or production deployment.",
        "No live-provider research or provider-quality claim is made by the "
        "deterministic proof, required Docker lane, or this release preparation.",
    ):
        assert complete_non_claim in known_limits
        for heading, body in normalized_sections.items():
            if heading != "Known Limits":
                assert complete_non_claim not in body


def _assert_v0_1_5_public_release_corpus_has_no_premature_claims() -> None:
    corpus = "\n".join(_read(path) for path in V015_PUBLIC_RELEASE_CORPUS).lower()
    for pattern in V015_PREMATURE_CLAIM_PATTERNS:
        assert re.search(pattern, corpus) is None


def test_current_release_version_is_consistent() -> None:
    package = json.loads(_read(PROJECT_ROOT / "frontend" / "package.json"))
    lock = json.loads(_read(PROJECT_ROOT / "frontend" / "package-lock.json"))

    assert _read(PROJECT_ROOT / "VERSION").strip() == "0.1.5"
    assert package["version"] == "0.1.5"
    assert lock["version"] == "0.1.5"
    assert lock["packages"][""]["version"] == "0.1.5"
    assert V015_RELEASE_NOTES.exists()
    assert sha256(V015_RELEASE_NOTES.read_bytes()).hexdigest() == V015_RELEASE_NOTES_SHA256


def test_changelog_preserves_published_release_boundary() -> None:
    changelog = _read(PROJECT_ROOT / "CHANGELOG.md")
    unreleased_heading = "## [Unreleased]"
    v0_1_5_match = re.search(
        r"^## \[0\.1\.5\] - (\d{4}-\d{2}-\d{2})$",
        changelog,
        re.MULTILINE,
    )
    assert v0_1_5_match is not None
    v0_1_5_heading = v0_1_5_match.group(0)
    v0_1_4_heading = "## [0.1.4] - 2026-07-16"
    v0_1_3_heading = "## [0.1.3] - 2026-07-14"
    v0_1_2_heading = "## [0.1.2] - 2026-07-14"
    v0_1_1_heading = "## [0.1.1] - 2026-07-13"
    v0_1_0_heading = "## [0.1.0] - 2026-06-28"

    assert unreleased_heading in changelog
    assert v0_1_5_heading in changelog
    assert v0_1_4_heading in changelog
    assert v0_1_3_heading in changelog
    assert v0_1_2_heading in changelog
    assert v0_1_1_heading in changelog
    assert v0_1_0_heading in changelog
    assert changelog.index(unreleased_heading) < changelog.index(v0_1_5_heading)
    assert changelog.index(v0_1_5_heading) < changelog.index(v0_1_4_heading)
    assert changelog.index(v0_1_4_heading) < changelog.index(v0_1_3_heading)
    assert changelog.index(v0_1_3_heading) < changelog.index(v0_1_2_heading)
    assert changelog.index(v0_1_2_heading) < changelog.index(v0_1_1_heading)
    assert changelog.index(v0_1_1_heading) < changelog.index(v0_1_0_heading)
    unreleased = changelog.split(unreleased_heading, 1)[1].split(v0_1_5_heading, 1)[0]
    bounded_producer_subsection = """### Bounded live producer evaluation

- Added a deterministic provider-free contract check and a separately
  authorized `observe-live` harness for one bounded generic scenario.
- Added a clean tracked-archive Docker lifecycle for protected create,
  application-owned persistence, backend restart, same-key replay, privilege
  inspection, and exact task-owned cleanup.
- Moved the secure-runtime precheck from the host production dependency graph
  into the exact locked backend image before service or provider startup while
  retaining the existing network, privilege, mount, and cleanup boundaries.
- No live provider observation or JSON/Markdown evidence report is committed;
  `VERSION` and the v0.1.5 release record remain unchanged."""
    assert unreleased.strip() == bounded_producer_subsection
    v0_1_5 = changelog.split(v0_1_5_heading, 1)[1].split(v0_1_4_heading, 1)[0]
    secure_runtime_subsection = """### Secure local runtime access

- Source execution now allows credential-free requests only when the direct
  peer and literal Host are both loopback; configured environments require
  the shared `X-API-Key` credential.
- CORS remains a browser boundary rather than authentication. WebSocket
  credentials are header-only, and legacy query credentials are rejected
  before run identity or connection ownership.
- The supported source launcher binds `127.0.0.1` with reload disabled and
  warning-level logging. Remote direct use requires a key and operator-owned
  TLS and is not a supported hosted deployment."""
    container_subsection = """### Secure local container delivery

- Compose now requires `API_SECRET`, `MYSQL_ROOT_PASSWORD`, and
  `MYSQL_PASSWORD`, publishes the backend and MySQL only on `127.0.0.1`, and
  keeps the MySQL root credential value out of the backend service.
- MySQL health gates backend startup; the backend declares an exact
  process/service health check. It drops all capabilities and enables
  `no-new-privileges` while retaining the root UID for existing `data` and
  `output` volume compatibility.
- Added a deterministic 16-case local contract proof and a disjoint required
  Docker lane for build, health, security inspection, named-volume restart
  persistence, bounded task-owned cleanup, and no observed provider, model, or
  tool request. This evidence does not claim TLS, identity, RBAC, hosted
  deployment, non-root operation, or provider quality."""
    assert v0_1_5.strip() == (
        f"{secure_runtime_subsection}\n\n{container_subsection}"
    )

    v0_1_4 = changelog.split(v0_1_4_heading, 1)[1].split(v0_1_3_heading, 1)[0]
    failure_cause_subsection = """### Durable run failure causes

- Added immutable application-database `run_failure_causes_v1` through
  `009_run_failure_cause_v1`; historical failed runs report `not_observed`
  without inferred diagnosis, while new terminal failures atomically persist
  bounded dispatch, execution, or finalization causes.
- Added an additive `failure_cause` field only to
  `GET /api/runs/{run_id}` and a deterministic 16-case proof.
  `GET /api/runs/{run_id}/result`, `409 run_failed`, and the frozen
  `dra.downstream-consumer.v1` fixture remain unchanged.
- The contract does not claim exactly-once execution, hard preemption,
  provider diagnosis, multi-instance high availability, or a billing record."""
    console_subsection = """### Console live authority closure

- Live Backend now renders only real service-owned run status and canonical
  result observations while Static Demo remains isolated.
- Ambiguous create reconciliation reuses the same key and byte-equivalent
  request, and a known `run_id` enables GET-only observation resume without a
  replacement create.
- The loopback-only Console still accepts no credentials and owns no review,
  verification, publication, or delivery authority. It does not claim durable
  browser intent, production deployment, exactly-once execution, or
  live-provider quality."""
    assert v0_1_4.strip() == f"{failure_cause_subsection}\n\n{console_subsection}"
    published_suffix = v0_1_4_heading + changelog.split(v0_1_4_heading, 1)[1]
    assert sha256(published_suffix.encode("utf-8")).hexdigest() == (
        "24d309bb3887af98db06622a8fcb5358c0cbdbc6c2aa7b60fa24817d810f4f81"
    )
    assert v0_1_5_match.group(1) in _read(V015_RELEASE_NOTES)

    v0_1_3 = changelog.split(v0_1_3_heading, 1)[1].split(v0_1_2_heading, 1)[0]
    durable_subsection = """### Durable run dispatch

- Added atomic `run_dispatches_v1` intent creation and migration
  `008_run_dispatch_reconciliation`, with exact verification, no backfill, and
  isolated `.pre-run-dispatch.bak` restore protection.
- Added single-node pre-execution reconciliation, exact start fencing, bounded
  asynchronous retry through three attempts, and deterministic public proof
  artifacts. `status: started` remains an acceptance acknowledgement; the
  contract does not claim exactly-once or running-execution recovery."""
    assert v0_1_3.strip() == durable_subsection

    v0_1_2 = changelog.split(v0_1_2_heading, 1)[1].split(v0_1_1_heading, 1)[0]
    assert "### Run creation reliability" in v0_1_2
    for phrase in (
        "### Durable run dispatch",
        "run_dispatches_v1",
        "008_run_dispatch_reconciliation",
    ):
        assert phrase not in v0_1_2
    for phrase in (
        "Idempotency-Key",
        "atomic replay/conflict behavior",
        "concurrent duplicate serialization",
        "Tool Client recovery after a lost response",
        "deterministic public reconciliation proof",
        "crash-before-schedule recovery",
        "exactly-once execution",
    ):
        assert phrase in v0_1_2

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
        "Decision Research Agent v0.1.5",
        "single-node",
        "run dispatch",
        "failure cause",
        "Agent Research Operations Console",
        "loopback-only",
        "does not accept credentials",
        "not a publicly hosted service",
        "API keys must be provided through environment variables",
        "Do not disclose suspected vulnerabilities in public Issues or pull requests.",
        "LangSmith traces are privacy-first by default",
    ]
    for phrase in required:
        assert phrase in security


def test_security_policy_publishes_v0_1_5_runtime_controls() -> None:
    security = _read(PROJECT_ROOT / "SECURITY.md")
    normalized = " ".join(security.split())

    assert "Decision Research Agent v0.1.5 ships" in normalized
    assert "The source template uses `API_SECRET=`" in normalized
    assert "Compose requires non-empty" in normalized
    assert "drops all backend capabilities" in normalized
    assert "root UID" in normalized
    assert "Unreleased / Current Main Security Controls" not in security


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


def test_v0_1_2_release_notes_cover_surface_compatibility_and_limits() -> None:
    notes = _read(V012_RELEASE_NOTES)

    required = [
        "# Decision Research Agent v0.1.2",
        "## Supported Surface",
        "## Changes",
        "optional `Idempotency-Key`",
        "`POST /api/runs`",
        "durable replay",
        "concurrent duplicate",
        "Tool Client",
        "lost response",
        "deterministic reconciliation proof",
        "run_idempotency_conflict",
        "run_idempotency_key_invalid",
        "run_idempotency_unavailable",
        "## Compatibility And Migration",
        "v0.1.1",
        "007_run_create_idempotency",
        "## Rollback",
        "## Required Verification",
        "## Known Limits",
        "crash_before_schedule_recovery: not_proven",
        "exactly_once_execution: not_claimed",
        "not a provider or production measurement",
    ]
    for phrase in required:
        assert phrase in notes


def test_v0_1_3_release_notes_cover_surface_compatibility_and_limits() -> None:
    notes = _read(V013_RELEASE_NOTES)

    required = [
        "# Decision Research Agent v0.1.3",
        "## Supported Surface",
        "## Changes",
        "application-owned dispatch authority",
        "before Agent invocation",
        "exact start fencing",
        "three attempts",
        "startup",
        "expired lease",
        "deterministic public proof",
        "status: started",
        "acceptance acknowledgement",
        "## Compatibility And Migration",
        "008_run_dispatch_reconciliation",
        "no backfill",
        "## Rollback",
        "## Required Verification",
        "## Known Limits",
        "exactly-once execution",
        "running execution recovery",
        "provider/tool side-effect exactly-once",
        "multi-instance high availability",
        "live-provider result",
    ]
    for phrase in required:
        assert phrase in notes


def test_v0_1_4_release_notes_cover_surface_compatibility_and_limits() -> None:
    notes = _read(V014_RELEASE_NOTES)

    required = [
        "# Decision Research Agent v0.1.4",
        "## Supported Surface",
        "## Changes",
        "Durable Run Failure Causes",
        "run_failure_causes_v1",
        "009_run_failure_cause_v1",
        "not_observed",
        "16-case",
        "Console Live Authority Closure",
        "Static Demo",
        "Live Backend",
        "Idempotency-Key",
        "GET-only",
        "canonical result",
        "## Compatibility And Migration",
        "additive",
        "## Rollback",
        "## Required Verification",
        "## Known Limits",
        "exactly-once execution",
        "hard preemption",
        "multi-instance high availability",
        "durable browser intent",
        "live-provider quality",
        "not a publicly hosted service",
    ]
    for phrase in required:
        assert phrase in notes


def test_v0_1_5_release_notes_cover_secure_local_runtime_and_limits() -> None:
    notes = _read(V015_RELEASE_NOTES)
    _assert_v0_1_5_release_notes_contract()

    required = [
        "# Decision Research Agent v0.1.5",
        "## Supported Surface",
        "## Changes",
        "## Compatibility And Migration",
        "## Rollback",
        "## Required Verification",
        "## Known Limits",
        "empty `API_SECRET`",
        "direct peer and literal Host",
        "loopback",
        "API_SECRET",
        "MYSQL_ROOT_PASSWORD",
        "MYSQL_PASSWORD",
        "127.0.0.1",
        "WebSocket",
        "X-API-Key",
        "query",
        "deterministic proof",
        "required Docker lane",
        "post-publication archive smoke",
        "root UID",
        "TLS",
        "identity",
        "RBAC",
        "hosted",
        "production deployment",
        "live-provider research",
    ]
    for phrase in required:
        assert phrase in notes


def test_v0_1_5_release_is_discoverable_without_claiming_publication() -> None:
    readme = _read(PROJECT_ROOT / "README.md")
    readme_cn = _read(PROJECT_ROOT / "README_CN.md")
    docs_index = _read(PROJECT_ROOT / "docs" / "README.md")
    assert "[v0.1.5 Release Notes](docs/releases/v0.1.5.md)" in readme
    assert "[v0.1.5 Release Notes](docs/releases/v0.1.5.md)" in readme_cn
    assert "[v0.1.5 Release Notes](releases/v0.1.5.md)" in docs_index
    assert "[v0.1.4 Release Notes](docs/releases/v0.1.4.md)" in readme
    assert "[v0.1.4 Release Notes](docs/releases/v0.1.4.md)" in readme_cn
    assert "[v0.1.4 Release Notes](releases/v0.1.4.md)" in docs_index
    assert "[v0.1.3 Release Notes](docs/releases/v0.1.3.md)" in readme
    assert "[v0.1.3 Release Notes](docs/releases/v0.1.3.md)" in readme_cn
    assert "[v0.1.3 Release Notes](releases/v0.1.3.md)" in docs_index
    assert "[v0.1.2 Release Notes](docs/releases/v0.1.2.md)" in readme
    assert "[v0.1.2 Release Notes](docs/releases/v0.1.2.md)" in readme_cn
    assert "[v0.1.2 Release Notes](releases/v0.1.2.md)" in docs_index
    assert "[v0.1.1 Release Notes](docs/releases/v0.1.1.md)" in readme
    assert "[v0.1.1 Release Notes](docs/releases/v0.1.1.md)" in readme_cn
    assert "[v0.1.1 Release Notes](releases/v0.1.1.md)" in docs_index
    assert "[v0.1.0 Release Notes](docs/releases/v0.1.0.md)" in readme
    assert "[v0.1.0 Release Notes](docs/releases/v0.1.0.md)" in readme_cn
    assert "[v0.1.0 Release Notes](releases/v0.1.0.md)" in docs_index
    assert (
        "- [v0.1.5 Release Notes](releases/v0.1.5.md) — current supported surface,"
        in docs_index
    )
    assert (
        "- [v0.1.4 Release Notes](releases/v0.1.4.md) — historical durable failure"
        in docs_index
    )
    assert (
        "- [v0.1.3 Release Notes](releases/v0.1.3.md) — historical durable run"
        in docs_index
    )
    assert (
        "- [v0.1.2 Release Notes](releases/v0.1.2.md) — historical run-creation"
        in docs_index
    )
    assert (
        "- [v0.1.1 Release Notes](releases/v0.1.1.md) — historical console,"
        in docs_index
    )
    assert "downstream-consumer and Agent evaluation contract gates." in docs_index
    assert docs_index.count("current supported surface") == 1
    assert (
        "[v0.1.4 Release Notes](releases/v0.1.4.md) — current supported surface"
        not in docs_index
    )
    _assert_v0_1_5_public_release_corpus_has_no_premature_claims()


@pytest.mark.parametrize(
    ("path", "old", "new", "contract"),
    (
        (
            V015_RELEASE_NOTES,
            "No live-provider research or provider-quality claim is made by the\n"
            "  deterministic proof, required Docker lane, or this release preparation.",
            "The live-provider research and provider-quality claims are made by the\n"
            "  deterministic proof, required Docker lane, and this release preparation.",
            _assert_v0_1_5_release_notes_contract,
        ),
        (
            V015_RELEASE_NOTES,
            "This release does not provide TLS, caller identity, per-user authorization,\n"
            "  RBAC, rate limiting, trusted-proxy handling, hosted production, or production deployment.",
            "This release provides TLS, caller identity, per-user authorization,\n"
            "  RBAC, hosted production, and production deployment.",
            _assert_v0_1_5_release_notes_contract,
        ),
        (
            V015_RELEASE_NOTES,
            "## Required Verification",
            "## Known Limits",
            _assert_v0_1_5_release_notes_contract,
        ),
        (
            PROJECT_ROOT / "SECURITY.md",
            "that are not part of v0.1.5.",
            "that are not part of v0.1.5.\n\nGitHub Release published.",
            _assert_v0_1_5_public_release_corpus_has_no_premature_claims,
        ),
    ),
    ids=(
        "positive-provider-claim",
        "positive-production-claim",
        "duplicate-known-limits-heading",
        "security-publication-claim",
    ),
)
def test_v0_1_5_release_contract_rejects_mutation(
    monkeypatch: pytest.MonkeyPatch,
    path: Path,
    old: str,
    new: str,
    contract,
) -> None:
    read_text = Path.read_text
    mutated = read_text(path, encoding="utf-8")
    assert mutated.count(old) == 1
    mutated = mutated.replace(old, new, 1)

    def mutated_read_text(self: Path, *args, **kwargs) -> str:
        if self == path:
            return mutated
        return read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", mutated_read_text)
    with pytest.raises(AssertionError):
        contract()


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
