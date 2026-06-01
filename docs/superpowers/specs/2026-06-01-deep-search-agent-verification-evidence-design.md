# Design: Deep Search Agent Verification Evidence

生成日期：2026-06-01
状态：Draft
用途：Superpowers writing plan 输入，供 Claude Code 执行验证收口和 Evidence Run

## Summary

本设计定义 Deep Search Agent 下一轮优化范围：把已经完成的 evidence-readiness 文档继续推进到可验证闭环。

当前项目已经具备作品集入口、Evidence Pack、技术决策说明和 Docker QA 截图。下一步不应继续扩功能，而应优先消除验证红灯、补真实端到端运行记录，并把所有公开指标绑定到实际命令、日志、截图或生成产物。

本轮输出面向后续 `superpowers:writing-plans`。计划生成后可交给 Claude Code 执行，再由 Claude Code + Gstack 和 Codex + Gstack 分别验收。

## Goals

- 让项目验证状态从“文档已说明边界”推进到“命令和证据可闭环”。
- 修复或合理隔离当前测试失败，让后端测试结果可解释、可复现。
- 验证前端生产构建，更新本机真实结果。
- 用 1-3 个真实任务样例补充 Evidence Pack 的 Run Log。
- 为后续职业展示材料提供可信素材，但不在本轮写最终简历或对外讲述稿。

## Current Facts

以下事实来自 2026-06-01 的本机检查。

- 初始检查时当前分支为 `main`，且与 `origin/main` 同步；本 spec 落盘后会产生文档 diff，后续执行必须以运行时 `git status --short --branch` 为准。
- 最近合并的 PR 为 `#12 docs/evidence-readiness`，已完成 README 作品集化、Evidence Pack 和技术决策文档。
- `python -m pytest -q` 当前结果为 `235 passed, 12 failed in 37.41s`。
- 12 个后端失败集中在两类：
  - `tests/unit/test_pdf_converter.py` 中 4 个 WeasyPrint 相关测试失败，本机缺 `cairo/pango/gobject` 等系统依赖。
  - `tests/unit/test_retry_utils.py` 中 8 个 retry monitor mock 断言失败；stdout 可见 retry 事件，但 mock 未观察到 `report_retry` 调用。
- `cd frontend && npm run build` 当前失败，错误为 `vue-tsc: command not found`。
- `frontend/node_modules` 当前不存在，但 `frontend/package.json` 的 `devDependencies` 已声明 `vue-tsc`。
- `docs/evidence/run-log.md` 当前仍是计划测量项，没有真实端到端任务样例、耗时、token、子 Agent 调用次数或 WebSocket 事件样例。
- `docs/evidence/assets/` 已包含三张 Docker QA 截图和 `qa-report-summary.md`。

在上述证据缺口关闭前，公开文档不得声称测试全绿、前端构建通过、已有 P95 性能数据或已有 token/cost benchmark。

## Recommended Direction

采用 verification-first 方案：先修验证链路，再补运行证据，最后只做必要的公开文档同步。

理由：

- 当前最影响工程可信度的不是功能缺失，而是测试和构建仍有红灯。
- Evidence Pack 已经建立目录结构，但缺少真实 run log。补真实样例比继续润色 README 更有价值。
- 对求职展示来说，能解释并修复验证缺口，比继续堆新 Agent 更能证明工程能力。

## Execution Scope

### 1. Backend Verification Closure

后续 implementation plan 应先处理后端测试。

允许方向：

- 对 retry monitor mock 失败做根因定位，确认是测试 patch 路径错误、monitor 导入时机问题，还是实现确实没有调用可 mock 的 `report_retry`。
- 如果是测试问题，修正测试以断言真实行为。
- 如果是实现问题，做最小业务代码修复，并补充测试说明。
- 对 WeasyPrint 依赖问题做环境边界处理：优先让测试在依赖存在时真实跑通；依赖缺失时使用明确 skip 或隔离策略，不能伪造成功。

验收目标：

- `python -m pytest -q` 在当前本机环境得到明确可解释结果。
- 最理想结果是全绿。
- 如果保留 skip，skip 原因必须写明本机系统依赖缺失，并且不能掩盖真实代码失败。

### 2. Frontend Build Verification

后续 implementation plan 应验证前端构建。

允许方向：

- 在 `frontend/` 下执行 `npm install` 或 `npm ci`，以项目 lockfile 为准。
- 执行 `npm run build`，记录真实输出。
- 如果构建失败，定位 TypeScript/Vite/Vue 配置或代码问题，并做最小修复。
- 如果构建通过，更新 Evidence Pack 和 README 中的前端构建状态。

验收目标：

- `cd frontend && npm run build` 有真实命令输出。
- 公开文档中的前端构建状态与命令结果一致。

### 3. Evidence Run Log

后续 implementation plan 应补充 `docs/evidence/run-log.md`。

最小要求：

- 优先记录 1 个真实端到端任务。
- 如果外部 API key、MySQL 或 RAGFlow 不可用，应记录实际阻塞原因，并降级为 `E2E blocked with partial evidence`：使用项目已有 Docker QA、mock 环境或局部可运行链路补证据，但不得声称端到端任务已完成。
- 不得把演示示例写成 benchmark。

真实端到端任务完成时，每条记录应包含：

- 运行日期和环境。
- 输入问题。
- 启动命令或 API 调用。
- 总耗时。
- 子 Agent 调用次数或可观测派发事件。
- WebSocket 事件样例。
- token 用量；如果无法采集，写明原因和待补命令。
- 生成产物路径，例如 Markdown/PDF 报告。
- 失败、跳过或降级说明。

如果只能完成 partial evidence，记录应包含：

- 阻塞的外部依赖或配置项。
- 已完成的局部链路，例如 Docker QA、API smoke test、mock-agent run 或 WebSocket 局部事件。
- 明确标注哪些指标不能声称已完成，例如真实 token 用量、真实外部搜索结果或完整报告产物。

### 4. Public Documentation Sync

后续 implementation plan 只在证据变化后同步公开文档。

允许修改：

- `README.md`
- `README_CN.md`
- `docs/README.md`
- `docs/evidence/README.md`
- `docs/evidence/run-log.md`
- `docs/evidence/assets/`
- `frontend/package.json`
- `frontend/package-lock.json`
- 与测试或构建修复直接相关的代码/测试/配置文件

禁止修改：

- `frontend/node_modules/`
- `docs/prd.md`
- 无关 OpenSpec archive
- 与本轮验证无关的 Agent 功能、Prompt 策略或产品范围
- 私有求职材料目录，除非单独拆出后续任务

## Career Material Timing

职业展示材料分两阶段处理。

### 现在可以写

现在可以在个人 Career 目录中准备非最终版素材骨架，但不建议作为本轮 repo 任务的一部分。

适合现在整理的内容：

- 项目事实清单。
- 架构亮点清单。
- 可被追问的技术决策。
- 当前验证缺口和修复计划。
- 面试追问清单。

### 验证完成后再写

最终职业展示材料应等本轮验证收口后再写。

适合后写的内容：

- 简历 bullet。
- 项目作品集页面。
- 面试 1 分钟 / 3 分钟讲述稿。
- STAR 案例。
- 对外可分享的技术文章。

原因：

- 当前测试和前端构建仍未闭环，最终材料过早定稿会被迫写得保守。
- 如果提前写强结论，后续真实命令结果可能不匹配，影响可信度。
- 等 run log 有真实耗时、token、事件和产物后，求职材料可以更具体。

## Out of Scope

本轮不做以下事项：

- 不新增子 Agent。
- 不迁移 MCP。
- 不做云部署大改。
- 不新增模型供应商抽象。
- 不实现认证、权限、持久化任务状态或 eval harness；这些可作为后续 roadmap。
- 不编写无证据支撑的 P95、平均耗时、token/cost、缓存命中率或成功率。
- 不把私有职业动机或不适合公开仓库的包装性表达写入公开文档。
- 不把 OpenSpec 作为本轮默认工作流入口。

## Writing Plan Input Requirements

后续 `superpowers:writing-plans` 应基于本文生成一个可执行计划。

计划必须包含：

- Source Spec：本文档路径。
- Allowed Files：明确列出允许修改的文件和目录。
- Forbidden Files：明确列出 `docs/prd.md`、无关 OpenSpec archive、无关功能模块。
- Implementation Tasks：按“后端测试 -> 前端构建 -> Evidence Run -> 文档同步 -> 验证”排序。
- Verification Commands：包含实际要运行的后端测试、前端构建、Markdown 扫描和 git diff 检查。
- Evidence Required：每个指标必须绑定命令输出、日志、截图或文件路径。
- Handoff Notes：说明哪些事项留给 Codex + Gstack 最终验收。

计划不得把“职业展示材料最终撰写”混入本轮实施。若需要写相关材料，应在验证完成后单独创建 spec 或 plan。

## Acceptance Criteria

- `python -m pytest -q` 状态被收口为全绿，或剩余 skip/失败具有明确、诚实、可复现的环境说明。
- `cd frontend && npm run build` 有真实结果，并同步到公开文档。
- `docs/evidence/run-log.md` 包含 `E2E completed` 真实任务记录，或在外部依赖不可用时包含 `E2E blocked with partial evidence` 记录；两者都不得使用示例伪数据。
- README / Evidence Pack 中所有指标均来自实际命令、日志、截图或产物。
- 新文档和更新文档不包含未完成占位符、未解释任务标记、无证据指标或不适合公开仓库的包装性表达。
- `git diff` 只包含本轮验证收口和证据整理相关改动。

## Review Plan

后续验收应执行：

```bash
python -m pytest -q
cd frontend && npm run build
PUBLIC_SAFETY_PATTERNS='T''BD|TO''DO|求职''包装|面试''话术|洗''稿|虚''构'
rg -n "$PUBLIC_SAFETY_PATTERNS" README.md README_CN.md docs/README.md docs/evidence docs/superpowers/specs \
  --glob '!docs/superpowers/plans/**'
git status --short --branch
git diff --stat
```

如果端到端任务依赖外部 API key 或私有服务，应额外记录：

- 哪些服务可用。
- 哪些服务不可用。
- 采用了真实调用、Docker QA、mock 环境还是局部链路验证。
- 哪些指标因此不能声称已完成。
