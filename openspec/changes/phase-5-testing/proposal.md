# Proposal: Phase 5 — 分层测试体系

**Change ID:** `phase-5-testing`
**Created:** 2026-05-18
**Status:** Draft

---

## Problem Statement

当前已有 133 个单元测试，覆盖了工具函数、安全校验、Telemetry、SharedContext 等确定性逻辑。但存在以下空白：

1. **无集成测试** — Agent 委派链路、报告生成、并发隔离等场景未覆盖
2. **无 API 端点集成测试** — server.py 的 REST 端点（/api/task、/api/upload）缺乏端到端验证
3. **无 ContextVar 隔离验证** — 两个并发 run_deep_agent 调用是否真正隔离，无测试保证
4. **测试组织不规范** — 所有测试在 `tests/unit/` 下，没有 integration 分层

## Proposed Solution

引入分层测试策略，按"确定性 vs 非确定性"拆分：

### 层 1：集成测试 — Agent 委派链路

Mock LLM 响应，验证主 Agent → 子 Agent 的委派结构是否正确。
- 不验证 LLM 输出内容（不确定），只验证调用结构（确定）
- 验证 subagents_list 格式、工具注册、任务分发

### 层 2：集成测试 — 报告生成

验证 Markdown/PDF 报告文件生成到正确的工作目录。
- 验证文件路径、文件存在性
- 验证 Markdown 内容包含预期标题

### 层 3：集成测试 — ContextVar 隔离

两个并发 run_deep_agent 调用，验证 session_dir 不交叉。
- 创建两个异步任务，分别设置不同 session_dir
- 验证每个任务只能读取自己的 session_dir

### 层 4：API 端点测试

验证 server.py 的核心 REST 端点：
- POST /api/task — 启动任务，返回 thread_id
- POST /api/upload — 文件上传，路径遍历防御
- GET /api/telemetry/{thread_id} — 遥测查询

### 层 5：测试基础设施

- 创建 `tests/conftest.py` — 共享 fixtures（session_dir、mock LLM、测试配置）
- 创建 `tests/integration/` 目录

## Scope

### In Scope
- `tests/conftest.py` — 新增共享 fixtures
- `tests/integration/test_agent_delegation.py` — Agent 委派链路
- `tests/integration/test_report_generation.py` — 报告生成
- `tests/integration/test_context_isolation.py` — ContextVar 隔离
- `tests/integration/test_api_endpoints.py` — API 端点测试

### Out of Scope
- 前端 UI 测试
- 真实 LLM API 调用测试
- 性能/压力测试
- 已有单元测试的修改（已有 133 个不变）

## Impact Analysis

| Component | Change Required | Details |
|-----------|-----------------|---------|
| `tests/conftest.py` | 新增 | 共享 fixtures：session_dir、mock LLM、event_loop |
| `tests/integration/` | 新增目录 + 4 个文件 | 集成测试 |
| `api/server.py` | 可选修改 | 如需测试，可能暴露更多可测试接口 |
| 已有测试 | 无修改 | 133 个单元测试保持不变 |

## Success Criteria

- [ ] 集成测试覆盖 Agent 委派、报告生成、ContextVar 隔离、API 端点
- [ ] 全量测试（unit + integration）全部通过，无回归
- [ ] 测试目录结构分层清晰：`tests/unit/` + `tests/integration/`
- [ ] conftest.py 提供可复用的 fixtures

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Mock LLM 与实际行为不一致 | Medium | Medium | Mock 只验证结构，不验证内容；与实际 agent 输出格式对齐 |
| ContextVar 隔离测试在 CI 中不稳定 | Low | High | 使用 asyncio.gather 确保真正的并发，不依赖时序 |
| 集成测试运行慢 | Medium | Low | 集成测试标记 `@pytest.mark.slow`，可单独跳过 |
