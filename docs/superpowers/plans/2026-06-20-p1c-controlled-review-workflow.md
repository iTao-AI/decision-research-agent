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
import json
from pathlib import Path

import pytest

from api.review_config import (
    ReviewConfigurationError,
    check_review_readiness,
    validate_review_runtime,
)


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


def test_readiness_requires_exact_thirteen_gate_pass(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.setenv("API_SECRET", "configured")
    monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
        str(tmp_path / "checkpoints.db"),
    )
    report = tmp_path / "gate.json"
    report.write_text(
        json.dumps(
            {
                "status": "PASS",
                "expected": 13,
                "passed": 13,
                "failed": [],
            }
        ),
        encoding="utf-8",
    )
    runtime = validate_review_runtime(output_dir=tmp_path / "output")

    readiness = check_review_readiness(
        runtime=runtime,
        gate_report_path=report,
    )

    assert readiness.ready is True
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
import json
import os
from pathlib import Path
import uuid

from api.review_gate import ReviewGate
from api.review_models import durable_hitl_enabled
from api.review_repository import init_review_schema


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


@dataclass(frozen=True)
class ReviewRuntimeReadiness:
    application_schema_ready: bool
    checkpoint_compatible: bool
    gate_report_status: str

    @property
    def ready(self) -> bool:
        return (
            self.application_schema_ready
            and self.checkpoint_compatible
            and self.gate_report_status == "PASS"
        )


def _persistent_path(raw: str | None, *, missing_code: str, memory_code: str) -> Path:
    value = (raw or "").strip()
    if not value:
        raise ReviewConfigurationError(missing_code)
    if value == ":memory:":
        raise ReviewConfigurationError(memory_code)
    return Path(value).expanduser().resolve()


def _ensure_writable_parent(path: Path, *, code: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    probe = path.parent / f".review-write-probe-{uuid.uuid4().hex}"
    try:
        with probe.open("x", encoding="utf-8") as handle:
            handle.write("ok\n")
    except OSError as exc:
        raise ReviewConfigurationError(code) from exc
    finally:
        probe.unlink(missing_ok=True)


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
    _ensure_writable_parent(
        output / ".review-output-probe",
        code="review_output_not_writable",
    )
    return ReviewRuntimeConfig(
        enabled=True,
        application_db_path=application,
        checkpoint_db_path=checkpoint,
        output_dir=output,
    )


def check_review_readiness(
    *,
    runtime: ReviewRuntimeConfig,
    gate_report_path: Path,
) -> ReviewRuntimeReadiness:
    if not runtime.enabled:
        return ReviewRuntimeReadiness(False, False, "DISABLED")
    application_schema_ready = False
    checkpoint_compatible = False
    gate_report_status = "MISSING"
    try:
        init_review_schema(str(runtime.application_db_path))
        application_schema_ready = True
    except Exception:
        pass
    try:
        ReviewGate(
            str(runtime.checkpoint_db_path),
            lambda decision_id: None,
        ).inspect("review_runtime_probe")
        checkpoint_compatible = True
    except Exception:
        pass
    try:
        report = json.loads(gate_report_path.read_text(encoding="utf-8"))
        if (
            report.get("expected") == 13
            and report.get("passed") == 13
            and report.get("failed") == []
        ):
            gate_report_status = report.get("status", "INVALID")
        else:
            gate_report_status = "INVALID"
    except (OSError, ValueError, TypeError):
        pass
    return ReviewRuntimeReadiness(
        application_schema_ready=application_schema_ready,
        checkpoint_compatible=checkpoint_compatible,
        gate_report_status=gate_report_status,
    )
```

Modify `api/server.py` lifespan:

```python
from api.review_config import (
    ReviewConfigurationError,
    check_review_readiness,
    validate_review_runtime,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    worker = None
    app.state.review_worker_task = None
    app.state.review_runtime_readiness = None
    runtime = validate_review_runtime(output_dir=output_dir)
    if runtime.enabled:
        readiness = check_review_readiness(
            runtime=runtime,
            gate_report_path=(
                project_root
                / "docs"
                / "evidence"
                / "durable-hitl-gate-report.json"
            ),
        )
        if not readiness.ready:
            raise ReviewConfigurationError("review_runtime_not_ready")
        app.state.review_runtime_readiness = readiness
        worker = ReviewWorker(
            db_path=str(runtime.application_db_path),
            checkpoint_path=str(runtime.checkpoint_db_path),
        )
        task = asyncio.create_task(worker.run_forever())
        await asyncio.sleep(0)
        if task.done():
            task.result()
        app.state.review_worker_task = task
    try:
        yield
    finally:
        app.state.review_worker_task = None
        app.state.review_runtime_readiness = None
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

Implement bounded health using `request.app.state.review_worker_task`, the
recorded gate report, schema initialization, and a `ReviewGate` open/inspect
compatibility check against the configured checkpoint database. Cache the
startup readiness snapshot on `app.state`; do not run a new checkpoint smoke on
every health request. Return `503 review_runtime_not_ready` if an enabled runtime
is not ready. Compute `worker_running` on each request as:

```python
task = getattr(request.app.state, "review_worker_task", None)
worker_running = task is not None and not task.done()
```

Return the bounded projection:

```python
readiness = getattr(request.app.state, "review_runtime_readiness", None)
if readiness is None or not readiness.ready or not worker_running:
    return _error(
        503,
        code="review_runtime_not_ready",
        problem="The controlled review runtime is not ready.",
        cause="A required worker, schema, checkpoint, or release gate is unavailable.",
        fix="Disable the feature, run doctor, and correct the reported readiness check.",
        retryable=True,
    )
return {
    "status": "ok",
    "feature_enabled": True,
    "worker_running": worker_running,
    "application_schema_ready": readiness.application_schema_ready,
    "checkpoint_compatible": readiness.checkpoint_compatible,
    "gate_report_status": readiness.gate_report_status,
}
```

Do not return paths or internal IDs.

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

When `--wait` is present, dispatch the accepted decision response into
`wait_for_review()` and print the terminal detail projection. Without `--wait`,
print only the bounded `202` acceptance response.

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
    environment: dict[str, str] | None = None,
) -> dict:
    args = ["exec", "-T"]
    for key, value in sorted((environment or {}).items()):
        args.extend(["-e", f"{key}={value}"])
    args.extend(["backend", *command])
    completed = self._compose(
        *args,
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
        ],
        environment={
            "DECISION_RESEARCH_AGENT_API_KEY":
                "durable-hitl-container-test-only",
        },
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
        environment={
            "DECISION_RESEARCH_AGENT_API_KEY":
                "durable-hitl-container-test-only",
        },
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

---

## Autoplan Review

**Review status:** GO with corrections applied

**Review date:** 2026-06-20

**Plan commit reviewed:** `a676236`

**Voice availability:**

- Claude Code autoplan runner: unavailable due account `429` monthly limit.
- Independent Codex runner: unavailable due Codex usage limit.
- Main Codex review: completed against the approved spec and actual repository.

The missing external voices are recorded as unavailable, not treated as
consensus.

### Phase 0: Scope Assessment

| Dimension | Result |
|---|---|
| Product scope | Controlled operator workflow over an already-proven durable path |
| UI scope | None; Design Review skipped |
| Engineering scope | API, auth, SQLite projection, startup, worker, CLI, Docker |
| DX scope | High; first-party CLI and operator runbook are primary delivery |
| Breaking change | Only when feature is explicitly enabled with invalid configuration |
| Existing default | Feature remains disabled and compatible |

### Phase 1: CEO Review

#### Premise Challenge

The plan assumes the next valuable milestone is not another Agent capability but
a usable review workflow over P1B. That premise is supported by the current
product state: P1A already proved Talent output value and P1B already proved the
durable state machine. Without discovery, inspection, decision, wait, and
recovery guidance, the durable path remains an internal mechanism rather than a
usable capability.

The plan also assumes UI should wait. That remains correct because implementing
review semantics in the existing Vue frontend would be throwaway work before the
planned React migration. The backend contract is the highest-leverage asset.

#### What Already Exists

- Immutable `ReviewBundle`, decision, workflow, resolution, and artifact tables.
- Authenticated, idempotent `approve` / `reject` endpoint.
- Pure LangGraph review gate and separate persistent checkpoint database.
- Lease/reclaim worker and startup reconciliation.
- Bounded run projection.
- Thirteen-gate restart, container, conflict, sync durability, and `SIGKILL`
  evidence.
- Feature flag defaulting to false.

P1C must expose and operate these pieces; it must not rebuild them.

#### Highest-Leverage Product Move

The minimum complete user journey is:

```text
discover -> inspect -> decide -> wait -> consume or diagnose
```

The queue/detail API and first-party CLI complete this journey while remaining
small enough to ship in two PRs. A decision endpoint alone would leave operators
managing hidden IDs and polling ad hoc responses.

#### Alternatives

| Option | Completeness | Decision | Reason |
|---|---:|---|---|
| Keep P1B internal | 3/10 | Reject | Durable code exists but has no operator workflow |
| Backend + CLI controlled release | 9/10 | Adopt | Completes the narrow journey and stabilizes future React APIs |
| Full review product now | 10/10 breadth, 3/10 focus | Reject | Mixes UI, identity, editing, distributed deployment, and research reruns |

#### Dream-State Delta

The long-term product may have React, multi-user identity, role permissions,
claim-level review, and distributed workers. P1C intentionally delivers only the
stable business contract those capabilities would consume. The delta is explicit
and does not block the current milestone.

#### Error and Rescue Registry

| Failure | User-visible result | Rescue |
|---|---|---|
| Feature disabled | `404 durable_hitl_disabled` | Use non-interrupt bundle or enable supported configuration |
| Invalid enabled configuration | Backend refuses startup | Correct secret and persistent paths, restart |
| Invalid credential | `401 invalid_api_key` | Supply configured environment credential |
| Stale decision | `409 stale_state_version` | Fetch current detail and resubmit intentionally |
| Conflicting decision | `409`, first decision preserved | Consume persisted result; do not amend |
| Worker not running | `503 review_runtime_not_ready` | Disable feature, inspect worker, restart after fix |
| Manual recovery | Explicit terminal diagnostic | Disable, back up, collect redacted evidence, escalate |
| CLI wait timeout | Non-zero structured error | Re-run show/wait; no duplicate decision |

#### CEO Failure Modes Registry

| Failure mode | Prevention |
|---|---|
| P1C grows into a workflow platform | Three-day gate and explicit stop conditions |
| Existing Vue receives throwaway review UI | No `frontend/` file in scope |
| Reject silently starts research | New `run_id` required |
| Single service key is misrepresented as user identity | Document fingerprint as controlled credential only |
| P1B PASS is overstated as production readiness | Single-node supported boundary repeated in API, CLI, and runbook |

#### Not in Scope

- Vue changes or React implementation.
- RBAC, SSO, multiple reviewers, or external identity.
- Postgres, multiple replicas, or distributed worker coordination.
- Claim editing, decision amendment, evidence verification, or automatic rerun.
- Skills, Async Subagents, LLM reviewer, or Agent Server.

#### CEO Completion Summary

The scope is complete enough to produce one useful product workflow and narrow
enough to protect delivery time. No scope expansion is required.

### Phase 2: Design Review

Skipped. The approved phase explicitly excludes UI and visual design. CLI output
remains structured JSON to match the existing Tool Client.

### Phase 3: Engineering Review

#### Scope Challenge Against Actual Code

The implementation reuses the correct existing boundaries:

- `api/review_repository.py` remains the application authority.
- `api/review_gate.py` remains checkpoint-only.
- `api/review_worker.py` remains the sole resume/resolution executor.
- `api/review_api.py` owns strict review ingress.
- `tools/decision_research_agent_tool.py` remains a stateless client.

No new service or database is needed.

#### Architecture

```text
Operator
   |
   v
Tool Client
   |
   v strict X-API-Key
Review API -----> Queue/detail projections
   |                    |
   v                    v
Application SQLite (business authority)
   |
   v lease/reclaim
Review Worker
   |
   v
Pure ReviewGate -----> Checkpoint SQLite (execution position only)
   |
   v fenced resolution
Reviewed artifact OR blocked delivery
```

#### Corrections Applied During Review

1. Replaced `os.access` with an actual exclusive write/delete probe. Permission
   bits alone are not reliable proof of writable storage.
2. Replaced a cached `review_worker_running=True` boolean with live
   `asyncio.Task.done()` evaluation.
3. Added explicit canonical API-key injection to the Docker CLI canary. The
   Tool Client must not read `API_SECRET` directly.
4. Added disable/re-enable preservation coverage.
5. Added second-page assertions to prove cursor pagination does not repeat rows.
6. Removed `sh -c` from rejection canary input; stdin is passed directly.
7. Clarified that decision submission does not echo rejection reason, while the
   strict-auth detail projection may return it.

#### Test Diagram

```text
Runtime config
  -> unit path/secret/write probes
  -> lifespan startup refusal
  -> review health task liveness

Repository read model
  -> status + limit + cursor validation
  -> deterministic first/second page
  -> bounded detail + reason
  -> sensitive field exclusion

API
  -> auth before validation
  -> list/detail/health
  -> immutable decision regression
  -> disable/re-enable
  -> manual recovery visibility

CLI
  -> HTTP error envelope
  -> URL encoding
  -> deterministic decision ID
  -> safe reason input
  -> bounded wait
  -> disabled doctor behavior

End to end
  -> Docker approve canary
  -> Docker reject canary
  -> 13 existing durable gates
  -> full backend suite
  -> unchanged frontend build
```

#### Engineering Failure Modes Registry

| Failure | Severity | Prevention / rescue |
|---|---|---|
| Startup succeeds without a worker | Critical | Validate config, start task, surface immediate task failure |
| Health says running after task exits | High | Evaluate task liveness per request |
| Queue leaks review content | High | Metadata-only SQL projection |
| Detail leaks actor/checkpoint internals | High | Explicit allowlist projection and serialization assertions |
| Cursor SQL injection | High | Fixed SQL fragment, bound status/cursor values |
| Pagination duplicates rows | Medium | `(created_at, workflow_id)` tie-break and second-page test |
| Static gate report treated as live truth | Medium | Report release evidence separately; worker/schema/checkpoint checks remain independent |
| CLI retries create a second decision | Critical | Semantic deterministic decision ID |
| Reject reason leaks through shell history | High | File/stdin only |
| Container canary lacks auth | High | Explicit test-only canonical Tool Client key |
| Full suite and gate runner collide on Docker | High | Run serially |
| Manual recovery gets a force endpoint | Critical | Read-only diagnostic contract and OpenAPI assertion |

#### Performance and Capacity

- Queue pages are capped at 100 and default to 20.
- The existing status-leading workflow index bounds the filtered candidate set;
  a new queue index is deferred until measured queue volume proves it necessary.
- No endpoint scans evidence content for list results.
- Health uses cached startup compatibility results plus live task state; it does
  not rebuild a graph on every request.
- Single-node capacity remains the explicit supported boundary.

#### Security and Privacy

- Review auth is stricter than the legacy development middleware.
- Review list omits claim/evidence text and reasons.
- Review detail returns the reason only under strict review auth.
- Actor fingerprint, request hash, lease owner, checkpoint identity, paths, raw
  exceptions, and secrets remain hidden.
- The Tool Client accepts no API key argument.
- LangSmith remains correlation-only.

#### Two-PR Assessment

The split is valid:

- PR 1 is independently safe because the feature remains disabled by default and
  adds a complete authenticated read API plus startup validation.
- PR 2 adds the first-party operator surface and release evidence without
  changing persistence semantics.

PR 2 should branch from the accepted PR 1 head; the exact SHA must be recorded in
the verification report.

#### Engineering Completion Summary

Architecture, data flow, failure behavior, test paths, privacy, rollout, and
rollback are specified. No unresolved critical engineering gap remains in the
plan.

### Phase 3.5: Developer Experience Review

#### Primary Persona

The primary user is a local operator or automation developer with a configured
single-node service and a pending Talent review. The secondary user is the
maintainer diagnosing startup or recovery state.

#### Developer Journey

| Stage | Intended experience |
|---|---|
| 1. Discover | README links to one controlled review runbook |
| 2. Configure | Set flag, secret, two persistent DB paths, persistent output |
| 3. Verify | `doctor` distinguishes disabled, ready, and unready |
| 4. Find work | `review list` defaults to waiting reviews |
| 5. Inspect | `review show --run-id` resolves current review ID |
| 6. Decide | `review approve/reject`; reject reason uses file/stdin |
| 7. Wait | `--wait` or `review wait` returns terminal detail |
| 8. Consume | `result` and artifact APIs expose reviewed or blocked state |
| 9. Recover | Stable error code points to runbook; rollback is flag-first |

#### Developer Empathy Narrative

“I have a configured service and one pending Talent review. I should not need to
query SQLite, copy checkpoint IDs, or understand the worker internals. I want one
command to see pending work, one to inspect it, one to decide, and a bounded wait
that tells me whether the result is ready, blocked, or requires operator
recovery.”

#### DX Scorecard

| Dimension | Before | Planned | Evidence |
|---|---:|---:|---|
| Getting started | 5/10 | 8/10 | Single runbook and doctor |
| API naming | 6/10 | 9/10 | Review nouns and stable resource routes |
| CLI discoverability | 4/10 | 9/10 | Nested `review` command group |
| Error actionability | 6/10 | 9/10 | Structured problem/cause/fix codes |
| Security ergonomics | 6/10 | 9/10 | Environment-only key, safe reason input |
| Recovery clarity | 4/10 | 8/10 | Manual recovery and rollback procedures |
| Upgrade safety | 6/10 | 8/10 | Disabled default and two-PR rollout |
| Integration readiness | 6/10 | 9/10 | Stable API for future React consumer |

Overall: approximately `5.4/10 -> 8.6/10`.

#### TTHW

- Existing configured service: target under 5 minutes from `doctor` to resolved
  synthetic review.
- Cold dependency and Docker setup: measured separately; not mixed with operator
  workflow time.

#### DX Implementation Checklist

- [ ] `doctor` reports disabled as intentional, enabled-unready as failure.
- [ ] `review list` needs no IDs.
- [ ] `review show` can resolve `review_id` from `run_id`.
- [ ] Reject reason never requires a shell argument.
- [ ] `--wait` has bounded timeout and non-zero failure.
- [ ] JSON errors retain server `code/problem/cause/fix`.
- [ ] Runbook contains approve, reject, manual recovery, and rollback.
- [ ] Future React uses the same API and does not redefine workflow semantics.

#### DX Completion Summary

The planned CLI is consistent with the existing JSON-first Tool Client and has a
complete operator journey. Human-readable tables are optional future polish, not
a P1C requirement.

### Cross-Phase Themes

**Stable backend contract before UI** appears in CEO, Engineering, and DX review.
It is the highest-confidence decision in the plan.

**Fail-closed without overstating production readiness** appears in every phase:
startup, auth, immutable decisions, manual recovery, and single-node
documentation must remain aligned.

**Existing state-machine reuse** appears in CEO and Engineering review. P1C must
stay a productization layer, not a second durable workflow implementation.

### Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|---|---|---|---|---|---|
| 1 | CEO | Keep backend/CLI-only P1C | User-confirmed | Focus | Stabilizes product contract before React | Build Vue review UI |
| 2 | CEO | Keep immutable approve/reject | User-delegated | Simplicity | Preserves audit and recovery semantics | Withdraw/amend decision |
| 3 | CEO | Require new run after rejection | Auto-decided | Explicitness | Avoids hidden research side effects | Auto-rerun |
| 4 | Eng | Use actual write probe | Auto-decided | Verified facts | `os.access` is insufficient | Permission-bit check only |
| 5 | Eng | Check live worker task | Auto-decided | Completeness | Cached boolean can become stale | Startup-only running flag |
| 6 | Eng | Keep queue projection bounded | Auto-decided | Privacy | Discovery does not need claim text | Full bundle in list |
| 7 | Eng | Keep fixed cursor SQL | Auto-decided | Security | Values remain bound parameters | Dynamic caller SQL |
| 8 | Eng | Inject test-only CLI key in canary | Auto-decided | Explicitness | Tool Client must not read server secret | API_SECRET fallback |
| 9 | Eng | Pass reject reason through stdin | Auto-decided | Security | Avoids shell history and command composition | Plain `--reason` |
| 10 | Eng | Do not add queue index yet | Auto-decided | YAGNI | Bounded single-node queue lacks measured bottleneck | Premature migration |
| 11 | DX | Keep JSON-first CLI | Auto-decided | Consistency | Matches existing client and automation use | New table renderer |
| 12 | DX | Treat disabled doctor state as healthy | Auto-decided | Safe defaults | Feature is intentionally off by default | Make default install fail |

### Review Scores

- CEO: GO, focused product milestone with no required expansion.
- Design: skipped, no UI scope.
- Engineering: GO after seven plan corrections; no unresolved critical gap.
- DX: `8.6/10` planned, configured-service TTHW target under 5 minutes.
- Claude voice: unavailable due `429`.
- Independent Codex voice: unavailable due usage limit.
- Consensus: unavailable; no disagreement inferred.

### Implementation Tasks Aggregated Across Phases

- [ ] Runtime config and live worker readiness: Task 1.
- [ ] Deterministic bounded queue/detail projections: Task 2.
- [ ] Strict-auth list/detail/health API: Task 3.
- [ ] PR 1 API/data contract closure: Task 4.
- [ ] Structured HTTP errors and read CLI: Task 5.
- [ ] Immutable approve/reject CLI: Task 6.
- [ ] Wait, doctor, and Docker canary: Task 7.
- [ ] Operator docs, 13-gate rerun, full closure: Task 8.

### Final Autoplan Gate

**Status:** APPROVED by project owner on 2026-06-20.

No user challenge or unresolved taste decision remains. The corrected plan is
the implementation baseline.
