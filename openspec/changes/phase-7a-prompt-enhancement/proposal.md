## Why

当前 Agent 执行流程无结构化阶段划分和门控检查。System prompt 是一段连续文本，Agent 可能跳过关键步骤（如未收集足够信息就生成报告），导致报告质量不稳定。报告生成也无标准大纲模板，每次生成结构可能不一致。

## What Changes

- **四阶段门控**：在 main agent system prompt 中加入明确的四阶段工作流（需求分析→信息收集→大纲确认→报告生成），每个阶段有准入条件、产出物和门控检查
- **报告大纲模板**：将标准报告大纲模板内嵌到 `prompts.yml` 的 `main_agent.system_prompt` 阶段 4 文本中，定义标准报告结构（摘要→背景→核心发现→结论建议→参考资料）
- **门控检查点**：关键约束（如"必须先收集信息再生成"）从软提示升级为硬门控，Agent 必须在每个阶段产出明确标记后才可进入下一阶段

## Capabilities

### New Capabilities

- `prompt-gating`: 四阶段门控机制，规范 Agent 执行流程和质量检查点
- `report-outline`: 标准化报告大纲模板，确保生成报告结构一致性

### Modified Capabilities

- `main-agent-prompt`: 修改 main agent system prompt，加入四阶段工作流和门控检查逻辑

## Impact

- **修改文件**: `prompt/prompts.yml`（main_agent system_prompt）
- **新增测试**: `tests/unit/test_prompt_config.py`（验证 prompt 结构正确性）
- **不影响**：Agent 代码逻辑、工具实现、API 端点、子 Agent
- **回归风险**：低 — 仅修改 prompt 文本，不改变代码逻辑
- **行为变化**：Agent 执行流程更结构化，报告生成质量更稳定
- **验证范围**：静态验证通过（prompt 结构测试）；端到端运行时验证需 API key 就绪后执行
