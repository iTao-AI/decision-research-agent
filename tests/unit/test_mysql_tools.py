from __future__ import annotations

import pytest


SENTINEL = "DRA_ERROR_EGRESS_SENTINEL"


class FakeCursor:
    def __init__(self, columns=("id",), batches=(), execute_error=None, close_error=None):
        self.description = [(column,) for column in columns]
        self._batches = list(batches)
        self.execute_error = execute_error
        self.close_error = close_error
        self.executed = []
        self.fetchmany_sizes = []
        self.close_count = 0

    def execute(self, sql):
        self.executed.append(sql)
        if self.execute_error is not None:
            raise self.execute_error

    def fetchmany(self, size):
        self.fetchmany_sizes.append(size)
        return self._batches.pop(0) if self._batches else []

    def fetchall(self):
        raise AssertionError("custom query must not call fetchall")

    def close(self):
        self.close_count += 1
        if self.close_error is not None:
            raise self.close_error


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.close_count = 0
        self.cursor_kwargs = []

    def cursor(self, **kwargs):
        self.cursor_kwargs.append(kwargs)
        return self._cursor

    def close(self):
        self.close_count += 1


def invoke(monkeypatch, cursor, query="SELECT id FROM items"):
    from tools import mysql_tools

    connection = FakeConnection(cursor)
    monkeypatch.setattr(mysql_tools, "_ensure_pool", lambda: None)
    monkeypatch.setattr(mysql_tools._connection_manager, "get_connection", lambda: connection)
    monkeypatch.setattr(mysql_tools._connection_manager, "release_connection", lambda value: value.close())
    monkeypatch.setattr(mysql_tools.monitor, "report_tool", lambda *args, **kwargs: None)
    reports = []
    monkeypatch.setattr(mysql_tools.monitor, "report_end", lambda *args, **kwargs: reports.append((args, kwargs)))
    result = mysql_tools.execute_sql_query.invoke({"query": query})
    return result, connection, reports


def test_validation_happens_before_pool_or_connection(monkeypatch):
    from tools import mysql_tools

    touched = []
    monkeypatch.setattr(mysql_tools, "_ensure_pool", lambda: touched.append(True) or None)
    monkeypatch.setattr(mysql_tools.monitor, "report_tool", lambda *args, **kwargs: None)
    monkeypatch.setattr(mysql_tools.monitor, "report_end", lambda *args, **kwargs: None)

    result = mysql_tools.execute_sql_query.invoke({"query": f"SELECT 1; DROP TABLE {SENTINEL}"})

    assert touched == []
    assert "unsafe" in result.lower()
    assert SENTINEL not in result


def test_custom_query_executes_only_owned_sql_and_bounded_fetch(monkeypatch):
    cursor = FakeCursor(batches=[[(1,), (2,)], []])

    result, connection, _ = invoke(monkeypatch, cursor)

    assert cursor.executed == ["SELECT /*+ MAX_EXECUTION_TIME(5000) */ id FROM items LIMIT 101"]
    assert cursor.fetchmany_sizes == [25, 25]
    assert connection.cursor_kwargs == [{"buffered": False}]
    assert result == "id\n1\n2"
    assert cursor.close_count == connection.close_count == 1


def rows(count):
    return [[(index,) for index in range(start, min(start + 25, count))] for start in range(0, count, 25)] + [[]]


def test_exact_100_rows_succeed_without_trailer(monkeypatch):
    result, _, _ = invoke(monkeypatch, FakeCursor(batches=rows(100)))
    assert result.count("\n") == 100
    assert "result_truncated" not in result


def test_101st_row_produces_exact_row_truncation_trailer(monkeypatch):
    result, _, _ = invoke(monkeypatch, FakeCursor(batches=rows(101)))
    trailer = "[result_truncated code=result_truncated reason=row_limit rows_returned=100 max_rows=100 max_serialized_bytes=65536]"
    assert result.endswith(trailer)
    assert result.count("\n") == 101


def test_byte_and_combined_limits_are_bounded(monkeypatch):
    byte_result, _, _ = invoke(monkeypatch, FakeCursor(columns=("payload",), batches=[[("界" * 30_000,)], []]))
    combined_result, _, _ = invoke(monkeypatch, FakeCursor(columns=("payload",), batches=[[(("x" * 1_000),)] * 101, []]))

    assert len(byte_result.encode("utf-8")) <= 65_536
    assert "reason=byte_limit" in byte_result
    assert len(combined_result.encode("utf-8")) <= 65_536
    assert "reason=row_and_byte_limit" in combined_result


def test_csv_quotes_special_cells_and_none(monkeypatch):
    cursor = FakeCursor(
        columns=("a", "b", "c", "d"),
        batches=[[("comma,value", 'say "hi"', "line\nbreak", None)], []],
    )
    result, _, _ = invoke(monkeypatch, cursor)

    assert result == 'a,b,c,d\n"comma,value","say ""hi""","line\nbreak",'


class ConnectorTimeout(Exception):
    errno = 3024


@pytest.mark.parametrize(
    ("error", "code"),
    [(ConnectorTimeout(SENTINEL), "timeout"), (TimeoutError(SENTINEL), "timeout"), (RuntimeError(SENTINEL), "execution_failed")],
)
def test_errors_are_stable_and_resources_close_once(monkeypatch, error, code):
    cursor = FakeCursor(execute_error=error)
    result, connection, reports = invoke(monkeypatch, cursor)

    assert f"code={code}" in result
    assert SENTINEL not in result
    assert reports[-1][1]["error"] == code
    assert reports[-1][1]["error_type"] == type(error).__name__
    assert cursor.close_count == connection.close_count == 1


def test_timeout_includes_configured_statement_budget(monkeypatch):
    monkeypatch.setenv("MYSQL_QUERY_TIMEOUT_MS", "100")
    result, _, _ = invoke(monkeypatch, FakeCursor(execute_error=ConnectorTimeout(SENTINEL)))
    assert "code=timeout" in result
    assert "max_execution_ms=100" in result


def test_cursor_close_error_returns_stable_cleanup_failure_and_releases_wrapper(monkeypatch):
    cursor = FakeCursor(batches=[[(1,)], []], close_error=RuntimeError(SENTINEL))
    result, connection, _ = invoke(monkeypatch, cursor)
    assert "code=cleanup_failed" in result
    assert SENTINEL not in result
    assert cursor.close_count == connection.close_count == 1


def test_base_exception_releases_cursor_and_wrapper_once(monkeypatch):
    cursor = FakeCursor(execute_error=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        invoke(monkeypatch, cursor)
    assert cursor.close_count == 1


@pytest.mark.parametrize(
    ("projection_code", "expected"),
    [
        ("configuration_missing", "configuration_missing"),
        ("privilege_contract_invalid", "privilege_contract_invalid"),
        ("pool_exhausted", "pool_exhausted"),
    ],
)
def test_manager_projection_reaches_tool_result_and_monitor(monkeypatch, projection_code, expected):
    from tools import mysql_tools
    from tools.error_projection import projection_for

    projection = projection_for(operation="mysql_connect", code=projection_code)
    monkeypatch.setattr(mysql_tools, "_ensure_pool", lambda: projection)
    monkeypatch.setattr(mysql_tools.monitor, "report_tool", lambda *args, **kwargs: None)
    reports = []
    monkeypatch.setattr(mysql_tools.monitor, "report_end", lambda *args, **kwargs: reports.append((args, kwargs)))

    result = mysql_tools.execute_sql_query.invoke({"query": "SELECT 1"})

    assert f"code={expected}" in result
    assert reports == [(("mysql_query",), {"error": expected, "error_type": "Exception"})]


def test_get_table_data_emits_one_paired_end_on_success(monkeypatch):
    from tools import mysql_tools

    monkeypatch.setattr(mysql_tools, "_validate_table_name_with_category", lambda value: ("", None))
    monkeypatch.setattr(mysql_tools, "_execute_query", lambda query: ("id\n1", None))
    monkeypatch.setattr(mysql_tools.monitor, "report_tool", lambda *args, **kwargs: None)
    reports = []
    monkeypatch.setattr(mysql_tools.monitor, "report_end", lambda *args, **kwargs: reports.append((args, kwargs)))

    assert mysql_tools.get_table_data.invoke({"table_name": "items"}) == "id\n1"
    assert reports == [(("mysql_table_data", "id\n1"), {})]


@pytest.mark.parametrize(
    ("code", "error_type", "message"),
    [
        ("pool_exhausted", "PoolError", "Database connection has no connection available."),
        (
            "privilege_contract_invalid",
            "PrivilegeContractError",
            "Database connection failed the read-only privilege check.",
        ),
    ],
)
def test_get_table_data_preserves_whitelist_setup_projection(
    monkeypatch,
    code,
    error_type,
    message,
):
    from tools import mysql_tools
    from tools.error_projection import projection_for

    projection = projection_for(operation="mysql_connect", code=code, error_type=error_type)
    monkeypatch.setattr(mysql_tools, "_get_table_whitelist", lambda: ([], projection))
    starts = []
    ends = []
    monkeypatch.setattr(mysql_tools.monitor, "report_tool", lambda *args, **kwargs: starts.append((args, kwargs)))
    monkeypatch.setattr(mysql_tools.monitor, "report_end", lambda *args, **kwargs: ends.append((args, kwargs)))

    result = mysql_tools.get_table_data.invoke({"table_name": "items"})

    assert result == f"[tool_error code={code} error_type={error_type}] {message}"
    assert starts == [(("mysql_table_data", {"table_name": "items"}), {})]
    assert ends == [(("mysql_table_data",), {"error": code, "error_type": error_type})]


def test_mysql_startup_is_optional_only_when_all_required_config_is_absent(monkeypatch):
    from tools import mysql_tools

    monkeypatch.setattr(mysql_tools, "get_db_config", lambda: {
        "user": None, "password": None, "host": None, "port": None, "database": None
    })
    touched = []
    monkeypatch.setattr(
        mysql_tools._connection_manager,
        "configure_and_create_pool",
        lambda config: touched.append(config),
    )

    assert mysql_tools.initialize_mysql_runtime() is None
    assert touched == []


def test_mysql_startup_fails_closed_on_partial_config(monkeypatch):
    from tools import mysql_tools

    monkeypatch.setattr(mysql_tools, "get_db_config", lambda: {
        "user": "reader", "password": None, "host": "mysql", "port": "3306", "database": "db"
    })

    with pytest.raises(mysql_tools.MySQLRuntimeStartupError) as caught:
        mysql_tools.initialize_mysql_runtime()
    assert str(caught.value) == "Database connection is not configured."
