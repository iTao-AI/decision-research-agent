from pathlib import Path

from utils.pdf_converter import convert_md_to_pdf


def convert_md_to_pdf_via_word(md_abs_path: Path, pdf_abs_path: Path) -> str:
    """
    将 Markdown 转换为 PDF。

    注意: 此函数已重构为调用跨平台 markdown + weasyprint 引擎。
    函数签名保持不变，原有调用方无需修改。
    原 pywin32/Word COM 实现已移除（仅 Windows 可用，不支持 Docker）。
    """
    return convert_md_to_pdf(md_abs_path, pdf_abs_path)
