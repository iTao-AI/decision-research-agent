# Durable Run Failure Cause v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist one immutable, bounded, application-owned terminal cause for
every post-migration failed ResearchRun and expose it additively on the run
status endpoint without changing the canonical result or downstream v1
contracts.

**Architecture:** Add strict Pydantic cause contracts and migration
`009_run_failure_cause_v1`, then join one cause row to the existing fenced run
terminal transaction. Preserve DeepAgents, LangChain, and LangGraph as sources
of bounded execution signals while the application database remains terminal
authority; replace implicit timeout ownership with an application termination
origin and shield every already-started database thread to settlement.

**Tech Stack:** Python 3.11, FastAPI lifespan, asyncio tasks, SQLite WAL with
`BEGIN IMMEDIATE`, Pydantic 2.13.4 strict models, DeepAgents 0.6.11, LangChain
1.3.10, LangGraph 1.2.6, pytest, deterministic JSON/Markdown proof, GitHub
Actions.

## Global Constraints

- Implement only
  `docs/superpowers/specs/2026-07-16-durable-run-failure-cause-design.md`.
- Work in the existing isolated branch containing the approved spec. Before
  implementation, fetch and compare `origin/main`; stop for redesign if the run
  persistence, dispatch, task-tracker, review, publication, or result contracts
  changed materially.
- Use TDD for every behavior change: focused RED, minimal implementation,
  focused GREEN, then broader verification.
- Migration identity is exactly `009_run_failure_cause_v1`; checksum is exactly
  `run-failure-cause-v1`; table is exactly `run_failure_causes_v1`.
- Public schema is exactly `dra.run-failure-cause.v1`; proof schema is exactly
  `dra.run-failure-cause-proof.v1`.
- Keep the phase/code allowlist exact. Never place raw exception classes,
  messages, tracebacks, provider payloads, queries, paths, credentials, retry
  guesses, or arbitrary harness strings in the failure-cause row, its public
  projection, or the proof.
- `GET /api/runs/{run_id}` gains only the top-level `failure_cause` field.
  `GET /api/runs/{run_id}/result`, every stable result error envelope, and the
  committed `dra.downstream-consumer.v1` fixture bytes remain unchanged.
- A post-`009` failed run must have exactly one observed cause. Historical
  failures receive only `not_observed`; nonfailed runs have no cause row.
- Cause, run, segment, Evidence, packet, artifact, and review writes share the
  winning terminal transaction. Failed runs are execution-terminal and cannot
  be version-incremented by later review or publication paths.
- Reuse existing native call-limit and recursion exceptions. Do not add Agent
  middleware, LangGraph checkpoint authority, LangSmith authority, provider
  behavior, runtime Skills, memory, Async Subagents, or a second business
  ledger.
- Do not add dependencies or change `requirements.txt`, `constraints.txt`,
  `VERSION`, frontend packages, authentication, CORS, provider URLs, upload
  permissions, or filesystem permissions.
- Keep `VERSION` at `0.1.3`. Do not push, create a PR, merge, tag, release,
  deploy, or clean the worktree during implementation.
- Public artifacts must remain credential-free, provider-free, network-free,
  deterministic, and free of private paths or consumer-specific content.

---

## File And Responsibility Map

| File | Responsibility |
|---|---|
| `api/run_failure_cause_models.py` | Strict constants, phase/code matrix, write contract, public projection variants, bounded conflict |
| `api/database.py` | Neutral SQLite backup/restore primitives shared without repository import cycles |
| `api/run_repository.py` | Sole `009` apply/verify coordinator, atomic execution terminal cause, one-query status projection, failed-state helper fences |
| `api/run_migrations.py` | Exact full-schema verification, earlier migration compatibility, historical marker verification |
| `api/run_dispatch_repository.py` | Exact-attempt dispatch terminal cause and pre-start timeout/cancellation reconciliation |
| `api/task_tracker.py` | Monotonic termination origin, explicit inner task, mutually exclusive callbacks, shield-and-settle helper |
| `api/review_repository.py` | Failed-state fences for review decision and resolution writers |
| `api/publication_repository.py` | Failed-state fences for backfill, invalidation, repair, and publication writers |
| `api/server.py` | Stage-aware mapper, start/terminal task settlement, timeout/cancel callbacks, bounded status corruption response |
| `scripts/downstream_consumer_contract.py` | Typed failed seed while preserving committed v1 fixture bytes |
| `scripts/run_failure_cause_proof.py` | Fixed production-path proof, strict validator, bounded CLI and baseline comparison |
| `.github/workflows/ci.yml` | Required failure-cause proof before broad backend tests |
| `tests/unit/test_run_failure_cause_models.py` | Strict model and phase/code contract |
| migration/repository/tracker/review/publication tests | SQL, transaction, state machine, and race regressions |
| run API, result, dispatch, Evidence, harness integration tests | Public projection, compatibility, and real execution boundaries |
| `tests/integration/test_run_failure_cause_proof.py` | Proof semantics, mutation resistance, CLI, deterministic bytes |
| `docs/evidence/run-failure-cause-v1.{json,md}` | Committed deterministic proof baselines |
| architecture/reference/README files | Public behavior, authority, migration, rollback, and non-claims |

## Framework Reuse Decision

- Keep `ModelCallLimitMiddleware` and `ToolCallLimitMiddleware` with
  `exit_behavior="error"`; map their existing typed exceptions to
  `call_budget_exceeded`.
- Keep LangGraph `GraphRecursionError` mapping to
  `recursion_limit_exceeded`.
- Keep `ResearchExecutionService` responsible for freezing partial Evidence and
  publishing an in-memory outcome. It does not write the durable cause.
- Use strict, frozen, extra-forbid Pydantic models for write and projection
  contracts.
- Use FastAPI lifespan, asyncio tasks, and existing SQLite transactions. Do not
  add LangGraph `TimeoutPolicy`: it bounds a graph node attempt, not the whole
  application ResearchRun.
- Keep LangSmith diagnostic-only. Trace availability, sampling, or redaction
  cannot affect the cause row or projection.

## State And Data Flow

```text
framework / packet / dispatch / tracker signal
                     |
                     v
          bounded application mapper
                     |
                     v
      exact run state-version or dispatch-attempt fence
                     |
                     v
 BEGIN IMMEDIATE terminal transaction
   run failed + segment failed + frozen Evidence + cause observed
                     |
                     v
 one joined status snapshot -> strict projection -> failure_cause
```

```text
pre-009 failed -------------------------------> not_observed
post-009 pending/running --terminal winner----> observed
nonfailed ------------------------------------> no row / null projection

failed --X--> any later execution/review/publication mutation
```

## Execution Ordering And Ownership

The plan has two safe parallel waves, followed by one integration owner:

1. Task 1 defines shared types and must complete first.
2. Tasks 2 and 5 are independent: migration/persistence schema versus tracker
   cancellation semantics.
3. After Task 2, Tasks 3, 4, and 6 own disjoint production files and may run in
   parallel: terminal repository/status, review/publication fences, and dispatch
   causes.
4. Task 7 is the single integration gate and exclusively owns `api/server.py`
   plus shared API integration tests.
5. Tasks 8 and 9 run after the production path is stable. The integration owner
   owns baselines, CI, documentation indexes, final verification, and commits.

The integration owner creates one isolated worktree and branch per parallel
lane; workers never share an index or commit concurrently in one worktree.
Wave 1 Tasks 2 and 5 start from the Task 1 commit. After their commits are
cherry-picked into the integration branch, Wave 2 Tasks 3, 4, and 6 each start
from that single integrated Task 2+5 HEAD. Task 7 starts only after all Wave 2
commits are integrated. Each worker modifies only its assigned files, runs its
focused RED/GREEN cycle, and returns one commit for ordered cherry-pick.
Workers must not edit `api/server.py`, CI, proof baselines, shared
documentation, or another lane's tests. The integration owner resolves shared
call sites and runs the combined matrix after every cherry-pick.

---

### Task 1: Define Strict Failure Cause Contracts

**Files:**

- Create: `api/run_failure_cause_models.py`
- Create: `tests/unit/test_run_failure_cause_models.py`

**Interfaces:**

- Consumes: Pydantic strict Python-object validation.
- Produces: constants, `RunFailureCauseWrite`,
  `ObservedRunFailureCause`, `NotObservedRunFailureCause`,
  `RunFailureCauseProjectionAdapter`, `RunStatusFailureCauseOpenAPI`, and
  `RunFailureCauseConflict`.

- [ ] **Step 1: Write the strict contract RED tests**

Create the test module with the exact matrix and representative strictness
checks below. Add parametrized cases for every valid phase/code pair, every
cross-phase mismatch, an unknown code, extra fields, coercion, mutation, naive
time, non-UTC offset, and raw exception text. Assert that
`RunStatusFailureCauseOpenAPI.model_json_schema()` declares one required
nullable discriminated field, permits existing top-level status properties,
and contains no storage-only terminal version.

```python
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from api.run_failure_cause_models import (
    RUN_FAILURE_CAUSE_CODES,
    RUN_FAILURE_CAUSE_MIGRATION_CHECKSUM,
    RUN_FAILURE_CAUSE_MIGRATION_VERSION,
    RUN_FAILURE_CAUSE_SCHEMA_VERSION,
    NotObservedRunFailureCause,
    ObservedRunFailureCause,
    RunFailureCauseWrite,
)


EXPECTED = {
    "dispatch": {
        "run_dispatch_schedule_failed",
        "run_dispatch_start_failed",
        "run_dispatch_start_timeout",
        "run_dispatch_lease_expired",
    },
    "execution": {
        "call_budget_exceeded",
        "recursion_limit_exceeded",
        "invalid_research_packet",
        "missing_research_packet",
        "run_timeout",
        "cancelled",
        "execution_error",
    },
    "finalization": {
        "run_timeout",
        "cancelled",
        "run_finalization_failed",
    },
}


def test_failure_cause_constants_and_matrix_are_exact():
    assert RUN_FAILURE_CAUSE_SCHEMA_VERSION == "dra.run-failure-cause.v1"
    assert RUN_FAILURE_CAUSE_MIGRATION_VERSION == "009_run_failure_cause_v1"
    assert RUN_FAILURE_CAUSE_MIGRATION_CHECKSUM == "run-failure-cause-v1"
    assert {key: set(value) for key, value in RUN_FAILURE_CAUSE_CODES.items()} == EXPECTED


@pytest.mark.parametrize(
    ("phase", "code"),
    [(phase, code) for phase, codes in EXPECTED.items() for code in sorted(codes)],
)
def test_write_contract_accepts_only_exact_phase_code_pairs(phase, code):
    value = RunFailureCauseWrite.model_validate(
        {"phase": phase, "code": code}, strict=True
    )
    assert value.phase == phase
    assert value.code == code


def test_projection_variants_are_strict_and_historical_has_no_inference():
    observed = ObservedRunFailureCause.model_validate(
        {
            "schema_version": "dra.run-failure-cause.v1",
            "observation_status": "observed",
            "phase": "execution",
            "code": "execution_error",
            "recorded_at": datetime(2026, 7, 16, tzinfo=timezone.utc),
        },
        strict=True,
    )
    assert observed.recorded_at.utcoffset() == timedelta(0)
    with pytest.raises(ValidationError):
        NotObservedRunFailureCause.model_validate(
            {
                "schema_version": "dra.run-failure-cause.v1",
                "observation_status": "not_observed",
                "phase": "execution",
            },
            strict=True,
        )
```

- [ ] **Step 2: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_run_failure_cause_models.py -q
```

Expected: collection fails with
`ModuleNotFoundError: No module named 'api.run_failure_cause_models'`.

- [ ] **Step 3: Implement the exact contracts**

Create the module with immutable constants and strict variants. The write model
contains only `phase` and `code`; database identity, timestamp, and terminal
version remain repository-owned.

```python
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

RUN_FAILURE_CAUSE_SCHEMA_VERSION = "dra.run-failure-cause.v1"
RUN_FAILURE_CAUSE_MIGRATION_VERSION = "009_run_failure_cause_v1"
RUN_FAILURE_CAUSE_MIGRATION_CHECKSUM = "run-failure-cause-v1"

RunFailurePhase = Literal["dispatch", "execution", "finalization"]
RUN_FAILURE_CAUSE_CODES = MappingProxyType({
    "dispatch": frozenset({
        "run_dispatch_schedule_failed",
        "run_dispatch_start_failed",
        "run_dispatch_start_timeout",
        "run_dispatch_lease_expired",
    }),
    "execution": frozenset({
        "call_budget_exceeded",
        "recursion_limit_exceeded",
        "invalid_research_packet",
        "missing_research_packet",
        "run_timeout",
        "cancelled",
        "execution_error",
    }),
    "finalization": frozenset({
        "run_timeout", "cancelled", "run_finalization_failed",
    }),
})


class _StrictContract(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")


class RunFailureCauseWrite(_StrictContract):
    phase: RunFailurePhase
    code: str

    @model_validator(mode="after")
    def require_exact_pair(self):
        if self.code not in RUN_FAILURE_CAUSE_CODES[self.phase]:
            raise ValueError("run_failure_cause_invalid")
        return self


class ObservedRunFailureCause(RunFailureCauseWrite):
    schema_version: Literal["dra.run-failure-cause.v1"] = (
        RUN_FAILURE_CAUSE_SCHEMA_VERSION
    )
    observation_status: Literal["observed"] = "observed"
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("run_failure_cause_timestamp_invalid")
        return value


class NotObservedRunFailureCause(_StrictContract):
    schema_version: Literal["dra.run-failure-cause.v1"] = (
        RUN_FAILURE_CAUSE_SCHEMA_VERSION
    )
    observation_status: Literal["not_observed"] = "not_observed"


RunFailureCauseProjection = Annotated[
    ObservedRunFailureCause | NotObservedRunFailureCause,
    Field(discriminator="observation_status"),
]
RunFailureCauseProjectionAdapter = TypeAdapter(RunFailureCauseProjection)


class RunStatusFailureCauseOpenAPI(BaseModel):
    model_config = ConfigDict(extra="allow")
    failure_cause: RunFailureCauseProjection | None


class RunFailureCauseConflict(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
```

- [ ] **Step 4: Run GREEN and strict mutation cases**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_run_failure_cause_models.py -q
```

Expected: all new model tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add api/run_failure_cause_models.py \
  tests/unit/test_run_failure_cause_models.py
git commit -m "feat(api): define run failure cause contracts"
```

---

### Task 2: Add Migration 009, Historical Markers, And Dedicated Backup

**Files:**

- Modify: `api/database.py` (move/re-export neutral SQLite backup primitives)
- Modify: `api/run_repository.py` (`_init_run_schema_unlocked`,
  `_insert_run_identity`, migration helpers)
- Modify: `api/run_migrations.py` (required schema, verification,
  `migrate_with_backup`)
- Modify: `tests/unit/test_run_migrations.py`
- Modify: `tests/unit/test_run_repository.py`

**Interfaces:**

- Consumes: Task 1 constants, models, and bounded conflict.
- Produces: exact table `run_failure_causes_v1`, verified marker `009`, one-shot
  historical `not_observed` rows, and run-creation readiness checks.

- [ ] **Step 1: Write migration RED tests**

Extend the existing migration helpers. Seed a current pre-`009` database by
running the existing migrations, then remove `009` with one test helper that
drops `run_failure_causes_v1` and deletes the exact marker in the same
transaction. Insert completed, pending, running, and failed runs directly only
after that removal. Do not leave the new table behind with only its marker
deleted; that is a partial-schema corruption case, not a pre-`009` seed. The
central assertion must distinguish historical absence from an observed cause.

```python
def test_009_marks_only_preexisting_failed_runs_not_observed(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    _seed_pre_009_runs(
        db_path,
        statuses=("completed", "pending", "running", "failed"),
    )

    migrate_with_backup(
        db_path=db_path,
        backup_path=str(tmp_path / "tasks.pre-run-dispatch.bak"),
    )

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT * FROM run_failure_causes_v1 ORDER BY run_id"
        ).fetchall()
        marker_count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
            ("009_run_failure_cause_v1",),
        ).fetchone()[0]
    finally:
        connection.close()

    assert marker_count == 1
    assert len(rows) == 1
    assert rows[0]["observation_status"] == "not_observed"
    assert rows[0]["terminal_state_version"] is None
    assert rows[0]["phase"] is None
    assert rows[0]["code"] is None
    assert rows[0]["recorded_at"] is None
```

Add exact RED cases:

```text
test_009_schema_marker_fk_and_variant_check_are_exact
test_009_inserts_historical_rows_before_single_marker
test_009_marker_present_is_verify_only_and_never_repairs
test_009_rejects_nullable_run_id_or_observation_status
test_009_rejects_null_observed_fields_and_noninteger_terminal_version
test_009_rejects_zero_and_negative_terminal_version
test_009_rejects_observed_terminal_version_mismatch
test_009_rejects_observed_recorded_at_or_segment_timestamp_mismatch
test_009_repeated_apply_is_idempotent
test_fresh_pre_003_database_applies_legacy_chain_then_009_without_nested_transaction
test_009_table_create_failure_restores_complete_dedicated_backup
test_009_historical_insert_failure_restores_complete_dedicated_backup
test_009_marker_insert_failure_restores_complete_dedicated_backup
test_009_post_verify_failure_restores_complete_dedicated_backup
test_009_existing_dedicated_backup_is_not_overwritten
test_direct_init_on_pre_009_database_creates_dedicated_backup_before_writes
test_create_run_cannot_bypass_009_backup_or_verification
test_dispatch_review_and_publication_init_cannot_bypass_009_backup
test_wrong_009_checksum_fails_init_migration_and_creation_without_repair
test_run_creation_rejects_missing_or_wrong_009_marker_before_insert
```

For marker ordering, install a temporary `BEFORE INSERT ON schema_migrations`
trigger that aborts the `009` marker unless the historical row count already
equals the failed-run count.

- [ ] **Step 2: Run migration RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_run_migrations.py \
  tests/unit/test_run_repository.py -q
```

Expected: failures report the missing `009` table/marker and missing
run-creation readiness check.

- [ ] **Step 3: Implement the exact DDL and one-shot order**

Add one table constant and private apply/verify helpers. Use `CREATE TABLE`, not
`CREATE TABLE IF NOT EXISTS`, on the marker-absent path so a partial table fails
closed.

Let the existing legacy schema `with connection:` transaction fully exit and
commit before invoking the `009` helper. The helper then opens its own
`BEGIN IMMEDIATE` transaction on the settled connection or a fresh connection;
it must never start inside the legacy transaction. Its rollback/close completes
before `init_run_schema` restores the dedicated backup.

```sql
CREATE TABLE run_failure_causes_v1 (
    run_id TEXT NOT NULL PRIMARY KEY
        REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
    observation_status TEXT NOT NULL
        CHECK(observation_status IN ('observed', 'not_observed')),
    terminal_state_version INTEGER,
    phase TEXT,
    code TEXT,
    recorded_at TEXT,
    CHECK(
        (
            observation_status = 'not_observed'
            AND terminal_state_version IS NULL
            AND phase IS NULL
            AND code IS NULL
            AND recorded_at IS NULL
        )
        OR
        (
            observation_status = 'observed'
            AND typeof(terminal_state_version) = 'integer'
            AND terminal_state_version > 0
            AND phase IS NOT NULL
            AND code IS NOT NULL
            AND recorded_at IS NOT NULL
            AND (
                (phase = 'dispatch' AND code IN (
                    'run_dispatch_schedule_failed',
                    'run_dispatch_start_failed',
                    'run_dispatch_start_timeout',
                    'run_dispatch_lease_expired'
                ))
                OR
                (phase = 'execution' AND code IN (
                    'call_budget_exceeded',
                    'recursion_limit_exceeded',
                    'invalid_research_packet',
                    'missing_research_packet',
                    'run_timeout',
                    'cancelled',
                    'execution_error'
                ))
                OR
                (phase = 'finalization' AND code IN (
                    'run_timeout',
                    'cancelled',
                    'run_finalization_failed'
                ))
            )
        )
    )
)
```

The marker-absent transaction order is exact:

```python
connection.execute("BEGIN IMMEDIATE")
marker = connection.execute(
    "SELECT checksum FROM schema_migrations WHERE version = ?",
    (RUN_FAILURE_CAUSE_MIGRATION_VERSION,),
).fetchone()
if marker is not None:
    _verify_run_failure_cause_marker(connection)
    _verify_run_failure_cause_schema(connection)
    _verify_run_failure_cause_rows(connection)
    connection.commit()
    return

connection.execute(RUN_FAILURE_CAUSE_TABLE_SQL)
_verify_run_failure_cause_schema(connection)
connection.execute(
    """
    INSERT INTO run_failure_causes_v1(
        run_id, observation_status, terminal_state_version,
        phase, code, recorded_at
    )
    SELECT run_id, 'not_observed', NULL, NULL, NULL, NULL
    FROM research_runs_v2
    WHERE execution_status = 'failed'
    ORDER BY run_id
    """
)
connection.execute(
    "INSERT INTO schema_migrations(version, applied_at, checksum) VALUES (?, ?, ?)",
    (
        RUN_FAILURE_CAUSE_MIGRATION_VERSION,
        _now(),
        RUN_FAILURE_CAUSE_MIGRATION_CHECKSUM,
    ),
)
_verify_run_failure_cause_marker(connection)
_verify_run_failure_cause_schema(connection)
_verify_run_failure_cause_rows(connection)
connection.commit()
```

`_verify_run_failure_cause_marker` requires exactly one row with the exact
version/checksum. On any exception, roll back and close this connection before
any restore. Marker-present startup is verification-only and never inserts or
repairs a cause row.

- [ ] **Step 4: Extend full schema verification and backup ownership**

Add `009` to required migrations/tables/columns. Verify exact `PRAGMA
table_info` order, types, `notnull`, single-column PK, FK/CASCADE, normalized
variant SQL, and cross-table rows. Parse observed timestamps through the strict
projection model, compare observed terminal version to run `state_version`,
require `recorded_at == run.updated_at`, and require a failed segment for the
same run with that `updated_at`.

Move the existing SQLite `backup_database` and `restore_database` primitives to
`api/database.py`. Import and re-export them from `api/run_migrations.py` so
existing migration callers/tests retain their import contract. This neutral
module lets `api/run_repository.py` own `009` backup orchestration without a
repository import cycle.

`init_run_schema` is the sole apply/verify entry. Under its existing process
lock, inspect the `009` marker before `_init_run_schema_unlocked` can write:

- exact marker/checksum present: run `_init_run_schema_unlocked` in
  verification-only mode for `009`; do not create a backup or repair rows;
- marker absent: derive the path below, refuse an existing file, create the
  full backup, then call `_init_run_schema_unlocked` so it applies `009`;
- wrong checksum: fail immediately without backup, schema write, or repair;
- initializer failure: let its migration connection roll back and close, then
  restore the dedicated backup and re-raise.

All `009` marker/schema/row helpers raise only typed
`RunFailureCauseConflict`: use `run_failure_cause_unavailable` for missing or
wrong readiness and `run_failure_cause_corrupt` for malformed persisted state.
`run_migrations.py` may let this `RuntimeError` subclass propagate through
operator verification. Normal run reads must never expose raw
SQLite/Pydantic errors from these helpers.

The dedicated path is:

```python
failure_backup_path = Path(
    f"{sqlite_db_path(db_path)}.pre-run-failure-cause.bak"
)
```

Keep the existing caller-supplied `backup_path` behavior and branch bodies for
older migrations. Add `failure_cause_applied` to `migrate_with_backup`; after
the current dispatch branch add
`elif not failure_cause_applied: init_run_schema(db_path)`. That call uses the
single coordinator above and owns the dedicated backup/restore. Earlier
branches also call the same coordinator internally, so they cannot apply `009`
without the dedicated backup; their existing caller backup and restore remain
unchanged. The final full verifier still runs after the selected branch.

Inside `_insert_run_identity`, check the exact marker/checksum and verified
table readiness on the current transaction connection before the first run
insert. Raise
`RunFailureCauseConflict("run_failure_cause_unavailable")` on mismatch.

- [ ] **Step 5: Run migration GREEN twice**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_run_migrations.py \
  tests/unit/test_review_migrations.py \
  tests/unit/test_evidence_verification_migrations.py \
  tests/unit/test_publication_migrations.py \
  tests/unit/test_run_repository.py -q
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_run_migrations.py \
  tests/unit/test_review_migrations.py \
  tests/unit/test_evidence_verification_migrations.py \
  tests/unit/test_publication_migrations.py \
  tests/unit/test_run_repository.py -q
```

Expected: both runs pass and no second apply repairs a deliberately corrupted
post-marker database.

- [ ] **Step 6: Commit Task 2**

```bash
git add api/database.py api/run_repository.py api/run_migrations.py \
  tests/unit/test_run_migrations.py tests/unit/test_run_repository.py
git commit -m "feat(api): migrate durable run failure causes"
```

---

### Task 3: Persist The Cause In The Winning Terminal Transaction

**Files:**

- Modify: `api/run_repository.py`
- Modify: `tests/unit/test_run_repository.py`
- Modify: `tests/integration/test_run_api.py`
- Modify: `tests/integration/test_run_result_api.py`
- Modify: `scripts/downstream_consumer_contract.py`
- Modify: `tests/integration/test_downstream_consumer_contract.py`

**Interfaces:**

- Consumes: Task 1 contracts and Task 2 verified table.
- Produces: one atomic failed terminal writer, one joined status projection,
  and unchanged result/downstream v1 contracts.

- [ ] **Step 1: Write atomic terminal RED tests**

Add repository cases covering the complete invariant rather than only the new
row:

```text
test_failed_finalization_requires_a_typed_failure_cause
test_nonfailed_finalization_rejects_a_failure_cause
test_failed_finalization_inserts_cause_at_winning_state_version
test_failed_finalization_uses_one_timestamp_for_run_segment_and_cause
test_stale_failed_finalization_inserts_no_cause
test_cause_insert_failure_rolls_back_run_segment_evidence_packet_artifact_and_review
test_transition_run_rejects_failed_target_and_failed_previous_status
test_allowed_previous_statuses_are_nonempty_pending_or_running_only
```

Use an `AFTER INSERT ON run_failure_causes_v1` abort trigger for the rollback
test and assert every table remains at its pre-call state. Assert that a losing
compare-and-set returns `False`, while contract misuse raises the bounded
`RunFailureCauseConflict` code.

The finalizer signature becomes:

```python
def finalize_run_transaction(
    *,
    run_id: str,
    segment_id: str,
    expected_state_version: int,
    allowed_previous_statuses: set[str],
    execution_status: str,
    delivery_status: str,
    evidence_entries: list[Any],
    failure_cause: RunFailureCauseWrite | None = None,
    db_path: str | None = None,
    review_status: str = "not_required",
    research_packets: list[Any] | None = None,
    review_bundle: Any | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    review_workflow: dict[str, str] | None = None,
) -> bool:
```

- [ ] **Step 2: Write status projection and compatibility RED tests**

Add exact API/repository cases:

```text
historical failed -> failure_cause.not_observed
new failed -> failure_cause.observed with no terminal_state_version exposed
pending/running/completed/completed_with_fallback -> failure_cause is null
failed with no row -> bounded conflict
nonfailed with any cause row -> bounded conflict
observed row with a different terminal_state_version -> bounded conflict
observed row with valid UTC recorded_at different from run.updated_at -> bounded conflict
not_observed row with a nonnull terminal_state_version -> bounded conflict
invalid recorded_at or phase/code -> bounded conflict
init pre-read corruption and direct joined projection corruption -> same bounded conflict
GET /result failed status/body -> byte-for-byte unchanged
downstream v1 JSON/Markdown/checksum -> byte-for-byte unchanged
```

The downstream script may seed its failed test run with a typed
`execution_error` cause, but must discard the new status-only field before its
v1 projection. Check the committed fixture rather than regenerating it as a
side effect of the test.

- [ ] **Step 3: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_run_repository.py \
  tests/integration/test_run_api.py \
  tests/integration/test_run_result_api.py \
  tests/integration/test_downstream_consumer_contract.py -q
```

Expected: new cause arguments, invariants, and status projections are absent;
the legacy cases that do not create failed runs continue to pass.

- [ ] **Step 4: Implement the winning transaction**

Validate before opening the write transaction:

```python
if not allowed_previous_statuses or not allowed_previous_statuses <= {
    "pending",
    "running",
}:
    raise RunFailureCauseConflict("run_failure_cause_transition_invalid")
if execution_status == "failed" and failure_cause is None:
    raise RunFailureCauseConflict("run_failure_cause_required")
if execution_status != "failed" and failure_cause is not None:
    raise RunFailureCauseConflict("run_failure_cause_forbidden")
```

After the fenced run update wins, compute
`terminal_state_version = expected_state_version + 1`. Perform all existing
terminal child writes unchanged, then insert the plain cause row in the same
transaction before commit:

```python
connection.execute(
    """
    INSERT INTO run_failure_causes_v1(
        run_id, observation_status, terminal_state_version,
        phase, code, recorded_at
    ) VALUES (?, 'observed', ?, ?, ?, ?)
    """,
    (
        run_id,
        terminal_state_version,
        failure_cause.phase,
        failure_cause.code,
        now,
    ),
)
```

Do not use `INSERT OR IGNORE`, `REPLACE`, or an upsert. Convert SQLite cause
constraint failures to `RunFailureCauseConflict("run_failure_cause_conflict")`
after the transaction rolls back.

Make `transition_run` reject `execution_status="failed"` and reject any
`allowed_previous_statuses` containing `failed`; all execution-terminal
failures must use the atomic finalizer.

- [ ] **Step 5: Implement one joined status snapshot**

Replace the initial status-table read in `get_run` with one left join that uses
explicit aliases:

```sql
SELECT
    r.*,
    c.observation_status AS failure_observation_status,
    c.terminal_state_version AS failure_terminal_state_version,
    c.phase AS failure_phase,
    c.code AS failure_code,
    c.recorded_at AS failure_recorded_at
FROM research_runs_v2 AS r
LEFT JOIN run_failure_causes_v1 AS c ON c.run_id = r.run_id
WHERE r.run_id = ?
```

Create a private `_failure_cause_projection(row)` that enforces the full
cross-row invariant and returns either `None` or
`model_dump(mode="json")` from the strict adapter. Remove the aliased storage
columns before `_run_row` consumes the run fields. Catch Pydantic,
recorded-at-versus-run-updated-at, and row-shape errors and raise only
`RunFailureCauseConflict("run_failure_cause_corrupt")`.

- [ ] **Step 6: Run GREEN and compatibility checks**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_run_failure_cause_models.py \
  tests/unit/test_run_repository.py \
  tests/integration/test_run_api.py \
  tests/integration/test_run_result_api.py \
  tests/integration/test_downstream_consumer_contract.py -q
PYTHON_DOTENV_DISABLED=1 python \
  scripts/downstream_consumer_contract.py check \
  --input docs/evidence/downstream-consumer-contract-v1.json
```

Expected: all tests pass; the downstream command reports `valid` and its
fixture has no diff.

- [ ] **Step 7: Commit Task 3**

```bash
git add api/run_repository.py scripts/downstream_consumer_contract.py \
  tests/unit/test_run_repository.py tests/integration/test_run_api.py \
  tests/integration/test_run_result_api.py \
  tests/integration/test_downstream_consumer_contract.py
git commit -m "feat(api): persist atomic run failure causes"
```

---

### Task 4: Fence Review And Publication Writers After Failure

**Files:**

- Modify: `api/review_repository.py`
- Modify: `api/publication_repository.py`
- Modify: `tests/unit/test_review_repository.py`
- Modify: `tests/unit/test_publication_repository.py`
- Modify: `tests/unit/test_publication_migrations.py`

**Interfaces:**

- Consumes: the existing run/review/publication state machine.
- Produces: no path that can increment or repair a failed run after its cause
  freezes the terminal state version.

- [ ] **Step 1: Write failed-state escape RED tests**

Seed deliberately inconsistent legacy rows directly so each writer is tested
at its own authority boundary. Cover:

```text
accept_review_decision rejects a failed run even with pending workflow
resolve_review rejects a failed run even with an accepted decision
publication backfill fails on a failed run with review/publication residue
stale_current_publication rejects a failed run
verification repair rejects a failed run
new verification publication rejects a failed run
every rejection leaves run state_version, cause row, review rows,
publication rows, snapshots, artifact flags, and Evidence unchanged
```

Assert the current bounded repository conflict family, not raw SQLite text.

- [ ] **Step 2: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_review_repository.py \
  tests/unit/test_publication_repository.py \
  tests/unit/test_publication_migrations.py -q
```

Expected: the seeded failed rows still reach one or more direct writers.

- [ ] **Step 3: Add exact execution-state fences**

In `accept_review_decision`, extend the same transaction's run predicate to
require:

```text
execution_status = completed
review_status = required
delivery_status = review_required
```

In `resolve_review`, require execution status in
`completed|completed_with_fallback` together with its existing review fence.
For each row-count miss, roll back and return or raise the repository's current
bounded stale/conflict outcome.

In publication code:

- `_backfill_publications` must detect any failed run that has review or
  publication residue and abort migration rather than manufacture history.
- `stale_current_publication` must require
  `execution_status IN ('completed', 'completed_with_fallback')` in the run
  update; a broad `execution_status != 'failed'` predicate is forbidden.
- `finalize_verification_publication` must select execution status in its first
  snapshot and require the same exact completed-state set in both the repair
  update and the new-publication update.
- A failed-state miss must roll back the whole existing transaction; it must
  not repair a snapshot, toggle current flags, or increment `state_version`.

Do not import the new projection model into these repositories and do not
write the cause table from them.

- [ ] **Step 4: Run GREEN and combined repository checks**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_review_repository.py \
  tests/unit/test_publication_repository.py \
  tests/unit/test_publication_migrations.py \
  tests/unit/test_run_repository.py -q
```

Expected: all tests pass and a frozen failed run's version remains equal to its
observed cause version.

- [ ] **Step 5: Commit Task 4**

```bash
git add api/review_repository.py api/publication_repository.py \
  tests/unit/test_review_repository.py \
  tests/unit/test_publication_repository.py \
  tests/unit/test_publication_migrations.py
git commit -m "fix(api): fence failed run authority mutations"
```

---

### Task 5: Make Timeout And Cancellation Cleanup Ordered

**Files:**

- Modify: `api/task_tracker.py`
- Modify: `tests/unit/test_task_tracker.py`
- Modify: `tests/unit/test_task_tracker_timeout.py`

**Interfaces:**

- Produces: monotonic termination ownership, mutually exclusive timeout/cancel
  callbacks, and a reusable shield-and-settle primitive for started tasks.
- Does not own database or failure-cause policy.

- [ ] **Step 1: Write deterministic tracker RED tests**

Use `asyncio.Event` barriers rather than sleeps. Cover:

```text
normal completion invokes neither callback
timeout claims origin before inner cancellation and invokes timeout once
external cancellation invokes cancel once and re-raises CancelledError
inner coroutine self-cancellation does not become app cancellation
timeout and external cancellation race has one winning origin/callback
inner completion and deadline ready with no outer cancel deterministically choose inner
target self-cancel and outer cancel in one turn preserve outer cancellation
finalization checkpoint expired while event loop was synchronously blocked claims timeout
live finalization checkpoint is released exactly once
second cancellation while callback runs waits for callback settlement
ordinary callback failure is logged and bounded
sync, async, and sync-raising callbacks all use the same settlement boundary
active_tasks entry is removed after every terminal path
deadline task is cancelled, awaited, and removed after every terminal path
checkpoint waiter is cancelled, awaited, and removed after every terminal path
settle_shielded_task returns result or ordinary exception after cancellation
settle_shielded_task reports but does not propagate outer cancellation
target self-cancel is returned as target exception without claiming app cancel
caller propagates remembered outer cancellation only after settlement/classification
```

- [ ] **Step 2: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_task_tracker.py \
  tests/unit/test_task_tracker_timeout.py -q
```

Expected: the current `asyncio.wait_for` wrapper cannot distinguish the races
or invoke an application cancellation callback.

- [ ] **Step 3: Add the termination contracts**

Add the exact public-within-application surface:

Add `TerminationKind = Literal["unset", "timeout", "cancelled"]` and
`CancelCallback = Callable[[str], Awaitable[Any] | Any]`. Add these exact
interfaces:

```text
TerminationOrigin.claim_timeout() -> bool
TerminationOrigin.claim_cancelled() -> bool
TerminationOrigin.value -> TerminationKind
FinalizationCheckpoint.request_and_wait() -> None
FinalizationCheckpoint.wait_requested() -> None
FinalizationCheckpoint.release() -> None
settle_shielded_task(task: asyncio.Task) ->
    tuple[Any, BaseException | None, int]
```

The method bodies are intentionally small, application-owned state handling:
each claim changes only `unset` to its value; `value` is read-only. The one-shot
checkpoint sets a request event, holds the inner task until the tracker releases
it, and rejects duplicate request/release misuse. The helper captures
`asyncio.current_task()` and repeatedly awaits `asyncio.shield(task)` until the
target is done. It records the maximum owning-task `Task.cancelling()` request
count before and after every await. The helper returns
`(result, target_exception, outer_cancellation_requests)`, never abandons the
target, and never re-raises the outer cancellation itself. `task.done()` alone
is not cancellation evidence. Each caller first classifies the settled target
result, then re-raises when the returned request count is nonzero.

Extend `create_tracked_task` with:

```python
def create_tracked_task(
    coroutine,
    task_id: str,
    timeout_seconds: int = DEFAULT_TASK_TIMEOUT,
    on_timeout: TimeoutCallback | None = None,
    on_cancel: CancelCallback | None = None,
    termination_origin: TerminationOrigin | None = None,
    finalization_checkpoint: FinalizationCheckpoint | None = None,
) -> asyncio.Task:
```

Add a private async `_invoke_callback(callback, *args)` wrapper. Its task calls
the callback inside the wrapper, uses `inspect.isawaitable` to await only an
awaitable result, and therefore handles synchronous returns, asynchronous
callbacks, and synchronous raises uniformly. Create a task from this async
wrapper, then pass that task to `settle_shielded_task`; never call a potentially
synchronous callback before `create_task`.

Replace `wait_for` with an explicit inner task, an explicit deadline task from
`asyncio.sleep(timeout_seconds)`, and, when supplied, a task waiting for the
checkpoint request. The tracker precomputes
`deadline_at = loop.time() + timeout_seconds`. Store all live control tasks in
`control_tasks` and await them with
`asyncio.wait(control_tasks, return_when=asyncio.FIRST_COMPLETED)` without using set
iteration order for classification. Before choosing inner completion, inspect
the wrapper's `Task.cancelling()` count; any external request claims
`cancelled`, even when the inner self-cancelled in the same turn. Otherwise,
inner completion wins a same-turn deadline tie.

When the checkpoint request wins, compare `loop.time()` to `deadline_at` even
if the deadline task has not yet been scheduled. An expired deadline claims
`timeout` and cancels the held inner task. A live request releases the
checkpoint once and resumes waiting. On a deadline win, claim `timeout`, cancel
and settle the inner task, then create the timeout callback as its own task and
shield it to settlement. On outer cancellation, claim `cancelled`, cancel and
settle the inner task, then create and settle the cancellation callback before
re-raising the outer `CancelledError`. A second outer cancellation increments
the remembered request count, but cannot skip callback settlement or change the
winning origin. In `finally`, cancel, await, and observe the deadline and
checkpoint-waiter tasks on every path.

Callbacks are mutually exclusive and invoked at most once. Ordinary callback
exceptions are logged with a fixed message and do not replace the original
timeout/cancellation semantic. If timeout won and an outer cancellation arrives
during the timeout callback, settle that callback, do not invoke `on_cancel`,
then re-raise the remembered cancellation instead of returning `None`.

- [ ] **Step 4: Run GREEN repeatedly**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_task_tracker.py \
  tests/unit/test_task_tracker_timeout.py -q
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_task_tracker.py \
  tests/unit/test_task_tracker_timeout.py -q
```

Expected: both runs pass without timing-sensitive retries or leaked active
tasks.

- [ ] **Step 5: Commit Task 5**

```bash
git add api/task_tracker.py tests/unit/test_task_tracker.py \
  tests/unit/test_task_tracker_timeout.py
git commit -m "fix(api): order timeout and cancellation cleanup"
```

---

### Task 6: Persist Dispatch Terminal Causes And Cancellation Reconciliation

**Files:**

- Modify: `api/run_dispatch_repository.py`
- Modify: `api/run_dispatch_worker.py` only if an existing worker call site
  needs the new return literal
- Modify: `tests/unit/test_run_dispatch_repository.py`
- Modify: `tests/unit/test_run_dispatch_worker.py` only if the worker changes
- Modify: `tests/integration/test_run_dispatch_api.py`

**Interfaces:**

- Consumes: Task 1 write model and Task 2 table.
- Produces: exact-attempt dispatch causes and a separate cancellation
  reconciliation result.

- [ ] **Step 1: Write dispatch RED tests**

Add exact cases:

```text
attempt 1 and 2 schedule/start failures release for retry with no cause row
attempt 3 schedule failure atomically writes run_dispatch_schedule_failed
attempt 3 start failure atomically writes run_dispatch_start_failed
attempt 3 pre-start timeout atomically writes run_dispatch_start_timeout
attempt 3 expired lease atomically writes run_dispatch_lease_expired
every terminal dispatch cause shares one timestamp with run and segment
attempt 3 pre-start cancellation remains leased and returns deferred
expired deferred attempt converges to lease_expired
started timeout/cancellation returns started without dispatch cause
stale or newer attempt is a no-op with no cause
cause insert failure rolls back dispatch, run, and segment changes
no path creates attempt 4
non-targeted scanning continues after terminalizing an exhausted row
```

- [ ] **Step 2: Run RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_run_dispatch_repository.py \
  tests/unit/test_run_dispatch_worker.py \
  tests/integration/test_run_dispatch_api.py -q
```

Expected: terminal dispatch paths do not write the new row and no cancellation
reconciler exists.

- [ ] **Step 3: Type and atomically write terminal dispatch causes**

Change `_terminalize_leased_dispatch` to receive a validated
`RunFailureCauseWrite` whose phase is `dispatch`. After the exact dispatch,
run, and segment updates all report one row, insert the observed cause with
`terminal_state_version = 1` and the same repository-owned UTC timestamp used
for dispatch, run, and segment updates. Any failed update or insert rolls back
the whole caller transaction.

Map only the existing bounded third-attempt codes:

```text
run_dispatch_schedule_failed -> run_dispatch_schedule_failed
run_dispatch_start_failed -> run_dispatch_start_failed
run_dispatch_start_timeout -> run_dispatch_start_timeout
expired third lease -> run_dispatch_lease_expired
```

Private retry bookkeeping may retain its existing bounded `last_error_code`;
it is not the public cause and does not create a cause row before terminal
failure.

Change timeout reconciliation to return exactly:

```python
Literal["retry", "failed", "started", "stale"]
```

Attempts 1 and 2 release to pending and return `retry`; the exact third leased
attempt terminalizes and returns `failed`; a real start fence returns
`started`; any mismatched attempt returns `stale`.

- [ ] **Step 4: Add separate cancellation reconciliation**

Add:

```python
def reconcile_run_dispatch_cancellation(
    *,
    db_path: str | None,
    claim: RunDispatchClaim,
) -> Literal["retry", "deferred", "started", "stale"]:
```

For exact leased attempts 1 and 2, release to pending with private
`last_error_code = 'run_dispatch_interrupted'` and return `retry`. For the
exact third leased attempt, leave the lease unchanged and return `deferred`;
the existing lease-expiry scanner later performs the public
`run_dispatch_lease_expired` terminal transition. A started exact attempt
returns `started`; unrelated or newer attempts return `stale`.

Do not persist public `cancelled` before the application-owned start fence and
do not synthesize a provider result.

- [ ] **Step 5: Run GREEN repeatedly**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_run_dispatch_repository.py \
  tests/unit/test_run_dispatch_worker.py \
  tests/integration/test_run_dispatch_api.py -q
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_run_dispatch_repository.py \
  tests/unit/test_run_dispatch_worker.py \
  tests/integration/test_run_dispatch_api.py -q
```

Expected: both runs pass; no attempt exceeds three and every terminal dispatch
failure has one observed cause.

- [ ] **Step 6: Commit Task 6**

```bash
git add api/run_dispatch_repository.py tests/unit/test_run_dispatch_repository.py \
  tests/integration/test_run_dispatch_api.py api/run_dispatch_worker.py \
  tests/unit/test_run_dispatch_worker.py
git commit -m "feat(api): reconcile dispatch failure causes"
```

---

### Task 7: Integrate Stage-Aware Failure Ownership In The API Runtime

**Files:**

- Modify: `api/server.py`
- Modify: `tests/unit/test_deepagents_harness.py`
- Modify: `tests/integration/test_harness_execution.py`
- Modify: `tests/integration/test_evidence_lifecycle.py`
- Modify: `tests/integration/test_run_api.py`
- Modify: `tests/integration/test_run_dispatch_api.py`
- Modify: `tests/integration/test_run_result_api.py`
- Modify: `tests/integration/test_run_auxiliary_isolation.py` if its status
  snapshot assertion needs the additive field

**Interfaces:**

- Consumes: Tasks 1, 3, 5, and 6.
- Produces: one bounded mapper, one application stage/origin owner, settled
  start and terminal database tasks, and a bounded corrupt-status response.
- Leaves `api/research_execution_service.py` and
  `agent/deepagents_harness.py` unchanged unless a failing production-path test
  proves an adapter defect; native framework signals already enter through
  those ports.

- [ ] **Step 1: Write mapper and native-signal RED tests**

Exercise the production harness/service/server chain, not a duplicate test
mapper. Use the installed native exception classes for the first two cases:

```text
ModelCallLimitExceededError -> execution/call_budget_exceeded
ToolCallLimitExceededError -> execution/call_budget_exceeded
GraphRecursionError -> execution/recursion_limit_exceeded
invalid packet resolution -> execution/invalid_research_packet
missing packet resolution -> execution/missing_research_packet
unknown harness value -> execution/execution_error
harness run_timeout string -> execution/execution_error
harness cancelled string -> execution/execution_error
ordinary exception text/path/credential -> execution/execution_error only
```

The application mapper is exact:

```python
_DIRECT_EXECUTION_FAILURES = frozenset(
    {
        "call_budget_exceeded",
        "recursion_limit_exceeded",
        "invalid_research_packet",
        "missing_research_packet",
    }
)


def _execution_failure_cause(failure_kind: str | None) -> RunFailureCauseWrite:
    code = (
        failure_kind
        if failure_kind in _DIRECT_EXECUTION_FAILURES
        else "execution_error"
    )
    return RunFailureCauseWrite(phase="execution", code=code)
```

- [ ] **Step 2: Write deterministic execution/race RED tests**

Use events around the start thread, outcome publication, artifact construction,
the cooperative finalization checkpoint, terminal thread, and callbacks. Drive
timeout/cancel cases through `create_tracked_task`; do not make them pass by
directly assigning stage or origin. Cover every authoritative interleaving:

```text
execution outcome failure writes its mapped execution cause
ordinary execution exception writes execution_error with partial Evidence
post-start inner self-cancel with unset origin writes execution_error and re-raises
artifact/review construction failure writes run_finalization_failed
first terminal transaction rollback permits finalization fallback
first terminal transaction commit wins over a later timeout/cancel
first terminal transaction stale result creates no fallback cause
timeout before terminal launch writes execution/run_timeout
timeout after outcome before terminal launch writes finalization/run_timeout
cancel before terminal launch writes execution/cancelled and re-raises
cancel after outcome before terminal launch writes finalization/cancelled and re-raises
real tracker reaches finalization timeout/cancel through checkpoint handshake
deadline expiry during synchronous materialization cannot launch success terminal
timeout versus explicit cancel has one monotonic origin and one cause
cancel while start_run_dispatch thread is live waits for its result
late committed start uses post-start cancellation semantics
pre-start attempts 1/2 cancel release for retry without public cause
pre-start attempt 3 cancel defers to lease expiry without public cancelled
stale timeout/cancel callback cannot replace a newer terminal winner
callback cancellation waits for its reconciliation thread to settle
status OpenAPI documents nullable observed/not_observed cause without filtering
result OpenAPI operation remains free of failure_cause
```

For every case assert run, segment, Evidence, artifact/review rows, cause,
`state_version`, dispatch attempt, and task cleanup. Do not assert only emitted
monitor events.

- [ ] **Step 3: Run combined RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_deepagents_harness.py \
  tests/integration/test_harness_execution.py \
  tests/integration/test_evidence_lifecycle.py \
  tests/integration/test_run_api.py \
  tests/integration/test_run_dispatch_api.py \
  tests/integration/test_run_result_api.py -q
```

Expected: typed finalizer calls, cancellation callback ownership, stage
distinction, and settled database-task behavior are not yet integrated.

- [ ] **Step 4: Add one monotonic stage holder and mapper**

Keep the stage private to `api/server.py` with exact values
`dispatch|execution|finalization`. It starts at `dispatch`, advances to
`execution` only after the exact start transaction returns `True`, advances to
`finalization` immediately after `run_deep_agent` returns an outcome, and never
moves backward.

Share the same stage holder, `TerminationOrigin`, `FinalizationCheckpoint`,
`OutcomeBox`, and dispatch claim between `_schedule_run_dispatch`,
`_run_dispatched_with_persistence`, `_run_started_v2_with_persistence`, and both
tracker callbacks. Do not derive stage or origin from exception text or
`OutcomeBox.failure_kind`.

When a normal outcome reports failure, map it through
`_execution_failure_cause`. When artifact/review construction or the first
terminal attempt raises after an outcome exists, use
`finalization/run_finalization_failed`. A caught `CancelledError` may write
`cancelled` only when the shared origin is `cancelled`; tracker timeout may
write `run_timeout` only when the origin is `timeout`. With origin still
`unset`, treat a post-start inner self-cancellation as
`execution/execution_error` or, after stage advancement,
`finalization/run_finalization_failed`; persist it before re-raising and do not
claim the origin or invoke a tracker callback.

After synchronous artifact/review materialization and before constructing the
terminal database task, call
`await finalization_checkpoint.request_and_wait()`, then re-read the origin.
The tracker owns release: it checks the precomputed monotonic deadline and its
own `Task.cancelling()` count when the request arrives. If timeout or
cancellation wins, it cancels the held inner task instead of releasing the
success path. Only a live request is released once. This handshake is the
production scheduling point that makes finalization timeout/cancel observable;
do not replace it with `asyncio.sleep(0)`, repeated yields, or a test-only hook.

- [ ] **Step 5: Shield start and terminal database tasks to settlement**

For every start or terminal `asyncio.to_thread` call whose late commit can race
termination:

1. create it as an explicit `asyncio.Task`;
2. await it through `settle_shielded_task`;
3. classify the settled result before any fallback;
4. re-propagate a nonzero outer cancellation-request count only after
   classification.

The classification is exact:

```text
result True  -> transaction committed; it is the winner
result False -> stale/losing compare-and-set; do not add a cause
exception    -> transaction rolled back or was unavailable; a bounded fallback
               may run if the current stage/origin has a valid cause
```

Before launching a success terminal transaction, inspect the origin. If it is
already `timeout` or `cancelled`, launch only the corresponding typed failure
transaction. Once any terminal transaction task has launched, settle it before
launching another.

Extend `_finalize_failed_run_v2` to require a `RunFailureCauseWrite`; it remains
best effort only in the sense that it returns a bounded boolean. It must never
omit the cause or swallow a live database thread.

- [ ] **Step 6: Connect timeout and cancellation callbacks**

`_schedule_run_dispatch` creates the one-shot checkpoint and passes it, both
callbacks, and the shared origin into `create_tracked_task`; the same checkpoint
is passed to the inner server wrapper.

The timeout callback first calls `reconcile_run_dispatch_timeout`:

- `retry|failed|stale`: no post-start fallback;
- `started`: read the current run and attempt the stage-appropriate
  `run_timeout` finalizer only if still pending/running.

The cancellation callback first calls
`reconcile_run_dispatch_cancellation`:

- `retry|deferred|stale`: no public cancellation cause;
- `started`: read the current run and attempt the stage-appropriate
  `cancelled` finalizer only if still pending/running.

These callbacks are fallback reconciliation. The inner wrapper gets the first
opportunity to settle its start/terminal task and freeze partial Evidence. All
paths use the same state-version fence, so a callback cannot replace a winner.

- [ ] **Step 7: Bound corrupt status responses and preserve result bytes**

Attach `RunStatusFailureCauseOpenAPI` only as the status route's `200` response
documentation metadata:

```python
@app.get(
    "/api/runs/{run_id}",
    responses={
        200: {
            "model": RunStatusFailureCauseOpenAPI,
            "description": "ResearchRun status with additive failure cause",
        }
    },
)
```

Do not use it as `response_model`, because that would filter the existing raw
status fields. In `test_run_api.py`, inspect `app.openapi()` and require the
nullable observed/not-observed union, exact bounded fields, and absence of
`terminal_state_version`. Assert the `/result` operation contains no
`failure_cause` reference and otherwise retains its existing schema.

Catch only `RunFailureCauseConflict` around the status repository call and
return this fixed response:

```python
JSONResponse(
    status_code=500,
    content={"detail": "ResearchRun state is unavailable"},
)
```

Do not include the conflict code, SQLite content, or cause row. Do not add this
catch or any cause field to `GET /api/runs/{run_id}/result`.

Test both detection points: one request lets marker-present
`init_run_schema` detect a corrupt row; another isolates the joined projector
after a successful init and then mutates the target row. Both must return the
same fixed `500` body.

- [ ] **Step 8: Run integration GREEN and race repetitions**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_task_tracker.py \
  tests/unit/test_task_tracker_timeout.py \
  tests/unit/test_run_repository.py \
  tests/unit/test_run_dispatch_repository.py \
  tests/unit/test_deepagents_harness.py \
  tests/integration/test_harness_execution.py \
  tests/integration/test_evidence_lifecycle.py \
  tests/integration/test_run_api.py \
  tests/integration/test_run_dispatch_api.py \
  tests/integration/test_run_result_api.py \
  tests/integration/test_run_auxiliary_isolation.py -q
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_task_tracker.py \
  tests/unit/test_task_tracker_timeout.py \
  tests/integration/test_run_api.py \
  tests/integration/test_run_dispatch_api.py -q
```

Expected: both runs pass with no leaked task warning, no unobserved thread
exception, and exactly one terminal cause per failed run.

- [ ] **Step 9: Commit Task 7**

```bash
git add api/server.py tests/unit/test_deepagents_harness.py \
  tests/integration/test_harness_execution.py \
  tests/integration/test_evidence_lifecycle.py \
  tests/integration/test_run_api.py \
  tests/integration/test_run_dispatch_api.py \
  tests/integration/test_run_result_api.py \
  tests/integration/test_run_auxiliary_isolation.py
git commit -m "feat(api): finalize durable run failure causes"
```

---

### Task 8: Add A Deterministic Production-Path Regression Proof

**Files:**

- Create: `scripts/run_failure_cause_proof.py`
- Create: `tests/integration/test_run_failure_cause_proof.py`
- Create: `docs/evidence/run-failure-cause-v1.json`
- Create: `docs/evidence/run-failure-cause-v1.md`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**

- Consumes: production migration, dispatch, tracker, service, terminal writer,
  and status projection.
- Produces: strict `dra.run-failure-cause-proof.v1` evidence independent of the
  frozen downstream v1 fixture.

- [ ] **Step 1: Write proof contract and mutation RED tests**

The test imports the proof module silently and asserts fixed ordering for all
16 cases:

```text
01 completed_null
02 historical_not_observed
03 dispatch_schedule_failed
04 dispatch_start_failed
05 dispatch_start_timeout
06 dispatch_lease_expired
07 execution_call_budget_exceeded
08 execution_recursion_limit_exceeded
09 execution_invalid_research_packet
10 execution_missing_research_packet
11 execution_timeout
12 finalization_timeout
13 execution_cancelled
14 finalization_cancelled
15 execution_error
16 finalization_failed
```

Require exact top-level fields, case fields, observation keys/types, boundaries,
limits, source identity, schema, status, and ordered invariant observations.
Add fail-closed mutations that independently break:

```text
production failure mapper
dispatch terminal cause insert
atomic terminal cause insert
joined status projection
production scheduler timeout/cancel callback wiring
tracked-task construction
shield-and-settle helper
finalization checkpoint request/release handshake
timeout-before-cancel origin ordering
```

Each mutation must make `check` fail even if the report builder and validator
remain unchanged.

Add CLI/baseline tests for missing/extra arguments, `--help`, missing/corrupt/
oversized baselines, bounded reads, output-path aliasing, replace/write
failure, cleanup, import silence, stable stderr JSON, and public-safety scans.
Add a clock-boundary test that removes each required patch alias independently
and proves the report no longer matches; this prevents dispatch timestamps from
silently returning to wall-clock time.

- [ ] **Step 2: Run proof RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_run_failure_cause_proof.py -q
```

Expected: collection fails because `scripts.run_failure_cause_proof` does not
exist.

- [ ] **Step 3: Implement the fixed production-path proof**

Follow the bounded CLI shape of the existing idempotency and dispatch proofs:

```text
build --json-output PATH --markdown-output PATH
check [--json-baseline PATH] [--markdown-baseline PATH]
--help
```

Invalid or missing CLI input returns exit `1`, empty stdout, and one stable
single-line JSON error on stderr. Help returns exit `0`. Baseline reads are
size-bounded before decode; writes validate both target paths before writing,
use sibling temporary files, replace atomically, and clean up on failure.

Use `FIXED_TIME = "2026-07-16T00:00:00+00:00"` and patch both
`api.run_repository._now` and the separately imported
`api.run_dispatch_repository._now` alias. Also patch any publication/server
time boundary that the final implemented case matrix actually serializes;
otherwise keep those production paths out of proof output. Audit all serialized
timestamps before accepting the baseline. Production defaults remain unchanged.
Use a deterministic fake harness only for non-framework Agent outcomes at the
existing harness port. The call-limit and recursion cases use the real
`DeepAgentsHarness.execute` with only its graph replaced by a fake that raises
the installed `ModelCallLimitExceededError`, `ToolCallLimitExceededError`, or
`GraphRecursionError`. Timeout and cancellation cases enter through
`RunDispatchWorker`, `_schedule_run_dispatch`, and `create_tracked_task`, then
obtain and await the real task from `get_active_task`; direct invocation of the
mapper or callback does not satisfy the proof. Every case must call the
production migration/repository/tracker/dispatch/service/server path that owns
its semantic; direct SQL is permitted only for the explicit pre-009 historical
seed and deliberate corruption observations.

Add an invariant observation that a real post-start inner self-cancellation
with unset origin persists bounded `execution_error`, re-raises cancellation,
invokes neither callback, and leaves no `running` run.

For each case validate persisted rows and the public status projection. For
the restart observation, close all connections, reconstruct application-owned
repositories against the same database, and compare the projection exactly.
Scan the failure-cause table columns, the public `failure_cause` projection,
JSON, and Markdown for raw exception markers, tracebacks, credentials, provider
payloads, private hosts, absolute paths, and synthetic query text. The existing
run query field is outside this additive privacy assertion.

- [ ] **Step 4: Generate baselines, then run GREEN twice**

```bash
PYTHON_DOTENV_DISABLED=1 python \
  scripts/run_failure_cause_proof.py build \
  --json-output docs/evidence/run-failure-cause-v1.json \
  --markdown-output docs/evidence/run-failure-cause-v1.md
PYTHON_DOTENV_DISABLED=1 python \
  scripts/run_failure_cause_proof.py check
PYTHON_DOTENV_DISABLED=1 python \
  scripts/run_failure_cause_proof.py check
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_run_failure_cause_proof.py -q
```

Expected: both checks report `status=valid` and `match=true`; independent JSON
and Markdown outputs are byte-identical to the committed files.

- [ ] **Step 5: Add the required CI gate**

Insert after `Run dispatch reconciliation proof` and before broad pytest:

```yaml
      - name: Run failure cause proof
        run: python scripts/run_failure_cause_proof.py check
```

Do not add a credential, service container, provider call, network step, or
dependency.

- [ ] **Step 6: Run the proof plus legacy gates**

```bash
PYTHON_DOTENV_DISABLED=1 python \
  scripts/run_failure_cause_proof.py check
PYTHON_DOTENV_DISABLED=1 python \
  scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 python \
  scripts/run_dispatch_reconciliation_proof.py check
PYTHON_DOTENV_DISABLED=1 python \
  scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 python \
  scripts/downstream_consumer_contract.py check \
  --input docs/evidence/downstream-consumer-contract-v1.json
```

Expected: the new proof matches and every existing gate remains green without
baseline drift.

- [ ] **Step 7: Commit Task 8**

```bash
git add scripts/run_failure_cause_proof.py \
  tests/integration/test_run_failure_cause_proof.py \
  docs/evidence/run-failure-cause-v1.json \
  docs/evidence/run-failure-cause-v1.md .github/workflows/ci.yml
git commit -m "test(api): prove durable run failure causes"
```

---

### Task 9: Publish The Contract And Run Final Verification

**Files:**

- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/README.md`
- Modify: `docs/evidence/README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/decisions/framework-runtime-boundaries.md`
- Modify: `docs/reference/api-contract.md`
- Modify: `docs/reference/data-models.md`
- Modify: `docs/reference/state-machines.md`
- Modify: `docs/reference/downstream-consumer-contract.md`
- Modify: `docs/AGENT_INTEGRATION.md`
- Modify: `tests/unit/test_documentation_contracts.py`

**Interfaces:**

- Produces: public discovery, authority/compatibility guidance, rollback
  instructions, and complete verification evidence.
- Does not create release notes or change the release version.

- [ ] **Step 1: Write documentation contract RED tests**

Require all of these facts in stable public locations:

```text
status endpoint additive field and three projection variants
exact schema, phase/code matrix, and migration/table names
application database owns terminal cause; framework/trace/checkpoint do not
historical not_observed is not an inferred diagnosis
result endpoint and downstream v1 fixture remain unchanged
timeout/cancel distinction and cooperative deadline boundary
attempts 1/2 are retry diagnostics; terminal exact dispatch attempt is public
rollback restores the dedicated pre-run-failure-cause backup
not exactly-once execution, not hard preemption, not provider diagnosis,
not multi-instance HA, and not a billing record
new proof links are discoverable from docs/evidence indexes
VERSION remains 0.1.3 and no v0.1.4 release note exists
```

- [ ] **Step 2: Run documentation RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_release_metadata.py -q
```

Expected: new reference and evidence discovery assertions fail; existing
release metadata remains green.

- [ ] **Step 3: Update public documentation**

Add one `Unreleased` subsection and concise bilingual README discovery. Update
architecture, API, data, state, framework-boundary, downstream-compatibility,
Agent-integration, docs index, and evidence index pages with the exact approved
contract.

Document migration rollback as an operator action that restores the dedicated
`.pre-run-failure-cause.bak` only after stopping application writers and
preserving the failed database for diagnosis. State that a marker-present
startup verifies and never repairs cause rows.

Do not add a new ADR solely to repeat the spec, do not edit
`docs/releases/v0.1.3.md`, and do not promise a future version.

- [ ] **Step 4: Run focused feature and documentation suites**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_run_failure_cause_models.py \
  tests/unit/test_run_migrations.py \
  tests/unit/test_run_repository.py \
  tests/unit/test_run_dispatch_repository.py \
  tests/unit/test_run_dispatch_worker.py \
  tests/unit/test_task_tracker.py \
  tests/unit/test_task_tracker_timeout.py \
  tests/unit/test_deepagents_harness.py \
  tests/unit/test_review_repository.py \
  tests/unit/test_publication_repository.py \
  tests/unit/test_publication_migrations.py \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_release_metadata.py \
  tests/integration/test_harness_execution.py \
  tests/integration/test_evidence_lifecycle.py \
  tests/integration/test_run_api.py \
  tests/integration/test_run_dispatch_api.py \
  tests/integration/test_run_result_api.py \
  tests/integration/test_run_auxiliary_isolation.py \
  tests/integration/test_run_failure_cause_proof.py \
  tests/integration/test_downstream_consumer_contract.py -q
```

Expected: the complete feature/docs matrix passes.

- [ ] **Step 5: Verify deterministic and compatibility evidence**

```bash
tmp_dir="$(mktemp -d)"
PYTHON_DOTENV_DISABLED=1 python scripts/run_failure_cause_proof.py build \
  --json-output "$tmp_dir/first.json" \
  --markdown-output "$tmp_dir/first.md"
PYTHON_DOTENV_DISABLED=1 python scripts/run_failure_cause_proof.py build \
  --json-output "$tmp_dir/second.json" \
  --markdown-output "$tmp_dir/second.md"
cmp "$tmp_dir/first.json" "$tmp_dir/second.json"
cmp "$tmp_dir/first.md" "$tmp_dir/second.md"
cmp "$tmp_dir/first.json" docs/evidence/run-failure-cause-v1.json
cmp "$tmp_dir/first.md" docs/evidence/run-failure-cause-v1.md
rm -rf "$tmp_dir"
PYTHON_DOTENV_DISABLED=1 python scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_dispatch_reconciliation_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 python scripts/downstream_consumer_contract.py check \
  --input docs/evidence/downstream-consumer-contract-v1.json
PYTHON_DOTENV_DISABLED=1 python scripts/check_canonical_identity.py --root .
PYTHON_DOTENV_DISABLED=1 python scripts/final_presentation_audit.py
```

Expected: byte comparisons and every gate pass. The temporary proof directory
is removed after successful comparisons; if a command fails, remove only that
known temporary directory during final cleanup.

- [ ] **Step 6: Run the declared broad suite**

Use the repository's locked Python 3.11 dependency installation, including
`langgraph-checkpoint-sqlite`, then run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q
```

Expected: the full backend suite passes. If the local environment is not the
locked stack, record the exact collection/import blocker and rely on CI for
the locked proof; never use an import stub to claim the full suite passed.
Frontend tests, lint, and build are required only if a frontend file or
frontend contract changed unexpectedly.

- [ ] **Step 7: Audit scope, authority, and public safety**

```bash
git diff --check origin/main..HEAD
git diff --exit-code origin/main..HEAD -- \
  requirements.txt constraints.txt pyproject.toml VERSION \
  frontend/package.json frontend/package-lock.json
git diff --exit-code origin/main..HEAD -- \
  docs/evidence/downstream-consumer-contract-v1.json
rg -n "langsmith|langgraph|deepagents" \
  api/run_failure_cause_models.py api/run_repository.py \
  api/run_dispatch_repository.py api/task_tracker.py
rg -n "API[_ -]?KEY|Bearer |sk-[A-Za-z0-9]|file://" \
  README.md README_CN.md CHANGELOG.md docs scripts/run_failure_cause_proof.py
```

Expected: diff check passes; dependency/version diff is empty; framework scan
shows no new authority import in failure persistence; public scan reports no
private path, consumer-specific name, credential, or token. Also run a local
private-marker scan without writing its marker set into repository artifacts.
Review any expected documentation word before declaring the scan clean.

- [ ] **Step 8: Commit Task 9**

```bash
git add README.md README_CN.md CHANGELOG.md docs/README.md \
  docs/evidence/README.md docs/architecture.md \
  docs/decisions/framework-runtime-boundaries.md \
  docs/reference/api-contract.md docs/reference/data-models.md \
  docs/reference/state-machines.md \
  docs/reference/downstream-consumer-contract.md \
  docs/AGENT_INTEGRATION.md tests/unit/test_documentation_contracts.py
git commit -m "docs(api): publish durable failure cause contract"
```

- [ ] **Step 9: Final branch handoff**

Confirm the worktree is clean and report ordered commits, changed files,
focused/full verification, proof hashes, legacy gate results, dependency and
authority diffs, and any exact environment limitation. Preserve the local
branch/worktree for authoritative branch-diff review. Do not push, create a PR,
merge, tag, release, deploy, or remove the worktree.
