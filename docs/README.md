# Decision Research Agent — 项目文档

当前仓库、运行时配置、Tool Client 和 health service ID 使用
`decision-research-agent` 技术标识，详见 [Agent Integration](AGENT_INTEGRATION.md)。

当前产品契约：

- LangChain = Agent Framework
- DeepAgents = research harness
- LangGraph = durable workflow runtime
- LangSmith = privacy-first tracing/evaluation
- Application DB = business authority
- v0.1.0 是 backend-and-CLI release，React deferred。
- Markdown-only delivery：交付结果通过 canonical result endpoint 返回 Markdown artifact。

## 文档索引

| 文档 | 说明 |
|------|------|
| [PRD](prd.md) | 产品需求文档 — 产品愿景、目标用户、核心功能、成功指标 |
| [v0.1.0 Release Notes](releases/v0.1.0.md) | 首个 backend-and-CLI release 的 breaking changes、migration、rollback 与 gate 边界 |
| [Agent Integration](AGENT_INTEGRATION.md) | 上层 Agent / 自动化脚本调用 Decision Research Agent 的稳定工具客户端 |
| [LangSmith 可观测性](observability.md) | 隐私优先 Trace 配置、CLI 验证和完整 Trace 切换门槛 |
| [Durable HITL 运维说明](operations/durable-hitl-feasibility.md) | 实验性 P1B 启用边界、决策语义、恢复边界和 13 项 gate 命令 |
| [Evidence Verification 运维说明](operations/evidence-verification-workflow.md) | P2A 启用、CLI、revisioned publication、恢复和 rollback 边界 |
| [Real-Source Proof 运维说明](operations/real-source-proof-workflow.md) | P2A PR3 小样本 manifest、人工核验、publication、fresh review 与报告流程 |
| [Run Log](evidence/run-log.md) | E2E、ResearchRun 和 benchmark 证据记录 |
| [技术决策说明](evidence/technical-decisions.md) | 关键工程决策 — 记录为什么选择 A 而不是 B |
| [Evidence Verification Authority](decisions/evidence-verification-authority.md) | P2A 的不可变 Evidence、追加式 human decision、revisioned publication 与 review 权威边界 |

## Superpowers 规划文档

Superpowers 文档用于沉淀设计输入和实施计划，供后续 writing plan 或实现阶段读取。

| 文档 | 说明 |
|------|------|
| [P2A Evidence Verification Design](superpowers/specs/2026-06-21-p2a-evidence-verification-design.md) | 追加式人工核验账本、确定性预检、版本化 DecisionBrief / ReviewBundle 与真实来源产品证据 |
| [P2A Verification Authority Plan](superpowers/plans/2026-06-22-p2a-verification-authority.md) | PR1 的不可变 baseline origin、确定性 preflight、追加式 decision ledger 与 snapshot 实施步骤 |
| [P2A Controlled Publication Design](superpowers/specs/2026-06-23-p2a-controlled-publication-design.md) | PR2 的 revisioned publication、fresh review、current delivery 与受控 API/CLI 边界 |
| [P2A Controlled Publication Plan](superpowers/plans/2026-06-23-p2a-controlled-publication.md) | PR2 的 schema migration、artifact rebuild、freshness state machine、API/CLI 与验证步骤 |
| [P2A Real-Source Proof Design](superpowers/specs/2026-06-23-p2a-real-source-proof-design.md) | PR3 的真实公开来源样本、人工核验、确定性重建与受控交付证明边界 |
| [P2A Real-Source Proof Plan](superpowers/plans/2026-06-23-p2a-real-source-proof.md) | PR3 的固定 manifest、deterministic seed、人工核验、proof report 与验证步骤 |
| [Technical Identifier Migration Design](superpowers/specs/2026-06-18-technical-identifier-migration-design.md) | 仓库改名后的 runtime env、health、Tool Client、LangSmith 与历史兼容边界 |
| [Technical Identifier Migration Plan](superpowers/plans/2026-06-18-technical-identifier-migration.md) | canonical-first 标识迁移、回滚和验证步骤 |
| [Evidence Readiness Plan](superpowers/plans/2026-06-01-evidence-readiness.md) | 证据化文档改造实施计划 — README 重写、Evidence Pack 目录、验证 |
| [Phase 7b Tool Resilience Plan](superpowers/plans/2026-05-31-phase-7b-tool-resilience.md) | 工具韧性增强实施计划 — 超时、重试、降级和任务级超时 |

## Evidence Pack

运行证据、技术决策说明和基准数据。

| 文件 | 说明 |
|------|------|
| [Evidence Pack 索引](evidence/README.md) | 证据目录总览 |
| [Run Log](evidence/run-log.md) | 端到端运行记录模板 |
| [Technical Decisions](evidence/technical-decisions.md) | 关键技术决策与代码路径 |
| [Durable HITL Gate Report](evidence/durable-hitl-gate-report.json) | P1B feasibility 的 13 项持久化、安全与 crash gate 结果 |
| [P2A Real-Source Proof JSON](evidence/p2a-real-source-proof.json) | 小样本真实来源 proof 的有界机器可读报告 |
| [P2A Real-Source Proof](evidence/p2a-real-source-proof.md) | 人工核验与 fresh review 执行结果、来源边界和限制 |

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
