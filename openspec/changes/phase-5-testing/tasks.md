# Implementation Tasks: Phase 5 — 分层测试体系

**Change ID:** `phase-5-testing`

---

## Phase A: 测试基础设施

- [x] A.1 创建 `tests/conftest.py`：session_dir fixture（tmpdir + 自动清理）
- [x] A.2 创建 `tests/integration/` 目录 + `__init__.py`
- [x] A.3 创建 `tests/integration/test_api_endpoints.py`：验证现有 telemetry API 端点（复用 Phase 4 已通过的 API 测试，迁移到 FastAPI TestClient）
- [x] A.4 运行全量测试，确认无回归

**Self-Check:**
- `pytest tests/ --tb=short` 全部通过
- conftest.py fixtures 可在 integration 测试中引用

---

## Phase B: 报告生成集成测试

- [x] B.1 编写 `tests/integration/test_report_generation.py`：Markdown 文件生成到 session_dir
- [x] B.2 验证报告路径隔离（两个 session_dir 不交叉）
- [x] B.3 运行新增测试，确认通过

**Self-Check:**
- `pytest tests/integration/test_report_generation.py -v` 全部通过
- 报告文件确实生成在 session_dir 下

---

## Phase C: ContextVar 隔离集成测试

- [x] C.1 编写 `tests/integration/test_context_isolation.py`：两个并发 run_deep_agent，验证 session_dir 隔离
- [x] C.2 验证 ContextVar 在 finally 中正确清理
- [x] C.3 运行新增测试，确认通过

**Self-Check:**
- `pytest tests/integration/test_context_isolation.py -v` 全部通过
- 并发隔离测试使用 asyncio.gather，不依赖时序

---

## Phase D: Agent 委派链路集成测试

- [x] D.1 编写 `tests/integration/test_agent_delegation.py`：Mock LLM 响应，验证 subagents_list 结构
- [x] D.2 验证每个子 Agent 的 to_dict() 输出格式
- [x] D.3 验证工具注册完整性
- [x] D.4 运行新增测试，确认通过

**Self-Check:**
- `pytest tests/integration/test_agent_delegation.py -v` 全部通过
- Mock 不验证 LLM 内容，只验证结构

---

## Phase E: 全量验证

- [x] E.1 运行全量测试套件（unit + integration）
- [x] E.2 确认测试数增长（133 → 165, +32）
- [x] E.3 验证 `python api/server.py` 能正常启动
- [x] E.4 无回归

**Self-Check:**
- `pytest tests/ -v` 全部通过
- 测试目录结构清晰：tests/unit/ + tests/integration/

---

## Completion Checklist

- [x] All phases complete
- [x] All quality gates passed
- [x] Documentation synced
- [ ] Ready for `/openspec-archive-change`
