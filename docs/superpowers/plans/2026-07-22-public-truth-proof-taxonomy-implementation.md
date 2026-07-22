# Public Truth And Proof Taxonomy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make repository-level capability claims, benchmark readiness, release evidence, and local/CI proof coverage describe the exact current facts without changing runtime behavior or evidence payloads.

**Architecture:** Add one narrow documentation-contract test that reads the public truth surfaces and executable producers together. Correct the stale Talent claim, classify retained evidence by authority and lifecycle, and label README commands as a selected local subset while enumerating the actual required CI proofs from the workflow.

**Tech Stack:** Markdown, YAML text contracts, Python 3.11, pytest.

## Global Constraints

- Implement against `docs/superpowers/specs/2026-07-22-artifact-delivery-and-limiter-diagnostics-design.md`.
- This lane is independent of PR A and PR B. It may develop and merge independently.
- Modify only `AGENTS.md`, `docs/evidence/README.md`, `README.md`, `README_CN.md`, and the new `tests/unit/test_public_truth_documentation.py`.
- Do not modify CI, benchmark producers, benchmark fixtures, proof scripts, evidence JSON/Markdown payloads, release notes, dependencies, runtime, API, DB, Agent code, or `VERSION`.
- Do not delete retained evidence. Classify it accurately and make each artifact's own explicit limits remain authoritative.
- Do not claim a Talent human value decision. The executable producer fixes `value_gate.passed=false`; a structurally complete bundle is only `ready_for_human_review`.
- Do not describe the downstream fixture command as a separate top-level CI job. Its behavior is covered by required pytest while the workflow has its own explicit proof steps.
- Do not imply that bounded live evidence exists. The deterministic provider-free contract is current; live evidence remains absent until a separately authorized successful observation is reviewed.
- Use `PYTHON_DOTENV_DISABLED=1` and a Python 3.11 environment matching the locked constraints.

---

## File Structure

- Add `tests/unit/test_public_truth_documentation.py`: lock executable claims, evidence classes,
  README command scope, required CI proof inventory, and bilingual parity.
- Modify `AGENTS.md`: replace the stale Talent value-gate claim with the exact structural readiness
  and human-decision boundary.
- Modify `docs/evidence/README.md`: group artifacts into required deterministic release evidence,
  optional capability evidence, historical bounded observations, and absent future evidence.
- Modify `README.md`: label commands as a selected local subset and list the exact required CI proof
  steps separately.
- Modify `README_CN.md`: mirror the same distinction in Chinese.

### Task 1: Define Executable Public-Truth Contracts

**Files:**
- Add: `tests/unit/test_public_truth_documentation.py`

**Interfaces:**
- Reads public documentation plus the current Talent producer and CI workflow.
- Fails when a public claim contradicts an executable fixed value or when proof classes collapse.
- Does not parse private process artifacts or infer facts from Git history.

- [ ] **Step 1: Add self-contained readers and section helpers**

Create the test file with no dependency on another test module:

```python
from pathlib import Path
import re


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
```

Keep every assertion tied to an exact source path and a bounded section so unrelated prose cannot
satisfy the contract.

- [ ] **Step 2: Add the Talent truth RED contract**

Read `scripts/talent_value_gate_runner.py`, `benchmarks/talent-hiring-signal-v1/README.md`, and
`AGENTS.md`. Require the executable fixed value and the public interpretation together:

```python
assert '"passed": False' in producer
assert '"ready_for_human_review": ready' in producer
assert "`value_gate.passed=false`" in benchmark
assert "human value decisions remain separate" in benchmark

purpose = _section(agents, "## Project Purpose", "## Source Of Truth")
assert "ready for separate human value review" in purpose
assert "does not record a passed human value gate" in purpose
assert "fixed-sample Talent benchmark whose value gate passed" not in agents
```

Add a mutation-style assertion that replacing the corrected sentences with the old passed-gate
sentence makes the helper assertion fail.

- [ ] **Step 3: Add the evidence taxonomy RED contract**

Require four exact headings in `docs/evidence/README.md`, in this order:

1. `## Required Deterministic CI/Release Baseline`
2. `## Optional Operator/Workflow Proof`
3. `## Historical Reviewed Record`
4. `## Absent Future Evidence`

Require these ownership rules:

- Agent evaluation, run creation, run dispatch, failure cause, secure local runtime, and downstream
  compatibility are in the required deterministic section.
- Durable HITL is in optional capability evidence and remains disabled by default.
- Real-source proof is in historical bounded observations and retains its explicit non-coverage.
- Bounded live producer JSON/Markdown names occur only in absent future evidence and remain stated
  as uncommitted.
- Directory presence does not confer verification or current release authority.

Use section-local path assertions so copying one artifact into two classes fails. Require every
regular `.json` or `.md` evidence file currently present in `docs/evidence/` to appear exactly once
in the index, except `README.md` itself. Enumerate with `Path.iterdir()` so the same contract works
in a Git checkout and in a source archive without `.git` metadata.

- [ ] **Step 4: Add README and CI coverage RED contracts**

Bound the English and Chinese command sections and require that they explicitly say the displayed
commands are a selected local subset, not the full required CI inventory. Require both READMEs to
name these exact required workflow proofs:

```text
Agent evaluation regression gate
Run creation idempotency proof
Run dispatch reconciliation proof
Run failure cause proof
Secure local runtime proof
Bounded live producer contract check
```

Read `.github/workflows/ci.yml` and assert the corresponding six `name:` steps remain present.
Require the documentation to say downstream fixture/CLI behavior is covered by required pytest and
is not an independent top-level workflow step. Assert that neither README claims every useful local
command is a dedicated CI step.

Add parity assertions so the English and Chinese sections contain the same six script basenames:

```python
required_scripts = {
    "agent_evaluation_gate.py",
    "run_creation_idempotency_proof.py",
    "run_dispatch_reconciliation_proof.py",
    "run_failure_cause_proof.py",
    "secure_local_runtime_proof.py",
    "bounded_live_producer_proof.py",
}
for script in required_scripts:
    assert script in english_ci_section
    assert script in chinese_ci_section
```

- [ ] **Step 5: Run the new tests to verify RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_public_truth_documentation.py
```

Expected: FAIL on the stale Talent claim, missing evidence classes, and unlabeled local/CI command
boundary.

### Task 2: Correct The Public Truth Surfaces

**Files:**
- Modify: `AGENTS.md:5-30`
- Modify: `docs/evidence/README.md`
- Modify: `README.md:250-285`
- Modify: `README_CN.md:225-260`
- Test: `tests/unit/test_public_truth_documentation.py`

- [ ] **Step 1: Correct the Talent claim**

Replace only the stale bullet with two bounded facts:

```text
- A fixed-sample Talent benchmark that can become ready for separate human
  value review when structural checks pass.
- The benchmark producer keeps `value_gate.passed=false`; no passed human
  value gate is recorded by the repository.
```

Keep the existing restricted profile, deterministic artifact, Evidence, and review authority
rules unchanged.

- [ ] **Step 2: Classify the evidence index without changing payloads**

Rewrite the opening table into the four approved sections. Preserve every existing artifact link
and all substantive limitation paragraphs. Use one concise row per file, and add an introductory
rule:

```text
This directory contains several evidence lifecycles. A tracked file is not
automatically a current release gate, an independent verification, or a live
observation; the section and the artifact's own limits define its role.
```

Classification:

| Section | Artifacts |
|---|---|
| Required deterministic CI/release baseline | Agent evaluation JSON/Markdown; downstream contract JSON; run creation JSON/Markdown; run dispatch JSON/Markdown; failure cause JSON/Markdown; secure local runtime JSON/Markdown |
| Optional operator/workflow proof | Durable HITL gate JSON |
| Historical reviewed record | Real-source proof JSON/Markdown |
| Absent future evidence | Bounded live producer JSON/Markdown names only, explicitly absent |

Do not move files. Do not imply that the historical observation is invalid; state only that it is
not a current deterministic release gate or comprehensive truth verification.

- [ ] **Step 3: Separate selected local commands from required CI proofs**

In both READMEs:

- rename or qualify the current block as a selected local verification subset;
- retain the commands already shown;
- add a compact `Required CI proof inventory` / `Required CI proof 清单` block containing all six
  proof scripts exactly as invoked by `.github/workflows/ci.yml`;
- state that ordinary pytest also covers downstream fixture/CLI behavior, while there is no
  separate top-level downstream workflow step;
- preserve provider-free and Docker boundaries already documented.

Do not edit the workflow or add badges.

- [ ] **Step 4: Run focused and existing documentation tests**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_public_truth_documentation.py \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_release_metadata.py \
  tests/unit/test_release_presentation_contracts.py
```

Expected: PASS.

- [ ] **Step 5: Run public-surface verification and commit**

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_dispatch_reconciliation_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_failure_cause_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/secure_local_runtime_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/bounded_live_producer_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/downstream_consumer_contract.py check
PYTHON_DOTENV_DISABLED=1 python scripts/check_canonical_identity.py --root .
PYTHON_DOTENV_DISABLED=1 python scripts/final_presentation_audit.py
git diff --check
```

Expected: all commands PASS and no proof artifact changes. Run `git status --short` after the
commands and fail the task if a proof payload, benchmark fixture, or release document changed.

```bash
git add AGENTS.md docs/evidence/README.md README.md README_CN.md \
  tests/unit/test_public_truth_documentation.py
git commit -m "docs: align proof and benchmark claims"
```

## PR C Completion Gate

- The branch changes exactly five approved files.
- `AGENTS.md` no longer claims a passed Talent human value gate and matches the executable fixed
  producer value.
- Every retained evidence file is indexed exactly once in the appropriate class.
- Both READMEs distinguish a selected local command subset from the exact required CI proof
  inventory.
- Downstream fixture/CLI coverage is described as pytest-owned rather than as a nonexistent
  top-level workflow job.
- CI, proof scripts, evidence payloads, benchmark outputs, runtime, dependencies, release metadata,
  and `VERSION` have no diff.
- Worktree is clean and no live/provider activity occurred.
- Stop with a `READY` report for authoritative branch-diff review. Do not push or create a PR
  without separate authorization.
