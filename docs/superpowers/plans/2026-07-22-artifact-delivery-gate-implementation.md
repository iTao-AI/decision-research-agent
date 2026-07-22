# Artifact Delivery Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the artifact-content endpoint return bytes only from one snapshot-consistent, canonical, ready result resolution.

**Architecture:** Add a narrow repository read projection that captures run delivery state, current publication selection, and candidate artifact bytes in one explicit SQLite read transaction. Keep selection and integrity policy in `api.run_result_service`, then make the artifact route a content-only view of the already resolved artifact.

**Tech Stack:** Python 3.11, FastAPI, SQLite WAL, dataclasses, pytest.

## Global Constraints

- Implement against the approved `docs/superpowers/specs/2026-07-22-artifact-delivery-and-limiter-diagnostics-design.md`.
- Preserve the path, method, successful media type, successful bytes, stable resolver error envelopes, and the existing non-selected artifact `404 {"detail":"Artifact 不存在"}` response.
- One request uses one explicit deferred SQLite read transaction; do not use `BEGIN IMMEDIATE` and do not rewrite generic `get_run()`.
- Request-snapshot consistency is the contract. A later commit affects the next request; continuous revocation during an open response is not claimed.
- An integrity-valid, resolver-selected `research_report_fallback_markdown` artifact is deliverable when the run is already `delivery_status=ready`.
- Do not modify Agent middleware, bounded producer code, evidence indexes, benchmark claims, database schema, migrations, dependencies, CI, release metadata, or `VERSION`.
- Use `PYTHON_DOTENV_DISABLED=1` and the repository Python 3.11 environment for tests.
- This lane is the landing carrier for the approved shared spec and all mechanically landed implementation plans. It must merge before PR B.

---

## File Structure

- Modify `api/run_repository.py`: own the narrow snapshot read and no delivery policy.
- Modify `api/run_result_service.py`: select and validate one artifact from the snapshot.
- Modify `api/server.py`: expose the resolved artifact bytes without a second repository read.
- Modify `tests/unit/test_run_repository.py`: lock the snapshot shape and corruption behavior.
- Modify `tests/integration/test_run_result_api.py`: lock state, integrity, fallback, route, and concurrency behavior.
- Modify `tests/integration/test_run_api.py`: retire the legacy raw-read route expectation.
- Modify `docs/reference/api-contract.md`: document the endpoint as canonical content delivery.
- Modify `tests/unit/test_documentation_contracts.py`: lock the public route authority wording.

### Task 1: Add The Snapshot-Consistent Repository Projection

**Files:**
- Modify: `api/run_repository.py:929-1100`
- Test: `tests/unit/test_run_repository.py`
- Test: `tests/integration/test_run_result_api.py`

**Interfaces:**
- Produces: `get_run_delivery_snapshot(*, run_id: str, db_path: str | None = None) -> dict[str, Any] | None`.
- Snapshot keys: `run_id`, `profile_id`, `execution_status`, `delivery_status`, `current_artifact_ids`, and `artifacts`.
- `current_artifact_ids` is an ordered `tuple[str, ...]`; `artifacts` is a tuple of complete artifact dictionaries including content.
- Does not decide terminal, review, delivery, selection, or integrity policy.

- [ ] **Step 1: Write failing shape and single-connection tests**

Add focused tests that use the existing `create_run()` and
`finalize_run_transaction()` helpers to seed generic and Talent runs, then assert the exact
projection. Define the following local helper in `tests/integration/test_run_result_api.py` so
later tasks reuse one concrete fixture instead of referring to an implicit test utility:

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SeededRun:
    db_path: Path
    run_id: str
    segment_id: str


def _seed_ready_generic(
    tmp_path,
    *,
    kind="research_report_markdown",
    content="# Report",
):
    from api.run_repository import create_run, finalize_run_transaction

    db_path = tmp_path / "tasks.db"
    created = create_run(
        db_path=str(db_path),
        thread_id="thread-1",
        query="query",
    )
    assert finalize_run_transaction(
        db_path=str(db_path),
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        delivery_status="ready",
        evidence_entries=[],
        artifacts=[_artifact(kind=kind, content=content)],
    )
    return SeededRun(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
    )


def test_run_delivery_snapshot_contains_only_resolver_inputs(tmp_path):
    from api.run_repository import get_run_delivery_snapshot

    seeded = _seed_ready_generic(tmp_path, content="# Decision Brief")
    snapshot = get_run_delivery_snapshot(
        db_path=str(seeded.db_path),
        run_id=seeded.run_id,
    )

    assert set(snapshot) == {
        "run_id",
        "profile_id",
        "execution_status",
        "delivery_status",
        "current_artifact_ids",
        "artifacts",
    }
    assert snapshot["current_artifact_ids"] == ()
    assert snapshot["artifacts"][0]["content"] == "# Decision Brief"
```

Add a test for an unknown run returning `None`, and a malformed
`artifact_ids_json` test that fails closed with `RunDeliverySnapshotConflict` rather than silently
falling back to a different artifact.

- [ ] **Step 2: Run the tests to verify RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_run_repository.py \
  tests/integration/test_run_result_api.py \
  -k 'delivery_snapshot'
```

Expected: FAIL because `get_run_delivery_snapshot` and
`RunDeliverySnapshotConflict` do not exist.

- [ ] **Step 3: Implement the minimal snapshot helper**

Add a stable internal exception and helper in `api/run_repository.py`:

```python
class RunDeliverySnapshotConflict(RuntimeError):
    """The persisted delivery projection cannot be read safely."""


def get_run_delivery_snapshot(
    *,
    run_id: str,
    db_path: str | None = None,
) -> dict[str, Any] | None:
    init_run_schema(db_path)
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN")
        run = conn.execute(
            """
            SELECT run_id, profile_id, execution_status, delivery_status
            FROM research_runs_v2
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if run is None:
            conn.commit()
            return None

        publication_table_exists = conn.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'run_publications_v2'
            """
        ).fetchone() is not None
        publication = (
            conn.execute(
                """
                SELECT artifact_ids_json
                FROM run_publications_v2
                WHERE run_id = ? AND is_current = 1
                """,
                (run_id,),
            ).fetchone()
            if publication_table_exists
            else None
        )
        current_ids: tuple[str, ...] = ()
        if publication is not None:
            parsed = json.loads(publication["artifact_ids_json"])
            if (
                type(parsed) is not list
                or any(type(value) is not str or not value for value in parsed)
                or len(set(parsed)) != len(parsed)
            ):
                raise ValueError("run_delivery_snapshot_corrupt")
            current_ids = tuple(parsed)

        rows = conn.execute(
            """
            SELECT artifact_id, kind, media_type, content, content_hash, created_at
            FROM run_artifacts_v2
            WHERE run_id = ?
            ORDER BY artifact_id
            """,
            (run_id,),
        ).fetchall()
        snapshot = {
            **dict(run),
            "current_artifact_ids": current_ids,
            "artifacts": tuple(dict(row) for row in rows),
        }
        conn.commit()
        return snapshot
    except (json.JSONDecodeError, sqlite3.Error, TypeError, ValueError) as exc:
        conn.rollback()
        raise RunDeliverySnapshotConflict(
            "run_delivery_snapshot_corrupt"
        ) from exc
    finally:
        conn.close()
```

Keep the existing `get_run()` and `get_artifact()` behavior unchanged.

- [ ] **Step 4: Add the controlled interleaving regression**

Monkeypatch `api.run_repository._connect` only in the test with a connection wrapper that pauses
immediately before the artifact query. The writer uses a second SQLite connection to commit a
blocked state and replacement artifact bytes after the reader's first SELECT. Assert the reader
returns the complete old-ready snapshot and the next snapshot sees the complete new-blocked state:

```python
assert first["delivery_status"] == "ready"
assert first["artifacts"][0]["content"] == "# Original"
assert second["delivery_status"] == "blocked"
assert second["artifacts"][0]["content"] == "# Replacement"
```

The wrapper must delegate `execute`, `commit`, `rollback`, and `close` to one real connection; it
must not add a production test hook.

- [ ] **Step 5: Run focused tests and commit**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_run_repository.py \
  tests/integration/test_run_result_api.py \
  -k 'delivery_snapshot'
git diff --check
```

Expected: PASS.

Commit:

```bash
git add api/run_repository.py tests/unit/test_run_repository.py \
  tests/integration/test_run_result_api.py
git commit -m "feat(api): read canonical delivery snapshots"
```

### Task 2: Resolve Results Entirely From One Snapshot

**Files:**
- Modify: `api/run_result_service.py:9-279`
- Test: `tests/integration/test_run_result_api.py`

**Interfaces:**
- Consumes: `get_run_delivery_snapshot` and `RunDeliverySnapshotConflict`.
- Produces: unchanged `ResolvedRunResult` and `RunResultUnavailable` public behavior.
- Removes: the resolver's direct call to `get_artifact`.

- [ ] **Step 1: Write failing resolver regressions**

Add tests that monkeypatch `api.run_result_service.get_artifact` to raise if called, cover all
existing 404/409 states, and add exact ready fallback and integrity cases:

```python
def test_ready_fallback_is_a_legal_canonical_result(tmp_path):
    seeded = _seed_ready_generic(
        tmp_path,
        kind="research_report_fallback_markdown",
        content="# Fallback Report\n\nBounded result.",
    )

    result = resolve_run_result(
        db_path=str(seeded.db_path),
        run_id=seeded.run_id,
    )

    assert result.artifact["kind"] == "research_report_fallback_markdown"
    assert result.artifact["content"] == "# Fallback Report\n\nBounded result."
```

For generic and Talent selections, mutate missing, empty, oversized, unsafe, and hash-invalid
content and expect `RunResultUnavailable(code="run_result_unavailable")`.

- [ ] **Step 2: Run the tests to verify RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/integration/test_run_result_api.py \
  -k 'snapshot or fallback or invalid_artifact'
```

Expected: at least the no-second-read assertion fails because the resolver still calls
`get_artifact()`.

- [ ] **Step 3: Move selection to the snapshot without changing policy**

Change the imports and resolver flow:

```python
from api.run_repository import (
    RunDeliverySnapshotConflict,
    get_run_delivery_snapshot,
)


def resolve_run_result(
    *,
    run_id: str,
    db_path: str | None = None,
) -> ResolvedRunResult:
    try:
        run = get_run_delivery_snapshot(run_id=run_id, db_path=db_path)
    except RunDeliverySnapshotConflict as exc:
        raise _unavailable() from exc
    if run is None:
        raise RunResultUnavailable(
            status_code=404,
            code="run_not_found",
            problem="The requested ResearchRun does not exist.",
            fix="Check the run_id returned by POST /api/runs.",
        )

    execution_status = run["execution_status"]
    delivery_status = run["delivery_status"]
    # Keep the existing terminal and delivery checks here unchanged.
    artifact_id = _select_artifact_id(run)
    by_id = {row["artifact_id"]: row for row in run["artifacts"]}
    artifact = by_id.get(artifact_id) if artifact_id is not None else None
    if not _valid_artifact(artifact):
        raise _unavailable()
    return ResolvedRunResult(
        run_id=run_id,
        execution_status=execution_status,
        delivery_status=delivery_status,
        artifact={
            "artifact_id": artifact["artifact_id"],
            "kind": artifact["kind"],
            "media_type": artifact["media_type"],
            "content": artifact["content"],
            "content_hash": artifact["content_hash"],
        },
    )
```

Update `_select_artifact_id` to use ordered `current_artifact_ids` and the snapshot's complete
artifact rows. Do not move policy into the repository.

- [ ] **Step 4: Run the resolver matrix and commit**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_run_result_service.py \
  tests/integration/test_run_result_api.py
git diff --check
```

Expected: PASS.

Commit:

```bash
git add api/run_result_service.py tests/integration/test_run_result_api.py
git commit -m "fix(api): resolve results from one snapshot"
```

### Task 3: Make Artifact Content A View Of The Resolved Result

**Files:**
- Modify: `api/server.py:1084-1091`
- Modify: `tests/integration/test_run_api.py:1814-1836`
- Test: `tests/integration/test_run_result_api.py`

**Interfaces:**
- Consumes: `resolve_run_result(run_id=...)` exactly once.
- Produces: resolver 404/409 envelopes, existing non-selected-ID artifact 404, and exact resolved bytes/media type.

- [ ] **Step 1: Write the failing route matrix**

Move the legacy artifact-route expectation into the result API suite and parameterize every
resolver disposition. Add a resolver spy that returns one artifact and fails if called twice. Add
a repository sentinel so the route cannot call `get_artifact` directly.

```python
def test_artifact_route_returns_only_resolved_bytes(client, monkeypatch):
    calls = []

    def resolve(*, run_id):
        calls.append(run_id)
        return ResolvedRunResult(
            run_id=run_id,
            execution_status="completed",
            delivery_status="ready",
            artifact={
                "artifact_id": "research-report.md",
                "kind": "research_report_fallback_markdown",
                "media_type": "text/markdown",
                "content": "# Fallback Report",
                "content_hash": hashlib.sha256(
                    b"# Fallback Report"
                ).hexdigest(),
            },
        )

    monkeypatch.setattr("api.server.resolve_run_result", resolve)
    response = client.get(
        "/api/runs/run_1/artifacts/research-report.md",
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.content == b"# Fallback Report"
    assert calls == ["run_1"]
```

- [ ] **Step 2: Run the route tests to verify RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/integration/test_run_result_api.py \
  tests/integration/test_run_api.py \
  -k 'artifact'
```

Expected: FAIL because the route still performs a raw `get_artifact` lookup.

- [ ] **Step 3: Implement the content-only route**

Replace the route body with:

```python
@app.get("/api/runs/{run_id}/artifacts/{artifact_id}")
async def get_run_artifact(run_id: str, artifact_id: str):
    try:
        result = await asyncio.to_thread(resolve_run_result, run_id=run_id)
    except RunResultUnavailable as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.payload(run_id=run_id),
        )
    artifact = result.artifact
    if artifact_id != artifact["artifact_id"]:
        return JSONResponse(
            status_code=404,
            content={"detail": "Artifact 不存在"},
        )
    return Response(
        content=artifact["content"],
        media_type=artifact["media_type"],
    )
```

Remove `get_artifact` from `api.server` imports only if no other server path uses it.

- [ ] **Step 4: Run route and broader API tests and commit**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/integration/test_run_result_api.py \
  tests/integration/test_run_api.py \
  -m 'not docker'
git diff --check
```

Expected: PASS.

Commit:

```bash
git add api/server.py tests/integration/test_run_result_api.py \
  tests/integration/test_run_api.py
git commit -m "fix(api): enforce artifact delivery authority"
```

### Task 4: Publish The Delivery Contract And Verify PR A

**Files:**
- Modify: `docs/reference/api-contract.md:148-158`
- Modify: `tests/unit/test_documentation_contracts.py`

**Interfaces:**
- Documents: one-snapshot canonical content delivery, resolver errors, ready fallback, and non-selected ID behavior.
- Does not document storage inspection or continuous revocation.

- [ ] **Step 1: Write the failing documentation contract**

Add a section-bound test that requires these exact concepts in the artifact endpoint section:

```python
for phrase in (
    "current canonical deliverable",
    "same SQLite request snapshot",
    "ready fallback artifact",
    "does not expose historical artifact content",
    '`404 {"detail":"Artifact 不存在"}`',
):
    assert phrase in artifact_section
for code in (
    "run_not_found",
    "run_not_terminal",
    "run_failed",
    "run_review_required",
    "run_delivery_blocked",
    "run_result_unavailable",
):
    assert code in artifact_section
```

- [ ] **Step 2: Run the contract to verify RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  -k 'artifact_delivery'
```

Expected: FAIL because the reference still describes raw persisted artifact access.

- [ ] **Step 3: Update the reference and run final verification**

Replace the raw-storage description with the approved authority wording, then run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_run_repository.py \
  tests/unit/test_run_result_service.py \
  tests/integration/test_run_result_api.py \
  tests/integration/test_run_api.py \
  tests/unit/test_documentation_contracts.py \
  -m 'not docker'
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m 'not docker'
PYTHON_DOTENV_DISABLED=1 python scripts/check_canonical_identity.py --root .
PYTHON_DOTENV_DISABLED=1 python scripts/final_presentation_audit.py
git diff --check
```

Expected: all commands PASS. If the full non-Docker suite is blocked by an environment mismatch,
record the exact package/import blocker and do not substitute a stub for the focused matrix.

- [ ] **Step 4: Commit the documentation**

```bash
git add docs/reference/api-contract.md tests/unit/test_documentation_contracts.py
git commit -m "docs(api): define canonical artifact delivery"
```

## PR A Completion Gate

- The actual branch diff matches the approved spec and this plan.
- All Task commits are present and the worktree is clean.
- No direct `get_artifact` call remains in the public route or canonical resolver.
- The concurrency regression proves coherent old or new snapshots, never mixed state/content.
- The ready fallback route succeeds only when canonical resolution says `ready`.
- No prohibited file, dependency, migration, CI, or version diff exists.
- Stop with a `READY` report for authoritative branch-diff review. Do not push or create a PR without separate authorization.
