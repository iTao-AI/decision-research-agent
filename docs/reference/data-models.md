# 数据模型文档

## ResearchRun 身份模型

当前业务身份由 application DB 持久化：

| 字段 | 作用 |
|---|---|
| `thread_id` | 调用方会话/对话分组，也用于 LangGraph runtime config correlation |
| `run_id` | 单次隔离研究执行的主身份 |
| `segment_id` | terminal write segment，用于 fenced finalization |
| `state_version` | 乐观锁版本，防止 stale writer 覆盖终态 |

`thread_id` 不再代表单个任务执行；同一 `thread_id` 可以并发创建多个
`run_id`。辅助状态（workspace、telemetry、token usage、monitor channel、
search cache）必须按 `run_id` 隔离。

Application DB = business authority。LangGraph checkpoint DB 和 LangSmith trace
都不是 ResearchRun、EvidenceLedger、review、verification、publication 或
delivery 的业务事实源。

## Execution Outcome

Agent harness 输出在进入业务账本前被 service 层冻结为 outcome snapshot：

| 字段 | 说明 |
|---|---|
| `answer` | 研究输出文本或 fallback 说明 |
| `evidence_entries` | 当前 run 捕获的不可变证据条目 |
| `research_packets` | Talent profile 的结构化 ResearchPacket |
| `failure_kind` | schema、contract、runtime 或 provider failure 分类 |
| `diagnostics` | 有界诊断，不应包含 secret、绝对路径或 traceback |

Outcome 不是业务权威。只有 fenced terminal transaction 写入
`research_runs_v2`、`evidence_entries_v2`、artifact/review/publication tables
之后，才成为可查询状态。

## Run creation idempotency ledger

`run_create_idempotency_v1` is application-database authority for optional
run-create replay identity. It stores `key_hash`, `request_schema_version`,
`request_hash`, `run_id`, and `created_at`. The raw key is never stored.
`run_id` is unique and references `research_runs_v2(run_id) ON DELETE CASCADE`.
The v1 ledger has no TTL or cleanup job. The canonical request hash covers the
validated query, caller-supplied nullable thread identity, profile ID, and
normalized scope; it excludes server-generated identity and profile version.

## Run dispatch intent

`run_dispatches_v1` is private application-database authority for the gap
between accepted creation and Agent invocation. Each `run_id` has exactly one
row created atomically with `research_runs_v2` and its initial segment. Status
is `pending`, `leased`, `started`, or `failed`; private lease owner/expiry,
`attempt_count`, bounded `last_error_code`, timestamps, and the run foreign key
support single-node reconciliation. Caller input never supplies worker IDs,
leases, retry budgets, database paths, provider settings, credentials, or
filesystem paths.

Migration `008_run_dispatch_reconciliation` creates and exactly verifies the
table, constraints, foreign key, marker/checksum, and ordered scan index. The
lifespan migration uses a separate `.pre-run-dispatch.bak`, restores it on
verification failure, and refuses to overwrite an existing backup. It performs
no backfill: runs created before `008` retain identity replay but are not
scheduled by the new worker.

## Evidence Entry

证据条目是 append-only snapshot。核心字段包括：

| 字段 | 说明 |
|---|---|
| `evidence_id` | run 内稳定引用 ID |
| `run_id` | 所属执行 |
| `source_type` | public web、provided aggregate、database 等来源类型 |
| `source_url` / `source_id` | 有界来源标识 |
| `snippet` | 持久化证据片段 |
| `fingerprint` | 内容和来源语义的稳定指纹 |
| `baseline_verification_origin` | collection-time origin，不表示人工验证 |

Talent findings and claims must reference evidence IDs from the same run.
Missing or invented references fail closed.

## Run Artifact

`run_artifacts_v2` 保存可交付或审计 artifact。

| 字段 | Generic contract |
|---|---|
| `artifact_id` | `research-report.md` |
| `kind` | `research_report_markdown` 或 `research_report_fallback_markdown` |
| `media_type` | `text/markdown` |
| `content_hash` | artifact `content` 的 SHA-256 hex |

Talent runs additionally persist canonical DecisionBrief and reviewed
publication artifacts. `GET /api/runs/{run_id}/result` only resolves the
current deliverable artifact and rejects missing, empty, unsafe, too-large, or
hash-mismatched content.

## Telemetry 数据结构

Telemetry is run-scoped and returned by `GET /api/telemetry/runs/{run_id}`:

```json
{
  "thread_id": "caller-session",
  "run_id": "run_...",
  "segment_id": "run_..._seg_...",
  "agent_name": "researcher",
  "tool_name": "talent_public_search",
  "duration_ms": 1500,
  "status": "success",
  "error": null,
  "timestamp": "2026-06-26T10:00:00Z"
}
```

## Durable Review 数据模型

Controlled durable review 使用两个独立 SQLite 文件：

- application DB（`DECISION_RESEARCH_AGENT_DB_PATH`）是业务事实源，保存 ResearchRun、不可变决策、
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
verification revision replaces active publication -> superseded
```

Run 的 `delivery_status` 包含：

- `pending`：run 已创建但尚未可交付；
- `review_required`：需要决策，尚不可交付；
- `ready`：`approve` 已 exactly-once resolution；
- `blocked`：`reject` 已 resolution，禁止交付；
- `failed`：研究执行失败。

Generic run 完成且 delivery ready 时，application DB 在同一个 fenced
terminal transaction 内写入 immutable `run_artifacts_v2` result artifact：

| 字段 | Generic contract |
|---|---|
| `artifact_id` | `research-report.md` |
| `kind` | `research_report_markdown` 或 `research_report_fallback_markdown` |
| `media_type` | `text/markdown` |
| `content_hash` | artifact `content` 的 SHA-256 hex |

`GET /api/runs/{run_id}/result` 只解析当前可交付 artifact。Generic run 选择
`research-report.md`；Talent run 优先选择 current publication 绑定的 Markdown
artifact，未启用 publication 时选择 canonical `decision-brief.md`。该投影不返回
本地路径、checkpoint metadata、数据库行或原始异常。

公开 run 投影不会返回 decision reason、actor fingerprint、lease owner、
checkpoint 路径或 checkpoint payload。`approve` 只允许交付，不改变 EvidenceLedger
验证状态；`reject` 不触发新的研究。

`approve` 和 `reject` 是一个 review revision 的不可变终态决策，接受后不能撤回、
改写或替换。重复研究或改变 research input/scope 必须创建新的 `run_id`；对同一
run 已持久化 Evidence fingerprint 的人工 verification 纠正，使用 append-only
decision revision，并在同一 `run_id` 内创建新的 publication revision。旧
publication、review 和 decision 继续作为不可变审计记录。

`GET /api/reviews` 队列和 review detail 都只是 application ledger 的只读投影，
不创建新的事实源或决策权威。application DB 仍是 review、decision、workflow 和
resolution 的业务权威；checkpoint DB 仍只负责 LangGraph 恢复位置。

## Evidence Verification Authority

Evidence verification authority keeps `evidence_entries_v2` immutable and adds:

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

Revisioned publication adds the following delivery state:

| Storage | Contract |
|---|---|
| `review_bundles_v2` | `UNIQUE(run_id, revision)`; immutable bundle per publication revision |
| `review_workflows_v2` | `UNIQUE(run_id, review_revision)`; active workflows may terminate as `superseded` |
| `review_resolutions_v2` | `UNIQUE(run_id, review_id)`; exact review resolution |
| `run_publications_v2` | Explicit publication revision, snapshot, review, artifacts, status, and current pointer |

`run_publications_v2` has a unique partial index on `run_id WHERE is_current=1`.
Publication, ReviewBundle, and post-review segment revision are equal. Snapshot
revision is independent.

```text
review_required -> ready | blocked | stale
ready -> stale
blocked -> stale
```

An accepted non-idempotent verification decision atomically stales the current
publication and supersedes its non-terminal workflow. Finalization is fenced by
`research_runs_v2.state_version`; a changed snapshot creates immutable
revisioned artifacts and a fresh review. Historical review decisions remain
queryable but cannot resolve a later publication.

Only a current publication with `status=ready` is deliverable. Review approval
still does not write Evidence verification decisions.

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06-22 | Evidence Verification Ledger 使用不可变 baseline origin 与独立 verification authority 边界 |
| 2026-06-23 | Revisioned publication 使用 fresh review、authenticated API/CLI 与 current delivery 语义 |
| 2026-06-20 | Controlled review 队列/详情是只读投影；review revision 与新 run 分别承接纠正语义 |
| 2026-06-19 | Durable review 使用双数据库权威边界、四表模型、状态机和 blocked delivery |
| 2026-05-19 | 初始数据模型文档 |
