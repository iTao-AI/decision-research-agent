# Run Creation Idempotency And Lost-Response Reconciliation v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional, durable `Idempotency-Key` contract to `POST /api/runs` so callers can recover the original run identity after a lost response without creating or scheduling a duplicate run.

**Architecture:** FastAPI validates the optional header and maps stable errors. A typed request fingerprint and a run-specific SQLite ledger bind one key hash to one canonical request and run identity inside the same `BEGIN IMMEDIATE` transaction that creates the run and initial segment. Replays return the persisted identity and do not construct a second coroutine; DeepAgents, LangGraph, and LangSmith retain their current runtime and diagnostic roles.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLite/WAL, pytest, standard-library `hashlib`, `json`, `uuid`, `urllib`, and `concurrent.futures`.

## Global Constraints

- Implement only the approved spec at `docs/superpowers/specs/2026-07-13-run-creation-idempotency-design.md`.
- Preserve the existing `create_run` signature and `dict` return, and preserve every unkeyed `POST /api/runs` response exactly; unkeyed requests must not gain `idempotent_replay`.
- A valid key is 8-128 ASCII characters matching `[A-Za-z0-9][A-Za-z0-9._:-]{7,127}`.
- Persist only the namespaced SHA-256 key hash, never the raw key.
- The canonical request hash includes schema version, query, caller-supplied nullable thread ID, profile ID, and validated/normalized scope; it excludes server-generated identities and `profile_version`.
- Same key/same request returns the original identity with `idempotent_replay=true`; same key/different request returns stable `409 run_idempotency_conflict` without identity disclosure.
- A supplied key must fail closed with `503 run_idempotency_unavailable` if its ledger cannot be read or written; never fall back to unkeyed creation.
- Replays never construct or schedule another research coroutine.
- Do not add outbox, worker, queue, lease, fencing, execution recovery, TTL, multi-tenant/RBAC scope, automatic retry, provider calls, frontend changes, new endpoint, or dependency changes.
- Lost-response proof starts after database creation and current-process scheduling have completed. It does not prove execution after handler/process interruption between commit and scheduling.
- The application database remains business authority. Framework checkpoints and traces do not own request idempotency.
- Public output must remain credential-free, provider-free, network-free, path-free, and free of private consumer or career context.
- Use `PYTHON_DOTENV_DISABLED=1` for Python validation commands.
- Do not bump a version, tag, publish, push, create a PR, merge, or deploy as part of implementation.

## Planned File Map

| File | Responsibility |
|---|---|
| `api/run_creation_models.py` | Strict key validation, canonical request hashing, key hashing, and typed acceptance |
| `api/run_repository.py` | Additive ledger schema, shared run/segment insertion, atomic create/replay/conflict |
| `api/run_migrations.py` | `007` verification and backup-aware upgrade from an already-published `006` database |
| `api/server.py` | Optional header, stable errors, keyed/unkeyed routing, replay scheduling fence |
| `tools/decision_research_agent_tool.py` | Header forwarding, CLI key generation/preservation, ambiguous-failure recovery context |
| `scripts/run_creation_idempotency_proof.py` | Deterministic production-path proof and JSON/Markdown check command |
| `.github/workflows/ci.yml` | Required proof check before the full backend suite |
| `tests/unit/test_run_creation_models.py` | Validation and canonical hash contract |
| `tests/unit/test_run_repository.py` | Atomic replay/conflict/race/corruption behavior |
| `tests/unit/test_run_migrations.py` | Additive marker/schema/FK/backup/restore behavior |
| `tests/integration/test_run_api.py` | Public API, scheduling, response-loss, and error envelopes |
| `tests/unit/test_decision_research_agent_tool.py` | CLI/client request and recovery semantics |
| `tests/integration/test_run_creation_idempotency_proof.py` | Proof determinism, baseline check, CLI failure boundaries |
| `docs/evidence/run-creation-idempotency-v1.json` | Committed deterministic machine-readable proof |
| `docs/evidence/run-creation-idempotency-v1.md` | Committed deterministic human-readable proof |
| Public reference/docs files listed in Task 6 | API, migration, Tool Client, architecture, evidence, and release-facing boundaries |

## What Already Exists

- `POST /api/runs` already validates the selected profile and scope, creates one durable run plus its initial segment, and then schedules the research coroutine in the current process.
- `create_run` intentionally permits independent runs with the same thread and payload; this remains the unkeyed contract.
- The application database already owns run, Evidence, review, verification, publication, and canonical-result facts. Existing review and Evidence paths demonstrate canonical request hashing plus `BEGIN IMMEDIATE` replay/conflict transactions.
- DeepAgents and LangGraph own research execution and resumable graph state; LangSmith owns diagnostics. None currently owns request idempotency.
- The Tool Client already has bounded JSON error handling, wait/status/result flows, and canonical-result output that must remain compatible.
- CI already runs deterministic downstream-consumer and Agent-evaluation checks. This work adds one focused proof without reusing either fixture as a second authority.

## NOT in Scope

- Transactional outbox, durable scheduler, queue, worker, lease, or crash-before-schedule recovery.
- Exactly-once execution, automatic client retry, key expiry/TTL, key deletion, tenant or actor scoping, RBAC, or anonymous access.
- A new endpoint, a second canonical result, changes to Evidence/review/publication authority, or changes to DeepAgents/LangGraph/LangSmith roles.
- Provider-backed proof, cost measurement, frontend work, profile changes, dependency changes, version bump, release, or deployment.

## Request And Persistence Flow

```text
caller
  |
  | POST /api/runs [optional Idempotency-Key]
  v
FastAPI profile/scope validation
  |
  +-- no key --> existing create_run transaction --> schedule once --> old response
  |
  +-- key --> strict key + canonical request hash
               |
               v
          BEGIN IMMEDIATE
               |
               +-- unused key --> insert run + segment + ledger --> commit
               |
               +-- same hash --> load original identity ----------> replay
               |
               +-- different hash -------------------------------> 409
               |
               +-- corrupt/unavailable ledger -------------------> 503
                           |
                           v
              first acceptance schedules once; replay returns early
```

---

### Task 1: Define Typed Key And Canonical Request Contracts

**Files:**
- Create: `api/run_creation_models.py`
- Create: `tests/unit/test_run_creation_models.py`

**Interfaces:**
- Produces: `RUN_CREATE_REQUEST_SCHEMA_VERSION`, `RUN_CREATE_IDEMPOTENCY_MIGRATION_VERSION`, `RUN_CREATE_IDEMPOTENCY_MIGRATION_CHECKSUM`, `validate_idempotency_key(value: str) -> str`, `idempotency_key_hash(value: str) -> str`, the keyword-only `run_create_request_hash` function, and `RunCreationAcceptance`.
- Consumes: Pydantic v2 already declared by the repository; no new dependency.

- [ ] **Step 1: Write failing strict validation and hashing tests**

Create `tests/unit/test_run_creation_models.py` with the following cases:

```python
import pytest

from api.run_creation_models import (
    RUN_CREATE_REQUEST_SCHEMA_VERSION,
    RunCreationAcceptance,
    idempotency_key_hash,
    run_create_request_hash,
    validate_idempotency_key,
)


@pytest.mark.parametrize(
    "value",
    [
        "12345678",
        "run-create-12345678",
        "A.b_c:d-12345678",
        "a" * 128,
    ],
)
def test_idempotency_key_accepts_exact_public_contract(value):
    assert validate_idempotency_key(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "1234567",
        "a" * 129,
        " leading-key",
        "trailing-key ",
        "line\nbreak",
        "trailing-newline\n",
        "control\x00key",
        "unicode-key-测试",
        "slash/key",
    ],
)
def test_idempotency_key_rejects_out_of_contract_values(value):
    with pytest.raises(ValueError, match="run_idempotency_key_invalid"):
        validate_idempotency_key(value)


def test_key_hash_is_namespaced_stable_and_does_not_contain_raw_key():
    raw = "run-create-12345678"
    first = idempotency_key_hash(raw)
    second = idempotency_key_hash(raw)
    assert first == second
    assert len(first) == 64
    assert raw not in first
    assert first != idempotency_key_hash("run-create-87654321")


def test_request_hash_is_canonical_for_scope_key_order():
    first = run_create_request_hash(
        query="bounded query",
        thread_id=None,
        profile_id="generic",
        scope={"b": 2, "a": {"d": 4, "c": 3}},
    )
    second = run_create_request_hash(
        query="bounded query",
        thread_id=None,
        profile_id="generic",
        scope={"a": {"c": 3, "d": 4}, "b": 2},
    )
    assert first == second


def test_request_hash_preserves_caller_thread_intent_and_request_content():
    base = dict(query="query", profile_id="generic", scope={})
    omitted = run_create_request_hash(thread_id=None, **base)
    explicit = run_create_request_hash(thread_id="thread-1", **base)
    changed_query = run_create_request_hash(
        thread_id=None,
        query="query ",
        profile_id="generic",
        scope={},
    )
    assert omitted != explicit
    assert omitted != changed_query


def test_acceptance_is_strict_and_json_serializable():
    value = RunCreationAcceptance(
        run_id="run_1",
        thread_id="thread_1",
        segment_id="run_1_seg_000",
        idempotent_replay=False,
    )
    assert value.model_dump(mode="json") == {
        "run_id": "run_1",
        "thread_id": "thread_1",
        "segment_id": "run_1_seg_000",
        "idempotent_replay": False,
    }
    assert RUN_CREATE_REQUEST_SCHEMA_VERSION == "dra.run-create-request.v1"
```

- [ ] **Step 2: Run the tests to prove RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q tests/unit/test_run_creation_models.py
```

Expected: collection fails with `ModuleNotFoundError: No module named 'api.run_creation_models'`.

- [ ] **Step 3: Implement the complete typed contract**

Create `api/run_creation_models.py`:

```python
"""Typed contracts for durable run-creation idempotency."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, TypeAdapter, ValidationError


RUN_CREATE_REQUEST_SCHEMA_VERSION = "dra.run-create-request.v1"
RUN_CREATE_IDEMPOTENCY_MIGRATION_VERSION = "007_run_create_idempotency"
RUN_CREATE_IDEMPOTENCY_MIGRATION_CHECKSUM = "run-create-idempotency-v1"
_KEY_HASH_NAMESPACE = "dra.run-create-idempotency.v1\0"

IdempotencyKey = Annotated[
    str,
    StringConstraints(
        min_length=8,
        max_length=128,
    ),
]
_IDEMPOTENCY_KEY_ADAPTER = TypeAdapter(IdempotencyKey)


class _StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RunCreateRequestFingerprint(_StrictContract):
    schema_version: Literal["dra.run-create-request.v1"] = (
        RUN_CREATE_REQUEST_SCHEMA_VERSION
    )
    query: str
    thread_id: str | None
    profile_id: str
    scope: dict[str, Any]


class RunCreationAcceptance(_StrictContract):
    run_id: str
    thread_id: str
    segment_id: str
    idempotent_replay: bool


def validate_idempotency_key(value: str) -> str:
    try:
        validated = _IDEMPOTENCY_KEY_ADAPTER.validate_python(value, strict=True)
    except ValidationError as exc:
        raise ValueError("run_idempotency_key_invalid") from exc
    if re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}",
        validated,
        flags=re.ASCII,
    ) is None:
        raise ValueError("run_idempotency_key_invalid")
    return validated


def idempotency_key_hash(value: str) -> str:
    validated = validate_idempotency_key(value)
    return hashlib.sha256(
        f"{_KEY_HASH_NAMESPACE}{validated}".encode("utf-8")
    ).hexdigest()


def run_create_request_hash(
    *,
    query: str,
    thread_id: str | None,
    profile_id: str,
    scope: dict[str, Any],
) -> str:
    fingerprint = RunCreateRequestFingerprint(
        query=query,
        thread_id=thread_id,
        profile_id=profile_id,
        scope=scope,
    )
    encoded = json.dumps(
        fingerprint.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
```

- [ ] **Step 4: Run focused tests to prove GREEN**

Run the Step 2 command again.

Expected: all tests in `test_run_creation_models.py` pass.

- [ ] **Step 5: Commit the typed contract**

```bash
git add api/run_creation_models.py tests/unit/test_run_creation_models.py
git commit -m "feat(api): define run idempotency contracts"
```

---

### Task 2: Add The Durable Ledger, Atomic Repository Path, And Upgrade Migration

**Files:**
- Modify: `api/run_repository.py`
- Modify: `api/run_migrations.py`
- Modify: `tests/unit/test_run_repository.py`
- Modify: `tests/unit/test_run_migrations.py`

**Interfaces:**
- Consumes: Task 1 hashes, constants, and `RunCreationAcceptance`.
- Produces: `RunCreationConflict(code)`, unchanged `create_run` behavior, and the keyword-only `create_or_replay_run` function returning `RunCreationAcceptance`.
- Invariant: run, initial segment, and keyed ledger row are created in one transaction.

- [ ] **Step 1: Add repository RED tests for replay, conflict, thread semantics, corruption, and races**

Append tests to `tests/unit/test_run_repository.py`. Use an 8+ character key in every keyed case and query the database directly to prove the raw key is absent:

```python
import concurrent.futures
import sqlite3


def test_keyed_run_create_replays_original_generated_identity(tmp_path):
    from api.run_repository import create_or_replay_run

    db_path = str(tmp_path / "runs.db")
    kwargs = dict(
        db_path=db_path,
        idempotency_key="run-key-00000001",
        thread_id=None,
        query="query",
        profile_id="generic",
        profile_version="1",
        scope={},
    )
    first = create_or_replay_run(**kwargs)
    second = create_or_replay_run(**kwargs)
    assert first.idempotent_replay is False
    assert second.idempotent_replay is True
    assert second.model_copy(update={"idempotent_replay": False}) == first


def test_same_key_with_different_request_conflicts_and_creates_nothing(tmp_path):
    from api.run_repository import RunCreationConflict, create_or_replay_run

    db_path = str(tmp_path / "runs.db")
    base = dict(
        db_path=db_path,
        idempotency_key="run-key-00000002",
        thread_id="thread-1",
        profile_id="generic",
        profile_version="1",
        scope={},
    )
    create_or_replay_run(query="first", **base)
    with pytest.raises(RunCreationConflict, match="run_idempotency_conflict"):
        create_or_replay_run(query="second", **base)
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM research_runs_v2").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM run_segments").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM run_create_idempotency_v1").fetchone()[0] == 1
    finally:
        connection.close()


def test_raw_key_is_not_persisted(tmp_path):
    from api.run_repository import create_or_replay_run

    db_path = str(tmp_path / "runs.db")
    raw_key = "raw-key-should-not-persist"
    create_or_replay_run(
        db_path=db_path,
        idempotency_key=raw_key,
        thread_id=None,
        query="query",
        scope={},
    )
    assert raw_key.encode("utf-8") not in (tmp_path / "runs.db").read_bytes()
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT key_hash, request_schema_version, request_hash "
            "FROM run_create_idempotency_v1"
        ).fetchone()
        assert len(row[0]) == len(row[2]) == 64
        assert row[1] == "dra.run-create-request.v1"
    finally:
        connection.close()


def test_concurrent_duplicate_create_serializes_to_one_run(tmp_path):
    from api.run_repository import create_or_replay_run

    db_path = str(tmp_path / "runs.db")
    kwargs = dict(
        db_path=db_path,
        idempotency_key="run-key-concurrent-0001",
        thread_id=None,
        query="query",
        profile_id="generic",
        profile_version="1",
        scope={},
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        accepted = list(pool.map(lambda _: create_or_replay_run(**kwargs), range(8)))
    assert sum(not item.idempotent_replay for item in accepted) == 1
    assert len({item.run_id for item in accepted}) == 1
    assert len({item.thread_id for item in accepted}) == 1
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM research_runs_v2").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM run_segments").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM run_create_idempotency_v1").fetchone()[0] == 1
    finally:
        connection.close()


def test_corrupt_ledger_binding_fails_closed(tmp_path):
    from api.run_repository import RunCreationConflict, create_or_replay_run

    db_path = str(tmp_path / "runs.db")
    kwargs = dict(
        db_path=db_path,
        idempotency_key="run-key-corrupt-0001",
        thread_id=None,
        query="query",
        scope={},
    )
    created = create_or_replay_run(**kwargs)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("DELETE FROM research_runs_v2 WHERE run_id = ?", (created.run_id,))
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(RunCreationConflict, match="run_idempotency_unavailable"):
        create_or_replay_run(**kwargs)
```

Keep the existing same-thread unkeyed test unchanged; add one keyed explicit-thread assertion rather than replacing it.

Also add a replay assertion that changes only `profile_version` between calls and still returns the original identity. `profile_version` is stored on the first run but is intentionally excluded from the caller-request fingerprint.

- [ ] **Step 2: Add migration RED tests for `007`, FK verification, and an existing `006` database**

Append to `tests/unit/test_run_migrations.py`:

```python
def _remove_idempotency_migration(db_path):
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute("DROP TABLE run_create_idempotency_v1")
            connection.execute(
                "DELETE FROM schema_migrations WHERE version = '007_run_create_idempotency'"
            )
    finally:
        connection.close()


def test_full_migration_includes_run_create_idempotency_schema(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    backup_path = str(tmp_path / "tasks.pre-idempotency.db")
    init_legacy_db(db_path).close()
    result = migrate_with_backup(db_path=db_path, backup_path=backup_path)
    assert "007_run_create_idempotency" in result["migration_versions"]
    assert "run_create_idempotency_v1" in result["tables"]
    connection = sqlite3.connect(db_path)
    try:
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(run_create_idempotency_v1)"
        ).fetchall()
    finally:
        connection.close()
    assert any(
        row[2] == "research_runs_v2"
        and row[3] == "run_id"
        and row[4] == "run_id"
        and row[6].upper() == "CASCADE"
        for row in foreign_keys
    )


def test_existing_publication_database_gets_new_backup_and_007(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    first_backup = str(tmp_path / "tasks.pre-publication.db")
    init_legacy_db(db_path).close()
    migrate_with_backup(db_path=db_path, backup_path=first_backup)
    _remove_idempotency_migration(db_path)
    second_backup = str(tmp_path / "tasks.pre-idempotency.db")
    result = migrate_with_backup(db_path=db_path, backup_path=second_backup)
    assert "007_run_create_idempotency" in result["migration_versions"]
    assert Path(second_backup).exists()


def test_007_failure_restores_existing_publication_database(tmp_path, monkeypatch):
    import api.run_migrations as migrations

    db_path = str(tmp_path / "tasks.db")
    init_legacy_db(db_path).close()
    migrate_with_backup(
        db_path=db_path,
        backup_path=str(tmp_path / "tasks.pre-publication.db"),
    )
    _remove_idempotency_migration(db_path)
    before = sqlite3.connect(db_path).iterdump()
    before_sql = "\n".join(before)
    original = migrations.init_run_schema

    def apply_then_fail(path):
        original(path)
        raise RuntimeError("idempotency migration failed")

    monkeypatch.setattr(migrations, "init_run_schema", apply_then_fail)
    with pytest.raises(RuntimeError, match="idempotency migration failed"):
        migrate_with_backup(
            db_path=db_path,
            backup_path=str(tmp_path / "tasks.pre-idempotency.db"),
        )
    connection = sqlite3.connect(db_path)
    try:
        after_sql = "\n".join(connection.iterdump())
    finally:
        connection.close()
    assert after_sql == before_sql
```

Add `from pathlib import Path` to this test module. Fix the `iterdump()` setup in the final test so the source connection is explicitly closed after materializing the dump; do not leave a temporary connection open.

Add a keyed-path integrity test that changes the `007_run_create_idempotency` checksum after initialization and proves `create_or_replay_run` raises `run_idempotency_unavailable` without creating a run. This is separate from the full migration verifier and protects the hot path from a forged or stale marker.

- [ ] **Step 3: Run repository and migration tests to prove RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_run_creation_models.py \
  tests/unit/test_run_repository.py \
  tests/unit/test_run_migrations.py
```

Expected: new tests fail because the ledger, keyed repository API, and `007` verifier do not exist.

- [ ] **Step 4: Implement the shared insertion and keyed transaction in `api/run_repository.py`**

Make these concrete changes:

1. Import Task 1 contracts.
2. Add `RunCreationConflict` with `.code` exactly like the existing repository conflict types.
3. In `init_run_schema`, create `run_create_idempotency_v1` after `research_runs_v2` and insert the `007` marker/checksum with `INSERT OR IGNORE`.
4. Extract a keyword-only `_insert_run_identity` helper returning `dict[str, str]` and containing the current run and initial-segment inserts without changing their persisted JSON or defaults.
5. Keep `create_run` signature and dict return unchanged; make it call the helper inside its current transaction.
6. Add the keyed function below. Do not join the ledger and run in the first lookup: a missing/corrupt run must be distinguishable from an unused key.

```python
class RunCreationConflict(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def create_or_replay_run(
    *,
    idempotency_key: str,
    thread_id: str | None,
    query: str,
    db_path: str | None = None,
    profile_id: str = "generic",
    profile_version: str = "1",
    scope: dict[str, Any] | None = None,
) -> RunCreationAcceptance:
    key_hash = idempotency_key_hash(idempotency_key)
    request_hash = run_create_request_hash(
        query=query,
        thread_id=thread_id,
        profile_id=profile_id,
        scope=scope or {},
    )
    connection = None
    try:
        init_run_schema(db_path)
        connection = _connect(db_path)
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            marker = connection.execute(
                "SELECT checksum FROM schema_migrations WHERE version = ?",
                (RUN_CREATE_IDEMPOTENCY_MIGRATION_VERSION,),
            ).fetchone()
            if (
                marker is None
                or marker["checksum"]
                != RUN_CREATE_IDEMPOTENCY_MIGRATION_CHECKSUM
            ):
                raise RunCreationConflict("run_idempotency_unavailable")
            existing = connection.execute(
                """
                SELECT request_schema_version, request_hash, run_id
                FROM run_create_idempotency_v1
                WHERE key_hash = ?
                """,
                (key_hash,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["request_schema_version"]
                    != RUN_CREATE_REQUEST_SCHEMA_VERSION
                    or existing["request_hash"] != request_hash
                ):
                    raise RunCreationConflict("run_idempotency_conflict")
                identity = connection.execute(
                    """
                    SELECT run.run_id, run.thread_id, segment.segment_id
                    FROM research_runs_v2 AS run
                    JOIN run_segments AS segment
                      ON segment.run_id = run.run_id
                     AND segment.sequence = 0
                     AND segment.kind = 'initial'
                    WHERE run.run_id = ?
                    """,
                    (existing["run_id"],),
                ).fetchone()
                if identity is None:
                    raise RunCreationConflict("run_idempotency_unavailable")
                return RunCreationAcceptance(
                    run_id=identity["run_id"],
                    thread_id=identity["thread_id"],
                    segment_id=identity["segment_id"],
                    idempotent_replay=True,
                )

            created = _insert_run_identity(
                connection,
                thread_id=thread_id or str(uuid.uuid4()),
                query=query,
                profile_id=profile_id,
                profile_version=profile_version,
                scope=scope or {},
            )
            connection.execute(
                """
                INSERT INTO run_create_idempotency_v1 (
                    key_hash, request_schema_version, request_hash,
                    run_id, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    key_hash,
                    RUN_CREATE_REQUEST_SCHEMA_VERSION,
                    request_hash,
                    created["run_id"],
                    _now(),
                ),
            )
            return RunCreationAcceptance(
                **created,
                idempotent_replay=False,
            )
    except RunCreationConflict:
        raise
    except sqlite3.Error as exc:
        raise RunCreationConflict("run_idempotency_unavailable") from exc
    finally:
        if connection is not None:
            connection.close()
```

Pass one `now` value into `_insert_run_identity` and the ledger insert so the new rows share one transaction timestamp. The snippet shows `_now()` for readability; the final implementation must compute it once before both inserts. The exact `007` marker lookup is the only integrity check added to the keyed hot path; do not call the full `verify_run_schema()` there.

- [ ] **Step 5: Implement explicit `007` verification and backup-aware upgrade**

In `api/run_migrations.py`:

- Import `init_run_schema` and all `007` constants.
- Add `run_create_idempotency_v1` to required tables and its five exact columns to required columns.
- Add the `007` checksum to expected migrations.
- Verify the declared `run_id -> research_runs_v2.run_id ON DELETE CASCADE` relation with `PRAGMA foreign_key_list`, not only `PRAGMA foreign_key_check`.
- Include `missing_foreign_keys` in the bounded `run_schema_verification_failed` message.
- Replace the current publication-marker-only orchestration with this state machine:

```python
def migrate_with_backup(*, db_path: str, backup_path: str) -> dict:
    markers = _migration_markers(db_path)
    publication_applied = (
        markers.get(PUBLICATION_MIGRATION_VERSION)
        == PUBLICATION_MIGRATION_CHECKSUM
    )
    idempotency_applied = (
        markers.get(RUN_CREATE_IDEMPOTENCY_MIGRATION_VERSION)
        == RUN_CREATE_IDEMPOTENCY_MIGRATION_CHECKSUM
    )

    if not publication_applied:
        migrate_publication_with_backup(
            db_path=db_path,
            backup_path=backup_path,
        )
    elif not idempotency_applied:
        if Path(backup_path).exists():
            raise RuntimeError("run_idempotency_migration_backup_already_exists")
        backup_database(db_path=db_path, backup_path=backup_path)
        try:
            init_run_schema(db_path)
            verify_run_schema(
                db_path=db_path,
                include_evidence_verification=True,
                include_publication=True,
            )
        except Exception:
            restore_database(backup_path=backup_path, db_path=db_path)
            raise

    return verify_run_schema(
        db_path=db_path,
        include_evidence_verification=True,
        include_publication=True,
    )
```

`_migration_markers` must return `{}` when `schema_migrations` does not exist, and it must fail closed if an existing known marker has the wrong checksum. When publication is absent, its existing migration remains the backup owner; its initialization chain must create `007` in the same migrated database. When publication exists and only `007` is absent, the new backup path is the backup owner. Do not overwrite an existing backup.

- [ ] **Step 6: Run focused repository/migration tests to prove GREEN**

Run the Step 3 command twice. The second run proves repeated schema initialization and migration verification remain stable.

Expected: both runs pass; the race test reports exactly one non-replay acceptance.

- [ ] **Step 7: Commit repository and migration behavior**

```bash
git add api/run_repository.py api/run_migrations.py \
  tests/unit/test_run_repository.py tests/unit/test_run_migrations.py
git commit -m "feat(api): persist idempotent run creation"
```

---

### Task 3: Integrate The Public API And Enforce The Scheduling Fence

**Files:**
- Modify: `api/server.py`
- Modify: `tests/integration/test_run_api.py`
- Modify: `tests/integration/test_durable_review_lifecycle.py` only if it asserts the startup backup filename

**Interfaces:**
- Consumes: `validate_idempotency_key`, `create_or_replay_run`, and `RunCreationConflict`.
- Produces: optional `Idempotency-Key` behavior and stable direct error envelopes.
- Invariant: the route does not call `_run_v2_with_persistence` on replay.

- [ ] **Step 1: Add API RED tests**

Add focused cases to `tests/integration/test_run_api.py` using `Idempotency-Key: run-key-api-0001` and a scheduler double that records and closes each coroutine:

```python
def test_keyed_create_replays_identity_and_schedules_once(tmp_path, monkeypatch):
    import api.server as server

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("API_SECRET", "test-integration-key")
    scheduled = []

    def capture_task(coroutine, task_id, **kwargs):
        scheduled.append(task_id)
        coroutine.close()

    monkeypatch.setattr(server, "create_tracked_task", capture_task)
    client = TestClient(app)
    headers = {**AUTH_HEADERS, "Idempotency-Key": "run-key-api-0001"}
    body = {"query": "research", "profile_id": "generic", "scope": {}}
    first = client.post("/api/runs", json=body, headers=headers)
    second = client.post("/api/runs", json=body, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["idempotent_replay"] is False
    assert second.json()["idempotent_replay"] is True
    assert {
        key: first.json()[key]
        for key in ("run_id", "thread_id", "segment_id")
    } == {
        key: second.json()[key]
        for key in ("run_id", "thread_id", "segment_id")
    }
    assert scheduled == [first.json()["run_id"]]


def test_keyed_create_conflict_is_stable_and_schedules_nothing_new(tmp_path, monkeypatch):
    import api.server as server

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("API_SECRET", "test-integration-key")
    scheduled = []

    def capture_task(coroutine, task_id, **kwargs):
        scheduled.append(task_id)
        coroutine.close()

    monkeypatch.setattr(server, "create_tracked_task", capture_task)
    client = TestClient(app)
    headers = {**AUTH_HEADERS, "Idempotency-Key": "run-key-api-0002"}
    assert client.post("/api/runs", json={"query": "first"}, headers=headers).status_code == 200
    conflict = client.post("/api/runs", json={"query": "second"}, headers=headers)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "run_idempotency_conflict"
    assert conflict.json()["retryable"] is False
    assert conflict.json()["run_id"] is None
    assert len(scheduled) == 1


def test_invalid_idempotency_key_is_stable_and_does_not_touch_repository(monkeypatch):
    import api.server as server

    monkeypatch.setenv("API_SECRET", "test-integration-key")
    monkeypatch.setattr(
        server,
        "create_or_replay_run",
        lambda **kwargs: pytest.fail("invalid key must fail before persistence"),
    )
    response = TestClient(app).post(
        "/api/runs",
        json={"query": "research"},
        headers={**AUTH_HEADERS, "Idempotency-Key": "short"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "run_idempotency_key_invalid"


def test_keyed_persistence_failure_is_503_without_unkeyed_fallback(monkeypatch):
    import api.server as server
    from api.run_repository import RunCreationConflict

    monkeypatch.setenv("API_SECRET", "test-integration-key")
    monkeypatch.setattr(
        server,
        "create_or_replay_run",
        lambda **kwargs: (_ for _ in ()).throw(
            RunCreationConflict("run_idempotency_unavailable")
        ),
    )
    monkeypatch.setattr(
        server,
        "create_run",
        lambda **kwargs: pytest.fail("must not fall back to unkeyed create"),
    )
    response = TestClient(app).post(
        "/api/runs",
        json={"query": "research"},
        headers={**AUTH_HEADERS, "Idempotency-Key": "run-key-api-0003"},
    )
    assert response.status_code == 503
    assert response.json()["code"] == "run_idempotency_unavailable"
    assert response.json()["retryable"] is True
```

Also add:

- an exact unkeyed response-key assertion proving `idempotent_replay` is absent;
- a lost-response test that performs the successful first keyed call, intentionally discards its body, retries, and asserts one scheduler call and one DB run;
- a replay test whose scheduler double fails if a coroutine is constructed on the second request;
- a replay test that separately patches `_run_v2_with_persistence` to fail if it is called on the second request, so the coroutine-construction fence is explicit;
- a keyed scheduling-failure test proving the existing failed-run finalization remains bound to the same key, retry returns the same identity, and `GET /api/runs/{run_id}` reports the failed state;
- an unknown `RunCreationConflict` code test proving it maps to the safe 503 unavailable envelope;
- conflict and unavailable response-body assertions proving the raw key is absent;
- stable error-envelope field assertions (`code`, `problem`, `cause`, `fix`, `retryable`, `run_id`, `request_id`) without asserting random `request_id` content.

- [ ] **Step 2: Run API tests to prove RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/integration/test_run_api.py \
  tests/integration/test_run_auxiliary_isolation.py
```

Expected: new keyed tests fail because the route ignores the header and schedules duplicate runs.

- [ ] **Step 3: Implement the route and stable error mapping**

In `api/server.py`:

1. Import `Annotated`, FastAPI `Header`, Task 1 validation, and Task 2 repository APIs.
2. Add a private keyword-only `_run_creation_error` returning `JSONResponse` with the same bounded seven fields used by controlled APIs: `code`, `problem`, `cause`, `fix`, `retryable`, `run_id`, `request_id`.
3. Change the route signature to accept `idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None`.
4. Keep profile and scope validation before persistence.
5. Branch exactly as follows:

```python
if idempotency_key is None:
    thread_id = request.thread_id or str(uuid.uuid4())
    created = await asyncio.to_thread(
        create_run,
        thread_id=thread_id,
        query=request.query,
        profile_id=request.profile_id,
        profile_version=profile.version,
        scope=validated_scope,
    )
    replay = False
else:
    try:
        validated_key = validate_idempotency_key(idempotency_key)
    except ValueError:
        return _run_creation_error(
            422,
            code="run_idempotency_key_invalid",
            problem="The run idempotency key is invalid.",
            cause="Idempotency-Key failed the bounded public contract.",
            fix="Use 8-128 high-entropy ASCII characters from the documented set.",
            retryable=False,
        )
    try:
        acceptance = await asyncio.to_thread(
            create_or_replay_run,
            idempotency_key=validated_key,
            thread_id=request.thread_id,
            query=request.query,
            profile_id=request.profile_id,
            profile_version=profile.version,
            scope=validated_scope,
        )
    except RunCreationConflict as exc:
        return _run_creation_conflict_response(exc.code)
    created = acceptance.model_dump(mode="json")
    thread_id = acceptance.thread_id
    replay = acceptance.idempotent_replay

response = {"status": "started", **created}
if idempotency_key is not None:
    response["idempotent_replay"] = replay
if replay:
    return response
```

Only after this block construct `OutcomeBox`, call `_run_v2_with_persistence`, and pass it to `create_tracked_task`. Return the already-built `response`. `_run_creation_conflict_response` maps only:

- `run_idempotency_conflict` -> 409, retryable false, no run ID;
- `run_idempotency_unavailable` -> 503, retryable true, no run ID;
- every unknown repository code -> the 503 unavailable envelope, without leaking the internal code.

When durable startup runs the new migration, change its backup suffix from `.pre-p2a-pr2.bak` to `.pre-run-idempotency.bak`. Update only tests/docs that explicitly assert that suffix.

- [ ] **Step 4: Run API and regression tests to prove GREEN**

Run the Step 2 command, then:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/integration/test_durable_review_lifecycle.py \
  tests/unit/test_run_repository.py \
  tests/unit/test_run_migrations.py
```

Expected: all pass. Unkeyed same-thread tests still produce distinct run IDs.

- [ ] **Step 5: Commit the API contract**

```bash
git add api/server.py tests/integration/test_run_api.py \
  tests/integration/test_durable_review_lifecycle.py
git commit -m "feat(api): reconcile idempotent run requests"
```

If `test_durable_review_lifecycle.py` has no actual diff, do not stage it.

---

### Task 4: Add Tool Client Key Preservation And Recovery

**Files:**
- Modify: `tools/decision_research_agent_tool.py`
- Modify: `tests/unit/test_decision_research_agent_tool.py`

**Interfaces:**
- Consumes: optional server `Idempotency-Key` header and existing stable Tool Client error envelope.
- Produces: the existing keyword-only `start_run` function with an added `idempotency_key: str | None = None` parameter, CLI `--idempotency-key`, generated `run-create-<uuid>` keys, and ambiguous-transport recovery context.
- Invariant: `run --wait --result` continues to print only the canonical result; it does not gain client metadata after a run ID has been received.

- [ ] **Step 1: Add Tool Client RED tests**

Add these cases to `tests/unit/test_decision_research_agent_tool.py`:

```python
def test_start_run_forwards_idempotency_key_only_in_header(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["idempotency_key"] = req.get_header("Idempotency-key")
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse({"status": "started", "run_id": "run_1"})

    monkeypatch.setattr(tool.request, "urlopen", fake_urlopen)
    tool.start_run(
        query="query",
        thread_id=None,
        profile_id="generic",
        scope={},
        idempotency_key="run-key-client-0001",
        config=tool.ToolConfig(),
    )
    assert captured["idempotency_key"] == "run-key-client-0001"
    assert "idempotency_key" not in captured["body"]


def test_cli_run_generates_and_returns_reusable_key(monkeypatch, capsys):
    received = []

    def fake_start_run(**kwargs):
        received.append(kwargs["idempotency_key"])
        return {"status": "started", "run_id": "run_1"}

    monkeypatch.setattr(tool, "start_run", fake_start_run)
    assert tool.main(["run", "--query", "query"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert received == [payload["idempotency_key"]]
    assert payload["idempotency_key"].startswith("run-create-")


@pytest.mark.parametrize(
    "error_code",
    ["request_timeout", "connection_failed"],
)
def test_cli_ambiguous_create_failure_returns_exact_recovery_key(
    monkeypatch, capsys, error_code
):
    def fail(**kwargs):
        raise tool.ToolClientError(error_code)

    monkeypatch.setattr(tool, "start_run", fail)
    assert tool.main(
        [
            "run",
            "--query",
            "private query",
            "--idempotency-key",
            "run-key-client-0002",
        ]
    ) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["code"] == error_code
    assert payload["idempotency_key"] == "run-key-client-0002"
    assert "private query" not in json.dumps(payload)


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (409, "run_idempotency_conflict"),
        (422, "run_idempotency_key_invalid"),
        (503, "run_idempotency_unavailable"),
    ],
)
def test_tool_client_preserves_run_idempotency_service_errors(
    monkeypatch, status, code
):
    body = io.BytesIO(
        json.dumps(
            {
                "code": code,
                "problem": "bounded",
                "cause": "bounded",
                "fix": "bounded",
                "retryable": status == 503,
                "run_id": None,
                "request_id": "request_1",
            }
        ).encode("utf-8")
    )
    http_error = tool.error.HTTPError(
        "http://127.0.0.1:8000/api/runs",
        status,
        "error",
        {},
        body,
    )
    monkeypatch.setattr(
        tool.request,
        "urlopen",
        lambda req, timeout: (_ for _ in ()).throw(http_error),
    )
    with pytest.raises(tool.ToolClientHTTPError) as captured:
        tool.start_run(
            query="query",
            thread_id=None,
            profile_id="generic",
            scope={},
            idempotency_key="run-key-client-0003",
            config=tool.ToolConfig(),
        )
    assert captured.value.status == status
    assert captured.value.payload["code"] == code
```

Update existing `start_run` test doubles to accept the new keyword through `**kwargs`; keep the exact canonical-result assertions unchanged.

- [ ] **Step 2: Run Tool Client tests to prove RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q tests/unit/test_decision_research_agent_tool.py
```

Expected: new tests fail because the client has no key parameter or CLI flag.

- [ ] **Step 3: Implement header forwarding and CLI recovery context**

Make these exact behavior changes:

```python
def _headers(
    config: ToolConfig,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["X-API-Key"] = config.api_key
    if extra:
        headers.update(extra)
    return headers
```

Add `headers: dict[str, str] | None = None` to `_request_json` and pass it to `_headers`. Add the optional `idempotency_key` to `start_run` and send:

```python
extra_headers = (
    {"Idempotency-Key": idempotency_key}
    if idempotency_key is not None
    else None
)
return _request_json(
    "POST",
    _join_url(config.base_url, "/api/runs"),
    config=config,
    payload=payload,
    headers=extra_headers,
)
```

Add `run.add_argument("--idempotency-key")`. In the `run` branch of `main`:

```python
idempotency_key = args.idempotency_key or f"run-create-{uuid.uuid4()}"
try:
    created = start_run(
        query=args.query,
        thread_id=args.thread_id,
        profile_id=args.profile,
        scope=scope,
        idempotency_key=idempotency_key,
        config=config,
    )
except ToolClientError as exc:
    if exc.payload.get("code") in {"request_timeout", "connection_failed"}:
        raise _with_error_context(
            exc,
            context={"idempotency_key": idempotency_key},
        ) from exc
    raise
if not args.wait:
    result = {**created, "idempotency_key": idempotency_key}
else:
    run_id = created.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ToolClientError("run_response_invalid")
    try:
        terminal = wait_for_run(
            run_id,
            config,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.wait_timeout_seconds,
        )
        result = (
            globals()["result"](run_id, config)
            if args.result
            else terminal
        )
    except ToolClientError as exc:
        raise _with_error_context(
            exc,
            context={"run_id": run_id},
        ) from exc
```

Retain the existing checked-in wait/result behavior exactly as shown. Do not attach the key to service-owned HTTP errors, post-create wait errors, or canonical result output. The caller already has the explicit key or a `run_id` in those cases.

- [ ] **Step 4: Run Tool Client tests to prove GREEN**

Run the Step 2 command. Then run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/integration/test_run_api.py \
  tests/unit/test_decision_research_agent_tool.py
```

Expected: all pass; existing `run --wait --result` tests retain their exact output.

- [ ] **Step 5: Commit Tool Client behavior**

```bash
git add tools/decision_research_agent_tool.py \
  tests/unit/test_decision_research_agent_tool.py
git commit -m "feat(tool): preserve run idempotency keys"
```

---

### Task 5: Build A Deterministic Public Reconciliation Proof And Required CI Check

**Files:**
- Create: `scripts/run_creation_idempotency_proof.py`
- Create: `tests/integration/test_run_creation_idempotency_proof.py`
- Create: `docs/evidence/run-creation-idempotency-v1.json`
- Create: `docs/evidence/run-creation-idempotency-v1.md`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: production repository, FastAPI route, scheduler fence, and Tool Client paths from Tasks 1-4.
- Produces: `json`, `markdown`, and `check` CLI commands, byte-stable committed evidence, and one required CI proof check.
- Boundary: the report must say `crash_before_schedule_recovery: not_proven` and must never claim exactly-once execution.

- [ ] **Step 1: Write proof contract and CLI RED tests**

Create `tests/integration/test_run_creation_idempotency_proof.py` with tests that import the production proof module and also execute its file entry point:

```python
import json
import os
import subprocess
import sys

from scripts.run_creation_idempotency_proof import (
    BASELINE_JSON_PATH,
    BASELINE_MARKDOWN_PATH,
    build_report,
    render_markdown,
    serialize_report,
)


EXPECTED_CASE_IDS = [
    "lost_response_replay",
    "request_conflict",
    "concurrent_duplicate_serialization",
    "durable_restart_lookup",
    "unkeyed_independence",
    "raw_key_non_persistence",
    "tool_client_key_recovery",
]


def test_report_uses_exact_cases_and_honest_boundary():
    report = build_report()
    assert report["schema_version"] == "dra.run-creation-idempotency-proof.v1"
    assert report["status"] == "valid"
    assert [case["case_id"] for case in report["cases"]] == EXPECTED_CASE_IDS
    assert all(case["status"] == "passed" for case in report["cases"])
    assert report["boundaries"] == {
        "client_response_loss_after_scheduling": "proven",
        "durable_identity_lookup_after_restart": "proven",
        "crash_before_schedule_recovery": "not_proven",
        "exactly_once_execution": "not_claimed",
    }


def test_report_bytes_are_deterministic_and_match_committed_evidence():
    first = build_report()
    second = build_report()
    assert serialize_report(first) == serialize_report(second)
    assert render_markdown(first) == render_markdown(second)
    assert BASELINE_JSON_PATH.read_bytes() == serialize_report(first)
    assert BASELINE_MARKDOWN_PATH.read_text(encoding="utf-8") == render_markdown(first)


def test_check_entrypoint_is_stable_json_and_network_free():
    completed = subprocess.run(
        [sys.executable, "scripts/run_creation_idempotency_proof.py", "check"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"},
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {"status": "valid", "match": True}
    assert completed.stderr == ""
```

Also add failure tests for:

- missing/corrupt/oversized committed evidence -> stable stderr `{"status":"invalid","code":"run_idempotency_proof_baseline_invalid"}` and exit 1;
- bounded baseline reads;
- `json` and `markdown` returning the exact renderer bytes on stdout;
- `--help` exit 0 and no import-time stdout/stderr;
- public report containing no `run_` random IDs, raw key values, timestamps, local paths, credentials, provider names, or private markers.

- [ ] **Step 2: Run proof tests to prove RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/integration/test_run_creation_idempotency_proof.py
```

Expected: collection fails because the proof module does not exist.

- [ ] **Step 3: Implement the deterministic proof against production paths**

Implement `scripts/run_creation_idempotency_proof.py` with these exact public contracts:

```python
REPORT_SCHEMA_VERSION = "dra.run-creation-idempotency-proof.v1"
MAX_REPORT_BYTES = 128_000
BASELINE_JSON_PATH = PROJECT_ROOT / "docs/evidence/run-creation-idempotency-v1.json"
BASELINE_MARKDOWN_PATH = PROJECT_ROOT / "docs/evidence/run-creation-idempotency-v1.md"
CASE_IDS = (
    "lost_response_replay",
    "request_conflict",
    "concurrent_duplicate_serialization",
    "durable_restart_lookup",
    "unkeyed_independence",
    "raw_key_non_persistence",
    "tool_client_key_recovery",
)
```

`build_report()` must use a fresh `TemporaryDirectory` and production paths:

1. Patch only `api.server.create_tracked_task` with a capture function that records the task ID and closes the coroutine. Set an ephemeral DB path, disabled durable HITL flags, a fixed test API secret, and restore every environment/global mutation in `finally`.
2. Through `TestClient(api.server.app)`, send a fixed keyed request, discard the first response payload from the proof logic, retry it, and assert same identity, one scheduling action, and one DB row. Normalize the report to booleans/counts only.
3. Send a same-key/different-query request and record the exact 409 code with no run ID.
4. Use `ThreadPoolExecutor` and `create_or_replay_run` with independent connections; record one new acceptance and the rest replays.
5. Create in the parent process and replay from a separate `sys.executable -c` process using the same DB path; compare identities internally but output only `same_identity: true`.
6. Use production `create_run` twice for the same thread/query and record distinct identities.
7. Inspect database bytes/columns to prove the fixed raw key is absent and hashes are present.
8. Patch `tools.decision_research_agent_tool.request.urlopen`: first run the CLI with `run --query query` and make it return a timeout envelope containing its generated key; then reuse that exact key with a fake successful response and assert the outgoing header. Capture stdout locally and emit no key in the proof report.

Return only this normalized shape:

```python
{
    "schema_version": REPORT_SCHEMA_VERSION,
    "status": "valid",
    "source": "deterministic_local",
    "cases": [
        {"case_id": case_id, "status": "passed", "observations": observations}
        for case_id, observations in exact_case_order
    ],
    "boundaries": {
        "client_response_loss_after_scheduling": "proven",
        "durable_identity_lookup_after_restart": "proven",
        "crash_before_schedule_recovery": "not_proven",
        "exactly_once_execution": "not_claimed",
    },
    "limits": [
        "Deterministic local contract proof, not a provider or production measurement.",
        "Response loss is simulated only after current-process scheduling completes.",
        "Process or handler failure before scheduling is not recovered by this design.",
    ],
}
```

Validation must reject extra/missing cases, wrong ordering, non-boolean/count observations, unsupported schema, non-public text, and any boundary drift. Use strict Pydantic models local to the proof module or exact project-owned validators; do not create a second runtime authority.

Implement:

- `serialize_report(report) -> bytes` as UTF-8, sorted keys, two-space indent, trailing newline;
- deterministic Markdown with summary, exact case table, boundaries, and limits;
- `json` writing only the serialized report to stdout;
- `markdown` writing only the rendered Markdown to stdout;
- `check` rebuilding from production paths and byte-comparing both committed artifacts;
- stable one-line JSON stdout on success and one-line JSON stderr on failure;
- argparse failures mapped to the same stable error boundary while `-h/--help` remains exit 0.

Do not accept arbitrary output paths or implement atomic pair replacement. Candidate artifacts are generated by shell redirection to `/tmp`, reviewed, and added with `apply_patch`; the proof CLI only renders or checks.

Do not import or invoke LangSmith, provider clients, network search, process-local token collectors, or the Agent evaluation fixture builder.

- [ ] **Step 4: Generate and review committed evidence**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/run_creation_idempotency_proof.py json \
  > /tmp/run-creation-idempotency-v1.json
PYTHON_DOTENV_DISABLED=1 python scripts/run_creation_idempotency_proof.py markdown \
  > /tmp/run-creation-idempotency-v1.md
```

Review both candidates for exact cases, no identities/secrets/paths/timestamps, and honest limits. Then use `apply_patch` to add the reviewed bytes at:

- `docs/evidence/run-creation-idempotency-v1.json`
- `docs/evidence/run-creation-idempotency-v1.md`

The CLI must never write the committed baselines itself.

- [ ] **Step 5: Add the required CI check**

In `.github/workflows/ci.yml`, immediately after the Agent evaluation gate and before full pytest, add:

```yaml
      - name: Run deterministic run creation idempotency proof
        env:
          PYTHON_DOTENV_DISABLED: '1'
        run: python scripts/run_creation_idempotency_proof.py check
```

Keep all action pins, permissions, timeouts, dependency commands, frontend jobs, and existing gate order unchanged.

- [ ] **Step 6: Run proof and focused regression checks**

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_creation_idempotency_proof.py check > /tmp/idempotency-check-1.json
PYTHON_DOTENV_DISABLED=1 python scripts/run_creation_idempotency_proof.py check > /tmp/idempotency-check-2.json
cmp /tmp/idempotency-check-1.json /tmp/idempotency-check-2.json
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/integration/test_run_creation_idempotency_proof.py \
  tests/integration/test_run_api.py \
  tests/unit/test_run_repository.py \
  tests/unit/test_run_migrations.py \
  tests/unit/test_decision_research_agent_tool.py
```

Expected: both checks return `{"status":"valid","match":true}`, `cmp` succeeds, and all focused tests pass.

- [ ] **Step 7: Commit proof and CI**

```bash
git add scripts/run_creation_idempotency_proof.py \
  tests/integration/test_run_creation_idempotency_proof.py \
  docs/evidence/run-creation-idempotency-v1.json \
  docs/evidence/run-creation-idempotency-v1.md \
  .github/workflows/ci.yml
git commit -m "test(api): prove run creation reconciliation"
```

---

### Task 6: Publish Public Contracts And Complete Verification

**Files:**
- Modify: `docs/reference/api-contract.md`
- Modify: `docs/reference/data-models.md`
- Modify: `docs/decisions/run-identity-boundaries.md`
- Modify: `docs/architecture.md`
- Modify: `docs/AGENT_INTEGRATION.md`
- Modify: `docs/evidence/README.md`
- Modify: `docs/README.md`
- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/unit/test_documentation_contracts.py`
- Modify: `docs/operations/controlled-review-workflow.md` only if it names the old startup backup suffix

**Interfaces:**
- Consumes: delivered API, migration, Tool Client, proof, and explicit non-guarantees.
- Produces: public-neutral operator/consumer documentation and final validation evidence.

- [ ] **Step 1: Add documentation RED tests**

Extend `tests/unit/test_documentation_contracts.py` with exact assertions that:

- API reference documents optional `Idempotency-Key`, header-absent compatibility, regex/length, first/replay response, 409/422/503 codes, service-wide scope, no run disclosure, and GET for current state;
- Agent integration documents generated/explicit CLI keys, no automatic retry, and a copy-ready retry example using the exact same query/profile/thread/scope/key;
- data model/identity ADR documents `run_create_idempotency_v1`, request hash fields, FK cascade, no TTL, application DB authority, and same-thread independence;
- architecture explicitly separates create identity reconciliation from DeepAgents/LangGraph execution and LangSmith diagnostics;
- evidence index links both proof artifacts and includes `crash_before_schedule_recovery: not_proven`;
- CI contains exactly one `python scripts/run_creation_idempotency_proof.py check` after the Agent evaluation gate and before full pytest;
- README and README_CN use bounded phrasing such as “lost-response run identity reconciliation,” never “exactly-once execution” or production recovery;
- CHANGELOG adds an Unreleased `Run creation reliability` subsection without claiming `v0.1.2` is released;
- no docs contain the raw proof key, local absolute path, private consumer name, provider invoice claim, or new framework authority.

- [ ] **Step 2: Run documentation tests to prove RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q tests/unit/test_documentation_contracts.py
```

Expected: new documentation assertions fail.

- [ ] **Step 3: Update references and consumer workflow**

Document these exact examples in `docs/reference/api-contract.md` and `docs/AGENT_INTEGRATION.md`:

```bash
KEY="run-create-$(python -c 'import uuid; print(uuid.uuid4())')"
python tools/decision_research_agent_tool.py run \
  --query "Compare the declared options" \
  --idempotency-key "$KEY"

# If creation returns request_timeout or connection_failed, retry the same
# request inputs and the exact same key. Do not change query/profile/thread/scope.
python tools/decision_research_agent_tool.py run \
  --query "Compare the declared options" \
  --idempotency-key "$KEY"
```

State beside the example:

- retrying with the same key and request returns the original run identity;
- changing any canonical request field under that key returns 409;
- the key is replay identity, not authentication;
- `status=started` is create acknowledgement and GET is current state;
- a handler/process interruption before scheduling can leave execution unstarted and is not recovered by v1;
- no automatic retry occurs.

Keep credentials out of command arguments and do not add a provider-dependent demo.

- [ ] **Step 4: Update architecture, migration, evidence, and release-facing docs**

Add the exact table/authority/boundary from the spec. Link the JSON and Markdown proof from `docs/evidence/README.md`, and link the API/Agent/evidence pages from `docs/README.md`. Add concise English/Chinese README bullets and this Unreleased CHANGELOG shape:

```markdown
### Run creation reliability

- Added optional durable `Idempotency-Key` handling for run creation, including
  atomic replay/conflict behavior, concurrent duplicate serialization, and
  Tool Client recovery after a lost response.
- Added a deterministic public reconciliation proof while explicitly excluding
  crash-before-schedule recovery and exactly-once execution claims.
```

Do not add a `v0.1.2` release heading or release document.

- [ ] **Step 5: Run focused documentation and feature verification**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_run_creation_models.py \
  tests/unit/test_run_repository.py \
  tests/unit/test_run_migrations.py \
  tests/integration/test_run_api.py \
  tests/unit/test_decision_research_agent_tool.py \
  tests/integration/test_run_creation_idempotency_proof.py
PYTHON_DOTENV_DISABLED=1 python scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 python scripts/downstream_consumer_contract.py check
```

Expected: all focused tests pass; both required deterministic checks match; downstream output is valid.

- [ ] **Step 6: Run complete available verification**

Use the project-declared Python 3.11 environment if available; do not install or change dependencies without authorization.

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q
python scripts/final_presentation_audit.py
git diff --check 889aabbe7c19415c63c1f2f698895f7b1f7ec9cd..HEAD
git status --short --branch
```

Run public-safety and scope audits:

```bash
rg -n "provider invoice|exactly-once execution" \
  README.md README_CN.md CHANGELOG.md docs api scripts tools tests .github
git diff --name-only 889aabbe7c19415c63c1f2f698895f7b1f7ec9cd..HEAD -- \
  requirements.txt constraints.txt pyproject.toml
rg -n "langsmith|langgraph\.checkpoint|deepagents" \
  api/run_creation_models.py api/run_repository.py \
  scripts/run_creation_idempotency_proof.py
```

Expected:

- forbidden private markers and raw-path searches produce no unintended match;
- `exactly-once execution` appears only in explicit non-claim/boundary language;
- dependency diff is empty;
- new run-creation files import no LangSmith, LangGraph checkpoint, or DeepAgents authority;
- full pytest passes when declared dependencies are available. If collection fails because the environment lacks declared packages, record exact missing imports and do not claim full-suite success.

- [ ] **Step 7: Review the complete branch diff**

Confirm:

- no unkeyed response change;
- no second coroutine construction on replay;
- no raw key persistence/server echo/logging;
- one `007` migration with an explicit old-`006` upgrade test and new backup path;
- no endpoint, dependency, profile, result, Evidence, review, frontend, checkpoint, tracing, worker, queue, TTL, or RBAC expansion;
- proof output contains only normalized deterministic observations and honest limits;
- every public claim is directly backed by a production-path test or deterministic proof.

- [ ] **Step 8: Commit documentation and final test contracts**

```bash
git add README.md README_CN.md CHANGELOG.md docs \
  tests/unit/test_documentation_contracts.py
git commit -m "docs(api): publish run reconciliation contract"
```

Run the Step 5 and Step 6 verification commands again after the commit and leave the worktree clean.

## Test Coverage Map

| Contract or branch | Primary coverage | Proof / regression |
|---|---|---|
| strict ASCII key, length, control characters | `tests/unit/test_run_creation_models.py` | API 422 envelope |
| canonical request hash and `profile_version` exclusion | model and repository unit tests | same-key replay identity |
| unkeyed compatibility and same-thread independence | existing repository/API tests plus exact response-key assertion | `unkeyed_independence` case |
| first keyed create | repository transaction and API integration tests | `lost_response_replay` case |
| same-key replay | repository/API tests, scheduler count, explicit `_run_v2_with_persistence` fence | lost-response and durable-restart cases |
| same-key changed request | repository/API conflict tests | `request_conflict` case |
| concurrent duplicates | independent-connection race test | `concurrent_duplicate_serialization` case |
| ledger corruption, wrong marker, SQLite failure | repository and migration tests | stable API 503 without fallback |
| schedule failure after commit | API failed-finalization, replay, and GET-state test | documented non-guarantee remains bounded |
| raw-key secrecy | DB bytes/columns and response-body assertions | `raw_key_non_persistence` case |
| Tool Client generated/explicit key recovery | Tool Client unit tests including exact canonical-result output | `tool_client_key_recovery` case |
| old `006` database upgrade and restore | migration backup/restore/FK tests | startup suffix regression test |
| deterministic public evidence | proof integration tests and byte comparison | required CI `check` |

## Failure Modes And Coverage

| Failure mode | Required behavior | Evidence |
|---|---|---|
| invalid or non-ASCII key | 422 `run_idempotency_key_invalid`; persistence untouched | model + API tests |
| key reused with changed canonical request | 409 `run_idempotency_conflict`; no run identity or raw key disclosed | repository + API + proof |
| missing table, wrong `007` marker, corrupt binding, or SQLite failure | 503 `run_idempotency_unavailable`; no unkeyed fallback | repository + API tests |
| unknown repository conflict code | safe 503 unavailable envelope | API test |
| simultaneous first requests | exactly one run/segment/ledger insertion; remaining acceptances are replays | race test + proof |
| caller loses response after scheduling | retrying exact request/key returns original identity and does not construct or schedule again | API test + proof |
| scheduling raises after commit | existing run is finalized failed, remains bound to key, and retry exposes the same identity | API test + GET assertion |
| process/handler stops after commit but before scheduling | explicitly not recovered or claimed in v1 | spec, docs, proof boundary |
| Tool Client times out or cannot connect during create | stable error context includes reusable key; no automatic retry | Tool Client tests |
| service returns 409/422/503 | preserve bounded service envelope; do not append client key | Tool Client tests |
| `006` exists but `007` is absent | create a new backup, apply `007`, verify, restore on failure | migration tests |
| migration backup already exists | fail without overwriting it | migration test |
| committed proof missing, oversized, corrupt, or drifted | bounded read, exit 1, stable JSON error | proof CLI tests |

## Execution Order

Execute Tasks 1-6 sequentially. The typed fingerprint fixes repository semantics; the repository fixes API behavior; the API fixes Tool Client recovery; all four production paths are then exercised by the proof and documented. Parallel edits would create shared-file and baseline conflicts without shortening the critical path.

## Implementation Handoff

Execute this plan in the existing isolated branch/worktree that contains the approved spec. Use `superpowers:executing-plans`, strict task-by-task TDD, and the commit boundaries above. Stop and return to design if implementation requires outbox/worker recovery, a new endpoint, key expiry, actor scoping, automatic retries, dependency changes, or framework checkpoint authority.

After implementation, retain the clean local branch/worktree for authoritative branch-diff review. Do not push, create a PR, merge, tag, release, deploy, or clean the worktree without separate authorization.

## GSTACK REVIEW REPORT

| Review | Runs | Status | Findings |
|---|---:|---|---|
| Eng Review | 1 | CLEAR | Folded two engineering issues: the existing-`006` to `007` backup path and over-scoped proof output machinery. No critical gaps remain. |
| CEO Review | - | Not run | Product scope was already approved as bounded run-creation reconciliation. |
| Design Review | - | Not applicable | No user-interface change. |
| Security Review | - | Integrated | Raw-key secrecy, bounded input, fail-closed persistence, and non-disclosing errors are explicit test contracts. |
| LLM Review | - | Not applicable | No model prompt, provider, or inference behavior changes. |
| DX Review | - | Integrated | Explicit/generated keys, copy-ready recovery flow, stable errors, and canonical result compatibility are planned. |

**VERDICT:** ENG CLEARED - ready for implementation.

NO UNRESOLVED DECISIONS
