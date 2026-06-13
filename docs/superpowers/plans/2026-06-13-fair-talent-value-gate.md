# Fair Talent Value Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline paired-run benchmark that gives Generic and Talent the same fixture envelope and exports review-ready evidence without auto-claiming that the value gate passed.

**Architecture:** A standalone script validates the existing fixture and `ResearchScope`, builds a deterministic shared prompt, invokes `run_deep_agent()` once per profile per repetition, and exports a sanitized JSON bundle. Pure helper functions own validation, serialization, scope checks, and completion status so the benchmark contract can be tested without model calls.

**Tech Stack:** Python 3.11, dataclasses, Pydantic contracts, existing `run_deep_agent()`, pytest.

---

## File Structure

- Create `scripts/talent_value_gate_runner.py`: pure benchmark contract helpers, paired execution orchestration, CLI, and JSON output.
- Create `tests/unit/test_talent_value_gate_runner.py`: deterministic input, validation, serialization, scope, failure, and CLI argument tests.
- Modify `benchmarks/talent-hiring-signal-v1/README.md`: execution command, output boundary, and human scoring procedure.

### Task 1: Deterministic Shared Input Contract

**Files:**
- Create: `tests/unit/test_talent_value_gate_runner.py`
- Create: `scripts/talent_value_gate_runner.py`

- [ ] **Step 1: Write failing tests for loading and deterministic envelope construction**

Add tests that load `benchmarks/talent-hiring-signal-v1/research-scope.json` and
`benchmarks/fixtures/talent-hiring-signal-v1.json`, assert the aggregate ID
matches, and assert repeated `build_prompt_envelope()` calls return identical
text and SHA-256 hashes.

- [ ] **Step 2: Run tests to verify RED**

Run: `python -m pytest tests/unit/test_talent_value_gate_runner.py -q`

Expected: FAIL because `scripts/talent_value_gate_runner.py` does not exist.

- [ ] **Step 3: Implement fixture validation and prompt construction**

Implement:

```python
def load_benchmark_inputs(scope_path: Path, fixture_path: Path) -> BenchmarkInputs:
    ...

def build_prompt_envelope(inputs: BenchmarkInputs) -> tuple[str, str]:
    ...
```

Validation must reject mismatched aggregate IDs, undeclared fixture URLs,
non-HTTP(S) URLs, empty content, and fixtures without samples.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `python -m pytest tests/unit/test_talent_value_gate_runner.py -q`

Expected: PASS.

### Task 2: Sanitized Run Serialization And Completion Gate

**Files:**
- Modify: `tests/unit/test_talent_value_gate_runner.py`
- Modify: `scripts/talent_value_gate_runner.py`

- [ ] **Step 1: Write failing tests for result serialization and fail-closed completion**

Construct `ExecutionOutcome` fixtures and assert:

- the serialized run contains final text, diagnostics, evidence, packets, and
  failure state;
- it contains no `session_dir`;
- an exception or missing Talent packet yields `benchmark_status=incomplete`;
- evidence URLs outside the fixture set are counted by Profile for human
  scope-adherence scoring;
- the value-gate object always has `passed=false` and empty human scores.

- [ ] **Step 2: Run tests to verify RED**

Run: `python -m pytest tests/unit/test_talent_value_gate_runner.py -q`

Expected: FAIL because serialization and completion helpers are missing.

- [ ] **Step 3: Implement serialization and completion helpers**

Implement:

```python
def serialize_outcome(outcome: AgentRunResult, *, elapsed_seconds: float) -> dict:
    ...

def build_benchmark_bundle(..., paired_results: list[dict]) -> dict:
    ...
```

Only emit allowlisted fields. Count completed runs, schema failures, and
out-of-scope evidence against the declared fixture URL set.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `python -m pytest tests/unit/test_talent_value_gate_runner.py -q`

Expected: PASS.

### Task 3: Paired Offline Execution

**Files:**
- Modify: `tests/unit/test_talent_value_gate_runner.py`
- Modify: `scripts/talent_value_gate_runner.py`

- [ ] **Step 1: Write failing async tests for paired execution**

Inject a fake async runner and assert:

- each repetition runs `generic` then `talent-hiring-signal`;
- both receive byte-identical prompt envelopes;
- each call gets unique `thread_id`, `run_id`, and `segment_id`;
- only Talent receives the validated `ResearchScope`;
- exceptions are captured as failed records without dropping earlier results.

- [ ] **Step 2: Run tests to verify RED**

Run: `python -m pytest tests/unit/test_talent_value_gate_runner.py -q`

Expected: FAIL because paired execution is missing.

- [ ] **Step 3: Implement paired orchestration and CLI**

Implement `run_value_gate()` with an injectable runner defaulting to
`run_deep_agent`, plus CLI flags:

```text
--scope
--fixture
--repetitions
--output
```

The CLI writes one JSON file and prints only the completion summary.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `python -m pytest tests/unit/test_talent_value_gate_runner.py -q`

Expected: PASS.

### Task 4: Benchmark Procedure Documentation

**Files:**
- Modify: `benchmarks/talent-hiring-signal-v1/README.md`

- [ ] **Step 1: Document the exact offline run command**

Document:

```bash
python scripts/talent_value_gate_runner.py \
  --scope benchmarks/talent-hiring-signal-v1/research-scope.json \
  --fixture benchmarks/fixtures/talent-hiring-signal-v1.json \
  --repetitions 3 \
  --output output/benchmarks/talent-hiring-signal-v1.json
```

- [ ] **Step 2: Document interpretation boundaries**

State that the runner compares profile behavior on identical snapshot input,
does not assess live search, does not auto-score subjective dimensions, and
cannot emit a passing value-gate decision.

- [ ] **Step 3: Verify docs and diff**

Run: `git diff --check`

Expected: exit 0.

### Task 5: Full Verification And Delivery

**Files:**
- Review all changed files.

- [ ] **Step 1: Run focused tests**

Run: `python -m pytest tests/unit/test_talent_value_gate_runner.py -q`

Expected: all focused tests pass.

- [ ] **Step 2: Run full backend suite**

Run: `python -m pytest -q`

Expected: all tests pass.

- [ ] **Step 3: Run syntax and diff checks**

Run:

```bash
python -m compileall -q scripts/talent_value_gate_runner.py
git diff --check origin/main...HEAD
```

Expected: exit 0.

- [ ] **Step 4: Run one no-model contract smoke**

Use an injected fake runner or a unit-level invocation to write a temporary
bundle and verify it parses as JSON, contains two paired run records, contains
no `session_dir`, and reports `benchmark_status=incomplete`.

- [ ] **Step 5: Review complete branch diff, commit, push, and create PR**

The PR must clearly state that a real model-backed benchmark has not yet been
executed and requires separate human scoring. Do not merge the PR.
