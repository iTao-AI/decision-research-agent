"""Bounded, read-only MySQL tools."""

from __future__ import annotations

import csv
import io
import os
import re

from langchain_core.tools import tool

from api.monitor import monitor
from tools.db_connection import MySQLConnectionManager
from tools.error_projection import classify_exception, projection_for
from tools.sql_read_only import ReadOnlyStatement, SqlAdmissionError, admit_read_only_query


MYSQL_LIST_TABLES = "mysql_list_tables"
MYSQL_TABLE_DATA = "mysql_table_data"
MYSQL_QUERY = "mysql_query"


def get_db_config():
    return {
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD"),
        "host": os.getenv("MYSQL_HOST"),
        "port": os.getenv("MYSQL_PORT"),
        "database": os.getenv("MYSQL_DATABASE"),
        "autocommit": True,
        "connect_timeout": 10,
        "read_timeout": 30,
    }


_connection_manager = MySQLConnectionManager(get_db_config())
_pool_created = False


def _ensure_pool():
    global _pool_created
    if not _pool_created:
        _connection_manager.config = get_db_config()
        error = _connection_manager.create_pool()
        if error:
            return error
        _pool_created = True
    return ""


def _validate_sql_type_with_category(query: str) -> tuple[str, str | None]:
    try:
        admit_read_only_query(query, environ=os.environ)
    except SqlAdmissionError as exc:
        message = "错误：SQL 查询不安全" if exc.code == "unsafe_statement" else "错误：SQL 查询无效"
        return message, exc.code
    return "", None


def _validate_sql_type(query: str) -> str:
    return _validate_sql_type_with_category(query)[0]


def _validate_table_name_with_category(table_name: str) -> tuple[str, str | None]:
    if not table_name or not table_name.strip():
        return "错误：表名不能为空", "input_invalid"
    if re.search(r"\b(UNION|SELECT|DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|TRUNCATE)\b", table_name.upper()):
        return "错误：无效的表名", "input_invalid"
    if re.search(r"[;'\"\\/\s]", table_name):
        return "错误：无效的表名", "input_invalid"
    whitelist, error = _get_table_whitelist()
    if error and not whitelist:
        return error, "service_unavailable"
    if table_name not in whitelist:
        return "错误：无效的表名", "input_invalid"
    return "", None


def _validate_table_name(table_name: str) -> str:
    return _validate_table_name_with_category(table_name)[0]


def _error_result(projection, *, timeout_ms: int | None = None) -> str:
    metadata = f"code={projection.code} error_type={projection.error_type}"
    if projection.code == "timeout" and timeout_ms is not None:
        metadata += f" max_execution_ms={timeout_ms}"
    return f"[tool_error {metadata}] {projection.message}"


def _csv_line(values) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["" if value is None else value for value in values])
    return buffer.getvalue()[:-1]


def _serialize_bounded(columns, rows, statement: ReadOnlyStatement) -> str:
    header = _csv_line(columns)
    row_lines = [_csv_line(row) for row in rows[: statement.max_rows]]
    row_truncated = len(rows) > statement.max_rows
    ordinary = "\n".join([header, *row_lines])
    byte_truncated = len(ordinary.encode("utf-8")) > statement.max_serialized_bytes
    if not row_truncated and not byte_truncated:
        return ordinary
    reason = (
        "row_and_byte_limit"
        if row_truncated and byte_truncated
        else "row_limit"
        if row_truncated
        else "byte_limit"
    )
    while True:
        trailer = (
            "[result_truncated code=result_truncated "
            f"reason={reason} rows_returned={len(row_lines)} "
            f"max_rows={statement.max_rows} "
            f"max_serialized_bytes={statement.max_serialized_bytes}]"
        )
        pieces = [header, *row_lines, trailer] if header else [*row_lines, trailer]
        output = "\n".join(pieces)
        if len(output.encode("utf-8")) <= statement.max_serialized_bytes:
            return output
        if row_lines:
            row_lines.pop()
            byte_truncated = True
            reason = "row_and_byte_limit" if row_truncated else "byte_limit"
            continue
        return trailer


def _close(cursor, connection) -> BaseException | None:
    cleanup_error: BaseException | None = None
    try:
        if cursor is not None:
            cursor.close()
    except BaseException as exc:
        cleanup_error = exc
    try:
        if connection is not None:
            _connection_manager.release_connection(connection)
    except BaseException as exc:
        if cleanup_error is None:
            cleanup_error = exc
    return cleanup_error


def _get_table_whitelist() -> tuple[list[str], str]:
    error = _ensure_pool()
    if error:
        return [], error
    connection = None
    cursor = None
    primary = None
    tables: list[str] = []
    try:
        connection = _connection_manager.get_connection()
        if isinstance(connection, str):
            return [], connection
        cursor = connection.cursor()
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
    except BaseException as exc:
        primary = exc
    cleanup = _close(cursor, connection if not isinstance(connection, str) else None)
    failure = primary or cleanup
    if failure is not None:
        if not isinstance(failure, Exception):
            raise failure
        return [], classify_exception(failure, operation="mysql_query").message
    return tables, ""


@tool
def list_sql_tables() -> str:
    """Query all available tables in the database."""
    monitor.report_tool(MYSQL_LIST_TABLES)
    tables, error = _get_table_whitelist()
    if error:
        monitor.report_end(MYSQL_LIST_TABLES, error="service_unavailable")
        return error
    result = f"可用数据表:{','.join(tables)}" if tables else "数据库没有查询到任何表！"
    monitor.report_end(MYSQL_LIST_TABLES, result)
    return result


@tool
def get_table_data(table_name: str) -> str:
    """Query first 100 rows of a validated table, returned as CSV."""
    monitor.report_tool(MYSQL_TABLE_DATA, {"table_name": table_name})
    error, code = _validate_table_name_with_category(table_name)
    if error:
        monitor.report_end(MYSQL_TABLE_DATA, error=code)
        return error
    return execute_sql_query.invoke({"query": f"SELECT * FROM `{table_name}` LIMIT 100"})


@tool
def execute_sql_query(query: str) -> str:
    """Execute one admitted, bounded, read-only custom SQL query."""
    monitor.report_tool(MYSQL_QUERY)
    try:
        statement = admit_read_only_query(query, environ=os.environ)
    except SqlAdmissionError as exc:
        projection = projection_for(operation="mysql_query", code=exc.code)
        monitor.report_end(MYSQL_QUERY, error=projection.code)
        return _error_result(projection)
    error = _ensure_pool()
    if error:
        monitor.report_end(MYSQL_QUERY, error="service_unavailable")
        return error
    connection = None
    cursor = None
    primary: BaseException | None = None
    result: str | None = None
    try:
        connection = _connection_manager.get_connection()
        if isinstance(connection, str):
            monitor.report_end(MYSQL_QUERY, error="service_unavailable")
            return connection
        cursor = connection.cursor(buffered=False)
        cursor.execute(statement.sql)
        if not cursor.description:
            result = "SQL 执行成功，受影响行数：0"
        else:
            columns = [desc[0] for desc in cursor.description]
            rows = []
            while len(rows) < statement.max_rows + 1:
                batch = cursor.fetchmany(statement.fetch_batch_rows)
                if not batch:
                    break
                remaining = statement.max_rows + 1 - len(rows)
                rows.extend(list(batch)[:remaining])
            if not rows:
                result = f"查询执行成功，无数据返回。涉及列名：{', '.join(columns)}"
            else:
                result = _serialize_bounded(columns, rows, statement)
    except BaseException as exc:
        primary = exc
    cleanup = _close(cursor, connection if not isinstance(connection, str) else None)
    if primary is not None:
        if not isinstance(primary, Exception):
            raise primary
        projection = classify_exception(primary, operation="mysql_query")
        monitor.report_end(MYSQL_QUERY, error=projection.code, error_type=projection.error_type)
        return _error_result(projection, timeout_ms=statement.timeout_ms)
    if cleanup is not None:
        if not isinstance(cleanup, Exception):
            raise cleanup
        projection = projection_for(
            operation="mysql_cleanup",
            code="cleanup_failed",
            error_type=type(cleanup).__name__,
        )
        monitor.report_end(MYSQL_QUERY, error=projection.code, error_type=projection.error_type)
        return _error_result(projection)
    assert result is not None
    monitor.report_end(MYSQL_QUERY, result)
    return result
