import pytest
from pathlib import Path
from unittest.mock import patch

from tests.conftest import weasyprint_available

from utils.pdf_converter import convert_md_to_pdf

WEASYPRINT_SKIP_REASON = "WeasyPrint system dependencies (cairo/pango/gobject) not available"


@pytest.fixture
def test_md_file(tmp_path):
    """创建包含中文内容的测试 Markdown 文件"""
    md = tmp_path / "test_report.md"
    md.write_text("# 测试报告\n\n这是一个包含中文的测试文档。\n\n## 功能测试\n\n| 项目 | 状态 |\n|------|------|\n| PDF生成 | 正常 |\n", encoding='utf-8')
    return md


@pytest.fixture
def output_pdf_path(tmp_path):
    return tmp_path / "test_output.pdf"


class TestConvertMdToPdf:
    """测试跨平台 PDF 转换器"""

    @pytest.mark.skipif(not weasyprint_available(), reason=WEASYPRINT_SKIP_REASON)
    def test_normal_conversion(self, test_md_file, output_pdf_path):
        """正常路径：MD 成功转换为 PDF"""
        result = convert_md_to_pdf(test_md_file, output_pdf_path)
        assert "成功转换" in result
        assert output_pdf_path.exists()
        assert output_pdf_path.stat().st_size > 0

    @pytest.mark.skipif(not weasyprint_available(), reason=WEASYPRINT_SKIP_REASON)
    def test_temp_html_cleaned_up(self, test_md_file, output_pdf_path):
        """临时 HTML 文件在转换后被清理"""
        temp_html = test_md_file.with_suffix('.temp.html')
        convert_md_to_pdf(test_md_file, output_pdf_path)
        assert not temp_html.exists()

    @pytest.mark.skipif(not weasyprint_available(), reason=WEASYPRINT_SKIP_REASON)
    def test_pdf_uses_same_directory(self, test_md_file):
        """输出 PDF 路径与 MD 同名同目录"""
        expected_pdf = test_md_file.with_suffix('.pdf')
        result = convert_md_to_pdf(test_md_file, expected_pdf)
        assert "成功转换" in result
        assert expected_pdf.exists()
        expected_pdf.unlink()

    def test_missing_input_file(self, tmp_path):
        """输入文件不存在时返回错误字符串"""
        missing_file = tmp_path / "nonexistent.md"
        output = tmp_path / "output.pdf"
        result = convert_md_to_pdf(missing_file, output)
        assert "错误" in result or "失败" in result
        assert not output.exists()

    def test_weasyprint_system_dep_missing(self, test_md_file, output_pdf_path):
        """weasyprint 系统依赖缺失时返回友好错误"""
        import builtins
        import sys

        real_import = builtins.__import__
        cached = sys.modules.pop("weasyprint", None)  # force fresh import attempt

        def fake_import(name, *args, **kwargs):
            if name == "weasyprint":
                raise OSError("cannot load library libcairo")
            return real_import(name, *args, **kwargs)

        try:
            with patch("builtins.__import__", side_effect=fake_import):
                result = convert_md_to_pdf(test_md_file, output_pdf_path)
                assert "转换失败" in result
                assert "cairo" in result.lower() or "pango" in result.lower() or "系统依赖" in result
        finally:
            if cached is not None:
                sys.modules["weasyprint"] = cached  # restore

    @pytest.mark.skipif(not weasyprint_available(), reason=WEASYPRINT_SKIP_REASON)
    def test_markdown_not_installed_error(self, test_md_file, output_pdf_path, monkeypatch):
        """markdown 库未安装时返回友好错误"""
        import utils.pdf_converter as converter_mod
        monkeypatch.setattr(converter_mod, 'markdown', None)
        result = convert_md_to_pdf(test_md_file, output_pdf_path)
        assert "转换失败" in result or "缺少依赖" in result

    @pytest.mark.skipif(not weasyprint_available(), reason=WEASYPRINT_SKIP_REASON)
    def test_chinese_content_rendering(self, tmp_path):
        """中文内容正确渲染，无乱码"""
        md = tmp_path / "chinese.md"
        md.write_text("# 中文标题\n\n这是一段中文内容。", encoding='utf-8')
        pdf = tmp_path / "chinese.pdf"
        result = convert_md_to_pdf(md, pdf)
        assert "成功转换" in result
        assert pdf.exists()
        assert pdf.stat().st_size > 1000
