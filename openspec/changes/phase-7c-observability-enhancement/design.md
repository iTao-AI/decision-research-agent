## Context

当前 Deep Search Agent 使用 LangChain/LangGraph 作为 Agent 框架，LLM 调用通过 `langchain.chat_models.init_chat_model` 初始化 Qwen-Max。项目已有 `agent/telemetry.py` 记录工具调用的 duration/status，但缺乏 token 用量追踪。所有工具调用每次都会重新执行，无缓存机制。

## Goals / Non-Goals

**Goals:**
- 追踪每次 LLM 调用的 prompt/completion/total tokens 及估算成本
- 提供 task 级别的 token 用量汇总
- 为 Tavily 搜索工具添加 TTL 内存缓存，相同查询在 TTL 内返回缓存结果
- 与现有 TelemetryCollector 集成，token 字段作为 TelemetryRecord 的可选扩展

**Non-Goals:**
- 不缓存 LLM 响应（prompt 变化频繁，缓存命中率低）
- 不使用 Redis/持久化缓存（增加部署复杂度，当前规模不需要）
- 不实现缓存失效的主动通知机制（TTL 被动过期即可）

## Decisions

### 1. Token 追踪：LangChain CallbackHandler

**选择**：继承 `BaseCallbackHandler`，实现 `on_llm_start`/`on_llm_end` 回调，通过 `response.token_usage` 获取 token 数据。

**替代方案对比**：
- **直接包装 LLM 调用**：需要改所有调用点，侵入性强
- **中间件层拦截**：LangChain 已有成熟的 Callback 体系，无需自建
- **CallbackHandler**：非侵入式，自动覆盖所有 LLM 调用，与 LangGraph 原生兼容

**定价**：Qwen-Max 当前价格（约 ¥0.04/1K prompt tokens, ¥0.12/1K completion tokens），在 `TokenUsage` 数据类中硬编码，支持通过环境变量覆盖。

### 2. 缓存：装饰器 + TTL 内存字典

**选择**：`@cached_tool(ttl=300)` 装饰器，使用 `functools` + `hashlib.sha256` 对函数参数做 hash key，内存字典存储 `{key: (value, expiry_timestamp)}`。

**替代方案对比**：
- **functools.lru_cache**：无法控制 TTL，过期策略不灵活
- **diskcache**：持久化缓存，增加磁盘 I/O，当前场景不需要
- **cachetools.TTLCache**：轻量但需要外部依赖，当前项目零外部依赖缓存更简洁
- **自实现 TTL 字典**：零依赖，控制精细，代码量 < 100 行

**缓存 key 生成**：对函数名 + 参数 JSON 序列化后取 SHA256，确保相同查询产生相同 key。

### 3. TelemetryRecord 扩展：可选字段

**选择**：新增 `token_usage: TokenUsageData | None = None` 可选字段，所有已有调用继续传 None。

**理由**：向后兼容，不影响已有代码路径。

### 4. 缓存作用域：仅 Tavily

**理由**：Tavily 是按次计费的搜索 API，重复查询浪费最明显。RAGFlow 和 MySQL 的查询模式不同（企业知识库查询通常不重复），后续可扩展。

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| 缓存返回过期数据（如搜索结果变化） | TTL 默认 5 分钟，短过期窗口平衡新鲜度和命中率 |
| 内存缓存无上限，可能增长 | 字典自然淘汰（过期 key 下次访问时清理），添加 MAX_CACHE_SIZE=1000 硬限制 |
| Token 定价过时导致成本估算不准 | 通过环境变量 `TOKEN_PRICING_JSON` 支持覆盖，不硬编码死 |
| CallbackHandler 在异步环境下的线程安全 | 使用 `ContextVar` 隔离 per-thread 数据，与现有 `api/context.py` 模式一致 |

## Migration Plan

1. 新增文件，不修改现有接口
2. 在 `api/server.py` 的 `run_deep_agent` 中注册 `TokenTrackingCallback`
3.  Tavily 工具添加 `@cached_tool` 装饰器
4. 无回滚风险 — 新增功能，不影响已有路径

## Open Questions

- Token 定价是否从环境变量读取？ → 是，默认内置 Qwen-Max 定价，可通过 `TOKEN_PRICING_JSON` 覆盖
- 缓存是否需要预热？ → 不需要，被动填充即可
