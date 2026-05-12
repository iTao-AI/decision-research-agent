# Implementation Tasks: Phase 1 — 子 Agent 架构升级

**Change ID:** `sub-agent-architecture-upgrade`

---

## Phase A: 基础层（AgentContext + AgentConfig + BaseAgent）

- [x] A.1 创建 `agent/sub_agents/base.py`，定义 `AgentContext` dataclass ✓ 2026-05-10
- [x] A.2 定义 `AgentConfig` dataclass ✓ 2026-05-10
- [x] A.3 定义 `BaseAgent` 基类 ✓ 2026-05-10
- [x] A.4-A.5 编写测试（合并为 test_agent_context.py） ✓ 2026-05-10

**Quality Gate:** 5/5 通过 ✓

---

## Phase B: 子 Agent 重构（NetworkSearchAgent）

- [x] B.1-B.4 NetworkSearchAgent 类 + main_agent.py 适配层 ✓ 2026-05-10

**Quality Gate:** 3/3 通过 ✓

---

## Phase C: 子 Agent 重构（DatabaseQueryAgent）

- [x] C.1 创建 `agent/sub_agents/database_query_agent.py` ✓ 2026-05-10
- [x] C.2 验证 `to_dict()` 输出与原始 dict 一致 ✓ 2026-05-10
- [x] C.3 编写 `tests/unit/test_database_query_agent.py` ✓ 2026-05-10

**Quality Gate:** 3/3 通过 ✓

---

## Phase D: 子 Agent 重构（KnowledgeBaseAgent）

- [x] D.1 创建 `agent/sub_agents/knowledge_base_agent.py` ✓ 2026-05-10
- [x] D.2 验证 `to_dict()` 输出与原始 dict 一致 ✓ 2026-05-10
- [x] D.3 编写 `tests/unit/test_knowledge_base_agent.py` ✓ 2026-05-10

**Quality Gate:** 3/3 通过 ✓

---

## Phase E: main_agent.py 适配层 + 回归测试

- [x] E.1 修改 `agent/main_agent.py` — 添加 `_resolve_subagent` 适配层 ✓ 2026-05-10
- [x] E.2-E.3 全量回归测试 — 验证所有 Agent 升级后行为不变 ✓ 2026-05-10

**Quality Gate:** 全量测试通过 ✓

---

## Completion Checklist

- [x] 所有 Phase 完成
- [x] 所有质量门通过
- [ ] 文档/注释更新
- [ ] 准备 `/openspec-archive sub-agent-architecture-upgrade`
