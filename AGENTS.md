# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

Deep Search Agent is an autonomous planning agent built on LangGraph. Users ask open-ended questions in natural language; the main agent autonomously plans, delegates to specialized sub-agents (network search, database query, knowledge base retrieval), synthesizes results, and generates reports in Markdown/PDF format.

## Commands

### Backend (Python 3.11+)

```bash
# Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Start the backend server (FastAPI + Uvicorn on port 8000)
python api/server.py
```

### Frontend (Node.js 20.19+ or 22.12+)

```bash
cd frontend
npm install
npm run dev          # Start Vite dev server
npm run build        # Type-check + production build
```

### API Endpoints

- `POST /api/task` — Start an async agent task (returns thread_id)
- `POST /api/upload` — Upload files for analysis
- `GET /api/files?path=...` — List files in output directory
- `GET /api/download?path=...` — Download a generated file
- `WebSocket /ws/{thread_id}` — Real-time reasoning stream

## Architecture

### Core Layers

```
agent/main_agent.py        — LangGraph agent creation + async entry point (run_deep_agent)
agent/llm.py               — LLM initialization (Qwen-Max via DashScope)
agent/prompts.py           — YAML prompt config loader (prompt/prompts.yml)
agent/sub_agents/          — Three sub-agents: network_search, database_query, knowledge_base

tools/                     — All agent tools: tavily, mysql, ragflow, markdown, pdf, file_read
api/server.py              — FastAPI server (REST + WebSocket)
api/monitor.py             — ToolMonitor singleton + ConnectionManager for WebSocket events
api/context.py             — ContextVar-based session isolation (async-safe)
```

### Key Design Patterns

1. **ContextVar Session Isolation**: `api/context.py` uses `ContextVar` to isolate per-request workspace directories. Prevents data races when multiple requests run concurrently in the same event loop. Always set context before agent execution and reset in `finally`.

2. **Singleton ToolMonitor**: `api/monitor.py` provides a global `monitor` singleton. Tools report progress via `monitor.report_start()`, `monitor.report_running()`, `monitor.report_end()`. Events are emitted via WebSocket (if connected) or fallback to console.

3. **YAML Prompt Config**: Agent system prompts live in `prompt/prompts.yml`, not hardcoded. Loaded by `agent/prompts.py` into `main_agent_config` and `sub_agents_config`.

4. **Async Task Execution**: Agent tasks are launched via `asyncio.create_task()` in `api/server.py`. Progress is pushed through WebSocket using `monitor` events.

### Data Flow

1. User submits query → `POST /api/task` → `asyncio.create_task(run_deep_agent())`
2. `run_deep_agent()` creates session workspace, sets ContextVar, invokes LangGraph `main_agent.astream()`
3. Main agent decomposes tasks → delegates to sub-agents via `task` tool
4. Stream chunks processed by `_process_stream_chunk()` → events reported to frontend via WebSocket
5. Results written as Markdown/PDF in session workspace

## Environment Variables

Required in `.env` (copy from `.env.example`):

- `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `LLM_QWEN_MAX` — DashScope LLM config
- `TAVILY_API_KEY` — Network search
- `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`, `MYSQL_PORT` — Database
- `RAGFLOW_API_URL`, `RAGFLOW_API_KEY` — Knowledge base

## Frontend

Vue 3 + TypeScript + Vite. Entry: `frontend/src/main.ts` → `frontend/src/App.vue`. Connects to backend via WebSocket for real-time agent reasoning display and REST for file management.

## OpenSpec 工作流规则

本项目使用 OpenSpec SDD 工作流管理迭代。所有变更通过 `proposal → spec → tasks → apply → archive` 流程推进。

### 核心纪律

1. **先读后做**：执行任何 OpenSpec 命令前，先读取：
   - `openspec/config.yaml`（项目约束）
   - `openspec/specs/` 目录下相关域的规范（当前系统行为）
   - `openspec/changes/` 当前活跃的变更（如果存在）

2. **不要猜测需求**：如果 spec 中没有明确定义某个行为，问用户，不要自行补充。

3. **out-of-scope 是红线**：proposal.md 中标注为 out-of-scope 的功能，严禁实现。

### Apply 阶段规则

每个 task 完成后：
1. 自检（运行测试、验证 spec 对齐）
2. 有问题直接修复直到通过
3. 标记 `[x]`，commit
4. 直接进入下一个 task

严禁一次性实现所有任务，必须逐个 task 按 TDD 循环执行。

### Task 完成自检

每个 task 标记 `[x]` 前必须：
1. 运行该 task 相关的所有测试，确认全部通过
2. 验证实现与 delta spec 对齐
3. 运行已有测试，确认无回归

### 配置同步

当变更引入新约定时（如新的错误处理模式、新的架构模式），需同步更新：
- `openspec/config.yaml` — OpenSpec 工作流新约束
- 本项目 `AGENTS.md` — 项目级执行规则

具体判断标准见 `~/.Codex/skills/sdd-vibecoding/SKILL.md` 中的「配置维护指南」。

### 归档流程

PR 合并到 main 后，在 main 分支上执行 `/openspec-archive`。归档 commit 必须直接进入 main，禁止提前在 feature 分支上归档。

### Phase 4 强制门控（CRITICAL）

- **进入 Phase 4 后，必须先调用 `Skill("openspec-apply")`，再调用 `Skill("test-driven-development")`**
- **严禁跳过 skill 直接写代码或测试**
- 如果 skill 无法调用，必须向用户报告并等待手动触发指令

### PR Body 格式

### PR Body 格式

PR body 按以下结构编写（不适用的段可省略）：

**Summary** — 必写，按「问题 → 方案 → 价值」三段式：
- **问题**：现有痛点或缺失（1 句）
- **方案**：核心变更（1-2 句）
- **价值**：对用户或项目的收益（1 句；内部变更可省略）

**技术细节** — 必写，列出关键文件变更（每条 1 句）

**Test plan** — 必写，验证步骤清单

**设计选型** — 仅当涉及技术决策时写，格式：方案 | 选择 | 理由

**Breaking Changes** — 仅当有破坏性变更时写，说明影响和迁移方式
