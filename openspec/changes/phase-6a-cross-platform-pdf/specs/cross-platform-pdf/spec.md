## ADDED Requirements

### Requirement: 跨平台 Markdown 转 PDF
系统 SHALL 使用 markdown + weasyprint 作为 PDF 生成引擎，替代原有的 pywin32 Word COM 方案。转换必须在 Mac、Linux、Windows 三平台均可用。

#### Scenario: 正常转换流程
- **WHEN** Agent 调用 `convert_md_to_pdf` 工具并提供有效 Markdown 文件路径
- **THEN** 系统在 session 工作目录下生成同名 PDF 文件，返回成功路径

#### Scenario: 中文字符正确渲染
- **WHEN** Markdown 文件包含中文字符（如简体中文报告内容）
- **THEN** 生成的 PDF 文件中中文内容无乱码，字体可读

#### Scenario: 输入文件不存在
- **WHEN** 提供的 Markdown 文件路径不存在
- **THEN** 工具返回错误字符串 "错误：文件不存在 {路径}"，不抛出异常

#### Scenario: weasyprint 系统依赖缺失
- **WHEN** 系统环境中未安装 cairo/pango/gobject 系统库（weasyprint 的 C 依赖）
- **THEN** 工具返回错误字符串，包含 "weasyprint 系统依赖缺失" 指引，不抛出异常

### Requirement: 统一 PDF 转换接口
`convert_md_to_pdf` 工具的对外签名、输入输出格式 SHALL 保持不变，确保现有 Agent 和前端无需修改。

#### Scenario: 指定输出文件名
- **WHEN** 调用工具时提供 `pdf_filename` 参数
- **THEN** PDF 输出到指定路径（自动追加 .pdf 后缀）

#### Scenario: 默认输出文件名
- **WHEN** 调用工具时不提供 `pdf_filename` 参数
- **THEN** PDF 输出到 Markdown 文件同目录下同名 .pdf 文件
