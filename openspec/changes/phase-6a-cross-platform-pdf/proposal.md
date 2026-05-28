## Why

当前 PDF 生成依赖 `pywin32` + Word COM 接口，仅在 Windows 平台可用。Mac 和 Linux 环境下该功能完全失效，且无法在 Docker 容器中运行。这使得 Agent 最核心的报告输出能力在非 Windows 平台上不可用。

## What Changes

- 将 PDF 生成引擎从 `pywin32` Word 替换为 **markdown + weasyprint** 跨平台方案
- 新增 `utils/pdf_converter.py` — 基于 markdown 库 + weasyprint 的 Markdown → PDF 转换器
- 重构 `tools/pdf_tools.py` — 使用新转换器，更新 docstring
- 重构 `utils/word_converter.py` — 替换内部实现，保持对外接口不变
- 引入 weasyprint 作为 HTML → PDF 引擎，确保中文渲染正确
- 更新 `requirements.txt` — 移除 `pywin32`，添加 `markdown` + `weasyprint`

## Capabilities

### New Capabilities
- `cross-platform-pdf`: 跨平台 PDF 生成能力 — 支持 Mac、Linux、Windows 三平台，中文渲染正确，Docker 友好

### Modified Capabilities
- `report-generation`（如有此 spec）: 报告生成流程不再依赖特定操作系统

## Impact

- **受影响文件**: `tools/pdf_tools.py`, `utils/word_converter.py`, `requirements.txt`
- **新增文件**: `utils/pdf_converter.py`
- **依赖变更**: 移除 `pywin32`（Windows 专用），添加 `markdown` + `weasyprint`（跨平台）
- **API 影响**: 无 — `convert_md_to_pdf` 工具对外接口保持不变
- **回归风险**: 低 — 工具签名不变，仅内部实现替换。weasyprint 需延迟导入以避免系统依赖缺失时阻止 agent 启动。

## Out of Scope

- Phase 6B（Docker 部署）— 本变更不创建 Dockerfile 或 docker-compose.yml
- PDF 样式美化 — 本次只做"能生成"，不做"好看"
- 批量 PDF 生成或并发优化
- Agent Prompt 层补强（Phase 7a）
