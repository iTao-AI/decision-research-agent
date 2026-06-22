# 数据模型文档

## Session Workspace 结构

每次任务执行时，系统创建一个独立的 session workspace 目录。

```
workspace/
├── session-<uuid>/
│   ├── task_input.md          # 用户输入的原始问题
│   ├── research_notes.md      # Agent 研究笔记
│   ├── draft_report.md        # 草稿报告
│   ├── final_report.md        # 最终 Markdown 报告
│   ├── final_report.pdf       # 最终 PDF 报告
│   └── uploads/               # 上传的文件
│       └── <filename>
```

## 子 Agent 输入输出

### Network Search Agent

**输入：**
```json
{
  "query": "搜索查询（自然语言）",
  "max_results": 5
}
```

**输出：**
```json
{
  "results": [
    {
      "title": "网页标题",
      "url": "https://...",
      "content": "摘要内容",
      "score": 0.95
    }
  ],
  "summary": "搜索结果的简要总结"
}
```

### Database Query Agent

**输入：**
```json
{
  "query": "自然语言查询描述",
  "tables": ["可选：指定查询的表名"]
}
```

**输出：**
```json
{
  "sql": "生成的 SQL 语句",
  "results": [
    { "column1": "value1", "column2": "value2" }
  ],
  "summary": "查询结果的简要总结"
}
```

### Knowledge Base Agent (RAGFlow)

**输入：**
```json
{
  "query": "检索查询（自然语言）",
  "top_k": 5
}
```

**输出：**
```json
{
  "results": [
    {
      "content": "检索到的知识片段",
      "source": "知识库来源",
      "score": 0.88
    }
  ],
  "summary": "检索结果的简要总结"
}
```

## 报告 Markdown Schema

生成的报告遵循以下结构：

```markdown
# [报告标题]

## 概述
[任务概述 + 核心发现摘要]

## 任务详情

### 子任务 1：[任务名称]
- **目标**：[子任务目标]
- **过程**：[执行过程]
- **结果**：[子任务结果]

### 子任务 2：[任务名称]
...

## 综合结论
[跨子任务综合分析]

## 参考文献
1. [标题](URL)
2. ...
```

## Telemetry 数据结构

```json
{
  "thread_id": "string",
  "model": "qwen-max",
  "total_tokens": 12345,
  "prompt_tokens": 8000,
  "completion_tokens": 4345,
  "tool_calls": [
    {
      "tool": "tavily_search",
      "duration_ms": 1500,
      "tokens_used": 500,
      "status": "success"
    }
  ],
  "started_at": "2026-05-19T10:00:00Z",
  "completed_at": "2026-05-19T10:05:00Z"
}
```

## Durable Review 数据模型

P1B feasibility 使用两个独立 SQLite 文件：

- application DB（`TASKS_DB_PATH`）是业务事实源，保存 ResearchRun、不可变决策、
  workflow、lease、恢复尝试、resolution 和 artifacts；
- checkpoint DB（`DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH`）只保存纯
  LangGraph ReviewGate 的执行 checkpoint，不保存业务权威结论。

application DB 新增四张表：

| 表 | 作用 |
|---|---|
| `review_decisions_v2` | 每个 review revision 的不可变 `approve` / `reject` 决策和幂等请求哈希 |
| `review_workflows_v2` | durable 状态机、post-review segment、lease、重试计数和错误码 |
| `review_resume_attempts_v2` | 每次 worker claim/resume/reconcile 的审计结果 |
| `review_resolutions_v2` | exactly-once resolution 与最终 artifact ID 集合 |

状态机：

```text
checkpoint_pending -> waiting_decision -> resume_pending -> resuming
    -> resolution_pending -> approved | rejected

ambiguous state or exhausted retries -> manual_recovery
```

Run 的 `delivery_status` 包含：

- `review_required`：需要决策，尚不可交付；
- `ready`：`approve` 已 exactly-once resolution；
- `blocked`：`reject` 已 resolution，禁止交付；
- `failed`：研究执行失败。

公开 run 投影不会返回 decision reason、actor fingerprint、lease owner、
checkpoint 路径或 checkpoint payload。`approve` 只允许交付，不改变 EvidenceLedger
验证状态；`reject` 不触发新的研究。

`approve` 和 `reject` 是一个 review revision 的不可变终态决策，接受后不能撤回、
改写或替换。纠正请求或重复研究必须创建新的 `run_id`；可保留相同 `thread_id`
用于分组，但不得改写旧 run，旧 run 继续作为不可变审计记录。

`GET /api/reviews` 队列和 review detail 都只是 application ledger 的只读投影，
不创建新的事实源或决策权威。application DB 仍是 review、decision、workflow 和
resolution 的业务权威；checkpoint DB 仍只负责 LangGraph 恢复位置。

## Evidence Verification Authority

P2A PR1 keeps `evidence_entries_v2` immutable and adds:

| Storage | Authority |
|---|---|
| `baseline_verification_origin` | Immutable collection-time origin: `none` or `declared_fixture` |
| `evidence_verification_preflights_v2` | Versioned deterministic, no-network eligibility checks |
| `evidence_verification_decisions_v2` | Append-only human `verify` / `reject` revisions |
| `evidence_verification_snapshots_v2` | Deterministic effective-state snapshots |

Effective public semantics are derived:

| Origin | State | Compatibility status |
|---|---|---|
| `none` | `unverified` | `unverified` |
| `declared_fixture` | `verified` | `verified` |
| `human` + `verify` | `verified` | `verified` |
| `human` + `reject` | `rejected` | `unverified` |

The baseline origin column never stores `human`. Human state comes only from
the latest accepted decision for the exact Evidence fingerprint. Review
approval remains independent and does not write these tables.

PR1 exposes only internal repository operations. It adds no HTTP/CLI mutation
surface and does not rebuild artifacts.

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06-22 | 增加 P2A PR1 Evidence Verification Ledger schema、不可变 baseline origin 与独立 verification authority 边界 |
| 2026-06-20 | 明确 P1C 队列/详情为只读投影，以及 review revision 决策与新 run 纠正语义 |
| 2026-06-19 | 增加 P1B durable review 双数据库权威边界、四表模型、状态机和 blocked delivery |
| 2026-05-19 | 初始数据模型文档 |
