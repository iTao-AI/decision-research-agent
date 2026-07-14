# Durable Run Dispatch Reconciliation v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task in the existing isolated worktree.

**Goal:** Atomically persist and reconcile pre-execution run dispatch so a committed `pending` ResearchRun can recover from handler cancellation, scheduler failure, or process restart without allowing stale tasks to enter DeepAgents.

**Architecture:** Add one application-owned `run_dispatches_v1` row to the existing run-create transaction, then claim it through a single-node SQLite lease worker. The scheduled coroutine must win an exact `(run_id, lease_owner, attempt_count)` start fence that atomically moves dispatch, run, and initial segment to started/running before any model or tool call; existing execution, Evidence, review, result, and terminal finalization remain in place after that fence.

**Tech Stack:** Python 3.11, FastAPI lifespan, asyncio, SQLite WAL with `BEGIN IMMEDIATE`, Pydantic 2.13.4 strict models, existing DeepAgents 0.6.11 / LangChain 1.3.10 / LangGraph 1.2.6 runtime, pytest, deterministic JSON/Markdown proof, GitHub Actions.

## Global Constraints

- Implement only `docs/superpowers/specs/2026-07-14-durable-run-dispatch-reconciliation-design.md`.
- Use the existing isolated worktree. Rebase onto the latest `origin/main` before implementation if the spec commit has not landed; stop if the runtime contract changed materially.
- Use TDD for every behavior change: focused RED, minimal implementation, focused GREEN, then broader verification.
- Do not add dependencies, endpoints, request/response fields, Tool Client commands, frontend behavior, runtime Skills, Async Subagents, or new Agent middleware.
- Migration identity is exactly `008_run_dispatch_reconciliation`; checksum is `run-dispatch-reconciliation-v1`; table is `run_dispatches_v1`.
- Dispatch statuses are exactly `pending`, `leased`, `started`, and `failed`; maximum scheduling attempts are `3`.
- Fence every claim/start/retry/failure write with `(run_id, lease_owner, attempt_count)`, never owner alone.
- Do not backfill or schedule pre-`008` runs. Preserve old keyed replay as identity-only.
- Keep `POST /api/runs` response shape and HTTP 200. `status="started"` remains acknowledgement, not proof that a model call began.
- Recovery ends once dispatch/run become `started/running`; do not add arbitrary running recovery or exactly-once claims.
- Keep `VERSION` at `0.1.2`. Do not push, create a PR, merge, tag, release, deploy, install dependencies, or clean the worktree.

## File And Responsibility Map

| File | Responsibility |
|---|---|
| `api/run_dispatch_models.py` | Strict constants, claim model, bounded conflict type |
| `api/run_repository.py` | Atomic run + segment + optional idempotency + dispatch creation |
| `api/run_dispatch_repository.py` | Claim, exact start fence, retry/exhaustion, attempt inspection |
| `api/run_migrations.py` | Migration `008`, exact verification, backup/restore path |
| `api/run_dispatch_worker.py` | Poll/wake worker and bounded scheduler errors |
| `api/server.py` | Lifespan, scheduler adapter, pre-start wrapper, timeout fence, route fast path |
| `scripts/run_dispatch_reconciliation_proof.py` | Deterministic production-path proof and baseline checker |
| `tests/unit/test_run_dispatch_*.py` | Contract, repository, and worker behavior |
| `tests/integration/test_run_dispatch_*.py` | API/lifespan/crash window and proof behavior |
| `.github/workflows/ci.yml` | Required dispatch proof before full pytest |
| `docs/evidence/run-dispatch-reconciliation-v1.{json,md}` | Committed proof baselines |
| architecture/reference/README files | Public behavior, authority, migration, non-claims |

## What Already Exists

- `api.run_repository` already owns canonical run identity, the initial segment,
  optional idempotency binding, SQLite setup, state-version fencing, and terminal
  finalization. Extend that transaction; do not create a parallel run store.
- `api.run_migrations.migrate_with_backup` already owns backup, apply, verify,
  and restore. Extend its ordered migration set and use a new
  `.pre-run-dispatch.bak` path for `008`; do not overwrite the earlier
  idempotency backup.
- `api.review_worker.ReviewWorker` provides the local operational pattern for a
  lease worker, but its repository, flags, checkpoint runtime, and business
  semantics remain separate from core dispatch.
- `api.task_tracker.create_tracked_task` already owns coroutine timeout and done
  callbacks. Reuse it with an attempt-qualified task ID; do not add a second
  task registry.
- `_run_v2_with_persistence`, `run_deep_agent`, Evidence persistence, review,
  result generation, and terminal finalization remain the running-state path.
  This feature inserts one fenced start in front of that path.
- DeepAgents, LangChain, LangGraph, and existing middleware remain the Agent
  runtime after the start fence. Their checkpoint/middleware hooks cannot join
  the pre-invocation SQLite transaction, so they are reused but not made dispatch
  authority.

## Data Flow And State Machine

```text
POST /api/runs
    |
    v
BEGIN IMMEDIATE
  run + initial segment + optional key binding + dispatch(pending, attempt=0)
    |
    +-- rollback all on any write or schema-integrity failure
    |
    v commit
targeted worker attempt + wake event ----------------------+
    |                                                       |
    v                                                       | polling fallback
claim pending/expired -> leased(owner, attempt+1) <---------+
    |
    v
create attempt-qualified tracked task
    |
    v
exact start fence: (run_id, owner, attempt)
    +-- stale/corrupt/terminal -> stop before Agent
    |
    +-- success -> dispatch started + run/segment running
                       |
                       v
              existing Agent/Evidence/review/result path
```

```text
pending --claim--> leased --fenced start--> started
   ^                 |
   |                 +-- scheduling/pre-start failure, attempt 1-2 --+
   |                                                                  |
   +------------------------------------------------------------------+

leased --scheduling/pre-start failure, attempt 3--> failed
leased --lease expiry--> leased with a higher attempt

Every mutating arrow out of leased is fenced by
(run_id, lease_owner, attempt_count).
```

## NOT In Scope

- Recovery after `started/running`; this needs a separate execution-resume and
  side-effect model.
- Exactly-once Agent, provider, or tool side effects; the fence proves one start
  winner from pending, not global exactly-once execution.
- Multi-instance high availability, an external broker, or distributed leases;
  v1 is explicitly single-node SQLite.
- Backfill or automatic scheduling of pre-`008` pending runs; their intent and
  provider-cost authorization are unknown.
- New middleware, Async Subagents, memory, public anonymous execution, generic
  outcome changes, usage persistence, consumer adapters, dependency updates, or
  release preparation.
- A runtime-configurable retry budget, worker ID, lease duration, database path,
  or provider URL from API callers.

## Failure Mode And Test Matrix

| Path | Production failure | Required handling | Required test | Caller observation |
|---|---|---|---|---|
| Create transaction | dispatch insert/schema verification fails | Roll back run, segment, key binding, and dispatch | repository fault injection | existing pre-commit error |
| Route after commit | handler cancelled before scheduling | durable pending row remains | integration cancellation + fresh worker | 200 may be lost; replay/poll recovers identity |
| Claim | two workers select one row | `BEGIN IMMEDIATE` plus exact update admits one claim | independent-connection race | no public transient error |
| Schedule | task construction/submission raises | bounded code, exact retry release; third attempt fails all three states | worker unit + integration exhaustion | create remains 200; polling later shows failed |
| Lease | first task is delayed past expiry | later attempt reclaims with incremented attempt | repository reclaim test | no duplicate Agent entry |
| Start | stale task wakes after reclaim | exact attempt fence returns false before fake Agent counter | production-fence integration test | silent stale no-op |
| Tracking | stale attempt completes after a newer task is registered | attempt-qualified tracker keys prevent cross-attempt removal | task integration regression | newer timeout tracking remains active |
| Timeout | old attempt timeout fires after newer start | exact attempt inspection/release is stale no-op | attempt-1/attempt-2 timeout test | newer running state unchanged |
| Migration | `008` verify/apply fails | restore new dispatch backup; never overwrite old backup | migration injection tests | startup fails closed |
| Worker loop | transient SQLite/OSError | bounded log, loop remains alive, poll retries | worker loop unit test | accepted run remains pollable |
| Running Agent | process dies after fenced start | unchanged current behavior; no v1 recovery claim | proof boundary assertion | run may remain running |

## Test Coverage Diagram

```text
CODE PATHS                                             CALLER / OPERATOR FLOWS
[+] run_dispatch_models.py                            [+] POST /api/runs
  +-- [★★★ PLANNED] strict fields/errors                +-- [★★★ PLANNED] unkeyed independent create
  +-- [★★★ PLANNED] canonical immutable scope           +-- [★★★ PLANNED] keyed replay/conflict
[+] run_repository.py                                   +-- [★★★ PLANNED] pre-commit failure
  +-- [★★★ PLANNED] four-write atomic create             +-- [★★★ PLANNED] post-commit scheduler failure -> 200
  +-- [★★★ PLANNED] both rollback injection points     [+] Service lifecycle
[+] run_dispatch_repository.py                          +-- [★★★ PLANNED] startup reconciliation
  +-- [★★★ PLANNED] oldest/targeted/expired claim        +-- [★★★ PLANNED] cancellation/restart recovery
  +-- [★★★ PLANNED] exact fenced start                   +-- [★★★ PLANNED] clean stop + immediate failure
  +-- [★★★ PLANNED] stale/retry/third-failure          [+] Agent boundary
[+] run_dispatch_worker.py                              +-- [★★★ PLANNED] one winner after production fence
  +-- [★★★ PLANNED] schedule error and loop survival     +-- [★★★ PLANNED] stale task blocked before fake Agent
  +-- [★★★ PLANNED] wake/poll/stop                       +-- [★★★ PLANNED] existing result/Evidence/review
[+] server.py                                         [+] Operator evidence
  +-- [★★★ PLANNED] lifespan + targeted fast path        +-- [★★★ PLANNED] deterministic JSON/Markdown/check
  +-- [★★★ PLANNED] attempt-qualified task tracking      +-- [★★★ PLANNED] migration backup/restore/no-backfill
  +-- [★★★ PLANNED] stale timeout no-op                  +-- [★★★ PLANNED] exact non-claims

Legend: ★★★ = behavior + edge + error paths specified in Tasks 1-6.
No LLM quality eval is added because prompts, tools, middleware, and model
behavior do not change; the existing Agent evaluation gate remains required.
```

## Execution Ordering

Sequential implementation, no parallelization opportunity. Tasks 1-4 share
`api/` state contracts and must land in dependency order; Task 5 consumes the
production path; Task 6 documents only verified behavior. Splitting these tasks
across worktrees would add merge risk without an independent lane.

Performance posture: one indexed claim query is allowed per idle poll and one
primary-key-targeted claim for the route fast path. SQLite work stays inside
`asyncio.to_thread`; the scheduler callback performs no provider or network
work. Do not add throughput/latency claims or a benchmark requirement to this
correctness PR.

---

### Task 1: Define Dispatch Contracts And Atomic Creation

**Files:**
- Create: `api/run_dispatch_models.py`
- Create: `tests/unit/test_run_dispatch_models.py`
- Modify: `api/run_repository.py`
- Modify: `tests/unit/test_run_repository.py`

**Interfaces:**
- Consumes: existing `_connect`, `_now`, `_insert_run_identity`, `create_run`, `create_or_replay_run`.
- Produces: migration/status constants, `RunDispatchClaim`, `RunDispatchConflict`, and one pending dispatch for every new post-`008` run.

- [ ] **Step 1: Write strict model RED tests**

Use this representative contract and add separate rejection tests for extra fields, coerced attempts, naive datetimes, invalid worker IDs, zero attempts, non-object/invalid/non-canonical `scope_json`, and mutation. Also prove mutating the dict returned by `claim.scope` does not change `claim.scope_json` or a later `claim.scope` value:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from api.run_dispatch_models import (
    MAX_RUN_DISPATCH_ATTEMPTS,
    RUN_DISPATCH_MIGRATION_CHECKSUM,
    RUN_DISPATCH_MIGRATION_VERSION,
    RUN_DISPATCH_STATUSES,
    RunDispatchClaim,
)


def valid_claim():
    return {
        "run_id": "run_0001",
        "thread_id": "thread-1",
        "segment_id": "run_0001_seg_000",
        "query": "research",
        "profile_id": "generic",
        "profile_version": "1",
        "scope_json": "{}",
        "lease_owner": "dispatch_worker_00000000000000000000000000000001",
        "attempt_count": 1,
        "lease_expires_at": datetime(2026, 7, 14, tzinfo=timezone.utc),
    }


def test_dispatch_constants():
    assert RUN_DISPATCH_MIGRATION_VERSION == "008_run_dispatch_reconciliation"
    assert RUN_DISPATCH_MIGRATION_CHECKSUM == "run-dispatch-reconciliation-v1"
    assert RUN_DISPATCH_STATUSES == frozenset({"pending", "leased", "started", "failed"})
    assert MAX_RUN_DISPATCH_ATTEMPTS == 3


def test_claim_is_strict_frozen_and_forbids_extra():
    claim = RunDispatchClaim.model_validate(valid_claim(), strict=True)
    with pytest.raises(ValidationError):
        RunDispatchClaim.model_validate({**valid_claim(), "attempt_count": "1"}, strict=True)
    with pytest.raises(ValidationError):
        RunDispatchClaim.model_validate({**valid_claim(), "extra": True}, strict=True)
    with pytest.raises(ValidationError):
        claim.attempt_count = 2
```

- [ ] **Step 2: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest tests/unit/test_run_dispatch_models.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'api.run_dispatch_models'`.

- [ ] **Step 3: Implement the strict model**

Create exact constants and this shape:

```python
class RunDispatchClaim(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    run_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=256)
    segment_id: str = Field(min_length=1, max_length=160)
    query: str
    profile_id: str = Field(min_length=1, max_length=128)
    profile_version: str = Field(min_length=1, max_length=64)
    scope_json: str = Field(min_length=2)
    lease_owner: str = Field(pattern=r"^dispatch_worker_[0-9a-f]{32}$")
    attempt_count: int = Field(ge=1)
    lease_expires_at: datetime

    @field_validator("lease_expires_at")
    @classmethod
    def require_timezone(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("run_dispatch_lease_invalid")
        return value

    @field_validator("scope_json")
    @classmethod
    def require_canonical_scope(cls, value):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("run_dispatch_scope_invalid") from exc
        if not isinstance(payload, dict):
            raise ValueError("run_dispatch_scope_invalid")
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        if canonical != value:
            raise ValueError("run_dispatch_scope_invalid")
        return value

    @property
    def scope(self) -> dict[str, Any]:
        return json.loads(self.scope_json)
```

Add `RunDispatchConflict(code)` and exact constants. Update new run insertion to
store scope with the same compact canonical JSON serialization. Keeping the
immutable canonical string in the claim avoids a mutable nested dict inside a
frozen Pydantic model; `claim.scope` returns a fresh parsed dict for the Agent.
Do not import runtime/tracing frameworks.

- [ ] **Step 4: Write atomic-creation RED tests**

Assert unkeyed create inserts one pending dispatch with attempt 0, keyed replay keeps exactly one dispatch, same-thread unkeyed calls each get their own dispatch, and a wrong `008` checksum fails before identity insertion. Use separate `BEFORE INSERT` abort triggers on `run_dispatches_v1` and `run_create_idempotency_v1`: the first proves no partial run/segment survives dispatch failure; the second proves a later key-binding failure rolls back the already inserted run, segment, and dispatch.

```python
def test_keyed_replay_keeps_one_dispatch(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    first = create_or_replay_run(
        idempotency_key="run-key-dispatch-0001",
        thread_id=None,
        query="research",
        db_path=db_path,
    )
    second = create_or_replay_run(
        idempotency_key="run-key-dispatch-0001",
        thread_id=None,
        query="research",
        db_path=db_path,
    )
    assert second.idempotent_replay is True
    connection = sqlite3.connect(db_path)
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM run_dispatches_v1 WHERE run_id = ?",
            (first.run_id,),
        ).fetchone()[0]
    finally:
        connection.close()
    assert count == 1
```

- [ ] **Step 5: Implement schema and transaction-local insert**

Add `run_dispatches_v1` after `research_runs_v2` with status, attempt, and four state-dependent CHECK constraints. Create exactly:

```sql
CREATE INDEX IF NOT EXISTS idx_run_dispatches_status_lease_created
ON run_dispatches_v1(status, lease_expires_at, created_at)
```

Insert in `_insert_run_identity` using the same connection and timestamp:

```python
connection.execute(
    """
    INSERT INTO run_dispatches_v1 (
        run_id, status, lease_owner, lease_expires_at, attempt_count,
        last_error_code, created_at, updated_at, started_at
    ) VALUES (?, 'pending', NULL, NULL, 0, NULL, ?, ?, NULL)
    """,
    (run_id, now, now),
)
```

Insert the `008` marker. Before creating any new identity, require that marker's
checksum on the same transaction connection; lifespan still performs the full
schema verifier before serving. Never populate dispatch rows by selecting
existing runs.

- [ ] **Step 6: Run GREEN and commit**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_run_dispatch_models.py tests/unit/test_run_repository.py -q
git diff --check
git add api/run_dispatch_models.py api/run_repository.py \
  tests/unit/test_run_dispatch_models.py tests/unit/test_run_repository.py
git commit -m "feat(api): persist run dispatch intent"
```

Expected: focused tests pass and the commit contains only Task 1 files.

---

### Task 2: Verify Migration And Implement The Dispatch State Machine

**Files:**
- Create: `api/run_dispatch_repository.py`
- Create: `tests/unit/test_run_dispatch_repository.py`
- Modify: `api/run_migrations.py`
- Modify: `tests/unit/test_run_migrations.py`

**Interfaces:**
- Consumes: Task 1 constants/model, `_connect`, `_now`, `init_run_schema`.
- Produces: `claim_run_dispatch`, `start_run_dispatch`, `release_run_dispatch_for_retry`, `dispatch_attempt_is_started`, `get_run_dispatch`, verified `008` migration.

- [ ] **Step 1: Write migration RED tests**

Cover marker/checksum, exact columns, PK/FK cascade, index order/uniqueness/partial flag, status/attempt/state checks, repeated application, restore on injected failure, existing-backup protection, and no backfill.

```python
def test_008_does_not_backfill_old_pending_run(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    _seed_pre_008_pending_run(db_path, run_id="run_old")
    init_run_schema(db_path)
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM run_dispatches_v1").fetchone()[0] == 0
    finally:
        connection.close()
```

Define `_seed_pre_008_pending_run` in this test module with direct SQLite DDL
for the pre-`008` `schema_migrations`, `research_runs_v2`, and `run_segments`
tables, then insert one pending run plus its initial segment. Do not call the
new schema initializer inside the helper; the test's explicit
`init_run_schema` call is the upgrade under test.

Create malformed schemas one property at a time and require stable missing-constraint labels for dispatch PK, FK, status check, attempt check, state check, and scan index.

- [ ] **Step 2: Run migration RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest tests/unit/test_run_migrations.py -q
```

Expected: new `008` verification assertions fail.

- [ ] **Step 3: Extend verifier and upgrade path**

Add table/index/columns/constants to required sets. Inspect `PRAGMA table_info`, `foreign_key_list`, `index_list`, `index_info`, and normalized `sqlite_master.sql`. Accept only the exact non-unique, non-partial ordered scan index. Extend `_migration_markers` and `migrate_with_backup` so missing `008` gets a new caller-supplied backup, apply/verify, and restore on failure without overwriting an existing backup. The API lifespan must pass `<application-db>.pre-run-dispatch.bak`; it must not reuse `<application-db>.pre-run-idempotency.bak`.

- [ ] **Step 4: Write state-machine RED tests**

Cover oldest-first and targeted claims, expiry/reclaim, exact start, stale owner, stale attempt with the same owner, concurrent independent connections, retry release, third-attempt exhaustion, raw-error exclusion, invalid `scope_json`, missing/corrupt initial segment, terminal run, and state-version mismatch.

```python
def test_same_worker_old_attempt_cannot_start_after_reclaim(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    created = create_run(thread_id="thread-1", query="research", db_path=db_path)
    first = claim_run_dispatch(
        db_path=db_path,
        worker_id="dispatch_worker_00000000000000000000000000000001",
        lease_seconds=30,
        run_id=created["run_id"],
        now=datetime(2026, 7, 14, tzinfo=timezone.utc),
    )
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute(
                "UPDATE run_dispatches_v1 SET lease_expires_at = ? WHERE run_id = ?",
                ("2026-07-13T23:59:59+00:00", created["run_id"]),
            )
    finally:
        connection.close()
    second = claim_run_dispatch(
        db_path=db_path,
        worker_id=first.lease_owner,
        lease_seconds=30,
        run_id=created["run_id"],
        now=datetime(2026, 7, 14, 0, 1, tzinfo=timezone.utc),
    )
    assert second.attempt_count == first.attempt_count + 1
    assert start_run_dispatch(db_path=db_path, claim=first) is False
    assert start_run_dispatch(db_path=db_path, claim=second) is True
```

- [ ] **Step 5: Run repository RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_run_dispatch_repository.py tests/unit/test_run_migrations.py -q
```

Expected: collection fails for missing repository functions after migration assertions reach GREEN.

- [ ] **Step 6: Implement exact transactions**

Implement these exact public signatures:

- `claim_run_dispatch(*, db_path: str | None, worker_id: str, lease_seconds: int, run_id: str | None = None, now: datetime | None = None) -> RunDispatchClaim | None`
- `start_run_dispatch(*, db_path: str | None, claim: RunDispatchClaim) -> bool`
- `release_run_dispatch_for_retry(*, db_path: str | None, claim: RunDispatchClaim, error_code: str) -> Literal["retry", "failed", "stale"]`
- `dispatch_attempt_is_started(*, db_path: str | None, claim: RunDispatchClaim) -> bool`
- `get_run_dispatch(*, db_path: str | None, run_id: str) -> dict[str, Any] | None`

The fixed retry ceiling comes from `MAX_RUN_DISPATCH_ATTEMPTS`; it is not a
function argument. Each mutating function uses an independent connection and
`BEGIN IMMEDIATE`.

Claim only a dispatch joined to `pending/state_version=0` and one pending initial segment. Eligibility is pending or an expired lease; order by `created_at, run_id`. Increment attempt once, build a complete `claim_payload` mapping from the joined row, and validate it with `RunDispatchClaim.model_validate(claim_payload, strict=True)`.

Start requires exact run/owner/attempt plus run pending/version 0 and initial segment pending. Re-read and compare thread ID, segment ID, query, profile ID/version, and canonical `scope_json` against the immutable claim before writing. Update dispatch leased->started, clear lease/error, set `started_at`; update run pending/0->running/1 and segment pending->running in one transaction. Any input or row-count mismatch rolls back and returns false.

Retry validates the stable error-code regex. Attempts 1-2 return exact lease to pending. Attempt 3 atomically changes dispatch/run/segment to failed, changes run state_version to 1, keeps run delivery `failed` and review `not_required`, and persists only the bounded code. Return exactly `retry`, `failed`, or `stale`.

- [ ] **Step 7: Run repeated GREEN and commit**

```bash
for i in 1 2; do
  PYTHON_DOTENV_DISABLED=1 python -m pytest \
    tests/unit/test_run_dispatch_repository.py tests/unit/test_run_migrations.py -q || exit 1
done
git diff --check
git add api/run_dispatch_repository.py api/run_migrations.py \
  tests/unit/test_run_dispatch_repository.py tests/unit/test_run_migrations.py
git commit -m "feat(api): reconcile run dispatch state"
```

Expected: both runs pass without SQLite race failures.

---

### Task 3: Add The Core Worker

**Files:**
- Create: `api/run_dispatch_worker.py`
- Create: `tests/unit/test_run_dispatch_worker.py`

**Interfaces:**
- Consumes: Task 2 claim/retry functions and `RunDispatchClaim`.
- Produces: `RunDispatchWorker`, `bounded_dispatch_error_code`, `wake`, `dispatch_run`, `run_once`, `run_forever`, `stop`.

- [ ] **Step 1: Write worker RED tests**

Use real temporary DB rows and an injected synchronous scheduler. Cover oldest polling, targeted fast path, one schedule per claim, scheduler exception release, third-attempt failure, wake, stop, loop survival after SQLite error, and bounded logs.

```python
@pytest.mark.asyncio
async def test_scheduler_failure_releases_claim_without_sensitive_text(tmp_path, caplog):
    db_path = str(tmp_path / "tasks.db")
    created = create_run(thread_id="thread-1", query="secret", db_path=db_path)

    def fail_scheduler(claim):
        raise RuntimeError("credential=/private/token")

    worker = RunDispatchWorker(
        db_path=db_path,
        scheduler=fail_scheduler,
        worker_id="dispatch_worker_00000000000000000000000000000001",
        lease_seconds=30,
        poll_seconds=0.01,
    )
    with caplog.at_level(logging.ERROR):
        assert await worker.dispatch_run(created["run_id"]) is True
    row = get_run_dispatch(db_path=db_path, run_id=created["run_id"])
    assert row["status"] == "pending"
    assert row["last_error_code"] == "run_dispatch_schedule_failed"
    assert "credential=/private/token" not in caplog.text
```

- [ ] **Step 2: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest tests/unit/test_run_dispatch_worker.py -q
```

Expected: module import fails.

- [ ] **Step 3: Implement the worker**

Implement `RunDispatchWorker` with these exact methods:

- `__init__(self, *, db_path: str | None, scheduler: Callable[[RunDispatchClaim], None], worker_id: str | None = None, lease_seconds: int = 30, poll_seconds: float = 1.0) -> None`
- `wake(self) -> None`
- `async dispatch_run(self, run_id: str) -> bool`
- `async run_once(self, *, run_id: str | None = None) -> bool`
- `async run_forever(self) -> None`
- `stop(self) -> None`

`run_once` claims in `asyncio.to_thread`, invokes the synchronous scheduler
once, and on exception logs only a bounded code before exact retry release.
Map SQLite/OSError to `run_dispatch_unavailable`, validation to
`run_dispatch_invalid`, and scheduler exceptions to
`run_dispatch_schedule_failed`. In `run_forever`, clear the wake event before
claiming; if no row was claimed, wait for stop, wake, or the poll timeout. This
ordering prevents a create committed between the claim and wait from losing its
wake. `stop` sets both stop and wake.

- [ ] **Step 4: Run GREEN and commit**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_run_dispatch_worker.py tests/unit/test_run_dispatch_repository.py -q
git diff --check
git add api/run_dispatch_worker.py tests/unit/test_run_dispatch_worker.py
git commit -m "feat(api): add durable run dispatcher"
```

---

### Task 4: Integrate Lifespan, Start Fence, Timeout, And API

**Files:**
- Modify: `api/server.py`
- Create: `tests/integration/test_run_dispatch_api.py`
- Modify: `tests/integration/test_run_api.py`
- Modify: `tests/integration/test_run_auxiliary_isolation.py`

**Interfaces:**
- Consumes: worker, claim, start/retry/attempt inspection, existing task tracker and terminal finalization.
- Produces: core lifespan worker, `_schedule_run_dispatch`, `_run_dispatched_with_persistence`, `_run_started_v2_with_persistence`, `_mark_dispatched_timeout`, route fast path.

- [ ] **Step 1: Write lifecycle/API RED tests**

Prove unconditional worker startup/shutdown, unchanged create responses, keyed replay without second Agent entry, scheduler failure returning 200 with durable retry, handler cancellation after commit, fresh-worker restart recovery, concurrent workers with one Agent entry, same-owner stale attempt blocked, pre-`008` identity-only replay, and stale timeout no-op.

The fake Agent counter must sit after production `start_run_dispatch`; do not replace the fence with a mock.

- [ ] **Step 2: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_run_dispatch_api.py tests/integration/test_run_api.py \
  tests/integration/test_run_auxiliary_isolation.py \
  tests/unit/test_task_tracker.py tests/unit/test_task_tracker_timeout.py -q
```

Expected: new tests fail because route/lifespan still own direct scheduling.

- [ ] **Step 3: Split pre-start from running execution**

Rename the existing body to the exact signature
`async def _run_started_v2_with_persistence(*, query: str, thread_id: str, run_id: str, segment_id: str, outcome_box: OutcomeBox, profile_id: str = "generic", scope: dict | None = None) -> None`.

Remove its initial transition and begin with state_version 1 / allowed previous `running`. Keep Agent call, artifacts, review, Evidence, cancellation, timeout, and terminal finalization otherwise unchanged.

Add `async def _run_dispatched_with_persistence(claim: RunDispatchClaim, *, db_path: str, outcome_box: OutcomeBox) -> None`. It calls `start_run_dispatch` against that path, returns silently on stale false, releases the exact claim with a bounded code on pre-start exception, logs no raw exception, and returns without re-raising into the generic task-tracker logger. Only a successful fence calls the started body using claim data. The existing running-state cancellation/error behavior remains unchanged after that call begins.

- [ ] **Step 4: Fence timeout by dispatch attempt**

Add `_mark_dispatched_timeout(claim, *, db_path, outcome_box, timeout_seconds)`. If `dispatch_attempt_is_started` is false, release the exact claim against that path with `run_dispatch_start_timeout`; stale is no-op. If true, call existing `_mark_run_timeout`. Test attempt 1 expiry, attempt 2 start, then attempt 1 timeout without changing attempt 2's running state.

- [ ] **Step 5: Move scheduling to one worker adapter**

```python
def _schedule_run_dispatch(claim, *, db_path):
    outcome_box = OutcomeBox()
    coroutine = _run_dispatched_with_persistence(
        claim, db_path=db_path, outcome_box=outcome_box
    )
    task_id = f"{claim.run_id}:dispatch:{claim.attempt_count}"
    try:
        create_tracked_task(
            coroutine,
            task_id,
            on_timeout=lambda _task_id, timeout_seconds: _mark_dispatched_timeout(
                claim,
                db_path=db_path,
                outcome_box=outcome_box,
                timeout_seconds=timeout_seconds,
            ),
        )
    except Exception:
        coroutine.close()
        raise
```

The attempt-qualified task ID prevents a stale attempt's done callback from removing a newer attempt from `active_tasks`. Add a regression test that holds attempt 1 open, reclaims/schedules attempt 2, completes attempt 1, and proves attempt 2 remains tracked until its own completion.

Add `create_run_dispatch_worker(application_db_path)`; it binds the private scheduler with `functools.partial(_schedule_run_dispatch, db_path=application_db_path)` so claims never carry a database path. Make FastAPI lifespan resolve the canonical path through `sqlite_db_path()`, run `migrate_with_backup(db_path=application_db_path, backup_path=f"{application_db_path}.pre-run-dispatch.bak")`, initialize/verify core schema, start this worker unconditionally, surface immediate task failure, and stop/await it separately from the review worker. Integration tests must set `DECISION_RESEARCH_AGENT_DB_PATH` to a temporary file before constructing `TestClient`; this keeps route repository defaults, lifespan, worker, and timeout callbacks on the same database without creating repository-local files.

- [ ] **Step 6: Route create/replay through the fast path**

After repository acceptance, both new and replay paths call the lifespan-owned worker's targeted `dispatch_run(run_id)`, then `wake()`, and return the existing response. `dispatch_run` contains expected claim/SQLite/scheduler failures and returns a handled boolean; those post-commit failures must not escape the route. Remove route-owned coroutine construction and immediate failure finalization. Worker scheduler failure after commit is bounded/retried and the route returns 200; pre-commit errors retain current mapping.

Adapt old tests: replace “replay never constructs coroutine” with “replay cannot win a second claim or enter Agent twice”; replace old scheduler-failure 500 with 200 plus retry/exhaustion polling.

- [ ] **Step 7: Run repeated GREEN and commit**

```bash
for i in 1 2 3; do
  PYTHON_DOTENV_DISABLED=1 python -m pytest \
    tests/integration/test_run_dispatch_api.py tests/integration/test_run_api.py \
    tests/integration/test_run_auxiliary_isolation.py tests/unit/test_task_tracker.py \
    tests/unit/test_task_tracker_timeout.py \
    tests/unit/test_run_dispatch_worker.py tests/unit/test_run_dispatch_repository.py -q || exit 1
done
git diff --check
git add api/server.py tests/integration/test_run_dispatch_api.py \
  tests/integration/test_run_api.py tests/integration/test_run_auxiliary_isolation.py
git commit -m "feat(api): recover unscheduled research runs"
```

Expected: three clean passes, no coroutine warnings, active-task leaks, or locked-DB flakes.

---

### Task 5: Add Deterministic Proof And CI

**Files:**
- Create: `scripts/run_dispatch_reconciliation_proof.py`
- Create: `tests/integration/test_run_dispatch_reconciliation_proof.py`
- Create: `docs/evidence/run-dispatch-reconciliation-v1.json`
- Create: `docs/evidence/run-dispatch-reconciliation-v1.md`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: production create/dispatch repository, worker, fence, verifier, and fake Agent boundary after the fence.
- Produces: `dra.run-dispatch-reconciliation-proof.v1` with `json`, `markdown`, and `check` modes.

- [ ] **Step 1: Write proof/CLI RED tests**

Require exact keys, ordered cases, boundaries, stable bytes, import silence, bounded reads, and one-line stable JSON stderr for invalid args and missing/corrupt/oversized baselines.

Ordered cases:

```python
EXPECTED_CASE_IDS = (
    "atomic_create",
    "commit_before_schedule_recovery",
    "handler_cancellation_recovery",
    "worker_restart_recovery",
    "expired_lease_reclaim",
    "concurrent_dispatch_fence",
    "stale_task_blocked",
    "scheduler_exhaustion",
    "keyed_replay_single_agent_entry",
    "unkeyed_compatibility",
    "contract_compatibility",
    "migration_safety",
)
```

- [ ] **Step 2: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_run_dispatch_reconciliation_proof.py -q
```

Expected: proof module import fails.

- [ ] **Step 3: Implement proof and fail-closed CLI**

Use exact constants:

```python
REPORT_SCHEMA_VERSION = "dra.run-dispatch-reconciliation-proof.v1"
BASELINE_JSON_PATH = PROJECT_ROOT / "docs/evidence/run-dispatch-reconciliation-v1.json"
BASELINE_MARKDOWN_PATH = PROJECT_ROOT / "docs/evidence/run-dispatch-reconciliation-v1.md"
MAX_BASELINE_BYTES = 1_000_000
```

Each case uses a disposable DB and production functions. Patch UUID/time only at their owning module boundary or omit volatile values. The fake Agent counter increments only after the real start fence. `contract_compatibility` completes one deterministic stubbed Agent run through the API, asserts canonical status/result/Evidence/review/verification shapes, and validates the existing downstream fixture through `validate_fixture_bundle`; it performs no provider call. `migration_safety` covers exact verification, repeated apply, injected restore, existing-backup protection, and no backfill. Validate the complete report before serialization. `check` rebuilds and byte-compares both baselines. Parse/report/baseline failure: stdout empty, compact JSON stderr, exit 1. Help exits 0. Reject symlink/non-regular/oversized baselines.

Required boundaries are exactly:

```json
{
  "commit_before_execution_start_recovery": "proven",
  "crash_before_schedule_recovery": "proven",
  "single_node_sqlite_dispatch_reconciliation": "proven",
  "exactly_once_execution": "not_claimed",
  "running_execution_recovery": "not_proven",
  "provider_tool_side_effect_exactly_once": "not_claimed",
  "multi_instance_high_availability": "not_proven",
  "live_provider_result": "not_observed"
}
```

- [ ] **Step 4: Generate baselines and run GREEN twice**

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/run_dispatch_reconciliation_proof.py json \
  > docs/evidence/run-dispatch-reconciliation-v1.json
PYTHON_DOTENV_DISABLED=1 python scripts/run_dispatch_reconciliation_proof.py markdown \
  > docs/evidence/run-dispatch-reconciliation-v1.md
PYTHON_DOTENV_DISABLED=1 python scripts/run_dispatch_reconciliation_proof.py check > /tmp/dispatch-1.json
PYTHON_DOTENV_DISABLED=1 python scripts/run_dispatch_reconciliation_proof.py check > /tmp/dispatch-2.json
cmp /tmp/dispatch-1.json /tmp/dispatch-2.json
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_run_dispatch_reconciliation_proof.py -q
```

- [ ] **Step 5: Add CI and commit**

Insert after the run-creation idempotency proof and before pytest:

```yaml
      - name: Run deterministic run dispatch reconciliation proof
        env:
          PYTHON_DOTENV_DISABLED: '1'
        run: python scripts/run_dispatch_reconciliation_proof.py check
```

Then run existing idempotency proof, new proof, Agent evaluation gate, and both proof tests. Commit:

```bash
git add scripts/run_dispatch_reconciliation_proof.py \
  tests/integration/test_run_dispatch_reconciliation_proof.py \
  docs/evidence/run-dispatch-reconciliation-v1.json \
  docs/evidence/run-dispatch-reconciliation-v1.md .github/workflows/ci.yml
git commit -m "test(api): prove durable run dispatch"
```

---

### Task 6: Publish Documentation And Run Final Verification

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/decisions/framework-runtime-boundaries.md`
- Modify: `docs/reference/api-contract.md`
- Modify: `docs/reference/data-models.md`
- Modify: `docs/reference/state-machines.md`
- Modify: `docs/AGENT_INTEGRATION.md`
- Modify: `docs/README.md`
- Modify: `docs/evidence/README.md`
- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/unit/test_documentation_contracts.py`

**Interfaces:**
- Consumes: actual implementation/proof behavior.
- Produces: public-neutral contract, operator guidance, clean committed review branch.

- [ ] **Step 1: Write documentation RED tests**

Require discoverability of `run_dispatches_v1`, migration `008`, create-ack semantics, asynchronous scheduling failure, proof files, no-backfill, and all non-claims. Assert `VERSION == 0.1.2`, old v0.1.2 proof still says crash recovery not proven, and new proof says proven.

- [ ] **Step 2: Run RED and update docs**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest tests/unit/test_documentation_contracts.py -q
```

Document: atomic create set, private dispatch state, exact claim fence, worker lifecycle, 200 acknowledgement, async retry/exhaustion, pre-008 no-backfill, recovery stopping at running, framework middleware reuse/rejection, migration backup/verify/rollback, and honest proof limits. Do not rewrite historical release notes or old evidence bytes.

- [ ] **Step 3: Run docs GREEN and commit**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_documentation_contracts.py tests/unit/test_release_metadata.py -q
PYTHON_DOTENV_DISABLED=1 python scripts/final_presentation_audit.py
PYTHON_DOTENV_DISABLED=1 python scripts/check_canonical_identity.py
git diff --check
git add docs/architecture.md docs/decisions/framework-runtime-boundaries.md \
  docs/reference/api-contract.md docs/reference/data-models.md \
  docs/reference/state-machines.md docs/AGENT_INTEGRATION.md docs/README.md \
  docs/evidence/README.md README.md README_CN.md CHANGELOG.md \
  tests/unit/test_documentation_contracts.py
git commit -m "docs(api): publish durable dispatch contract"
```

- [ ] **Step 4: Run the focused implementation matrix**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_run_dispatch_models.py tests/unit/test_run_dispatch_repository.py \
  tests/unit/test_run_dispatch_worker.py tests/unit/test_run_migrations.py \
  tests/unit/test_run_repository.py tests/unit/test_task_tracker.py \
  tests/integration/test_run_dispatch_api.py tests/integration/test_run_api.py \
  tests/integration/test_run_auxiliary_isolation.py \
  tests/integration/test_run_dispatch_reconciliation_proof.py \
  tests/integration/test_run_creation_idempotency_proof.py \
  tests/unit/test_documentation_contracts.py tests/unit/test_release_metadata.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Run proofs, full suite, and final audits**

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/run_dispatch_reconciliation_proof.py check > /tmp/final-dispatch-1.json
PYTHON_DOTENV_DISABLED=1 python scripts/run_dispatch_reconciliation_proof.py check > /tmp/final-dispatch-2.json
cmp /tmp/final-dispatch-1.json /tmp/final-dispatch-2.json
PYTHON_DOTENV_DISABLED=1 python scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 python scripts/downstream_consumer_contract.py check \
  --input docs/evidence/downstream-consumer-contract-v1.json
PYTHON_DOTENV_DISABLED=1 python -m pytest -q
PYTHON_DOTENV_DISABLED=1 python scripts/final_presentation_audit.py
PYTHON_DOTENV_DISABLED=1 python scripts/check_canonical_identity.py
git diff --check origin/main..HEAD
git diff --name-only origin/main..HEAD -- requirements.txt constraints.txt pyproject.toml
git status --short --branch
```

If the full suite is blocked by a missing declared dependency, report interpreter/package versions, missing import, and error count; do not install dependencies, use a stub for the full suite, or claim it passed.

- [ ] **Step 6: Run runtime boundary scan**

```bash
rg -n "from (langsmith|langgraph|deepagents)|import (langsmith|langgraph|deepagents)" \
  api/run_dispatch_models.py api/run_dispatch_repository.py api/run_dispatch_worker.py || true
```

Expected: `final_presentation_audit.py` has already reported no public/private marker violation, the dependency diff is empty, the new application dispatch authority files import no framework runtime/tracing authority, and the worktree is clean.

- [ ] **Step 7: Report for authoritative review**

Report base/final HEAD, ordered commits, changed files, every RED/GREEN command and count, repeated proof bytes, migration/no-backfill/rollback evidence, framework reuse decision, dependency diff, exact non-claims, environment risks, clean status, and confirmation of no push/PR/merge/version/release/deploy/cleanup. Do not run a second broad review in the execution window.
