# Implementation Tasks: Agent 间通信 — SharedContext 共享事实层

**Change ID:** `agent-inter-agent-communication`

---

## Task Group 1: 基础层 — SharedContext 实现

- [x] 1.1 新建 `agent/shared_context.py`，实现 `SharedContext` 类 ✓ 2026-05-11
  - 使用 in-memory 存储 + ContextVar 实现 per-thread_id 隔离
  - `publish_fact(thread_id, ...)` — 支持 topic/source/fact，去重，容量上限 100 条
  - `query_facts(thread_id, topic, source_filter)` — 按主题/来源过滤
  - `clear_facts(thread_id)` — session 级别清理
- [x] 1.2 新建 `tests/unit/test_shared_context.py` ✓ 2026-05-11
  - 发布/查询基础路径、去重、空数据、source_filter
  - 容量上限（超过 100 条自动淘汰最早的）
  - 线程隔离（不同 thread_id 不互相干扰）
  - clear_facts 正常路径和空 thread_id 路径
- [x] 1.3 新建 `tests/unit/test_shared_context_integration.py`，覆盖 ContextVar 集成路径

**Self-Check:** PASSED — 18/18 tests pass, 73 existing tests no regressions

---

## Task Group 2: 主 Agent 集成 — StateGraph 接入 shared_facts

- [x] 2.1 改造 `agent/main_agent.py`，StateGraph 初始化时注入 shared_facts ✓ 2026-05-11
- [x] 2.2 验证 main_agent 可正常运行，StateGraph 包含 shared_facts 字段 ✓ 2026-05-11
- [x] 2.3 新增回归测试，确认 main_agent 初始化不破坏现有功能 ✓ 2026-05-11

**Self-Check:** PASSED — shared_context accessible from main_agent, no ContextVar conflict with existing api/context.py

---

## Task Group 3: 子 Agent 接入 — 事实发布和查询

- [x] 3.1 改造 `agent/sub_agents/network_search_agent.py`，搜索结果发布到 shared_context ✓ 2026-05-11
- [x] 3.2 改造 `agent/sub_agents/database_query_agent.py`，查询结果发布到 shared_context ✓ 2026-05-11
- [x] 3.3 改造子 Agent 执行前查询 shared_context，利用已发布事实增强输出 ✓ 2026-05-11
- [x] 3.4 新增测试覆盖子 Agent 发布/查询路径 ✓ 2026-05-11

**Self-Check:** PASSED — sub-agents have shared_context tools, tools are callable, 98 tests total no regressions

---

## Completion Checklist

- [ ] All task groups complete
- [ ] All quality gates passed
- [ ] Documentation synced
- [ ] Ready for `/openspec-archive`
