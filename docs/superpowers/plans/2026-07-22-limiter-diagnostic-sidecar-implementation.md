# Limiter Diagnostic Sidecar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the exact native call-limiter kind and bounded counters in one operator-only sidecar so a failed bounded live evaluation can be diagnosed without parsing model output, changing the public failure taxonomy, or increasing budgets.

**Architecture:** Project the locked LangChain limiter exceptions into a frozen application contract at the DeepAgents harness boundary. When an exact proof-owned mode is enabled, the execution service writes one strict sidecar into the existing backend output volume. The bounded producer reads it through a fixed in-container reader, validates container and volume ownership before and after extraction, and publishes at most one existing-style, post-cleanup operator receipt.

**Tech Stack:** Python 3.11, LangChain 1.3.10, DeepAgents 0.6.11, LangGraph 1.2.6, Pydantic 2.13.4, Docker Compose, pytest.

## Global Constraints

- Implement against `docs/superpowers/specs/2026-07-22-artifact-delivery-and-limiter-diagnostics-design.md` after PR A has landed.
- Preserve `ModelCallLimitMiddleware` and `ToolCallLimitMiddleware` as enforcement. Do not add a second counter, change middleware ordering, increase any model/tool/task/subagent limit, or change the primary/fallback models.
- Preserve `dra.run-failure-cause.v1`, every API and DB contract, canonical result/Evidence authority, and the public bounded-evaluation error envelope.
- The exact opt-in is `DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_LIMITER_DIAGNOSTICS=true`. Ordinary runtime leaves it absent and writes nothing. Any other non-empty value fails closed before Agent execution.
- Do not parse `str(exc)`, messages, model text, trace content, or LangSmith data. Only locked native exception classes and structured attributes are admissible.
- The runtime sidecar and exported receipt are operator diagnostics, not application or business authority. They do not prove that a budget is appropriate or that a run is acceptable.
- The bounded producer must use direct `docker exec` with a fixed reader command. Do not use `docker compose cp`, a host bind mount, a broad container shell, or a host temporary payload file.
- Maintain owner-only permissions, strict size limits, no overwrite, exact cleanup, and existing total deadline accounting.
- Do not modify artifact delivery code, database schema, migrations, dependencies, CI workflow shape, release metadata, or `VERSION`.
- Rebase or sync this lane onto the merged PR A commit before final verification and merge.
- Use `PYTHON_DOTENV_DISABLED=1` and a Python 3.11 environment matching the locked constraints. Record exact versions with the verification evidence.

---

## File Structure

- Modify `agent/harness_contracts.py`: define the frozen limiter projection carried by `HarnessExecutionError`.
- Modify `agent/deepagents_harness.py`: map native locked exceptions without parsing text.
- Add `api/operator_diagnostics.py`: own the opt-in, strict runtime sidecar schema, and safe non-overwriting writer.
- Modify `api/research_execution_service.py`: invoke an injected best-effort diagnostic writer only for a typed limiter failure.
- Modify `agent/main_agent.py`: inject the writer selected by the exact environment mode.
- Modify `scripts/bounded_live_producer_lifecycle.py`: admit and materialize the proof-owned exact mode and expose exact owned resource identities.
- Add `scripts/bounded_live_producer_runtime_diagnostics.py`: fixed in-container sidecar reader.
- Modify `scripts/bounded_live_producer_contracts.py`: define the strict exported limiter receipt.
- Modify `scripts/bounded_live_producer_diagnostics.py`: add the third non-overwriting receipt filename and publisher.
- Modify `scripts/bounded_live_producer_proof.py`: extract before cleanup, retain typed fields, and publish after cleanup.
- Modify focused harness, execution-service, lifecycle, proof, Docker, and documentation tests listed in each task.
- Modify `docs/reference/bounded-live-producer-evaluation.md`: publish the closed field set and non-authority boundary.

### Task 1: Project Native Limiter Exceptions Into A Frozen Contract

**Files:**
- Modify: `agent/harness_contracts.py:1-80`
- Modify: `agent/deepagents_harness.py:1-150`
- Test: `tests/unit/test_deepagents_harness.py`
- Test: `tests/integration/test_harness_execution.py`

**Interfaces:**
- Adds: `CallBudgetDiagnostic` with a closed `limiter_kind`, `tool_scope`, bounded counters, and `agent_role="not_observed"`.
- Extends: `HarnessExecutionError(..., call_budget_diagnostic: CallBudgetDiagnostic | None = None)`.
- Adds: `_call_budget_diagnostic(exc) -> CallBudgetDiagnostic | None` in the framework adapter.
- Keeps: `failure_kind="call_budget_exceeded"` and the original exception in `__cause__`.

- [ ] **Step 1: Write the five native-exception RED cases**

Construct the locked native exceptions with their real constructors and exercise the real
`DeepAgentsHarness.execute` catch boundary. Cover:

1. coordinator model limit;
2. global tool limit (`tool_name is None`);
3. task-tool limit (`tool_name == "task"`);
4. a model-limit exception propagated from a subagent graph;
5. a tool-limit exception propagated from a subagent graph.

Assert exact closed fields and that no role is inferred:

```python
assert error.failure_kind == "call_budget_exceeded"
assert error.call_budget_diagnostic == CallBudgetDiagnostic(
    limiter_kind="model",
    tool_scope="not_applicable",
    run_count=40,
    run_limit=40,
    thread_count=40,
    thread_limit=None,
    agent_role="not_observed",
)
assert isinstance(error.__cause__, ModelCallLimitExceededError)
```

Add negative cases for an unknown `tool_name`, missing attributes, booleans passed as counters,
negative counts, zero limits, counts above the documented bound, and unrelated exceptions. These
cases must produce no diagnostic projection while retaining the existing public failure kind.

- [ ] **Step 2: Run the focused tests to verify RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_deepagents_harness.py \
  tests/integration/test_harness_execution.py \
  -k 'call_budget_diagnostic or native_call_limit'
```

Expected: FAIL because `CallBudgetDiagnostic` and the extended error field do not exist.

- [ ] **Step 3: Implement strict construction without text parsing**

In `agent/harness_contracts.py`, define a frozen slots dataclass with exact validation:

```python
MAX_CALL_BUDGET_DIAGNOSTIC_COUNT = 1_000_000


@dataclass(frozen=True, slots=True)
class CallBudgetDiagnostic:
    limiter_kind: Literal["model", "tool"]
    tool_scope: Literal["not_applicable", "all_tools", "task"]
    run_count: int
    run_limit: int
    thread_count: int
    thread_limit: int | None
    agent_role: Literal["not_observed"] = "not_observed"

    def __post_init__(self) -> None:
        if (
            type(self.run_count) is not int
            or type(self.run_limit) is not int
            or type(self.thread_count) is not int
            or self.thread_limit is not None
            and type(self.thread_limit) is not int
        ):
            raise ValueError("call_budget_diagnostic_invalid")
        counts = (self.run_count, self.thread_count)
        limits = (self.run_limit,) + (() if self.thread_limit is None else (self.thread_limit,))
        if (
            any(value < 0 or value > MAX_CALL_BUDGET_DIAGNOSTIC_COUNT for value in counts)
            or any(value < 1 or value > MAX_CALL_BUDGET_DIAGNOSTIC_COUNT for value in limits)
            or self.limiter_kind == "model" and self.tool_scope != "not_applicable"
            or self.limiter_kind == "tool" and self.tool_scope == "not_applicable"
        ):
            raise ValueError("call_budget_diagnostic_invalid")
```

Extend `HarnessExecutionError` with an optional exact-type field. In
`agent/deepagents_harness.py`, use only `isinstance` plus direct `run_count`, `run_limit`,
`thread_count`, `thread_limit`, and `tool_name` access. Map `None` to `all_tools`, `"task"` to
`task`, model limits to `not_applicable`, and return `None` for every unknown or malformed shape.
Do not catch validation errors by inventing alternate values.

- [ ] **Step 4: Run the locked harness matrix and commit**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_deepagents_harness.py \
  tests/integration/test_harness_execution.py
git diff --check
```

Expected: PASS.

```bash
git add agent/harness_contracts.py agent/deepagents_harness.py \
  tests/unit/test_deepagents_harness.py tests/integration/test_harness_execution.py
git commit -m "feat(agent): project native limiter diagnostics"
```

### Task 2: Add The Disabled-By-Default Runtime Sidecar Writer

**Files:**
- Add: `api/operator_diagnostics.py`
- Modify: `api/research_execution_service.py:161-410`
- Modify: `agent/main_agent.py:1-65`
- Add: `tests/unit/test_operator_diagnostics.py`
- Add: `tests/unit/test_research_execution_service.py`
- Modify: `tests/unit/test_deepagents_harness.py`

**Interfaces:**
- Adds: `CALL_BUDGET_SIDECAR_SCHEMA_VERSION = "dra.call-budget-origin-sidecar.v1"`.
- Adds: `CALL_BUDGET_SIDECAR_DIRECTORY = PurePosixPath("operator-diagnostics")` and
  `CALL_BUDGET_SIDECAR_FILENAME = "call-budget-v1.json"`; the writer inserts one validated run-ID
  component between them beneath the output root.
- Adds: `call_budget_diagnostic_writer_from_environment(*, output_root: Path) -> Callable[[str, CallBudgetDiagnostic], None] | None`.
- Extends: `ResearchExecutionService(..., call_budget_diagnostic_writer: Callable | None = None)`.

- [ ] **Step 1: Write RED contracts for mode selection and safe publication**

Test all exact environment states:

```python
monkeypatch.delenv(
    "DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_LIMITER_DIAGNOSTICS",
    raising=False,
)
assert call_budget_diagnostic_writer_from_environment(output_root=tmp_path) is None

monkeypatch.setenv(
    "DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_LIMITER_DIAGNOSTICS",
    "true",
)
assert callable(call_budget_diagnostic_writer_from_environment(output_root=tmp_path))
```

Reject `"TRUE"`, `"1"`, whitespace, empty text, and every other value with one stable
configuration exception. For the writer, test exact canonical bytes, mode `0600`, regular-file
identity, owner UID, maximum 4096 bytes, parent/run directory confinement, no symlink traversal,
no overwrite, link/write/fsync failure, and concurrent publication.

In the execution service, inject a spy writer and prove:

- it receives only `(run_id, typed_diagnostic)` for `call_budget_exceeded`;
- it is not called for recursion, execution, cancellation, or a malformed native projection;
- writer failure does not change `ExecutionOutcome.failure_kind`, persisted failure cause, or the
  public response;
- the sidecar write happens before the outcome is frozen and does not enter Evidence or result
  artifacts.

- [ ] **Step 2: Run the focused tests to verify RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_operator_diagnostics.py \
  tests/unit/test_research_execution_service.py \
  -k 'call_budget or operator_diagnostic'
```

Expected: FAIL because the writer module and injection seam do not exist.

- [ ] **Step 3: Implement one strict runtime file**

Use a strict Pydantic model or an equivalently closed dataclass serializer with this complete
payload:

```json
{"limiter":{"agent_role":"not_observed","limiter_kind":"model","run_count":40,"run_limit":40,"thread_count":40,"thread_limit":null,"tool_scope":"not_applicable"},"schema_version":"dra.call-budget-origin-sidecar.v1"}
```

The actual serializer must use sorted compact JSON plus one newline and reject unknown keys on
readback. Publish under:

```text
<output_root>/operator-diagnostics/<validated_run_id>/call-budget-v1.json
```

Validate `run_id` with the existing public ID grammar before opening directories. Open every
component descriptor-relative with `O_NOFOLLOW`; create only the exact task directories; create a
random temporary regular file using `O_CREAT|O_EXCL`, force `0600`, write with bounded loops,
`fsync` the file, link to the final name without overwrite, verify the linked inode and exact
bytes through the still-open descriptor, remove the temporary name by inode ownership, and
`fsync` the directory. Map all writer failures to a private stable exception.

Add the optional writer to `ResearchExecutionService`. In the exact `HarnessExecutionError` catch,
invoke it only when `failure_kind == "call_budget_exceeded"`, the diagnostic has exact type, and
the effective run ID is valid. Catch writer exceptions locally, append only a stable diagnostic
code to the internal accumulator, then preserve the existing frozen outcome.

In `agent/main_agent.py`, call the environment resolver when constructing the execution service.
This is the only production wiring. Absent mode produces `None` and no filesystem write.

- [ ] **Step 4: Run service, API, and persistence regressions and commit**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_operator_diagnostics.py \
  tests/unit/test_research_execution_service.py \
  tests/unit/test_deepagents_harness.py \
  tests/integration/test_run_api.py \
  tests/integration/test_run_failure_cause_proof.py \
  -m 'not docker'
git diff --check
```

Expected: PASS with the public failure cause still exactly `execution/call_budget_exceeded`.

```bash
git add api/operator_diagnostics.py api/research_execution_service.py \
  agent/main_agent.py tests/unit/test_operator_diagnostics.py \
  tests/unit/test_research_execution_service.py tests/unit/test_deepagents_harness.py
git commit -m "feat(api): write opt-in limiter sidecars"
```

### Task 3: Make The Live Mode Exact And Proof-Owned

**Files:**
- Modify: `scripts/bounded_live_producer_lifecycle.py:40-1100`
- Modify: `tests/unit/test_bounded_live_producer_lifecycle.py`
- Modify: `tests/integration/test_bounded_live_producer_proof.py`

**Interfaces:**
- Adds the exact key to the live allowlist.
- Preserves absence as disabled and materializes the exact source value only when it is lowercase
  `true`.
- Rejects an externally supplied value unless it is exactly `true`.
- Keeps base Compose, `.env.example`, and ordinary runtime defaults unchanged.

- [ ] **Step 1: Write RED tests for task-only materialization**

Assert that an approved credential source without the new key yields a materialized task file in
which the key remains absent and the runtime writer is disabled. Assert that a source containing
exact lowercase `true` preserves that exact value, while `false`, `TRUE`, `1`, empty, duplicate, or
whitespace-padded values fail before Docker or provider activity.

Add a byte-level test proving `LiveConfiguration.close()` zeroes the augmented in-memory raw bytes
and removes the exact snapshot directory on both success and primary failure.

- [ ] **Step 2: Run to verify RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_bounded_live_producer_lifecycle.py \
  tests/integration/test_bounded_live_producer_proof.py \
  -k 'limiter_diagnostics_mode or live_configuration_materialized'
```

Expected: FAIL because the key is not admitted by the closed live configuration.

- [ ] **Step 3: Implement exact augmentation**

Introduce one constant for the key. During `load_live_configuration`, allow it but require exact
`true` when present. Preserve the source bytes and exact single assignment during task-only
materialization; do not add the key when absent. Re-parse the final bytes before writing and assert
the complete closed environment contract. The separately authorized live launcher is responsible
for supplying a task-external owner-only credential source that includes the exact opt-in; this PR
does not mutate a persistent credential file.

Never write the augmented bytes back to the source `.env`. Keep `LANGSMITH_TRACING=false`, feature
gates, fake runtime secrets, and every existing credential rule unchanged.

- [ ] **Step 4: Run lifecycle tests and commit**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_bounded_live_producer_lifecycle.py \
  tests/integration/test_bounded_live_producer_proof.py \
  -k 'configuration or environment or cleanup'
git diff --check
```

Expected: PASS.

```bash
git add scripts/bounded_live_producer_lifecycle.py \
  tests/unit/test_bounded_live_producer_lifecycle.py \
  tests/integration/test_bounded_live_producer_proof.py
git commit -m "feat(eval): enable proof-owned limiter diagnostics"
```

### Task 4: Extract One Sidecar Through A Fixed Container Reader

**Files:**
- Add: `scripts/bounded_live_producer_runtime_diagnostics.py`
- Modify: `scripts/bounded_live_producer_lifecycle.py`
- Modify: `scripts/bounded_live_producer_proof.py:940-1625`
- Add: `tests/unit/test_bounded_live_producer_runtime_diagnostics.py`
- Modify: `tests/unit/test_bounded_live_producer_lifecycle.py`
- Modify: `tests/integration/test_bounded_live_producer_proof.py`
- Modify: `tests/integration/test_bounded_live_producer_container.py`

**Interfaces:**
- Container command: `python /app/scripts/bounded_live_producer_runtime_diagnostics.py read --run-id <run_id>`.
- Container source: `/app/output/operator-diagnostics/<run_id>/call-budget-v1.json`.
- Host result: validated `CallBudgetOriginSidecar` object or `None`.
- Missing, malformed, oversized, wrong-mode, wrong-owner, identity drift, non-owned container, or
  non-owned volume returns no diagnostic and never changes the primary error.

- [ ] **Step 1: Write reader and ownership RED tests**

For the in-container reader, cover exact bytes, missing file, traversal-like run IDs, symlinks,
directories, mode other than `0600`, wrong UID, oversized content, extra keys, invalid enums,
invalid counter bounds, trailing bytes, and pre/post inode or size drift. It must write canonical
validated bytes only to stdout and stable one-line JSON only to stderr on failure.

For the host orchestrator, fake Docker responses and require this order:

1. discover the exact full backend container ID;
2. prove it is in `ManagedComposeProject`'s owned container set;
3. prove the exact named volume `<project>_backend_output` is in the owned volume set;
4. inspect the backend mount and require that exact volume at `/app/output`;
5. direct `docker exec` the fixed argv with bounded stdout/stderr;
6. strict-validate canonical bytes;
7. re-discover and re-inspect the same container and volume after reading.

Mutation tests must reject a short ID, changed container ID, anonymous volume, bind mount, extra
mount, wrong destination, volume ownership drift, command drift, shell invocation, or a second
reader call.

- [ ] **Step 2: Run to verify RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_bounded_live_producer_runtime_diagnostics.py \
  tests/unit/test_bounded_live_producer_lifecycle.py \
  tests/integration/test_bounded_live_producer_proof.py \
  -k 'runtime_diagnostic or sidecar_extraction'
```

Expected: FAIL because the fixed reader and extraction method do not exist.

- [ ] **Step 3: Implement the reader and bounded extraction**

The reader opens `/app/output` and each validated path component descriptor-relative using
`O_NOFOLLOW`, then checks regular-file type, effective UID, mode `0600`, link count, and a 4096-byte
maximum. Read through one descriptor, validate the strict runtime schema, recheck identity, and
emit the canonical serialization. Do not emit the source path or invalid raw bytes.

Move the generic project resource refresh and exact service-container resolution into methods on
`ManagedComposeProject` only if that reduces duplicated ownership checks; keep command execution
inside the existing bounded subprocess/deadline implementation. Add
`read_call_budget_sidecar(run_id, deadline)` with the exact seven-step protocol above.

In the live primary flow, call it only after terminal observation has produced exact
`execution/call_budget_exceeded`, before cleanup begins. Retain the typed value in an outer local
variable. If extraction fails or returns no object, preserve the original run failure and continue
cleanup with no diagnostic receipt.

- [ ] **Step 4: Run unit, proof, and real Docker tests and commit**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_bounded_live_producer_runtime_diagnostics.py \
  tests/unit/test_bounded_live_producer_lifecycle.py \
  tests/integration/test_bounded_live_producer_proof.py
PYTHON_DOTENV_DISABLED=1 \
  DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
  python -m pytest -q tests/integration/test_bounded_live_producer_container.py
git diff --check
```

Expected: PASS. Record task-owned container, volume, network, image, temporary path, and process
inventory before and after the Docker command.

```bash
git add scripts/bounded_live_producer_runtime_diagnostics.py \
  scripts/bounded_live_producer_lifecycle.py \
  scripts/bounded_live_producer_proof.py \
  tests/unit/test_bounded_live_producer_runtime_diagnostics.py \
  tests/unit/test_bounded_live_producer_lifecycle.py \
  tests/integration/test_bounded_live_producer_proof.py \
  tests/integration/test_bounded_live_producer_container.py
git commit -m "feat(eval): extract owned limiter sidecars"
```

### Task 5: Publish The Third Operator Receipt Without Changing Old Bytes

**Files:**
- Modify: `scripts/bounded_live_producer_contracts.py`
- Modify: `scripts/bounded_live_producer_diagnostics.py`
- Modify: `scripts/bounded_live_producer_proof.py`
- Modify: `tests/unit/test_bounded_live_producer_contracts.py`
- Modify: `tests/unit/test_bounded_live_producer_diagnostics.py`
- Modify: `tests/integration/test_bounded_live_producer_proof.py`

**Interfaces:**
- Adds schema: `dra.bounded-live-producer-call-budget-diagnostic.v1`.
- Adds filename: `bounded-live-producer-call-budget-diagnostic-v1.json`.
- Receipt fields: existing primary run-failure identity plus `limiter_kind`, `tool_scope`,
  `run_count`, `run_limit`, `thread_count`, `thread_limit`, and `agent_role`.
- Selection: result-boundary receipt, run-failure receipt, or call-budget receipt; never more than
  one for one invocation.

The exact successful serialization shape is:

```json
{
  "schema_version": "dra.bounded-live-producer-call-budget-diagnostic.v1",
  "primary": {
    "code": "run_failed",
    "phase": "observe",
    "retryable": false,
    "cleanup_status": "succeeded"
  },
  "run_failure": {
    "cause_schema_version": "dra.run-failure-cause.v1",
    "observation_status": "observed",
    "phase": "execution",
    "code": "call_budget_exceeded"
  },
  "limiter": {
    "limiter_kind": "model",
    "tool_scope": "not_applicable",
    "run_count": 40,
    "run_limit": 40,
    "thread_count": 40,
    "thread_limit": null,
    "agent_role": "not_observed"
  }
}
```

- [ ] **Step 1: Write RED schema, byte-compatibility, and selection tests**

Lock exact strict receipt bytes and parse round trips. Capture the current serialized bytes for
the result-boundary and generic run-failure receipts in tests before modifying the registry, then
assert they remain byte-identical afterward.

Test the complete selection table:

| Primary failure | Extracted sidecar | Published receipt |
|---|---|---|
| `consumer_projection_invalid/result` | any | result-boundary |
| `run_failed/observe` non-budget | absent | generic run-failure |
| `run_failed/observe` call budget | valid | call-budget |
| `run_failed/observe` call budget | absent/invalid | generic run-failure |
| any other primary failure | any | none |

Also cover cleanup failure after successful extraction: the selected receipt keeps the original
failure identity and records final `cleanup_status=failed`. Publication remains after cleanup and
writer failure remains best effort.

- [ ] **Step 2: Run to verify RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_bounded_live_producer_contracts.py \
  tests/unit/test_bounded_live_producer_diagnostics.py \
  tests/integration/test_bounded_live_producer_proof.py \
  -k 'call_budget_receipt or diagnostic_selection or receipt_byte_compatibility'
```

Expected: FAIL because the third receipt is not registered.

- [ ] **Step 3: Extend the closed diagnostic union and sink**

Add strict Pydantic models with `extra="forbid"`, exact literals, and the same counter bounds as
the runtime sidecar. Extend `EvaluationError.diagnostic` only if necessary for an in-process typed
value; do not add fields to the public JSON error. Prefer keeping the extracted sidecar as a
separate local value passed to `_publish_diagnostic_best_effort` so public failure construction is
unchanged.

Add the filename and serializer to the existing sink preflight registry. Reuse the existing
non-overwrite, owner-only, inode-bound, fsync publication mechanism. Update
`_publish_diagnostic_best_effort` to make one exact selection and one publisher call. Preflight
must reject a directory containing any of the three final names.

- [ ] **Step 4: Run receipt, cleanup, and compatibility tests and commit**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_bounded_live_producer_contracts.py \
  tests/unit/test_bounded_live_producer_diagnostics.py \
  tests/integration/test_bounded_live_producer_proof.py
git diff --check
```

Expected: PASS, including exact old receipt bytes.

```bash
git add scripts/bounded_live_producer_contracts.py \
  scripts/bounded_live_producer_diagnostics.py \
  scripts/bounded_live_producer_proof.py \
  tests/unit/test_bounded_live_producer_contracts.py \
  tests/unit/test_bounded_live_producer_diagnostics.py \
  tests/integration/test_bounded_live_producer_proof.py
git commit -m "feat(eval): publish limiter diagnostic receipts"
```

### Task 6: Document The Boundary And Verify PR B

**Files:**
- Modify: `docs/reference/bounded-live-producer-evaluation.md`
- Modify: `docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md`
- Modify: `docs/superpowers/plans/2026-07-18-bounded-live-producer-evaluation-implementation.md`
- Modify: `tests/unit/test_documentation_contracts.py`

**Interfaces:**
- Documents the exact mode, native structured source, closed receipt fields, extraction ownership,
  post-cleanup publication, and non-authority boundary.
- States that role remains `not_observed` and no budget/model adjustment follows automatically.

- [ ] **Step 1: Write the failing documentation contract**

Require the exact environment key, both schema versions, fixed sidecar path, fixed direct-reader
command, seven closed fields, post-cleanup wording, and these non-claims:

- no API/DB/public failure change;
- no model or budget change;
- no role inference;
- no LangSmith authority;
- no successful live-provider evidence claim.

Add mutations that remove one field, allow an arbitrary tool name, describe the receipt as
authoritative, or imply automatic retry.

Also require a bounded `Post-Observation Limiter Diagnostic Amendment` in the original bounded
producer design and implementation record. It must state that the earlier Change 1 middleware and
runtime prohibitions remain historical Change 1 boundaries, while this separately approved change
adds only structured native-exception projection and operator-only transport. The amendment must
repeat the no-budget, no-model, no-API/DB/Evidence, no-live-success, and default-disabled limits.

- [ ] **Step 2: Run to verify RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  -k 'limiter_diagnostic_sidecar'
```

Expected: FAIL because the reference and historical bounded-producer records do not contain this
current amendment.

- [ ] **Step 3: Update the reference and run final verification**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_deepagents_harness.py \
  tests/integration/test_harness_execution.py \
  tests/unit/test_operator_diagnostics.py \
  tests/unit/test_research_execution_service.py \
  tests/unit/test_bounded_live_producer_runtime_diagnostics.py \
  tests/unit/test_bounded_live_producer_contracts.py \
  tests/unit/test_bounded_live_producer_diagnostics.py \
  tests/unit/test_bounded_live_producer_lifecycle.py \
  tests/integration/test_bounded_live_producer_proof.py \
  tests/unit/test_documentation_contracts.py
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m 'not docker'
PYTHON_DOTENV_DISABLED=1 \
  DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
  python -m pytest -q \
  tests/integration/test_bounded_live_producer_container.py \
  tests/integration/test_durable_review_container.py
PYTHON_DOTENV_DISABLED=1 python scripts/bounded_live_producer_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/check_canonical_identity.py --root .
PYTHON_DOTENV_DISABLED=1 python scripts/final_presentation_audit.py
git diff --check
```

Expected: all commands PASS. Run the deterministic `check` twice and compare stdout bytes. If the
full host suite is blocked by a version/import mismatch, report the exact blocker while retaining
fresh focused and locked Docker evidence; do not install an unapproved dependency or use an import
stub as full-suite evidence.

- [ ] **Step 4: Commit the public contract**

```bash
git add docs/reference/bounded-live-producer-evaluation.md \
  docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md \
  docs/superpowers/plans/2026-07-18-bounded-live-producer-evaluation-implementation.md \
  tests/unit/test_documentation_contracts.py
git commit -m "docs(eval): define limiter diagnostic sidecar"
```

## PR B Completion Gate

- The lane is based on the merged PR A commit and contains no artifact-delivery reimplementation.
- Five native limiter cases pass against the locked framework versions.
- Ordinary runtime writes no sidecar; exact proof mode writes at most one strict runtime sidecar.
- Container and named-volume identity are proven before and after a fixed direct-reader invocation.
- At most one post-cleanup operator receipt is published, and the two existing receipt bytes remain
  compatible.
- Public failure cause, API, DB, result, Evidence, budgets, models, dependencies, CI, and version
  remain unchanged.
- Worktree and task-owned Docker resources are clean.
- Stop with a `READY` report for authoritative branch-diff review. Do not push, create a PR, run a
  live provider, or publish evidence without separate authorization.
