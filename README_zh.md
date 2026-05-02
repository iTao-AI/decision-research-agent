# Deep Search Agent

一个基于 LangGraph 的自主规划智能体系统。用户用自然语言提问，主 Agent 自主规划并委派 3 个子 Agent（网络搜索、数据库查询、知识库检索）搜集信息，最终生成 Markdown/PDF 报告。

## 架构

```
用户问题
    │
    ▼
┌──────────────────────────────────┐
│         主 Agent（规划器）         │
│  - 任务分解                      │
│  - 子 Agent 委托                 │
│  - 文件系统上下文管理             │
│  - 报告生成                      │
├──────────┬──────────┬────────────┤
│ 网络搜索  │ 数据库   │ 知识库     │
│ Agent    │ Agent    │ Agent      │
│ (Tavily) │ (MySQL)  │ (RAGFlow)  │
└──────────┴──────────┴────────────┘
    │           │           │
    ▼           ▼           ▼
  互联网      业务数据    企业知识
  搜索        查询        检索
```

**数据流：**
1. 用户通过 REST API 或 WebSocket 提交问题
2. 主 Agent（LangGraph）分析问题并制定任务计划
3. 子 Agent 通过 `task` 工具被派遣，拥有独立上下文
4. 结果被汇总并写入 Markdown/PDF 报告
5. 进度通过 WebSocket 实时推送到前端

## 技术栈

| 层级 | 技术 |
|------|------|
| Agent 框架 | DeepAgents SDK（LangGraph 生态） |
| 大模型 | Qwen-Max（DashScope，OpenAI 兼容接口） |
| 网络搜索 | Tavily Search API |
| 数据库 | MySQL（mysql.connector） |
| 知识库 | RAGFlow（企业级 RAG 引擎） |
| Web API | FastAPI + Uvicorn |
| 实时通信 | WebSocket |
| 前端 | Vue 3 + Vite |

## 核心功能

- **自主任务规划**：Agent 自主决定搜索什么、搜索几次、何时停止
- **分层子 Agent 委托**：三个专业子 Agent 针对不同信息源
- **文件系统上下文管理**：基于 ContextVar 的会话隔离，防止并发请求干扰
- **实时推理流**：基于 WebSocket 的 Agent 思考过程实时追踪
- **报告生成**：自动从搜集信息生成 Markdown/PDF 报告
- **文件上传与分析**：支持上传文档（PDF、Word、Excel）供 Agent 分析

## 快速开始

### 前置要求

- Python >= 3.11
- Node.js >= 18
- Tavily API 密钥（https://app.tavily.com/）
- DashScope API 密钥（https://bailian.console.aliyun.com/）

### 1. 安装后端依赖

```bash
cd deep-search-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境

```bash
cp .env.example .env
vim .env
```

填入你的 API 密钥。

### 3. 运行

```bash
# 启动后端
python api/server.py

# 另一个终端，启动前端
cd frontend
npm install && npm run dev
```

API 端点：
- **POST /api/task** — 启动 Agent 任务
- **POST /api/upload** — 上传文件供分析
- **GET /api/files** — 查看生成的文件
- **GET /api/download** — 下载生成的文件
- **WebSocket /ws/{thread_id}** — 实时推理流

## API 参考

### POST /api/task

启动 Agent 任务。Agent 异步执行，进度通过 WebSocket 推送。

```json
{
  "query": "调研 AI 行业趋势并生成 PDF 报告",
  "thread_id": "可选的 UUID"
}
```

### WebSocket /ws/{thread_id}

使用 `/api/task` 返回的 `thread_id` 连接。事件包括：
- `session_created` — 工作目录就绪
- `tool_start` — 工具正在执行
- `assistant_call` — 子 Agent 被派遣
- `task_result` — 最终答案就绪
- `error` — 执行失败

## 项目结构

```
deep-search-agent/
├── agent/
│   ├── main_agent.py        # 主 Agent 编排 + 运行时
│   ├── llm.py               # 大模型初始化
│   ├── prompts.py           # 提示词配置加载器
│   └── sub_agents/
│       ├── network_search_agent.py      # Tavily 搜索子 Agent
│       ├── database_query_agent.py      # MySQL 查询子 Agent
│       └── knowledge_base_agent.py      # RAGFlow 子 Agent
├── tools/
│   ├── tavily_tools.py      # 网络搜索工具
│   ├── mysql_tools.py       # 数据库查询工具（列表/预览/SQL）
│   ├── ragflow_tools.py     # 知识库工具（助手列表/提问）
│   ├── markdown_tools.py    # Markdown 报告生成
│   ├── pdf_tools.py         # Markdown 转 PDF
│   └── upload_file_read_tool.py  # 文件读取（PDF/Word/Excel/文本）
├── api/
│   ├── server.py            # FastAPI 服务（REST + WebSocket）
│   ├── monitor.py           # 实时进度监控器（单例）
│   └── context.py           # ContextVar 会话隔离
├── utils/
│   ├── path_utils.py        # 路径解析与虚拟路径清洗
│   └── word_converter.py    # Markdown 通过 Word 转 PDF
├── prompt/
│   └── prompts.yml          # Agent 系统提示词（YAML 配置）
└── frontend/                # Vue 3 前端（WebSocket 实时展示）
```

## License

MIT
