## Why

当前项目缺乏对 LLM 调用的 token 用量追踪和查询结果缓存能力。token 用量无法量化导致成本不可控（Qwen-Max 调用费用无法统计）；每次重复查询都会重新调用外部服务（Tavily 等），浪费 API 配额、增加延迟并产生额外费用。

## What Changes

- **Token 追踪**：通过 LangChain Callback 拦截 LLM 调用，记录 prompt/completion tokens 和估算成本，汇总到 task 级别
- **工具级缓存**：基于 TTL 的内存缓存装饰器，先应用到 Tavily 搜索工具，相同查询在 TTL 内直接返回缓存结果
- **TelemetryRecord 扩展**：增加 `token_usage` 字段，与现有 telemetry 系统无缝集成
- **REST 端点**：`GET /api/token-usage/{thread_id}` 返回 token 用量汇总

**Out of Scope**：
- LLM 响应缓存（不缓存 LLM 输出）
- 全任务结果缓存（不缓存子任务输出）
- 持久化缓存（仅内存 TTL，重启后清空）
- Redis/外部缓存后端

## Capabilities

### New Capabilities
- `token-usage-tracking`: LLM 调用的 token 用量追踪、汇总和查询
- `tool-cache`: 基于 TTL 的工具级内存缓存，当前仅覆盖 Tavily

### Modified Capabilities
- `observability`: TelemetryRecord 数据模型扩展（新增 token_usage 字段）

## Impact

- **新增文件**：`agent/token_tracking.py`（CallbackHandler + TokenUsage 数据模型）、`tools/cache.py`（TTL 缓存装饰器）
- **修改文件**：`agent/telemetry.py`（TelemetryRecord 扩展）、`api/server.py`（新增 token-usage REST 端点）、`agent/llm.py`（注册 CallbackHandler）、`tools/tavily_tools.py`（应用缓存装饰器）
- **无破坏性变更**：TelemetryRecord 新增可选字段，不影响已有调用
- **回归风险**：低 — 缓存仅影响工具层，token 追踪仅增加回调，不改变核心逻辑
