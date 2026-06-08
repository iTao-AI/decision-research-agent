# Deep Search Agent — 项目文档

## 文档索引

| 文档 | 说明 |
|------|------|
| [PRD](prd.md) | 产品需求文档 — 产品愿景、目标用户、核心功能、成功指标 |
| [Agent Integration](AGENT_INTEGRATION.md) | 上层 Agent / 自动化脚本调用 Deep Search Agent 的稳定工具客户端 |
| [Run Log](evidence/run-log.md) | E2E、ResearchRun 和 benchmark 证据记录 |
| [技术决策说明](evidence/technical-decisions.md) | 关键工程决策 — 记录为什么选择 A 而不是 B |

## Superpowers 规划文档

Superpowers 文档用于沉淀设计输入和实施计划，供后续 writing plan 或实现阶段读取。

| 文档 | 说明 |
|------|------|
| [Verification Evidence Design](superpowers/specs/2026-06-01-deep-search-agent-verification-evidence-design.md) | 验证收口设计 — 后端测试、前端构建、真实端到端运行证据和职业展示材料时机 |
| [Evidence Readiness Design](superpowers/specs/2026-06-01-deep-search-agent-evidence-readiness-design.md) | 证据化文档改造设计 — README 作品集化、Evidence Pack、技术决策说明和验证边界 |
| [Evidence Readiness Plan](superpowers/plans/2026-06-01-evidence-readiness.md) | 证据化文档改造实施计划 — README 重写、Evidence Pack 目录、验证 |
| [Phase 7b Tool Resilience Plan](superpowers/plans/2026-05-31-phase-7b-tool-resilience.md) | 工具韧性增强实施计划 — 超时、重试、降级和任务级超时 |

## Evidence Pack

运行证据、技术决策说明和基准数据。

| 文件 | 说明 |
|------|------|
| [Evidence Pack 索引](evidence/README.md) | 证据目录总览 |
| [Run Log](evidence/run-log.md) | 端到端运行记录模板 |
| [Technical Decisions](evidence/technical-decisions.md) | 关键技术决策与代码路径 |

## 技术参考文档

技术参考文档位于项目根目录 `spec/` 下，包含：

| 文档 | 说明 |
|------|------|
| [architecture.md](../spec/architecture.md) | 系统架构、模块职责、数据流 |
| [api-contract.md](../spec/api-contract.md) | REST + WebSocket API 端点定义 |
| [data-models.md](../spec/data-models.md) | 数据模型、Session Workspace、子 Agent 输入输出 |
| [tool-registry.md](../spec/tool-registry.md) | 工具接口定义清单 |
| [state-machine.md](../spec/state-machine.md) | LangGraph 图结构、节点定义、状态流转 |
| [external-services.md](../spec/external-services.md) | 外部依赖清单、SLA、超时/降级策略 |

## 与 openspec/ 的区别

- **`docs/`** — 产品意图和架构决策（为什么）
- **`spec/`** — 系统当前技术状态的快照（现在是什么）
- **`openspec/`** — 变更过程管理（这次改了什么），由 OpenSpec 工具自动管理
