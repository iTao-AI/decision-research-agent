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

**响应：**
```json
{
  "thread_id": "唯一的会话线程ID",
  "status": "started"
}
```

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

获取指定线程的遥测记录。

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

## WebSocket

### WebSocket /ws/{thread_id}

实时接收 Agent 推理流事件。

WebSocket events: `session_created`, `tool_start`, `assistant_call`, `task_result`, `task_finalized`, `error`

**连接参数：**
- `thread_id`：POST /api/task 返回的线程 ID

**消息格式（服务端 → 客户端）：**
```json
{
  "type": "monitor_event",
  "event": "session_created | tool_start | assistant_call | task_result | task_finalized | error",
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
| `error` | 发生错误 |

`task_finalized` 表示后端已写入持久化终态。`data.status` 可能为 `completed`、`completed_with_fallback` 或 `failed`；`data.output_path` 在成功和兜底成功时指向可下载 Markdown 文件。

## 认证

除 `/health` 和 API 文档外，HTTP API 在配置 `API_SECRET` 后要求通过 `X-API-Key` 请求头传递密钥。工具客户端只从 `DEEP_SEARCH_AGENT_API_KEY` 环境变量读取密钥，不接受命令行密钥参数。

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
| 2026-05-19 | 初始 API 规范 |
