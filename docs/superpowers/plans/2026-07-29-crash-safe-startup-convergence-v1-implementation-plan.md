# Crash-Safe Startup Convergence And Explicit Replacement v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkboxes for execution tracking.

**Status:** Approved for implementation.

**Goal:** Close the live post-start process-death gap without runtime
self-modification, heartbeat expiry, checkpoint replay, or automatic Agent
retry. A fresh application boot must first converge exact previous-generation
execution owners to immutable failed source runs. Only an authenticated,
zero-body, explicitly keyed request may then create one fresh replacement run.

**Architecture:** Add dormant strict contracts, migration `010`, and
transactional boot/owner/replacement repositories first. Activate them in one
atomic implementation task that simultaneously changes schema initialization,
process-lifetime single-writer exclusion, lifespan ordering and shutdown,
dispatch start, owner propagation, phase fencing, every running-state
finalizer, and every current direct caller. The writer gate is local,
OS-released, non-blocking, and held from before migration until all tracked run
tasks and callbacks settle at shutdown; it is not heartbeat, leader election,
or multi-instance authority. Add the recovery API, Tool Client, real-process
provider-free proof, CI, and public truth only after the core ownership path is
coherent. Online execution records and fences evidence; recovery and
replacement decisions remain explicit, application-owned operations. No
runtime path diagnoses failures into new rules, mutates prompts, or promotes
candidates.

**Tech Stack:** Python 3.11, FastAPI 0.138.0, Starlette 1.3.1, Pydantic 2.13.4,
SQLite, pytest 9.0.3, pytest-asyncio 1.4.0, standard-library subprocess and
signal primitives.

**Approved design:**
`docs/superpowers/specs/2026-07-28-crash-safe-agent-run-recovery-v1-design.md`

**Planned public target:**
`docs/superpowers/plans/2026-07-29-crash-safe-startup-convergence-v1-implementation-plan.md`

---

## Global Constraints

1. The approved design is authoritative. This plan may make implementation
   mechanics more explicit but may not reintroduce:
   - heartbeat renewal;
   - lease expiry thresholds;
   - a periodic recovery scanner;
   - automatic retry or replacement;
   - checkpoint or node replay;
   - provider/tool replay;
   - multi-instance or high-availability claims;
   - runtime prompt, Skill, rule, or program mutation.
2. Migration identity is exact:

   ```text
   version: 010_run_execution_recovery
   checksum: run-execution-recovery-v1
   backup: <configured-application-db>.pre-run-execution-recovery.bak
   ```

3. The only public mutation added by this feature is:

   ```text
   POST /api/runs/{source_run_id}/retries
   Idempotency-Key: required
   Request body: exactly zero bytes
   ```

4. The existing `RuntimeAccessMiddleware` remains the sole HTTP access
   authority. Recovery does not add a credential mechanism or bypass existing
   loopback/API-key behavior.
5. Existing Evidence admission, strict citation, review, verification,
   publication, delivery, result, evaluation, profile, model, and tool
   semantics stay unchanged. The only permitted integration is exact owner
   fencing around the existing running lifecycle and terminal transaction.
6. Migration, startup convergence, repository tests, API contract tests, and
   the real-process proof are provider-free. They must not require credentials,
   model calls, graph calls, subagents, tools, Docker, or external network
   access.
7. Dependency pins and `constraints.txt` do not change. The known
   `ragflow-sdk 0.13.0` metadata declaration for `pytest<9` remains a
   diagnostic-only upstream metadata mismatch against the repository's
   deliberate `pytest==9.0.3` no-deps lock. It is not an authorization to
   change either pin.
8. `release disposition = hold`. No task creates a tag, GitHub Release,
   deployment, consumer re-pin, or `v0.1.7` claim.
9. No task writes canonical JSON/Markdown evidence for this feature. The
   bounded proof emits one deterministic runtime JSON report only.
10. Boot IDs, owner IDs, raw recovery keys, key hashes, request hashes,
    database paths, process IDs, worker IDs, credentials, queries, scopes,
    model output, and tool arguments never enter public responses, proof
    output, logs, telemetry, docs examples, or committed fixtures.
11. Execution is serial. Tasks 1-3 create dormant primitives. Task 4 is the one
    atomic activation boundary. No partial Task 4 commit may be retained.
12. The implementation window does not run AutoPlan or change product
    direction. Plan corrections come from the planning authority as a separate
    docs-only authority commit, after which implementation stops and
    re-locks its base.
13. The approved single-writer premise is enforced, not merely documented.
    Exactly one process may hold the DB-scoped execution-writer capability.
    Apart from validating/creating the canonical DB parent when absent and
    opening/creating the empty private coordination file itself, lock
    contention or unsupported locking fails before migration, backup,
    writability probes, output-directory creation, boot activation, workers,
    or requests and does not touch the application DB. Those coordination
    artifacts contain no authority payload. The gate is single-node only and
    creates no HA claim.
14. Shutdown releases the writer capability last. Task admission closes,
    worker loops stop, and every tracked run task plus timeout/cancellation
    callback settles first. An un-settled task blocks shutdown; the process
    does not voluntarily release the capability and hand authority to a new
    process.
15. Exact recovery profile drift is fail-closed. The original source remains
    auditable and immutable; recovery never upgrades the profile silently.
    One-hop exhaustion also creates no hidden fallback. After inspection, an
    operator may deliberately create an unrelated ordinary keyed run from
    caller-retained input, outside recovery lineage.

## Framework Boundary Verification

The implementation uses current framework behavior already compatible with the
locked repository versions:

- FastAPI lifespan code before `yield` completes before requests are served,
  and code after `yield` owns shutdown. Use the existing
  `@asynccontextmanager` lifespan rather than adding legacy startup handlers:
  <https://fastapi.tiangolo.com/advanced/events/>.
- Lifespan tests must enter `TestClient` as a context manager so activation and
  shutdown actually run:
  <https://fastapi.tiangolo.com/advanced/testing-events/>.
- Starlette request headers are case-insensitive, and
  `async for chunk in request.stream()` permits a bounded streaming body check
  without buffering or parsing the complete body:
  <https://www.starlette.io/requests/>.
- Existing middleware ordering stays unchanged; the route-level zero-body
  guard runs only after `RuntimeAccessMiddleware` admits the request:
  <https://www.starlette.io/middleware/>.
- Python 3.11 `fcntl.flock` provides the Unix advisory, non-blocking
  process-lifetime file lock used by the single-node writer gate. Unsupported
  platforms fail closed rather than substituting a PID file or time-based
  lease:
  <https://docs.python.org/3.11/library/fcntl.html#fcntl.flock>.

These native capabilities satisfy the required startup and body-ordering
contracts. The standard-library lock satisfies the approved single-writer
premise without heartbeat or leader election. Do not add another web
framework, body parser, hosted tracing service, middleware layer, distributed
lock, or dependency.

## Implementation Environment Gate

The execution window must begin from the clean feature branch containing the
approved spec and mechanically landed approved plan. It must not create or
install an environment without separate authority.

```bash
test "$(git branch --show-current)" = \
  "codex/crash-safe-startup-convergence-v1"
test -z "$(git status --porcelain)"
test -x .venv/bin/python || {
  printf '%s\n' DRA_PINNED_ENVIRONMENT_REQUIRED
  exit 1
}

.venv/bin/python - <<'PY'
import importlib.metadata as metadata
import sys

assert sys.version_info[:2] == (3, 11), sys.version
expected = {
    "fastapi": "0.138.0",
    "starlette": "1.3.1",
    "pydantic": "2.13.4",
    "pytest": "9.0.3",
    "pytest-asyncio": "1.4.0",
}
actual = {
    name: metadata.version(name)
    for name in expected
}
assert actual == expected, (actual, expected)
print("DRA_PINNED_ENVIRONMENT_OK")
PY
```

If `.venv` is absent or any required pin differs, stop with
`DRA_PINNED_ENVIRONMENT_REQUIRED`. Do not change pins, enable the network, or
install packages until the authority explicitly approves an exact setup
procedure. `uv pip check` may be recorded as a non-gating metadata diagnostic;
it is not the repository's acceptance gate.

Run a pre-edit baseline:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_run_dispatch_models.py \
  tests/unit/test_run_dispatch_repository.py \
  tests/unit/test_run_dispatch_worker.py \
  tests/unit/test_task_tracker.py \
  tests/unit/test_task_tracker_timeout.py \
  tests/unit/test_run_repository.py \
  tests/unit/test_run_migrations.py \
  tests/integration/test_run_dispatch_api.py \
  tests/integration/test_durable_review_lifecycle.py \
  tests/integration/test_bounded_live_producer_proof.py \
  tests/integration/test_agent_evaluation_v2_gate.py \
  tests/unit/test_decision_research_agent_tool.py
```

Expected: zero failures. Record the actual pass count and duration; do not
hard-code an old count.

## Implementation Base Lock

After the user approves the AutoPlan-reviewed complete plan, the execution
window mechanically lands the exact frozen plan, changes only its status to:

```text
Status: Approved for implementation.
```

and commits that docs-only phase before any behavior edit.

Immediately after that commit:

```bash
IMPLEMENTATION_BASE="$(git rev-parse HEAD)"
test -z "$(git status --porcelain)"
git show --stat --oneline "$IMPLEMENTATION_BASE"
```

The handoff records:

- exact spec SHA-256;
- exact plan SHA-256;
- exact `IMPLEMENTATION_BASE`;
- branch and worktree;
- pinned environment result.

Every implementation-only diff uses:

```bash
git diff --check "$IMPLEMENTATION_BASE"...HEAD
git diff --name-status "$IMPLEMENTATION_BASE"...HEAD
```

A later authority plan correction is a separate plan-only commit. The
implementation window must preserve any task-owned WIP byte-for-byte, land only
the authorized plan correction, recompute identities, and resume only after the
authority explicitly says the contract is reconciled.

## File And Responsibility Map

### New focused modules

| File | Responsibility |
| --- | --- |
| `api/run_execution_models.py` | Closed migration/boot/owner constants, immutable private `RunExecutionOwnerHandle`, one-assignment thread-safe owner box, bounded conflicts |
| `api/run_execution_writer_lock.py` | Canonical DB-scoped, non-blocking Unix advisory lock held for the complete process writer lifetime; bounded contention/unsupported errors |
| `api/run_execution_migrations.py` | Exact three-table schema, index, marker, backfill, cross-table verification, dedicated full backup/restore |
| `api/run_execution_repository.py` | Startup convergence/activation, current-boot checks, persisted phase fence, active-owner validation and closure helpers |
| `api/run_recovery_models.py` | Strict public acceptance, canonical source fingerprint, recovery key validation and distinct hash namespace |
| `api/run_recovery_repository.py` | Exact eligibility, one-hop lineage, first/replay conflict logic, atomic replacement run/segment/dispatch creation |
| `scripts/run_execution_recovery_crash_worker.py` | Provider-free child process that commits execution/finalization state, signals readiness, and waits for a real signal |
| `scripts/run_execution_recovery_proof.py` | Deterministic real-`SIGKILL`, startup convergence, stale-fence, retry/replay, migration/restore, and old-revision rollback report |
| `tests/run_execution_helpers.py` | Test-only helper that uses migration, boot activation, dispatch claim, and the real production start fence; no direct running bypass |
| `tests/unit/test_run_execution_models.py` | Closed model, privacy, and owner-box tests |
| `tests/unit/test_run_execution_writer_lock.py` | First-writer, overlap rejection, no-DB-touch, descriptor safety, and OS release after real process death |
| `tests/unit/test_run_execution_migrations.py` | Exact schema/backfill/backup/restore/fail-closed tests |
| `tests/unit/test_run_execution_repository.py` | Boot activation, convergence, phase, stale-owner, and all-or-nothing transaction tests |
| `tests/unit/test_run_recovery_models.py` | Exact public shape, key namespace, and canonical fingerprint tests |
| `tests/unit/test_run_recovery_repository.py` | Eligibility, lineage, concurrency, replay, corruption, and rollback tests |
| `tests/integration/test_run_execution_recovery.py` | Production lifespan/start/finalization/timeout/cancel/stale-generation integration |
| `tests/integration/test_run_recovery_api.py` | Middleware/body/key/repository/wake ordering and exact HTTP contracts |
| `tests/integration/test_run_recovery_tool_journey.py` | Real loopback production-app and Tool Client acceptance/wait/result journeys under provider-free test budgets |
| `tests/integration/test_run_execution_recovery_proof.py` | Real-process proof CLI, determinism, privacy, and failure-boundary tests |
| `docs/operations/run-execution-recovery.md` | Stopped-writer migration, startup semantics, explicit retry, diagnostics, and rollback runbook |

### Existing production surfaces

| File | Required change |
| --- | --- |
| `api/database.py` | Split pure canonical DB-path resolution from the explicit, validated parent-directory bootstrap required before the sibling writer lock |
| `api/run_dispatch_models.py` | Carry the private boot identity in an immutable dispatch claim |
| `api/run_dispatch_repository.py` | Fence claim/start by boot; winning start creates and returns the exact active owner |
| `api/run_dispatch_worker.py` | Require one lifespan boot identity and propagate it into claim/start scheduling |
| `api/run_repository.py` | Route every initializer through migration `010`; require owner on every running fence/finalizer; close owner in terminal transaction; reject direct transition into or out of running |
| `api/run_migrations.py` | Require and verify `010` marker, tables, index, fields, foreign keys, uniqueness, checks, and cross-table state |
| `api/task_tracker.py` | Close new task admission and deterministically cancel/settle every tracked run task and termination callback before writer release |
| `api/server.py` | Acquire writer gate before migration, activate boot before workers, retain private boot state, drain tracked tasks at shutdown, release writer gate last, propagate owner box, persist finalization phase, add explicit retry route |
| `tools/decision_research_agent_tool.py` | Add explicit `retry` command, exact response validation, key preservation, optional replacement wait/result |
| `.github/workflows/ci.yml` | Run the provider-free recovery proof before the full non-Docker suite |

### Existing direct callers that must be classified and retained

The implementation must rerun this inventory before edits:

```bash
rg -n \
  'RunDispatchClaim\(|RunDispatchWorker\(|claim_run_dispatch\(|start_run_dispatch\(|create_tracked_task\(|finalize_run_transaction\(|transition_run\(|_run_dispatched_with_persistence\(|_schedule_run_dispatch\(' \
  api scripts tests --glob '*.py'
```

Current live callers are classified as follows:

| Path | Required treatment |
| --- | --- |
| `scripts/bounded_live_producer_container_fixture.py` | Activate a boot, carry it through the worker, receive the real owner handle, persist finalization phase, finalize with that handle |
| `scripts/evidence_verification_container_fixture.py` | Construct its idle worker with an activated boot; retain provider/Agent prohibition |
| `scripts/run_dispatch_reconciliation_proof.py` | Use boot-aware claims and owner-returning starts while keeping this proof's pre-start scope and public boundaries unchanged |
| `scripts/run_failure_cause_proof.py` | Use boot-aware start and exact owner for every running finalizer; preserve the existing proof output |
| `scripts/agent_evaluation_replay.py` | Activate one isolated boot, open tracked-task admission, claim with that boot, pass the real owner box through the private dispatch path, then close/drain admission before returning; preserve Evaluation Sensitivity v2 semantics |
| `scripts/downstream_consumer_contract.py` | Replace its direct pending-to-running transition with migration + boot + real dispatch start; keep pending/terminal fixture construction unchanged |
| `scripts/durable_hitl_fixture.py` | Replace direct running transition with the real start path and pass the owner into its running finalizer |
| `scripts/real_source_proof.py` | Retain pending-to-terminal fixture behavior; do not add an owner because it never represents running execution |
| `tests/unit/test_run_repository.py` | Migrate all positive running/finalization cases to `tests/run_execution_helpers.py`; retain raw corrupt-state rows only as named negative controls |
| `tests/unit/test_run_dispatch_models.py` | Add boot identity strictness and privacy cases |
| `tests/unit/test_run_dispatch_repository.py` | Assert handle return, boot fencing, owner atomicity, and retained pending dispatch failure behavior |
| `tests/unit/test_run_dispatch_worker.py` | Require boot propagation and stale-boot no-claim/no-start behavior |
| `tests/unit/test_run_migrations.py` | Extend the full migration chain and protected-initializer matrix through `010` |
| `tests/unit/test_task_tracker_timeout.py` | Retain ordered timeout/cancel behavior and prove close-admission/drain cannot lose a task or callback |
| `tests/unit/test_task_tracker.py` | Make admission lifecycle explicit in every positive tracker test and prove teardown closes/drains rather than clearing a live registry |
| `tests/integration/test_run_dispatch_api.py` | Carry the exact owner box/handle through start, timeout, cancellation, and stale-attempt races |
| `tests/integration/test_run_api.py` | Replace direct running transition in the positive path; retain pending terminal fixtures |
| `tests/integration/test_durable_review_lifecycle.py` | Activate a boot, open admission, make the private dispatch path boot/owner aware, then close/drain before fixture teardown |
| `tests/integration/test_strict_citation_profile.py` | Migrate its direct running finalizers and private `_run_dispatched_with_persistence` entry to exact boot/owner authority |
| `tests/integration/test_context_reliability_regression.py` | Pass the exact owner box/handle through its private dispatch persistence entry while preserving the retained context contract |
| `tests/integration/test_bounded_live_producer_proof.py` | Activate one boot and pass that exact boot to both the external claim and fixture worker; retain the provider-free producer contract |
| `tests/unit/test_publication_service.py` | Replace its direct running transition with the real protected helper |
| `tests/unit/test_review_repository.py` | Replace its direct running transition with the real protected helper |
| `tests/unit/test_evidence_verification_container_fixture.py` | Activate a boot for the fixture worker and require the real owner for running finalization |
| `tests/unit/test_publication_repository.py` | Keep the raw ownerless-running mutation only in the explicitly named corruption negative control; it must never become a reusable helper |
| all other `finalize_run_transaction` callers | Pending-to-terminal fixture paths may stay ownerless; any path whose allowed prior state includes `running` must pass an exact owner |

After Task 4, add a source-contract test that rejects production calls which
pass `execution_status="running"` to `transition_run`. Do not make a broad text scan
that rejects explicit corruption fixtures or SQL contract literals; inspect the
AST or a narrow production allowlist.

## Authority And Transaction Flow

```text
application lifespan
  -> pure environment/configured-DB path parsing only
  -> validate required Unix lock primitives without filesystem mutation
  -> create and validate only the canonical DB parent directory when absent
  -> derive canonical configured-DB writer-lock identity
  -> acquire non-blocking process-lifetime exclusive writer lock
       contention/unsupported -> bounded failure; DB, backup, output, probes,
                                 migration, boot, and workers untouched
                                 (validated empty parent and fixed empty lock
                                 coordination artifact may remain)
  -> output-directory creation and review writability probes
  -> migration 010 backup/apply/verify
  -> generate private boot_id
  -> BEGIN IMMEDIATE
       verify previous boot and all running/active-owner invariants
       previous active owners -> interrupted
       exact old runs/segments -> failed
       exact existing public causes inserted
       singleton boot -> new boot_id
     COMMIT
  -> start dispatch/review workers
  -> accept requests
```

```text
application shutdown
  -> lifespan request admission has ended
  -> atomically close tracked-task admission
  -> signal dispatch/review workers to stop
  -> await worker loops; late scheduling cannot register a task
  -> cancel and settle every tracked run task
  -> settle owner-aware timeout/cancellation/finalization callbacks
  -> require tracked-task registry empty
  -> clear private boot/application state
  -> release exclusive writer lock last
```

```text
pending dispatch
  -> claim carries current boot_id
  -> BEGIN IMMEDIATE
       singleton boot must equal claim boot
       dispatch leased -> started
       run pending/v0 -> running/v1
       initial segment pending -> running
       active owner execution + boot_id + owner_id
     COMMIT
  -> immutable owner handle assigned once
  -> Agent/Harness execution
  -> persisted owner phase execution -> finalization
  -> existing business finalization
       exact boot + owner + run + segment + state fence
       existing authorized business rows
       active owner -> closed and private IDs cleared
     COMMIT
```

```text
explicit recovery
  -> existing runtime access middleware
  -> bounded zero-body stream guard
  -> recovery key validation
  -> BEGIN IMMEDIATE
       current boot fence
       source/owner/cause/profile/lineage eligibility
       key binding or exact replay
       fresh pending run + segment + dispatch
       one-hop immutable lineage
     COMMIT
  -> best-effort targeted dispatch + wake
  -> exact HTTP 202 accepted response
```

## Exact Schema Contract

Migration `010` creates exactly three private tables and one named scan index.
No field is added to public run status or result rows.

### `run_execution_boot_v1`

```sql
CREATE TABLE run_execution_boot_v1 (
    boot_scope TEXT PRIMARY KEY
        CHECK(boot_scope = 'application'),
    boot_id TEXT NOT NULL
        CHECK(length(boot_id) > 0),
    activated_at TEXT NOT NULL
)
```

After successful startup it contains exactly one row.

### `run_execution_owners_v1`

```sql
CREATE TABLE run_execution_owners_v1 (
    run_id TEXT PRIMARY KEY
        REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
    segment_id TEXT NOT NULL UNIQUE
        REFERENCES run_segments(segment_id) ON DELETE CASCADE,
    status TEXT NOT NULL
        CHECK(status IN ('active', 'closed', 'interrupted')),
    phase TEXT NOT NULL
        CHECK(phase IN ('execution', 'finalization')),
    boot_id TEXT,
    owner_id TEXT,
    created_at TEXT NOT NULL,
    phase_updated_at TEXT NOT NULL,
    closed_at TEXT,
    recovery_reason TEXT,
    CHECK(
        (
            status = 'active'
            AND boot_id IS NOT NULL
            AND length(boot_id) > 0
            AND owner_id IS NOT NULL
            AND length(owner_id) > 0
            AND closed_at IS NULL
            AND recovery_reason IS NULL
        )
        OR
        (
            status = 'closed'
            AND boot_id IS NULL
            AND owner_id IS NULL
            AND closed_at IS NOT NULL
            AND recovery_reason IS NULL
        )
        OR
        (
            status = 'interrupted'
            AND boot_id IS NULL
            AND owner_id IS NULL
            AND closed_at IS NOT NULL
            AND recovery_reason IN (
                'previous_boot_interrupted',
                'pre_v1_running_without_owner'
            )
        )
    )
)
```

```sql
CREATE INDEX idx_run_execution_owners_status_boot_created
ON run_execution_owners_v1(status, boot_id, created_at)
```

The cross-table verifier, not a repair path, additionally proves:

- `segment_id` belongs to `run_id`, `kind='initial'`, `sequence=0`;
- active owner, run, and segment are all running at run state version `1`;
- closed owner belongs to a terminal run/segment;
- interrupted owner belongs to exact failed run/segment state and phase-derived
  public cause;
- every post-010 running run has exactly one active owner;
- no active owner exists for a non-running run;
- all timestamps are parseable UTC values and terminal owner/run/segment/cause
  timestamps are identical where the contract requires it.

### `run_recovery_retries_v1`

```sql
CREATE TABLE run_recovery_retries_v1 (
    key_hash TEXT PRIMARY KEY,
    request_schema_version TEXT NOT NULL
        CHECK(request_schema_version = 'dra.run-recovery-request.v1'),
    request_hash TEXT NOT NULL,
    source_run_id TEXT NOT NULL UNIQUE
        REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
    replacement_run_id TEXT NOT NULL UNIQUE
        REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
    recovery_reason TEXT NOT NULL
        CHECK(recovery_reason IN (
            'previous_boot_interrupted',
            'pre_v1_running_without_owner'
        )),
    interrupted_phase TEXT NOT NULL
        CHECK(interrupted_phase IN ('execution', 'finalization')),
    recovery_attempt INTEGER NOT NULL
        CHECK(recovery_attempt = 1),
    created_at TEXT NOT NULL,
    CHECK(source_run_id != replacement_run_id)
)
```

SQLite's exact unique constraints on `source_run_id` and
`replacement_run_id` provide the one-source/one-replacement/one-hop boundary.
Do not add a second attempt table, queue, scanner, or mutable retry counter.

## Failure Mode Matrix

| Window | Winning authority | Required result |
| --- | --- | --- |
| Migration before marker | dedicated complete backup | all `010` writes commit and verify, or the complete pre-010 DB is restored |
| First writer already live | DB-scoped OS lock | second process may participate only in idempotent canonical-parent/empty-lock coordination, then fails before DB, backup, output, probes, migration, boot, workers, or request mutation |
| Writer process receives `SIGKILL` | OS descriptor lifetime | kernel releases the advisory lock; a fresh process may acquire and then converge |
| Unsupported advisory-lock platform | writer gate | bounded startup failure; no PID-file, timer, or optimistic single-writer fallback |
| Pre-010 exact running row | migration transaction | interrupted owner + failed run/segment + existing execution cause, no invented business rows |
| Pre-010 incoherent running row | verifier | startup fails and restores; no guessing or repair |
| New boot with execution owner | convergence transaction | original fails with `execution/execution_error` |
| New boot with finalization owner | convergence transaction | original fails with `finalization/run_finalization_failed` |
| New boot with ownerless/wrong-boot running state | convergence verifier | startup fails before workers or requests |
| Stale worker claim/start | current boot singleton | old boot cannot enter Agent execution |
| Start owner insert failure | one start transaction | dispatch/run/segment/owner all roll back |
| Cancellation during start settlement | owner box + shielded settlement | committed handle is assigned once before any running finalizer |
| Phase update loses boot/owner race | exact active owner | stale path stops before citation/artifact/review work |
| Normal/failed/timeout/cancel finalization | owner-aware terminal transaction | one winner closes owner and writes coherent terminal state |
| Stale fallback finalizer | exact active owner | no Evidence, packet, artifact, review, publication, delivery, or cause write |
| Recovery body/key invalid | route ordering | no repository access or worker wake |
| Same key + same source | retry ledger | same replacement, replay flag only changes |
| Same key + different source/snapshot | retry ledger | exact conflict, no new identity |
| Different key + bound source | unique source | exact conflict, no new identity |
| Replacement used as source | unique replacement | exhausted, no second hop |
| Post-commit dispatch false/wake error | durable acceptance | same HTTP 202; replay may request wake again |
| Tool Client loses response | caller-retained key | stable local context; no automatic second POST |
| Real process death | next boot only | startup convergence, no runtime scanner or automatic replacement |
| Graceful shutdown with active run | closed admission + tracker drain | callbacks and owner-aware finalization settle before writer authority is released |
| Tracked task cannot settle | held writer gate | shutdown remains blocked/fail-closed until operator termination; no overlapping successor |

## Execution Ordering

Tasks 1-3 are deliberately dormant:

- Task 1 defines values and immutable capabilities.
- Task 2 can migrate an explicitly supplied test database but is not called by
  `init_run_schema` or application lifespan.
- Task 3 can operate only on an explicitly migrated test database but is not
  imported by the production dispatch/finalization path.

Task 4 is the single production activation commit. It must include migration
entry, process-lifetime writer exclusion, boot activation, tracked-task
shutdown drain, claim/start, owner assignment, persisted phase, running-state
terminal fencing, all timeout/cancellation/fallback paths, and all live direct
callers. If any focused or retained test fails, do not retain a partial Task 4
commit.

Tasks 5-8 consume that coherent base. Do not parallelize tasks that share the
database, server lifespan, or exact public contract.

---

### Task 1: Define Closed Boot, Owner, And Recovery Contracts

**Files:**

- Create: `api/run_execution_models.py`
- Create: `api/run_recovery_models.py`
- Create: `tests/unit/test_run_execution_models.py`
- Create: `tests/unit/test_run_recovery_models.py`

**Interfaces produced:**

```python
RUN_EXECUTION_RECOVERY_MIGRATION_VERSION = "010_run_execution_recovery"
RUN_EXECUTION_RECOVERY_MIGRATION_CHECKSUM = "run-execution-recovery-v1"
RUN_RECOVERY_REQUEST_SCHEMA_VERSION = "dra.run-recovery-request.v1"
RUN_RECOVERY_SCHEMA_VERSION = "dra.run-recovery.v1"
RUN_EXECUTION_RECOVERY_PROOF_SCHEMA_VERSION = (
    "dra.run-execution-recovery-proof.v1"
)
```

The exact public names are `RunExecutionOwnerHandle`,
`RunExecutionOwnerBox`, `RunExecutionConflict`, `RunRecoveryAcceptance`,
`RunRecoveryRequestFingerprint`, `RunRecoveryConflict`,
`validate_recovery_key`, `recovery_key_hash`, and
`run_recovery_request_hash`. The concrete fields and algorithms are fixed in
Steps 4-5.

- [ ] **Step 1: Write strict execution model RED tests**

Create these exact tests:

- `test_execution_constants_are_closed_and_have_no_lease_expiry`
- `test_owner_handle_is_strict_frozen_and_private_identity_bounded`
- `test_owner_handle_rejects_coercion_wrong_prefix_and_empty_identity`
- `test_owner_box_is_empty_then_assigns_exactly_once`
- `test_owner_box_is_thread_safe_and_never_replaces_winner`
- `test_owner_box_returns_the_same_immutable_handle`
- `test_execution_conflict_contains_only_a_bounded_code`

Negative controls must prove the module does not define heartbeat, lease
duration, expiry threshold, scan interval, or automatic retry constants.

- [ ] **Step 2: Write recovery model RED tests**

Create these exact tests:

- `test_recovery_acceptance_has_exact_ten_field_public_shape`
- `test_recovery_acceptance_rejects_extra_fields_and_coercion`
- `test_recovery_acceptance_rejects_source_equal_replacement`
- `test_recovery_acceptance_requires_exact_replacement_initial_segment`
- `test_recovery_acceptance_rejects_empty_or_overlong_public_identities`
- `test_recovery_key_rejects_missing_short_unicode_whitespace_and_bool`
- `test_recovery_key_hash_uses_a_distinct_namespace_and_never_contains_raw_key`
- `test_request_hash_binds_every_immutable_source_and_terminal_field`
- `test_request_hash_is_canonical_for_scope_key_order_only`
- `test_request_hash_changes_for_segment_profile_state_cause_owner_or_attempt_drift`
- `test_recovery_conflict_contains_only_a_bounded_code`

The valid public example is:

```python
{
    "schema_version": "dra.run-recovery.v1",
    "status": "accepted",
    "reason": "previous_boot_interrupted",
    "interrupted_phase": "execution",
    "source_run_id": "run_source",
    "run_id": "run_replacement",
    "thread_id": "caller-thread",
    "segment_id": "run_replacement_seg_000",
    "recovery_attempt": 1,
    "idempotent_replay": False,
}
```

- [ ] **Step 3: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_run_execution_models.py \
  tests/unit/test_run_recovery_models.py
```

Expected: collection fails because both modules are absent.

- [ ] **Step 4: Implement exact private owner types**

Use strict frozen Pydantic models and application-private prefixes:

```python
BootId = Annotated[
    str,
    StringConstraints(pattern=r"^boot_[0-9a-f]{32}$"),
]
OwnerId = Annotated[
    str,
    StringConstraints(pattern=r"^owner_[0-9a-f]{32}$"),
]

class RunExecutionOwnerHandle(_StrictContract):
    run_id: str = Field(min_length=1, max_length=128)
    segment_id: str = Field(min_length=1, max_length=160)
    boot_id: BootId
    owner_id: OwnerId
```

`RunExecutionOwnerBox` uses a `threading.Lock`, stores either `None` or one
`RunExecutionOwnerHandle`, raises bounded
`run_execution_owner_already_assigned` on a second assignment, and never
exposes a mutation method.

Generate IDs only in repository/server code:

```python
def new_boot_id() -> str:
    return f"boot_{uuid.uuid4().hex}"

def new_owner_id() -> str:
    return f"owner_{uuid.uuid4().hex}"
```

Do not add timestamps, expiry, process identity, or worker identity to the
handle.

- [ ] **Step 5: Implement exact recovery contracts and hashes**

Recovery key validation reuses the current public character/length policy but
has a separate namespace:

```python
_RECOVERY_KEY_HASH_NAMESPACE = "dra.run-recovery-idempotency.v1\0"

def validate_recovery_key(value: str) -> str:
    validated = _RECOVERY_KEY_ADAPTER.validate_python(value, strict=True)
    if re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}",
        validated,
        flags=re.ASCII,
    ) is None:
        raise ValueError("run_recovery_key_invalid")
    return validated
```

The strict fingerprint contains exactly:

```python
class RunRecoveryRequestFingerprint(_StrictContract):
    schema_version: Literal["dra.run-recovery-request.v1"]
    source_run_id: str
    segment_id: str
    query: str
    thread_id: str
    profile_id: str
    profile_version: str
    scope: dict[str, Any]
    execution_status: Literal["failed"]
    review_status: Literal["not_required"]
    delivery_status: Literal["failed"]
    terminal_state_version: Literal[2]
    failure_phase: Literal["execution", "finalization"]
    failure_code: str
    recovery_reason: Literal[
        "previous_boot_interrupted",
        "pre_v1_running_without_owner",
    ]
    interrupted_phase: Literal["execution", "finalization"]
    recovery_attempt: Literal[1]
```

Serialize with sorted compact UTF-8 JSON. The repository creates the
fingerprint from already validated persisted values; the hash function does
not normalize invalid scope or profile data.

`RunRecoveryAcceptance` owns the relational response contract rather than
leaving it to the Tool Client:

```python
@model_validator(mode="after")
def _validate_replacement_identity(self) -> Self:
    if self.source_run_id == self.run_id:
        raise ValueError("run_recovery_response_invalid")
    if self.segment_id != f"{self.run_id}_seg_000":
        raise ValueError("run_recovery_response_invalid")
    return self
```

Its source, replacement, thread, and segment identities are non-empty and
bounded using the existing public run/segment limits; `recovery_attempt` is
`Literal[1]` and `idempotent_replay` is strict `bool`. Server repository
returns and Tool Client validation must use this same closed model so an
impossible relationship cannot cross any public boundary.

- [ ] **Step 6: Run GREEN and commit**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_run_execution_models.py \
  tests/unit/test_run_recovery_models.py
git diff --check
git add \
  api/run_execution_models.py \
  api/run_recovery_models.py \
  tests/unit/test_run_execution_models.py \
  tests/unit/test_run_recovery_models.py
git commit -m "feat(recovery): define boot ownership contracts"
```

Expected: the four Task 1 files are the complete commit; no production caller
imports the new modules yet.

---

### Task 2: Add Dormant Migration 010 With Exact Backfill And Restore

**Files:**

- Create: `api/run_execution_migrations.py`
- Create: `tests/unit/test_run_execution_migrations.py`

**Interfaces produced:** `run_execution_recovery_marker_present`,
`migrate_run_execution_recovery_with_backup`,
`verify_run_execution_recovery_schema`, and
`verify_run_execution_recovery_connection`. The first three accept an exact
`db_path`; the connection-scoped verifier accepts an existing
`sqlite3.Connection` and never commits or rolls it back.

Task 2 must not modify `api/run_repository.py`, `api/run_migrations.py`,
`api/server.py`, or the dispatch path. Tests call the dormant migration
explicitly.

- [ ] **Step 1: Build exact pre-010 fixtures**

Define a test-local `build_through_009_fixture()` that calls the current
legacy `_init_run_schema_unlocked` migration primitive directly. It must not
call public `init_run_schema`, because Task 4 will extend that public
initializer through `010`. Immediately assert the complete known through-009
marker/checksum set is present and the `010` marker, three tables, and named
index are absent. Then seed these categories before calling the dormant
migration:

```text
run_pending
run_running_exact
run_completed
run_completed_with_fallback
run_failed_with_observed_cause
run_failed_not_observed_history
```

The exact running fixture is:

```text
run: execution=running, review=not_required, delivery=pending, state_version=1
initial segment: kind=initial, sequence=0, attempt=1, status=running
dispatch: status=started
failure cause: absent
```

Snapshot every existing table as ordered rows plus normalized schema before
migration. Keep this helper test-only and rerun it unchanged after Task 4 so
the retained test continues to prove a real `009 -> 010` boundary rather than
accidentally constructing an already-migrated database. Do not create
through-009 state by deleting `010` rows or tables after public initialization.

- [ ] **Step 2: Write schema and backfill RED tests**

Create these exact tests:

- `test_010_marker_tables_index_columns_foreign_keys_and_checks_are_exact`
- `test_through_009_fixture_has_exact_legacy_markers_and_no_010_surface`
- `test_010_backfills_only_exact_preexisting_running_rows`
- `test_010_backfill_uses_one_terminal_timestamp_and_existing_execution_cause`
- `test_010_pending_and_terminal_business_rows_are_unchanged`
- `test_010_created_at_is_observation_time_not_claimed_start_time`
- `test_010_repeated_apply_is_verify_only_and_does_not_repeat_backfill`
- `test_010_existing_dedicated_backup_is_never_overwritten`

- [ ] **Step 3: Write fail-closed migration RED tests**

Parameterize faults at:

```text
boot table creation
owner table creation
lineage table creation
owner index creation
running-row validation
owner insert
run update
segment update
failure-cause insert
marker insert
post-commit verification
```

Required test names:

- `test_010_each_apply_or_verify_failure_restores_complete_backup`
- `test_010_closes_connections_before_restore`
- `test_010_rejects_wrong_marker_checksum_without_repair`
- `test_010_rejects_ownerless_or_malformed_preexisting_authority_tables`
- `test_010_rejects_running_wrong_review_delivery_or_state_version`
- `test_010_rejects_missing_duplicate_noninitial_or_nonrunning_segment`
- `test_010_rejects_existing_cause_for_running_source`
- `test_010_rejects_foreign_key_unique_check_and_index_drift`
- `test_010_rejects_partial_lineage_and_replacement_as_source`

Compare logical dumps after restore. Do not require the SQLite database file
bytes to be identical across backup APIs.

- [ ] **Step 4: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_run_execution_migrations.py
```

Expected: collection fails because the migration module is absent.

- [ ] **Step 5: Implement marker inspection without mutation**

`run_execution_recovery_marker_present` opens only enough schema to distinguish:

- no `schema_migrations` table -> absent;
- no `010` row -> absent;
- one exact row -> present;
- duplicate/wrong checksum/unreadable schema -> bounded
  `run_execution_recovery_unavailable`.

It never creates tables, inserts a marker, or repairs a checksum.

- [ ] **Step 6: Implement one dedicated backup-protected apply**

Use:

```python
backup_path = Path(
    f"{sqlite_db_path(db_path)}.pre-run-execution-recovery.bak"
)
```

Algorithm:

```text
serialize in-process migration call
inspect marker
if exact marker:
    verify only
    return
if dedicated backup exists:
    fail without overwrite
close inspection connection
backup complete DB
open configured SQLite connection
BEGIN IMMEDIATE
create three exact tables and owner scan index
validate every pre-010 running row and initial segment
backfill exact rows with one UTC timestamp
insert exact marker last
COMMIT
close connection
verify with a fresh connection
on any failure:
    close every migration/verification connection
    restore complete backup
    re-raise bounded conflict
```

Do not call `init_run_schema` from this function; Task 4 will call it only
after the existing chain through `009` is complete.

- [ ] **Step 7: Implement exact backfill transaction**

For each exact pre-010 running run, insert:

```sql
INSERT INTO run_execution_owners_v1 (
    run_id, segment_id, status, phase, boot_id, owner_id,
    created_at, phase_updated_at, closed_at, recovery_reason
) VALUES (
    ?, ?, 'interrupted', 'execution', NULL, NULL,
    ?, ?, ?, 'pre_v1_running_without_owner'
)
```

with the same timestamp in all three timestamp fields. Then:

```sql
UPDATE research_runs_v2
SET execution_status = 'failed',
    review_status = 'not_required',
    delivery_status = 'failed',
    state_version = 2,
    updated_at = ?
WHERE run_id = ?
  AND execution_status = 'running'
  AND review_status = 'not_required'
  AND delivery_status = 'pending'
  AND state_version = 1
```

Update the exact initial segment to `failed` with the same timestamp and insert
the existing observed cause:

```text
phase=execution
code=execution_error
terminal_state_version=2
recorded_at=<same timestamp>
```

If any expected row count differs from one, roll back. Do not infer
`finalization` from timestamps, payloads, logs, or traces.

- [ ] **Step 8: Implement exact schema and row verification**

Verification must check:

- exact marker/checksum;
- exact normalized table SQL shown above;
- exact columns, PKs, unique constraints, named index order, and foreign keys;
- `PRAGMA foreign_key_check`;
- boot singleton cardinality `0..1` before activation and exact
  `boot_scope='application'` if present;
- owner state combinations and UTC timestamps;
- segment ownership, kind, sequence, and run identity;
- active/running, closed/terminal, interrupted/failed cross-table invariants;
- phase-derived failure cause for interrupted rows;
- lineage source/replacement distinction, uniqueness, exact attempt, and no
  replacement-as-source row;
- post-010 running rows cannot be ownerless.

Verification returns only public-neutral counts and schema identities. It
never returns boot/owner/key/hash/run values.

- [ ] **Step 9: Run GREEN and commit**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_run_execution_migrations.py
git diff --check
git add \
  api/run_execution_migrations.py \
  tests/unit/test_run_execution_migrations.py
git commit -m "feat(recovery): add dormant recovery migration"
```

Expected: only the two Task 2 files. Existing application startup still stops
at its current schema behavior, so this commit is deployable and behaviorally
dormant.

---

### Task 3: Add Dormant Boot, Owner, Phase, And Replacement Transactions

**Files:**

- Create: `api/run_execution_repository.py`
- Create: `api/run_recovery_repository.py`
- Create: `tests/unit/test_run_execution_repository.py`
- Create: `tests/unit/test_run_recovery_repository.py`

**Interfaces produced:**

`RunExecutionActivation` is a frozen dataclass with
`interrupted_execution_count` and `interrupted_finalization_count`.
`activate_run_execution_boot`, `run_execution_boot_is_current`, and
`advance_run_execution_phase` accept an exact `db_path` plus the boot or
owner capability described by their name.
`run_execution_owner_fence_is_current` and `close_run_execution_owner`
accept an existing `sqlite3.Connection`, an exact
`RunExecutionOwnerHandle`, and their expected state/phase or close timestamp;
they never commit independently.
`create_or_replay_run_recovery` accepts:

```python
source_run_id: str
idempotency_key: str
boot_id: str
exact_profile_is_available: Callable[[str, str], bool]
db_path: str
```

and returns `RunRecoveryAcceptance`.

Task 3 repositories operate only on a database explicitly migrated by Task 2.
No live production module imports them yet.

- [ ] **Step 1: Write startup activation and convergence RED tests**

Create these exact tests:

- `test_first_boot_activation_inserts_exact_singleton_without_owner_mutation`
- `test_clean_next_boot_replaces_singleton_without_creating_failure_rows`
- `test_next_boot_converges_execution_owner_with_exact_existing_cause`
- `test_next_boot_converges_finalization_owner_with_exact_existing_cause`
- `test_convergence_uses_one_timestamp_for_owner_run_segment_and_cause`
- `test_convergence_is_all_or_nothing_across_multiple_active_owners`
- `test_convergence_writes_no_evidence_packet_artifact_review_or_lineage`
- `test_convergence_invokes_no_agent_model_graph_tool_or_provider_boundary`

Fault-inject each owner/run/segment/cause/boot write. Assert every row remains
at the previous boot state after rollback.

- [ ] **Step 2: Write corruption and stale-generation RED tests**

Required negative controls:

- `test_activation_rejects_ownerless_post_010_running_run`
- `test_activation_rejects_active_owner_on_terminal_run`
- `test_activation_rejects_owner_from_nonprevious_boot`
- `test_activation_rejects_wrong_segment_kind_sequence_or_status`
- `test_activation_rejects_duplicate_or_existing_failure_cause`
- `test_activation_rejects_partial_lineage_or_wrong_migration_marker`
- `test_old_boot_loses_current_boot_check_after_activation`
- `test_old_owner_loses_phase_and_terminal_fences_after_activation`

These are deliberate raw-state corruption fixtures. Keep them local to the
test file and label them as negative controls.

- [ ] **Step 3: Write phase and owner helper RED tests**

- `test_phase_fence_updates_execution_to_finalization_once`
- `test_phase_fence_requires_current_boot_owner_run_segment_and_state`
- `test_phase_fence_rejects_backward_or_second_transition`
- `test_owner_fence_can_require_execution_or_finalization_phase`
- `test_close_owner_clears_private_ids_and_uses_terminal_timestamp`
- `test_close_owner_is_connection_scoped_and_rolls_back_with_caller`

- [ ] **Step 4: Write replacement repository RED tests**

Use a source created by real dormant migration or startup convergence. Required
tests:

- `test_recovery_creates_run_segment_dispatch_and_lineage_in_one_transaction`
- `test_recovery_copies_exact_query_thread_profile_version_and_scope`
- `test_recovery_returns_exact_acceptance_without_private_authority`
- `test_same_key_and_source_replays_same_replacement`
- `test_lost_response_style_replay_changes_only_replay_flag`
- `test_same_key_different_source_conflicts_without_new_rows`
- `test_same_key_changed_canonical_snapshot_conflicts`
- `test_different_key_bound_source_conflicts_without_new_rows`
- `test_replacement_as_source_is_exhausted`
- `test_ineligible_source_and_profile_drift_create_nothing`
- `test_profile_drift_keeps_source_immutable_and_returns_not_eligible`
- `test_corrupt_owner_cause_scope_or_lineage_is_unavailable`
- `test_stale_route_boot_cannot_create_or_replay`
- `test_concurrent_same_key_requests_create_exactly_one_replacement`
- `test_each_insert_failure_rolls_back_key_run_segment_dispatch_and_lineage`

Snapshot the source run, owner, cause, Evidence, packet, artifact, review,
verification, publication, and delivery rows before every acceptance/replay/
rejection test. They must be logically unchanged afterward.

- [ ] **Step 5: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_run_execution_repository.py \
  tests/unit/test_run_recovery_repository.py
```

Expected: collection fails because both repositories are absent.

- [ ] **Step 6: Implement startup convergence and activation**

Use one configured SQLite connection with `PRAGMA foreign_keys=ON`,
`busy_timeout=5000`, and:

```sql
BEGIN IMMEDIATE
```

Algorithm:

```text
verify exact 010 schema and rows
read singleton previous boot, if present
read every post-010 running run and every active owner
require exact one-to-one running/active-owner correspondence
if active owners exist:
    require a previous singleton
    require every active owner.boot_id == previous singleton.boot_id
for each active owner:
    derive existing cause only from persisted owner.phase
    update exact run running/not_required/pending/v1
      -> failed/not_required/failed/v2
    update exact initial segment running -> failed
    insert one existing observed failure cause at v2
    update owner active -> interrupted
    clear boot_id and owner_id
    set recovery_reason=previous_boot_interrupted
    use one exact UTC timestamp for all terminal writes
replace or insert singleton with supplied new boot_id and activation time
verify exact post-transaction rows using the same connection
commit
```

The activation result contains counts only. It does not contain run, boot, or
owner identities and is not logged with raw values.

- [ ] **Step 7: Implement phase and owner transaction helpers**

`advance_run_execution_phase` must update exactly one row only when:

```text
singleton.boot_id == handle.boot_id
owner run/segment/boot/owner all match
owner status=active
owner phase=execution
run running/state_version=1
initial segment running
```

The transaction changes only:

```text
owner.phase=finalization
owner.phase_updated_at=<UTC now>
```

`run_execution_owner_fence_is_current` and `close_run_execution_owner` accept
an existing connection so the caller's business transaction cannot be split.
They do not open, commit, or roll back independently.

- [ ] **Step 8: Implement exact source snapshot validation**

`api/run_recovery_repository.py` owns a private reader that returns a fully
validated immutable snapshot only when:

```text
source run exists
execution/review/delivery = failed/not_required/failed
state_version = 2
initial segment = failed, kind initial, sequence 0
owner = interrupted
owner reason and phase are closed literals
owner/run/segment/cause timestamps are coherent
failure cause matches:
  previous execution -> execution/execution_error
  previous finalization -> finalization/run_finalization_failed
profile ID/version are exact strings
scope_json is canonical compact JSON object
source is not any replacement_run_id
```

Do not normalize or upgrade invalid query, thread, profile, version, or scope.
Unbound corruption raises private `run_recovery_state_invalid`, which the API
will later map to public `run_recovery_unavailable`.

An exact profile ID/version that is no longer available is an eligibility
failure, not state corruption and not permission to upgrade. Return the
existing bounded `run_recovery_not_eligible` classification, create no key,
run, segment, dispatch, or lineage row, and leave the failed source unchanged.
Task 8 must document the operator choices: restore the exact profile
implementation and replay the same recovery request, or inspect the source and
deliberately create an unrelated ordinary keyed run from caller-retained input.

- [ ] **Step 9: Implement one-hop keyed replacement transaction**

Validate/hash the raw key before SQLite. Inside one `BEGIN IMMEDIATE`:

1. verify migration and exact route `boot_id`;
2. read an existing `key_hash` row first;
3. if the key is bound to another source, return conflict without creating
   rows;
4. validate the requested source snapshot and compute its canonical hash;
5. if the key exists, require exact source, request hash, reason, phase,
   attempt, and replacement rows, then return replay;
6. reject any source already present as `replacement_run_id`;
7. reject any different key when `source_run_id` already has lineage;
8. invoke the immutable in-process `exact_profile_is_available` callback and
   require exact version equality;
9. create fresh `run_`, initial segment, and pending dispatch identities using
   the source's exact immutable request fields;
10. insert one exact lineage row;
11. verify all new rows and commit once.

The insert code may mirror `_insert_run_identity`, but it must accept the
existing connection and must not call public `create_run` or
`create_or_replay_run`, open another transaction, use the ordinary key
namespace, or wake a worker.

- [ ] **Step 10: Stabilize bounded conflict classification**

Repositories expose only:

```text
run_execution_recovery_unavailable
run_execution_boot_stale
run_execution_owner_stale
run_recovery_source_not_found
run_recovery_not_eligible
run_recovery_exhausted
run_recovery_conflict
run_recovery_key_invalid
run_recovery_state_invalid
run_recovery_unavailable
```

Exception strings contain only the code. Raw SQLite exceptions are chained
internally but never serialized or logged.

- [ ] **Step 11: Run GREEN and commit**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_run_execution_models.py \
  tests/unit/test_run_execution_migrations.py \
  tests/unit/test_run_execution_repository.py \
  tests/unit/test_run_recovery_models.py \
  tests/unit/test_run_recovery_repository.py
git diff --check
git add \
  api/run_execution_repository.py \
  api/run_recovery_repository.py \
  tests/unit/test_run_execution_repository.py \
  tests/unit/test_run_recovery_repository.py
git commit -m "feat(recovery): add dormant recovery transactions"
```

Expected: the four Task 3 files only. Production startup, dispatch, API, and
Tool Client behavior are still unchanged.

---

### Task 4: Atomically Activate Boot Ownership Across The Complete Running Lifecycle

This is one semantic task and one commit. It is intentionally larger than the
other tasks because process writer exclusion, migration activation, start
ownership, shutdown draining, phase fencing, and all running terminal writers
must become authoritative together.

**Production files:**

- Modify: `api/database.py`
- Create: `api/run_execution_writer_lock.py`
- Modify: `api/run_dispatch_models.py`
- Modify: `api/run_dispatch_repository.py`
- Modify: `api/run_dispatch_worker.py`
- Modify: `api/run_repository.py`
- Modify: `api/run_migrations.py`
- Modify: `api/task_tracker.py`
- Modify: `api/server.py`

**Fixture/proof callers:**

- Modify: `scripts/bounded_live_producer_container_fixture.py`
- Modify: `scripts/evidence_verification_container_fixture.py`
- Modify: `scripts/agent_evaluation_replay.py`
- Modify: `scripts/run_dispatch_reconciliation_proof.py`
- Modify: `scripts/run_failure_cause_proof.py`
- Modify: `scripts/downstream_consumer_contract.py`
- Modify: `scripts/durable_hitl_fixture.py`

**Test support and retained tests:**

- Create: `tests/run_execution_helpers.py`
- Modify: `tests/unit/test_database_config.py`
- Create: `tests/unit/test_run_execution_writer_lock.py`
- Modify: `tests/unit/test_run_dispatch_models.py`
- Modify: `tests/unit/test_run_dispatch_repository.py`
- Modify: `tests/unit/test_run_dispatch_worker.py`
- Modify: `tests/unit/test_run_migrations.py`
- Modify: `tests/unit/test_task_tracker.py`
- Modify: `tests/unit/test_task_tracker_timeout.py`
- Modify: `tests/unit/test_run_repository.py`
- Modify: `tests/integration/test_run_dispatch_api.py`
- Modify: `tests/integration/test_run_api.py`
- Modify: `tests/integration/test_durable_review_lifecycle.py`
- Modify: `tests/integration/test_bounded_live_producer_proof.py`
- Modify: `tests/unit/test_publication_service.py`
- Modify: `tests/unit/test_review_repository.py`
- Modify: `tests/unit/test_evidence_verification_container_fixture.py`
- Create: `tests/integration/test_run_execution_recovery.py`
- Modify: `tests/integration/test_strict_citation_profile.py`
- Modify: `tests/integration/test_context_reliability_regression.py`

If fresh inventory finds another positive caller that can enter or leave
`running`, add that exact path to Task 4 before editing and report it to the
authority. Do not silently preserve it through an ownerless overload.

- [ ] **Step 1: Write exclusive-writer and production activation RED tests**

In `tests/unit/test_run_execution_writer_lock.py`, add:

- `test_pure_database_path_resolution_does_not_create_missing_parent`
- `test_writer_bootstrap_creates_missing_nested_parent_without_database`
- `test_first_writer_acquires_canonical_db_scoped_lock`
- `test_two_processes_bootstrap_missing_parent_and_only_one_acquires`
- `test_second_process_writer_fails_nonblocking_with_bounded_code`
- `test_contention_does_not_open_or_mutate_the_application_database`
- `test_lock_descriptor_is_noninheritable_nofollow_and_private`
- `test_lock_file_contains_no_path_pid_boot_or_owner_identity`
- `test_unsupported_advisory_lock_platform_fails_closed`
- `test_unsupported_platform_does_not_create_database_or_runtime_directories`
- `test_real_sigkill_releases_writer_lock_for_a_fresh_process`

The contention test uses a separate process. It must prove a bounded immediate
failure rather than waiting on a timeout. The `SIGKILL` test verifies the first
child crossed and read back lock acquisition, asserts exact
`returncode == -signal.SIGKILL`, then proves a fresh process acquires the same
canonical DB-scoped lock. No test treats stale lock-file existence as
ownership; only the kernel-held descriptor is authority.

The missing-parent tests start with a nested configured DB path whose parent
does not exist. Pure path resolution must leave the filesystem unchanged. The
writer bootstrap may create and validate only that canonical parent, after
which two real processes race the same fixed sibling lock and exactly one wins.
Before any migration or application connection, assert that the DB, backup,
output, review probe, boot, and worker artifacts do not exist; the only allowed
residue is the validated empty parent and fixed zero-byte lock file.

In `tests/integration/test_run_execution_recovery.py`, add:

- `test_lifespan_bootstraps_missing_nested_db_parent_before_writer_acquire`
- `test_lifespan_acquires_writer_before_any_migration_backup_or_boot_write`
- `test_lifespan_writer_contention_fails_before_database_and_workers`
- `test_server_import_does_not_create_output_directory`
- `test_review_writability_probes_run_only_after_writer_acquire`
- `test_lifespan_applies_010_and_activates_boot_before_dispatch_worker`
- `test_lifespan_fails_before_workers_when_010_or_convergence_is_invalid`
- `test_testclient_context_runs_activation_and_shutdown`
- `test_lifespan_clears_private_boot_state_on_shutdown`
- `test_no_periodic_recovery_worker_or_heartbeat_task_is_started`
- `test_shutdown_closes_task_admission_before_worker_stop`
- `test_shutdown_drains_tracked_runs_and_callbacks_before_writer_release`
- `test_shutdown_does_not_release_writer_while_owner_finalizer_is_unsettled`
- `test_shutdown_cancellation_settles_drain_before_writer_release`
- `test_drain_failure_never_calls_writer_release`

Instrument production factories and assert exact ordering:

```text
pure configured-DB path parsing
lock primitive support validation
canonical DB parent bootstrap and validation
exclusive writer acquire
output directory and review writability probes
migration 010 apply/verify
boot convergence/activation
tracked-task admission open
dispatch worker construction/start
review worker construction/start when enabled
request
tracked-task admission close
worker stop and settlement
tracked run cancellation/finalizer settlement
tracked registry empty
private boot state clear
exclusive writer release
```

In `tests/unit/test_task_tracker_timeout.py`, retain every current timeout and
cancellation race and add:

- `test_close_task_admission_rejects_new_coroutine_without_scheduling`
- `test_close_and_drain_snapshots_after_admission_is_closed`
- `test_drain_cancels_and_settles_each_task_and_callback_once`
- `test_drain_returns_only_after_active_registry_is_empty`
- `test_open_task_admission_requires_an_empty_closed_registry`

A rejected coroutine is closed by the caller/registry so it cannot leak a
`RuntimeWarning`. The drain has no elapsed-time lease or fallback release.

- [ ] **Step 2: Write atomic start and owner-box RED tests**

Add or update:

- `test_dispatch_claim_carries_exact_private_boot_identity`
- `test_stale_boot_cannot_claim_or_start_after_new_activation`
- `test_start_fence_returns_exact_owner_handle_after_commit`
- `test_start_fence_atomically_writes_dispatch_run_segment_and_owner`
- `test_owner_insert_or_boot_check_failure_rolls_back_all_start_writes`
- `test_scheduler_assigns_committed_owner_handle_exactly_once`
- `test_cancellation_during_start_settlement_preserves_committed_handle`
- `test_timeout_callback_never_synthesizes_a_missing_owner`

Update old boolean assertions. Winning `start_run_dispatch` returns
`RunExecutionOwnerHandle`; losing/stale start returns `None`.

- [ ] **Step 3: Write persisted phase and terminal RED tests**

Required cases:

- `test_harness_outcome_persists_finalization_phase_before_strict_citation`
- `test_harness_outcome_persists_phase_before_artifact_review_or_publication`
- `test_stale_phase_fence_stops_all_business_work`
- `test_normal_completion_closes_exact_owner_in_terminal_transaction`
- `test_execution_exception_closes_exact_execution_owner`
- `test_finalization_exception_closes_exact_finalization_owner`
- `test_timeout_uses_persisted_owner_phase_for_public_cause`
- `test_cancellation_uses_persisted_owner_phase_for_public_cause`
- `test_stale_normal_timeout_cancel_and_fallback_finalizers_are_noops`
- `test_owner_close_failure_rolls_back_every_business_and_terminal_write`
- `test_pending_dispatch_failure_remains_ownerless_and_compatible`

For stale cases, assert zero new rows in every existing business table and no
failure-cause overwrite.

- [ ] **Step 4: Write direct-caller and source-contract RED tests**

`tests/run_execution_helpers.py` must use only production APIs:

```python
@dataclass(frozen=True)
class StartedRun:
    boot_id: str
    claim: RunDispatchClaim
    handle: RunExecutionOwnerHandle

def activate_and_start_created_run(
    *,
    db_path: str,
    run_id: str,
) -> StartedRun:
    migrate_run_execution_recovery_with_backup(db_path=db_path)
    boot_id = new_boot_id()
    activate_run_execution_boot(db_path=db_path, boot_id=boot_id)
    claim = claim_run_dispatch(
        db_path=db_path,
        worker_id=f"dispatch_worker_{uuid.uuid4().hex}",
        boot_id=boot_id,
        lease_seconds=30,
        run_id=run_id,
    )
    if claim is None:
        raise AssertionError("expected exact pending dispatch claim")
    handle = start_run_dispatch(db_path=db_path, claim=claim)
    if handle is None:
        raise AssertionError("expected exact protected start")
    return StartedRun(boot_id=boot_id, claim=claim, handle=handle)
```

The helper:

1. applies migration `010`;
2. activates a generated boot;
3. claims the exact existing pending dispatch;
4. crosses `start_run_dispatch`;
5. returns the real handle.

It may not update run/segment/owner rows directly.

Add these narrow AST/source tests:

- `test_production_cannot_transition_directly_into_running`
- `test_every_running_finalize_call_supplies_owner_handle`
- `test_negative_corruption_fixtures_are_not_imported_by_production`

Also make these current positive journeys explicit RED-to-GREEN contracts:

- `scripts/agent_evaluation_replay.py` activates one boot, opens task admission,
  supplies that boot to its claim, carries one owner box through
  `_run_dispatched_with_persistence`, and closes/drains admission before the
  replay case exits;
- `tests/integration/test_durable_review_lifecycle.py` uses the same
  boot/owner/admission lifecycle around its private dispatch path;
- `tests/integration/test_bounded_live_producer_proof.py` supplies one exact
  activated boot to both its external claim and
  `create_fixture_worker(..., boot_id=...)`;
- `tests/unit/test_task_tracker.py` explicitly opens admission before positive
  scheduling and closes/drains it in teardown; it may not use
  `clear_active_tasks()` to erase a live task.

Add exact regression names:

- `test_evaluation_replay_uses_boot_owner_and_drains_task_admission`
- `test_durable_review_private_dispatch_uses_boot_owner_and_drains`
- `test_bounded_producer_claim_and_fixture_worker_share_exact_boot`
- `test_tracker_positive_fixture_opens_then_closes_and_drains_admission`

Do not reject SQL schema literals or deliberately malformed test fixtures by
raw repository-wide substring scanning.

- [ ] **Step 5: Run the complete Task 4 RED set**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_database_config.py \
  tests/unit/test_run_execution_writer_lock.py \
  tests/unit/test_run_dispatch_models.py \
  tests/unit/test_run_dispatch_repository.py \
  tests/unit/test_run_dispatch_worker.py \
  tests/unit/test_task_tracker.py \
  tests/unit/test_task_tracker_timeout.py \
  tests/unit/test_run_repository.py \
  tests/unit/test_run_migrations.py \
  tests/integration/test_run_dispatch_api.py \
  tests/integration/test_run_execution_recovery.py \
  tests/integration/test_durable_review_lifecycle.py \
  tests/integration/test_bounded_live_producer_proof.py \
  tests/integration/test_strict_citation_profile.py \
  tests/integration/test_context_reliability_regression.py \
  tests/integration/test_run_api.py \
  tests/unit/test_publication_service.py \
  tests/unit/test_review_repository.py \
  tests/unit/test_evidence_verification_container_fixture.py
```

Expected: failures demonstrate missing writer exclusion/drain, boot
propagation, handle return, owner-aware terminal APIs, startup activation, and
the clean-checkout missing-parent path.

- [ ] **Step 6: Implement the DB-scoped process-lifetime writer gate**

First change `api/database.py` so `application_db_path()` is a pure canonical
resolver: it may read the explicit argument/environment/default and resolve the
identity, but it must not create a directory, open SQLite, probe writability, or
touch a file. Preserve `:memory:` handling only for the existing explicit
test/tool path.

Add one explicit runtime helper:

```python
def prepare_application_db_parent(db_path: Path) -> Path: ...
```

It accepts the already resolved DB identity and creates its missing parent with
`parents=True`, `exist_ok=True`, and a private requested mode. It then requires
the parent to be a directory, re-resolves the DB identity, and fails closed if
the canonical identity changed.
It must not chmod a pre-existing directory, create/open the DB, create a
backup, run a general writability probe, or log the path. Direct isolated
backup/restore/migration helpers that require a parent must call an explicit
mutation helper in their own already-authorized scope rather than regaining an
implicit side effect through path resolution.

Create `api/run_execution_writer_lock.py` using only the standard library.
Before any parent creation, require the lock primitives below. Then invoke the
single controlled parent bootstrap, derive the lock path from the canonical
absolute configured DB identity and a fixed suffix, and acquire it immediately.
The path is application-private and never enters a public error, log, response,
fixture, proof, or documentation example.

After primitive validation and parent bootstrap, open the fixed sibling lock
file with:

```text
O_RDWR | O_CREAT | O_CLOEXEC | O_NOFOLLOW
mode 0600
```

Require reliable `fcntl.flock`, `O_CLOEXEC`, and `O_NOFOLLOW` before invoking
`prepare_application_db_parent`; if any is unavailable, fail with
`run_execution_writer_unavailable` rather than mutating the filesystem,
following a link, inheriting a descriptor, or substituting another mechanism.
After opening:

1. set the descriptor non-inheritable;
2. require `fstat` to describe a regular file;
3. require no group/other permission bits, correcting only the task-owned lock
   file to `0600`;
4. acquire `fcntl.flock(fd, LOCK_EX | LOCK_NB)`;
5. map only `EACCES`/`EAGAIN` to
   `run_execution_writer_already_active`;
6. map parent-bootstrap, unsafe file type, permission, and other acquisition
   errors to `run_execution_writer_unavailable`;
7. retain the descriptor in an immutable one-release capability for the
   complete lifespan.

The file contains zero bytes. It never stores a PID, timestamp, boot ID,
owner ID, hostname, path, or token. Release unlocks and closes the exact
descriptor once. A stale empty file is harmless; `SIGKILL` releases the
kernel-held lock when the descriptor closes. Do not use a PID file, delete the
lock file on release, wait/retry contention, or infer liveness from file
metadata. The validated DB parent and fixed empty lock file are coordination
artifacts, not application data or evidence, and may remain after contention or
process death.

- [ ] **Step 7: Activate migration 010 through every initializer**

Restructure `init_run_schema` without a bypass:

```text
acquire existing schema init lock
apply/verify legacy through 009 with existing protections
call migrate_run_execution_recovery_with_backup exactly once
verify exact 010 marker/schema/rows
return
```

`api/run_migrations.py` must:

- add all `010` tables, index, columns, marker, and constraints to the required
  verifier;
- call the new cross-table verifier;
- include `010` in known checksum validation;
- ensure `migrate_with_backup` reaches the dedicated `010` function rather
  than creating its tables in an outer legacy transaction;
- preserve every existing publication, verification, review, idempotency,
  dispatch, and failure-cause backup behavior.

Any run, dispatch, review, verification, or publication initializer that
reaches a pre-010 database must therefore traverse the same public
`init_run_schema` or verify the exact marker before writing.

Do not change `build_through_009_fixture()` to call the newly extended public
initializer. Rerun `tests/unit/test_run_execution_migrations.py` after this
activation and require its pre-010 assertion to remain RED if `010` is present
before the dormant migration call.

- [ ] **Step 8: Acquire authority, activate boot, and release authority last**

`api/task_tracker.py` adds three production lifecycle operations:

```python
def open_tracked_task_admission() -> None: ...
def close_tracked_task_admission() -> None: ...
async def drain_tracked_tasks() -> None: ...
```

Admission state and the active-task registry are changed under one in-process
lock. Opening requires an empty registry. Closing is synchronous and wins
before a shutdown snapshot; `create_tracked_task` after close raises bounded
`task_tracker_closed` without scheduling the coroutine. Draining requires
closed admission, snapshots every registered wrapper task, cancels each,
settles each wrapper and its existing timeout/cancellation callback, and
returns only when the registry is empty. It has no timeout that would hand
authority to another process while finalization is still running.

The FastAPI lifespan order is exact:

```text
pure environment/configured-DB identity parsing
validate Unix advisory-lock primitives
create and validate only the canonical DB parent when missing
acquire_run_execution_writer (non-blocking)
create output directory and run review writability probes
init_run_schema -> legacy through 009 -> migration 010
activate fresh boot
open tracked-task admission
construct/start dispatch and review workers
yield
close tracked-task admission
signal both worker loops to stop
await both worker loops
drain all tracked run tasks and callbacks
require active-task registry empty
clear app state and private boot identity
release writer capability
```

Before lock acquisition, parse only the configured application DB identity and
other values that do not create probes, DB connections, application data, or
logs containing private identity. The sole permitted filesystem mutation is
the controlled canonical DB-parent bootstrap required to create the sibling
lock; acquire the lock immediately afterward. Move the current module-import
`output_dir.mkdir(...)` into the locked lifespan. Run
`validate_review_runtime` and its writable-parent probes only after lock
acquisition because the live helper creates directories and temporary probes.

Except for the validated parent/empty-lock coordination artifacts, writer
acquisition must precede every supported application-lifespan migration,
backup, DB connection, output/review writability mutation, boot, worker, or
request mutation. A contention/unsupported failure therefore leaves the
application DB, backup, output, probe, migration, boot, worker, and other
runtime surfaces untouched. Dormant repository/migration functions remain
internal primitives for isolated tests/proofs; they are not a supported
concurrent live-DB writer interface.
The runbook must forbid invoking them or any fixture/proof script against the
live application DB. After successful migration:

```python
boot_id = new_boot_id()
activation = await asyncio.to_thread(
    activate_run_execution_boot,
    db_path=application_db_path,
    boot_id=boot_id,
)
app.state.run_execution_boot_id = boot_id
```

Only then construct:

```python
run_dispatch_worker = create_run_dispatch_worker(
    application_db_path,
    boot_id=boot_id,
)
```

Initialize `app.state.run_execution_boot_id = None` before the `try`, and clear
it only after worker loops and tracked tasks settle. Retain the writer
capability in a local lifespan variable, not `app.state`, and release it in the
last successful shutdown step. Log only bounded event codes and activation
counts. Do not log the DB path, lock path, descriptor, boot ID, task IDs, or
owner IDs.

If a tracked task or owner-aware callback cannot settle, `drain_tracked_tasks`
does not return and the writer capability is not voluntarily released. An
operator may terminate the process; the OS then releases the descriptor and a
fresh process performs normal startup convergence. Do not add a shutdown lease,
force-clear the registry, synthesize terminal state, or release early.

Create the drain as an inner task and use the existing shielded-settlement
pattern so cancellation of the outer lifespan shutdown cannot skip drain and
fall through to release. Release is an explicit call guarded by a successful
empty-registry result; the writer capability has no `__del__` or context-manager
auto-release. A drain exception also skips voluntary release and surfaces one
bounded shutdown authority error. Startup failure before task admission may
release only after migration restore/transaction rollback and proof that no
worker or tracked task exists.

- [ ] **Step 9: Bind boot identity to claim and start**

Extend `RunDispatchClaim`:

```python
boot_id: BootId
```

`RunDispatchWorker.__init__` requires `boot_id` and passes it to
`claim_run_dispatch`. The claim transaction verifies the current boot before
leasing a new candidate. Existing exact dispatch owner/attempt/payload rules
remain unchanged.

Change start signature:

```python
def start_run_dispatch(
    *,
    db_path: str | None,
    claim: RunDispatchClaim,
) -> RunExecutionOwnerHandle | None:
```

Inside the existing `BEGIN IMMEDIATE`, verify the singleton equals
`claim.boot_id`, generate the private owner ID inside repository code, perform
the existing three updates, insert one `active/execution` owner with the same
timestamp, then commit. Return the handle only after commit.

If any row count or insert fails, roll back all four authorities and return
`None` only for a clean stale/losing fence. Schema/corruption errors raise a
bounded exception.

- [ ] **Step 10: Assign and propagate the owner exactly once**

In `_schedule_run_dispatch`, construct one box before the coroutine and
callbacks:

```python
owner_box = RunExecutionOwnerBox()
```

Pass it to:

- `_run_dispatched_with_persistence`;
- `_run_started_v2_with_persistence`;
- `_mark_dispatched_timeout`;
- `_mark_dispatched_cancellation`;
- `_finalize_failed_run_v2`.

After the shielded start task returns a handle:

```python
if handle is None:
    return
owner_box.assign(handle)
```

Do this before advancing in-memory stage or invoking Agent code. Because the
tracked inner task is settled before timeout/cancel callbacks, a committed
handle cannot be lost. If a path observes `dispatch=started` but the box is
empty, log a bounded authority-unavailable code and perform no running-state
write; never synthesize a handle from the database.

- [ ] **Step 11: Persist finalization phase before any post-Harness work**

Immediately after `run_deep_agent` returns an outcome, before:

- strict-citation preparation/invocation;
- cited-Evidence marking;
- generic artifact construction;
- Talent artifact/review construction;
- publication/review workflow preparation;
- terminal persistence;

call:

```python
phase_won = await asyncio.to_thread(
    advance_run_execution_phase,
    db_path=db_path,
    handle=owner_box.require(),
)
if not phase_won:
    return
stage.advance_to_finalization()
```

This applies even when the Harness returns a bounded failure outcome. Existing
known Agent failure codes remain execution failure causes; the persisted owner
phase becomes authoritative specifically for startup convergence,
timeout/cancellation classification, and failures occurring after the phase
transition.

- [ ] **Step 12: Require owner-aware finalization and current fence**

Change:

```python
def run_finalization_fence_is_current(
    *,
    run_id: str,
    segment_id: str,
    expected_state_version: int,
    owner_handle: RunExecutionOwnerHandle,
    db_path: str | None = None,
) -> bool:
```

It must join the boot singleton and active owner and require
`phase='finalization'`.

Extend the existing keyword-only `finalize_run_transaction` signature with:

```python
owner_handle: RunExecutionOwnerHandle | None = None
```

Rules:

- if `allowed_previous_statuses` contains `running`, an exact owner is
  mandatory;
- if it contains `pending` only, an owner is forbidden and existing fixture/
  dispatch compatibility remains;
- direct mixed `{pending, running}` finalization is rejected;
- normal completed finalization requires persisted owner phase
  `finalization`;
- timeout/cancellation/finalization failure derives or verifies its public
  phase from the persisted owner row;
- known bounded Harness failure retains the existing execution cause but still
  closes the exact owner after the persisted finalization phase;
- closing the owner is the last write inside the same transaction and uses the
  same terminal timestamp;
- owner close failure rolls back every run, segment, Evidence, packet,
  artifact, review, publication, delivery, and cause write.

Change `transition_run` to reject any target `running` and any allowed previous
status `running`. The production start and owner-aware terminal transaction are
the only legal running boundaries.

- [ ] **Step 13: Migrate every live direct caller**

Apply the classification table above:

- worker/proof constructors receive a boot ID;
- start callers accept a handle rather than comparing `is True`;
- running finalizers pass the exact `owner_handle`;
- `tests/integration/test_strict_citation_profile.py` passes the owner box into
  its private dispatch entry and exact handles into both injected running
  finalizers;
- `tests/integration/test_context_reliability_regression.py` passes the same
  production owner box/handle contract into its private dispatch entry;
- `scripts/agent_evaluation_replay.py` and
  `tests/integration/test_durable_review_lifecycle.py` explicitly own one
  isolated boot plus an open/close/drain task-admission lifecycle;
- `tests/integration/test_bounded_live_producer_proof.py` shares one boot
  identity across its claim and fixture worker;
- tracker unit tests no longer depend on implicit process-global open
  admission or erase live entries during cleanup;
- positive direct transitions use the real test helper or production
  migration/activation/claim/start path;
- pending-to-terminal fixtures remain unchanged;
- raw malformed state exists only in named negative-control tests.

Rerun the inventory command and review every match manually. The narrow source
contract must cover every production running finalizer and private dispatch
entry, then explicitly exclude only named raw corruption fixtures. Record the
path-by-path classification in the Task 4 commit body; do not add a production
overload, default owner, lookup-by-run fallback, or fixture-only bypass.

- [ ] **Step 14: Run focused GREEN**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_run_execution_models.py \
  tests/unit/test_database_config.py \
  tests/unit/test_run_execution_writer_lock.py \
  tests/unit/test_run_execution_migrations.py \
  tests/unit/test_run_execution_repository.py \
  tests/unit/test_run_dispatch_models.py \
  tests/unit/test_run_dispatch_repository.py \
  tests/unit/test_run_dispatch_worker.py \
  tests/unit/test_task_tracker.py \
  tests/unit/test_task_tracker_timeout.py \
  tests/unit/test_run_repository.py \
  tests/unit/test_run_migrations.py \
  tests/integration/test_run_dispatch_api.py \
  tests/integration/test_run_execution_recovery.py \
  tests/integration/test_durable_review_lifecycle.py \
  tests/integration/test_bounded_live_producer_proof.py \
  tests/integration/test_strict_citation_profile.py \
  tests/integration/test_context_reliability_regression.py \
  tests/integration/test_run_api.py \
  tests/unit/test_publication_service.py \
  tests/unit/test_review_repository.py \
  tests/unit/test_evidence_verification_container_fixture.py
```

Expected: zero failures.

- [ ] **Step 15: Run retained proof and lifecycle GREEN**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/run_dispatch_reconciliation_proof.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/run_failure_cause_proof.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/agent_evaluation_v2_gate.py check

PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/integration/test_run_creation_idempotency_proof.py \
  tests/integration/test_run_dispatch_reconciliation_proof.py \
  tests/integration/test_run_failure_cause_proof.py \
  tests/integration/test_durable_review_kill9.py \
  tests/integration/test_agent_evaluation_v2_gate.py \
  tests/integration/test_strict_citation_profile.py \
  tests/integration/test_evidence_verification_compatibility.py \
  tests/integration/test_run_result_api.py
```

Expected: all retained provider-free contracts pass without changing their
public proof schemas or claims.

- [ ] **Step 16: Commit the atomic activation**

Before staging:

```bash
git diff --check
git status --short
rg -n \
  'RunDispatchClaim\(|RunDispatchWorker\(|claim_run_dispatch\(|start_run_dispatch\(|create_tracked_task\(|finalize_run_transaction\(|transition_run\(|_run_dispatched_with_persistence\(|_schedule_run_dispatch\(' \
  api scripts tests --glob '*.py'
```

Stage every Task 4 path together and inspect:

```bash
git diff --cached --check
git diff --cached --stat
git diff --cached
git commit -m "feat(recovery): fence running execution by boot owner"
```

Expected: one semantic Task 4 commit. If the complete staged diff is not
coherent or any retained test is red, unstage without discarding WIP and stop;
do not commit a partial activation.

---

### Task 5: Add The Explicit Zero-Body Recovery API

**Files:**

- Modify: `api/server.py`
- Create: `tests/integration/test_run_recovery_api.py`
- Modify: `tests/integration/test_run_api.py`

**Public interface:**

```text
POST /api/runs/{source_run_id}/retries
Idempotency-Key: required
body: zero bytes
success: HTTP 202 + exact dra.run-recovery.v1
```

- [ ] **Step 1: Write middleware-order RED tests**

Use the existing runtime access configuration and a `TestClient` context so
lifespan boot activation runs. Spy on:

- body guard;
- recovery repository;
- targeted `dispatch_run`;
- `wake`.

Required tests:

- `test_missing_api_key_is_rejected_before_body_repository_and_wake`
- `test_wrong_api_key_is_rejected_before_body_repository_and_wake`
- `test_correct_api_key_reaches_zero_body_guard_then_repository`
- `test_loopback_mode_preserves_existing_runtime_access_behavior`
- `test_recovery_does_not_add_a_second_authentication_header`

Existing runtime-access denials retain their current response shape; do not map
them into recovery errors.

- [ ] **Step 2: Write zero-body RED tests**

Required cases:

- `test_zero_bytes_without_content_length_are_accepted`
- `test_zero_content_length_and_zero_bytes_are_accepted`
- `test_positive_content_length_is_rejected_before_stream_and_repository`
- `test_invalid_content_length_is_rejected_before_stream_and_repository`
- `test_whitespace_object_null_and_one_byte_chunk_are_rejected`
- `test_chunked_body_guard_stops_after_first_nonempty_chunk`
- `test_body_is_never_parsed_as_json_or_pydantic`

Include `b" "`, `b"{}"`, `b"null"`, and an async stream that yields one byte
without a content length. Every rejection is exact HTTP `422` and proves zero
repository/wake calls.

- [ ] **Step 3: Write key, success, replay, and error RED tests**

Required tests:

- `test_missing_or_malformed_recovery_key_fails_after_body_before_repository`
- `test_first_recovery_returns_exact_ten_field_202_contract`
- `test_replay_returns_same_replacement_and_only_flips_replay_flag`
- `test_source_not_found_maps_to_exact_404_envelope`
- `test_not_eligible_exhausted_and_conflict_map_to_exact_409_envelopes`
- `test_profile_drift_maps_to_not_eligible_and_preserves_failed_source`
- `test_one_hop_exhaustion_creates_no_hidden_fallback_or_second_post`
- `test_state_corruption_and_repository_failure_map_to_exact_503_envelope`
- `test_every_recovery_error_has_exact_keys_messages_retryability_and_request_id`
- `test_recovery_errors_never_expose_private_authority_or_exception_text`

The exact error key set is:

```python
{
    "code",
    "problem",
    "cause",
    "fix",
    "retryable",
    "run_id",
    "request_id",
}
```

`run_id` is always `None`; `request_id` matches
`^request_[0-9a-f]{32}$`.

- [ ] **Step 4: Write post-commit scheduling RED tests**

- `test_repository_commit_precedes_targeted_dispatch_and_wake`
- `test_dispatch_false_after_commit_still_returns_same_202`
- `test_wake_exception_after_commit_still_returns_same_202`
- `test_post_commit_failure_logs_only_bounded_code_without_identities`
- `test_replay_requests_targeted_dispatch_and_wake_again`
- `test_precommit_failure_returns_503_and_never_dispatches`

- [ ] **Step 5: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/integration/test_run_recovery_api.py \
  tests/integration/test_run_api.py
```

Expected: new API tests fail because the route and body guard are absent.

- [ ] **Step 6: Implement the bounded raw-body guard**

Import `Request` from FastAPI/Starlette and add a private helper:

```python
async def _require_zero_recovery_body(request: Request) -> None:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        normalized = content_length.strip()
        if (
            len(normalized) > 20
            or re.fullmatch(r"[0-9]+", normalized, flags=re.ASCII) is None
            or int(normalized) != 0
        ):
            raise RunRecoveryBodyNotAllowed

    async for chunk in request.stream():
        if chunk:
            # One observed byte is sufficient; never buffer or parse the body.
            raise RunRecoveryBodyNotAllowed
```

Use a bounded private exception with no body content. Do not call
`request.body()`, `request.json()`, or a Pydantic body model.

The route order is exactly:

```text
RuntimeAccessMiddleware
_require_zero_recovery_body
validate_recovery_key
create_or_replay_run_recovery
dispatch_run(replacement)
wake
response
```

- [ ] **Step 7: Implement exact public errors**

Use one closed mapping:

```python
_RUN_RECOVERY_ERRORS = {
    "run_recovery_source_not_found": (
        404,
        "The recovery source run does not exist.",
        "No ResearchRun matches the requested source identity.",
        "Verify the source run ID before requesting a replacement.",
        False,
    ),
    "run_recovery_not_eligible": (
        409,
        "The source run is not eligible for explicit replacement.",
        "The source is not the exact interrupted terminal contract.",
        "Inspect the source status and failure cause before requesting replacement.",
        False,
    ),
    "run_recovery_exhausted": (
        409,
        "The recovery hop budget is exhausted.",
        "The source is already a replacement run.",
        "Inspect the existing replacement; v1 does not create a second hop.",
        False,
    ),
    "run_recovery_conflict": (
        409,
        "The recovery request conflicts with an existing binding.",
        "The key or source is bound to different canonical recovery content.",
        "Retry the exact original source and key.",
        False,
    ),
    "run_recovery_key_invalid": (
        422,
        "The recovery idempotency key is invalid.",
        "Idempotency-Key failed the bounded public contract.",
        "Use 8-128 allowed high-entropy ASCII characters.",
        False,
    ),
    "run_recovery_body_not_allowed": (
        422,
        "The recovery request body is not allowed.",
        "Explicit replacement accepts no request body bytes.",
        "Remove the request body and retry with the same source and key.",
        False,
    ),
    "run_recovery_unavailable": (
        503,
        "Durable run recovery is unavailable.",
        "Recovery authority could not be read or committed safely.",
        "Retry the exact source and key after service recovery.",
        True,
    ),
}
```

Copy the exact `problem`, `cause`, and `fix` strings from the approved spec.
Map private `run_recovery_state_invalid`, migration errors, SQLite errors, and
unexpected repository validation failures to the single public unavailable
entry. Never serialize exception text.

Exact profile drift uses the already approved
`409 run_recovery_not_eligible` envelope; one-hop replacement-as-source uses
`409 run_recovery_exhausted`. Neither path mutates the source or silently
creates an ordinary run. The more detailed operator choices belong in the
runbook, not in a new public error schema.

- [ ] **Step 8: Implement the explicit route**

```python
@app.post(
    "/api/runs/{source_run_id}/retries",
    status_code=202,
)
async def retry_research_run(
    source_run_id: str,
    request: Request,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
):
    try:
        await _require_zero_recovery_body(request)
    except RunRecoveryBodyNotAllowed:
        return _run_recovery_error("run_recovery_body_not_allowed")
    if idempotency_key is None:
        return _run_recovery_error("run_recovery_key_invalid")
    try:
        validated_key = validate_recovery_key(idempotency_key)
    except ValueError:
        return _run_recovery_error("run_recovery_key_invalid")

    boot_id = app.state.run_execution_boot_id
    if not isinstance(boot_id, str):
        return _run_recovery_error("run_recovery_unavailable")
    try:
        acceptance = await asyncio.to_thread(
            create_or_replay_run_recovery,
            source_run_id=source_run_id,
            idempotency_key=validated_key,
            boot_id=boot_id,
            exact_profile_is_available=_exact_profile_is_available,
            db_path=sqlite_db_path(),
        )
    except RunRecoveryConflict as exc:
        public_code = (
            exc.code
            if exc.code in _RUN_RECOVERY_ERRORS
            else "run_recovery_unavailable"
        )
        return _run_recovery_error(public_code)
    except (RunExecutionConflict, sqlite3.Error, ValidationError):
        return _run_recovery_error("run_recovery_unavailable")

    worker = app.state.run_dispatch_worker
    try:
        dispatched = await worker.dispatch_run(acceptance.run_id)
        worker.wake()
    except Exception:
        logging.error("run_recovery_post_commit_wake_deferred")
    else:
        if not dispatched:
            logging.info("run_recovery_post_commit_dispatch_deferred")
    return JSONResponse(
        status_code=202,
        content=acceptance.model_dump(mode="json"),
    )
```

The exact profile callback is:

```python
def _exact_profile_is_available(
    profile_id: str,
    profile_version: str,
) -> bool:
    try:
        return profile_registry.get(profile_id).version == profile_version
    except KeyError:
        return False
```

Pass `app.state.run_execution_boot_id` into the repository. If it is absent,
return unavailable; do not generate or read a different boot.

After acceptance:

```python
try:
    dispatched = await worker.dispatch_run(acceptance.run_id)
    worker.wake()
except Exception:
    log bounded post-commit wake code
else:
    if not dispatched:
        log bounded deferred code
return JSONResponse(
    status_code=202,
    content=acceptance.model_dump(mode="json"),
)
```

Never roll back or relabel an already committed acceptance.

- [ ] **Step 9: Prove existing API compatibility**

Add explicit assertions that unchanged endpoints retain:

- ordinary keyed/unkeyed `POST /api/runs`;
- `GET /api/runs/{run_id}`;
- result and artifact endpoints;
- failure-cause projection;
- review/evidence/publication paths;
- middleware denial shapes.

No existing status or result response gains recovery lineage, reason, boot, or
owner fields.

- [ ] **Step 10: Run GREEN and commit**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_run_recovery_models.py \
  tests/unit/test_run_recovery_repository.py \
  tests/integration/test_run_recovery_api.py \
  tests/integration/test_run_api.py \
  tests/integration/test_run_result_api.py \
  tests/unit/test_secure_local_runtime_contracts.py \
  tests/integration/test_secure_local_runtime_proof.py
git diff --check
git add \
  api/server.py \
  tests/integration/test_run_recovery_api.py \
  tests/integration/test_run_api.py
git commit -m "feat(recovery): add explicit replacement endpoint"
```

Expected: all exact API and secure-runtime paths pass.

---

### Task 6: Add The Explicit Tool Client Retry Command

**Files:**

- Modify: `tools/decision_research_agent_tool.py`
- Modify: `tests/unit/test_decision_research_agent_tool.py`
- Create: `tests/integration/test_run_recovery_tool_journey.py`

**Interfaces produced:** `retry_run` accepts `source_run_id`,
`idempotency_key`, and `ToolConfig` and returns a JSON object.
`validate_recovery_response` accepts that JSON object and returns the strict
ten-field public acceptance as JSON-compatible values or raises
`run_recovery_response_invalid`.

- [ ] **Step 1: Write request and parser RED tests**

- `test_retry_posts_zero_body_to_encoded_source_path_with_key`
- `test_retry_parser_requires_source_run_id`
- `test_retry_parser_has_optional_key_wait_result_and_bounds`
- `test_retry_result_requires_wait_before_network`
- `test_existing_run_result_review_and_evidence_parsers_are_unchanged`

The HTTP stub must assert:

- `data is None`;
- no JSON payload was serialized;
- `Idempotency-Key` is exact;
- the encoded path ends in `/retries`;
- exactly one POST occurs.

- [ ] **Step 2: Write key-preservation and response RED tests**

- `test_retry_preserves_caller_supplied_key_exactly`
- `test_retry_generates_run_recovery_uuid_key_when_absent`
- `test_retry_help_requires_automation_to_persist_key_before_network`
- `test_retry_success_output_includes_source_replacement_and_key`
- `test_retry_validates_exact_success_schema_before_waiting`
- `test_invalid_json_nonobject_or_malformed_success_is_response_invalid`
- `test_ambiguous_failure_returns_source_and_same_key_without_second_post`
- `test_http_rejection_preserves_server_error_without_automatic_retry`

Generated and supplied keys must be present in local structured output for:

- success;
- connection failure;
- timeout;
- invalid JSON;
- non-object JSON;
- malformed success schema.

The server never echoes the key; this is caller-local recovery context.

- [ ] **Step 3: Write wait/result and non-automation RED tests**

- `test_retry_without_wait_returns_after_durable_acceptance`
- `test_retry_wait_polls_replacement_not_source`
- `test_retry_wait_result_fetches_replacement_result_only`
- `test_retry_wait_timeout_retains_source_replacement_and_key`
- `test_run_wait_and_result_never_call_retry_run`
- `test_failed_status_never_triggers_hidden_replacement`
- `test_malformed_success_does_not_generate_a_second_key_or_post`

- [ ] **Step 3A: Write the provider-free local-service journey RED tests**

Create:

- `test_documented_retry_command_reaches_durable_acceptance_within_90_second_test_budget`
- `test_documented_retry_wait_result_targets_replacement_within_120_second_test_budget`
- `test_provider_free_timing_diagnostics_have_exact_private_neutral_schema`

Run the production FastAPI app on a test-owned ephemeral loopback port with an
explicit temporary application DB and API secret. Build an eligible failed
source through the real migration, boot, dispatch-start, and next-boot
convergence transactions. For the first case, use an idle targeted dispatch
worker and invoke the actual Tool Client process with an explicit
pre-generated key; assert the real HTTP `202` acceptance, source/replacement
split, and exit within the 90-second test budget.

For the optional wait/result case, use the existing provider-free stub-Harness
technique with the production dispatch/finalization path so the replacement
reaches a deterministic result without model, graph, tool, provider, external
network, or external/provider credential access; the only credential is the
test-owned local runtime API secret. Invoke the actual Tool Client process with
`retry --wait --result`, assert it polls/fetches only the replacement, and
require completion within the two-minute test budget.

Both are test budgets enforced by bounded subprocess timeouts and monotonic
readback, not latency or SLA measurements. Record actual observed durations in
test diagnostics for authority review, but do not freeze them into public
claims. The local server and client must shut down cleanly and leave no
process, port, lock, DB, key, or temp artifact outside the test root.

Freeze separate test-owned monotonic observation points for each real client
journey without adding production telemetry:

```text
A0 = immediately before the acceptance-only Tool Client subprocess starts
A1 = after that real client exits successfully having validated HTTP 202
W0 = immediately before the wait/result Tool Client subprocess starts
W1 = after that real client exits successfully having validated the
     replacement result
```

The acceptance-only test records `acceptance_seconds = A1-A0`. The wait/result
test records only `completion_seconds = W1-W0`; it must not infer or emit an
acceptance duration from a server-side commit hook. Both observations therefore
end only after the independent real client has validated its promised public
result. No test wrapper may replace or short-circuit the production repository,
HTTP response, dispatch, polling, or result path.

On success, each journey prints one captured-by-default review diagnostic line:

```text
DRA_RECOVERY_TTHW_OBSERVATION {"case_id":"durable_acceptance","scope":"provider_free_local_fixture","status":"observed",...}
DRA_RECOVERY_TTHW_OBSERVATION {"case_id":"wait_result","scope":"provider_free_local_fixture","status":"observed",...}
```

The closed JSON payload is case-specific:

- `durable_acceptance` contains exactly `case_id`, `scope`, `status`,
  nonnegative rounded `acceptance_seconds`, and the exact
  `budget_seconds=90`;
- `wait_result` contains exactly `case_id`, `scope`, `status`, nonnegative
  rounded `completion_seconds`, and the exact `budget_seconds=120`.

Neither schema permits the other duration field. Both contain no port, path,
run/thread/segment identity, key, API secret, query, PID, or provider value.
Tests validate the exact keys, types, and bounds.
Ordinary captured pytest output stays quiet; authority review can read the
actual local observations with:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q -s \
  tests/integration/test_run_recovery_tool_journey.py \
  -k 'documented_retry'
```

These values remain review-only local-fixture observations. They are not
committed evidence and do not authorize a README latency, availability, SLA, or
production-performance claim.

- [ ] **Step 4: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_decision_research_agent_tool.py \
  tests/integration/test_run_recovery_tool_journey.py
```

Expected: new retry tests fail while all existing Tool Client cases remain
green.

- [ ] **Step 5: Implement zero-body client request**

Use the existing `_request_json` with `payload=None`:

```python
def retry_run(
    *,
    source_run_id: str,
    idempotency_key: str,
    config: ToolConfig,
) -> dict[str, Any]:
    encoded = parse.quote(source_run_id, safe="")
    return _request_json(
        "POST",
        _join_url(config.base_url, f"/api/runs/{encoded}/retries"),
        config=config,
        headers={"Idempotency-Key": idempotency_key},
    )
```

Do not change `_request_json` in a way that changes existing run/review/
evidence behavior.

- [ ] **Step 6: Validate exact success before composition**

Validate with `RunRecoveryAcceptance.model_validate(payload, strict=True)` or
an exact local adapter using the same closed model. Reject:

- missing or extra keys;
- coerced booleans/integers;
- invalid literals;
- source equal to replacement;
- empty replacement/thread/segment values;
- unexpected recovery attempt.

Map malformed 2xx responses to:

```text
code: run_recovery_response_invalid
source_run_id: <source>
idempotency_key: <same caller key>
```

Do not wait, fetch a result, create a new key, or issue a second POST.

- [ ] **Step 7: Add the explicit top-level command**

```text
retry
  --run-id <failed source>            required
  --idempotency-key <key>             optional
  --wait                              optional
  --result                            optional; requires --wait
  --poll-seconds <seconds>            default 1
  --wait-timeout-seconds <seconds>    default 600
```

When absent:

```python
idempotency_key = f"run-recovery-{uuid.uuid4()}"
```

The help text must state:

- `--run-id` is the immutable failed source;
- the command creates a new run;
- wait/result target the returned replacement;
- interactive callers should retain the key printed by the command;
- automation and crash-recoverable callers must generate and durably retain
  the key before invoking the command, then pass `--idempotency-key`;
- automatic key generation is invocation-local convenience only; it cannot
  recover a key if the client process dies before emitting local output;
- the key deduplicates replacement creation, not provider/tool effects.

Do not add a client ledger, hidden key file, environment mutation, automatic
replay, or a second persistence authority to solve client-process loss.

- [ ] **Step 8: Preserve bounded local error context**

For connection and timeout errors, preserve the existing code and add:

```python
{
    "source_run_id": source_run_id,
    "idempotency_key": idempotency_key,
}
```

For invalid JSON/non-object/malformed success, return
`run_recovery_response_invalid` with the same context. For a structured server
HTTP error, preserve the server's error envelope and do not falsely describe
the outcome as ambiguous.

Never log the key. It may appear only in final CLI stdout/stderr intended for
the invoking caller.

- [ ] **Step 9: Run GREEN and commit**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_decision_research_agent_tool.py \
  tests/integration/test_run_recovery_tool_journey.py
git diff --check
git add \
  tools/decision_research_agent_tool.py \
  tests/unit/test_decision_research_agent_tool.py \
  tests/integration/test_run_recovery_tool_journey.py
git commit -m "feat(recovery): add explicit retry client"
```

Expected: three files only; no runtime automatically imports or invokes the
client retry command.

---

### Task 7: Prove Real Process Death, Startup Convergence, Replay, And Rollback

**Files:**

- Create: `scripts/run_execution_recovery_crash_worker.py`
- Create: `scripts/run_execution_recovery_proof.py`
- Create: `tests/integration/test_run_execution_recovery_proof.py`
- Modify: `.github/workflows/ci.yml`

**Required command:**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/run_execution_recovery_proof.py check
```

The command prints exactly one deterministic JSON object to stdout and nothing
to stderr on success.

- [ ] **Step 1: Freeze the report contract in RED tests**

Use exact schema:

```python
{
    "schema_version": "dra.run-execution-recovery-proof.v1",
    "status": "valid",
    "source": "provider_free_real_process",
    "cases": [
        {
            "case_id": "exclusive_writer_fail_closed",
            "status": "passed",
            "observations": {
                "overlap_rejected": True,
                "database_untouched": True,
                "os_released_after_sigkill": True,
            },
        },
        {
            "case_id": "migration_backfill_restore",
            "status": "passed",
            "observations": {
                "backup_restored": True,
                "pre_v1_running_converged": True,
                "invented_business_rows": 0,
            },
        },
        {
            "case_id": "execution_phase_sigkill",
            "status": "passed",
            "observations": {
                "real_sigkill": True,
                "cause_exact": True,
                "active_owners_after": 0,
            },
        },
        {
            "case_id": "finalization_phase_sigkill",
            "status": "passed",
            "observations": {
                "real_sigkill": True,
                "cause_exact": True,
                "active_owners_after": 0,
            },
        },
        {
            "case_id": "stale_generation_fenced",
            "status": "passed",
            "observations": {
                "phase_writes": 0,
                "business_writes": 0,
                "terminal_writes": 0,
            },
        },
        {
            "case_id": "explicit_replacement_replay",
            "status": "passed",
            "observations": {
                "replacement_runs": 1,
                "lineage_rows": 1,
                "same_replacement": True,
                "replay_marked": True,
            },
        },
        {
            "case_id": "old_revision_rollback",
            "status": "passed",
            "observations": {
                "backup_restored": True,
                "old_revision_verified": True,
            },
        },
        {
            "case_id": "retained_contracts",
            "status": "passed",
            "observations": {
                "provider_calls": 0,
                "tool_calls": 0,
                "retained_checks_passed": True,
            },
        },
    ],
    "boundaries": {
        "process_lifetime_single_writer_gate": "proven",
        "single_node_startup_convergence": "proven",
        "execution_phase_interruption_classification": "proven",
        "finalization_phase_interruption_classification": "proven",
        "explicit_one_hop_replacement": "proven",
        "provider_free_contract": "proven",
        "exact_resume": "not_claimed",
        "exactly_once_execution": "not_claimed",
        "external_side_effect_deduplication": "not_claimed",
        "multi_instance_high_availability": "not_claimed",
        "live_provider_result": "not_observed",
        "automatic_release_or_rollback": "not_claimed",
    },
    "limits": [
        "Provider-free contract proof, not a production reliability measurement.",
        "Startup convergence is single-node and startup-only.",
        "Replacement creation does not deduplicate provider or tool side effects.",
        "No exact resume, automatic release, or business impact is observed.",
    ],
}
```

Exact ordered case IDs:

```text
exclusive_writer_fail_closed
migration_backfill_restore
execution_phase_sigkill
finalization_phase_sigkill
stale_generation_fenced
explicit_replacement_replay
old_revision_rollback
retained_contracts
```

Exact boundary keys:

```python
{
    "process_lifetime_single_writer_gate": "proven",
    "single_node_startup_convergence": "proven",
    "execution_phase_interruption_classification": "proven",
    "finalization_phase_interruption_classification": "proven",
    "explicit_one_hop_replacement": "proven",
    "provider_free_contract": "proven",
    "exact_resume": "not_claimed",
    "exactly_once_execution": "not_claimed",
    "external_side_effect_deduplication": "not_claimed",
    "multi_instance_high_availability": "not_claimed",
    "live_provider_result": "not_observed",
    "automatic_release_or_rollback": "not_claimed",
}
```

Required tests:

- `test_report_has_exact_ordered_cases_boundaries_and_limits`
- `test_report_validation_rejects_missing_extra_reordered_or_false_values`
- `test_report_bytes_are_deterministic_across_two_isolated_runs`
- `test_report_contains_no_private_identity_path_pid_key_hash_or_query`
- `test_check_has_one_json_stdout_line_and_empty_stderr`
- `test_invalid_arguments_and_injected_failures_have_stable_stderr`
- `test_each_proof_stage_maps_to_one_exact_safe_error_code`
- `test_stale_generation_stage_maps_every_fence_failure_to_one_safe_code`
- `test_module_import_is_silent_and_help_succeeds`

Freeze these failure-only stderr codes:

```text
run_execution_recovery_proof_writer_lock_failed
run_execution_recovery_proof_migration_failed
run_execution_recovery_proof_execution_sigkill_failed
run_execution_recovery_proof_finalization_sigkill_failed
run_execution_recovery_proof_stale_generation_failed
run_execution_recovery_proof_replacement_failed
run_execution_recovery_proof_rollback_revision_unavailable
run_execution_recovery_proof_rollback_import_mismatch
run_execution_recovery_proof_rollback_restore_failed
run_execution_recovery_proof_rollback_old_revision_verify_failed
run_execution_recovery_proof_retained_contract_failed
```

Each failure emits exactly one code line to stderr, no JSON success object to
stdout, and no exception, ID, path, PID, signal value, key/hash, query, or DB
identity.

- [ ] **Step 2: Write the overlapping-writer and OS-release RED proof**

Start child A with an explicit temporary DB identity. It acquires the real
production writer gate, readbacks the held descriptor state, atomically writes
only a fixed readiness marker, and blocks. Start child B against the same DB
identity and require:

```text
bounded run_execution_writer_already_active
non-blocking exit
application DB absent or byte/logically unchanged
no migration backup
no migration marker
no boot activation
no worker construction
```

Send real `signal.SIGKILL` to child A, assert exact
`returncode == -signal.SIGKILL`, then start fresh child C and prove the same
production gate can be acquired before normal migration/activation. Do not
delete the empty lock file, wait for a lease, or read a PID.

- [ ] **Step 3: Write real execution-phase SIGKILL RED test**

The child worker:

1. uses an explicit temporary DB;
2. runs migration and boot activation;
3. creates a provider-free run and dispatch claim;
4. crosses the real production start fence;
5. opens a separate read connection and verifies the committed running row,
   segment, active owner, and current boot;
6. atomically publishes a readiness marker containing only a fixed token;
7. blocks with signal-aware process waiting.

The parent:

1. waits for the marker with a bounded monotonic deadline;
2. sends real `signal.SIGKILL`;
3. waits for the process exit and asserts exact
   `returncode == -signal.SIGKILL`;
4. starts a fresh Python subprocess that applies/verifies migration and
   activates a new boot;
5. asserts exact interrupted owner, failed source, and
   `execution/execution_error`;
6. asserts no business payload was invented.

Use marker polling as synchronization; do not rely on an arbitrary delay to
guess that the transaction committed. The marker is published only after the
independent DB readback, so a naturally exited or pre-commit child cannot
satisfy the proof.

- [ ] **Step 4: Write real finalization-phase SIGKILL RED test**

The second child crosses the same start fence, calls the real persisted phase
transition, verifies it won with a separate DB readback, atomically signals
readiness, and blocks. The parent again asserts exact
`returncode == -signal.SIGKILL`. After real `SIGKILL`, a fresh process must
converge to:

```text
owner status=interrupted
owner phase=finalization
recovery reason=previous_boot_interrupted
public cause=finalization/run_finalization_failed
run/segment failed at the same timestamp
```

- [ ] **Step 5: Write stale-generation and no-side-effect RED tests**

Retain the predecessor handle privately in the proof harness. After the new
boot commits, assert the old handle loses:

- start;
- phase update;
- finalization fence;
- normal finalization;
- timeout finalization;
- cancellation finalization;
- fallback finalization.

Assert no new Evidence, packet, artifact, review, verification, publication,
delivery payload, cause, or lineage appears from stale attempts.

Fault-inject stale start, phase, normal finalization, timeout, cancellation, and
fallback checks independently. Every such proof-stage failure must emit only
`run_execution_recovery_proof_stale_generation_failed`; it may not be
misclassified as execution, finalization, or retained-contract failure, and it
must not include any private identity or exception text.

Patch/guard Agent, graph, model, subagent, tool, and provider entry points to
raise if invoked during migration or convergence.

- [ ] **Step 6: Write authenticated provider-free replacement RED test**

Use the production FastAPI app in a `TestClient` context with:

- explicit local `API_SECRET`;
- provider-disabled environment;
- an idle proof dispatch worker whose targeted dispatch returns `False`;
- no Agent/model/tool call.

POST zero bytes with the correct API key and recovery key. Assert first/replay
return the same replacement, only replay flag changes, the source stays
immutable, and exactly one lineage/run/segment/dispatch is created.

The idle worker demonstrates the approved post-commit scheduling boundary; it
is not a second recovery implementation.

- [ ] **Step 7: Write migration and old-revision rollback RED tests**

In an isolated temporary directory:

1. create a through-009 pre-feature fixture with the same test-only
   legacy-through-009 primitive used by Task 2 and assert `010` is absent;
2. create a diagnostic copy;
3. run current migration/verification and exact running backfill;
4. restore the dedicated pre-010 backup to a new rollback DB;
5. require `git cat-file -e <revision>^{commit}`, then export exact Git
   revision
   `bfd744a5611c7673d9385a45bed0131d6cb47655` with local `git archive`;
6. extract to a fresh root and record the exact source revision in a
   test-private marker created by the parent;
7. run a fresh provider-disabled Python subprocess with the export root as
   `cwd`, `PYTHONNOUSERSITE=1`, isolated mode, and the export root inserted
   first in `sys.path`;
8. clear any target `api`/repository modules from `sys.modules` before import,
   import the old migration/repository code, and open/verify the restored DB;
9. assert the private revision marker equals the exact SHA and every target
   module's resolved `__file__` is under the export root.

Do not check out, reset, or create a Git worktree. Do not mutate the live
application DB. The proof uses only temporary fixtures. Passing a path first
on `PYTHONPATH` without `cwd`, module-path, and isolated-process assertions is
not sufficient.

- [ ] **Step 8: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/integration/test_run_execution_recovery_proof.py
```

Expected: collection fails because the proof files are absent.

- [ ] **Step 9: Implement the bounded child worker**

The child accepts only private test-harness arguments:

```text
--db
--marker
--mode writer|execution|finalization
```

Writer mode acquires only the production writer gate and readbacks the held
state; execution/finalization modes follow the production lifecycle described
above. It emits no stdout/stderr on its successful readiness path. Marker
content is one fixed mode token, not a run/boot/owner/process identity. Use
`signal.pause()` where available after readiness; the parent owns termination.

- [ ] **Step 10: Implement deterministic proof assembly**

`build_report()` creates isolated temporary roots and returns only closed
booleans/counts. It never serializes:

- IDs generated by the run;
- temp paths;
- DB names;
- PIDs or exit signals;
- raw keys or hashes;
- boot/owner identities;
- fixture query/scope.

`serialize_report()` uses:

```python
json.dumps(
    validate_report(report),
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
) + "\n"
```

`check` prints the full deterministic report. There is no `build` command and
no committed evidence path.

Wrap each top-level proof stage in the closed safe-code mapping frozen in Step
1. Preserve chained exceptions only in-process for tests; never print their
text. Unknown failures map to the nearest owning stage's stable code rather
than a raw traceback.

- [ ] **Step 11: Make rollback identity available and add required CI**

The backend checkout must retain the fixed rollback revision. Change only the
backend job's existing checkout step to:

```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
  with:
    fetch-depth: 0
```

Use full history rather than a depth of two because the immutable rollback
revision will move farther from future PR heads. Before the proof, add a local
object preflight:

```yaml
- name: Verify crash-safe rollback source identity
  env:
    ROLLBACK_REVISION: bfd744a5611c7673d9385a45bed0131d6cb47655
  run: |
    git cat-file -e "$ROLLBACK_REVISION^{commit}"
    git archive --format=tar "$ROLLBACK_REVISION" >/dev/null
```

In the backend job, after the retained failure-cause/dispatch proofs and before
`Run tests`, add:

```yaml
- name: Run crash-safe execution recovery proof
  env:
    PYTHON_DOTENV_DISABLED: '1'
  run: python scripts/run_execution_recovery_proof.py check
```

Do not add secrets, provider variables, artifacts, uploads, Docker steps, or a
network service. `actions/checkout` may fetch repository history as the normal
hosted-CI source step; the proof itself performs no network access.

- [ ] **Step 12: Run GREEN and retained gates**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/integration/test_run_execution_recovery_proof.py

PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/run_execution_recovery_proof.py check

PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/run_dispatch_reconciliation_proof.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/run_failure_cause_proof.py check
```

Expected: new report is valid/deterministic/private; retained proof outputs
remain exact.

- [ ] **Step 13: Commit**

```bash
git diff --check
git add \
  scripts/run_execution_recovery_crash_worker.py \
  scripts/run_execution_recovery_proof.py \
  tests/integration/test_run_execution_recovery_proof.py \
  .github/workflows/ci.yml
git commit -m "test(recovery): prove startup convergence after process death"
```

Expected: exactly four Task 7 files.

---

### Task 8: Align Public Truth And Run The Immutable Completion Gate

**Documentation files:**

- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/README.md`
- Modify: `docs/getting-started.md`
- Modify: `docs/AGENT_INTEGRATION.md`
- Modify: `docs/architecture.md`
- Modify: `docs/decisions/framework-runtime-boundaries.md`
- Modify: `docs/decisions/run-identity-boundaries.md`
- Modify: `docs/reference/api-contract.md`
- Modify: `docs/reference/data-models.md`
- Modify: `docs/reference/state-machines.md`
- Create: `docs/operations/run-execution-recovery.md`
- Modify: `docs/superpowers/README.md`

**Documentation tests:**

- Modify: `tests/unit/test_documentation_contracts.py`
- Modify: `tests/unit/test_public_truth_documentation.py`

- [ ] **Step 1: Write documentation truth RED tests**

Required tests must assert all public authorities agree on:

```text
startup-only convergence
process-lifetime DB-scoped exclusive writer gate
clean-checkout canonical DB-parent bootstrap before the sibling lock
writer contention and unsupported-platform fail-closed behavior
tracked-task drain before writer release
private boot generation and owner fence
original source becomes immutable failed
execution vs finalization public cause mapping
POST /api/runs/{source_run_id}/retries
required Idempotency-Key
exactly zero body bytes
new run, not resume
one-hop replacement
accepted is not started/completed/successful
post-commit wake is best effort
Tool Client source/replacement semantics
automation persists and supplies its key before network
generated key is invocation-local convenience only
dedicated migration backup
existing-backup collision diagnosis and explicit operator disposition
stopped-writer upgrade and rollback
exact-profile drift fail-closed outcome
one-hop exhausted manual ordinary-run escape hatch
exact old rollback revision
fresh archived old-revision root and isolated module provenance readback
provider-free proof command
release hold
```

Add negative assertions for:

```text
automatic retry
automatic resume
exactly-once execution
heartbeat monitoring
periodic scanner
production HA
distributed lock or leader election
provider success
business impact
published v0.1.7
```

- [ ] **Step 2: Run documentation RED**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_public_truth_documentation.py
```

Expected: new truth assertions fail because docs do not yet describe the
feature.

- [ ] **Step 3: Update architecture and decision authorities**

`docs/architecture.md` and both decision records must distinguish:

1. durable pending dispatch reconciliation;
2. the local process-lifetime exclusive writer gate that makes single-writer
   startup convergence enforceable;
3. boot-generation startup convergence for application-owned running state;
4. explicit creation of a replacement run;
5. external side effects that cannot be undone or deduplicated.

Explain why LangGraph checkpoint replay is not used: incomplete graph nodes,
model calls, API calls, and tools may re-execute, while the current tool set
does not provide uniform external idempotency.

State clearly that this is Harness reliability and application authority, not
runtime self-evolution. The lock covers the supported local application
lifespan only; it is not a distributed lock, leader election, or authorization
for repository helpers/scripts to write a live DB concurrently.

- [ ] **Step 4: Update API, data, state, integration, and getting-started docs**

Document:

- exact HTTP request/response/error matrix;
- zero-body behavior including whitespace/JSON rejection;
- source vs replacement IDs;
- key retention and replay;
- Tool Client command and optional wait/result;
- private schema concepts without example private identity values;
- state transitions and startup ordering;
- no status/result schema change;
- one exact authenticated Tool Client copy-paste command against an
  already-running local service:

  ```bash
  : "${SOURCE_RUN_ID:?set the immutable failed source run ID}"
  : "${RECOVERY_KEY:?persist a high-entropy recovery key before POST}"
  : "${DECISION_RESEARCH_AGENT_API_KEY:?set the configured local API key}"

  PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
    tools/decision_research_agent_tool.py \
    retry \
    --run-id "${SOURCE_RUN_ID}" \
    --idempotency-key "${RECOVERY_KEY}"
  ```

The Tool Client reads the API key only from
`DECISION_RESEARCH_AGENT_API_KEY`; never put it in command-line arguments.
Explain that automation must persist `RECOVERY_KEY` in its own durable state
before this request. The Tool Client's generated key is only an interactive
invocation-local convenience.

The API reference also freezes one raw wire-level zero-body example without
placing the API secret in `curl` argv:

```bash
curl --config - <<EOF
url = "http://127.0.0.1:8000/api/runs/${SOURCE_RUN_ID}/retries"
request = "POST"
header = "X-API-Key: ${DECISION_RESEARCH_AGENT_API_KEY}"
header = "Idempotency-Key: ${RECOVERY_KEY}"
fail-with-body
silent
show-error
EOF
```

The `curl` command line contains only `--config -`; secret and recovery headers
arrive through stdin configuration. It intentionally has no `--data`,
`--json`, `--form`, upload, or `Content-Type`, so it sends zero body bytes.
Documentation tests must reject API-key CLI arguments and any raw example that
adds a body flag.

Use only the budgets enforced by
`tests/integration/test_run_recovery_tool_journey.py`:

```text
90 seconds to reach durable acceptance in the documented provider-free fixture
2 minutes for optional wait/result in that fixture
```

Explicitly say these are not latency, completion, availability, or production
SLA claims. Until implementation records actual observed durations, publish no
measured TTHW. Even afterward, retain actual timings as review evidence unless
the authority separately approves a clearly scoped local-fixture observation.

- [ ] **Step 5: Add the operator migration and rollback runbook**

`docs/operations/run-execution-recovery.md` must require:

**Upgrade**

```text
stop all application writers
confirm configured DB and dedicated backup path
start one application writer
pure resolution validates lock support and may create only the missing
canonical DB parent needed for the sibling coordination lock
exclusive writer gate acquires immediately afterward and before any DB,
backup, output, probe, migration, boot, or worker mutation
migration 010 backs up, applies, verifies
startup convergence activates a fresh boot before workers
preserve backup
```

**Writer gate diagnostics**

```text
run_execution_writer_already_active
  -> do not delete the empty lock file or retry in a loop
  -> identify the intended single application writer with operator tooling
  -> stop the duplicate or finish the current writer's shutdown
  -> restart exactly one writer

run_execution_writer_unavailable
  -> do not bypass with a PID file, timer, or environment flag
  -> verify supported Unix advisory locking and safe private lock-file parent
  -> on a clean checkout, verify the configured DB parent can be created and
     canonicalized without creating the DB or any other runtime directory
  -> remediate the exact platform/file-type/permission condition
  -> restart only after the production gate can acquire

shutdown does not complete
  -> do not start a successor while the old process still holds the gate
  -> inspect the blocked tracked task/finalizer without mutating DB authority
  -> if deliberate termination is required, stop the process
  -> OS releases the descriptor; the next single writer performs convergence
```

The runbook must explicitly forbid running repository helpers, migrations,
fixtures, or proof scripts against the live application DB. Their direct APIs
exist for isolated tests/proofs and do not acquire application-lifespan writer
authority.

**Existing backup collision with missing `010` marker**

```text
startup fails without overwriting either file
stop all writers
preserve diagnostic copies of current DB and existing dedicated backup
verify the backup's schema/revision/provenance and current DB marker state
choose one explicit operator-approved disposition:
  verified pre-010 backup:
    create and verify a named archival copy
    restore that verified copy to the application DB, accepting data loss
    move the original fixed-path backup to a separate named archive
    verify the fixed backup path is now absent and both archive/readback are sound
    retry so migration creates a fresh dedicated backup from the restored DB
  proven stale/wrong backup:
    move the fixed-path file to a named archive
    verify the fixed backup path is absent and current DB remains unchanged
    retry, or choose a separately approved new application DB path
never delete/overwrite/rename automatically
```

If the exact `010` marker is already present, startup performs verify-only and
the retained backup remains rollback evidence; it is not a collision to erase.

**Rollback**

```text
stop all writers
preserve a diagnostic copy of post-010 DB
obtain explicit approval for post-backup data loss
restore the complete pre-010 backup
verify exact old-revision source provenance in a fresh archive root
open and verify the restored DB only from that provider-disabled isolated root
only then accept writes
```

The runbook must include one copyable source-provenance verifier equivalent to:

```bash
set -euo pipefail
: "${RESTORED_DB:?set the absolute path to the restored pre-010 database}"

ROLLBACK_REVISION="bfd744a5611c7673d9385a45bed0131d6cb47655"
ROLLBACK_EXPORT_ROOT="$(
  mktemp -d "${TMPDIR:-/tmp}/dra-rollback-source.XXXXXX"
)"

test "$(git rev-parse "${ROLLBACK_REVISION}^{commit}")" = \
  "${ROLLBACK_REVISION}"
git cat-file -e "${ROLLBACK_REVISION}^{commit}"
git archive --format=tar "${ROLLBACK_REVISION}" \
  | tar -x -C "${ROLLBACK_EXPORT_ROOT}"

(
  cd "${ROLLBACK_EXPORT_ROOT}"
  env \
    -u OPENAI_API_KEY \
    -u DEEPSEEK_API_KEY \
    -u TAVILY_API_KEY \
    PYTHON_DOTENV_DISABLED=1 \
    DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL=false \
    DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION=false \
    python3.11 -I - \
    "${ROLLBACK_EXPORT_ROOT}" \
    "${RESTORED_DB}" \
    "${ROLLBACK_REVISION}" <<'PY'
import importlib
import json
from pathlib import Path
import sys

export_root = Path(sys.argv[1]).resolve()
restored_db = Path(sys.argv[2]).expanduser().resolve()
expected_revision = sys.argv[3]

for name in tuple(sys.modules):
    if name == "api" or name.startswith("api."):
        del sys.modules[name]
sys.path.insert(0, str(export_root))

migrations = importlib.import_module("api.run_migrations")
repository = importlib.import_module("api.run_repository")
for module in (migrations, repository):
    module_path = Path(module.__file__).resolve()
    if module_path != export_root and export_root not in module_path.parents:
        raise SystemExit("rollback_source_identity_invalid")

migrations.verify_run_schema(db_path=str(restored_db))
print(
    json.dumps(
        {
            "revision": expected_revision,
            "source_identity": "verified_export_root",
            "status": "verified",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
)
PY
)
```

The verifier must print exactly one public-neutral JSON line and no traceback.
It may not import from the current checkout, user site-packages, or an existing
Python process. Preserve the export root and diagnostic DB copy until the
rollback decision is accepted; any later cleanup is separate. Documentation
contract tests must require the exact object readback, fresh `git archive`
root, isolated working directory/import, provider-disabled environment, module
`__file__` containment check, and old-revision schema readback.

Forbid dropping only new tables, deleting the marker, editing owner rows, or
copying replacement rows into the old schema.

**Recovery eligibility diagnostics**

```text
exact profile ID/version unavailable
  -> source remains immutable failed and auditable
  -> restore the exact profile implementation and replay the same source/key
  -> or inspect the source and deliberately create an unrelated ordinary keyed
     run from caller-retained input
  -> never substitute a newer profile inside recovery lineage

replacement used as recovery source
  -> v1 is exhausted and creates no second hop
  -> inspect the source and existing replacement
  -> if another attempt is deliberate, create an unrelated ordinary keyed run
     from caller-retained input
  -> never retry automatically or hide the ordinary-run boundary
```

- [ ] **Step 6: Update README, CHANGELOG, docs index, and release truth**

README/README_CN describe the bounded capability and proof command without
overclaiming. `CHANGELOG.md` records it under the unreleased section only.
`docs/README.md` and `docs/superpowers/README.md` link the current spec, plan,
runbook, and relevant references.

Do not create a release note under `docs/releases/`, change package version,
or say the feature is in `v0.1.6`.

- [ ] **Step 7: Run documentation GREEN**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_public_truth_documentation.py
```

Expected: zero failures.

- [ ] **Step 8: Run all deterministic feature and retained gates**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/run_execution_recovery_proof.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/run_dispatch_reconciliation_proof.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/run_failure_cause_proof.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/agent_evaluation_v2_gate.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/evidence_gated_loop_gate.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/secure_local_runtime_proof.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/bounded_live_producer_proof.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/integration/test_run_recovery_tool_journey.py
```

Expected: every command exits zero with its existing exact stable output;
recovery proof emits its new exact report.

- [ ] **Step 9: Run the full non-Docker matrix**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q -m "not docker"
```

Expected: zero failures. Record actual passed/deselected count and duration.
Do not run Docker unless a retained Docker-specific change or failure proves it
necessary and the authority separately approves the environment action.

- [ ] **Step 10: Run presentation and canonical identity audits**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/final_presentation_audit.py --root .
PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/check_canonical_identity.py --root .
git diff --check
git diff --check "$IMPLEMENTATION_BASE"...HEAD
```

Expected:

```json
{"status":"ok","violations":[]}
```

for both audit commands, allowing their existing JSON spacing/order.

- [ ] **Step 11: Run public-safety and private-identity checks**

Use the actual current host value dynamically rather than embedding it in the
plan or a test fixture:

```bash
CURRENT_HOST_PREFIX="$(cd .. && pwd -P)"
if git diff --text "$IMPLEMENTATION_BASE"...HEAD -- . \
  | rg -F "$CURRENT_HOST_PREFIX"; then
  printf '%s\n' DRA_PRIVATE_HOST_PATH_FOUND
  exit 1
fi

if git diff --text "$IMPLEMENTATION_BASE"...HEAD -- . \
  | rg -n \
    'source_thread_id|<codex_delegation>|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|token='; then
  printf '%s\n' DRA_PRIVATE_COORDINATION_OR_CREDENTIAL_FOUND
  exit 1
fi

printf '%s\n' DRA_RECOVERY_PUBLIC_SAFETY_OK
```

Required negative-control literals inside scanner tests must be reviewed by
exact file/fixture context. Do not weaken the repository presentation audit or
write a raw-marker command whose scope contradicts its own approved fixtures.

- [ ] **Step 12: Verify forbidden implementation surfaces**

From `IMPLEMENTATION_BASE`, require no changes to:

```text
agent prompts
profile registry definitions
model/provider/tool implementations
Evidence admission semantics
strict-citation semantics
review decision semantics
verification decision semantics
publication semantics
result schema
frontend
Docker/Compose
dependency manifests or pins
version/tag/release files
consumer pins
```

Use:

```bash
git diff --name-only "$IMPLEMENTATION_BASE"...HEAD
git diff --stat "$IMPLEMENTATION_BASE"...HEAD
```

and manually compare each path to the plan file map. A new path requires
authority review before staging; do not silently expand scope.

- [ ] **Step 13: Commit public truth**

```bash
git diff --check
git add \
  README.md \
  README_CN.md \
  CHANGELOG.md \
  docs/README.md \
  docs/getting-started.md \
  docs/AGENT_INTEGRATION.md \
  docs/architecture.md \
  docs/decisions/framework-runtime-boundaries.md \
  docs/decisions/run-identity-boundaries.md \
  docs/reference/api-contract.md \
  docs/reference/data-models.md \
  docs/reference/state-machines.md \
  docs/operations/run-execution-recovery.md \
  docs/superpowers/README.md \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_public_truth_documentation.py
git diff --cached --check
git diff --cached
git commit -m "docs(recovery): define startup convergence operations"
```

Expected: Task 8 contains only public truth and its tests.

- [ ] **Step 14: Re-run the immutable completion gate after the final commit**

Repeat Steps 8-12 against the final HEAD. Then:

```bash
test -z "$(git status --porcelain)"
git log --oneline "$IMPLEMENTATION_BASE"..HEAD
git diff --check "$IMPLEMENTATION_BASE"...HEAD
```

Do not claim completion from pre-commit results.

---

## Retained Regression Matrix

The final authority review must explicitly retain:

| Capability | Required evidence |
| --- | --- |
| Process-lifetime single writer | writer-lock unit/subprocess tests + proof `exclusive_writer_fail_closed` |
| Graceful shutdown authority order | task-tracker drain tests + lifespan integration ordering |
| Ordinary unkeyed run creation | existing API/repository tests |
| Keyed run creation and lost-response replay | creation proof + tests |
| Three-attempt pre-start dispatch reconciliation | dispatch proof + tests |
| Exact failure-cause projection and privacy | failure-cause proof + tests |
| Generic result | result API/integration tests |
| Strict-citation result and finalization fence | strict profile tests |
| Talent artifact/review workflow | review and durable kill9 tests |
| Evidence verification | compatibility/repository tests |
| Publication | publication repository/service tests |
| Downstream consumer contract | existing contract proof/test |
| Local Tool Client recovery journey | real loopback service acceptance and wait/result tests under documented budgets |
| Context Reliability | existing regression command/tests |
| Evaluation v1 | `agent_evaluation_gate.py check` |
| Evaluation Sensitivity v2 | `agent_evaluation_v2_gate.py check` |
| Evidence-Gated Loop Kernel | `evidence_gated_loop_gate.py check` |
| Secure local runtime | secure runtime proof/tests |
| Bounded live producer contract | existing proof/tests |
| Public-neutral presentation | presentation audit |
| Canonical product identity | canonical identity audit |
| Full backend compatibility | full non-Docker pytest |
| Hosted compatibility | exact reviewed-head GitHub CI and CodeQL after publication authorization |

## Security And Privacy Completion Checks

- Raw recovery keys exist only at the HTTP/client boundary and caller-local CLI
  output; the DB stores only a namespaced hash.
- Boot and owner identities are application-private capabilities and are
  cleared from closed/interrupted rows.
- The writer lock file is empty, private, non-inheritable, no-follow, and
  authoritative only while the OS descriptor is held; its path and descriptor
  never cross public surfaces.
- Pure DB-path resolution is side-effect free. A clean first start may create
  and validate only the canonical DB parent before the sibling lock; that
  parent and the empty lock file carry no run, boot, owner, query, path, or
  credential payload and grant no authority by existence.
- Public status/result/telemetry/proof/log surfaces contain no boot, owner,
  key/hash, DB path, PID, worker ID, query, scope, exception, or credential.
- Middleware denial happens before body observation or repository access.
- The zero-body guard reads at most until the first observed byte and performs
  no parsing.
- Startup convergence has no replacement, Agent, model, graph, tool, provider,
  review, verification, publication, or release authority.
- Recovery creates one new run only after explicit authorized caller action.
- Exact profile drift and one-hop exhaustion create no replacement or hidden
  ordinary run.
- A replacement may repeat external side effects; documentation states this
  rather than claiming exactly-once behavior.

## Rollback Verification

Completion requires both directions in isolated fixtures:

```text
pre-010 DB
  -> current revision
  -> dedicated backup
  -> migration/backfill/verify
```

and:

```text
post-010 diagnostic copy preserved
  -> complete pre-010 backup restored
  -> exact bfd744a5611c7673d9385a45bed0131d6cb47655 exported locally
  -> separate provider-disabled old-revision process
  -> restored DB opens/verifies
```

The proof does not authorize live data rollback. A real rollback requires
stopped writers and explicit operator approval because all post-backup data is
discarded.

## Final Non-Claims

The completed feature may claim:

- fail-closed process-lifetime exclusion for the supported single-node
  application writer;
- startup-only convergence of exact application-owned running state in a
  single-node SQLite deployment;
- boot/owner fencing of stale process generations;
- exact execution/finalization interruption classification;
- explicit authenticated one-hop replacement with durable idempotency;
- provider-free real-process and rollback contract proof.

It may not claim:

- exact resume;
- automatic retry or self-healing Agent behavior;
- exactly-once execution, model calls, tool calls, billing, or side effects;
- live heartbeat monitoring;
- active multi-instance support or production HA;
- production reliability, latency, adoption, or business impact;
- live-provider success;
- automatic release/rollback;
- inclusion in `v0.1.6` or publication as `v0.1.7`.

## Definition Of Done

The phase is complete only when:

1. the exact approved plan is landed and its implementation base is locked;
2. Tasks 1-8 each have a coherent semantic commit;
3. pure DB-path resolution plus a validated clean-checkout parent bootstrap
   makes the sibling writer gate reachable without opening the DB;
4. one DB-scoped OS writer gate is acquired before application DB, backup,
   output/probe, migration, boot, worker, or request mutation and held until
   tracked tasks/callbacks settle and private state clears;
5. overlap and unsupported locking may leave only the validated parent and
   empty coordination lock, never application data; real process death
   releases the kernel-held gate;
6. migration `010` is backup-protected, exact, repeat-safe, and fail-closed;
7. every post-010 running run owns one exact active current-boot owner;
8. fresh startup converges previous-boot owners before workers and requests;
9. stale generations cannot start, change phase, persist business rows, or
   finalize;
10. every running terminal path uses and closes the exact owner;
11. explicit recovery enforces auth, zero body, key, eligibility, one hop, and
   exact replay;
12. Tool Client preserves caller authority and never retries automatically;
13. real execution/finalization `SIGKILL`, stale fencing, replacement replay,
    migration restore, and exact old-revision rollback are proven
    provider-free;
14. all retained gates, full non-Docker tests, presentation, identity,
    private-boundary, and diff checks pass on final HEAD;
15. the worktree is clean;
16. the planning authority completes actual-diff review before any publication;
17. publication, merge, release, deploy, and cleanup remain separately
    authorized actions.

<!-- AUTONOMOUS DECISION LOG -->
## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|---|---|---|---|---|---|
| 1 | CEO | Keep crash-safe startup convergence as the next bounded reliability slice | Auto-decided from user-approved premise | Highest completeness with evidence | Live code has durable pre-start reconciliation but no owner generation for post-start process death; this closes a real Harness gap and remains provider-free and testable | No-change/manual-only |
| 2 | CEO | Keep explicit one-hop replacement after convergence | Auto-decided | Complete the operator journey without runtime authority expansion | Convergence alone only produces a trustworthy failed source; an authenticated caller still needs one replay-safe way to create a fresh run | Failure-only convergence with no recovery action |
| 3 | CEO | Reject heartbeat, periodic scanning, transparent checkpoint resume, and automatic retry | Auto-decided | Minimize new runtime authority and unverifiable side effects | The application cannot prove exactly-once model/tool/provider effects, and the approved goal is evidence-preserving recovery rather than self-healing automation | Runtime self-repair platform |
| 4 | CEO | Keep migration activation, start ownership, phase fencing, and every running terminal writer in one Task 4 commit | Auto-decided | Preserve atomic authority coherence | A partial activation would create ownerless running states or terminal bypasses; file count is secondary to one coherent lifecycle boundary | Split activation across independently usable commits |
| 5 | CEO | Keep release, merge, deploy, and rollback execution outside this implementation authority | Auto-decided | Separate implementation proof from publication authority | Provider-free proof and CI can establish a reviewable contract but cannot justify automatic publication or operational rollback | Automatic release or rollback |
| 6 | Design | Skip Design review | Auto-decided | Review only applicable surfaces | The approved slice changes no frontend, visual flow, or UI interaction | UI review ceremony |
| 7 | CEO | Require a process-lifetime exclusive-writer gate before migration and boot activation | Auto-decided safety correction | Fail closed before destructive authority transfer | Without a live-process exclusion, an overlapping second process can terminalize work still owned by the first; a local OS-released lock closes this single-node gap without heartbeat or leader election | Documentation-only single-writer assumption |
| 8 | CEO | Fail closed on recovery profile drift and document the exact operator outcome | Auto-decided | Preserve immutable execution semantics | Replaying an old source under a silently upgraded profile would violate the exact source snapshot; the source remains auditable failed state when its exact profile is unavailable | Implicit profile upgrade |
| 9 | CEO | Keep one-hop exhaustion and define the manual ordinary-run escape hatch | Auto-decided | Preserve bounded lineage while leaving an explicit operator path | A replacement cannot become a second recovery source; after inspection, an operator may deliberately create an unrelated ordinary keyed run with caller-retained input | Automatic second hop or hidden fallback |
| 10 | Engineering | Acquire a DB-scoped OS writer capability before writable startup and release it only after shielded tracked-task drain | Auto-decided P0 correction | Authority must outlive every writer it protects | Boot fencing alone cannot distinguish a dead predecessor from an overlapping live process, and early shutdown release would recreate that overlap | Assumed single writer plus ordinary `finally` release |
| 11 | Engineering | Freeze a test-only through-009 constructor independent of public `init_run_schema` | Auto-decided P1 correction | A retained migration test must preserve its historical source state | Once Task 4 activates `010` in the public initializer, using it to build the pre-feature fixture would false-green the backfill proof | Delete `010` after initialization |
| 12 | Engineering | Fetch full backend history and preflight the exact rollback object before proof | Auto-decided P1 correction | Hosted proof must possess its immutable source identity | Default shallow checkout does not guarantee that the fixed pre-feature revision remains available to `git archive` on future heads | Local-only archive success |
| 13 | Engineering | Expand the Task 4 caller map to strict-citation, Context Reliability, and every direct/indirect running boundary | Auto-decided P1 correction | No compatibility bypass may retain ownerless running state | Live static inventory found omitted private dispatch entries and running finalizers; focused retained tests now name them | Narrow allowlist with unreviewed leftovers |
| 14 | Engineering | Put source/replacement/segment relations in the shared strict model and strengthen SIGKILL/exported-revision provenance | Auto-decided P1 correction | Proof and response relationships must be impossible to spoof structurally | Strict scalar fields alone permit incoherent identities, while marker presence or `PYTHONPATH` order alone can false-green process/rollback proof | Client-only validation and path-order inference |
| 15 | Engineering | Keep Tasks 1-3 dormant, Task 4 atomic, and Tasks 5-8 serial | Auto-decided | Preserve one coherent authority transition | Schema, lifespan, task tracker, dispatch, owner, API, and proof assumptions share mutable boundaries and are unsafe to parallelize | Multi-lane implementation |
| 16 | DevEx | Split pure DB-path resolution from one controlled parent bootstrap before the sibling writer lock | Auto-decided P1 first-success correction | A clean checkout must reach the safety gate without reintroducing hidden pre-lock application mutation | The default ignored `data/` directory is absent on a clean checkout; pure resolution plus an explicit validated parent bootstrap permits the fixed lock while tests prove DB, backup, output, probes, boot, and workers remain absent on contention or unsupported failure | Implicit mkdir in canonical resolver, or assuming the parent already exists |
| 17 | DevEx | Freeze every current claim, private dispatch, and tracked-task admission caller inside Task 4 | Auto-decided P0 integration correction | Atomic authority changes require complete current caller coverage | Agent Evaluation v2 replay, durable-review lifecycle, bounded-producer proof, and basic tracker tests use the exact claim/private-dispatch/admission surfaces Task 4 changes; deferring discovery to the final suite would make the atomic commit unverifiable | Rely only on a future inventory stop |
| 18 | DevEx | Give stale-generation proof failures one dedicated safe diagnostic code | Auto-decided P1 debugging correction | Independent proof stages need one-hop bounded diagnosis | The report already treats stale fencing as an independent case, so its injected failures must not be misclassified as execution, finalization, or retained-contract errors | Reuse a neighboring stage code |
| 19 | DevEx | Put exact old-revision archive and import provenance into the operator rollback runbook | Auto-decided P1 safety correction | Destructive rollback requires executable source identity, not narrative intent | A proof-only provenance check does not prevent an operator from validating restored data with the current checkout or user-site modules; the copyable isolated verifier closes that gap before writes resume | State only “run the exact revision” |
| 20 | DevEx | Emit privacy-safe review-only timing diagnostics from the real local Tool Client journeys | Auto-decided P2 evidence improvement | A budget pass and an observed duration answer different questions | Separate client-observed A0/A1 and W0/W1 readback makes first-success evidence reviewable while keeping it local-fixture-only and outside public performance claims | Infer actual TTHW from the 90/120-second ceilings |
| 21 | Authority self-review | Keep this slice in the program/Harness layer and preserve online/offline authority separation | Auto-decided from approved architecture | Deterministic safety belongs in code, constraints, verification, and rollback boundaries | Online execution may record and fence evidence, but one failure cannot become a permanent rule; diagnosis, candidate selection, retained regression, acceptance, publication, and rollback remain explicit offline or operator-owned work | Runtime self-modification, automatic promotion, or a generic evolution platform |
| 22 | DevEx | Bind timing diagnostics only to public results observed by the independent client | Auto-decided P2 measurement correction | Measurement labels must match their actual observation boundary | The acceptance-only journey can report client-validated 202 time, while the wait/result journey can safely report only client-validated completion; a server commit hook cannot prove client observation | Label a server-side durable-commit timestamp as client-observed acceptance |

## GSTACK REVIEW REPORT

### Review Summary

| Review | Result | Score | Findings and disposition |
|---|---|---:|---|
| CEO | PASS after amendments | 9/10 plan completeness | The approved premise remains a bounded crash-recovery Harness slice. Writer overlap, exact profile drift, and the exhausted one-hop operator journey are now closed in the plan. |
| Engineering | PASS after amendments | 9/10 plan completeness | The plan now requires a process-lifetime DB-scoped writer gate, a real through-009 migration fixture, exact rollback-object availability, complete running-state caller coverage, strict public relations, and serial authority-changing tasks. |
| Design | SKIPPED | N/A | No visual, frontend, or interaction-design surface changes. |
| DevEx | PASS after amendments | 45/45 plan completeness | Clean-checkout parent bootstrap, complete caller inventory, stable stale-generation diagnostics, executable old-revision provenance, and case-specific client-observed local-fixture timing readback are specified. Actual timing remains implementation evidence, not a plan claim. |

CEO and Engineering review used the planning authority after bounded
independent-review attempts did not return usable results. DevEx received an
independent first-success review and a separate authority review; all
actionable findings were reconciled without changing the approved product
direction.

### CODEX Summary

- The scope is complete enough to implement without inventing product or
  architecture decisions in the execution window.
- Tasks 1-3 remain dormant contract and migration construction. Task 4 is one
  indivisible authority transition. Tasks 5-8 remain serial integration,
  proof, documentation, and closeout work.
- The plan retains explicit RED/GREEN commands, fixed provider-free proof
  profiles, stable safe error codes, immutable revision provenance, retained
  compatibility gates, and one exact implementation allowlist.
- Implementation, hosted exact-head CI, measured TTHW, actual-diff review,
  publication, merge, release, deploy, and operational rollback remain future
  evidence or approval gates.

### CROSS-MODEL Consensus

The reviews converged on four boundaries:

1. single-writer exclusion and shutdown drain must protect every mutation
   authority, not merely startup migration;
2. immutable identities and rollback provenance must be executable and
   fail-closed;
3. every current claim, private dispatch, tracked-task admission, and running
   finalizer caller must be migrated together;
4. online execution records and fences evidence, while diagnosis, candidate
   choice, retained regression, acceptance, release, and rollback remain
   offline or operator-owned.

No review supported heartbeat scanning, exact resume, automatic retry, runtime
self-modification, dynamic verifier loading, generic EvalOps, hosted
observability, or automatic release.

### VERDICT

The implementation plan is approved by the planning authority and the user. It
is a bounded program/Harness reliability slice with a provider-free proof path
and clear rollback boundary. This approval authorizes only the task sequence
and verification gates in this plan; publication, merge, release, deploy, and
operational rollback remain separately authorized actions.

NO UNRESOLVED DECISIONS
