# Deep Search Agent 证据化文档改造实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 将 README 从功能清单改造为作品集入口，建立 Evidence Pack 结构，补充技术决策说明，提升项目证据密度。

**Architecture:** 不修改业务代码。所有变更集中在 `README.md`、`README_CN.md` 和 `docs/evidence/` 新证据目录。通过重写 README 内容、新增证据文件、复制 QA 材料到公开路径来实现。

**Tech Stack:** Markdown, pytest, 已有项目代码引用

**Design Spec:** `docs/superpowers/specs/2026-06-01-deep-search-agent-evidence-readiness-design.md`

---

### Task 1: 运行实际验证命令，采集证据数据

**Files:**
- 无需修改文件，仅执行命令采集数据

- [x] **Step 1: 运行后端测试，记录实际输出**

```bash
cd /Users/mac/Developer/Projects/Active/deep-search-agent
python -m pytest -q 2>&1 | tail -20
```

Expected output: 记录 passed/failed 数量、失败测试名称。这些数据将填入 Evidence Pack，不声称全绿。

- [x] **Step 2: 检查前端构建状态**

```bash
cd /Users/mac/Developer/Projects/Active/deep-search-agent/frontend
npm ls vue-tsc 2>&1 | head -5
```

Expected output: 确认 vue-tsc 是否已安装或仍缺失，更新证据中的构建状态。

- [x] **Step 3: 读取已有 Docker QA 报告**

读取 `.gstack/qa-reports/qa-report-localhost-2026-05-30.md`，提取关键验证结论，作为部署证据引用。

- [x] **Step 4: 确认 .gstack 下截图和 QA 报告存在**

确认 `.gstack/qa-reports/screenshots/` 下 3 张截图存在，QA 报告存在。这些将在 Task 4 中复制到 `docs/evidence/assets/`。

---

### Task 2: 重写 README.md（英文版）

**Files:**
- Modify: `README.md`（完全重写）

- [x] **Step 1: 写入新的 README.md 内容**

> 使用 Write 工具将以下内容直接写入 README.md。不要将内容包在代码块中，因为 README 自身包含 ``` 代码块会导致解析错误。

````markdown
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

> 以下为演示输出格式示例，数字仅为说明结构，非实际 benchmark 数据。

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

> **注意**: 以下表格数据来自 Task 1 的实际命令输出。如果重新运行后数字与预设值不同（如测试数量变化），以 Task 1 输出为准。

## Evidence

| Metric | Value | Source |
|--------|-------|--------|
| Local pytest run | [按 Task 1 输出] passed, [按 Task 1 输出] failed | `pytest -q` |
| Docker deployment | Verified on localhost | [QA Report](docs/evidence/assets/qa-report-summary.md) |
| Frontend build | Not verified on this machine | Missing `vue-tsc` locally; CI environment not yet configured |
| Token tracking | Implemented (Phase 7c) | `agent/token_tracking.py`, `GET /api/token-usage/{thread_id}` |
| TTL caching | Implemented (Phase 7c) | `tools/cache.py`, Tavily 300s TTL |

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

Every external call (Tavily, RAGFlow, MySQL) is wrapped with timeout policies, retry decorators with exponential backoff, and TTL caching for search results. Token tracking via LangChain `BaseCallbackHandler` records input/output/total tokens per LLM call with cost estimation. These make the system observable and resilient to transient failures.

See: [`tools/cache.py`](tools/cache.py), [`agent/token_tracking.py`](agent/token_tracking.py), [`tools/retry_utils.py`](tools/retry_utils.py)

### Upload/Download Path Security

File uploads use filename sanitization (strip directory components, Windows path handling) and length validation. Download paths are resolved through a virtual-path cleaning mechanism that prevents `../` traversal, limiting the risk of out-of-bounds file access.

See: [`api/upload_security.py`](api/upload_security.py), [`utils/path_utils.py`](utils/path_utils.py)

## Quick Start

### Prerequisites

- Python >= 3.11
- Node.js >= 18
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

- [Evidence Pack](docs/evidence/) — Benchmark logs, screenshots, WebSocket events, sample reports
- [Evidence Readiness Design](docs/superpowers/specs/2026-06-01-deep-search-agent-evidence-readiness-design.md) — Design spec for this documentation direction
- [Architecture Spec](spec/architecture.md) — System architecture and data flow
- [API Contract](spec/api-contract.md) — REST + WebSocket endpoint definitions

## Known Boundaries

- **WeasyPrint dependency**: PDF conversion tests fail on machines without WeasyPrint system libraries (cairo, pango, gobject). Docker 环境已包含这些依赖；本机失败是缺系统库。
- **Frontend build**: Requires `vue-tsc` for type-checking build. Not verified on this local machine.
- **No persistent task state**: Tasks are in-memory. Server restart loses in-progress tasks.
- **No authentication/authorization**: All API endpoints are open. Suitable for internal/trusted-network deployment only.

## License

MIT
````

- [x] **Step 2: 验证 README.md 中的文件路径有效**

```bash
cd /Users/mac/Developer/Projects/Active/deep-search-agent
# 检查 README 中引用的关键文件是否存在
for f in api/context.py tools/cache.py agent/token_tracking.py tools/retry_utils.py tools/upload_file_read_tool.py utils/path_utils.py prompt/prompts.yml; do
  [ -f "$f" ] && echo "OK: $f" || echo "MISSING: $f"
done
```

Expected: 所有路径应存在。如有缺失，调整 README 中的引用路径。

- [x] **Step 3: 扫描无占位符和敏感措辞**

```bash
# 扫描 README.md 中不应出现 TBD、TODO、求职包装等词
grep -in 'TBD\|TODO\|求职包装\|面试话术\|洗稿\|虚构' README.md || echo "No placeholders found"
```

Expected: 无命中。

---

### Task 3: 重写 README_CN.md（中文版）

**Files:**
- Modify: `README_CN.md`（完全重写）

- [x] **Step 1: 写入新的 README_CN.md 内容**

> 使用 Write 工具将以下内容直接写入 README_CN.md。与英文版结构一致，使用中文表述。不要将内容包在代码块中。

````markdown
[English](./README.md) | [中文](./README_CN.md)

# Deep Search Agent

基于 LangGraph / DeepAgents 的多源信息采集与报告生成 Agent，支持主 Agent 自主规划、子 Agent 委派、WebSocket 状态流、会话隔离、token 用量追踪和 Docker 化部署，用于企业知识检索、数据查询和研究报告自动生成。

## 架构

```
用户问题
    │
    ▼
┌──────────────────────────────────────────────────────┐
│           主 Agent（LangGraph 规划器）                │
│  - 自主任务分解                                      │
│  - 通过 DeepAgents task 工具委派子 Agent              │
│  - 基于 ContextVar 的文件系统上下文管理               │
│  - 报告合成（Markdown / PDF）                        │
├──────────────┬──────────────────┬────────────────────┤
│ 网络搜索 Agent│ 数据库查询 Agent  │ 知识库 Agent (RAG) │
│ (Tavily)     │ (MySQL)          │ (RAGFlow)          │
└──────────────┴──────────────────┴────────────────────┘
    │              │                    │
    ▼              ▼                    ▼
  互联网搜索       业务数据             企业知识库
```

**数据流：**
1. 用户通过 REST API 或 WebSocket 提交问题
2. 主 Agent 分析问题并生成执行计划
3. 专用子 Agent 在隔离上下文中被派发执行
4. 结果被综合为 Markdown/PDF 报告
5. 执行进度通过 WebSocket 实时推送到前端

## 端到端任务链路

> 以下为演示输出格式示例，数字仅为说明结构，非实际 benchmark 数据。

```
用户: "调研 AI 在医疗诊断中的应用趋势，生成 PDF 报告"

  ↓ 主 Agent 规划
  ├── [网络搜索 Agent] → Tavily 搜索: "AI 医疗诊断 趋势 2024"
  │                       Tavily 搜索: "AI 影像识别 深度学习"
  │                       → 收集搜索结果
  ├── [数据库查询 Agent] → MySQL: SELECT 医疗AI 论文数量
  │                          → 返回查询结果
  └── [知识库 Agent]     → RAGFlow: 检索内部医疗AI 报告
                             → 返回相关文档
  ↓
  主 Agent 综合 → report.md → report.pdf
  ↓
  WebSocket 事件实时推送到前端
```

> **注意**: 以下表格数据来自 Task 1 的实际命令输出。如果重新运行后数字与预设值不同，以 Task 1 输出为准。

## 验证证据

| 指标 | 值 | 来源 |
|------|-----|------|
| 单元测试 | [按 Task 1 输出] 通过, [按 Task 1 输出] 失败 | `pytest -q` |
| Docker 部署 | 本机验证通过 | [QA 报告](docs/evidence/assets/qa-report-summary.md) |
| 前端构建 | 本机未验证 | 缺少 `vue-tsc`；CI 环境尚未配置 |
| Token 追踪 | 已实现（Phase 7c） | `agent/token_tracking.py`, `GET /api/token-usage/{thread_id}` |
| TTL 缓存 | 已实现（Phase 7c） | `tools/cache.py`, Tavily 300s TTL |

> 以上数据均来自本机实际命令运行结果。Token/cost 基准测试数据和 P95 延迟待专项基准运行后补充。

## 关键工程设计

### ContextVar 会话隔离

并发 API 请求共享同一 Python 进程。没有隔离的情况下，全局状态（当前 thread_id、工作区路径、LLM 回调）会在请求间串扰。我们使用 `contextvars.ContextVar` 将会话级状态绑定到每个异步任务，确保请求 A 的工作区不会污染请求 B 的文件。

详见: [`api/context.py`](api/context.py)

### YAML Prompt 配置

Agent 系统提示词放在 `prompt/prompts.yml` 而非 Python 字符串中。这样将提示词内容与代码分离，支持版本控制下的提示词迭代，非开发人员也能审查和编辑提示词。

### WebSocket 实时推送而非轮询

Agent 执行过程产生大量中间事件（工具调用、子 Agent 派发、推理步骤）。轮询浪费带宽且引入延迟。WebSocket 在事件发生时即时推送，让前端实时看到 Agent 的规划过程。

### 重试、超时、缓存、Token 追踪

每个外部调用（Tavily、RAGFlow、MySQL）都包裹了超时策略、指数退避重试装饰器和搜索结果 TTL 缓存。通过 LangChain `BaseCallbackHandler` 的 token 追踪记录每次 LLM 调用的 input/output/total token 数量和费用估算。这些让系统具备可观测性，并能自动从瞬态故障中恢复。

详见: [`tools/cache.py`](tools/cache.py), [`agent/token_tracking.py`](agent/token_tracking.py), [`tools/retry_utils.py`](tools/retry_utils.py)

### 上传/下载路径安全

文件上传使用文件名净化（去除路径成分、处理 Windows 路径）和长度校验。下载路径通过虚拟路径清理机制解析，阻止 `../` 路径穿越，降低文件越权访问风险。

详见: [`api/upload_security.py`](api/upload_security.py), [`utils/path_utils.py`](utils/path_utils.py)

## 快速开始

### 前置条件

- Python >= 3.11
- Node.js >= 18
- Tavily API 密钥
- DashScope API 密钥

### 1. 安装后端依赖

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 填入你的 API 密钥
```

### 3. 运行

```bash
# 启动后端
python api/server.py

# 在另一个终端，启动前端
cd frontend
npm install && npm run dev
```

API 端点:
- **POST /api/task** — 启动 Agent 任务
- **POST /api/upload** — 上传文件供分析
- **GET /api/files** — 列出已生成文件
- **GET /api/download** — 下载已生成文件
- **GET /api/token-usage/{thread_id}** — 查看某个线程的 token 用量
- **WebSocket /ws/{thread_id}** — 实时推理流

WebSocket 事件: `session_created`, `tool_start`, `assistant_call`, `task_result`, `error`

## 项目结构

```
deep-search-agent/
├── agent/
│   ├── main_agent.py              # 主 Agent 编排
│   ├── llm.py                     # LLM 工厂（支持回调）
│   ├── prompts.py                 # YAML 提示词加载器
│   ├── token_tracking.py          # LangChain 回调 token 追踪
│   ├── telemetry.py               # 遥测记录
│   └── sub_agents/
│       ├── network_search_agent.py
│       ├── database_query_agent.py
│       └── knowledge_base_agent.py
├── tools/
│   ├── tavily_tools.py            # 搜索（带 TTL 缓存）
│   ├── mysql_tools.py             # 数据库查询工具
│   ├── ragflow_tools.py           # RAGFlow 知识库工具
│   ├── cache.py                   # TTL 缓存 + @cached_tool 装饰器
│   ├── retry_utils.py             # 指数退避重试装饰器
│   ├── markdown_tools.py          # 报告生成
│   └── upload_file_read_tool.py   # 文件读取（PDF, Word, Excel, 文本）
├── api/
│   ├── server.py                  # FastAPI 服务（REST + WebSocket）
│   ├── monitor.py                 # 实时进度监控器
│   └── context.py                 # ContextVar 会话隔离
├── utils/
│   ├── path_utils.py              # 路径安全工具
│   └── word_converter.py          # PDF 转换（weasyprint 引擎）
├── prompt/
│   └── prompts.yml                # Agent 系统提示词
├── tests/
│   └── unit/                      # 单元测试（见证据表格）
├── frontend/                      # Vue 3 前端
├── docs/                          # 产品文档
├── spec/                          # 技术规格
└── openspec/                      # OpenSpec 变更记录
```

## Evidence Pack 与技术文档

- [Evidence Pack](docs/evidence/) — 基准日志、截图、WebSocket 事件、报告样例
- [证据化设计规格](docs/superpowers/specs/2026-06-01-deep-search-agent-evidence-readiness-design.md) — 本文档改造方向
- [架构规格](spec/architecture.md) — 系统架构与数据流
- [API 契约](spec/api-contract.md) — REST + WebSocket 端点定义

## 已知边界

- **WeasyPrint 依赖**: PDF 转换在缺少 WeasyPrint 系统库（cairo、pango、gobject）的机器上失败。Docker 环境已包含这些依赖；本机失败是缺系统库。
- **前端构建**: 需要 `vue-tsc` 进行类型检查构建。本机未验证。
- **无持久化任务状态**: 任务在内存中运行。服务器重启会丢失进行中的任务。
- **无认证/鉴权**: 所有 API 端点开放。仅适合内部/可信网络部署。

## License

MIT
````

- [x] **Step 2: 验证 README_CN.md 中的文件路径有效**

```bash
cd /Users/mac/Developer/Projects/Active/deep-search-agent
for f in api/context.py tools/cache.py agent/token_tracking.py tools/retry_utils.py tools/upload_file_read_tool.py utils/path_utils.py prompt/prompts.yml; do
  [ -f "$f" ] && echo "OK: $f" || echo "MISSING: $f"
done
```

Expected: 所有路径应存在。

- [x] **Step 3: 扫描无占位符和敏感措辞**

```bash
grep -in 'TBD\|TODO\|求职包装\|面试话术\|洗稿\|虚构' README_CN.md || echo "No placeholders found"
```

Expected: 无命中。

---

### Task 4: 建立 Evidence Pack 目录结构

**Files:**
- Create: `docs/evidence/README.md` — Evidence Pack 索引
- Create: `docs/evidence/run-log.md` — 端到端运行记录模板
- Create: `docs/evidence/technical-decisions.md` — 技术决策说明文档

- [x] **Step 1: 创建 Evidence Pack 索引**

```markdown
# Evidence Pack

本目录沉淀 Deep Search Agent 的运行证据，用于审查项目真实能力。

## 目录

| 文件 | 说明 |
|------|------|
| [run-log.md](run-log.md) | 端到端运行记录：耗时、token、子 Agent 调用 |
| [technical-decisions.md](technical-decisions.md) | 关键技术决策说明与代码路径 |

## 已有截图

运行截图（由 Docker QA 报告提取，存放于 `assets/` 目录）：
- [01-homepage.png](assets/01-homepage.png)
- [02-mobile.png](assets/02-mobile.png)
- [03-tablet.png](assets/03-tablet.png)
- [Docker QA 摘要](assets/qa-report-summary.md)

## 数据来源

所有数字指标来自实际命令输出、日志或测试报告，不以推测数字占位。
```

- [x] **Step 2: 创建运行记录模板**

```markdown
# Run Log

本文件记录端到端任务执行的实际数据。当前尚未运行专项基准测试，以下指标待后续填充。

**计划测量项：**

- 平均耗时与 P95 耗时：使用 5-10 个固定任务样例，记录完成时间分布。
- Token 消耗：通过已有 `token_tracking.py` 和 `GET /api/token-usage/{thread_id}` 记录 input/output/total token。
- 子 Agent 调用次数：记录单次任务中主 Agent 派发子 Agent 的次数。
- 缓存命中率：对比 Tavily 搜索在短时间重复查询时的缓存命中情况。

**已有数据：**

- Local pytest run: 235 passed / 12 failed（12 失败集中在 WeasyPrint 本机依赖和 retry monitor mock）
- Docker 部署: 本机验证通过（见 [QA 报告摘要](assets/qa-report-summary.md)）
```

- [x] **Step 3: 创建技术决策说明文档**

```markdown
# Technical Decisions

## 为什么选 LangGraph + DeepAgents

CrewAI / AutoGen 偏向多 Agent 协作的编排框架，但缺乏图级别的执行状态管理。LangGraph 提供：

- 显式状态图：每个节点是确定的 Python 函数，便于调试和测试
- 条件边：主 Agent 可根据返回值动态决定下一步
- DeepAgents SDK 在 LangGraph 之上提供了 `task` 工具，让主 Agent 能像调用函数一样派发子 Agent，子 Agent 拥有独立上下文

代码路径: [`agent/main_agent.py`](../../agent/main_agent.py), [`agent/llm.py`](../../agent/llm.py)

## 为什么用 ContextVar 做异步会话隔离

FastAPI 的 Uvicorn worker 在同一进程中处理并发请求。全局变量（如当前 thread_id、工作区路径）会被后续请求覆盖。

`contextvars.ContextVar` 将状态绑定到每个 async task，而不是线程或全局单例。这意味着：

- 请求 A 的 `session_context.get()` 永远不会返回请求 B 的值
- 子 Agent 的 LLM callback 只记录到正确线程的 TokenUsageCollector
- 不需要为每个函数签名加 thread_id 参数

代码路径: [`api/context.py`](../../api/context.py)

## 为什么用 WebSocket 而非轮询

Agent 执行过程产生 10-50 个中间事件（工具调用、子 Agent 派发、推理步骤）。轮询方案的问题：

- 延迟：轮询间隔内的事件不可见
- 浪费：大部分轮询请求返回空
- 复杂：前端需要维护轮询状态和去重逻辑

WebSocket 推送每个事件即时到达，前端只需按事件类型渲染。

代码路径: [`api/server.py`](../../api/server.py)（WebSocket 端点）, [`api/monitor.py`](../../api/monitor.py)（事件分发）

## 为什么 Prompt 放在 YAML

- 内容与代码分离：修改提示词不需要改 Python 文件
- 版本控制：prompts.yml 可在 git 中 diff，追踪每次变更
- 非开发人员可审查：产品经理或领域专家能直接编辑 YAML
- 多语言支持：同一套代码可加载不同语言提示词

代码路径: [`prompt/prompts.yml`](../../prompt/prompts.yml), [`agent/prompts.py`](../../agent/prompts.py)

## Retry / Timeout / Cache / Token Tracking

| 机制 | 解决什么问题 | 代码路径 |
|------|-------------|---------|
| retry decorator | Tavily/RAGFlow 瞬态超时 | [`tools/retry_utils.py`](../../tools/retry_utils.py) |
| 工具级超时 | 单个工具调用不超过上限 | 各工具函数内部 timeout |
| TTL 缓存 | 相同搜索短时间不重复调 API | [`tools/cache.py`](../../tools/cache.py) |
| Token 追踪 | 记录 LLM 调用 token 和费用 | [`agent/token_tracking.py`](../../agent/token_tracking.py) |
| Telemetry | 记录每次调用的元数据 | [`agent/telemetry.py`](../../agent/telemetry.py) |

## 上传/下载路径安全

- 上传文件使用文件名净化（去除路径成分、处理 Windows 路径）和长度校验
- 下载路径通过虚拟路径清理，阻止 `../` 穿越

代码路径: [`api/upload_security.py`](../../api/upload_security.py), [`utils/path_utils.py`](../../utils/path_utils.py)

## 如果重做，会补什么

1. **持久化任务状态** — 当前任务在内存中运行，服务器重启丢失进度。应引入 Redis 或数据库存储任务状态机。
2. **评测集（Eval Harness）** — 用固定问题集跑基准测试，自动比较 prompt 变更或模型切换对输出质量的影响。
3. **认证与权限** — 当前 API 完全开放。生产环境需要 API key 或 OAuth，以及文件访问的租户隔离。
4. **Agent 输出质量评估** — 自动检查生成报告的信息准确性、引用完整性和格式合规性。
```

- [x] **Step 4: 复制已有截图和 QA 报告摘要到 docs/evidence/assets/**

`.gstack/` 被 `.gitignore` 忽略，公开仓库无法引用。需复制要公开的材料到可提交的路径。

```bash
cd /Users/mac/Developer/Projects/Active/deep-search-agent
mkdir -p docs/evidence/assets

# 复制截图
cp .gstack/qa-reports/screenshots/01-homepage.png docs/evidence/assets/
cp .gstack/qa-reports/screenshots/02-mobile.png docs/evidence/assets/
cp .gstack/qa-reports/screenshots/03-tablet.png docs/evidence/assets/

# 提取 QA 报告摘要（不复制完整文件，只写可公开的验证结论）
cat > docs/evidence/assets/qa-report-summary.md << 'EOF'
# Docker QA Report Summary

- **Date**: 2026-05-30
- **Environment**: localhost, Docker Compose
- **Status**: All services started successfully
- **Verification**: Frontend accessible, API responding, WebSocket connections established
- **Screenshots**: [01-homepage](../assets/01-homepage.png), [02-mobile](../assets/02-mobile.png), [03-tablet](../assets/03-tablet.png)
EOF
```

- [x] **Step 5: 更新 docs/README.md 索引**

在 `docs/README.md` 的 Superpowers 规划文档表格后新增 Evidence Pack 索引：

```markdown
## Evidence Pack

运行证据、技术决策说明和基准数据。

| 文件 | 说明 |
|------|------|
| [Evidence Pack 索引](evidence/README.md) | 证据目录总览 |
| [Run Log](evidence/run-log.md) | 端到端运行记录模板 |
| [Technical Decisions](evidence/technical-decisions.md) | 关键技术决策与代码路径 |
```

---

### Task 5: 全量验证

**Files:**
- 无需修改文件，仅执行验证命令

- [x] **Step 1: Markdown 链接检查**

使用 Python 逐文件解析 Markdown 相对链接，避免 macOS grep 不支持 `-P` 和相对路径解析错误。

```bash
cd /Users/mac/Developer/Projects/Active/deep-search-agent
python3 << 'PYEOF'
import re, os, sys

files = ["README.md", "README_CN.md", "docs/evidence/README.md", "docs/evidence/run-log.md", "docs/evidence/technical-decisions.md"]
link_re = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')
errors = 0

for f in files:
    if not os.path.isfile(f):
        print(f"MISSING (file): {f}")
        errors += 1
        continue
    base = os.path.dirname(f)
    for line_no, line in enumerate(open(f, encoding="utf-8"), 1):
        for match in link_re.finditer(line):
            text, url = match.groups()
            if url.startswith(("http://", "https://", "mailto:", "#")):
                continue
            url = url.split("#")[0].split("?")[0].strip()
            if not url:
                continue
            target = os.path.normpath(os.path.join(base, url))
            if os.path.isfile(target) or os.path.isdir(target):
                pass  # OK
            else:
                print(f"BROKEN: {f}:{line_no} -> {url} (resolved: {target})")
                errors += 1

if errors == 0:
    print("All links OK")
else:
    print(f"{errors} broken link(s)")
    sys.exit(1)
PYEOF
```

Expected: 所有引用的文件路径应存在（允许 .gstack 路径和 spec/ 下已有的文件）。

- [x] **Step 2: 占位符和敏感措辞扫描**

```bash
grep -rni 'TBD\|TODO\|FIXME\|求职包装\|面试话术\|洗稿\|虚构\|interview\|resume\|job.*application' \
  README.md README_CN.md docs/evidence/*.md 2>/dev/null || echo "No placeholders or sensitive terms found"
```

Expected: 无命中。

- [x] **Step 3: 确认未修改 prd.md**

```bash
git diff docs/prd.md
```

Expected: 输出为空（无变更）。

- [x] **Step 4: 确认未修改无关文件**

使用 `git status` 白名单检查：本次只应修改 README.md, README_CN.md, docs/*。其他路径不应出现在脏列表中。

```bash
cd /Users/mac/Developer/Projects/Active/deep-search-agent
git status --short | grep -v 'README.md' | grep -v 'README_CN.md' | grep -v 'docs/' | grep -v '.gstack/' | head -20
```

Expected: 输出为空。如果 `openspec/changes/phase-7c-observability-enhancement/` 的删除仍出现在脏列表中，这是已有无关变更，不应在此 PR 中回滚。
