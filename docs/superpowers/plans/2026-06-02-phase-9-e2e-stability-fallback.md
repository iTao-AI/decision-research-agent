# Phase 9: E2E 稳定性与报告生成兜底

## Summary

- 目标：让真实 E2E 任务在「生成报告 / 未生成报告 / 超时 / 异常」四种情况下都有确定性终态，避免 CI 或人工验证看到任务“看似通过但没有产物”。
- 关键修正：把 Phase 8 遗留的随机报告生成问题收敛为后端终态治理，不做 benchmark、不做 prompt 调优、不引入新的前端测试框架。
- Autoplan 结论：原计划需要补强 timeout、异常吞掉、last agent text 捕获、report 选择契约和 `completed_with_fallback` 持久化。

## Key Changes

- 新增后端运行结果契约：`AgentRunResult`
  - 字段包含 `thread_id`、`query`、`session_dir`、`last_agent_text`、`assistant_calls`、`tool_starts`、`error_message`。
  - `run_deep_agent()` 正常结束时返回该结构。
  - LangGraph stream 异常时只负责上报 monitor error，然后 re-raise；禁止再返回 `"Error: ..."` 并被上层标记为成功。

- 新增内部 accumulator
  - `_process_stream_chunk(chunk, accumulator)` 继续发 WebSocket 事件，同时记录最后一段非空 AIMessage 文本、assistant tool call 数、tool start 数和诊断信息。
  - fallback 报告只使用 accumulator 内部捕获内容，不依赖 WebSocket 截断后的显示文本。

- 新增任务 finalizer：`finalize_task_run(...)`
  - 只在 `output/session_{thread_id}` 下查找报告。
  - 排除 `fallback_report.md`，只接受 `stat().st_size > 0` 的 `.md` 文件，选择最新 mtime 的报告作为正式产物。
  - 找到正式报告：状态写 `completed`，持久化 `output_path` 和 best-effort `token_usage_json`。
  - 未找到正式报告：写确定性 `fallback_report.md`，状态写 `completed_with_fallback`，内容包含原始 query、原因、最后 agent 输出和诊断；不伪装成完整研究结果。
  - 异常或 timeout：状态写 `failed`，持久化 `error_message`，不生成 fallback 成功态。

- 修正 task timeout 语义
  - `api/task_tracker.py` 不再把 `asyncio.TimeoutError` 转成 `"Error: Agent task timed out..."` 字符串。
  - `create_tracked_task(..., on_timeout=...)` 在超时时调用 server 提供的回调，由回调写入 `failed` 并发 monitor error。
  - timeout 不是成功路径，也不会进入 `completed_with_fallback`。

- 修正持久化终态
  - `TERMINAL_STATUSES = {"completed", "completed_with_fallback", "failed"}`。
  - `completed_with_fallback` 同样写 `completed_at`。
  - `GET /api/tasks/{thread_id}` 支持返回 `completed_with_fallback`。

- 前端只做必要适配
  - 处理新增 `task_finalized` WebSocket 事件。
  - `completed` 和 `completed_with_fallback` 都触发文件刷新；fallback 状态显示为“已生成兜底报告”。
  - 不引入 Vitest 或新的前端测试依赖，本阶段用 `npm run build` 和手动 E2E 验证覆盖。

- 新增手动 E2E runner：`scripts/e2e_runner.py`
  - 先连接 WebSocket，再提交 `POST /api/task`。
  - WebSocket 只作为事件证据，最终完成状态以轮询 `GET /api/tasks/{thread_id}` 为准。
  - 支持 `--api-base`、`--ws-base`、`--query`、`--api-key`、`--timeout-seconds`、`--output`。
  - 输出 JSON：`thread_id`、`query`、`status`、`elapsed_seconds`、`websocket_events`、`assistant_calls`、`tool_starts`、`token_usage`、`output_path`、`report_size_bytes`、`fallback_used`。

## Public Interfaces

- `GET /api/tasks/{thread_id}`
  - `status` 新增合法值：`completed_with_fallback`。
  - `output_path` 在 `completed` 和 `completed_with_fallback` 时都应存在。
  - `error_message` 只在 `failed` 时作为失败原因来源。

- WebSocket 新增事件：`task_finalized`
  - payload 包含 `thread_id`、`status`、`fallback_used`、`output_path`、`error_message`。
  - 兼容现有 `task_result`，fallback 结束时额外发一条用户可读结果消息。

## Test Plan

- 后端单元测试
  - persistence：`completed_with_fallback` 会写 `completed_at`。
  - task tracker：timeout 会触发 `on_timeout`，不会返回 `"Error: ..."` 字符串。
  - main agent accumulator：mock stream chunk 后能捕获 last agent text、assistant call 和 tool count。
  - finalizer：有正式 `.md` 时选最新报告；无正式报告时生成 `fallback_report.md`；异常/timeout 不走 fallback 成功态。

- 后端集成测试
  - mock `run_deep_agent()` 返回有报告结果：任务最终为 `completed`。
  - mock `run_deep_agent()` 返回无报告结果：任务最终为 `completed_with_fallback`。
  - mock `run_deep_agent()` 抛异常：任务最终为 `failed`。
  - mock timeout：任务最终为 `failed`，有 `error_message`。

- 前端验证
  - 运行 `cd frontend && npm run build`。
  - 手动验证 `task_finalized` 到达后 UI 停止 running 状态并刷新文件列表。
  - 不新增前端测试框架。

- E2E 验证
  - 启动后端和前端。
  - 用真实 key 手动运行 `scripts/e2e_runner.py`。
  - 验证 JSON 中 terminal status、report size、fallback flag 和 persisted task 状态一致。
  - 不把真实 LLM E2E 放入 CI。

## Docs And Hygiene

- 更新 API 文档，说明 `completed_with_fallback`、`task_finalized` 和 runner 输出结构。
- 更新 `docs/evidence/run-log.md`，把 Phase 8 “DONE_WITH_CONCERNS” 后续闭环记录到 Phase 9。
- 修正 `CLAUDE.md` 中 Node 版本描述，使其与 `AGENTS.md`、README、README_CN 一致：`Node.js 20.19+ or 22.12+`。

## Assumptions

- Phase 9 不解决 LLM 是否稳定调用 `generate_markdown` 的根因，只保证后端产物和状态确定。
- fallback report 是透明兜底报告，不声称完成完整研究。
- 不新增依赖，除非 `scripts/e2e_runner.py` 实测必须补充 WebSocket 客户端依赖；如必须新增，优先使用当前环境已由 `uvicorn[standard]` 提供的 `websockets`。
- 不自动 commit、push、创建 PR；实现完成后再按项目流程由用户确认。
