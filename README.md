[English](./README.md) | [中文](./README_CN.md)

# Decision Research Agent

An evidence-driven research agent that gathers source-backed findings and turns them into decision-ready briefs. Built on LangGraph / DeepAgents, it combines autonomous planning, delegated research, auditable evidence capture, run-scoped persistence, and deterministic delivery contracts.

The repository and compatibility identifier remain `deep-search-agent` during the ongoing migration.

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
| Local pytest run | 303 passed, 0 failed | `PYTHONPATH=. pytest -q` |
| Docker deployment | Verified on localhost | [QA Report](docs/evidence/assets/qa-report-summary.md) |
| Frontend build | Passed | `cd frontend && npm run build` |
| E2E Run #1 | 282s, 459K tokens, 2 sub-agents, report.md generated | [Run Log](docs/evidence/run-log.md) |
| Token tracking | Implemented (Phase 7c) | `agent/token_tracking.py`, `GET /api/token-usage/{thread_id}` |
| TTL caching | Implemented (Phase 7c) | `tools/cache.py`, Tavily 300s TTL |
| API Key auth | Implemented (Phase 8) | `api/server.py`, `APIKeyMiddleware` |
| SQLite persistence | Implemented (Phase 8) | `api/persistence.py`, `GET /api/tasks/{thread_id}` |
| Search dedup | Implemented (Phase 8) | `tools/tavily_tools.py`, `search_with_dedup` |
| CI/CD | Configured (Phase 8) | `.github/workflows/ci.yml` |
| Fallback reports | Implemented (Phase 9) | `api/task_finalizer.py`, deterministic terminal states |
| Task timeout handling | Implemented (Phase 9) | `api/server.py`, `_mark_task_timeout` callback |
| ResearchRun + EvidenceLedger | Implemented (Phase 10) | `agent/research.py`, `GET /api/research/runs/{thread_id}` |

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
- DeepSeek API key

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
- **GET /api/tasks/{thread_id}** — View persisted task status and output path
- **GET /api/token-usage/{thread_id}** — View token usage for a thread
- **GET /api/research/runs/{thread_id}** — View ResearchRun and EvidenceLedger for a thread
- **GET /api/research/runs** — List recent ResearchRun records
- **POST /api/runs** / **GET /api/runs/{run_id}** — Start and inspect isolated research runs
- **GET /api/telemetry/runs/{run_id}** / **GET /api/token-usage/runs/{run_id}** — View run-scoped observability
- **WebSocket /ws/runs/{run_id}** — Run-scoped real-time event stream
- **WebSocket /ws/{thread_id}** — Real-time reasoning stream

WebSocket events: `session_created`, `tool_start`, `assistant_call`, `task_result`, `task_finalized`, `run_timeout`, `error`

### Talent Benchmark Fixtures

Talent runs can read server-bundled `provided_aggregate` fixtures without
receiving filesystem or upload access. The provider is disabled by default and
only resolves aggregate IDs declared in a validated `ResearchScope`.

```bash
export DEEP_SEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES=true

# Example fixture and matching scope:
# benchmarks/fixtures/talent-hiring-signal-v1.json
# benchmarks/talent-hiring-signal-v1/research-scope.json
```

The provider never accepts caller-controlled paths. Keep it disabled outside
explicit benchmark or development runs.

## Project Structure

```
deep-search-agent/
├── agent/
│   ├── main_agent.py              # Main agent orchestration
│   ├── llm.py                     # LLM factory with callback support
│   ├── prompts.py                 # YAML prompt config loader
│   ├── token_tracking.py          # LangChain callback for token tracking
│   ├── telemetry.py               # Telemetry recording
│   ├── research.py                # ResearchRun evidence extraction and quality gate
│   ├── run_result.py               # AgentRunAccumulator + stream processing (Phase 9)
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
│   ├── context.py                 # ContextVar session isolation
│   ├── persistence.py              # SQLite task + research run persistence
│   └── task_finalizer.py           # Deterministic task finalization (Phase 9)
├── utils/
│   ├── path_utils.py              # Path security helpers
│   └── word_converter.py          # PDF 转换（weasyprint 引擎）
├── prompt/
│   └── prompts.yml                # Agent system prompts
├── tests/
│   └── unit/                      # 单元测试（见 Evidence 表格）
├── frontend/                      # Vue 3 frontend
├── docs/                          # Product docs
├── scripts/
│   ├── e2e_runner.py              # Manual E2E runner
│   └── benchmark_runner.py        # Repeated benchmark runner
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
- **Research evidence persistence**: Terminal tasks also persist ResearchRun metadata and EvidenceLedger entries. Query by `GET /api/research/runs/{thread_id}`. Evidence entries are source-like observations from tool messages, not independently verified facts.
- **CI/CD**: GitHub Actions runs backend tests and frontend build on push/PR to `main`. API keys must be configured in GitHub Secrets.
- **Benchmark data**: A repeated benchmark runner exists at `scripts/benchmark_runner.py`, but new median/P95 numbers should only be reported after a real multi-run benchmark is executed and archived. The existing 5-query data remains a single snapshot.

## License

MIT. See [LICENSE](./LICENSE).

## Security

Report suspected vulnerabilities through GitHub private vulnerability reporting. See [SECURITY.md](./SECURITY.md).
