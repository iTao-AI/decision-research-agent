import os
import re
from dotenv import load_dotenv
from langchain_core.tools import tool
from mysql.connector import connect, Error

from api.monitor import monitor

load_dotenv()

# 定义加载配置的函数
def get_db_config():
    """
    获取数据库配置文件
    :return:
    """
    config = {
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD"),
        "host": os.getenv("MYSQL_HOST"),
        "port": os.getenv("MYSQL_PORT"),
        "database": os.getenv("MYSQL_DATABASE"),
        "autocommit": True
    }
    return config


def _validate_sql_type(query: str) -> str:
    """
    校验 SQL 语句类型，只允许纯 SELECT 查询。

    Returns:
        str: 错误信息或空字符串表示合法
    """
    if not query or not query.strip():
        return "错误：SQL 语句不能为空"

    normalized = query.strip().upper()

    # 只允许 SELECT 开头的语句
    if not normalized.startswith("SELECT"):
        return "错误：只允许 SELECT 查询，拒绝写入操作"

    # 拒绝 SELECT INTO
    if re.search(r'\bINTO\b', normalized):
        return "错误：SELECT INTO 不被允许"

    # 拒绝包含写入关键字的语句
    write_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE', 'TRUNCATE']
    for keyword in write_keywords:
        if re.search(r'\b' + keyword + r'\b', normalized):
            return f"错误：只允许 SELECT 查询，检测到写入关键字 {keyword}"

    return ""


def _get_table_whitelist() -> tuple:
    """
    从数据库获取表名白名单。
    复用 list_sql_tables() 的 SHOW TABLES 逻辑。

    Returns:
        tuple: (list: 合法表名列表, str: 错误信息或空字符串)
    """
    config = get_db_config()
    try:
        if not all([config["user"], config["password"], config["host"], config["port"], config["database"]]):
            return [], "错误：数据库配置缺失"
        with connect(**config) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                tables = cursor.fetchall()
                return [table[0] for table in tables], ""
    except Error as e:
        return [], f"错误：无法获取表名白名单: {e}"


def _validate_table_name(table_name: str) -> str:
    """
    校验表名合法性。

    Returns:
        str: 错误信息或空字符串表示合法
    """
    if not table_name or not table_name.strip():
        return "错误：表名不能为空"

    # 拒绝包含 SQL 关键字的表名
    if re.search(r'\b(UNION|SELECT|DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|TRUNCATE)\b', table_name.upper()):
        return "错误：无效的表名"

    # 拒绝包含特殊字符的表名
    if re.search(r'[;\'\"\\/\s]', table_name):
        return "错误：无效的表名"

    # 白名单校验
    whitelist, error = _get_table_whitelist()
    if error and not whitelist:
        return error
    if table_name not in whitelist:
        return f"错误：无效的表名 '{table_name}'"

    return ""


@tool
def list_sql_tables() -> str:
    """Query all available tables in the database."""
    monitor.report_tool("数据库获取表名工具！")
    config = get_db_config()

    try:
        if not all([config["user"], config["password"], config["host"], config["port"], config["database"]]):
            return "错误: 数据库连接必要配置确实，查询失败！"
        with connect(**config) as conn:
            with conn.cursor() as cursor:
                cursor.execute("show tables;")
                tables = cursor.fetchall()
                if not tables:
                    return "数据库没有查询到任何表！"
                table_names = [table[0] for table in tables]
                return f"可用数据表:{','.join(table_names)}"
    except Error as e:
        return f"查询可用表名失败:{e}"


@tool
def get_table_data(table_name: str) -> str:
    """Query first 100 rows of a table, returned as CSV."""
    monitor.report_tool("数据库内容浏览工具", {"读取读取的表": table_name})

    # 表名白名单校验
    error = _validate_table_name(table_name)
    if error:
        return error

    config = get_db_config()
    if not all([config["user"], config["password"], config["host"], config["port"], config["database"]]):
        return "错误: 数据库配置缺失（检查账号，数据库名和密码必要配置！）"

    try:
        with connect(**config) as conn:
            with conn.cursor() as cursor:
                safe_table_name = table_name.replace("`", "").replace(";", "").split()[0]
                cursor.execute(f"select * from {safe_table_name} limit 100")
                if not cursor.description:
                    return f"数据表 {table_name}为空或者表名无效！"
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                result = [",".join(map(str, row)) for row in rows]
                header = ",".join(columns)
                return f"{header}\n" + "\n".join(result)
    except Error as e:
        return f"读取数据表：{table_name} 失败!{str(e)}"

@tool
def execute_sql_query(query: str) -> str:
    """Execute a custom SQL query."""
    monitor.report_tool("数据库查询工具")

    # SQL 语句类型校验
    error = _validate_sql_type(query)
    if error:
        return error

    config = get_db_config()
    try:
        if not all([config.get("user"), config.get("password"), config.get("database")]):
            return "错误：数据库配置缺失（请检查账号、密码、数据库名）。"
        with connect(**config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                if not cursor.description:
                    return f"SQL 执行成功，受影响行数：{cursor.rowcount}"
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                if not rows:
                    return f"查询执行成功，无数据返回。涉及列名：{', '.join(columns)}"
                rows_t = [",".join(map(str, row)) for row in rows]
                header_str = ",".join(columns)
                return f"{header_str}\n" + "\n".join(rows_t)
    except Error as e:
        return f"执行自定义语句{query}失败，错误!{str(e)}"
