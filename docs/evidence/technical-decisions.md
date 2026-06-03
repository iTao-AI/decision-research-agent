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

## 如果重做，会补什么（实施情况）

1. ~~**持久化任务状态** — 已实现（Phase 8）：SQLite + WAL 模式，`api/persistence.py`~~
2. ~~**认证与权限** — 已实现（Phase 8）：APIKeyMiddleware，X-API-Key header~~
3. **评测集（Eval Harness）** — 用固定问题集跑基准测试，自动比较 prompt 变更或模型切换对输出质量的影响。5 个 benchmark 问题已定义，待运行。
4. **Agent 输出质量评估** — 自动检查生成报告的信息准确性、引用完整性和格式合规性。

## Phase 8 新增决策

### 为什么选 SQLite 而非 Redis
- Python 标准库自带 sqlite3，零额外依赖
- WAL 模式支持并发读写，单机部署足够
- 将来迁移到 PostgreSQL 成本极低（都是 SQL）
- Redis 需要在个人服务器上额外维护一个进程

### 为什么选 API Key 而非 JWT
- 个人部署不需要多用户、登录、注册流程
- 5 行 middleware 代码 vs JWT 需要密钥管理、过期策略、refresh token
- 这是明确的工程判断——选择简单方案而非过度设计

### 搜索去重的设计选择
- 使用 per-thread 内存 cache（`_search_cache: dict = {}`），而非 Redis/TTL
- 同一 thread 内相同 query 直接返回缓存，跨 thread 隔离
- 不引入额外依赖，cache 随任务结束可手动清理

## Phase 9 新增决策

### 为什么选「确定性终态」模型

Phase 8 收口时发现：同一 query 跑多次 E2E，有时生成报告、有时 agent 回答在 AIMessage 中但未写文件、有时 token 爆炸（459K → 3M）。根源是 DeepSeek 模型行为随机 + 报告生成依赖 agent 自主调用 write_file 工具。

「确定性终态」把「报告是否生成」从 agent 的不可靠决策中抽离出来，变成后端代码的确定性逻辑：

- 流的最后有 Markdown 文件 → `completed`
- 流正常结束但无 Markdown 文件 → 后端生成 fallback 报告 → `completed_with_fallback`
- 异常/超时 → `failed`

这样每次 E2E 都有明确终态，不会出现「stream ended but no report」的尴尬。演示时即使 agent 没有生成正式报告，fallback 报告也包含完整诊断信息。

### Fallback 报告内容策略

Fallback 报告不是空的占位符，而是包含：

1. 线程 ID 和生成时间（可追溯性）
2. 原始查询（保留用户意图）
3. 最后一个 agent 文本输出（即使没写成文件，LLM 的思考也在这里）
4. 诊断事件列表（`tool:tavily`、`tool:ragflow` 等，证明 agent 确实在干活）

这样 fallback 报告本身就是问题排查的起点——审查者或 debug 者看到它就能判断是 query 太难、模型没调用工具、还是工具调用后没收到结果。

### TaskFinalization 接口设计

`TaskFinalization` 是不可变数据类，五个字段：

- `thread_id` — 对应原始请求
- `status` — `"completed" | "completed_with_fallback" | "failed"`
- `output_path` — 报告文件绝对路径（或 None）
- `fallback_used` — 布尔值，前端据此决定是否显示「兜底报告」标记
- `error_message` — 仅 `failed` 时有值

`finalize_task_run()` 是唯一入口，接收 `AgentRunResult`，返回 `TaskFinalization`。不抛异常——报告搜索失败时走 fallback 路径而非崩溃。
