from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RELEASE_DATE = "2026-07-24"
V016_RELEASE_NOTES = PROJECT_ROOT / "docs" / "releases" / "v0.1.6.md"
V016_H2_ORDER = (
    "Supported Surface",
    "Changes",
    "Compatibility And Migration",
    "Rollback",
    "Required Verification",
    "Known Limits",
)
HISTORICAL_RELEASE_NOTE_SHA256 = {
    "v0.1.0.md": "96088198dae7236c05f5bdc5b37f69f126f76c4e4191c7affd36a41d247b8ef2",
    "v0.1.1.md": "2debd84d4383a6335e54ff59cad3521c458698c4ca2b3eb78b4303a8933bbbf7",
    "v0.1.2.md": "4fbde856a85bd5be4ec0d38640f50119024b9dd980b86479b9d7af658789f5bb",
    "v0.1.3.md": "f1b4f34fce15463994645a7e4be0fee03cb22428541116afd96ba45e47c5431d",
    "v0.1.4.md": "2dd2b7650ce0d8f57e8f63954f49165fb1b0974cbc597cf14a414675b3aa8bba",
    "v0.1.5.md": "61cbac951a6513a3eb8f160647b9f16b95ca6ed96a4cca8bea80786462a90b6b",
}
V015_AND_EARLIER_CHANGELOG_SHA256 = (
    "8f9dae3993209cb9669ea2fe98b53450260eb7d902b14371107a3d41823c897d"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _collapsed(text: str) -> str:
    return " ".join(text.split())


def _h2_sections(notes: str) -> dict[str, str]:
    matches = list(re.finditer(r"^## (.+)$", notes, re.MULTILINE))
    assert tuple(match.group(1) for match in matches) == V016_H2_ORDER
    return {
        match.group(1): notes[
            match.end() : matches[index + 1].start()
            if index + 1 < len(matches)
            else len(notes)
        ]
        for index, match in enumerate(matches)
    }


def test_v0_1_6_version_identity_is_consistent() -> None:
    package = json.loads(_read(PROJECT_ROOT / "frontend" / "package.json"))
    lock = json.loads(_read(PROJECT_ROOT / "frontend" / "package-lock.json"))

    assert _read(PROJECT_ROOT / "VERSION").strip() == "0.1.6"
    assert package["version"] == "0.1.6"
    assert lock["version"] == "0.1.6"
    assert lock["packages"][""]["version"] == "0.1.6"
    assert V016_RELEASE_NOTES.exists()


def test_v0_1_6_changelog_freezes_unreleased_and_preserves_history() -> None:
    changelog = _read(PROJECT_ROOT / "CHANGELOG.md")
    unreleased_heading = "## [Unreleased]"
    v0_1_6_heading = f"## [0.1.6] - {RELEASE_DATE}"
    v0_1_5_heading = "## [0.1.5] - 2026-07-18"

    assert v0_1_6_heading in changelog
    assert changelog.index(unreleased_heading) < changelog.index(v0_1_6_heading)
    assert changelog.index(v0_1_6_heading) < changelog.index(v0_1_5_heading)
    unreleased = changelog.split(unreleased_heading, 1)[1].split(
        v0_1_6_heading,
        1,
    )[0]
    assert unreleased.strip() == ""

    v0_1_6 = changelog.split(v0_1_6_heading, 1)[1].split(v0_1_5_heading, 1)[0]
    for heading in (
        "### DeepSeek provider protocol",
        "### Bounded live observation evidence",
        "### Bounded live producer evaluation",
    ):
        assert v0_1_6.count(heading) == 1
    for phrase in (
        "langchain-deepseek==1.1.0",
        "not a required CI or current release baseline",
        "deterministic provider-free contract check",
        "canonical persisted artifact",
        "canonical publishable public HTTPS URLs",
        "ordered required cited domains",
    ):
        assert phrase in _collapsed(v0_1_6)

    historical_suffix = v0_1_5_heading + changelog.split(v0_1_5_heading, 1)[1]
    assert sha256(historical_suffix.encode("utf-8")).hexdigest() == (
        V015_AND_EARLIER_CHANGELOG_SHA256
    )
    for filename, expected_sha256 in HISTORICAL_RELEASE_NOTE_SHA256.items():
        path = PROJECT_ROOT / "docs" / "releases" / filename
        assert sha256(path.read_bytes()).hexdigest() == expected_sha256


def test_v0_1_6_release_notes_cover_truth_verification_and_non_claims() -> None:
    assert V016_RELEASE_NOTES.exists()
    notes = _read(V016_RELEASE_NOTES)
    sections = _h2_sections(notes)
    normalized = {heading: _collapsed(body) for heading, body in sections.items()}
    changes = normalized["Changes"]
    compatibility = normalized["Compatibility And Migration"]
    verification = normalized["Required Verification"]
    known_limits = normalized["Known Limits"]

    assert notes.startswith(
        "# Decision Research Agent v0.1.6\n\n"
        f"Release preparation date: {RELEASE_DATE}."
    )
    for phrase in (
        "bounded live producer evaluation",
        "provider-free required gate",
        "langchain-deepseek",
        "ChatDeepSeek",
        "canonical artifact completion",
        "bounded operator diagnostics",
        "generic researcher",
        "network-search runtime caps",
        "nested Evidence capture",
        "Evidence finalization",
        "source admission",
        "required-domain request alignment",
        "Historical Reviewed Record",
        "public truth",
        "proof taxonomy",
        "CI portability repairs",
    ):
        assert phrase in changes

    for phrase in (
        "No API schema",
        "database schema",
        "migration",
        "Evidence schema",
        "dependency",
        "Docker",
        "Compose",
    ):
        assert phrase in compatibility

    for command in (
        "python scripts/agent_evaluation_gate.py check",
        "python scripts/run_creation_idempotency_proof.py check",
        "python scripts/run_dispatch_reconciliation_proof.py check",
        "python scripts/run_failure_cause_proof.py check",
        "python scripts/secure_local_runtime_proof.py check",
        "python scripts/bounded_live_producer_proof.py check",
        'python -m pytest -q -m "not docker"',
        "python -m pytest -q -m docker",
        "python scripts/check_canonical_identity.py --root .",
        "python scripts/final_presentation_audit.py",
        "npm ci",
        "npm run test",
        "npm run lint",
        "npm run build",
        "npm audit --audit-level=moderate",
    ):
        assert command in verification

    for phrase in (
        "not a required CI or current release baseline",
        "source truth",
        "research quality",
        "provider quality",
        "provider billing",
        "exactly-once",
        "production readiness",
        "SLA",
        "external users",
        "business adoption",
        "Night Voyager live integration",
        "cross-project business closure",
        "immutable v0.1.6 release",
    ):
        assert phrase in known_limits
