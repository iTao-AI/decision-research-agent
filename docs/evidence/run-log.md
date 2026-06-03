# Run Log

本文件记录端到端任务执行的实际数据。当前只有 E2E Run #1 可作为已完成端到端样例；专项 benchmark 和 token before/after 对比仍待后续稳定脚本补充。

**计划测量项：**

- 平均耗时与 P95 耗时：使用 5-10 个固定任务样例，记录完成时间分布。
- Token 消耗：通过已有 `token_tracking.py` 和 `GET /api/token-usage/{thread_id}` 记录 input/output/total token。
- 子 Agent 调用次数：记录单次任务中主 Agent 派发子 Agent 的次数。
- 缓存命中率：对比 Tavily 搜索在短时间重复查询时的缓存命中情况。

**前端构建：**

- `cd frontend && npm install`：成功
- `cd frontend && npm run build`：成功，输出 "built in 357ms"

**已有数据：**

- Local pytest run: 264 passed, 0 failed（`python -m pytest -q`）
- Docker 部署: 本机验证通过（见 [QA 报告摘要](assets/qa-report-summary.md)）

## E2E Run #1

- **日期**: 2026-06-01
- **环境**: 本机 (macOS, Python 3.13, DeepSeek API)
- **输入问题**: "2024年AI发展趋势"
- **命令**: POST /api/task + WebSocket /ws/evidence-run-002
- **总耗时**: 4 分 42 秒 (281.97s)
- **子 Agent 调用**: 网络搜索助手 (2 次，分别搜索技术突破和行业动态)
- **工具调用**: 网络搜索工具 (Tavily，多次搜索查询)
- **WebSocket 事件**: 50 个 monitor_event (session_created → assistant_call → tool_start → task_result)
- **Token 用量**: input: 446,542 / output: 12,723 / total: 459,265 / cost: $19.39 / calls: 21
- **生成产物**: `output/session_evidence-run-002/2024年AI发展趋势报告.md` (12,142 bytes)
- **备注**: WebSocket 180s 超时后断开，但报告文件已完整生成；未生成 PDF（需 WeasyPrint 系统依赖）

## Phase 8 Closure Notes

- **状态**: DONE_WITH_CONCERNS
- **已完成验证**: `python -m pytest -q` 为 264 passed；`cd frontend && npm run build` 成功。
- **E2E 结论**: E2E Run #1 是当前唯一稳定 completed 样例。后续多次同题 E2E 运行出现 459K 到 3M tokens 波动，且报告生成行为不稳定。
- **调查结论**: 在未修改的原始代码上重跑同题 E2E 也出现无报告结果，说明 token/report 波动主要来自 DeepSeek 模型随机行为，不能作为本轮 token before/after benchmark 证据。
- **后续跟进**: Task 6（token before/after 对比）和 Task 8（5 问 benchmark）应等固定 WebSocket 客户端脚本、重复运行策略和中位数统计方案确定后再执行。

## Phase 9 Plan

- **状态**: PLANNED
- **目标**: 将 Phase 8 的 E2E 不稳定报告生成问题收敛为确定性后端终态：`completed`、`completed_with_fallback` 或 `failed`。
- **验证策略**: 后端单元测试覆盖 persistence、timeout、agent run accumulator 和 task finalizer；集成测试覆盖 completed、fallback、exception、timeout；真实 E2E 使用 `scripts/e2e_runner.py` 手动记录。
- **非目标**: 本阶段不做 5 问 benchmark，不做 prompt 调优，不把真实 LLM E2E 放入 CI。
