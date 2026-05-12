# Proposal: Phase 1 — 子 Agent 架构升级

**Change ID:** `sub-agent-architecture-upgrade`
**Created:** 2026-05-10
**Status:** Draft

---

## Problem Statement

当前三个子 Agent（`network_search_agent`、`database_query_agent`、`knowledge_base_agent`）是 dict 字面量，没有类型注解、没有状态管理、没有统一的上下文传递机制。

**为什么这是个问题：**
1. **无法讲述架构故事** — 面试或 code review 时，问"Agent 之间怎么共享上下文？怎么做状态追踪？" — 当前代码答不上来
2. **扩展性差** — 每个新 Agent 都要复制粘贴 dict 模板，增加 tool 也要手动改
3. **无类型安全** — dict 的 key 拼写错误在运行时才会暴露
4. **无状态追踪** — 无法记录 Agent 的调用次数、token 消耗、执行时间等元数据

## Proposed Solution

引入 `AgentConfig`（TypedDict/dataclass）+ `AgentContext` 模式：

1. **`AgentContext`** — 记录 Agent 执行上下文（thread_id、workspace_dir、memory、metadata）
2. **`AgentConfig`** — 带类型注解的 Agent 配置对象，替代 dict 字面量
3. **`BaseAgent`** — 基类提供统一的初始化和元数据追踪接口
4. **适配层** — 保持与 `deepagents.create_deep_agent` 的兼容性（subagents 仍需要是 dict 格式）

## Scope

### In Scope
- `agent/sub_agents/base.py` — 新建 AgentContext + AgentConfig + BaseAgent
- `agent/sub_agents/network_search_agent.py` — 从 dict 重构为 NetworkSearchAgent 类
- `agent/sub_agents/database_query_agent.py` — 从 dict 重构为 DatabaseQueryAgent 类
- `agent/sub_agents/knowledge_base_agent.py` — 从 dict 重构为 KnowledgeBaseAgent 类
- `agent/main_agent.py` — 适配层：Agent 类 → dict 格式输出

### Out of Scope
- `api/context.py` 整合 — Phase 1 保持 AgentContext 独立，后续 Phase 再与 `api.context` 的 ContextVar 整合
- `monitor` 单例解耦 — 通过 AgentContext 注入属于 Phase 4 范围
- Agent 之间共享状态（SharedBus）— 属于 Phase 3 范围
- 工具工程化（env 加载、错误降级）— 属于 Phase 2 范围

## Impact Analysis

| Component | Change Required | Details |
|-----------|-----------------|---------|
| `agent/sub_agents/` | Yes — 重构 | 3 个子 Agent 从 dict 改为类 |
| `agent/main_agent.py` | Yes — 适配层 | Agent 类需输出 dict 兼容 deepagents |
| `agent/prompts.py` | No | prompt 配置不变 |
| 工具层 | No | 工具函数无需修改 |
| 前端 | No | 对外接口无变化 |
| 测试 | Yes | 需新增 AgentContext 和配置类测试 |

## Architecture Considerations

### 兼容性约束

`deepagents.create_deep_agent` 期望 `subagents` 参数是 dict 列表。`AgentConfig` 必须提供 `.to_dict()` 方法输出兼容格式，或在 `main_agent.py` 中做适配转换。

### 与现有上下文系统的关系

`api/context.py` 已有 `ContextVar` 管理 session 和 thread 状态。Phase 1 的 `AgentContext` 是 Agent 层的上下文，不与 `api.context` 冲突，但未来应该整合。Phase 1 先独立实现，避免耦合过深。

## Success Criteria

- [ ] 3 个子 Agent 从 dict 升级为类，功能不变（行为一致性验证）
- [ ] `AgentConfig` 带完整类型注解，mypy/pyright 无报错
- [ ] `AgentContext` 支持跨工具调用的状态共享
- [ ] `main_agent.py` 通过适配层输出兼容格式
- [ ] 新增单元测试覆盖 AgentContext 和配置类

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| `deepagents` 内部 dict 格式变化导致不兼容 | Low | High | 先读 `deepagents` 源码确认 dict schema，严格对齐 |
| Agent 重构后行为变化（prompt 丢失、tool 丢失） | Medium | High | 写行为一致性测试：升级前后的 Agent 输出对比 |
| `AgentContext` 与 `api.context` 双状态系统混乱 | Low | Medium | Phase 1 明确隔离，Phase 后续整合 |
