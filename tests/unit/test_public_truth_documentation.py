from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_readmes_publish_equivalent_bounded_loop_kernel_claim() -> None:
    english = _read("README.md")
    chinese = _read("README_CN.md")
    for text in (english, chinese):
        assert "Evidence-Gated Loop Kernel" in text
        assert "provider-free" in text
        assert "three reviewed" in text or "三个已审查" in text
        assert "accept" in text or "接受" in text
        assert "reject" in text or "拒绝" in text
        assert "no-change" in text or "不修改" in text
        assert "release" in text or "发布" in text
        assert "rollback" in text or "回滚" in text
        assert "v0.1.6" in text


def test_ci_runs_loop_after_v2_and_before_remaining_proofs() -> None:
    text = _read(".github/workflows/ci.yml")
    v2 = "python scripts/agent_evaluation_v2_gate.py check"
    loop = "python scripts/evidence_gated_loop_gate.py check"
    next_gate = "python scripts/run_creation_idempotency_proof.py check"
    assert text.index(v2) < text.index(loop) < text.index(next_gate)
    assert text.count(loop) == 1
    assert "PYTHON_DOTENV_DISABLED: '1'" in text


def test_crash_safe_recovery_is_unreleased_linked_and_provider_free() -> None:
    readme = _read("README.md")
    chinese = _read("README_CN.md")
    changelog = _section(_read("CHANGELOG.md"), "## [Unreleased]", "## [0.1.6]")
    docs_index = _read("docs/README.md")
    superpowers = _read("docs/superpowers/README.md")
    for text in (readme, chinese, changelog):
        assert "run_execution_recovery_proof.py check" in text
        assert "provider-free" in text
        assert "startup-only" in text
        assert "one-hop" in text
        assert "release" in text.lower() or "发布" in text
    for target in (
        "operations/run-execution-recovery.md",
        "superpowers/specs/2026-07-28-crash-safe-agent-run-recovery-v1-design.md",
        "superpowers/plans/2026-07-29-crash-safe-startup-convergence-v1-implementation-plan.md",
    ):
        assert target in docs_index
    assert "2026-07-28-crash-safe-agent-run-recovery-v1-design.md" in superpowers
    assert (
        "2026-07-29-crash-safe-startup-convergence-v1-implementation-plan.md"
        in superpowers
    )
    assert "released in v0.1.7" not in changelog


def test_recovery_getting_started_and_tool_client_truth_is_copyable() -> None:
    getting_started = _read("docs/getting-started.md")
    integration = _read("docs/AGENT_INTEGRATION.md")
    combined = " ".join((getting_started + "\n" + integration).split())
    for literal in (
        ': "${SOURCE_RUN_ID:?set the immutable failed source run ID}"',
        ': "${RECOVERY_KEY:?persist a high-entropy recovery key before POST}"',
        ': "${DECISION_RESEARCH_AGENT_API_KEY:?set the configured local API key}"',
        "--run-id \"${SOURCE_RUN_ID}\"",
        "--idempotency-key \"${RECOVERY_KEY}\"",
        "90 seconds",
        "2 minutes",
        "not latency",
        "not",
        "SLA",
    ):
        assert literal in combined


def test_loop_kernel_unreleased_truth_and_readme_contract() -> None:
    changelog = _read("CHANGELOG.md")
    unreleased = _section(changelog, "## [Unreleased]", "## [0.1.6]")
    normalized = " ".join(unreleased.split())
    assert "Evidence-Gated Loop Kernel" in unreleased
    assert "provider-free" in unreleased
    assert "release remains on hold" in normalized
    assert "not runtime self-modification" in normalized
    for text in (_read("README.md"), _read("README_CN.md")):
        for required in (
            "python scripts/evidence_gated_loop_gate.py check",
            "[Evidence-Gated Loop Kernel]"
            "(docs/reference/evidence-gated-loop-kernel.md)",
            "[canonical JSON]"
            "(docs/evidence/evidence-gated-loop-kernel-v1.json)",
            "dra.evidence-gated-loop-registry.v1",
            "dra.evolution-case.v1",
            "dra.evidence-gated-loop-report.v1",
            '{"match":true,"record_status":"valid","status":"valid"}',
        ):
            assert required in text


def test_unreleased_changelog_does_not_claim_release_or_runtime_evolution() -> None:
    changelog = _read("CHANGELOG.md")
    unreleased = _section(changelog, "## [Unreleased]", "## [0.1.6]")
    normalized = " ".join(unreleased.split())
    assert "Evidence-Gated Loop Kernel" in unreleased
    assert "provider-free" in unreleased
    assert "release remains on hold" in normalized
    assert "not runtime self-modification" in normalized
    assert (
        "not runtime self-modification, live-provider success, "
        "or a v0.1.7 release"
    ) in normalized
    for forbidden in (
        "autonomous self-improvement",
        "implements runtime self-modification",
        "demonstrates live-provider strict success",
        "released in v0.1.7",
    ):
        assert forbidden not in normalized


def test_readmes_link_commands_schemas_and_nonclaims() -> None:
    for text in (_read("README.md"), _read("README_CN.md")):
        for required in (
            "python scripts/evidence_gated_loop_gate.py check",
            "[Evidence-Gated Loop Kernel]"
            "(docs/reference/evidence-gated-loop-kernel.md)",
            "[canonical JSON]"
            "(docs/evidence/evidence-gated-loop-kernel-v1.json)",
            "dra.evidence-gated-loop-registry.v1",
            "dra.evolution-case.v1",
            "dra.evidence-gated-loop-report.v1",
        ):
            assert required in text
        assert (
            "not runtime self-modification" in text
            or "不是运行时自修改" in text
        )
        assert (
            "not a v0.1.7 release" in text
            or ("不证明" in text and "v0.1.7 已发布" in text)
        )
        assert '{"match":true,"record_status":"valid","status":"valid"}' in text

    english = _read("README.md")
    chinese = _read("README_CN.md")
    assert "No intermediate output is expected" in english
    assert "420-second aggregate profile deadline" in english
    assert "not an end-to-end TTHW claim" in english
    assert "不会输出中间进度" in chinese
    assert "420 秒 aggregate profile deadline" in chinese
    assert "不是端到端 TTHW claim" in chinese


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


def test_strict_citation_public_docs_preserve_compatibility_and_nonclaims() -> None:
    reference = _read("docs/reference/strict-citation-profile.md")
    readme = _read("README.md")
    readme_cn = _read("README_CN.md")
    docs_index = _read("docs/README.md")
    api_contract = _read("docs/reference/api-contract.md")
    state_machines = _read("docs/reference/state-machines.md")
    architecture = _read("docs/architecture.md")
    framework = _read("docs/decisions/framework-runtime-boundaries.md")
    integration = _read("docs/AGENT_INTEGRATION.md")
    downstream = _read("docs/reference/downstream-consumer-contract.md")
    changelog = _read("CHANGELOG.md")

    for document in (readme, readme_cn, docs_index):
        assert "strict-citation-profile.md" in document
    assert "`profile_id`" in api_contract
    assert "`generic-strict-citation`" in api_contract
    assert "zero exact citations remain warning-only" in api_contract
    assert "failed / not_required / failed" in state_machines
    assert "configured chat model" in architecture
    assert "one application-level invocation" in framework
    assert "--profile generic-strict-citation" in integration
    assert "dra.strict-citation-profile.v1" in downstream
    assert "generic-strict-citation" in changelog

    combined = "\n".join(
        (
            reference,
            api_contract,
            state_machines,
            architecture,
            framework,
            integration,
            downstream,
        )
    )
    for nonclaim in (
        "citation correctness",
        "citation completeness",
        "source quality",
        "entailment",
        "live-provider reliability",
        "hosted observability",
        "downstream adoption",
    ):
        assert nonclaim in combined
    assert "v0.1.6 fixture remains unchanged" in downstream
    assert "Release remains a separate decision" in reference


def _assert_talent_public_truth(agents: str) -> None:
    purpose = _section(agents, "## Project Purpose", "## Source Of Truth")
    assert "ready for separate human value review" in purpose
    assert "does not record a passed human value gate" in purpose
    assert "fixed-sample Talent benchmark whose value gate passed" not in agents


def _assert_bounded_live_historical_classification(evidence: str) -> None:
    headings = (
        "## Required Deterministic CI/Release Baseline",
        "## Optional Operator/Workflow Proof",
        "## Historical Reviewed Record",
        "## Absent Future Evidence",
    )
    required = _section(evidence, headings[0], headings[1])
    optional = _section(evidence, headings[1], headings[2])
    historical = " ".join(_section(evidence, headings[2], headings[3]).split())
    absent = _section(evidence, headings[3])
    for filename in (
        "bounded-live-producer-v1.json",
        "bounded-live-producer-v1.md",
    ):
        link = f"]({filename})"
        assert link in historical
        assert all(link not in section for section in (required, optional, absent))
    for phrase in (
        "one bounded DeepSeek producer observation",
        "`completed / not_required / ready`",
        "`supported / accept_draft`",
        "59 Evidence rows",
        "`docs.python.org`",
        "`peps.python.org`",
        "cost and search cost remain `not_observed`",
        "not a required CI or current release baseline",
        "does not prove source truth",
        "research or provider quality",
        "downstream business acceptance",
        "provider billing",
        "exactly-once",
        "production readiness",
        "SLA",
    ):
        assert phrase in historical


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

    _assert_bounded_live_historical_classification(evidence)

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


def test_bounded_live_evidence_rejects_required_or_absent_reclassification() -> None:
    evidence = _read("docs/evidence/README.md")
    historical_start = evidence.index("## Historical Reviewed Record")
    absent_start = evidence.index("## Absent Future Evidence")
    bounded_rows = "\n".join(
        line
        for line in evidence[historical_start:absent_start].splitlines()
        if "bounded-live-producer-v1." in line
    )
    assert bounded_rows

    for destination in (
        "## Required Deterministic CI/Release Baseline",
        "## Absent Future Evidence",
    ):
        mutated = evidence.replace(bounded_rows + "\n", "", 1)
        mutated = mutated.replace(destination, destination + "\n" + bounded_rows, 1)
        with pytest.raises(AssertionError):
            _assert_bounded_live_historical_classification(mutated)


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
