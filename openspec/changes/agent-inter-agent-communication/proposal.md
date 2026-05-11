# Proposal: Agent 间通信 — SharedContext 共享事实层

**Change ID:** `agent-inter-agent-communication`
**Created:** 2026-05-11
**Status:** Draft

---

## Problem Statement

子 Agent 之间没有信息共享机制。主 Agent 拿到所有子 Agent 的结果后手动拼接，导致：
- 子 Agent 无法利用其他 Agent 已发现的中间结论
- 主 Agent 需要重复汇总信息，token 消耗增加
- 搜索结果之间无法产生关联推理（如网络搜索发现某公司，数据库 Agent 无法直接查询该公司相关记录）

## Proposed Solution

在 LangGraph StateGraph 之上加一层薄语义封装 `SharedContext`，让子 Agent 可以：
- **发布事实**：将关键发现（实体、数值、关系）发布到共享 state
- **查询事实**：按主题查询其他 Agent 已发布的事实

**技术决策**：
- 不实现独立的 pub/sub 总线，而是使用 in-memory SharedContext + ContextVar session 隔离
- ContextVar 隔离模式与 Phase 1 的 `api/context.py` 保持一致（每个 thread_id 独立实例）
- 子 Agent 通过 tool 调用 publish/query，不直接 import SharedContext
- 每 session 事实上限 100 条，超出时 oldest-first 淘汰

## Scope

### In Scope
- 新增 `agent/shared_context.py` — 基于 LangGraph state 的事实发布/查询封装
- 改造 `agent/main_agent.py` — StateGraph 中加入 `shared_facts` 字段
- 改造子 Agent 调用 shared_context 发布/查询事实
- 编写单元测试覆盖 publish/query 路径

### Out of Scope
- 实现独立的 pub/sub 消息队列
- WebSocket 实时推送（属于 Phase 4 可观测性）
- 事实的版本控制或冲突解决

## Impact Analysis

| Component | Change Required | Details |
|-----------|-----------------|---------|
| Agent 架构 | Yes | StateGraph 新增 shared_facts 字段 |
| 子 Agent | Yes | 可选接入 publish/query 能力 |
| 主 Agent | Yes | 增加 shared_facts 初始化和消费 |
| 测试 | Yes | 新增 shared_context 单元测试 |

## Success Criteria

- [x] SharedContext 支持发布、查询、清理事实，数据按 thread_id 隔离
- [x] 容量上限 100 条/session，超出时自动淘汰最早的事实
- [x] main_agent.py 的 StateGraph 包含 shared_facts 字段
- [x] 至少一个子 Agent（如 network_search_agent）接入事实发布
- [x] 所有新增代码有对应测试覆盖

**Status:** Implementation Complete
**Completed:** 2026-05-11

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| ContextVar 隔离失效 | Low | High | 每 thread_id 独立实例，不依赖全局单例 |
| 子 Agent 发布事实增加 token 消耗 | Low | Medium | 事实数据仅存结构化摘要，不存原文 |
| 事实无限制增长导致内存泄漏 | Low | Medium | 容量上限 100 条 + session 结束清理 |
