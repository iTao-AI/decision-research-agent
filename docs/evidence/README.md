# Evidence Pack

本目录沉淀 Deep Search Agent 的运行证据，用于审查项目真实能力。

## 目录

| 文件 | 说明 |
|------|------|
| [run-log.md](run-log.md) | E2E Run #1 数据（282s / 459K tokens / 2 子Agent）+ Phase 8 收口 + Phase 9 确定性终态 + Phase 10 ResearchRun / EvidenceLedger |
| [technical-decisions.md](technical-decisions.md) | 关键技术决策说明与代码路径 |
| [durable-hitl-gate-report.json](durable-hitl-gate-report.json) | P1B durable HITL feasibility 的 13 项 gate 机器可读结果 |
| [p2a-real-source-proof.json](p2a-real-source-proof.json) | P2A PR3 小样本真实来源 proof 的有界机器可读报告 |
| [p2a-real-source-proof.md](p2a-real-source-proof.md) | P2A PR3 人工核验、publication、fresh review 与限制说明 |

## Phase 9 产出（2026-06-03）

- 确定性终态：`completed` / `completed_with_fallback` / `failed`
- Fallback 报告生成：当 agent 未产出正式报告时，系统自动生成含诊断信息的兜底报告
- Timeout 回调：超时任务在取消前持久化 `failed` 状态
- 测试：282 passed, 0 failed（含 `test_task_finalizer.py`、`test_persistence.py` 中 Phase 9 相关用例）

## Phase 10 产出（2026-06-08）

- ResearchRun：终态任务记录 query、status、token usage、diagnostics、assistant/tool 调用计数和质量门禁。
- EvidenceLedger：从工具消息抽取来源型 evidence，并在最终 Markdown 报告中匹配 source URL。
- API：`GET /api/research/runs/{thread_id}` 和 `GET /api/research/runs`。
- Benchmark runner：`scripts/benchmark_runner.py` 可执行重复固定 query benchmark；新的多轮结果尚未执行。
- 测试：303 passed, 0 failed（`PYTHONPATH=. pytest -q`，2026-06-08）。

## P1B Durable HITL Feasibility（2026-06-19）

- 13/13 gate PASS，包括容器重启、幂等冲突、lease reclaim、sync durability
  和五个 SIGKILL crash windows。
- 完整后端回归：598 passed, 0 failed（Python 3.11 compatibility
  environment，`python -m pytest -q`）。
- 该结果只证明有边界的 feasibility；feature flag 仍默认关闭，不代表生产启用。

## P2A Real-Source Proof

- 样本由固定 manifest 声明，Evidence 以
  `baseline_verification_origin=none` 进入现有核验流程。
- 每条 Evidence 由本地 operator 打开公开来源后做 `verify` 或 `reject`
  决策；approval 只许可交付，不替代 Evidence verification。
- 2026-06-25 实际 proof：6 条来源均经人工核验为 `human_verified`，
  unresolved 0；publication revision 2 为 `ready`，fresh review revision 2
  为 `approved`。
- 报告只证明小样本工作流执行，不是来源归档、抓取能力、市场覆盖率或招聘结果声明。

## 已有截图

运行截图（由 Docker QA 报告提取，存放于 `assets/` 目录）：
- [01-homepage.png](assets/01-homepage.png)
- [02-mobile.png](assets/02-mobile.png)
- [03-tablet.png](assets/03-tablet.png)
- [Docker QA 摘要](assets/qa-report-summary.md)

## 数据来源

所有数字指标来自实际命令输出、日志或测试报告，不以推测数字占位。
