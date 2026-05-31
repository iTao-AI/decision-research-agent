## MODIFIED Requirements

### Requirement: TelemetryRecord 数据结构

系统提供的 `TelemetryRecord` 数据类扩展 token 用量字段。

#### Scenario: 创建包含 token 用量的记录
- **WHEN** 创建 `TelemetryRecord(thread_id="abc", tool_name="search", duration_ms=150.0, status="success", token_usage=TokenUsageData(prompt_tokens=100, completion_tokens=200))`
- **THEN** 记录包含原有的 thread_id、agent_name、tool_name、duration_ms、status、timestamp 字段，并新增可选的 `token_usage` 字段

#### Scenario: 创建不带 token 用量的记录（向后兼容）
- **WHEN** 创建 `TelemetryRecord(thread_id="abc", tool_name="search", duration_ms=150.0, status="success")`（不传 token_usage）
- **THEN** 记录正常创建，token_usage 字段为 None
