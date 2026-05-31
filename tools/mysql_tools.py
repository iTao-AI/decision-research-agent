import os
import re
from langchain_core.tools import tool

from api.monitor import monitor
from tools.db_connection import MySQLConnectionManager


def get_db_config():
    """获取数据库配置文件"""
    return {
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD"),
        "host": os.getenv("MYSQL_HOST"),
        "port": os.getenv("MYSQL_PORT"),
        "database": os.getenv("MYSQL_DATABASE"),
        "autocommit": True,
        "connect_timeout": 10,   # 连接超时 10s
        "read_timeout": 30,      # 读取超时 30s
    }


# 模块级连接管理器（延迟初始化）
_connection_manager = MySQLConnectionManager(get_db_config())
_pool_created = False


def _ensure_pool():
    """确保连接池已创建"""
    global _pool_created
    if not _pool_created:
        _connection_manager.config = get_db_config()
        error = _connection_manager.create_pool()
        if error:
            return error
        _pool_created = True
    return ""


def _validate_sql_type(query: str) -> str:
    """校验 SQL 语句类型，只允许纯 SELECT 查询。"""
    if not query or not query.strip():
        return "错误：SQL 语句不能为空"

    normalized = query.strip().upper()

    if not normalized.startswith("SELECT"):
        return "错误：只允许 SELECT 查询，拒绝写入操作"

    if re.search(r'\bINTO\b', normalized):
        return "错误：SELECT INTO 不被允许"

    write_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE', 'TRUNCATE']
    for keyword in write_keywords:
        if re.search(r'\b' + keyword + r'\b', normalized):
            return f"错误：只允许 SELECT 查询，检测到写入关键字 {keyword}"

    return ""


def _validate_table_name(table_name: str) -> str:
    """校验表名合法性。"""
    if not table_name or not table_name.strip():
        return "错误：表名不能为空"

    if re.search(r'\b(UNION|SELECT|DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|TRUNCATE)\b', table_name.upper()):
        return "错误：无效的表名"

    if re.search(r'[;\'\"\\/\s]', table_name):
        return "错误：无效的表名"

    whitelist, error = _get_table_whitelist()
    if error and not whitelist:
        return error
    if table_name not in whitelist:
        return f"错误：无效的表名 '{table_name}'"

    return ""


def _get_table_whitelist() -> tuple:
    """从数据库获取表名白名单。"""
    error = _ensure_pool()
    if error:
        return [], error
    try:
        conn = _connection_manager.get_connection()
        if isinstance(conn, str):
            return [], conn
        try:
            with conn.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                tables = cursor.fetchall()
                return [table[0] for table in tables], ""
        finally:
            _connection_manager.release_connection(conn)
    except Exception as e:
        return [], f"错误：无法获取表名白名单: {e}"


@tool
def list_sql_tables() -> str:
    """Query all available tables in the database."""
    monitor.report_tool("数据库获取表名工具！")

    error = _ensure_pool()
    if error:
        monitor.report_end("数据库获取表名工具！", error=error)
        return error

    conn = None
    try:
        conn = _connection_manager.get_connection()
        if isinstance(conn, str):
            monitor.report_end("数据库获取表名工具！", error=conn)
            return conn
        with conn.cursor() as cursor:
            cursor.execute("show tables;")
            tables = cursor.fetchall()
            if not tables:
                monitor.report_end("数据库获取表名工具！", "数据库没有查询到任何表！")
                return "数据库没有查询到任何表！"
            table_names = [table[0] for table in tables]
            result = f"可用数据表:{','.join(table_names)}"
            monitor.report_end("数据库获取表名工具！", result)
            return result
    except Exception as e:
        monitor.report_end("数据库获取表名工具！", error=str(e))
        return f"查询可用表名失败:{e}"
    finally:
        if conn is not None and not isinstance(conn, str):
            _connection_manager.release_connection(conn)


@tool
def get_table_data(table_name: str) -> str:
    """Query first 100 rows of a table, returned as CSV."""
    monitor.report_tool("数据库内容浏览工具", {"读取读取的表": table_name})

    error = _validate_table_name(table_name)
    if error:
        monitor.report_end("数据库内容浏览工具", error=error)
        return error

    error = _ensure_pool()
    if error:
        monitor.report_end("数据库内容浏览工具", error=error)
        return error

    conn = None
    try:
        conn = _connection_manager.get_connection()
        if isinstance(conn, str):
            monitor.report_end("数据库内容浏览工具", error=conn)
            return conn
        with conn.cursor() as cursor:
            safe_table_name = table_name.replace("`", "").replace(";", "").split()[0]
            cursor.execute(f"select * from {safe_table_name} limit 100")
            if not cursor.description:
                monitor.report_end("数据库内容浏览工具", f"数据表 {table_name}为空或者表名无效！")
                return f"数据表 {table_name}为空或者表名无效！"
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            result = [",".join(map(str, row)) for row in rows]
            header = ",".join(columns)
            output = f"{header}\n" + "\n".join(result)
            monitor.report_end("数据库内容浏览工具", output)
            return output
    except Exception as e:
        monitor.report_end("数据库内容浏览工具", error=f"读取数据表：{table_name} 失败!{str(e)}")
        return f"读取数据表：{table_name} 失败!{str(e)}"
    finally:
        if conn is not None and not isinstance(conn, str):
            _connection_manager.release_connection(conn)


@tool
def execute_sql_query(query: str) -> str:
    """Execute a custom SQL query."""
    monitor.report_tool("数据库查询工具")

    error = _validate_sql_type(query)
    if error:
        monitor.report_end("数据库查询工具", error=error)
        return error

    error = _ensure_pool()
    if error:
        monitor.report_end("数据库查询工具", error=error)
        return error

    conn = None
    try:
        conn = _connection_manager.get_connection()
        if isinstance(conn, str):
            monitor.report_end("数据库查询工具", error=conn)
            return conn
        with conn.cursor() as cursor:
            cursor.execute(query)
            if not cursor.description:
                result = f"SQL 执行成功，受影响行数：{cursor.rowcount}"
                monitor.report_end("数据库查询工具", result)
                return result
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            if not rows:
                result = f"查询执行成功，无数据返回。涉及列名：{', '.join(columns)}"
                monitor.report_end("数据库查询工具", result)
                return result
            rows_t = [",".join(map(str, row)) for row in rows]
            header_str = ",".join(columns)
            output = f"{header_str}\n" + "\n".join(rows_t)
            monitor.report_end("数据库查询工具", output)
            return output
    except Exception as e:
        monitor.report_end("数据库查询工具", error=f"执行自定义语句{query}失败，错误!{str(e)}")
        return f"执行自定义语句{query}失败，错误!{str(e)}"
    finally:
        if conn is not None and not isinstance(conn, str):
            _connection_manager.release_connection(conn)
