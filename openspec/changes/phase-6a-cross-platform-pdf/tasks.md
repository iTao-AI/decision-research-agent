## 1. 依赖安装

- [ ] 1.1 在 `requirements.txt` 中添加 `pandoc` 和 `weasyprint`，移除 `pywin32`
- [ ] 1.2 本地执行 `pip install pandoc weasyprint`，验证安装成功

## 2. 新增跨平台 PDF 转换器

- [ ] 2.1 创建 `utils/pdf_converter.py` — 实现 `convert_md_to_pdf_pandoc(md_path, pdf_path)` 函数
  - 使用 `markdown` 库将 MD → HTML
  - 使用 `weasyprint` 将 HTML → PDF
  - CSS 中包含中文字体回退链
  - 错误处理返回错误字符串，不抛异常
- [ ] 2.2 处理 pandoc 缺失场景 — 检测 pandoc 是否可用，返回友好错误信息
- [ ] 2.3 处理 weasyprint 系统依赖缺失场景 — 检测 cairo/pango 是否可用

## 3. 重构现有文件

- [ ] 3.1 重构 `utils/word_converter.py` — 内部调用改为 `convert_md_to_pdf_pandoc`，保持 `convert_md_to_pdf_via_word` 函数签名不变
- [ ] 3.2 验证 `tools/pdf_tools.py` 无需改动（仅 import 路径不变）
- [ ] 3.3 检查是否有其他文件直接引用 `pywin32` 或 `win32com`

## 4. 中文字体验证

- [ ] 4.1 创建包含中文的测试 Markdown 文件
- [ ] 4.2 在 Mac 环境下测试 PDF 生成，验证中文无乱码
- [ ] 4.3 确认 CSS 字体回退链覆盖 Mac/Linux/Windows 三平台

## 5. 测试验证

- [ ] 5.1 运行已有 PDF 相关集成测试，确认通过
- [ ] 5.2 新增单元测试：验证 `convert_md_to_pdf_pandoc` 正常路径
- [ ] 5.3 新增单元测试：验证 pandoc 缺失时的错误处理
- [ ] 5.4 新增单元测试：验证输入文件不存在时的错误处理
- [ ] 5.5 运行全部测试 `pytest tests/`，确认无回归
