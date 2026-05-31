## ADDED Requirements

### Requirement: TokenUsage 数据模型

系统提供 `TokenUsageData` 数据类，描述单次 LLM 调用的 token 用量信息。

#### Scenario: 创建完整的 token 用量记录
- **WHEN** 创建 `TokenUsageData(prompt_tokens=150, completion_tokens=300, model="qwen-max", cost=0.042)`
- **THEN** 记录包含 prompt_tokens、completion_tokens、total_tokens、model、cost 字段，其中 total_tokens = prompt_tokens + completion_tokens

#### Scenario: 创建时 total_tokens 自动计算
- **WHEN** 创建 `TokenUsageData(prompt_tokens=100, completion_tokens=50)`
- **THEN** total_tokens 自动计算为 150

### Requirement: TokenTrackingCallbackHandler

系统提供 `TokenTrackingCallbackHandler` 类，继承 LangChain 的 `BaseCallbackHandler`，拦截 LLM 调用的 token 用量。

#### Scenario: on_llm_end 记录 token 用量
- **WHEN** LLM 调用完成且响应包含 token_usage
- **THEN** 回调提取 prompt/completion tokens，生成 TokenUsageData，追加到 collector

#### Scenario: 按 thread_id 隔离
- **WHEN** 多个并发任务调用 LLM
- **THEN** 每个 thread_id 下的 token 记录独立存储，互不干扰

#### Scenario: 无 token_usage 时静默跳过
- **WHEN** LLM 响应不包含 token_usage 字段
- **THEN** 不记录任何数据，不抛出异常

### Requirement: TokenUsageCollector

系统提供 `TokenUsageCollector` 类，管理 token 用量记录的存储和查询。

#### Scenario: 记录 token 用量
- **WHEN** 调用 `record(thread_id="abc", usage=TokenUsageData(...))`
- **THEN** 该记录追加到对应 thread_id 的列表中

#### Scenario: 按 thread_id 查询汇总
- **WHEN** 调用 `get_summary(thread_id="abc")`
- **THEN** 返回 `{total_prompt: int, total_completion: int, total_tokens: int, total_cost: float, call_count: int}`

#### Scenario: 查询不存在的 thread_id
- **WHEN** 调用 `get_summary("nonexistent")`
- **THEN** 返回全零汇总 `{total_prompt: 0, total_completion: 0, total_tokens: 0, total_cost: 0.0, call_count: 0}`

#### Scenario: 容量控制
- **WHEN** 某 thread_id 下已记录 1000 条记录后继续添加
- **THEN** 自动淘汰最早的一条记录，保持总量不超过 1000

### Requirement: Token 定价计算

系统内置默认 token 定价，支持通过环境变量覆盖。

#### Scenario: 默认 Qwen-Max 定价
- **WHEN** 未设置 `TOKEN_PRICING_JSON` 环境变量
- **THEN** 使用内置定价：prompt ¥0.04/1K tokens, completion ¥0.12/1K tokens

#### Scenario: 环境变量覆盖定价
- **WHEN** 设置 `TOKEN_PRICING_JSON='{"qwen-max": {"prompt": 0.05, "completion": 0.15}}'`
- **THEN** qwen-max 模型使用新的定价计算成本

### Requirement: /api/token-usage 端点

FastAPI 提供 REST 端点查询指定 session 的 token 用量汇总。

#### Scenario: 查询存在的 thread_id
- **WHEN** `GET /api/token-usage/{thread_id}` 且该 thread 有 token 记录
- **THEN** 返回 JSON 包含 total_prompt、total_completion、total_tokens、total_cost、call_count

#### Scenario: 查询不存在的 thread_id
- **WHEN** `GET /api/token-usage/nonexistent`
- **THEN** 返回全零汇总，不抛出异常
