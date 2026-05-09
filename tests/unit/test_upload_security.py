"""文件上传安全单元测试 - Phase B"""
import pytest


class TestUploadSecurity:
    """Phase B: 文件上传安全"""

    def test_path_traversal_defense(self):
        """路径遍历攻击应该被防御"""
        from api.upload_security import sanitize_filename

        assert sanitize_filename("../../../etc/passwd") == "passwd"
        assert sanitize_filename("/etc/shadow") == "shadow"
        assert sanitize_filename("data/file.csv") == "file.csv"

    def test_empty_filename_rejected(self):
        """空文件名应该被拒绝"""
        from api.upload_security import validate_filename

        assert "文件名不能为空" in validate_filename("")
        assert "文件名不能为空" in validate_filename(None)

    def test_oversized_filename_rejected(self):
        """超长文件名（>255 字符）应该被拒绝"""
        from api.upload_security import validate_filename

        long_name = "a" * 256 + ".txt"
        assert "文件名过长" in validate_filename(long_name)

    def test_valid_filename_allowed(self):
        """合法文件名应该被允许"""
        from api.upload_security import validate_filename

        assert validate_filename("report.txt") == ""
        assert validate_filename("data_2024.csv") == ""

    def test_filename_sanitized(self):
        """文件名净化：Path(filename).name 应该提取纯文件名"""
        from api.upload_security import sanitize_filename

        assert sanitize_filename("../../../etc/passwd") == "passwd"
        assert sanitize_filename("/etc/shadow") == "shadow"
        assert sanitize_filename("report.txt") == "report.txt"
        assert sanitize_filename("data/file.csv") == "file.csv"

    def test_windows_path_traversal(self):
        """Windows 风格路径遍历也应该被防御"""
        from api.upload_security import sanitize_filename

        result = sanitize_filename("..\\..\\etc\\passwd")
        assert "/" not in result
        assert ".." not in result
