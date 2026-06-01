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

> 以下数字仅为演示输出格式示例，非实际 benchmark 数据。

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
| Local pytest run | 247 通过, 0 失败 | `pytest -q` |
| Docker 部署 | 本机验证通过 | [QA 报告](docs/evidence/assets/qa-report-summary.md) |
| 前端构建 | 通过 | `cd frontend && npm run build` |
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

Tavily 和 RAGFlow 调用包裹了超时策略和指数退避重试装饰器。MySQL 连接使用 connect_timeout 和 read_timeout。Tavily 搜索结果使用 TTL 缓存（300s）。通过 LangChain `BaseCallbackHandler` 的 token 追踪记录每次 LLM 调用的 input/output/total token 数量和费用估算。这些让系统具备可观测性，并能自动从瞬态故障中恢复。

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

- [Evidence Pack](docs/evidence/) — QA 截图、运行记录、技术决策
- [证据化设计规格](docs/superpowers/specs/2026-06-01-deep-search-agent-evidence-readiness-design.md) — 本文档改造方向
- [架构规格](spec/architecture.md) — 系统架构与数据流
- [API 契约](spec/api-contract.md) — REST + WebSocket 端点定义

## 已知边界

- **WeasyPrint 依赖**: PDF 转换测试需要 WeasyPrint 系统库（cairo、pango、gobject）。依赖可用时真实运行；依赖缺失时相关转换测试 skip，并保留系统依赖缺失路径测试。Docker 环境已包含这些依赖。
- **前端构建**: 已验证（`cd frontend && npm run build` 成功，built in 357ms）。
- **无持久化任务状态**: 任务在内存中运行。服务器重启会丢失进行中的任务。
- **无认证/鉴权**: 所有 API 端点开放。仅适合内部/可信网络部署。

## License

MIT
