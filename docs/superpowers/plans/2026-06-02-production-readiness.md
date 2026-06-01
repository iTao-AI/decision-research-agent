# Phase 8: Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把项目从"可验证的 demo"推进到"可稳定运行的服务"——token 效率优化、SQLite 持久化、API Key 鉴权、GitHub Actions CI/CD、benchmark 基准测试。

**Architecture:** 先鉴权（最小改动、立即生效），再持久化（新模块），然后 token 优化（分析→修改→验证），CI 配置，最后跑 benchmark 采集数据。

**Tech Stack:** Python 3.11+, FastAPI, SQLite (sqlite3), pytest, DeepSeek-chat, Vue 3 + Vite, GitHub Actions

**Source Spec:** `docs/superpowers/specs/2026-06-02-deep-search-agent-production-readiness-design.md`

**Allowed Files:**
- `api/server.py`, `api/persistence.py`
- `prompt/prompts.yml`
- `tools/tavily_tools.py` 或同等文件
- `.github/workflows/ci.yml`, `.env.example`
- `tests/unit/test_persistence.py`, `tests/unit/test_auth_middleware.py`, `tests/unit/test_search_dedup.py`, `tests/integration/test_task_endpoint.py`
- `frontend/src/` (API Key header injection)
- `docs/evidence/run-log.md`, `docs/evidence/README.md`, `docs/evidence/technical-decisions.md`
- `README.md`, `README_CN.md`

**Forbidden Files:**
- `docs/prd.md`, OpenSpec archive, `frontend/node_modules/`, 无关 Agent 功能/Prompt 策略

---

### Task 1: .env.example 增加 API_SECRET

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: 编辑 .env.example**

在 `.env.example` 中 `# Frontend Origin` 行之前插入：

```bash
# API Authentication
API_SECRET=your-secret-key
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "chore: add API_SECRET to .env.example"
```

---

### Task 2: API Key 鉴权 Middleware

**Files:**
- Modify: `api/server.py:29-43`
- Create: `tests/unit/test_auth_middleware.py`

- [ ] **Step 1: 写鉴权测试（TDD — red）**

```python
"""Test API Key authentication middleware."""
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def auth_app():
    """Create a test app with auth middleware loaded."""
    # Avoid side effects on the real app — test the middleware directly
    from api.server import app
    return app


class TestAuthMiddleware:
    """Test X-API-Key middleware behavior."""

    def test_no_key_returns_401(self):
        """Request without X-API-Key header returns 401."""
        os.environ["API_SECRET"] = "test-key"
        from api.server import app
        client = TestClient(app)
        response = client.get("/api/files?path=/nonexistent")
        assert response.status_code == 401
        body = response.json()
        assert "API_SECRET" in body.get("detail", "")

    def test_wrong_key_returns_401(self):
        """Wrong API key returns 401."""
        os.environ["API_SECRET"] = "test-key"
        from api.server import app
        client = TestClient(app)
        response = client.get(
            "/api/files?path=/nonexistent",
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 401

    def test_correct_key_passes(self):
        """Correct API key passes through to endpoint logic."""
        os.environ["API_SECRET"] = "test-key"
        from api.server import app
        client = TestClient(app)
        response = client.get(
            "/api/files?path=/nonexistent",
            headers={"X-API-Key": "test-key"},
        )
        # 404 not found (directory doesn't exist) — NOT 401
        assert response.status_code != 401

    def test_api_secret_not_set_warns_and_passes(self):
        """If API_SECRET is not in env, log warning and skip auth."""
        if "API_SECRET" in os.environ:
            del os.environ["API_SECRET"]
        from api.server import app
        client = TestClient(app)
        response = client.get("/api/files?path=/nonexistent")
        # Should not be 401 when auth is disabled
        assert response.status_code != 401

    def test_websocket_protected(self):
        """WebSocket connection with wrong key is rejected."""
        os.environ["API_SECRET"] = "test-key"
        from api.server import app
        client = TestClient(app)
        # WebSocket without proper key should fail
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/test-thread"):
                pass
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/unit/test_auth_middleware.py -v`
Expected: All 5 tests FAIL (middleware not implemented yet)

- [ ] **Step 3: 实现 auth middleware**

在 `api/server.py` 中，在 `app = FastAPI(...)` 之后、`output_dir` 之前加入：

```python
import os
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware that checks X-API-Key header against API_SECRET in .env."""

    async def dispatch(self, request: Request, call_next):
        # Skip auth for docs and health endpoints
        if request.url.path in ("/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        api_secret = os.environ.get("API_SECRET", "")
        if not api_secret:
            logging.warning(
                "API_SECRET is not set — all requests are accepted without authentication. "
                "Set API_SECRET=your-key in .env to enable API key protection."
            )
            return await call_next(request)

        client_key = request.headers.get("X-API-Key", "")
        if client_key != api_secret:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=401,
                content={"detail": "请设置 API_SECRET（在 .env 中）并通过请求头 X-API-Key 传递正确的密钥"},
            )

        return await call_next(request)


app.add_middleware(APIKeyMiddleware)
```

- [ ] **Step 4: 运行鉴权测试确认通过**

Run: `python -m pytest tests/unit/test_auth_middleware.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add api/server.py tests/unit/test_auth_middleware.py
git commit -m "feat: add API Key auth middleware (P2)

问题: API 端点完全开放，任何人可触发 DeepSeek 调用。
方案: FastAPI middleware 检查 X-API-Key 请求头，匹配 .env 中的
API_SECRET。API_SECRET 未设置时打印警告并接受所有请求。"
```

---

### Task 3: 前端注入 API Key Header

**Files:**
- Modify: `frontend/src/` (App.vue 或 components/ 中的 API 调用)

- [ ] **Step 1: 定位前端 API 调用点**

Run:
```bash
grep -rn "fetch\|axios\|localhost:8000" frontend/src/ --include="*.ts" --include="*.vue" | head -20
```

根据输出定位所有对 `localhost:8000` 的 fetch 调用。

- [ ] **Step 2: 注入 X-API-Key header**

在每个 fetch 调用的 headers 中加入：

```javascript
headers: {
    'Content-Type': 'application/json',
    'X-API-Key': 'your-secret-key',  // 从环境变量或配置读取
}
```

如果是构建时注入（推荐），修改 `frontend/vite.config.ts` 加入 `define`：

```typescript
define: {
    'import.meta.env.VITE_API_SECRET': JSON.stringify(process.env.VITE_API_SECRET || ''),
}
```

前端代码中使用：
```javascript
'X-API-Key': import.meta.env.VITE_API_SECRET,
```

- [ ] **Step 3: 验证前端构建**

Run: `cd frontend && npm run build`
Expected: Build passes

- [ ] **Step 4: Commit**

```bash
git add frontend/src/ frontend/vite.config.ts
git commit -m "chore: inject X-API-Key header in frontend API calls"
```

---

### Task 4: SQLite 任务状态持久化

**Files:**
- Create: `api/persistence.py`
- Modify: `api/server.py`
- Create: `tests/unit/test_persistence.py`

- [ ] **Step 1: 写持久化测试（TDD — red）**

```python
"""Test SQLite persistence module."""
import pytest
import sqlite3
from pathlib import Path


@pytest.fixture
def db_path(tmp_path):
    """Create a temp SQLite database."""
    db = tmp_path / "test_tasks.db"
    yield str(db)
    if db.exists():
        db.unlink()


class TestPersistence:
    """Test api/persistence.py operations."""

    def test_init_db_creates_table(self, db_path):
        """init_db creates the tasks table if it doesn't exist."""
        from api.persistence import init_db
        conn = init_db(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_init_db_idempotent(self, db_path):
        """Calling init_db twice doesn't error."""
        from api.persistence import init_db
        conn1 = init_db(db_path)
        conn1.close()
        conn2 = init_db(db_path)
        conn2.close()

    def test_save_and_get_task(self, db_path):
        """Save a task and retrieve it by thread_id."""
        from api.persistence import init_db, save_task, get_task
        init_db(db_path)
        save_task(db_path, thread_id="test-001", query="测试查询")
        task = get_task(db_path, "test-001")
        assert task is not None
        assert task["thread_id"] == "test-001"
        assert task["query"] == "测试查询"
        assert task["status"] == "pending"

    def test_update_task_status(self, db_path):
        """Update task status from pending to completed."""
        from api.persistence import init_db, save_task, update_task
        init_db(db_path)
        save_task(db_path, thread_id="test-002", query="test")
        update_task(
            db_path,
            "test-002",
            status="completed",
            output_path="/output/report.md",
            token_usage_json='{"total": 1000}',
        )
        task = update_task.__wrapped__ if hasattr(update_task, '__wrapped__') else None
        # Use the module-level get_task instead
        from api.persistence import get_task as gt
        task = gt(db_path, "test-002")
        assert task["status"] == "completed"
        assert task["output_path"] == "/output/report.md"

    def test_get_nonexistent_task(self, db_path):
        """Querying a nonexistent thread returns None."""
        from api.persistence import init_db, get_task
        init_db(db_path)
        assert get_task(db_path, "nonexistent") is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/unit/test_persistence.py -v`
Expected: All tests FAIL (module not implemented)

- [ ] **Step 3: 实现 api/persistence.py**

```python
"""SQLite persistence for task state."""
import sqlite3
import threading
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict


# Thread-local connections for WAL mode safety
_local = threading.local()

DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "tasks.db"


def _get_db_path(db_path: str = None) -> str:
    path = db_path or os.environ.get("TASKS_DB_PATH", str(DEFAULT_DB_PATH))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


def init_db(db_path: str = None) -> sqlite3.Connection:
    """Initialize the tasks database and return a connection."""
    path = _get_db_path(db_path)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            thread_id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            output_path TEXT,
            token_usage_json TEXT,
            error_message TEXT
        )
    """)
    conn.commit()
    return conn


def save_task(
    db_path: str = None,
    thread_id: str = "",
    query: str = "",
    status: str = "pending",
) -> None:
    """Insert a new task record."""
    path = _get_db_path(db_path)
    conn = init_db(path)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO tasks (thread_id, query, status, created_at)
           VALUES (?, ?, ?, ?)""",
        (thread_id, query, status, now),
    )
    conn.commit()
    conn.close()


def update_task(
    db_path: str = None,
    thread_id: str = "",
    status: str = None,
    output_path: str = None,
    token_usage_json: str = None,
    error_message: str = None,
) -> None:
    """Update a task record. Only provided fields are updated."""
    path = _get_db_path(db_path)
    conn = init_db(path)
    now = datetime.now(timezone.utc).isoformat()
    sets = []
    params = []
    if status is not None:
        sets.append("status = ?")
        params.append(status)
        if status == "running":
            sets.append("started_at = ?")
            params.append(now)
        elif status in ("completed", "failed"):
            sets.append("completed_at = ?")
            params.append(now)
    if output_path is not None:
        sets.append("output_path = ?")
        params.append(output_path)
    if token_usage_json is not None:
        sets.append("token_usage_json = ?")
        params.append(token_usage_json)
    if error_message is not None:
        sets.append("error_message = ?")
        params.append(error_message)
    if not sets:
        return
    params.append(thread_id)
    conn.execute(
        f"UPDATE tasks SET {', '.join(sets)} WHERE thread_id = ?",
        params,
    )
    conn.commit()
    conn.close()


def get_task(db_path: str = None, thread_id: str = "") -> Optional[Dict]:
    """Retrieve a task by thread_id. Returns None if not found."""
    path = _get_db_path(db_path)
    conn = init_db(path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM tasks WHERE thread_id = ?", (thread_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)
```

- [ ] **Step 4: 运行持久化测试确认通过**

Run: `python -m pytest tests/unit/test_persistence.py -v`
Expected: 5 passed

- [ ] **Step 5: 集成到 server.py 任务生命周期**

在 `api/server.py` 的 `run_task` 函数中加入持久化调用：

```python
from api.persistence import save_task, update_task

@app.post("/api/task")
async def run_task(request: TaskRequest):
    """Start an agent task asynchronously."""
    thread_id = request.thread_id or str(uuid.uuid4())
    save_task(thread_id=thread_id, query=request.query, status="pending")
    create_tracked_task(run_deep_agent(request.query, thread_id), thread_id)
    # Mark as running
    update_task(thread_id=thread_id, status="running")
    return {"status": "started", "thread_id": thread_id}
```

在 WebSocket endpoint 中，收到 `task_result` 事件时更新完成状态。在 `_process_stream_chunk` 函数（如存在）或 equivalent 处加入：

```python
# When task completes successfully
update_task(
    thread_id=thread_id,
    status="completed",
    output_path=str(output_path),
)
```

添加任务查询端点：

```python
@app.get("/api/tasks/{thread_id}")
async def get_task_status(thread_id: str):
    """Get task status and metadata."""
    task = get_task(thread_id=thread_id)
    if task is None:
        return JSONResponse(status_code=404, content={"detail": "任务不存在"})
    return task
```

- [ ] **Step 6: 运行全量测试确认无回归**

Run: `python -m pytest -q`
Expected: All existing + new tests pass

- [ ] **Step 7: Commit**

```bash
git add api/persistence.py api/server.py tests/unit/test_persistence.py
git commit -m "feat: add SQLite task persistence (P1)

问题: 任务状态仅在内存中，服务器重启丢失进度。
方案: sqlite3 标准库实现 tasks 表，WAL 模式支持并发。
在任务创建/开始/完成生命周期中持久化状态。
新增 GET /api/tasks/{thread_id} 端点查询历史任务。"
```

---

### Task 5: Token 效率优化

**Files:**
- Modify: `prompt/prompts.yml`
- Modify: `tools/tavily_tools.py`
- Create: `tests/unit/test_search_dedup.py`

- [ ] **Step 1: 写搜索去重测试（TDD — red）**

```python
"""Test search query deduplication within a single task."""
import pytest


class TestSearchDedup:
    """Test that identical queries are not re-executed within same task."""

    def test_dedup_same_query_uses_cache(self):
        """Same query within a task returns cached result."""
        from tools.tavily_tools import search_with_dedup
        results_1 = search_with_dedup("AI trends 2024", thread_id="test-dedup")
        results_2 = search_with_dedup("AI trends 2024", thread_id="test-dedup")
        # Second call should return same result without calling API again
        assert results_1 == results_2

    def test_different_query_not_deduped(self):
        """Different queries should NOT be deduped."""
        from tools.tavily_tools import search_with_dedup
        results_1 = search_with_dedup("AI trends", thread_id="test-dedup-2")
        results_2 = search_with_dedup("quantum computing", thread_id="test-dedup-2")
        assert results_1 != results_2

    def test_dedup_scoped_per_thread(self):
        """Dedup cache is isolated per thread_id."""
        from tools.tavily_tools import search_with_dedup
        results_1 = search_with_dedup("AI trends", thread_id="thread-a")
        results_2 = search_with_dedup("AI trends", thread_id="thread-b")
        # Different threads should have separate caches
        assert id(results_1) != id(results_2)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/unit/test_search_dedup.py -v`
Expected: FAIL (import error or logic not implemented)

- [ ] **Step 3: 实现搜索去重**

在 `tools/tavily_tools.py` 中添加：

```python
# Per-thread search result cache
_search_cache: dict = {}  # {thread_id: {query: results}}


def search_with_dedup(query: str, thread_id: str = "default"):
    """Search with deduplication — same query per thread returns cached result."""
    if thread_id not in _search_cache:
        _search_cache[thread_id] = {}
    cache = _search_cache[thread_id]
    if query in cache:
        return cache[query]
    # Call the real search function
    result = tavily_search(query)  # existing function
    cache[query] = result
    return result


def clear_search_cache(thread_id: str = None):
    """Clear the search cache for a thread, or all threads if None."""
    if thread_id:
        _search_cache.pop(thread_id, None)
    else:
        _search_cache.clear()
```

- [ ] **Step 4: 运行搜索去重测试确认通过**

Run: `python -m pytest tests/unit/test_search_dedup.py -v`
Expected: 3 passed

- [ ] **Step 5: 精简 prompts.yml**

读取 `prompt/prompts.yml`，识别可精简的部分：
- 合并重复指令（子 Agent 调用路径被描述了 3 次）
- 移除"必须且只能在该工作目录下"的冗余强调
- 缩短子 Agent 描述（当前约 800 tokens，可压缩到 400）
- 保留所有功能性指令

精简后确保 E2E 测试（至少跑一次同一查询）可以看到 token 下降。

- [ ] **Step 6: 运行全量测试**

Run: `python -m pytest -q`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add tools/tavily_tools.py tests/unit/test_search_dedup.py prompt/prompts.yml
git commit -m "perf: optimize token efficiency with search dedup + prompt trim (P0)

问题: E2E Run #1 消耗 459K tokens/21 calls，有冗余搜索和冗长 prompt。
方案: 同一任务内相同 query 返回缓存结果；精简 prompts.yml
重复和冗余指令。"
```

---

### Task 6: E2E token 验证（before/after 对比）— Follow-up

**Files:**
- Modify: `docs/evidence/run-log.md`

- [ ] **Status: 暂缓执行**

多次同题 E2E 运行出现 459K 到 3M tokens 波动，且报告生成行为不稳定。在未修改的原始代码上重跑也出现无报告结果，因此当前数据不能作为可靠 before/after benchmark。

后续执行前必须先固定 WebSocket 客户端脚本、重复运行次数和统计口径（例如取中位数），再将结果追加到 `docs/evidence/run-log.md`。

---

### Task 7: GitHub Actions CI/CD

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: 创建 CI workflow**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  backend:
    name: Backend Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          OPENAI_BASE_URL: ${{ secrets.OPENAI_BASE_URL }}
          TAVILY_API_KEY: ${{ secrets.TAVILY_API_KEY }}
        run: python -m pytest -q

  frontend:
    name: Frontend Build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '18'
      - name: Install and build
        run: |
          cd frontend
          npm ci
          npm run build
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions CI pipeline (P3)

push 和 PR 时自动运行 backend pytest + frontend build。"
```

- [ ] **Step 3: Push 并验证 CI 通过**

Run: `git push origin main`
然后检查 GitHub Actions tab 确认两个 job 都通过。

---

### Task 8: Benchmark 基准测试 — Follow-up

**Files:**
- Modify: `docs/evidence/run-log.md`

- [ ] **Status: 暂缓执行**

待 E2E 随机性收敛后，按以下顺序逐个执行，并记录耗时、token、LLM calls、子 Agent、WebSocket events、报告大小：

1. "2024年人工智能发展趋势"
2. "量子计算最新突破"（单主题搜索）
3. "自动驾驶技术现状与未来"（技术对比类）
4. "latest advances in CRISPR gene editing 2024"（英文搜索）
5. "中国新能源汽车市场分析"（中文深度分析）

结果追加到 `docs/evidence/run-log.md`。本轮 benchmark 仍待后续采集。

---

### Task 9: 公开文档同步

**Files:**
- Modify: `README.md`, `README_CN.md`
- Modify: `docs/evidence/README.md`
- Modify: `docs/evidence/technical-decisions.md`

- [ ] **Step 1: 更新 README Evidence 表格**

更新 Known Boundaries：
- 添加 "API Key 鉴权已实现，请求需带 X-API-Key header"
- 添加 "任务状态通过 SQLite 持久化，服务器重启不丢失"
- 添加 "CI/CD: GitHub Actions 自动运行测试和构建"
- 添加 "Benchmark 仍待后续稳定脚本补充；不使用 token before/after 作为本轮验收证据"

相应的更新 `README_CN.md`。

- [ ] **Step 2: 更新 docs/evidence/README.md**

```markdown
| [run-log.md](run-log.md) | E2E Run #1 + Phase 8 收口状态；benchmark 仍待后续稳定脚本补充 |
```

- [ ] **Step 3: 更新 docs/evidence/technical-decisions.md**

在 "如果重做，会补什么" 后追加：

```markdown
## Phase 8 新增决策

### 为什么选 SQLite 而非 Redis
- Python 标准库自带 sqlite3，零额外依赖
- WAL 模式支持并发读写，单机部署足够
- 将来迁移到 PostgreSQL 成本极低（都是 SQL）
- Redis 需要在个人服务器上额外维护一个进程

### 为什么选 API Key 而非 JWT
- 个人部署不需要多用户、登录、注册流程
- 5 行 middleware 代码 vs JWT 需要密钥管理、过期策略、refresh token
- 面试时：这是明确的工程判断——选择简单方案而非过度设计
```

- [ ] **Step 4: 运行安全扫描和链接检查**

```bash
PUBLIC_SAFETY_PATTERNS='TBD|TODO'
rg -n "$PUBLIC_SAFETY_PATTERNS" README.md README_CN.md docs/README.md docs/evidence docs/superpowers/specs --glob '!docs/superpowers/plans/**'
```

Expected: 无命中

Run: Markdown 链接检查
Expected: 所有链接有效

- [ ] **Step 5: Commit**

```bash
git add README.md README_CN.md docs/evidence/README.md docs/evidence/technical-decisions.md
git commit -m "docs: sync public docs with Phase 8 production readiness

- Evidence 表格新增 E2E Run #2
- Known Boundaries: API Key / SQLite / CI 说明
- technical-decisions: SQLite vs Redis, API Key vs JWT 决策记录"
```

---

### Task 10: 全量验证

- [ ] **Step 1: 运行全部测试**

Run: `python -m pytest -q`
Expected: 247 + new tests → ~270 passed, 0 failed

- [ ] **Step 2: 前端构建**

Run: `cd frontend && npm run build`
Expected: Build passes

- [ ] **Step 3: 安全扫描**

```bash
PUBLIC_SAFETY_PATTERNS='TBD|TODO'
rg -n "$PUBLIC_SAFETY_PATTERNS" README.md README_CN.md docs/README.md docs/evidence docs/superpowers/specs --glob '!docs/superpowers/plans/**'
```

Expected: 无命中

- [ ] **Step 4: 检查 git status**

Run: `git status --short --branch`
Expected: 工作区干净，所有改动已提交

- [ ] **Step 5: 运行 git diff 检查**

Run: `git diff --cached --check`
Expected: 无 warning

---

## Verification Commands

```bash
# 1. 全量测试
python -m pytest -q

# 2. 前端构建
cd frontend && npm run build

# 3. 安全扫描
PUBLIC_SAFETY_PATTERNS='TBD|TODO'
rg -n "$PUBLIC_SAFETY_PATTERNS" README.md README_CN.md docs/README.md docs/evidence docs/superpowers/specs --glob '!docs/superpowers/plans/**'

# 4. 工作区状态
git status --short --branch
git diff --stat
```

## Handoff Notes

- P0（token 优化）代码已实现，但 E2E before/after 对比因模型随机性暂缓，不作为本轮验收证据
- P4（benchmark）5 个问题仍待后续稳定脚本执行
- CI/CD 首次 push 后需在 GitHub Settings → Secrets 配置 API keys
- `tests/` 目录需手动创建新测试文件
- `data/` 目录（tasks.db）已加入 .gitignore
