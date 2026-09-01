from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RELEASE = PROJECT_ROOT / "docs/releases/v0.1.9.md"
RELEASE_DATE = "2026-09-01"
HISTORICAL_V018_SHA256 = (
    "8f3656b2ba0ce4b4efdc5c914833ddabea1d38a7b07ab87c96cf645c12a64d95"
)
H2_ORDER = (
    "Supported Surface",
    "Changes",
    "Compatibility And Migration",
    "Rollback",
    "Required Verification",
    "Known Limits",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sections(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"^## (.+)$", text, re.MULTILINE))
    assert tuple(match.group(1) for match in matches) == H2_ORDER
    return {
        match.group(1): text[
            match.end() : matches[index + 1].start()
            if index + 1 < len(matches)
            else len(text)
        ]
        for index, match in enumerate(matches)
    }


def test_v0_1_9_current_release_identity_is_consistent() -> None:
    package = json.loads(
        (PROJECT_ROOT / "frontend/package.json").read_text(encoding="utf-8")
    )
    lock = json.loads(
        (PROJECT_ROOT / "frontend/package-lock.json").read_text(encoding="utf-8")
    )

    assert (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip() == "0.1.9"
    assert package["version"] == "0.1.9"
    assert lock["version"] == "0.1.9"
    assert lock["packages"][""]["version"] == "0.1.9"
    assert RELEASE.exists()


def test_v0_1_9_moves_the_complete_current_main_inventory() -> None:
    changelog = _read(PROJECT_ROOT / "CHANGELOG.md")
    unreleased = changelog.split("## [Unreleased]", 1)[1].split(
        "## [0.1.9] - 2026-09-01", 1
    )[0]
    release = changelog.split("## [0.1.9] - 2026-09-01", 1)[1].split(
        "## [0.1.8] - 2026-07-30", 1
    )[0]

    assert not unreleased.strip()
    assert tuple(re.findall(r"^### (.+)$", release, re.MULTILINE)) == (
        "Frontend lock/security maintenance",
        "Native showcase/provenance",
        "Node 22/24 support matrix",
        "Frontend test-patch/provenance refresh",
        "Blocked failure diagnosis",
        "Live Backend research question input",
        "Known-run GET-only reattachment",
    )
    normalized = " ".join(release.split())
    for phrase in (
        "changes already merged on the current default branch after stable `v0.1.8`",
        "frontend transitive security locks",
        "native deterministic Static Demo showcase frames",
        "Node.js 22/24 support matrix",
        "frontend test patches",
        "blocked-failure diagnosis",
        "bounded user-authored generic research question",
        "known `run_id` can be re-entered after a page refresh",
        "not a promise of a future release",
    ):
        assert phrase in normalized


def test_v0_1_9_release_record_is_public_neutral_and_closed() -> None:
    notes = _read(RELEASE)
    assert notes.startswith(
        "# Decision Research Agent v0.1.9\n\n"
        f"Release preparation date: {RELEASE_DATE}."
    )
    sections = {key: " ".join(value.split()) for key, value in _sections(notes).items()}

    for phrase in (
        "current default-branch additions after the immutable stable `v0.1.8`",
        "provider-free",
        "local-only",
        "application database remains business authority",
        "Human review and release authority",
        "review_required",
        "not_delivered",
    ):
        assert phrase in sections["Supported Surface"]

    for phrase in (
        "frontend transitive security locks",
        "native deterministic Static Demo showcase frames",
        "Node.js 22/24 support matrix",
        "frontend test patches",
        "blocked-failure diagnosis",
        "bounded user-authored generic research question",
        "GET-only",
    ):
        assert phrase in sections["Changes"]

    for phrase in (
        "No runtime API, schema, domain, or authority migration",
        "same key and byte-equivalent request",
        "does not reconstruct an ambiguous POST",
        "v0.1.8 remains immutable",
    ):
        assert phrase in sections["Compatibility And Migration"]

    for phrase in (
        "Stop recommending v0.1.9",
        "Do not move the published `v0.1.8` tag",
        "Preserve the failed source as immutable and not delivered",
    ):
        assert phrase in sections["Rollback"]

    for command in (
        "python scripts/check_dependency_compatibility.py",
        "python scripts/agent_evaluation_gate.py check",
        "python scripts/secure_local_runtime_proof.py check",
        "PYTHON_DOTENV_DISABLED=1 python scripts/downstream_consumer_contract.py check --input docs/evidence/downstream-consumer-contract-v1.json",
        'python -m pytest -q -m "not docker"',
        'python -m pytest -q -m docker',
        "npm ci",
        "npm run test",
        "npm run lint",
        "npm run build",
        "npm audit --audit-level=moderate",
        "python scripts/check_canonical_identity.py --root .",
        "python scripts/final_presentation_audit.py --root .",
    ):
        assert command in sections["Required Verification"]

    for phrase in (
        "does not claim that a `v0.1.9` tag, GitHub Release, or publication",
        "No real-provider research, hosted Console operation, deployment, business-impact",
        "does not claim research quality, provider quality, or adoption",
        "the failed source remains immutable and not delivered",
    ):
        assert phrase in sections["Known Limits"]


def test_v0_1_9_preserves_the_historical_v0_1_8_release_note() -> None:
    historical = PROJECT_ROOT / "docs/releases/v0.1.8.md"
    assert sha256(historical.read_bytes()).hexdigest() == HISTORICAL_V018_SHA256


def test_v0_1_9_is_discoverable_from_bilingual_and_docs_indexes() -> None:
    for relative_path in ("README.md", "README_CN.md"):
        text = _read(PROJECT_ROOT / relative_path)
        assert "[v0.1.9 Release Notes](docs/releases/v0.1.9.md)" in text

    docs_index = _read(PROJECT_ROOT / "docs/README.md")
    assert "[v0.1.9 Release Notes](releases/v0.1.9.md)" in docs_index
    assert "[v0.1.8 Release Notes](releases/v0.1.8.md)" in docs_index


def test_v0_1_9_plan_is_public_neutral_and_discoverable() -> None:
    superpowers_index = _read(PROJECT_ROOT / "docs/superpowers/README.md")
    plan = _read(
        PROJECT_ROOT
        / "docs/superpowers/plans/2026-09-01-v0-1-9-bounded-release-implementation-plan.md"
    )
    assert "Decision Research Agent v0.1.9" in plan
    assert "Career" not in plan
    assert "threadId" not in plan
    assert "codex/memories" not in plan
    assert "## Current v0.1.9 Release Records" in superpowers_index
    assert "## Historical v0.1.8 Release Records" in superpowers_index
    assert "## Current v0.1.8 Release Records" not in superpowers_index
    assert "2026-09-01-v0-1-9-bounded-release-implementation-plan.md" in superpowers_index
