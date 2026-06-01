# Run Log

本文件记录端到端任务执行的实际数据。当前尚未运行专项基准测试，以下指标待后续填充。

**计划测量项：**

- 平均耗时与 P95 耗时：使用 5-10 个固定任务样例，记录完成时间分布。
- Token 消耗：通过已有 `token_tracking.py` 和 `GET /api/token-usage/{thread_id}` 记录 input/output/total token。
- 子 Agent 调用次数：记录单次任务中主 Agent 派发子 Agent 的次数。
- 缓存命中率：对比 Tavily 搜索在短时间重复查询时的缓存命中情况。

**前端构建：**

- `cd frontend && npm install`：成功
- `cd frontend && npm run build`：成功，输出 "built in 357ms"

**已有数据：**

- Local pytest run: 247 passed, 0 failed（`python -m pytest -q`）
- Docker 部署: 本机验证通过（见 [QA 报告摘要](assets/qa-report-summary.md)）

## E2E blocked with partial evidence

- **阻塞原因**: `.env` 中 `OPENAI_API_KEY` 和 `TAVILY_API_KEY` 均为占位值（`your-*`），无法调用真实 LLM 和搜索服务
- **已完成局部链路**:
  - 后端测试全绿：247 passed, 0 failed（`python -m pytest -q`）
  - 前端构建通过：`cd frontend && npm run build` 成功，built in 357ms
  - Docker QA 验证通过（见 `assets/` 中的截图和 QA 摘要）
  - API 端点响应正确（POST /api/task, GET /api/files, WebSocket）
- **不能声称的指标**: 真实 token 用量、真实外部搜索结果、真实耗时、P95 延迟、子 Agent 调用次数
