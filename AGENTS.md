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
agent/llm.py               — LLM initialization (DeepSeek official API via OpenAI-compatible client)
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

- `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `LLM_MODEL`, `LLM_FALLBACK_MODEL`, `LLM_REASONING_EFFORT`, `LLM_THINKING_MODE` — DeepSeek official API config
- `LLM_QWEN_MAX` — Legacy model variable, used only when `LLM_MODEL` is not set
- `TAVILY_API_KEY` — Network search
- `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`, `MYSQL_PORT` — Database
- `RAGFLOW_API_URL`, `RAGFLOW_API_KEY` — Knowledge base

## Frontend

Vue 3 + TypeScript + Vite. Entry: `frontend/src/main.ts` → `frontend/src/App.vue`. Connects to backend via WebSocket for real-time agent reasoning display and REST for file management.

## Codex Role

- Codex owns direction, planning review, and final independent acceptance.
- Claude Code owns implementation, TDD discipline, implementation subagents, and near-field fixes.
- Codex must not claim tests, builds, QA, performance, or review passed unless actual command output supports the claim.
- Codex must not commit, push, create PRs, ship, deploy, install tools, or modify user-level agent files unless the user explicitly asks.

## Skill Trigger Naming

- Codex Superpowers skills use namespaced handles such as `superpowers:brainstorming`, `superpowers:writing-plans`, and `superpowers:verification-before-completion`.
- Codex GStack skills use `gstack-<skill-name>` handles such as `gstack-office-hours`, `gstack-autoplan`, `gstack-review`, `gstack-qa-only`, `gstack-investigate`, and `gstack-ship`.
- Claude Code uses different skill names. Do not copy Claude-side skill trigger lines into Codex instructions without translating them.

## Claude Execution Handoff

- If `subagent-driven-development` is active in Claude Code, the activated skill procedure owns execution order; do not manually execute plan tasks just because the plan is detailed.
- Claude main controller owns task extraction, context packaging, `SUPERPOWERS_GATE`, and evidence acceptance.
- Implementation subagents own task-local RED/GREEN work when dispatched with full task text, allowed files, RED/GREEN commands, expected evidence, and stop conditions.
- If `CLAUDE.md` is ignored or local-only, worktree sessions must copy, regenerate, or explicitly include Claude-facing rules before implementation.
- If tool calls fail 3 consecutive times with missing/empty parameters or malformed invocation, stop manual execution and switch to a fresh subagent or new session.

## Planning Flow

When planning is required, use this Codex-facing sequence:

```text
gstack-office-hours
superpowers:brainstorming
superpowers:writing-plans
gstack-autoplan
Codex locks the plan
```

`gstack-office-hours` 只用于方向不清或产品取舍。小任务可跳过。

`superpowers:writing-plans` 在 `gstack-autoplan` 之前；`gstack-autoplan` 审查已有 plan。

## Final Acceptance Flow

Before final acceptance, Codex must review:

- Source spec
- Implementation plan
- Claude execution evidence
- `@agent-gstack-fixfirst-reviewer` output, if the agent is available
- Git diff
- Actual command output

Recommended Codex-facing sequence:

```text
gstack-review
gstack-qa-only or gstack-qa when needed
superpowers:verification-before-completion
gstack-investigate only when failure or ambiguity remains
gstack-ship only when the user explicitly asks to ship
superpowers:finishing-a-development-branch when integration guidance is needed
```

## PR Body 格式

PR body 按以下结构编写。核心原则是先给 reviewer 明确完成状态，再展开实现和验证；不要把未完成项藏在 Test plan 末尾。

**Summary** — 必写，用 1 段说明这次 PR 改了什么、为什么改、带来什么价值。

**Completion status** — 必写，用 checkbox 明确完成 / 未完成状态：
- `[x]` 已完成的核心任务、文档同步和验证。
- `[ ] Not completed: ...` 尚未完成但和 PR 范围相关的工作，并说明原因。

**Implementation details** — 必写，列出关键文件变更，每条 1 句。

**Verification** — 必写，列出实际运行的检查和结果；未运行的检查写 `Not run: <check>` 并说明原因。

**Risk / Impact** — 涉及 API、数据结构、持久化、兼容性或用户行为变化时必写：
- User impact
- System impact
- Compatibility impact
- Rollback plan

**Design choices** — 涉及技术选型时写，格式：Option | Decision | Reason。

**Review focus** — 推荐写，列出希望 reviewer 重点看的 2-4 个问题。

**Breaking Changes** — 仅当有破坏性变更时写，说明影响和迁移方式。
