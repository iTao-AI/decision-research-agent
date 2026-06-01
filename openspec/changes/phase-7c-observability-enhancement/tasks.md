## Phase 1: Token 追踪基础

- [x] 1.1 创建 `agent/token_tracking.py` — TokenUsageData 数据模型 + TokenUsageCollector 收集器（含容量控制）
- [x] 1.2 创建 TokenUsageCollector 的 get_summary 方法，按 thread_id 汇总 token 用量
- [x] 1.3 创建 TokenTrackingCallbackHandler，继承 BaseCallbackHandler，实现 on_llm_end 回调
- [x] 1.4 编写 `tests/unit/test_token_tracking.py` — TokenUsageData、Collector、CallbackHandler 单元测试（已含）

## Phase 2: 工具级 TTL 缓存

- [x] 2.1 创建 `tools/cache.py` — TTLCache 类（get/set/expiry/cap）
- [x] 2.2 创建 `@cached_tool` 装饰器，支持 TTL 参数和 cache key 生成（SHA256 hash）
- [x] 2.3 编写 `tests/unit/test_cache.py` — TTLCache 过期、容量、装饰器缓存命中/miss 测试

## Phase 3: 集成

- [x] 3.1 修改 `agent/llm.py` — 初始化 LLM 时注册 TokenTrackingCallbackHandler
- [x] 3.2 修改 `api/server.py` — 在 run_deep_agent 中将 CallbackHandler 注册到 LLM
- [x] 3.3 修改 `tools/tavily_tools.py` — 为 _search_with_resilience 应用 @cached_tool 装饰器
- [x] 3.4 修改 `agent/telemetry.py` — TelemetryRecord 新增可选 token_usage 字段

## Phase 4: API 端点与回归

- [x] 4.1 在 `api/server.py` 新增 `GET /api/token-usage/{thread_id}` REST 端点
- [x] 4.2 运行全量回归测试，确认 180+ 测试全部通过
- [x] 4.3 手动验证：触发一次搜索任务，检查 /api/token-usage 返回正确数据（API 端点已验证可访问）
