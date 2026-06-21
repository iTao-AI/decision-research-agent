# API 规范文档

## REST API

### GET /health

轻量服务健康检查，供上层 Agent / 自动化脚本确认 API 进程可达。

**响应：**
```json
{
  "status": "ok",
  "service": "deep-search-agent"
}
```

### POST /api/task

启动一个异步 Agent 任务。

**请求体：**
```json
{
  "query": "用户的研究问题（自然语言）",
  "thread_id": "可选：1-128 位字母、数字、点、下划线或连字符"
}
```

### POST /api/runs

启动一个以 `run_id` 隔离的研究执行。同一 `thread_id` 可以同时存在多个 run。

**响应：**
```json
{
  "status": "started",
  "thread_id": "调用方会话标识",
  "run_id": "唯一研究执行标识",
  "segment_id": "当前执行片段标识"
}
```

### GET /api/runs/{run_id}

查询一个 run 的执行、review、delivery、segment 与 evidence 状态。

**响应：**
```json
{
  "run_id": "唯一研究执行标识",
  "thread_id": "调用方会话标识",
  "execution_status": "completed",
  "review_status": "required | resolved",
  "delivery_status": "review_required | ready | blocked",
  "review_workflow": {
    "workflow_id": "rwf_...",
    "review_id": "review_...",
    "review_revision": 1,
    "status": "waiting_decision | resume_pending | resuming | resolution_pending | approved | rejected | manual_recovery",
    "decision_id": null,
    "post_review_segment_id": "run_..._seg_review_...",
    "attempt_count": 0,
    "last_error_code": null
  },
  "review_decision": null,
  "review_resolution": null
}
```

响应只包含有界投影。决策原始 `reason`、`actor_fingerprint`、lease owner、
checkpoint 路径和 checkpoint payload 不会返回。

### GET /api/reviews

严格认证的 durable review 队列。Feature flag 关闭返回
`404 durable_hitl_disabled`；启用后缺少 `API_SECRET` 返回
`503 review_auth_not_configured`；缺少或错误的 `X-API-Key` 返回
`401 invalid_api_key`。

**查询参数：**

- `status`：精确 workflow 状态，默认 `waiting_decision`；可选值为
  `checkpoint_pending | waiting_decision | resume_pending | resuming |
  resolution_pending | approved | rejected | manual_recovery`。
- `limit`：`1..100`，默认 20。
- `cursor`：可选的不透明分页游标；调用方只能原样回传服务端返回的值。

结果按 `created_at DESC, workflow_id DESC` 确定性排序。顶层响应结构明确为
`{"reviews": [...], "next_cursor": "opaque-or-null"}`。`reviews` 中每一项仅包含
`workflow_id`、`run_id`、`review_id`、`review_revision`、`profile_id`、
`workflow_status`、`review_status`、`delivery_status`、`state_version`、
`created_at`、`updated_at` 和 `last_error_code`；`next_cursor` 只属于顶层分页
envelope，不属于单条 review metadata。
队列不返回 query、claim、evidence、decision reason、artifact、lease 或
checkpoint 内部信息。无效状态、越界 limit 或无效 cursor 返回
`422 invalid_review_query`。

### GET /api/runs/{run_id}/reviews/{review_id}

严格认证的 review 详情只读投影。返回不可变 `ReviewBundle`、有界 workflow、
当前 `state_version`、review/delivery 状态、已接受决策（包括有界 `reason`）
和已有 resolution/artifact ID。`manual_recovery` 时还返回
`operator_guidance.code` 和稳定的
`operator_guidance.docs_url=/docs/operations/controlled-review-workflow#manual-recovery`。
目标 runbook `docs/operations/controlled-review-workflow.md` 由 PR2 交付，PR1
仅冻结该稳定链接契约，不声明当前文档已经存在。

该接口不返回 `actor_fingerprint`、幂等 request hash、lease owner、
checkpoint identity/path/payload、secret-bearing metadata 或原始 exception。
不存在的 run/review 组合返回 `404 review_not_found`。认证和 feature flag
行为与 `GET /api/reviews` 相同。

### GET /api/reviews/health

供第一方 Tool Client 使用的严格认证 readiness 接口。Feature flag 关闭返回
`404 durable_hitl_disabled`；启用但 worker、application schema、checkpoint
兼容性或 13-gate report 任一未就绪时返回
`503 review_runtime_not_ready`。

就绪时返回有界字段 `status`、`feature_enabled`、`worker_running`、
`application_schema_ready`、`checkpoint_compatible` 和
`gate_report_status`。不返回文件系统路径、secret、worker/checkpoint ID 或原始
exception。认证行为与 `GET /api/reviews` 相同。

### POST /api/runs/{run_id}/reviews/{review_id}/decisions

受控 P1C durable review 决策路径，仅支持 Talent Hiring Signal profile，默认关闭。
必须同时设置 `DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL=true`、
非空 `API_SECRET`，并通过 `X-API-Key` 认证。

**请求体：**

```json
{
  "decision_id": "caller_stable_decision_id",
  "review_revision": 1,
  "action": "approve | reject",
  "reason": "reject 时必填，approve 时可选",
  "expected_state_version": 2
}
```

**202 响应：**

```json
{
  "status": "resume_pending",
  "run_id": "run_...",
  "review_id": "review_...",
  "decision_id": "caller_stable_decision_id",
  "idempotent_replay": false
}
```

重复提交内容相同的 `decision_id` 返回 `202` 且
`idempotent_replay=true`。冲突决策、stale state 或错误工作流状态返回固定错误
envelope：

```json
{
  "code": "review_already_decided",
  "problem": "This review revision already has an accepted decision.",
  "cause": "A conflicting decision was submitted.",
  "fix": "Fetch the run and use the persisted decision result.",
  "retryable": false,
  "run_id": "run_...",
  "request_id": "request_..."
}
```

Feature flag 关闭返回 `404 durable_hitl_disabled`；已启用但未配置
`API_SECRET` 返回 `503 review_auth_not_configured`；无效凭证返回
`401 invalid_api_key`。P1C 仅移除该 endpoint 的 OpenAPI deprecated 标记；
请求体、幂等语义、冲突处理和异步 `202` 响应保持不变。

### GET /api/tasks/{thread_id}

查询异步 Agent 任务的持久化状态。

**响应：**
```json
{
  "thread_id": "唯一的会话线程ID",
  "query": "用户提交的原始问题",
  "status": "pending | running | completed | completed_with_fallback | failed",
  "created_at": "ISO 8601 时间戳",
  "started_at": "ISO 8601 时间戳或 null",
  "completed_at": "ISO 8601 时间戳或 null",
  "output_path": "完成状态下可下载的 Markdown 文件绝对路径或 null",
  "token_usage_json": "JSON 字符串或 null",
  "error_message": "失败原因或 null"
}
```

### GET /api/research/runs/{thread_id}

查询单次任务的 ResearchRun 与 EvidenceLedger。

**响应：**
```json
{
  "thread_id": "唯一的会话线程ID",
  "query": "用户提交的原始问题",
  "status": "completed | completed_with_fallback | failed",
  "started_at": "ISO 8601 时间戳或 null",
  "completed_at": "ISO 8601 时间戳或 null",
  "output_path": "完成状态下可下载的 Markdown 文件绝对路径或 null",
  "fallback_used": false,
  "assistant_calls": 2,
  "tool_starts": 3,
  "diagnostics": ["tool:tavily_search"],
  "token_usage": {
    "total_prompt": 100,
    "total_completion": 20,
    "total_tokens": 120,
    "total_cost": 0.001,
    "call_count": 1
  },
  "quality_report": {
    "status": "passed | warning | failed",
    "issues": [],
    "metrics": {
      "report_size_bytes": 1024,
      "evidence_count": 2,
      "cited_evidence_count": 1,
      "total_tokens": 120,
      "diagnostic_count": 3
    }
  },
  "evidence": [
    {
      "thread_id": "唯一的会话线程ID",
      "query_text": "用户提交的原始问题",
      "subagent_name": "network_search",
      "tool_name": "tavily_search",
      "source_url": "https://example.com/source",
      "snippet": "来源片段",
      "citation_status": "cited | uncited",
      "verification_status": "unverified | verified | failed",
      "created_at": "ISO 8601 时间戳"
    }
  ]
}
```

### GET /api/research/runs

查询最近的 ResearchRun 列表，不包含逐条 EvidenceLedger。

**查询参数：**
- `limit`：返回数量，默认 50，最大 200。

**响应：**
```json
{
  "runs": [
    {
      "thread_id": "唯一的会话线程ID",
      "query": "用户提交的原始问题",
      "status": "completed",
      "quality_report": { "status": "passed", "issues": [] },
      "token_usage": { "total_tokens": 120 }
    }
  ]
}
```

### POST /api/upload

上传文件用于分析。

**请求：**
- Content-Type: `multipart/form-data`
- 字段：`file`（文件对象）

**响应：**
```json
{
  "file_path": "上传后的文件路径",
  "status": "success"
}
```

### GET /api/files

列出输出目录下的文件。

**查询参数：**
- `path`（可选）：子目录路径

**响应：**
```json
{
  "files": [
    {
      "name": "filename.md",
      "path": "/path/to/file",
      "size": 1024,
      "modified": "2026-05-19T10:00:00Z"
    }
  ]
}
```

### GET /api/download

下载生成的文件。

**查询参数：**
- `path`：文件路径（相对于输出目录）

**响应：**
- Content-Type: 根据文件类型
- Body: 文件二进制流

### GET /api/telemetry/{thread_id}

兼容接口：获取指定线程下所有 run 的遥测记录。

**路径参数：**
- `thread_id`：POST /api/task 返回的线程 ID

**响应：**
```json
{
  "telemetry": [
    {
      "timestamp": "ISO 8601 时间戳",
      "type": "事件类型",
      "data": { ... }
    }
  ]
}
```

### GET /api/telemetry/runs/{run_id}

获取单个 run 的遥测记录；每条记录同时携带 `thread_id`、`run_id` 和
`segment_id`。

### GET /api/token-usage/runs/{run_id}

获取单个 run 的 token 用量汇总。兼容接口 `GET /api/token-usage/{thread_id}`
继续保留。

## WebSocket

### WebSocket /ws/runs/{run_id}

实时接收单个 run 的事件。同一 `thread_id` 的并发 run 使用不同连接，不会互相
覆盖。事件顶层携带 `thread_id`、`run_id` 和 `segment_id`。

Run-scoped events: `session_created`, `tool_start`, `assistant_call`, `task_result`,
`run_timeout`, `error`

### WebSocket /ws/{thread_id}

兼容接口：实时接收 legacy thread-scoped Agent 推理流事件。

Legacy events: `session_created`, `tool_start`, `assistant_call`, `task_result`,
`task_finalized`, `error`

**连接参数：**
- `thread_id`：POST /api/task 返回的线程 ID

**消息格式（服务端 → 客户端）：**
```json
{
  "type": "monitor_event",
  "event": "session_created | tool_start | assistant_call | task_result | task_finalized | run_timeout | error",
  "message": "事件描述",
  "data": { ... },
  "timestamp": "ISO 8601 时间戳"
}
```

**事件类型说明：**

| type | 含义 |
|------|------|
| `session_created` | 后端会话目录已创建 |
| `tool_start` | 工具开始执行 |
| `assistant_call` | 子 Agent 被派发 |
| `task_result` | Agent 输出中间或最终可见结果 |
| `task_finalized` | 后端已写入持久化终态 |
| `run_timeout` | run-scoped task tracker 已触发超时并执行失败终结检查 |
| `error` | 发生错误 |

`task_finalized` 表示后端已写入持久化终态。`data.status` 可能为 `completed`、`completed_with_fallback` 或 `failed`；`data.output_path` 在成功和兜底成功时指向可下载 Markdown 文件。
`run_timeout` 仅发送到 `/ws/runs/{run_id}`。

## 认证

除 `/health` 和 API 文档外，HTTP API 在配置 `API_SECRET` 后要求通过 `X-API-Key` 请求头传递密钥。工具客户端优先从 `DECISION_RESEARCH_AGENT_API_KEY` 环境变量读取密钥，并兼容 `DEEP_SEARCH_AGENT_API_KEY` 旧别名；不接受命令行密钥参数。显式空 canonical key 会禁用鉴权请求头，不会回退读取旧 key。

所有调用方提供的 `thread_id` 必须为 1-128 位字母、数字、点、下划线或连字符；服务端会拒绝路径分隔符和路径穿越形式。

## 错误响应

```json
{
  "error": "错误描述",
  "detail": "详细错误信息（开发环境）"
}
```

**HTTP 状态码：**
- `200`：成功
- `400`：请求参数错误
- `404`：资源未找到
- `500`：服务器内部错误

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06-18 | canonical Tool Client 和 `DECISION_RESEARCH_AGENT_*` 配置生效；精确 health 响应保持不变 |
| 2026-06-12 | 新增 run-scoped telemetry、token usage、WebSocket 与同 thread 并发契约 |
| 2026-06-08 | 新增 ResearchRun / EvidenceLedger 查询接口 |
| 2026-05-19 | 初始 API 规范 |
