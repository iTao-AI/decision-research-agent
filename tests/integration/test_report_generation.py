"""Integration tests for report generation.

Verifies that Markdown reports are generated into the correct session directory
and that concurrent sessions do not cross-contaminate.
"""
import pytest

from api.context import set_session_context, reset_session_context
from tools.markdown_tools import generate_markdown


@pytest.fixture
def session_dir_v2():
    """Create a temporary session directory for report generation tests."""
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="test_report_session_")
    token = set_session_context(tmpdir)
    try:
        yield tmpdir
    finally:
        reset_session_context(token)
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


class TestReportGeneration:
    """Markdown report generation tests."""

    def test_generate_markdown_file_created_in_session_dir(self, session_dir_v2):
        """generate_markdown creates .md file in the session directory."""
        content = "# Test Report\n\nThis is a test report."
        result = generate_markdown.invoke({"content": content, "filename": "test_report.md"})

        from pathlib import Path
        expected_path = Path(session_dir_v2) / "test_report.md"

        assert expected_path.exists(), f"Expected {expected_path} to exist"
        assert expected_path.read_text(encoding="utf-8") == content
        assert "已成功生成" in result

    def test_generate_markdown_with_subdirectory(self, session_dir_v2):
        """generate_markdown creates subdirectories if they don't exist."""
        content = "# Nested Report"
        result = generate_markdown.invoke({"content": content, "filename": "nested_report.md", "path": "reports/2026"})

        from pathlib import Path
        expected_path = Path(session_dir_v2) / "reports" / "2026" / "nested_report.md"

        assert expected_path.exists(), f"Expected {expected_path} to exist"
        assert expected_path.read_text(encoding="utf-8") == content

    def test_generate_markdown_content_matches_input(self, session_dir_v2):
        """Generated file content exactly matches input content."""
        content = """# 测试报告

## 摘要
这是一个测试报告。

## 详细信息
- 项目: deep-search-agent
- 日期: 2026-05-18
"""
        generate_markdown.invoke({"content": content, "filename": "detailed_report.md"})

        from pathlib import Path
        actual = (Path(session_dir_v2) / "detailed_report.md").read_text(encoding="utf-8")
        assert actual == content

    def test_generate_markdown_auto_adds_extension(self, session_dir_v2):
        """generate_markdown adds .md extension if missing."""
        content = "# No Extension"
        generate_markdown.invoke({"content": content, "filename": "no_extension"})

        from pathlib import Path
        expected_path = Path(session_dir_v2) / "no_extension.md"
        assert expected_path.exists()


class TestReportPathIsolation:
    """Verify reports from different sessions don't cross-contaminate."""

    def test_two_sessions_generate_independent_reports(self):
        """Two session directories produce isolated reports when used sequentially."""
        import tempfile
        import shutil

        dir_a = tempfile.mkdtemp(prefix="test_isolation_a_")
        dir_b = tempfile.mkdtemp(prefix="test_isolation_b_")

        try:
            # Generate report in session A
            set_session_context(dir_a)
            content_a = "# Report A\n\nSession A content."
            generate_markdown.invoke({"content": content_a, "filename": "report.md"})
            set_session_context("")  # clear to default

            # Generate report in session B
            set_session_context(dir_b)
            content_b = "# Report B\n\nSession B content."
            generate_markdown.invoke({"content": content_b, "filename": "report.md"})
            set_session_context("")  # clear to default

            from pathlib import Path

            # Verify A has only A's content
            file_a = Path(dir_a) / "report.md"
            assert file_a.exists()
            assert "Session A content" in file_a.read_text()
            assert "Session B content" not in file_a.read_text()

            # Verify B has only B's content
            file_b = Path(dir_b) / "report.md"
            assert file_b.exists()
            assert "Session B content" in file_b.read_text()
            assert "Session A content" not in file_b.read_text()

        finally:
            set_session_context("")  # restore default
            shutil.rmtree(dir_a, ignore_errors=True)
            shutil.rmtree(dir_b, ignore_errors=True)
