# Bounded Run Failure Diagnostic Receipt v1 Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` or
> `superpowers:subagent-driven-development` to execute this plan task by task. Use
> `superpowers:test-driven-development` for every behavior change and
> `superpowers:verification-before-completion` before reporting completion.

**Goal:** Classify terminal run failures before `/result` and publish one optional,
provider-free-tested, public-safe receipt containing only the existing application-owned
`dra.run-failure-cause.v1` phase/code pair.

**Architecture:** Reuse the existing application failure-cause projection as the sole phase/code
authority. Enrich the proof-owned `run_failed / observe` error with a strict in-memory projection,
then reuse the existing owner-only diagnostic sink to select exactly one fixed receipt after final
cleanup. The existing Result Diagnostic Receipt v1, public error envelope, REST/API, database,
Agent runtime, canonical result, Evidence, and business authority remain unchanged.

**Tech Stack:** Python 3.11, Pydantic v2 strict models, existing application
`RunFailureCauseProjectionAdapter`, descriptor-relative standard-library filesystem APIs, pytest,
and the existing bounded live producer proof harness.

## Global Constraints

- Implement against `origin/main@dc611f042d8a2af3bd90cd34be5b699a7d2e0eeb` plus the approved
  design commit already present on the task branch.
- Keep `VERSION=0.1.5`. Do not add release metadata, live evidence, dependencies, migrations,
  framework changes, or CI provider activity.
- Do not call `observe-live`, any provider/model/search endpoint, or any credential source.
- Preserve byte-identical `dra.bounded-live-producer-evaluation-error.v1` serialization and
  provider-free `bounded_live_producer_proof.py check` output.
- Preserve the existing Result Diagnostic Receipt v1 schema, filename, serializer, eligibility,
  and bytes.
- A failed, fallback, delivery-blocked, or malformed terminal status must not call `/result`.
  Only an exact `completed / ready` status may request `/result`, exactly once.
- Validate failed-run cause data through the existing application-owned
  `RunFailureCauseProjectionAdapter`; do not duplicate or widen the phase/code registry.
- A run-failure receipt is eligible only for `run_failed / observe` with an exact observed cause.
  Missing, `not_observed`, malformed, cross-phase, coerced, or extra-field cause data must fail
  closed as `run_state_invalid / observe` and publish no run-failure receipt.
- The new receipt must not contain run/thread/segment identity, state version, timestamp, HTTP
  facts, provider/model identity, duration, query, scope, URL, header, path, log, exception,
  traceback, content, token, credential, or secret-derived data.
- The existing `--diagnostic-dir` remains the only diagnostic CLI option. Preflight rejects the
  invocation if either approved fixed final filename exists. One invocation publishes at most one
  selected receipt after cleanup.
- Keep all sink protections: absolute repo-external owner-only directory, descriptor-relative
  access, symlink rejection, identity binding, mode `0600`, bounded write, non-overwrite, `fsync`,
  quarantine cleanup, and best-effort publication that never replaces the primary error.
- No parallel work may start before Task 1 establishes the shared contract. Tasks 2 and 3 have
  disjoint file ownership and may run in parallel only when the parent determines the coordination
  cost is lower than the expected gain. Tasks 4 and 5 are parent-owned and serial.
- Every task must show a real RED failure before implementation, then focused GREEN. Commit only
  task-owned files and keep the worktree clean between tasks.

## File And Responsibility Map

| File | Responsibility |
|---|---|
| `scripts/bounded_live_producer_contracts.py` | Strict run-failure diagnostic model, receipt model, `EvaluationError` eligibility, serializer, and application-registry reuse |
| `scripts/bounded_live_producer_proof.py` | Status-before-result classification, application cause validation, diagnostic preservation, selection, and post-cleanup publication |
| `scripts/bounded_live_producer_diagnostics.py` | Two fixed basenames, preflight for both, shared safe publisher, and exact wrapper functions |
| `tests/unit/test_bounded_live_producer_contracts.py` | Strict schema, every existing phase/code pair, cleanup bound, public bytes, and Result v1 compatibility |
| `tests/unit/test_bounded_live_producer_diagnostics.py` | Both-name preflight, selection target, non-overwrite, symlink/race, permission, `fsync`, and cleanup reuse |
| `tests/integration/test_bounded_live_producer_proof.py` | Terminal ordering, no-result failure paths, exact success call count, lifecycle selection, cleanup, and CLI behavior |
| `tests/unit/test_run_failure_cause_models.py` | Existing application phase/code authority regression coverage; modify only if a missing contract regression is proven |
| `docs/reference/bounded-live-producer-evaluation.md` | Operator contract, two receipt registries, selection table, privacy boundary, and stop condition |
| `docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md` | Narrow amendment linking the status-before-result and sibling receipt authority |
| `docs/superpowers/specs/2026-07-22-bounded-run-failure-diagnostic-receipt-design.md` | Approved design authority; do not rewrite except for a verified contradiction |
| `docs/superpowers/plans/2026-07-22-bounded-run-failure-diagnostic-receipt-implementation.md` | This implementation plan |
| `tests/unit/test_documentation_contracts.py` | Exact discovery, registry, compatibility, and non-claim mutations |

## Delivery Graph

```text
Task 1: shared strict contract
  ├─ Task 2: terminal classifier and application-cause projection
  └─ Task 3: two-name safe diagnostic sink
         ↓
Task 4: lifecycle selection and post-cleanup publication
         ↓
Task 5: public docs and full verification
```

---

### Task 1: Define The Strict Run-Failure Diagnostic Contract

**Files:**

- Modify: `scripts/bounded_live_producer_contracts.py`
- Modify: `tests/unit/test_bounded_live_producer_contracts.py`

**Interfaces:**

- Reuse: `RUN_FAILURE_CAUSE_SCHEMA_VERSION`, `RUN_FAILURE_CAUSE_CODES`, and
  `RunFailurePhase` from `api.run_failure_cause_models`.
- Add: `RUN_FAILURE_DIAGNOSTIC_SCHEMA_VERSION`.
- Add: `RunFailureDiagnostic`, `RunFailureDiagnosticPrimary`, and
  `RunFailureDiagnosticReceipt`.
- Extend: `EvaluationError.diagnostic` to the exact union
  `ResultBoundaryDiagnostic | RunFailureDiagnostic | None` with primary-error eligibility checks.
- Add: `serialize_run_failure_diagnostic(error: EvaluationError) -> bytes`.

- [ ] **Step 1: Write RED contract tests**

Add tests that instantiate every application-owned phase/code pair without copying a new local
registry into the test subject:

```python
@pytest.mark.parametrize(
    ("phase", "code"),
    [
        (phase, code)
        for phase, codes in RUN_FAILURE_CAUSE_CODES.items()
        for code in sorted(codes)
    ],
)
def test_run_failure_receipt_reuses_application_pairs(
    phase: str,
    code: str,
) -> None:
    error = EvaluationError(
        "run_failed",
        "observe",
        False,
        CleanupStatus.SUCCEEDED,
        diagnostic=RunFailureDiagnostic(
            cause_schema_version="dra.run-failure-cause.v1",
            observation_status="observed",
            phase=phase,
            code=code,
        ),
    )

    raw = serialize_run_failure_diagnostic(error)
    receipt = RunFailureDiagnosticReceipt.model_validate_json(raw, strict=True)

    assert receipt.run_failure.phase == phase
    assert receipt.run_failure.code == code
    assert len(raw) <= MAX_DIAGNOSTIC_BYTES
```

Add RED tests for:

- exact schema and canonical UTF-8 JSON bytes;
- `cleanup_status` accepting only `succeeded` and `failed`, rejecting `not_started`;
- cross-phase code pairs, extra fields, string coercion, mutable assignment, and unsafe string
  injection;
- run-failure metadata attached to any primary other than `run_failed / observe`;
- Result metadata attached to any primary other than
  `consumer_projection_invalid / result`;
- default public error bytes remaining identical with or without either internal diagnostic;
- existing Result Diagnostic Receipt v1 expected bytes remaining identical; and
- silent import in a fresh subprocess.

- [ ] **Step 2: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_bounded_live_producer_contracts.py \
  -k 'run_failure_diagnostic or result_diagnostic_compatibility or default_public_error'
```

Expected: collection or assertion failures because the new models, union eligibility, and
serializer do not exist.

- [ ] **Step 3: Implement the minimal strict contract**

Use the application constant and phase type directly. The new in-memory projection contains only:

```python
class RunFailureDiagnostic(StrictModel):
    cause_schema_version: Literal["dra.run-failure-cause.v1"]
    observation_status: Literal["observed"]
    phase: RunFailurePhase
    code: str

    @model_validator(mode="after")
    def require_application_pair(self) -> "RunFailureDiagnostic":
        if self.code not in RUN_FAILURE_CAUSE_CODES[self.phase]:
            raise ValueError("run_failure_diagnostic_pair_invalid")
        return self
```

The receipt primary is fixed to `run_failed / observe / retryable=false`; its cleanup type must be
an exact literal union of `succeeded` and `failed`. Build canonical compact JSON with a trailing
newline, run the existing public-safety validation, and enforce the existing 4 KiB diagnostic
bound.

Preserve `EvaluationError.__slots__`, constructor call compatibility, `serialize_error()`, and the
existing result serializer. Reject ambiguous or ineligible diagnostic unions in the constructor.

- [ ] **Step 4: Run GREEN and compatibility tests**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_bounded_live_producer_contracts.py \
  tests/unit/test_run_failure_cause_models.py
```

- [ ] **Step 5: Commit**

```bash
git add scripts/bounded_live_producer_contracts.py \
  tests/unit/test_bounded_live_producer_contracts.py
git commit -m "feat(eval): define run failure diagnostics"
```

---

### Task 2: Classify Terminal Status Before Requesting Result

**Depends on:** Task 1.

**Files:**

- Modify: `scripts/bounded_live_producer_proof.py`
- Modify: `tests/integration/test_bounded_live_producer_proof.py`

**Ownership boundary:** This task does not modify the sink module or sink unit tests. It may run in
parallel with Task 3 from the exact Task 1 commit.

- [ ] **Step 1: Write RED ordering and cause-projection tests**

Use a fake client whose `result_observation()` raises an assertion when a terminal status is not
eligible. Cover:

1. exact failed status with one canonical observed application cause returns
   `run_failed / observe` and carries `RunFailureDiagnostic`;
2. failed status never calls `/result`;
3. `completed_with_fallback` never calls `/result` and remains
   `run_fallback_rejected / observe`;
4. completed but non-ready never calls `/result` and remains
   `run_delivery_not_ready / observe`;
5. unknown terminal execution or malformed terminal tuple never calls `/result` and becomes
   `run_state_invalid / observe`;
6. exact `completed / ready` calls `/result` exactly once and preserves the accepted projection;
7. wrong run/thread/profile identity is rejected before terminal classification; and
8. direct `project_live_observation()` keeps the same identity-first and terminal-defense behavior.

Parameterize failed-run cause inputs for every existing phase/code pair plus missing,
`not_observed`, malformed timestamp, cross-phase code, coerced value, extra field, and null. The
invalid set must produce `run_state_invalid / observe`, no diagnostic, and zero result calls.

- [ ] **Step 2: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/integration/test_bounded_live_producer_proof.py \
  -k 'observe_terminal and (failure or fallback or delivery or result_order or cause)'
```

Expected: failed/fallback/non-ready paths currently call `/result`, and valid failed causes are not
projected.

- [ ] **Step 3: Add one strict application-cause projector**

Import the existing `RunFailureCauseProjectionAdapter` and `ObservedRunFailureCause`. Validate the
JSON-origin projection with the locked Pydantic strict JSON path so the RFC3339 timestamp is
validated without accepting Python-object coercion. Reject any serialization, schema, union, or
observation-status error as `run_state_invalid / observe`.

Create `RunFailureDiagnostic` only from a validated `ObservedRunFailureCause`; copy only schema,
observation status, phase, and code. Do not retain `recorded_at`.

- [ ] **Step 4: Move terminal classification ahead of `/result`**

After identity validation and the pending/running polling branch:

```text
failed                  -> validate cause -> raise run_failed / observe
completed_with_fallback -> raise run_fallback_rejected / observe
completed + not ready   -> raise run_delivery_not_ready / observe
completed + ready       -> continue
anything else           -> raise run_state_invalid / observe
```

Only the final branch calls `result_observation()` exactly once. Keep
`project_live_observation()` as defense in depth and make its identity check precede terminal
classification.

- [ ] **Step 5: Run GREEN and the complete proof integration file**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/integration/test_bounded_live_producer_proof.py
```

- [ ] **Step 6: Commit**

```bash
git add scripts/bounded_live_producer_proof.py \
  tests/integration/test_bounded_live_producer_proof.py
git commit -m "fix(eval): classify terminal failures before result"
```

---

### Task 3: Extend The Existing Safe Sink To Two Fixed Receipts

**Depends on:** Task 1.

**Files:**

- Modify: `scripts/bounded_live_producer_diagnostics.py`
- Modify: `tests/unit/test_bounded_live_producer_diagnostics.py`

**Ownership boundary:** This task does not modify proof orchestration or integration tests. It may
run in parallel with Task 2 from the exact Task 1 commit.

- [ ] **Step 1: Write RED two-name sink tests**

Define expected constants:

```python
RESULT_DIAGNOSTIC_FILENAME = "bounded-live-producer-result-diagnostic-v1.json"
RUN_FAILURE_DIAGNOSTIC_FILENAME = (
    "bounded-live-producer-run-failure-diagnostic-v1.json"
)
```

Preserve `DIAGNOSTIC_FILENAME` as a compatibility alias for the existing result filename. Add RED
tests proving:

- preflight rejects either pre-existing fixed final name;
- result publication still produces exactly the old filename and bytes;
- run-failure publication produces exactly the new filename and strict bytes;
- a selected publication never overwrites either final file;
- the shared path retains descriptor identity, symlink rejection, mode `0600`, bounded partial
  writes, file/directory `fsync`, final-link verification, replacement protection, quarantine
  cleanup, and primary-error independence for both basenames; and
- no generic caller-controlled basename is accepted.

- [ ] **Step 2: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_bounded_live_producer_diagnostics.py \
  -k 'run_failure or both_fixed_names or result_compatibility'
```

- [ ] **Step 3: Refactor the publisher without weakening safety**

Parameterize only the internal approved basename and serializer. Keep public wrappers:

```python
publish_result_diagnostic(...)
publish_run_failure_diagnostic(...)
```

The internal basename must be selected from a closed module-owned mapping, not caller text. Update
temporary/quarantine names to derive from the selected fixed basename. Preflight loops over both
approved final names before returning one directory-identity-bound `DiagnosticSink`.

- [ ] **Step 4: Run GREEN and full sink tests**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_bounded_live_producer_diagnostics.py
```

- [ ] **Step 5: Commit**

```bash
git add scripts/bounded_live_producer_diagnostics.py \
  tests/unit/test_bounded_live_producer_diagnostics.py
git commit -m "feat(eval): publish run failure diagnostic receipts"
```

---

### Task 4: Integrate Exact Diagnostic Selection After Cleanup

**Depends on:** Tasks 2 and 3 integrated into the parent branch.

**Files:**

- Modify: `scripts/bounded_live_producer_proof.py`
- Modify: `tests/integration/test_bounded_live_producer_proof.py`

- [ ] **Step 1: Write RED lifecycle-selection tests**

Add deterministic tests for:

- `run_failed / observe` plus exact `RunFailureDiagnostic` publishing only the run-failure file;
- `consumer_projection_invalid / result` plus `ResultBoundaryDiagnostic` publishing only the
  existing result file;
- no diagnostic directory producing the unchanged public error and no filesystem output;
- success and all ineligible failures producing neither file;
- cleanup success and cleanup failure producing `succeeded` and `failed` respectively in the
  selected receipt;
- live configuration close failure preserving the primary `run_failed / observe`, grouping
  cleanup failure, and publishing the final failed cleanup status;
- diagnostic publication failure never replacing the primary/grouped error;
- preflight rejecting the invocation before live configuration if either final filename exists;
  and
- one invocation being unable to publish both files even when publisher functions are mutation
  patched.

- [ ] **Step 2: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/integration/test_bounded_live_producer_proof.py \
  -k 'diagnostic and (run_failure or selection or cleanup or preflight)'
```

- [ ] **Step 3: Implement closed selection**

Keep the in-memory diagnostic while the primary error passes through `run_cleanup_guarded()`,
configuration close, and grouped-error projection. After final cleanup status is known, select by
the exact diagnostic type and eligible primary tuple:

```text
ResultBoundaryDiagnostic + consumer_projection_invalid/result
  -> publish Result Diagnostic Receipt v1

RunFailureDiagnostic + run_failed/observe
  -> publish Run Failure Diagnostic Receipt v1

anything else
  -> publish nothing
```

Do not add a new CLI option. Continue treating publication as best effort and never serialize the
diagnostic into the public error envelope.

- [ ] **Step 4: Run GREEN and complete bounded feature matrix**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_bounded_live_producer_contracts.py \
  tests/unit/test_bounded_live_producer_diagnostics.py \
  tests/unit/test_bounded_live_producer_http.py \
  tests/unit/test_bounded_live_producer_lifecycle.py \
  tests/integration/test_bounded_live_producer_proof.py \
  tests/unit/test_run_failure_cause_models.py
```

- [ ] **Step 5: Commit**

```bash
git add scripts/bounded_live_producer_proof.py \
  tests/integration/test_bounded_live_producer_proof.py
git commit -m "feat(eval): select bounded diagnostic receipts"
```

---

### Task 5: Publish The Contract And Run Full Relevant Verification

**Depends on:** Task 4.

**Files:**

- Modify: `docs/reference/bounded-live-producer-evaluation.md`
- Modify: `docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md`
- Modify: `tests/unit/test_documentation_contracts.py`
- Verify unchanged: `docs/superpowers/specs/2026-07-22-bounded-run-failure-diagnostic-receipt-design.md`
- Verify unchanged: `docs/superpowers/plans/2026-07-22-bounded-run-failure-diagnostic-receipt-implementation.md`

- [ ] **Step 1: Write RED documentation contracts**

Lock:

- status-before-result ordering and the no-`/result` terminal failure boundary;
- the exact new schema and fixed filename;
- the complete existing application phase/code matrix by reference to its authority;
- `cleanup_status` limited to `succeeded|failed`;
- the two-file selection table and preflight rejection if either exists;
- unchanged Result Diagnostic Receipt v1 registry and compatibility statement;
- no raw content, identity, timestamp, HTTP, provider/model, path, log, trace, or credential fields;
- non-authoritative receipt status and strict-consumer requirement;
- no API/DB/Agent/result/Evidence/dependency/version/release change; and
- separate authorization for at most one later live attempt.

Add mutation tests for a missing failure code, cross-phase code, swapped filename, widened cleanup
status, changed Result v1 filename, both-receipts publication claim, and a live-success overclaim.

- [ ] **Step 2: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  -k 'bounded and run_failure_diagnostic'
```

- [ ] **Step 3: Update the public reference and narrow original-design amendment**

Document the operator flow without publishing any private live-run fact or raw failure content.
The original bounded producer design receives only a short superseding amendment that points to
the new status-before-result and sibling receipt authority; do not rewrite historical decisions.

- [ ] **Step 4: Run focused docs and release contracts**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_release_metadata.py \
  tests/unit/test_release_presentation_contracts.py \
  tests/unit/test_demo_console_contracts.py
```

- [ ] **Step 5: Run full provider-free verification**

Run the repository-required environment or the exact CI-compatible locked environment. Do not
install unapproved dependencies and do not use a stub to claim full validation.

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/bounded_live_producer_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/bounded_live_producer_proof.py check
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m "not docker"
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m docker
python scripts/agent_evaluation_gate.py check
python scripts/downstream_consumer_contract.py check
python scripts/check_canonical_identity.py --root .
python scripts/final_presentation_audit.py
git diff --check origin/main..HEAD
```

Capture the two provider-free `check` outputs separately and prove byte equality. Verify:

- no live evidence pair exists;
- no `observe-live`, provider, model, search, or credential access occurred;
- `VERSION`, dependencies, CI, API, DB, Agent runtime, canonical result, Evidence, frontend, and
  release metadata have no diff;
- approved spec and plan hashes are unchanged;
- public/private marker and credential-value scans are clean; and
- task-owned Docker containers, volumes, networks, images, temporary directories, and processes
  are zero after the required Docker lane. Do not broad-prune shared or historical resources.

- [ ] **Step 6: Commit documentation and final verification record**

```bash
git add docs/reference/bounded-live-producer-evaluation.md \
  docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md \
  tests/unit/test_documentation_contracts.py
git commit -m "docs(eval): publish run failure diagnostics"
```

## Completion And Stop Boundary

The implementation phase is complete only when:

- the branch contains the approved spec and plan plus the five task commits;
- the worktree is clean;
- all actual RED-to-GREEN and final verification evidence is reported accurately;
- Result Diagnostic Receipt v1 compatibility is explicitly proven;
- no provider/live/evidence/version/release work occurred; and
- the branch is stopped locally for authoritative branch-diff review.

Do not push, create or modify a PR, merge, tag, release, deploy, run a provider, publish live
evidence, or clean up the final branch/worktree without separate authorization. After merge, any
final live observation remains a new, separately authorized one-shot operation.
