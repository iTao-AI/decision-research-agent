import logging
from pathlib import Path
try:
    from typing import Annotated, Optional
except ImportError:
    from typing_extensions import Annotated, Optional

from langchain_core.tools import tool
from api.monitor import monitor
from api.context import get_session_context
from utils.path_utils import resolve_path
from utils.word_converter import convert_md_to_pdf_via_word


@tool
def convert_md_to_pdf(
        md_filename: Annotated[str, "Markdown document path (with .md extension)"],
        pdf_filename: Annotated[Optional[str], "Output PDF path (optional, defaults to same name)"] = None
) -> str:
    """Convert a Markdown document to PDF (cross-platform via markdown + weasyprint)."""
    monitor.report_tool("Markdown转PDF工具")

    try:
        session_dir = get_session_context()
        md_path = Path(md_filename).with_suffix('.md')
        md_abs_path = Path(resolve_path(str(md_path), session_dir))

        if not md_abs_path.exists():
            monitor.report_end("Markdown转PDF工具", error=f"文件不存在 {md_abs_path}")
            return f"错误：文件不存在 {md_abs_path}"

        if pdf_filename:
            pdf_path = Path(pdf_filename).with_suffix('.pdf')
            pdf_abs_path = Path(resolve_path(str(pdf_path), session_dir))
        else:
            pdf_abs_path = md_abs_path.with_suffix('.pdf')

        result = convert_md_to_pdf_via_word(md_abs_path, pdf_abs_path)
        monitor.report_end("Markdown转PDF工具", result)
        return result

    except Exception as e:
        logging.error(f"转换失败: {e}", exc_info=True)
        monitor.report_end("Markdown转PDF工具", error=str(e))
        return f"转换失败: {str(e)}"
