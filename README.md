[English](./README.md) | [中文](./README_CN.md)

# Deep Search Agent

A multi-source information collection and report generation Agent built on LangGraph / DeepAgents. It supports main-agent autonomous planning, sub-agent delegation, WebSocket status streaming, session isolation, token usage tracking, and Docker deployment — for enterprise knowledge retrieval, data querying, and automated research report generation.

## Architecture

```
User Question
    │
    ▼
┌──────────────────────────────────────────────────────┐
│              Main Agent (LangGraph Planner)          │
│  - Autonomous task decomposition                     │
│  - Sub-agent delegation via DeepAgents `task` tool   │
│  - File system context management (ContextVar)       │
│  - Report synthesis (Markdown / PDF)                 │
├──────────────┬──────────────────┬────────────────────┤
│ Network      │ Database         │ Knowledge Base     │
│ Search Agent │ Query Agent      │ (RAG) Agent        │
│ (Tavily)     │ (MySQL)          │ (RAGFlow)          │
└──────────────┴──────────────────┴────────────────────┘
    │              │                    │
    ▼              ▼                    ▼
  Internet       Business           Enterprise
  Search         Data               Knowledge
```

**Data flow:**
1. User submits a question via REST API or WebSocket
2. Main Agent analyzes the question and creates an execution plan
3. Specialized sub-agents are dispatched with isolated contexts
4. Results are synthesized into Markdown/PDF reports
5. Progress streams to the frontend via WebSocket in real time

## End-to-End Task Walkthrough

> Numbers below are illustrative examples of the output format, not benchmark results.

```
User: "调研 AI 在医疗诊断中的应用趋势，生成 PDF 报告"

  ↓ Main Agent plans
  ├── [Network Search Agent] → Tavily search: "AI medical diagnosis trends 2024"
  │                              Tavily search: "AI radiology deep learning"
  │                              → Collects search results
  ├── [Database Query Agent]  → MySQL: SELECT recent medical-AI papers count
  │                              → Returns query results
  └── [Knowledge Base Agent]  → RAGFlow: retrieve internal medical-AI reports
                                 → Returns relevant documents
  ↓
  Main Agent synthesizes → report.md → report.pdf
  ↓
  WebSocket events streamed to frontend in real time
```

> **Note**: Evidence table data comes from Task 1 actual command output. If numbers differ on re-run, Task 1 output takes precedence.

## Evidence

| Metric | Value | Source |
|--------|-------|--------|
| Local pytest run | 264 passed, 0 failed | `pytest -q` |
| Docker deployment | Verified on localhost | [QA Report](docs/evidence/assets/qa-report-summary.md) |
| Frontend build | Passed | `cd frontend && npm run build` |
| E2E Run #1 | 282s, 459K tokens, 2 sub-agents, report.md generated | [Run Log](docs/evidence/run-log.md) |
| Token tracking | Implemented (Phase 7c) | `agent/token_tracking.py`, `GET /api/token-usage/{thread_id}` |
| TTL caching | Implemented (Phase 7c) | `tools/cache.py`, Tavily 300s TTL |
| API Key auth | Implemented (Phase 8) | `api/server.py`, `APIKeyMiddleware` |
| SQLite persistence | Implemented (Phase 8) | `api/persistence.py`, `GET /api/tasks/{thread_id}` |
| Search dedup | Implemented (Phase 8) | `tools/tavily_tools.py`, `search_with_dedup` |
| CI/CD | Configured (Phase 8) | `.github/workflows/ci.yml` |

> All metrics above are from actual command runs on this machine. Token/cost benchmark data and P95 latency are pending dedicated benchmark runs.

## Key Engineering Decisions

### ContextVar Session Isolation

Concurrent API requests share the same Python process. Without isolation, global state (current thread_id, workspace path, LLM callbacks) would bleed between requests. We use `contextvars.ContextVar` to attach session-scoped state to each async task, ensuring request A's workspace never touches request B's files.

See: [`api/context.py`](api/context.py)

### YAML Prompt Configuration

Agent system prompts live in `prompt/prompts.yml` instead of Python string literals. This separates prompt content from code, enables version-controlled prompt iteration without touching Python files, and allows non-developers to review/edit prompts.

### WebSocket over Polling

The agent execution produces many intermediate events (tool calls, sub-agent dispatches, reasoning steps). Polling would waste bandwidth and introduce latency. WebSocket pushes each event as it happens, giving the frontend real-time visibility into the agent's planning process.

### Retry, Timeout, Cache, Token Tracking

Tavily and RAGFlow calls are wrapped with timeout policies and retry decorators with exponential backoff. MySQL connections use connect_timeout and read_timeout. Tavily search results use TTL caching (300s). Token tracking via LangChain `BaseCallbackHandler` records input/output/total tokens per LLM call with cost estimation. These make the system observable and resilient to transient failures.

See: [`tools/cache.py`](tools/cache.py), [`agent/token_tracking.py`](agent/token_tracking.py), [`tools/retry_utils.py`](tools/retry_utils.py)

### Upload/Download Path Security

File uploads use filename sanitization (strip directory components, Windows path handling) and length validation. Download paths are resolved through a virtual-path cleaning mechanism that prevents `../` traversal, limiting the risk of out-of-bounds file access.

See: [`api/upload_security.py`](api/upload_security.py), [`utils/path_utils.py`](utils/path_utils.py)

## Quick Start

### Prerequisites

- Python >= 3.11
- Node.js 20.19+ or 22.12+
- Tavily API key
- DashScope API key

### 1. Install Backend Dependencies

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Fill in your API keys
```

### 3. Run

```bash
# Start the backend
python api/server.py

# In another terminal, start the frontend
cd frontend
npm install && npm run dev
```

API endpoints:
- **POST /api/task** — Start an agent task
- **POST /api/upload** — Upload files for analysis
- **GET /api/files** — List generated files
- **GET /api/download** — Download generated files
- **GET /api/token-usage/{thread_id}** — View token usage for a thread
- **WebSocket /ws/{thread_id}** — Real-time reasoning stream

WebSocket events: `session_created`, `tool_start`, `assistant_call`, `task_result`, `error`

## Project Structure

```
deep-search-agent/
├── agent/
│   ├── main_agent.py              # Main agent orchestration
│   ├── llm.py                     # LLM factory with callback support
│   ├── prompts.py                 # YAML prompt config loader
│   ├── token_tracking.py          # LangChain callback for token tracking
│   ├── telemetry.py               # Telemetry recording
│   └── sub_agents/
│       ├── network_search_agent.py
│       ├── database_query_agent.py
│       └── knowledge_base_agent.py
├── tools/
│   ├── tavily_tools.py            # Search with TTL caching
│   ├── mysql_tools.py             # Database query tools
│   ├── ragflow_tools.py           # RAGFlow knowledge base tools
│   ├── cache.py                   # TTL cache + @cached_tool decorator
│   ├── retry_utils.py             # Retry decorator with backoff
│   ├── markdown_tools.py          # Report generation
│   └── upload_file_read_tool.py   # File reading (PDF, Word, Excel, text)
├── api/
│   ├── server.py                  # FastAPI server (REST + WebSocket)
│   ├── monitor.py                 # Real-time progress monitor
│   └── context.py                 # ContextVar session isolation
├── utils/
│   ├── path_utils.py              # Path security helpers
│   └── word_converter.py          # PDF 转换（weasyprint 引擎）
├── prompt/
│   └── prompts.yml                # Agent system prompts
├── tests/
│   └── unit/                      # 单元测试（见 Evidence 表格）
├── frontend/                      # Vue 3 frontend
├── docs/                          # Product docs
├── spec/                          # Technical specifications
└── openspec/                      # OpenSpec change records
```

## Evidence Pack & Technical Docs

- [Evidence Pack](docs/evidence/) — QA screenshots, run log, technical decisions
- [Evidence Readiness Design](docs/superpowers/specs/2026-06-01-deep-search-agent-evidence-readiness-design.md) — Design spec for this documentation direction
- [Architecture Spec](spec/architecture.md) — System architecture and data flow
- [API Contract](spec/api-contract.md) — REST + WebSocket endpoint definitions

## Known Boundaries

- **WeasyPrint dependency**: PDF conversion tests require WeasyPrint system libraries (cairo, pango, gobject). On machines with dependencies available, tests run for real. On machines without them, conversion tests are skipped via `pytest.mark.skipif`, and the missing-dependency error path is tested via import-stage `OSError` simulation. Docker 环境已包含这些依赖。
- **Frontend build**: Verified (`cd frontend && npm run build` succeeded, built in 357ms).
- **API Key auth**: All `/api/*` endpoints are protected by `APIKeyMiddleware`. Requests without `X-API-Key` header get 401. Set `API_SECRET=your-key` in `.env` to enable; if unset, a warning is logged but all requests pass through (dev mode).
- **WebSocket auth**: Browser clients pass the key via the `api_key` query parameter because native WebSocket constructors cannot set custom headers. Production logs should avoid recording full WebSocket URLs.
- **Task state persistence**: Tasks are persisted to SQLite (`data/tasks.db`) through `api/persistence.py`. Server restart does not lose completed task records. Query by `GET /api/tasks/{thread_id}`.
- **CI/CD**: GitHub Actions runs backend tests and frontend build on push/PR to `main`. API keys must be configured in GitHub Secrets.
- **Benchmark data**: Pending dedicated benchmark run — 5 fixed queries defined in the Phase 8 spec. Token before/after comparison is not used as Phase 8 acceptance evidence because repeated E2E runs are currently nondeterministic.

## License

MIT
