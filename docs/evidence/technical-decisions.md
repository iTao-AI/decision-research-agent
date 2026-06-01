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
