from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _section(text: str, heading: str, next_heading: str | None = None) -> str:
    start = text.index(heading)
    if next_heading is None:
        return text[start:]
    end = text.index(next_heading, start + len(heading))
    return text[start:end]


def _workflow_step_names(workflow: str) -> tuple[str, ...]:
    return tuple(
        match.group(1).strip()
        for match in re.finditer(r"^\s+- name:\s+(.+?)\s*$", workflow, re.MULTILINE)
    )


def _assert_talent_public_truth(agents: str) -> None:
    purpose = _section(agents, "## Project Purpose", "## Source Of Truth")
    assert "ready for separate human value review" in purpose
    assert "does not record a passed human value gate" in purpose
    assert "fixed-sample Talent benchmark whose value gate passed" not in agents


def test_talent_claim_matches_executable_fixed_value() -> None:
    producer = _read("scripts/talent_value_gate_runner.py")
    benchmark = _read("benchmarks/talent-hiring-signal-v1/README.md")
    agents = _read("AGENTS.md")

    assert '"passed": False' in producer
    assert '"ready_for_human_review": ready' in producer
    assert "`value_gate.passed=false`" in benchmark
    assert "human value decisions remain separate" in benchmark
    _assert_talent_public_truth(agents)

    corrected = agents
    mutated = re.sub(
        r"- A fixed-sample Talent benchmark that can become\n"
        r"  ready for separate human value review when structural checks pass\.\n"
        r"- The benchmark producer keeps `value_gate\.passed=false`; the repository\n"
        r"  does not record a passed human value gate\.",
        "- A fixed-sample Talent benchmark whose value gate passed.",
        corrected,
        count=1,
    )
    assert mutated != corrected
    with pytest.raises(AssertionError):
        _assert_talent_public_truth(mutated)


def test_evidence_index_classifies_each_retained_artifact_once() -> None:
    evidence = _read("docs/evidence/README.md")
    headings = (
        "## Required Deterministic CI/Release Baseline",
        "## Optional Operator/Workflow Proof",
        "## Historical Reviewed Record",
        "## Absent Future Evidence",
    )
    positions = tuple(evidence.index(heading) for heading in headings)
    assert positions == tuple(sorted(positions))

    required = _section(evidence, headings[0], headings[1])
    optional = _section(evidence, headings[1], headings[2])
    historical = _section(evidence, headings[2], headings[3])
    absent = _section(evidence, headings[3])
    classes = (required, optional, historical, absent)

    required_files = {
        "agent-evaluation-regression-v1.json",
        "agent-evaluation-regression-v1.md",
        "downstream-consumer-contract-v1.json",
        "run-creation-idempotency-v1.json",
        "run-creation-idempotency-v1.md",
        "run-dispatch-reconciliation-v1.json",
        "run-dispatch-reconciliation-v1.md",
        "run-failure-cause-v1.json",
        "run-failure-cause-v1.md",
        "secure-local-runtime-v1.json",
        "secure-local-runtime-v1.md",
    }
    for filename in required_files:
        assert f"]({filename})" in required
        assert all(f"]({filename})" not in section for section in classes[1:])

    assert "](durable-hitl-gate-report.json)" in optional
    assert "disabled by default" in optional
    assert all(
        "](durable-hitl-gate-report.json)" not in section
        for section in (required, historical, absent)
    )

    for filename in ("real-source-proof.json", "real-source-proof.md"):
        assert f"]({filename})" in historical
        assert all(
            f"]({filename})" not in section
            for section in (required, optional, absent)
        )
    for phrase in (
        "not a current deterministic release gate",
        "not comprehensive truth verification",
    ):
        assert phrase in historical

    for filename in (
        "bounded-live-producer-v1.json",
        "bounded-live-producer-v1.md",
    ):
        assert filename in absent
        assert all(filename not in section for section in classes[:3])
    assert "No live report is committed" in absent

    assert (
        "Directory presence does not confer verification or current release authority"
        in evidence
    )

    indexed_targets = Counter(
        target
        for target in re.findall(r"\]\(([^)]+)\)", evidence)
        if "/" not in target
    )
    retained = {
        path.name
        for path in (ROOT / "docs/evidence").iterdir()
        if path.is_file()
        and path.name != "README.md"
        and path.suffix in {".json", ".md"}
    }
    assert set(indexed_targets) & retained == retained
    assert all(indexed_targets[filename] == 1 for filename in retained)


def test_readmes_distinguish_selected_local_checks_from_required_ci_proofs() -> None:
    readme = _read("README.md")
    readme_cn = _read("README_CN.md")
    workflow = _read(".github/workflows/ci.yml")

    english = _section(readme, "## Verification", "## Documentation")
    chinese = _section(readme_cn, "## 验证", "## 文档")
    assert "selected local verification subset" in english
    assert "not the full required CI proof inventory" in english
    assert "选定的本地验证子集" in chinese
    assert "并非完整的 required CI proof 清单" in chinese

    proof_labels = {
        "Agent evaluation regression gate",
        "Run creation idempotency proof",
        "Run dispatch reconciliation proof",
        "Run failure cause proof",
        "Secure local runtime proof",
        "Bounded live producer contract check",
    }
    for label in proof_labels:
        assert label in english
        assert label in chinese

    required_steps = {
        "Run deterministic Agent evaluation gate",
        "Run deterministic run creation idempotency proof",
        "Run deterministic run dispatch reconciliation proof",
        "Run failure cause proof",
        "Run secure local runtime proof",
        "Run bounded live producer contract check",
    }
    assert required_steps.issubset(set(_workflow_step_names(workflow)))

    required_scripts = {
        "agent_evaluation_gate.py",
        "run_creation_idempotency_proof.py",
        "run_dispatch_reconciliation_proof.py",
        "run_failure_cause_proof.py",
        "secure_local_runtime_proof.py",
        "bounded_live_producer_proof.py",
    }
    for script in required_scripts:
        assert script in english
        assert script in chinese

    assert "Required pytest covers downstream fixture/CLI behavior" in english
    assert "required pytest 覆盖 downstream fixture/CLI behavior" in chinese
    assert "not an independent top-level workflow step" in english
    assert "没有独立的 top-level workflow step" in " ".join(chinese.split())
    for section in (english, chinese):
        assert "every useful local command is a dedicated CI step" not in section
