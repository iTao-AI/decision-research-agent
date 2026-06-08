# Run Log

本文件记录端到端任务执行的实际数据。当前只有 E2E Run #1 可作为已完成端到端样例；重复 benchmark runner 已补充，但新的多轮 benchmark 和 token before/after 对比仍待真实执行。

**计划测量项：**

- 平均耗时与 P95 耗时：使用 5-10 个固定任务样例，记录完成时间分布。
- Token 消耗：通过已有 `token_tracking.py` 和 `GET /api/token-usage/{thread_id}` 记录 input/output/total token。
- 子 Agent 调用次数：记录单次任务中主 Agent 派发子 Agent 的次数。
- 缓存命中率：对比 Tavily 搜索在短时间重复查询时的缓存命中情况。

**前端构建：**

- `cd frontend && npm install`：成功
- `cd frontend && npm run build`：成功，输出 "built in 357ms"

**已有数据：**

- Local pytest run: 303 passed, 0 failed（`PYTHONPATH=. pytest -q`，2026-06-08）
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

## Phase 9 Implementation

- **状态**: DONE（2026-06-03）
- **目标达成**: 将 E2E 不稳定报告生成问题收敛为确定性后端终态。
- **新增模块**:
  - `agent/run_result.py` — `AgentRunAccumulator`（流状态收集）+ `AgentRunResult`（不可变结果对象）+ `process_stream_chunk()`（替换 server.py 内联流处理）
  - `api/task_finalizer.py` — `TaskFinalization`（终态数据类）+ `finalize_task_run()`（报告搜索 / fallback 报告 / 持久化）
  - `api/server.py` — `_mark_task_timeout()` 回调 + `_run_task_with_persistence()` 封装；WebSocket 新增 `task_finalized` 事件
  - `api/monitor.py` — `report_task_finalized()` 方法（发射终态事件）
- **确定性终态**: `completed`（正式报告）| `completed_with_fallback`（兜底报告）| `failed`（异常/超时）
- **Fallback 报告内容**: 线程 ID、生成时间、原始查询、最后一个 agent 输出、诊断事件列表
- **测试覆盖**: 282 passed, 0 failed（含 `test_task_finalizer.py`、`test_persistence.py`、`test_monitor_sanitization.py` 中 Phase 9 相关用例）
- **非目标**: 本阶段未做 5 问 benchmark、prompt 调优、真实 LLM E2E 入 CI

## Phase 9 5-Query Benchmark（2026-06-03）

- **日期**: 2026-06-03
- **环境**: macOS, Python 3.13, deepseek-chat, 127.0.0.1:8000
- **方法**: 5 条固定 query，`scripts/e2e_runner.py` 串行执行，每条 timeout 900s
- **说明**: 单次快照，非统计采样。DeepSeek 不暴露 seed 参数，不同 run 的 token 消耗可能差异显著。

### 逐条数据

| Thread ID | Query | 目标子代理 | 状态 | 耗时 | Token | 子代理调用 | 工具调用 | 报告大小 | Fallback |
|---|---|---|---|---|---|---|---|---|---|
| evidence-001 | 2024年人工智能三大重要技术突破 | network_search | completed_with_fallback | 55s | 133,562 | 2 | 8 | 8,606 bytes | ✓ |
| evidence-002 | What are the key challenges in implementing RAG systems? | network_search | completed | 111s | 247,921 | 2 | 10 | 14,399 bytes | — |
| evidence-003 | 对比 PyTorch 和 JAX 在 LLM 训练中的性能差异 | network_search | completed | 117s | 821,685 | 2 | 23 | 15,427 bytes | — |
| evidence-004 | 查询项目数据库中最近一个月的数据 | database_query | completed_with_fallback | 16s | 38,804 | 1 | 1 | 1,415 bytes | ✓ |
| evidence-005 | 检索知识库中关于 Agent 架构的文档并总结 | knowledge_base | completed_with_fallback | 91s | 134,011 | 2 | 13 | 3,100 bytes | ✓ |

### 汇总

| 指标 | 值 |
|------|-----|
| 总耗时 | 390s（6.5 分钟） |
| 平均耗时 | 78s（中位数 91s） |
| Token 总量 | 1,375,983 |
| Token 中位数 | 134,011 |
| 完成率 | 5/5（0 failed, 0 timeout） |
| Fallback 率 | 3/5（60%） |
| 报告大小范围 | 1,415 — 15,427 bytes |

### 备注

- **evidence-001**（AI 突破）：网络搜索子代理正常工作，但 agent 未调用 write_file 工具写报告，走 fallback 路径。fallback 报告含最后一次 agent 文本输出和诊断事件列表。
- **evidence-002**（RAG 挑战）：唯一产生正式报告的英文 query，agent 调用了 write_file 输出完整 Markdown 报告。
- **evidence-003**（PyTorch vs JAX）：token 消耗最大（822K），agent 进行了多次搜索和对比，生成了正式报告。Token 波动在 DeepSeek 正常范围内。
- **evidence-004**（数据库查询）：外部 MySQL 不可用，子代理快速返回失败后走 fallback 路径。16s 耗时说明系统正确处理了 graceful degradation。
- **evidence-005**（知识库检索）：RAGFlow 未配置或不可用，走 fallback 路径。13 次工具调用说明 agent 尝试了多次检索。
- **成本说明**: token_tracking.py 定价已修正为 DeepSeek 官方定价（¥1/1M input, ¥4/1M output），5 问总成本 ¥1.50，单条 ¥0.04 — ¥0.87。
- **evidence-004/005**: 这两个 query 的可用性依赖外部服务，结果证明了系统的 graceful degradation 能力 —— 不可用时走 fallback 而非 crash。

## Phase 10 ResearchRun / EvidenceLedger Harness（2026-06-08）

- **状态**: IMPLEMENTED_WITHOUT_LIVE_BENCHMARK
- **目标**: 将单次任务从“任务状态 + 输出文件”扩展为可审计 ResearchRun：原始 query、终态、assistant/tool 调用计数、diagnostics、token usage、质量门禁和 EvidenceLedger。
- **新增模块**:
  - `agent/research.py` — evidence 抽取、引用匹配、report quality gate。
  - `api/persistence.py` — `research_runs` 和 `evidence_entries` SQLite 表。
  - `api/task_finalizer.py` — 任务终态时持久化 ResearchRun 和 EvidenceLedger。
  - `api/server.py` — `GET /api/research/runs/{thread_id}` 和 `GET /api/research/runs`。
  - `tools/deep_search_agent_tool.py` — `research-run` / `research-runs` 查询命令。
  - `scripts/benchmark_runner.py` — 多轮固定 query benchmark 汇总脚本。
- **质量门禁**: 空报告和 fallback 报告判定为 failed；无 evidence 或无 cited evidence 判定为 warning；token 超过阈值判定为 warning。
- **证据边界**: EvidenceLedger 条目来自工具消息中的来源型观察。`citation_status=cited` 只表示 source URL 出现在最终 Markdown 报告中，`verification_status` 默认仍为 `unverified`，不代表人工事实核验。
- **benchmark 边界**: 本阶段只实现重复 benchmark runner 和汇总逻辑，未执行新的真实多轮 benchmark；现有 5-query 数据仍是单次快照，不能写成稳定中位数/P95。
- **验证**: `PYTHONPATH=. pytest -q`，303 passed, 0 failed（2026-06-08）。
