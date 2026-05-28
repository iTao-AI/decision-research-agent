import logging
from pathlib import Path

try:
    import markdown
except ImportError:
    pass


def convert_md_to_pdf(md_abs_path: Path, pdf_abs_path: Path) -> str:
    """
    使用 markdown + weasyprint 将 Markdown 转换为 PDF（跨平台）。
    流程：MD → HTML (markdown) → PDF (weasyprint)
    weasyprint 在函数内延迟导入，避免系统依赖缺失时阻止整个 agent 启动。
    """
    # 延迟导入 weasyprint — 系统依赖 (cairo/pango/gobject) 可能缺失
    try:
        from weasyprint import HTML
    except OSError as e:
        return f"转换失败: weasyprint 系统依赖缺失 (cairo/pango)，请参考 https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation"

    temp_html_path = md_abs_path.with_suffix('.temp.html')

    try:
        # 1. MD → HTML
        with open(md_abs_path, 'r', encoding='utf-8') as f:
            md_content = f.read()

        html_body = markdown.markdown(md_content, extensions=['tables', 'fenced_code'])
        html_content = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", "SimHei", sans-serif;
                    line-height: 1.6;
                    margin: 2cm;
                }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #333; padding: 8px; }}
                pre {{
                    background-color: #f5f5f5;
                    padding: 10px;
                    border-radius: 4px;
                    white-space: pre-wrap;
                    word-wrap: break-word;
                }}
                code {{ font-family: "Menlo", "Consolas", "Monaco", monospace; }}
                h1 {{ font-size: 24pt; }}
                h2 {{ font-size: 20pt; }}
                h3 {{ font-size: 16pt; }}
            </style>
        </head>
        <body>
            {html_body}
        </body>
        </html>
        """

        with open(temp_html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        # 2. HTML → PDF via weasyprint
        HTML(filename=str(temp_html_path)).write_pdf(str(pdf_abs_path))

        if pdf_abs_path.exists():
            return f"成功转换: {pdf_abs_path} (跨平台引擎)"
        else:
            return f"转换完成但未生成文件: {pdf_abs_path}"

    except ImportError as e:
        missing = str(e).split()[-1].strip("'\"")
        return f"转换失败: 缺少依赖库 {missing}，请运行: pip install markdown weasyprint"
    except Exception as e:
        logging.error(f"PDF转换失败: {e}", exc_info=True)
        return f"转换失败: {str(e)}"

    finally:
        # 3. 清理临时文件
        if temp_html_path.exists():
            try:
                temp_html_path.unlink()
            except OSError:
                pass
