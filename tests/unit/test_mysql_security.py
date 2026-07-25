"""SQL 安全单元测试 - Phase A"""
import pytest
from tools.mysql_tools import _validate_sql_type, _validate_table_name
from unittest.mock import MagicMock


class TestSQLValidation:
    """Task A.1: SQL 语句类型校验"""

    def test_select_allowed(self):
        """SELECT 语句应该被允许"""
        error = _validate_sql_type("SELECT * FROM users")
        assert error == "", f"SELECT 应该被允许，但返回错误：{error}"

    def test_select_with_where_allowed(self):
        """SELECT ... WHERE 应该被允许"""
        error = _validate_sql_type("SELECT * FROM users WHERE id = 1")
        assert error == ""

    def test_drop_rejected(self):
        """DROP 语句应该被拒绝"""
        error = _validate_sql_type("DROP TABLE users")
        assert "错误" in error

    def test_delete_rejected(self):
        """DELETE 语句应该被拒绝"""
        error = _validate_sql_type("DELETE FROM users WHERE id=1")
        assert "错误" in error

    def test_update_rejected(self):
        """UPDATE 语句应该被拒绝"""
        error = _validate_sql_type("UPDATE users SET name='test'")
        assert "错误" in error

    def test_insert_rejected(self):
        """INSERT 语句应该被拒绝"""
        error = _validate_sql_type("INSERT INTO users VALUES (1, 'test')")
        assert "错误" in error

    def test_alter_rejected(self):
        """ALTER 语句应该被拒绝"""
        error = _validate_sql_type("ALTER TABLE users ADD COLUMN email VARCHAR(100)")
        assert "错误" in error

    def test_create_rejected(self):
        """CREATE 语句应该被拒绝"""
        error = _validate_sql_type("CREATE TABLE test (id INT)")
        assert "错误" in error

    def test_truncate_rejected(self):
        """TRUNCATE 语句应该被拒绝"""
        error = _validate_sql_type("TRUNCATE TABLE users")
        assert "错误" in error

    def test_select_into_rejected(self):
        """SELECT INTO 语句应该被拒绝"""
        error = _validate_sql_type("SELECT * INTO new_table FROM users")
        assert "错误" in error

    def test_union_delete_rejected(self):
        """UNION DELETE 应该被拒绝"""
        error = _validate_sql_type("SELECT * FROM users UNION DELETE FROM orders")
        assert "错误" in error

    def test_empty_sql_rejected(self):
        """空 SQL 语句应该被拒绝"""
        error = _validate_sql_type("")
        assert "错误" in error

    def test_whitespace_only_sql_rejected(self):
        """纯空白 SQL 语句应该被拒绝"""
        error = _validate_sql_type("   ")
        assert "错误" in error


class TestTableNameWhitelist:
    """Task A.2: 表名白名单校验"""

    def test_malicious_table_name_rejected(self):
        """恶意表名应该被拒绝"""
        error = _validate_table_name('users; DROP TABLE users')
        assert "错误" in error

    def test_union_select_rejected(self):
        """UNION SELECT 表名应该被拒绝"""
        error = _validate_table_name('users UNION SELECT * FROM information_schema.tables')
        assert "错误" in error

    def test_empty_table_name_rejected(self):
        """空表名应该被拒绝"""
        error = _validate_table_name('')
        assert "错误" in error

    def test_path_traversal_table_name_rejected(self):
        """路径遍历表名应该被拒绝"""
        error = _validate_table_name('../../etc/passwd')
        assert "错误" in error

    def test_whitespace_only_table_name(self):
        """纯空白表名应该被拒绝"""
        error = _validate_table_name('   ')
        assert "错误" in error

    def test_table_name_with_semicolon(self):
        """包含分号的表名应该被拒绝"""
        error = _validate_table_name('users;')
        assert "错误" in error


@pytest.mark.parametrize(
    ("tool_name", "invoke_args", "patched_name", "patched_value", "expected"),
    [
        (
            "mysql_table_data",
            {"table_name": "bad;table"},
            "_get_table_whitelist",
            ([], ""),
            "input_invalid",
        ),
        (
            "mysql_query",
            {"query": "DELETE FROM users"},
            "_ensure_pool",
            "",
            "input_invalid",
        ),
        (
            "mysql_list_tables",
            {},
            "_ensure_pool",
            "pool unavailable OBS_MARKER",
            "service_unavailable",
        ),
    ],
)
def test_observation_error_categories_are_structured_and_message_independent(
    monkeypatch,
    tool_name,
    invoke_args,
    patched_name,
    patched_value,
    expected,
):
    from tools import mysql_tools

    monkeypatch.setattr(mysql_tools, patched_name, lambda: patched_value)
    report_end = MagicMock()
    monkeypatch.setattr(mysql_tools.monitor, "report_end", report_end)
    monkeypatch.setattr(mysql_tools.monitor, "report_tool", MagicMock())
    tools = {
        "mysql_table_data": mysql_tools.get_table_data,
        "mysql_query": mysql_tools.execute_sql_query,
        "mysql_list_tables": mysql_tools.list_sql_tables,
    }

    result = tools[tool_name].invoke(invoke_args)

    assert type(result) is str
    report_end.assert_called_once_with(tool_name, error=expected)
