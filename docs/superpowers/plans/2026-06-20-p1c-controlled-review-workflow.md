# P1C Controlled Review Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote the disabled P1B durable review path into a strictly authenticated, single-node backend and CLI workflow for discovering, deciding, waiting on, and retrieving Talent reviews.

**Architecture:** Keep the existing application ledger, pure LangGraph review gate, SQLite checkpointer, lease worker, and immutable decision semantics. Add a fail-closed runtime configuration boundary, read-only review queue/detail/health projections, then a first-party CLI that consumes those APIs. The existing Vue frontend remains untouched; a future React client must reuse these contracts.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLite WAL, LangGraph persistent checkpointer, urllib-based Tool Client, pytest, Docker Compose.

---

## Delivery Boundary

Implement in two focused PRs:

| PR | Scope | Completion proof |
|---|---|---|
| PR 1 | Runtime validation, review list/detail/health APIs, strict auth, repository queries | Focused API/repository tests, full backend suite |
| PR 2 | CLI list/show/approve/reject/wait, doctor integration, Docker canary, operator docs | CLI tests, approve/reject container canary, 13/13 P1B gates, full backend suite, frontend build |

Do not modify any file under `frontend/`. Do not add React, RBAC, Postgres,
claim editing, decision amendment, automatic reruns, Skills, or Async Subagents.

## File Map

### PR 1

- Create `api/review_config.py`: validate the supported P1C runtime configuration and expose a bounded readiness snapshot.
- Modify `api/review_models.py`: bounded list query, cursor, queue item, detail, and health response contracts.
- Modify `api/review_repository.py`: deterministic queue pagination and authenticated detail projection.
- Modify `api/review_api.py`: shared strict auth plus list, detail, health, and supported decision routes.
- Modify `api/server.py`: fail-closed startup and review worker runtime state.
- Modify `spec/api-contract.md`: stable P1C endpoint contract.
- Modify `spec/data-models.md`: immutable decision and queue projection semantics.
- Create `tests/unit/test_review_config.py`.
- Test `tests/unit/test_review_models.py`.
- Test `tests/unit/test_review_repository.py`.
- Test `tests/integration/test_durable_review_api.py`.
- Test `tests/integration/test_durable_review_lifecycle.py`.

### PR 2

- Modify `tools/decision_research_agent_tool.py`: structured HTTP errors and nested review commands.
- Modify `tests/unit/test_decision_research_agent_tool.py`: request, parsing, decision identity, reason safety, wait, and doctor tests.
- Modify `tests/integration/test_durable_review_container.py`: first-party CLI approve/reject canary.
- Create `docs/operations/controlled-review-workflow.md`: supported configuration, operator journey, manual recovery, rollout, and rollback.
- Modify `README.md`: controlled P1C entry point and boundary.
- Modify `docs/AGENT_INTEGRATION.md`: automation-facing review commands and error behavior.
- Modify `TODOS.md`: mark P1C complete and retain React/RBAC/multi-instance work as deferred.
- Modify `docs/evidence/durable-hitl-gate-report.json` only by rerunning the existing gate runner.

## PR 1: Controlled Review API

### Task 1: Fail-Closed Runtime Configuration

**Files:**
- Create: `api/review_config.py`
- Modify: `api/server.py:108-138`
- Create: `tests/unit/test_review_config.py`
- Test: `tests/integration/test_durable_review_lifecycle.py`

- [ ] **Step 1: Write failing configuration tests**

Add these tests:

```python
from pathlib import Path

import pytest

from api.review_config import ReviewConfigurationError, validate_review_runtime


def test_enabled_review_requires_secret_and_explicit_persistent_paths(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.delenv("API_SECRET", raising=False)
    monkeypatch.delenv("TASKS_DB_PATH", raising=False)
    monkeypatch.delenv(
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
        raising=False,
    )

    with pytest.raises(
        ReviewConfigurationError,
        match="review_auth_not_configured",
    ):
        validate_review_runtime(output_dir=tmp_path / "output")


@pytest.mark.parametrize(
    ("tasks_path", "checkpoint_path", "code"),
    [
        (":memory:", "checkpoint.db", "review_application_db_not_persistent"),
        ("tasks.db", ":memory:", "review_checkpoint_db_not_persistent"),
        ("same.db", "same.db", "review_databases_must_be_separate"),
    ],
)
def test_enabled_review_rejects_unsupported_database_paths(
    tmp_path,
    monkeypatch,
    tasks_path,
    checkpoint_path,
    code,
):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.setenv("API_SECRET", "configured")
    monkeypatch.setenv(
        "TASKS_DB_PATH",
        tasks_path if tasks_path == ":memory:" else str(tmp_path / tasks_path),
    )
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
        (
            checkpoint_path
            if checkpoint_path == ":memory:"
            else str(tmp_path / checkpoint_path)
        ),
    )

    with pytest.raises(ReviewConfigurationError, match=code):
        validate_review_runtime(output_dir=tmp_path / "output")


def test_disabled_review_needs_no_runtime_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "false")
    monkeypatch.delenv("API_SECRET", raising=False)

    result = validate_review_runtime(output_dir=tmp_path / "output")

    assert result.enabled is False
```

Update the existing lifespan test so enabled + missing secret fails startup:

```python
def test_app_lifespan_fails_startup_without_api_secret(monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.delenv("API_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="review_auth_not_configured"):
        with TestClient(server.app):
            pass
```

Update the existing enabled worker lifecycle test before entering
`TestClient(server.app)`:

```python
monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "tasks.db"))
monkeypatch.setenv(
    "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
    str(tmp_path / "review-checkpoints.db"),
)
```

Add `tmp_path` to that test's fixture arguments.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python -m pytest \
  tests/unit/test_review_config.py \
  tests/integration/test_durable_review_lifecycle.py \
  -q
```

Expected: FAIL because `api.review_config` and fail-closed startup do not exist.

- [ ] **Step 3: Implement the runtime validator**

Create `api/review_config.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from api.review_models import durable_hitl_enabled


class ReviewConfigurationError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ReviewRuntimeConfig:
    enabled: bool
    application_db_path: Path | None = None
    checkpoint_db_path: Path | None = None
    output_dir: Path | None = None


def _persistent_path(raw: str | None, *, missing_code: str, memory_code: str) -> Path:
    value = (raw or "").strip()
    if not value:
        raise ReviewConfigurationError(missing_code)
    if value == ":memory:":
        raise ReviewConfigurationError(memory_code)
    return Path(value).expanduser().resolve()


def _ensure_writable_parent(path: Path, *, code: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not os.access(path.parent, os.W_OK):
        raise ReviewConfigurationError(code)


def validate_review_runtime(*, output_dir: Path) -> ReviewRuntimeConfig:
    if not durable_hitl_enabled():
        return ReviewRuntimeConfig(enabled=False)
    if not os.getenv("API_SECRET", ""):
        raise ReviewConfigurationError("review_auth_not_configured")

    application = _persistent_path(
        os.getenv("TASKS_DB_PATH"),
        missing_code="review_application_db_not_configured",
        memory_code="review_application_db_not_persistent",
    )
    checkpoint = _persistent_path(
        os.getenv("DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH"),
        missing_code="review_checkpoint_db_not_configured",
        memory_code="review_checkpoint_db_not_persistent",
    )
    if application == checkpoint:
        raise ReviewConfigurationError("review_databases_must_be_separate")

    output = output_dir.resolve()
    _ensure_writable_parent(application, code="review_application_db_not_writable")
    _ensure_writable_parent(checkpoint, code="review_checkpoint_db_not_writable")
    output.mkdir(parents=True, exist_ok=True)
    if not os.access(output, os.W_OK):
        raise ReviewConfigurationError("review_output_not_writable")
    return ReviewRuntimeConfig(True, application, checkpoint, output)
```

Modify `api/server.py` lifespan:

```python
from api.review_config import validate_review_runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    worker = None
    app.state.review_worker_running = False
    runtime = validate_review_runtime(output_dir=output_dir)
    if runtime.enabled:
        worker = ReviewWorker(
            db_path=str(runtime.application_db_path),
            checkpoint_path=str(runtime.checkpoint_db_path),
        )
        task = asyncio.create_task(worker.run_forever())
        await asyncio.sleep(0)
        if task.done():
            task.result()
        app.state.review_worker_running = True
    try:
        yield
    finally:
        app.state.review_worker_running = False
        if worker is not None:
            worker.stop()
        if task is not None:
            await task
```

Do not catch `ReviewConfigurationError`; startup must fail.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
python -m pytest \
  tests/unit/test_review_config.py \
  tests/integration/test_durable_review_lifecycle.py \
  -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add \
  api/review_config.py \
  api/server.py \
  tests/unit/test_review_config.py \
  tests/integration/test_durable_review_lifecycle.py
git commit -m "feat(review): validate controlled runtime"
```

### Task 2: Queue Cursor and Repository Projections

**Files:**
- Modify: `api/review_models.py`
- Modify: `api/review_repository.py:336-413`
- Test: `tests/unit/test_review_models.py`
- Test: `tests/unit/test_review_repository.py`

- [ ] **Step 1: Write failing model and repository tests**

Add model tests:

```python
from api.review_models import (
    ReviewListQuery,
    decode_review_cursor,
    encode_review_cursor,
)


def test_review_cursor_round_trips_without_exposing_sql():
    cursor = encode_review_cursor(
        created_at="2026-06-20T00:00:00+00:00",
        workflow_id="rwf_example",
    )

    assert decode_review_cursor(cursor) == (
        "2026-06-20T00:00:00+00:00",
        "rwf_example",
    )
    assert "rwf_example" not in cursor


def test_review_list_query_rejects_unknown_status_and_unbounded_limit():
    with pytest.raises(ValidationError):
        ReviewListQuery(status="unknown")
    with pytest.raises(ValidationError):
        ReviewListQuery(limit=101)
```

Add repository tests using `_required_review_run`:

```python
from api.review_repository import get_review_detail, list_review_workflows


def test_review_queue_defaults_to_waiting_and_uses_stable_cursor(tmp_path):
    db_path = str(tmp_path / "queue.db")
    _required_review_run(
        tmp_path,
        suffix="queue-a",
        db_path=db_path,
    )
    _required_review_run(
        tmp_path,
        suffix="queue-b",
        db_path=db_path,
    )
    page = list_review_workflows(
        db_path=db_path,
        status="waiting_decision",
        limit=1,
        cursor=None,
    )

    assert len(page["reviews"]) == 1
    assert page["reviews"][0]["workflow_status"] == "waiting_decision"
    assert page["next_cursor"] is not None
    assert "lease_owner" not in page["reviews"][0]
    second_page = list_review_workflows(
        db_path=db_path,
        status="waiting_decision",
        limit=1,
        cursor=decode_review_cursor(page["next_cursor"]),
    )
    assert len(second_page["reviews"]) == 1
    assert (
        second_page["reviews"][0]["workflow_id"]
        != page["reviews"][0]["workflow_id"]
    )


def test_review_detail_includes_bundle_and_reason_but_excludes_audit_secrets(
    required_review_run,
):
    request = ReviewDecisionRequest(
        decision_id="decision_reject",
        review_revision=1,
        action="reject",
        reason="Evidence boundary was not accepted.",
        expected_state_version=2,
    )
    accept_review_decision(
        db_path=required_review_run.db_path,
        run_id=required_review_run.run_id,
        review_id=required_review_run.review_id,
        request=request,
        actor_fingerprint="actor_hash",
    )

    detail = get_review_detail(
        db_path=required_review_run.db_path,
        run_id=required_review_run.run_id,
        review_id=required_review_run.review_id,
    )

    assert detail["review_bundle"]["review_id"] == required_review_run.review_id
    assert detail["decision"]["reason"] == "Evidence boundary was not accepted."
    encoded = json.dumps(detail)
    assert "actor_hash" not in encoded
    assert "checkpoint_thread_id" not in encoded
    assert "lease_owner" not in encoded
```

Refactor the test helper before this assertion:

```python
def _required_review_run(
    tmp_path,
    *,
    suffix: str,
    db_path: str | None = None,
) -> RequiredReviewRun:
    db_path = db_path or str(tmp_path / f"runs-{suffix}.db")
    created = create_run(
        db_path=db_path,
        thread_id=f"thread-{suffix}",
        query="query",
        profile_id="talent-hiring-signal",
    )
    review = ReviewBundle(
        review_id=f"review_{suffix}",
        run_id=created["run_id"],
        revision=1,
        status="required",
        claim_snapshots=[],
        evidence_snapshots=[evidence],
        triggers=["manual_review_required"],
        recommended_actions=["Review the bundle."],
        required_before_delivery=True,
    )
```

Retain the existing explicit scope, artifact, workflow, and finalization code.
Only the optional shared `db_path`, unique `thread_id`, and unique `review_id`
change.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python -m pytest \
  tests/unit/test_review_models.py \
  tests/unit/test_review_repository.py \
  -q
```

Expected: FAIL because cursor, list, and detail contracts do not exist.

- [ ] **Step 3: Implement bounded query and cursor models**

Add to `api/review_models.py`:

```python
from base64 import urlsafe_b64decode, urlsafe_b64encode
from pydantic import TypeAdapter


ReviewListStatus = Literal[
    "checkpoint_pending",
    "waiting_decision",
    "resume_pending",
    "resuming",
    "resolution_pending",
    "approved",
    "rejected",
    "manual_recovery",
]


class ReviewListQuery(FrozenModel):
    status: ReviewListStatus = "waiting_decision"
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=512)


_BOUNDED_ID_ADAPTER = TypeAdapter(BoundedId)


def encode_review_cursor(*, created_at: str, workflow_id: str) -> str:
    raw = json.dumps(
        [created_at, workflow_id],
        separators=(",", ":"),
    ).encode("utf-8")
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_review_cursor(cursor: str) -> tuple[str, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(urlsafe_b64decode(padded).decode("utf-8"))
        created_at, workflow_id = value
        _BOUNDED_ID_ADAPTER.validate_python(workflow_id)
        datetime.fromisoformat(created_at)
    except Exception as exc:
        raise ValueError("invalid_review_cursor") from exc
    return created_at, workflow_id
```

Do not duplicate the ID regex outside `BoundedId`.

- [ ] **Step 4: Implement deterministic queue and detail queries**

Add to `api/review_repository.py`:

```python
def list_review_workflows(
    *,
    status: str,
    limit: int,
    cursor: tuple[str, str] | None,
    db_path: str | None = None,
) -> dict[str, Any]:
    init_review_schema(db_path)
    connection = _connect(db_path)
    try:
        params: list[Any] = [status]
        cursor_sql = ""
        if cursor is not None:
            created_at, workflow_id = cursor
            cursor_sql = """
              AND (
                workflow.created_at < ?
                OR (
                  workflow.created_at = ?
                  AND workflow.workflow_id < ?
                )
              )
            """
            params.extend([created_at, created_at, workflow_id])
        params.append(limit + 1)
        rows = connection.execute(
            f"""
            SELECT
              workflow.workflow_id,
              workflow.run_id,
              workflow.review_id,
              workflow.review_revision,
              workflow.status AS workflow_status,
              workflow.last_error_code,
              workflow.created_at,
              workflow.updated_at,
              run.profile_id,
              run.review_status,
              run.delivery_status,
              run.state_version
            FROM review_workflows_v2 AS workflow
            JOIN research_runs_v2 AS run ON run.run_id = workflow.run_id
            WHERE workflow.status = ?
            {cursor_sql}
            ORDER BY workflow.created_at DESC, workflow.workflow_id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        page = rows[:limit]
        next_cursor = None
        if len(rows) > limit:
            last = page[-1]
            next_cursor = encode_review_cursor(
                created_at=last["created_at"],
                workflow_id=last["workflow_id"],
            )
        return {
            "reviews": [dict(row) for row in page],
            "next_cursor": next_cursor,
        }
    finally:
        connection.close()
```

Use fixed SQL fragments only; `status` remains a bound parameter and the
cursor never becomes SQL text.

Implement `get_review_detail()` with one transactionally consistent connection:

```python
def get_review_detail(
    *,
    run_id: str,
    review_id: str,
    db_path: str | None = None,
) -> dict[str, Any] | None:
    init_review_schema(db_path)
    connection = _connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT
              workflow.*,
              run.profile_id,
              run.review_status,
              run.delivery_status,
              run.state_version,
              bundle.bundle_json
            FROM review_workflows_v2 AS workflow
            JOIN research_runs_v2 AS run ON run.run_id = workflow.run_id
            JOIN review_bundles_v2 AS bundle
              ON bundle.review_id = workflow.review_id
            WHERE workflow.run_id = ? AND workflow.review_id = ?
            """,
            (run_id, review_id),
        ).fetchone()
        if row is None:
            return None
        decision = connection.execute(
            "SELECT * FROM review_decisions_v2 WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        resolution = connection.execute(
            "SELECT * FROM review_resolutions_v2 WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        result = {
            "run_id": run_id,
            "review_id": review_id,
            "review_revision": row["review_revision"],
            "profile_id": row["profile_id"],
            "state_version": row["state_version"],
            "review_status": row["review_status"],
            "delivery_status": row["delivery_status"],
            "workflow": _workflow_projection(row),
            "review_bundle": json.loads(row["bundle_json"]),
            "decision": _decision_detail_projection(decision),
            "resolution": _resolution_projection(resolution),
        }
        return result
    finally:
        connection.close()
```

`_decision_detail_projection()` may include `reason`, but must never include
`actor_fingerprint` or `request_hash`.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
python -m pytest \
  tests/unit/test_review_config.py \
  tests/unit/test_review_models.py \
  tests/unit/test_review_repository.py \
  -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add \
  api/review_models.py \
  api/review_repository.py \
  tests/unit/test_review_models.py \
  tests/unit/test_review_repository.py
git commit -m "feat(review): query controlled review queue"
```

### Task 3: Strict Review List, Detail, and Health APIs

**Files:**
- Modify: `api/review_api.py`
- Modify: `api/server.py:66-105`
- Test: `tests/integration/test_durable_review_api.py`

- [ ] **Step 1: Write failing route tests**

Add tests for every read route:

```python
def test_review_list_requires_strict_review_auth(required_review_run, monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.setenv("API_SECRET", "correct")
    monkeypatch.setenv("TASKS_DB_PATH", required_review_run.db_path)
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
        f"{required_review_run.db_path}.checkpoints",
    )

    response = TestClient(app).get("/api/reviews")

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_api_key"


def test_review_list_returns_bounded_waiting_projection(
    required_review_run,
    auth,
):
    response = TestClient(app).get("/api/reviews", headers=auth)

    assert response.status_code == 200
    item = response.json()["reviews"][0]
    assert item["run_id"] == required_review_run.run_id
    assert item["workflow_status"] == "waiting_decision"
    assert "reason" not in item
    assert "checkpoint_thread_id" not in item


def test_review_detail_returns_bundle_and_hides_audit_internals(
    required_review_run,
    auth,
):
    response = TestClient(app).get(
        (
            f"/api/runs/{required_review_run.run_id}"
            f"/reviews/{required_review_run.review_id}"
        ),
        headers=auth,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["review_bundle"]["review_id"] == required_review_run.review_id
    encoded = response.text
    assert "actor_fingerprint" not in encoded
    assert "checkpoint_thread_id" not in encoded
    assert "lease_owner" not in encoded


def test_review_health_reports_running_worker(auth, monkeypatch):
    with TestClient(app) as client:
        app.state.review_worker_running = True
        response = client.get("/api/reviews/health", headers=auth)

    assert response.status_code == 200
    assert response.json()["worker_running"] is True


def test_invalid_review_cursor_returns_actionable_422(auth):
    response = TestClient(app).get(
        "/api/reviews?cursor=not-valid",
        headers=auth,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_review_query"


def test_disable_then_reenable_preserves_review_state(
    required_review_run,
    auth,
    monkeypatch,
):
    detail_url = (
        f"/api/runs/{required_review_run.run_id}"
        f"/reviews/{required_review_run.review_id}"
    )
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "false")
    disabled = TestClient(app).get(detail_url, headers=auth)
    assert disabled.status_code == 404
    assert disabled.json()["code"] == "durable_hitl_disabled"

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    enabled = TestClient(app).get(detail_url, headers=auth)
    assert enabled.status_code == 200
    assert enabled.json()["workflow"]["status"] == "waiting_decision"


def test_manual_recovery_is_visible_without_force_mutation_route(
    manual_recovery_run,
    auth,
):
    response = TestClient(app).get(
        (
            f"/api/runs/{manual_recovery_run.run_id}"
            f"/reviews/{manual_recovery_run.review_id}"
        ),
        headers=auth,
    )
    assert response.status_code == 200
    assert response.json()["workflow"]["status"] == "manual_recovery"
    assert response.json()["operator_guidance"]["code"] == "checkpoint_corrupt"
    paths = app.openapi()["paths"]
    assert not any("force" in path for path in paths)
```

Add a regression assertion that the decision route no longer appears as
deprecated in `app.openapi()`.

Update the `auth` fixture to provide every enabled runtime prerequisite:

```python
from api.review_repository import _connect


@pytest.fixture
def auth(required_review_run, tmp_path, monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.setenv("API_SECRET", "correct")
    monkeypatch.setenv("TASKS_DB_PATH", required_review_run.db_path)
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
        str(tmp_path / "review-checkpoints.db"),
    )
    return {"X-API-Key": "correct"}


@pytest.fixture
def manual_recovery_run(required_review_run):
    connection = _connect(required_review_run.db_path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE review_workflows_v2
                SET status = 'manual_recovery',
                    last_error_code = 'checkpoint_corrupt'
                WHERE workflow_id = ?
                """,
                (required_review_run.workflow_id,),
            )
    finally:
        connection.close()
    return required_review_run
```

- [ ] **Step 2: Run route tests and verify RED**

Run:

```bash
python -m pytest tests/integration/test_durable_review_api.py -q
```

Expected: FAIL because read routes and health projection do not exist.

- [ ] **Step 3: Generalize strict review authentication**

Keep authentication in `api/review_api.py` and reuse it for every review route:

```python
def authenticate_review_request(request: Request, *, run_id: str | None = None):
    if not durable_hitl_enabled():
        return None, _error(
            404,
            code="durable_hitl_disabled",
            problem="Durable review is disabled.",
            cause="The feature flag is false.",
            fix="Enable the controlled single-node review configuration first.",
            retryable=False,
            run_id=run_id,
        )
    secret = os.getenv("API_SECRET", "")
    if not secret:
        return None, _error(
            503,
            code="review_auth_not_configured",
            problem="Durable review authentication is not configured.",
            cause="API_SECRET is empty after startup.",
            fix="Disable the feature and restart with API_SECRET configured.",
            retryable=False,
            run_id=run_id,
        )
    supplied = request.headers.get("X-API-Key", "")
    if not hmac.compare_digest(supplied, secret):
        return None, _error(
            401,
            code="invalid_api_key",
            problem="The review credential is invalid.",
            cause="X-API-Key did not match the configured service credential.",
            fix="Provide the configured X-API-Key.",
            retryable=False,
            run_id=run_id,
        )
    fingerprint = hashlib.sha256(
        f"decision-research-agent-review:{secret}".encode()
    ).hexdigest()
    return fingerprint, None
```

In `APIKeyMiddleware`, bypass generic middleware auth for the bounded review
router only, so the router always returns the structured review error envelope:

```python
def _is_review_api_path(path: str) -> bool:
    return path == "/api/reviews" or path.startswith("/api/reviews/") or (
        path.startswith("/api/runs/")
        and "/reviews/" in path
    )
```

- [ ] **Step 4: Add list, detail, and health routes**

Implement query validation after authentication:

```python
@router.get("/api/reviews")
async def list_reviews(request: Request):
    _, error = authenticate_review_request(request)
    if error is not None:
        return error
    try:
        query = ReviewListQuery.model_validate(dict(request.query_params))
        cursor = (
            decode_review_cursor(query.cursor)
            if query.cursor is not None
            else None
        )
    except (ValidationError, ValueError):
        return _error(
            422,
            code="invalid_review_query",
            problem="The review query is invalid.",
            cause="Status, limit, or cursor failed the bounded contract.",
            fix="Use a documented workflow status, limit 1-100, and returned cursor.",
            retryable=False,
        )
    return await asyncio.to_thread(
        list_review_workflows,
        status=query.status,
        limit=query.limit,
        cursor=cursor,
    )
```

Implement detail:

```python
@router.get("/api/runs/{run_id}/reviews/{review_id}")
async def show_review(run_id: str, review_id: str, request: Request):
    _, error = authenticate_review_request(request, run_id=run_id)
    if error is not None:
        return error
    detail = await asyncio.to_thread(
        get_review_detail,
        run_id=run_id,
        review_id=review_id,
    )
    if detail is None:
        return _conflict_response("review_not_found", run_id=run_id)
    if detail["workflow"]["status"] == "manual_recovery":
        detail["operator_guidance"] = {
            "code": detail["workflow"]["last_error_code"],
            "docs_url": "/docs/operations/controlled-review-workflow#manual-recovery",
        }
    return detail
```

Implement bounded health using `request.app.state.review_worker_running`, the
recorded gate report, schema initialization, and a `ReviewGate` open/inspect
compatibility check against the configured checkpoint database. Cache the
startup readiness snapshot on `app.state`; do not run a new checkpoint smoke on
every health request. Return `503 review_runtime_not_ready` if an enabled runtime
is not ready. Do not return paths or internal IDs.

- [ ] **Step 5: Promote the decision route contract**

Remove `deprecated=True` from the route decorator. Keep the request body,
idempotency, conflict handling, and asynchronous `202` response unchanged.

- [ ] **Step 6: Run focused API tests and verify GREEN**

Run:

```bash
python -m pytest \
  tests/integration/test_durable_review_api.py \
  tests/integration/test_durable_review_lifecycle.py \
  -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add \
  api/review_api.py \
  api/server.py \
  tests/integration/test_durable_review_api.py \
  tests/integration/test_durable_review_lifecycle.py
git commit -m "feat(review): expose controlled review api"
```

### Task 4: PR 1 Contract Documentation and Verification

**Files:**
- Modify: `spec/api-contract.md`
- Modify: `spec/data-models.md`

- [ ] **Step 1: Document exact API behavior**

Add these sections to `spec/api-contract.md`:

```markdown
### GET /api/reviews

Strict-auth queue endpoint. Defaults to `status=waiting_decision`, accepts
`limit=1..100` and an opaque cursor, and returns bounded metadata only.

### GET /api/runs/{run_id}/reviews/{review_id}

Strict-auth review detail. Returns the immutable ReviewBundle, workflow, accepted
decision reason, and resolution projection. It never returns actor fingerprint,
request hash, lease owner, checkpoint identity, or raw exceptions.

### GET /api/reviews/health

Strict-auth readiness endpoint used by the first-party Tool Client. Disabled
feature returns `404 durable_hitl_disabled`; enabled but unready returns
`503 review_runtime_not_ready`.
```

Update `spec/data-models.md` to state:

```markdown
`approve` and `reject` are immutable terminal decisions for a review revision.
A correction or repeated research request creates a new `run_id`; it does not
rewrite the prior run. Queue and detail APIs are projections of the existing
application ledger and introduce no new authority.
```

- [ ] **Step 2: Run PR 1 verification**

Run:

```bash
python -m pytest \
  tests/unit/test_review_config.py \
  tests/unit/test_review_models.py \
  tests/unit/test_review_repository.py \
  tests/integration/test_durable_review_api.py \
  tests/integration/test_durable_review_lifecycle.py \
  -q
python -m pytest -q
git diff --check
```

Expected:

- focused tests PASS;
- full backend suite PASS;
- no whitespace errors.

- [ ] **Step 3: Commit**

```bash
git add spec/api-contract.md spec/data-models.md
git commit -m "docs(review): document controlled api"
```

- [ ] **Step 4: PR 1 review checkpoint**

Review the diff from the recorded PR 1 base:

```bash
git diff --stat 7732ea1...HEAD
git diff --check 7732ea1...HEAD
```

Confirm:

- no CLI or frontend files changed;
- disabled behavior remains compatible;
- list/detail are read-only projections;
- decision mutation semantics are unchanged; and
- enabled invalid configuration fails startup.

If `main` advances before implementation starts, rebase the implementation
branch first and replace `7732ea1` in the execution record with the new exact
base SHA. Do not use a moving branch name in the final verification record.

## PR 2: First-Party Review CLI and Operations

### Task 5: Structured HTTP Failures and Review Read Commands

**Files:**
- Modify: `tools/decision_research_agent_tool.py`
- Test: `tests/unit/test_decision_research_agent_tool.py`

- [ ] **Step 1: Write failing HTTP and read-command tests**

Add:

```python
def test_http_error_preserves_structured_review_envelope(monkeypatch):
    body = io.BytesIO(
        json.dumps(
            {
                "code": "durable_hitl_disabled",
                "problem": "Durable review is disabled.",
                "retryable": False,
            }
        ).encode("utf-8")
    )
    http_error = tool.error.HTTPError(
        "http://127.0.0.1:8000/api/reviews",
        404,
        "Not Found",
        {},
        body,
    )
    monkeypatch.setattr(
        tool.request,
        "urlopen",
        lambda req, timeout: (_ for _ in ()).throw(http_error),
    )

    with pytest.raises(tool.ToolClientHTTPError) as captured:
        tool.list_reviews(tool.ToolConfig())

    assert captured.value.status == 404
    assert captured.value.payload["code"] == "durable_hitl_disabled"


def test_review_list_and_show_encode_requests(monkeypatch):
    urls = []

    def fake_urlopen(req, timeout):
        urls.append(req.full_url)
        return FakeResponse({"reviews": [], "next_cursor": None})

    monkeypatch.setattr(tool.request, "urlopen", fake_urlopen)
    config = tool.ToolConfig(base_url="http://127.0.0.1:9000")

    tool.list_reviews(
        config,
        status="waiting_decision",
        limit=20,
        cursor="cursor-value",
    )

    assert urls == [
        (
            "http://127.0.0.1:9000/api/reviews"
            "?status=waiting_decision&limit=20&cursor=cursor-value"
        )
    ]
```

Add parser assertions for:

```text
review list
review show --run-id run_1
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python -m pytest \
  tests/unit/test_decision_research_agent_tool.py \
  -q
```

Expected: FAIL because structured HTTP errors and review commands do not exist.

- [ ] **Step 3: Preserve structured HTTP error bodies**

Add:

```python
class ToolClientHTTPError(ToolClientError):
    def __init__(self, status: int, payload: dict[str, Any]):
        self.status = status
        self.payload = payload
        super().__init__(payload.get("code") or f"http_{status}")
```

Handle `HTTPError` before `URLError`:

```python
    except error.HTTPError as exc:
        try:
            parsed = _read_json(exc)
        except ToolClientError:
            parsed = {
                "code": f"http_{exc.code}",
                "problem": "The server returned a non-JSON error.",
                "retryable": False,
            }
        raise ToolClientHTTPError(exc.code, parsed) from exc
```

In `main()`, print `exc.payload` for `ToolClientHTTPError`; never print the URL or
headers if they could contain credentials.

- [ ] **Step 4: Add review read functions and parser group**

Implement:

```python
def list_reviews(
    config: ToolConfig,
    *,
    status: str = "waiting_decision",
    limit: int = 20,
    cursor: str | None = None,
) -> dict[str, Any]:
    query = {"status": status, "limit": str(limit)}
    if cursor:
        query["cursor"] = cursor
    return _request_json(
        "GET",
        _join_url(config.base_url, f"/api/reviews?{parse.urlencode(query)}"),
        config=config,
    )


def show_review(
    *,
    run_id: str,
    review_id: str | None,
    config: ToolConfig,
) -> dict[str, Any]:
    resolved_review_id = review_id
    if resolved_review_id is None:
        run = get_run(run_id, config)
        workflow = run.get("review_workflow") or {}
        resolved_review_id = workflow.get("review_id")
        if not resolved_review_id:
            raise ToolClientError("run_has_no_durable_review")
    return _request_json(
        "GET",
        _join_url(
            config.base_url,
            (
                f"/api/runs/{parse.quote(run_id, safe='')}"
                f"/reviews/{parse.quote(resolved_review_id, safe='')}"
            ),
        ),
        config=config,
    )
```

Create nested argparse subcommands. Keep the top-level API key environment-only.

- [ ] **Step 5: Run tests and verify GREEN**

Run:

```bash
python -m pytest tests/unit/test_decision_research_agent_tool.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add \
  tools/decision_research_agent_tool.py \
  tests/unit/test_decision_research_agent_tool.py
git commit -m "feat(review): add cli discovery commands"
```

### Task 6: Immutable Approve and Reject CLI Commands

**Files:**
- Modify: `tools/decision_research_agent_tool.py`
- Test: `tests/unit/test_decision_research_agent_tool.py`

- [ ] **Step 1: Write failing decision and reason-safety tests**

Add:

```python
def test_stable_decision_id_is_semantic_and_retry_safe():
    first = tool.stable_decision_id(
        run_id="run_1",
        review_id="review_1",
        revision=1,
        action="reject",
        reason="Not accepted",
    )
    assert first == tool.stable_decision_id(
        run_id="run_1",
        review_id="review_1",
        revision=1,
        action="reject",
        reason="Not accepted",
    )
    assert first != tool.stable_decision_id(
        run_id="run_1",
        review_id="review_1",
        revision=1,
        action="approve",
        reason=None,
    )


def test_reject_parser_has_no_plain_reason_argument():
    parser = tool._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["review", "reject", "--run-id", "run_1", "--reason", "secret"]
        )


def test_reject_requires_exactly_one_safe_reason_source(tmp_path):
    reason_file = tmp_path / "reason.txt"
    reason_file.write_text("Not accepted\\n", encoding="utf-8")

    assert tool.read_rejection_reason(
        reason_file=reason_file,
        reason_stdin=False,
        stdin=io.StringIO(""),
    ) == "Not accepted"
    with pytest.raises(tool.ToolClientError, match="reason_source_required"):
        tool.read_rejection_reason(
            reason_file=None,
            reason_stdin=False,
            stdin=io.StringIO(""),
        )
```

Add a request test asserting the CLI fetches current review revision and run
state version before posting.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python -m pytest tests/unit/test_decision_research_agent_tool.py -q
```

Expected: FAIL because decision helpers and mutation commands do not exist.

- [ ] **Step 3: Implement deterministic decision IDs**

Add:

```python
import hashlib
import sys
import uuid


def stable_decision_id(
    *,
    run_id: str,
    review_id: str,
    revision: int,
    action: str,
    reason: str | None,
) -> str:
    reason_hash = hashlib.sha256((reason or "").encode("utf-8")).hexdigest()
    semantic = "\\n".join(
        [run_id, review_id, str(revision), action, reason_hash]
    )
    return f"decision_{uuid.uuid5(uuid.NAMESPACE_URL, semantic).hex}"
```

- [ ] **Step 4: Implement bounded reason input**

Add:

```python
def read_rejection_reason(
    *,
    reason_file: Path | None,
    reason_stdin: bool,
    stdin,
) -> str:
    if (reason_file is None) == (not reason_stdin):
        raise ToolClientError("exactly_one_reason_source_required")
    value = (
        reason_file.read_text(encoding="utf-8")
        if reason_file is not None
        else stdin.read()
    ).strip()
    if not 1 <= len(value) <= 1000:
        raise ToolClientError("rejection_reason_must_be_1_to_1000_characters")
    return value
```

The immediate decision submission response must not echo the reason.
Strict-authenticated `review show` and terminal `review wait` may return it as
part of the documented detail projection.

- [ ] **Step 5: Implement approve/reject submission**

```python
def submit_review_decision(
    *,
    run_id: str,
    review_id: str | None,
    decision_id: str | None,
    action: str,
    reason: str | None,
    config: ToolConfig,
) -> dict[str, Any]:
    detail = show_review(run_id=run_id, review_id=review_id, config=config)
    resolved_review_id = detail["review_id"]
    resolved_decision_id = decision_id or stable_decision_id(
        run_id=run_id,
        review_id=resolved_review_id,
        revision=detail["review_revision"],
        action=action,
        reason=reason,
    )
    payload = {
        "decision_id": resolved_decision_id,
        "review_revision": detail["review_revision"],
        "action": action,
        "reason": reason,
        "expected_state_version": detail["state_version"],
    }
    return _request_json(
        "POST",
        _join_url(
            config.base_url,
            (
                f"/api/runs/{parse.quote(run_id, safe='')}"
                f"/reviews/{parse.quote(resolved_review_id, safe='')}"
                "/decisions"
            ),
        ),
        config=config,
        payload=payload,
    )
```

Add parser commands:

```text
review approve --run-id --review-id? --decision-id? --wait
review reject --run-id --review-id? --decision-id? --reason-file|--reason-stdin --wait
```

- [ ] **Step 6: Run tests and verify GREEN**

Run:

```bash
python -m pytest tests/unit/test_decision_research_agent_tool.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add \
  tools/decision_research_agent_tool.py \
  tests/unit/test_decision_research_agent_tool.py
git commit -m "feat(review): submit immutable cli decisions"
```

### Task 7: Review Wait, Doctor, and Real Container Canary

**Files:**
- Modify: `tools/decision_research_agent_tool.py`
- Modify: `tests/unit/test_decision_research_agent_tool.py`
- Modify: `tests/integration/test_durable_review_container.py`

- [ ] **Step 1: Write failing wait and doctor tests**

Add:

```python
def test_wait_for_review_returns_terminal_resolution(monkeypatch):
    responses = iter(
        [
            {"workflow": {"status": "resume_pending"}},
            {"workflow": {"status": "approved"}},
        ]
    )
    monkeypatch.setattr(tool, "show_review", lambda **kwargs: next(responses))
    monkeypatch.setattr(tool.time, "sleep", lambda seconds: None)

    result = tool.wait_for_review(
        run_id="run_1",
        review_id="review_1",
        config=tool.ToolConfig(),
        poll_seconds=0.01,
        timeout_seconds=1,
    )

    assert result["workflow"]["status"] == "approved"


def test_wait_for_review_fails_closed_on_manual_recovery(monkeypatch):
    monkeypatch.setattr(
        tool,
        "show_review",
        lambda **kwargs: {
            "workflow": {
                "status": "manual_recovery",
                "last_error_code": "checkpoint_corrupt",
            }
        },
    )

    with pytest.raises(tool.ToolClientError, match="manual_recovery"):
        tool.wait_for_review(
            run_id="run_1",
            review_id="review_1",
            config=tool.ToolConfig(),
            poll_seconds=0.01,
            timeout_seconds=1,
        )


def test_doctor_treats_disabled_review_as_optional(monkeypatch):
    monkeypatch.setattr(tool, "healthcheck", lambda config: {"status": "ok"})
    monkeypatch.setattr(
        tool,
        "profile_manifest",
        lambda profile_id, config: {
            "profile": {"profile_id": "talent-hiring-signal"},
            "harness_policy": {"allowed_tools": []},
        },
    )
    monkeypatch.setattr(
        tool,
        "review_health",
        lambda config: (_ for _ in ()).throw(
            tool.ToolClientHTTPError(
                404,
                {"code": "durable_hitl_disabled"},
            )
        ),
    )

    result = tool.doctor(tool.ToolConfig())

    assert result["status"] == "ok"
    assert result["checks"]["durable_review"]["status"] == "disabled"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python -m pytest tests/unit/test_decision_research_agent_tool.py -q
```

Expected: FAIL because wait and review health integration do not exist.

- [ ] **Step 3: Implement bounded wait**

```python
def wait_for_review(
    *,
    run_id: str,
    review_id: str | None,
    config: ToolConfig,
    poll_seconds: float = 1.0,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = show_review(
            run_id=run_id,
            review_id=review_id,
            config=config,
        )
        status = result["workflow"]["status"]
        if status in {"approved", "rejected"}:
            return result
        if status == "manual_recovery":
            code = result["workflow"].get("last_error_code") or "unknown"
            raise ToolClientError(f"manual_recovery:{code}")
        time.sleep(poll_seconds)
    raise ToolClientError("review_wait_timeout")
```

Validate both wait arguments are positive before polling.

- [ ] **Step 4: Extend doctor**

Add `review_health(config)` for `GET /api/reviews/health`. In `doctor()`:

```python
try:
    review = review_health(config)
except ToolClientHTTPError as exc:
    if (
        exc.status == 404
        and exc.payload.get("code") == "durable_hitl_disabled"
    ):
        checks["durable_review"] = {"status": "disabled"}
    else:
        raise
else:
    checks["durable_review"] = {
        "status": "ok" if review.get("status") == "ok" else "failed",
        "worker_running": review.get("worker_running"),
        "gate_report_status": review.get("gate_report_status"),
    }
```

An enabled but unready review runtime makes the overall doctor result `failed`.

- [ ] **Step 5: Add a real first-party CLI container canary**

Extend `DockerProject` without shell command composition:

```python
def exec_json(
    self,
    command: list[str],
    *,
    input_text: str | None = None,
) -> dict:
    completed = self._compose(
        "exec",
        "-T",
        "backend",
        *command,
        timeout=120,
        input_text=input_text,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    return json.loads(lines[-1])
```

Add `input_text: str | None = None` to `_compose()` and pass it to
`subprocess.run(input=input_text, ...)`.

Add an integration test that seeds two pending reviews and executes the real
Tool Client inside the running backend container:

```python
def test_controlled_review_cli_approve_and_reject_canary(docker_project):
    approve = docker_project.exec_json(
        ["python", "scripts/durable_hitl_container_fixture.py", "seed"]
    )
    approved = docker_project.exec_json(
        [
            "python",
            "tools/decision_research_agent_tool.py",
            "review",
            "approve",
            "--run-id",
            approve["run_id"],
            "--wait",
        ]
    )
    assert approved["workflow"]["status"] == "approved"
    assert approved["delivery_status"] == "ready"

    reject = docker_project.exec_json(
        ["python", "scripts/durable_hitl_container_fixture.py", "seed"]
    )
    rejected = docker_project.exec_json(
        [
            "python",
            "tools/decision_research_agent_tool.py",
            "review",
            "reject",
            "--run-id",
            reject["run_id"],
            "--reason-stdin",
            "--wait",
        ],
        input_text="Evidence boundary was not accepted.\n",
    )
    assert rejected["workflow"]["status"] == "rejected"
    assert rejected["delivery_status"] == "blocked"
    assert not any(
        item["artifact_id"].startswith("decision-brief.reviewed")
        for item in rejected["artifacts"]
    )
```

Before implementing this test, update
`scripts/durable_hitl_container_fixture.py` so each `seed` command creates a
unique fixture suffix:

```python
fixture_suffix = uuid.uuid4().hex[:12]
thread_id = f"durable-review-{fixture_suffix}"
packet_id = f"packet-{fixture_suffix}"
```

Pass rejection input through `subprocess.run(input=...)`; do not use `sh -c`.

- [ ] **Step 6: Run focused tests and canary**

Run:

```bash
python -m pytest tests/unit/test_decision_research_agent_tool.py -q
DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
  python -m pytest \
  tests/integration/test_durable_review_container.py::test_controlled_review_cli_approve_and_reject_canary \
  -q
```

Expected: unit tests PASS and the real container canary PASS without skip.

- [ ] **Step 7: Commit**

```bash
git add \
  tools/decision_research_agent_tool.py \
  scripts/durable_hitl_container_fixture.py \
  tests/unit/test_decision_research_agent_tool.py \
  tests/integration/test_durable_review_container.py
git commit -m "feat(review): complete controlled cli workflow"
```

### Task 8: Operator Documentation and Release Closure

**Files:**
- Create: `docs/operations/controlled-review-workflow.md`
- Modify: `README.md`
- Modify: `docs/AGENT_INTEGRATION.md`
- Modify: `TODOS.md`
- Regenerate: `docs/evidence/durable-hitl-gate-report.json`

- [ ] **Step 1: Write the operator runbook**

Create `docs/operations/controlled-review-workflow.md` with these exact sections:

```markdown
# Controlled Review Workflow

## Supported Boundary

Single backend replica, persistent application SQLite, separate persistent
checkpoint SQLite, persistent output, explicit feature flag, and one configured
API credential. This is not a multi-user or multi-instance deployment contract.

## Configure

List the four required environment variables without example secret values.

## Verify

Run `doctor`, the 13-gate runner, one synthetic approve, and one synthetic reject.

## Operate

Document `review list`, `review show`, `review approve`, `review reject`,
`review wait`, and reviewed artifact retrieval.

## Manual Recovery

Disable the feature, preserve both databases and output, capture redacted status,
classify the stable error code, and escalate. Do not edit the database or delete
the checkpoint.

## Rollback

Disable the feature and restart. Preserve all state. Re-enable only after doctor
and reconciliation pass.

## Non-Goals

No UI, React migration, RBAC, Postgres, multiple replicas, claim editing,
decision amendment, or automatic rerun.
```

- [ ] **Step 2: Update public entry points**

Update `README.md` to replace “P1B feasibility only” with:

- P1B durability evidence passed;
- P1C provides a controlled backend/CLI workflow when explicitly enabled;
- the default remains disabled;
- supported boundary is single-node only; and
- existing Vue UI does not expose review controls.

Update `docs/AGENT_INTEGRATION.md` with copy-paste commands using canonical
environment variables and no secret literals.

Update `TODOS.md`:

```markdown
- [x] Controlled single-node review API and CLI workflow.
- [ ] React frontend migration and review UI.
- [ ] Multi-user identity/RBAC.
- [ ] Shared database and multi-instance worker coordination.
```

- [ ] **Step 3: Run the complete P1C verification matrix**

Run serially because the durable gate includes Docker:

```bash
python -m pytest -q

python scripts/durable_hitl_gate_runner.py \
  --output docs/evidence/durable-hitl-gate-report.json

cd frontend
npm ci
npm run build
cd ..

git diff --check
```

Expected:

- full backend suite PASS;
- gate report has `status=PASS`, `expected=13`, `passed=13`, `failed=[]`;
- frontend build PASS despite no frontend source changes;
- no whitespace errors.

Do not run the full suite and gate runner in parallel because both may start
Docker resources.

- [ ] **Step 4: Verify public and privacy boundaries**

Run:

```bash
rg -n \
  '/Users/|job-search|interview-only|API_SECRET=.+|actor_fingerprint|lease_owner|checkpoint_thread_id' \
  README.md \
  docs/AGENT_INTEGRATION.md \
  docs/operations/controlled-review-workflow.md
```

Expected:

- no Career/private motivation;
- no secret value;
- internal fields appear only in explicit “not exposed” explanations.

Inspect the changed-file list:

```bash
PR2_BASE=$(git log --format=%H \
  --grep='^docs(review): document controlled api$' -n 1)
test -n "$PR2_BASE"
git diff --name-only "$PR2_BASE"...HEAD
```

Expected: no `frontend/` source file.

- [ ] **Step 5: Commit**

```bash
git add \
  README.md \
  docs/AGENT_INTEGRATION.md \
  docs/operations/controlled-review-workflow.md \
  docs/evidence/durable-hitl-gate-report.json \
  TODOS.md
git commit -m "docs(review): publish controlled workflow"
```

- [ ] **Step 6: Final implementation handoff**

Record:

- both PR base and head commits;
- exact full-suite result;
- exact 13-gate report;
- frontend build result;
- controlled canary result;
- feature flag default;
- supported single-node boundary; and
- deferred React/RBAC/multi-instance work.

Do not claim public internet production readiness or multi-user support.

## Final Acceptance Checklist

- [ ] Feature flag remains false by default.
- [ ] Enabled invalid configuration fails startup.
- [ ] Review list/detail/health/decision routes use strict review auth.
- [ ] Queue listing is deterministic and cursor-bounded.
- [ ] Review detail exposes reason only on strict-auth detail.
- [ ] Actor fingerprint, request hash, lease owner, and checkpoint internals remain hidden.
- [ ] Approve and reject are immutable per review revision.
- [ ] Rejection requires file/stdin reason and creates no reviewed deliverable.
- [ ] Equivalent CLI retries derive the same decision ID.
- [ ] `manual_recovery` is visible but not force-mutable.
- [ ] CLI approve and reject canaries pass in Docker.
- [ ] Disable/re-enable preserves ledger and checkpoint state.
- [ ] All thirteen P1B gates remain PASS.
- [ ] Full backend suite passes.
- [ ] Frontend build passes with no frontend source changes.
- [ ] Operator documentation states the single-node boundary.
