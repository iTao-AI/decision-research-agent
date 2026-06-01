# Run Log

本文件记录端到端任务执行的实际数据。当前尚未运行专项基准测试，以下指标待后续填充。

**计划测量项：**

- 平均耗时与 P95 耗时：使用 5-10 个固定任务样例，记录完成时间分布。
- Token 消耗：通过已有 `token_tracking.py` 和 `GET /api/token-usage/{thread_id}` 记录 input/output/total token。
- 子 Agent 调用次数：记录单次任务中主 Agent 派发子 Agent 的次数。
- 缓存命中率：对比 Tavily 搜索在短时间重复查询时的缓存命中情况。

**已有数据：**

- Local pytest run: 235 passed / 12 failed（12 失败集中在 WeasyPrint 本机依赖和 retry monitor mock）
- Docker 部署: 本机验证通过（见 [QA 报告摘要](assets/qa-report-summary.md)）
