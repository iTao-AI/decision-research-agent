from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RELEASE_DATE = "2026-07-29"
V017_RELEASE_NOTES = PROJECT_ROOT / "docs" / "releases" / "v0.1.7.md"
V017_H2_ORDER = (
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
    "v0.1.6.md": "0cb73ea51e8aae8d4e997a0225a31439dbc11b2977692d3510b8d33d1963552e",
}
REQUIRED_VERIFICATION_COMMANDS = (
    "python scripts/agent_evaluation_gate.py check",
    "python scripts/agent_evaluation_v2_gate.py check",
    "python scripts/evidence_gated_loop_gate.py check",
    "python scripts/run_creation_idempotency_proof.py check",
    "python scripts/run_dispatch_reconciliation_proof.py check",
    "python scripts/run_failure_cause_proof.py check",
    "python scripts/secure_local_runtime_proof.py check",
    "python scripts/bounded_live_producer_proof.py check",
    "python scripts/downstream_consumer_contract.py check",
    "python scripts/run_execution_recovery_proof.py check",
    'python -m pytest -q -m "not docker"',
    "python -m pytest -q -m docker",
    "python scripts/check_canonical_identity.py --root .",
    "python scripts/final_presentation_audit.py --root .",
    "npm ci",
    "npm run test",
    "npm run lint",
    "npm run build",
    "npm audit --audit-level=moderate",
)
PREMATURE_CLAIM_PATTERNS = (
    r"\bv0\.1\.7 is published\b",
    r"\bv0\.1\.7 tag (?:has been |was )?(?:created|published)\b",
    r"\bgithub release (?:has been |was )?published\b",
    r"\barchive smoke (?:has |was )?(?:passed|completed)\b",
    r"\bdeployment (?:has been |was )?completed\b",
    r"\blive-provider strict success (?:has been |was )?"
    r"(?:achieved|completed|demonstrated|proved)\b",
    r"\b(?:achieved|completed|demonstrated|proved) "
    r"live-provider strict success\b",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _collapsed(text: str) -> str:
    return " ".join(text.split())


def _sections(notes: str) -> dict[str, str]:
    matches = list(re.finditer(r"^## (.+)$", notes, re.MULTILINE))
    assert tuple(match.group(1) for match in matches) == V017_H2_ORDER
    return {
        match.group(1): notes[
            match.end() :
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(notes)
        ]
        for index, match in enumerate(matches)
    }


def test_v0_1_7_version_identity_is_consistent() -> None:
    package = json.loads(_read(PROJECT_ROOT / "frontend/package.json"))
    lock = json.loads(_read(PROJECT_ROOT / "frontend/package-lock.json"))
    assert _read(PROJECT_ROOT / "VERSION").strip() == "0.1.7"
    assert package["version"] == "0.1.7"
    assert lock["version"] == "0.1.7"
    assert lock["packages"][""]["version"] == "0.1.7"
    assert V017_RELEASE_NOTES.exists()


def test_v0_1_7_release_notes_have_closed_sections() -> None:
    notes = _read(V017_RELEASE_NOTES)
    sections = {key: _collapsed(value) for key, value in _sections(notes).items()}
    assert notes.startswith(
        "# Decision Research Agent v0.1.7\n\n"
        f"Release preparation date: {RELEASE_DATE}."
    )
    supported = sections["Supported Surface"]
    for phrase in (
        "Online execution emits privacy-safe evidence",
        "provider-free offline evaluation",
        "humans own release and rollback decisions",
        "startup convergence protects application state after crashes",
        "Application database state remains business authority",
        "LangGraph checkpoints remain execution-position state",
        "Observation and optional tracing remain diagnostic",
        "does not mutate runtime state or authorize its own release",
        "Context Reliability Regression v1",
        "privacy-safe observation",
        "Agent Evaluation Sensitivity Gate v2",
        "generic-strict-citation@1",
        "Evidence-Gated Loop Kernel v1",
        "Crash-Safe Startup Convergence v1",
    ):
        assert phrase in supported
    for phrase in (
        "Context Reliability Regression v1",
        "privacy-safe observation",
        "Agent Evaluation Sensitivity Gate v2",
        "generic-strict-citation@1",
        "Evidence-Gated Loop Kernel v1",
        "Crash-Safe Startup Convergence v1",
    ):
        assert phrase in sections["Changes"]
    for phrase in (
        "dra.downstream-consumer.v1",
        "commit-based producer tuple",
        "Raw observation",
        "010_run_execution_recovery",
        "stopped writers",
        "ragflow-sdk 0.13.0",
        "pytest==9.0.3",
    ):
        assert phrase in sections["Compatibility And Migration"]
    for phrase in (
        "bfd744a5611c7673d9385a45bed0131d6cb47655",
        "complete pre-010 backup",
        "does not prove an unrestricted downgrade",
    ):
        assert phrase in sections["Rollback"]
    for command in REQUIRED_VERIFICATION_COMMANDS:
        assert command in sections["Required Verification"]
        for heading, body in sections.items():
            if heading != "Required Verification":
                assert command not in body
    for phrase in (
        "No autonomous evolution",
        "No live-provider strict success",
        "exact resume",
        "multi-instance high availability",
        "SLA",
        "external-user adoption",
        "business impact",
        "No source truth",
        "Existing independent consumer proof does not prove acceptance",
        "observed transport artifact",
    ):
        assert phrase in sections["Known Limits"]
    lowered = notes.lower()
    for pattern in PREMATURE_CLAIM_PATTERNS:
        assert re.search(pattern, lowered) is None


def test_v0_1_7_preserves_historical_release_notes() -> None:
    for filename, expected in HISTORICAL_RELEASE_NOTE_SHA256.items():
        path = PROJECT_ROOT / "docs" / "releases" / filename
        assert sha256(path.read_bytes()).hexdigest() == expected
