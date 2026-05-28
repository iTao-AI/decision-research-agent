## Context

当前 PDF 生成依赖 `pywin32` + Word COM 接口（`utils/word_converter.py`），仅 Windows 可用。流程为：MD → HTML → Word → PDF。`tools/pdf_tools.py` 调用 `convert_md_to_pdf_via_word()`。Mac/Linux 环境下此功能完全失效。

## Goals / Non-Goals

**Goals:**
- 替换为跨平台 PDF 引擎，Mac/Linux/Windows 三平台可用
- 中文渲染正确（无乱码）
- 保持 `convert_md_to_pdf` 工具对外接口不变
- Docker 友好（可在容器中运行）

**Non-Goals:**
- Docker 部署配置（Phase 6B 负责）
- PDF 样式美化
- 批量/并发 PDF 生成
- Agent Prompt 层改动

## Decisions

### Decision 1: markdown + weasyprint 方案

**选择**: markdown（MD → HTML，Python 库） + weasyprint（HTML → PDF）

**为什么**:
- markdown 是 Python 库，已有项目中已安装，无需额外系统依赖
- weasyprint 是纯 Python 库，无需安装系统级 TeX 发行版（xelatex 需要数 GB 的依赖）
- weasyprint 支持 CSS 控制字体，中文渲染只需在 CSS 中指定可用字体即可
- 无需安装 pandoc 二进制文件，减少外部依赖

**备选方案对比**:
- **pandoc + xelatex**: 需要安装 TeX Live 发行版（>3GB），Docker 镜像体积膨胀严重
- **pandoc + weasyprint**: 多一个 pandoc 二进制依赖，但 markdown 库已足够做 MD → HTML
- **pdfkit/wkhtmltopdf**: 依赖 wkhtmltopdf 二进制，已停止维护

### Decision 1.5: weasyprint 延迟导入

**选择**: weasyprint 在函数体内延迟导入，而非模块级 import

**为什么**: weasyprint 依赖 cairo/pango/gobject 系统库。如果模块级导入，系统缺失这些库时整个 agent 无法启动。延迟导入允许 agent 在其他功能正常运行的同时，PDF 功能优雅降级并返回友好错误信息。

### Decision 2: 保留中间 HTML 步骤

**选择**: MD → HTML → PDF，保留中间 HTML 转换步骤

**为什么**: 现有代码已经使用 `markdown` 库做 MD → HTML 转换，只需替换 HTML → PDF 部分，改动最小。

### Decision 3: 文件结构

- **新建** `utils/pdf_converter.py` — 核心转换逻辑（markdown + weasyprint）
- **重构** `utils/word_converter.py` — 内部调用改为 `convert_md_to_pdf`，对外函数签名不变
- **重构** `tools/pdf_tools.py` — 仅更新 docstring，无需改动核心逻辑

### Decision 4: 中文字体处理

**选择**: 在 HTML 模板的 CSS 中使用系统字体回退链：
```css
font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", "SimHei", sans-serif;
```

**为什么**: 各平台都有至少一种可用中文字体，不需要嵌入字体文件。Mac 用 PingFang SC，Windows 用 Microsoft YaHei，Linux 用 Noto Sans CJK SC。

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| pandoc 未安装在目标环境 | 工具返回明确错误信息，指导用户安装 |
| weasyprint 依赖 cairo/pango 系统库 | Linux 需 `apt install libcairo2 libpango-1.0-0`，需在 requirements.txt 或文档中注明 |
| PDF 渲染质量与 Word 方案有差异 | 本次只保证"能生成 + 中文可读"，样式优化后续处理 |
| 现有集成测试期望 Word 引擎输出 | 更新测试断言，验证文件生成而非具体引擎 |

## Migration Plan

1. 安装新依赖：`pip install pandoc weasyprint`，Linux 额外安装系统库
2. 部署新版本代码，PDF 工具自动使用新引擎
3. 移除 `pywin32` 依赖
4. **回滚**: 保留 `word_converter.py` 中的旧代码作为注释，紧急时可恢复

## Open Questions

- Linux 环境下中文字体（Noto Sans CJK SC）是否需要额外安装？需在 Docker 阶段确认。
- 是否需要支持代码语法高亮（pandoc 的 `--highlight-style`）？当前方案不包含，后续可加。
