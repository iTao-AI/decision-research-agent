# Design: Deep Search Agent Production Readiness

生成日期：2026-06-02
状态：Draft
用途：Superpowers writing plan 输入，供 Claude Code 执行 Phase 8 生产就绪优化

## Summary

本设计定义 Deep Search Agent 的 Phase 8 生产就绪优化。在验证闭环（260 passed, E2E Run #1 完成）的基础上，通过 token 效率优化、任务状态持久化、API 鉴权、CI/CD 自动化和 benchmark 基准测试，把项目从"可验证的 demo"推进到"可稳定运行的服务"。

本轮输出面向后续 `superpowers:writing-plans`。计划生成后可交给 Claude Code 执行。

## Goals

- 优化 token 使用效率，兼顾效果和查询质量，不设具体成本目标但应有可测量的改善
- 引入 SQLite 持久化任务状态，服务器重启后任务不丢失
- 引入 API Key 鉴权，防止未授权调用消耗 API 额度
- 引入 GitHub Actions CI/CD，push 时自动跑测试和前端构建
- 用 5 个固定问题跑 benchmark，采集耗时、token、子 Agent 调用和缓存命中率

关键路径 P0-P3 做生产级完整实现；P4 benchmark 做到可运行。

## Current Facts

以下事实来自 2026-06-02 的本机/代码检查。

- 当前在 main 分支，已同步 origin/main。
- `python -m pytest -q`：260 passed, 0 failed。
- `cd frontend && npm run build`：通过，built in ~100-400ms。
- E2E Run #1 已完成：282s, 459K tokens, $19.39, 21 LLM calls, 2 子 Agent, 50 WebSocket events。
- LLM 已从百炼切换到 DeepSeek（`deepseek-chat`），base URL `https://api.deepseek.com/v1`。
- Tavily API key 已配置。
- `.env` 文件在仓库根目录，包含所有敏感配置（API keys、数据库密码等）。
- 当前无任何鉴权机制，所有 API 端点开放。
- 当前无 CI/CD pipeline。
- 项目无 VERSION 文件、无 CHANGELOG.md。
- 任务状态仅在内存中（ContextVar），无持久化。

## Out of Scope

- 不新增子 Agent。
- 不迁移模型供应商。
- 不做云部署或 K8s。
- 不引入多用户系统或 OAuth。
- 不修改前端功能。
- 不写职业展示材料（留给后续 spec）。

## Execution Scope

### P0: Token 效率优化

**目标：** 优化 token 使用效率，兼顾查询效果，不设具体成本目标但应有可测量的 before/after 对比。

**当前基准（E2E Run #1）：** 459,265 tokens / 21 LLM calls / 2 子 Agent / $19.39

**允许方向：**

- 分析 `prompt/prompts.yml` 中的 system prompt，识别冗余指令、重复约束、可精简的示例
- 限制子 Agent 搜索查询数量（例如每个子 Agent 最多 3 次 Tavily 搜索）
- 检查 LLM 调用链路：定位 21 次调用中是否有不必要的重试或重复请求
- 引入搜索去重：同一任务中相同 query 不重复调 Tavily
- 如果 `token_tracking.py` 支持，按调用类型（planning / sub-agent / synthesis）分解 token 消耗，精确定位热点

**不允许方向：**

- 不换用更便宜的模型（保持 DeepSeek-chat）
- 不缩短或删除搜索结果内容（影响报告质量）
- 不把 Tavily 搜索改成静态数据（必须保留实时搜索能力）

**验收目标：**

- before/after 对比数据（同一问题跑两次，记录 token 差异）
- token 消耗有可测量的下降
- 报告质量不退化（人工对比生成内容）

### P1: SQLite 任务状态持久化

**目标：** 引入 SQLite 存储任务状态，服务器重启后不丢失任务记录。

**方案要点：**

- 使用 Python 标准库 `sqlite3`，零额外依赖
- WAL 模式（Write-Ahead Logging），支持并发读写
- 存储任务元数据：thread_id、状态（pending/running/completed/failed）、开始时间、结束时间、输入 query、输出路径
- 在 `api/context.py` 旁新建 `api/persistence.py`，封装 SQLite 操作
- 启动时自动创建表（`CREATE TABLE IF NOT EXISTS`），无需手动 migration
- 在 `api/server.py` 的任务生命周期钩子（start / complete / error）中调用持久化

**数据库设计：**

```sql
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
);
```

**验收目标：**

- 启动一个任务 → 重启服务器 → 能通过 API 查询到该任务的状态和结果
- 任务完成后数据库中有完整记录
- 不影响现有测试（260 passed）

### P2: API Key 鉴权

**目标：** 引入 API Key 保护所有 `/api/*` 端点，防止未授权调用。

**方案要点：**

- `.env` 中新增 `API_SECRET` 环境变量
- `.env.example` 同步包含 `API_SECRET=your-secret-key` 模板
- FastAPI middleware 检查请求头 `X-API-Key`，不匹配返回 401 + `{"detail": "请设置 API_SECRET（在 .env 中）并通过请求头 X-API-Key 传递"}`
- 服务器启动时如果 `API_SECRET` 未设置，打印警告日志但不拒绝请求（向后兼容开发环境）
- WebSocket `/ws/{thread_id}` 端点同样保护（在连接握手阶段检查）
- 前端调用 API 时自动附加 API Key（`frontend/` 修改 1-2 处 fetch 调用）

**验收目标：**

- 不带 Key 请求 → 401
- 带正确 Key 请求 → 正常响应
- WebSocket 连接同样受保护
- 不影响现有测试（测试中使用 fixture 注入 Key）

### P3: GitHub Actions CI/CD

**目标：** push 时自动运行测试和前端构建。

**方案要点：**

- 创建 `.github/workflows/ci.yml`
- 矩阵：Python 3.11+（项目要求的最低版本）
- 步骤：checkout → install deps → pytest → frontend build
- 不需要 Docker build（不是 web 服务部署）
- 不需要 deploy step（Vercel/Netlify 等暂不引入）

**CI 流程：**

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python -m pytest -q
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '18'
      - run: cd frontend && npm ci && npm run build
```

**验收目标：**

- push 到 GitHub 后 CI 自动触发
- pytest job 通过
- frontend build job 通过

### P4: Benchmark 基准测试

**目标：** 用 5 个固定查询采集系统性性能数据。

**方案要点：**

- 5 个固定问题覆盖不同场景：单关键词搜索、多源综合、中文深度、英文搜索、技术对比
- 每个问题记录：耗时、token（input/output/total）、LLM 调用次数、子 Agent 调用次数、WebSocket 事件数、生成报告大小
- 对比首次查询和重复查询的差异（验证 TTL 缓存命中）
- 输出追加到 `docs/evidence/run-log.md` 的 Benchmark 表格中

**5 个 benchmark 问题：**

1. "2024年人工智能发展趋势"（和 E2E Run #1 相同，做对比）
2. "量子计算最新突破"（单主题搜索）
3. "自动驾驶技术现状与未来"（技术对比类）
4. "latest advances in CRISPR gene editing 2024"（英文搜索）
5. "中国新能源汽车市场分析"（中文深度分析）

**验收目标：**

- 5 个问题全部执行完毕
- 每个问题有完整的指标记录
- before/after 表格可对比（问题 1 和 E2E Run #1 对比，验证 token 优化效果）

## Allowed Files

- `agent/` — token 追踪和 LLM 调用相关
- `api/server.py`, `api/context.py` — 鉴权和持久化
- `api/persistence.py` — 新建 SQLite 持久化模块
- `tools/` — 搜索去重、缓存相关
- `prompt/prompts.yml` — system prompt 优化
- `.github/workflows/ci.yml` — 新建 CI pipeline
- `docs/evidence/run-log.md` — benchmark 数据
- `docs/evidence/README.md`, `docs/evidence/technical-decisions.md` — 文档同步
- `README.md`, `README_CN.md` — 公开文档同步
- `tests/unit/test_persistence.py` — 新建 SQLite 持久化测试
- `tests/unit/test_auth_middleware.py` — 新建 API Key 鉴权测试
- `tests/unit/test_search_dedup.py` — 新建搜索去重测试
- `tests/integration/test_task_endpoint.py` — 新建任务端点集成测试
- `frontend/src/` — API Key 传参

## Forbidden Files

- `docs/prd.md`
- 无关 OpenSpec archive
- `frontend/node_modules/`
- 与 Phase 8 无关的 Agent 功能、Prompt 策略

## Acceptance Criteria

- `python -m pytest -q` 保持全绿（新增 persistence / auth middleware / search dedup / task endpoint 测试）
- `cd frontend && npm run build` 通过
- before/after token 对比有可测量的改善
- 不带 API Key → 401 + 友好提示（"请设置 API_SECRET"），带 Key → 正常
- 服务器启动时如果 API_SECRET 未设置，打印清晰警告
- 任务完成后重启服务器，可通过 `GET /api/tasks/{thread_id}` 查询到已完成任务
- CI 在 push 后自动通过
- Benchmark 5 个问题全部执行，数据写入 run-log.md
- 公开文档同步更新（Evidence 表格、Known Boundaries、技术决策）

## Review Plan

```bash
python -m pytest -q
cd frontend && npm run build
PUBLIC_SAFETY_PATTERNS='TBD|TODO'
rg -n "$PUBLIC_SAFETY_PATTERNS" README.md README_CN.md docs/README.md docs/evidence docs/superpowers/specs --glob '!docs/superpowers/plans/**'
git status --short --branch
git diff --stat
```
