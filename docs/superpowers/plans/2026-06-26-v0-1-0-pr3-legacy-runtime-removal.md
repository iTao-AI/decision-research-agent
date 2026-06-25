# v0.1.0 PR3 Legacy Runtime Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Coding
> subagents are disabled by repository policy. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Delete the duplicated task/thread runtime, old technical identity,
compatibility aliases, and Vue frontend after canonical run delivery and
consumer smoke are proven.

**Architecture:** Use one canonical database resolver and one run-scoped API.
Provide explicit backup/export/drop tooling for old tables, but retain no
runtime alias, forwarding route, tombstone endpoint, or hidden legacy flag.

**Tech Stack:** Python 3.11, FastAPI, SQLite WAL, Docker Compose, pytest.

---

## Delivery Boundary

Included:

- task/thread route and persistence deletion;
- old Tool Client command and shim deletion;
- canonical env/database/health/MySQL/pool identifiers;
- explicit legacy database archive/drop command;
- Vue, Nginx, frontend Compose/CI deletion;
- active-surface canonical identity scan;
- current contracts and ADR updates.

Excluded:

- React;
- historical Git/spec/evidence/trace rewrites;
- automatic destructive DB table drops;
- release tag and GitHub Release.

## Task 1: Introduce the Canonical Database Resolver

**Files:**

- Create: `api/database.py`
- Create: `tests/unit/test_database_config.py`
- Modify: all canonical repositories/configuration that import
  `api.persistence._get_db_path`

- [ ] **Step 1: Write resolver RED tests**

```python
def test_database_path_uses_only_canonical_env(monkeypatch, tmp_path):
    canonical = tmp_path / "decision_research_agent.db"
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(canonical))
    monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "ignored.db"))
    assert application_db_path() == canonical.resolve()


def test_old_env_alone_is_not_read(monkeypatch, tmp_path):
    monkeypatch.delenv("DECISION_RESEARCH_AGENT_DB_PATH", raising=False)
    monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "old.db"))
    assert application_db_path().name == "decision_research_agent.db"
```

- [ ] **Step 2: Run RED**

```bash
../../.venv/bin/python -m pytest tests/unit/test_database_config.py -q
```

- [ ] **Step 3: Implement resolver**

Default:

```python
DEFAULT_APPLICATION_DB_PATH = (
    PROJECT_ROOT / "data" / "decision_research_agent.db"
)
```

Read only `DECISION_RESEARCH_AGENT_DB_PATH`. Ensure parent exists. Keep
`:memory:` support only for explicit test arguments, not runtime review
configuration.

- [ ] **Step 4: Migrate imports and readiness**

Update `api/run_repository.py`, review/publication/verification repositories,
`api/review_config.py`, migrations, scripts, tests, Compose, and `.env.example`.
Delete all runtime reads of `TASKS_DB_PATH`.

- [ ] **Step 5: Run GREEN and commit**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_database_config.py \
  tests/unit/test_run_repository.py \
  tests/unit/test_review_config.py \
  tests/unit/test_run_migrations.py -q
git commit -m "refactor(storage): use canonical application database"
```

## Task 2: Delete Legacy Task Persistence and Routes

**Files:**

- Modify: `api/server.py`
- Delete: `api/persistence.py`
- Delete: `api/task_finalizer.py`
- Delete legacy-only tests.
- Modify run/API/telemetry/token/WebSocket contract tests.

- [ ] **Step 1: Write absence RED tests**

Assert normal `404` for:

```text
POST /api/task
GET /api/tasks/{thread_id}
GET /api/research/runs
GET /api/research/runs/{thread_id}
GET /api/telemetry/{thread_id}
GET /api/token-usage/{thread_id}
WS /ws/{thread_id}
POST /api/upload
GET /api/download
```

Keep:

```text
/api/runs*
/api/telemetry/runs/{run_id}
/api/token-usage/runs/{run_id}
/ws/runs/{run_id}
```

- [ ] **Step 2: Run RED**

```bash
../../.venv/bin/python -m pytest \
  tests/integration/test_api_endpoints.py \
  tests/unit/test_telemetry_api.py \
  tests/unit/test_token_tracking.py -q
```

- [ ] **Step 3: Delete legacy server code**

Remove:

- `TaskRequest`;
- `_run_task_with_persistence`;
- task timeout/finalization callbacks;
- `active_run_threads` and its lock/helpers;
- `updated_dir`, `output_dir`, upload/download contracts, and host directory
  coupling;
- imports from deleted persistence/finalizer modules;
- thread-grouped telemetry/token/WS handlers.

Do not add a replacement upload endpoint in this PR. File ingestion is deferred
to the future React/API design.

- [ ] **Step 4: Delete modules/tests and run GREEN**

```bash
../../.venv/bin/python -m pytest \
  tests/integration/test_api_endpoints.py \
  tests/integration/test_run_api.py \
  tests/integration/test_run_auxiliary_isolation.py \
  tests/unit/test_telemetry_api.py \
  tests/unit/test_token_tracking.py -q
```

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(api): remove legacy task runtime"
```

## Task 3: Remove Tool Client and Environment Compatibility

**Files:**

- Modify: `tools/decision_research_agent_tool.py`
- Delete: `tools/deep_search_agent_tool.py`
- Delete: `agent/runtime_env.py`
- Delete/modify corresponding tests.
- Modify: `.env.example`

- [ ] **Step 1: Write CLI/env absence RED tests**

Assert parser rejection for:

```text
start-task
get-task
token-usage --thread-id
research-run
research-runs
```

Assert only:

```text
DECISION_RESEARCH_AGENT_URL
DECISION_RESEARCH_AGENT_API_KEY
DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS
DECISION_RESEARCH_AGENT_DB_PATH
```

are read. Old env values must not trigger warnings because the resolver is
deleted; they are simply ignored.

- [ ] **Step 2: Run RED**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_decision_research_agent_tool.py \
  tests/unit/test_runtime_env.py \
  tests/unit/test_deep_search_agent_tool.py -q
```

- [ ] **Step 3: Delete commands, functions, shim, resolver, and tests**

Keep healthcheck, doctor, run, result, review, and Evidence commands.

- [ ] **Step 4: Run GREEN and commit**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_decision_research_agent_tool.py \
  tests/unit/test_env_centralization.py -q
git commit -m "refactor(cli): remove legacy client contracts"
```

## Task 4: Add Explicit Legacy Database Retirement

**Files:**

- Create: `scripts/retire_legacy_database.py`
- Create: `tests/unit/test_retire_legacy_database.py`
- Modify: `docs/operations/` migration guide.

- [ ] **Step 1: Write migration RED tests**

Cover:

- source verify;
- byte backup;
- export `tasks`, `research_runs`, `evidence_entries` to archival SQLite;
- no drop without `--drop-legacy-tables`;
- drop with explicit flag;
- canonical schema/foreign-key verification;
- restore on failure;
- existing backup conflict fails closed;
- idempotent verify-only rerun.

- [ ] **Step 2: Run RED**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_retire_legacy_database.py -q
```

- [ ] **Step 3: Implement CLI**

Required arguments:

```text
--database
--backup
--archive
--drop-legacy-tables
```

Never infer permission to drop. Print bounded JSON status without row content
or absolute paths.

- [ ] **Step 4: Run GREEN and commit**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_retire_legacy_database.py \
  tests/unit/test_run_migrations.py -q
git commit -m "feat(storage): retire legacy database tables safely"
```

## Task 5: Remove Vue and Frontend Infrastructure

**Files:**

- Delete: `frontend/`
- Delete: `Dockerfile.frontend`
- Delete: `nginx.conf`
- Modify: `docker-compose.yml`
- Modify: `.github/workflows/ci.yml`
- Modify: `.dockerignore`
- Remove Vue screenshots/current UI guidance from active docs.

- [ ] **Step 1: Write repository RED checks**

Add a test that fails while any of these exist:

```text
frontend/
Dockerfile.frontend
nginx.conf
frontend CI job
frontend Compose service
```

- [ ] **Step 2: Run RED**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_canonical_identity.py -q
```

- [ ] **Step 3: Delete frontend and update deployment**

Compose exposes backend and MySQL only. Remove `backend_output` if no active
runtime writes host reports after PR1/PR2.

- [ ] **Step 4: Run backend Docker build**

```bash
docker compose build backend
docker compose config
```

Expected: no frontend service, Dockerfile, Nginx, Node cache, or port 80.

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(frontend): retire legacy Vue application"
```

## Task 6: Canonicalize Active Technical Identity

**Files:**

- Create: `scripts/check_canonical_identity.py`
- Create: `tests/unit/test_canonical_identity.py`
- Modify: active code/config/tests/docs/ADR/Compose/MySQL defaults/pool labels.

- [ ] **Step 1: Encode exact active-surface scan**

Reject:

```text
deep-search-agent
Deep Search Agent
deep_search_agent
deep_search
DEEP_SEARCH_AGENT_
deep_search_agent_tool
TASKS_DB_PATH
/api/task
/api/tasks/
/api/research/runs
```

Allow only path-specific historical files. Do not add wildcard exclusions.

- [ ] **Step 2: Change exact health payload**

```json
{"status":"ok","service":"decision-research-agent"}
```

Rename MySQL defaults to `decision_research`; require operator-supplied
password. Rename pool labels.

- [ ] **Step 3: Run RED/GREEN scan**

```bash
../../.venv/bin/python scripts/check_canonical_identity.py
../../.venv/bin/python -m pytest \
  tests/unit/test_canonical_identity.py \
  tests/unit/test_health_endpoint.py \
  tests/unit/test_mysql_connection_manager.py -q
```

- [ ] **Step 4: Update active contracts/ADRs**

Update `docs/decisions/product-naming.md`,
`docs/decisions/run-identity-boundaries.md`, `spec/api-contract.md`,
`spec/architecture.md`, `spec/data-models.md`, and current operations docs.
Historical documents remain unchanged.

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(identity): remove legacy product contracts"
```

## PR3 Final Gate

```bash
../../.venv/bin/python scripts/check_canonical_identity.py
../../.venv/bin/python -m pytest -q
docker compose config
docker compose build backend
git diff --check
```

Required:

- removed routes return normal `404`;
- canonical run/result/review/verification flows pass;
- no old env or Tool Client shim is read/imported;
- new runtime never reads/writes old task tables;
- archive/drop recovery tests pass;
- no Vue/frontend source, CI, Compose, docs, or screenshots remain active;
- first-party consumer smoke still passes with canonical health identity;
- worktree clean after commits.
