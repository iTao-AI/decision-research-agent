"""Phase A: mysql_tools 重构测试 — 验证使用 ConnectionManager"""
import pytest
import sys
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def _mock_dependencies():
    """Mock all external dependencies before importing mysql_tools"""
    mock_mysql = MagicMock()
    mock_mysql.Error = Exception
    mock_mysql.errors.Error = Exception
    mock_mysql.pooling.MySQLConnectionPool = MagicMock()
    sys.modules["mysql.connector"] = mock_mysql
    sys.modules["mysql"] = MagicMock()

    mock_dotenv_mod = MagicMock()
    sys.modules["dotenv"] = MagicMock()
    sys.modules["dotenv"].load_dotenv = mock_dotenv_mod

    mock_monitor = MagicMock()
    sys.modules["api.monitor"] = MagicMock()
    sys.modules["api.monitor"].monitor = mock_monitor
    yield

    for mod in ["mysql.connector", "mysql", "dotenv", "api.monitor",
                "tools.db_connection", "tools.mysql_tools"]:
        sys.modules.pop(mod, None)


def _setup_pool_mock(mock_cm, mock_conn, mock_cursor=None):
    """统一设置 ConnectionManager mock: pool 创建成功，返回连接"""
    mock_cm.create_pool.return_value = ""
    mock_cm.get_connection.return_value = mock_conn
    if mock_cursor is None:
        mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_cursor


class TestMySQLToolsWithConnectionManager:
    """测试 mysql_tools 使用 ConnectionManager 而非直接 connect"""

    def test_list_sql_tables_uses_connection_manager(self):
        """list_sql_tables 应使用 ConnectionManager"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("users",), ("orders",)]

        with patch("tools.mysql_tools._connection_manager") as mock_cm:
            _setup_pool_mock(mock_cm, mock_conn, mock_cursor)

            from tools.mysql_tools import list_sql_tables
            result = list_sql_tables.invoke({})

            mock_cm.create_pool.assert_called_once()
            mock_cm.get_connection.assert_called_once()
            assert "users" in result
            assert "orders" in result

    def test_list_sql_tables_missing_config_returns_error(self):
        """配置缺失时 list_sql_tables 应返回错误字符串"""
        with patch("tools.mysql_tools._connection_manager") as mock_cm:
            mock_cm.create_pool.return_value = "错误：MySQL 配置缺失"

            from tools.mysql_tools import list_sql_tables
            result = list_sql_tables.invoke({})

            assert "错误" in result

    def test_get_table_data_uses_connection_manager(self):
        """get_table_data 应使用 ConnectionManager"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchmany.side_effect = [[(1, "Alice"), (2, "Bob")], []]

        with patch("tools.mysql_tools._connection_manager") as mock_cm:
            _setup_pool_mock(mock_cm, mock_conn, mock_cursor)
            with patch(
                "tools.mysql_tools._validate_table_name_with_category",
                return_value=("", None),
            ):
                from tools.mysql_tools import get_table_data
                result = get_table_data.invoke({"table_name": "users"})

                mock_cm.get_connection.assert_called_once()
                assert "id" in result
                assert "Alice" in result

    def test_execute_sql_query_uses_connection_manager(self):
        """execute_sql_query 应使用 ConnectionManager"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchmany.side_effect = [[(1, "Alice")], []]

        with patch("tools.mysql_tools._connection_manager") as mock_cm:
            _setup_pool_mock(mock_cm, mock_conn, mock_cursor)

            from tools.mysql_tools import execute_sql_query
            result = execute_sql_query.invoke({"query": "SELECT * FROM users"})

            mock_cm.get_connection.assert_called_once()
            assert "id" in result
            assert "Alice" in result

    def test_execute_sql_query_returns_error_string_not_exception(self):
        """execute_sql_query 应返回错误字符串而非抛异常"""
        with patch("tools.mysql_tools._connection_manager") as mock_cm:
            mock_cm.create_pool.return_value = "错误：连接失败"

            from tools.mysql_tools import execute_sql_query
            result = execute_sql_query.invoke({"query": "SELECT * FROM users"})

            assert "错误" in result

    def test_error_returns_string_not_raises(self):
        """所有工具函数应返回错误字符串，不抛异常"""
        with patch("tools.mysql_tools._connection_manager") as mock_cm:
            mock_cm.create_pool.return_value = ""
            mock_cm.get_connection.side_effect = Exception("DB error")

            from tools.mysql_tools import execute_sql_query
            result = execute_sql_query.invoke({"query": "SELECT * FROM users"})
            assert isinstance(result, str)
