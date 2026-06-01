# Design: Deep Search Agent Evidence Readiness

生成日期：2026-06-01
状态：Draft
用途：Superpowers writing plan 输入

## Summary

本设计定义 Deep Search Agent 下一轮文档证据化改造方向：把现有项目文档从“功能说明”升级为“证据优先”的工程作品入口。

本次目标不是新增产品范围，也不是修改运行时代码，而是让现有工程能力更容易被验证：架构决策、运行证据、验证状态、部署证明和已知边界都应能通过文件、命令、日志或截图追溯。

## Goals

- 提升公开项目文档的证据密度。
- 支撑 AI Agent、LLM 应用、AI 提效工程方向的项目展示。
- 将 README 从功能清单改造成作品集入口，突出真实执行链路。
- 建立 Evidence Pack 结构，用于后续沉淀 benchmark 日志、截图、WebSocket 事件、生成报告、token 用量和部署记录。
- 所有数字指标都必须来自实际命令、日志、截图或测试输出。

## Current Facts

以下事实来自 2026-06-01 的本地检查和验证。

- 后端测试命令 `python -m pytest -q` 完成，结果为 `235 passed / 12 failed`。
- 12 个后端失败集中在两类问题：
  - WeasyPrint 本机系统依赖导致 PDF 转换相关测试失败。
  - retry monitor 测试中的 mock 断言未观察到 `report_retry`，但 stdout 中可见 retry 事件输出。
- 前端构建命令 `npm run build` 未完成，原因是本地环境未找到 `vue-tsc`。
- 已有 Docker QA 报告位于 `.gstack/qa-reports/qa-report-localhost-2026-05-30.md`。
- 已有 Docker QA 截图位于 `.gstack/qa-reports/screenshots/`。
- 当前工作区存在无关 OpenSpec archive 删除，路径为 `openspec/changes/phase-7c-observability-enhancement/`。
- 当前工作区存在无关未跟踪计划文件：`docs/superpowers/plans/2026-05-30-phase-7a-prompt-enhancement.md`。

在上述失败被修复或明确标注为环境边界前，公开文档不得声称项目已完全验证通过。

## Documentation Direction

### README as Portfolio Entry

README 第一屏应回答四个问题：

- 这个项目自动化了什么真实工作流？
- 项目采用了什么架构？
- 有哪些证据能证明它能运行？
- 哪些工程设计让它不只是单提示词 demo？

README 应优先呈现：

- 一句话产品定位。
- 架构图或现有架构说明入口。
- 端到端任务链路：用户问题 -> main agent -> sub-agents -> tools -> generated report -> WebSocket status stream。
- 运行证据表，只填写已实测数据。
- 部署和验证状态，附实际命令。
- Evidence Pack 和相关 spec 的链接。

### Evidence Pack

新增公开安全的证据区或证据目录，用于持续沉淀：

- 端到端运行记录。
- 平均耗时和 P95 耗时，完成实测后再写入。
- token 用量和估算成本，完成实测后再写入。
- 单次任务的子 Agent 调用次数。
- WebSocket 事件样例。
- 生成的 Markdown/PDF 报告样例。
- Docker Compose 部署截图或日志。
- 已知限制和失败检查记录。

未实测字段不得出现在公开文档的空表格中，也不得以推测数字占位。需要保留的后续测量项应放在后续 writing plan 或私有执行记录中。

### Technical Decision Defense

后续文档应补充简洁的技术决策说明，并尽量附代码路径：

- 为什么 `LangGraph + DeepAgents` 适合 planner + delegated sub-agent 模型。
- 为什么使用 `ContextVar` 做异步会话隔离。
- 为什么使用 WebSocket 展示实时状态，而不是只用轮询。
- 为什么 Prompt 放在 YAML，而不是硬编码在 Python 中。
- retry、timeout、cache、token tracking、telemetry 如何提升可运维性。
- upload/download 路径如何被约束，降低文件越权访问风险。

### Out of Scope

本轮文档改造不得扩展到无关功能：

- 不新增子 Agent。
- 不迁移 MCP。
- 不进行大规模云部署重设计。
- 不新增模型供应商抽象。
- 不编造 benchmark 数字。
- 不声称未实际通过的测试或构建已经通过。

## Writing Plan Input Requirements

后续 `superpowers:writing-plans` 应只规划文档和证据整理工作。若需要修复测试或构建问题，应拆成独立计划，避免把业务代码修改混入本轮文档改造。

实施计划必须遵守：

- 不修改业务逻辑。
- 不修改 `docs/prd.md`。
- 保留无关工作区改动，不回滚、不覆盖。
- 所有数字结论必须来自实际命令输出或证据文件。
- 公开文档只写项目事实、工程设计和验证边界。
- 验证步骤必须包含 Markdown 链接检查和占位符扫描。

## Acceptance Criteria

- 后续 writing plan 可以直接基于本文档生成 README 和 Evidence Pack 的实施计划，不需要再次决定范围。
- 公开文档能清楚区分已实测事实和后续测量工作。
- 当前验证失败被诚实呈现，不被掩盖成全量通过。
- 文档策略让项目更容易通过文件、截图、日志和命令输出被审查。
- 公开文档不包含私有流程表述或无证据支撑的成果宣称。
