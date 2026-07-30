import pytest


def admit(query: str, timeout: str | None = None):
    from tools.sql_read_only import admit_read_only_query

    environ = {} if timeout is None else {"MYSQL_QUERY_TIMEOUT_MS": timeout}
    return admit_read_only_query(query, environ=environ)


@pytest.mark.parametrize(
    "query",
    [
        "SELECT id FROM items",
        " select id from items ",
        "SeLeCt 'drop; -- data', `update` FROM items;",
        "SELECT 'it\\\'s', \"a\"\"b\" FROM items",
        "SELECT id FROM items UNION SELECT id FROM archive",
        "WITH recent AS (SELECT id FROM items) SELECT id FROM recent",
        "WITH RECURSIVE n AS (SELECT 1 UNION SELECT 2) SELECT * FROM n",
        "SELECT * FROM (SELECT * FROM items LIMIT 500) nested",
    ],
)
def test_compatible_queries_receive_owned_hint_and_outer_cap(query):
    statement = admit(query)

    assert "/*+ MAX_EXECUTION_TIME(5000) */" in statement.sql
    assert statement.sql.rstrip().endswith("LIMIT 101")
    assert statement.timeout_ms == 5000
    assert (statement.max_rows, statement.fetch_batch_rows, statement.max_serialized_bytes) == (
        100,
        25,
        65_536,
    )
    assert not statement.sql.rstrip().endswith(";")


@pytest.mark.parametrize(
    ("query", "suffix"),
    [
        ("SELECT * FROM items LIMIT 10", "LIMIT 10"),
        ("SELECT * FROM items LIMIT 2, 200", "LIMIT 2, 101"),
        ("SELECT * FROM items LIMIT 200 OFFSET 3", "LIMIT 101 OFFSET 3"),
    ],
)
def test_numeric_outer_limits_are_preserved_or_tightened(query, suffix):
    assert admit(query).sql.endswith(suffix)


@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        "SELECT 1; SELECT 2",
        "SELECT 1 -- comment",
        "SELECT 1#comment",
        "SELECT /* hidden */ 1",
        "DELIMITER $$ SELECT 1",
        "SELECT 'unterminated",
        "SELECT (1",
        "WITH x AS (SELECT 1) DELETE FROM x",
        "SELECT id INTO OUTFILE '/tmp/x' FROM items",
        "SELECT id INTO @value FROM items",
        "UPDATE items SET value=1",
        "CALL mutate()",
        "DO SLEEP(1)",
        "HANDLER items OPEN",
        "LOAD DATA INFILE 'x' INTO TABLE items",
        "PREPARE stmt FROM 'SELECT 1'",
        "EXECUTE stmt",
        "DEALLOCATE PREPARE stmt",
        "SET @x=1",
        "USE other",
        "SELECT * FROM items FOR UPDATE",
        "SELECT * FROM items FOR SHARE",
        "SELECT * FROM items LOCK IN SHARE MODE",
        "SELECT SLEEP(1)",
        "SELECT BENCHMARK(2, 1+1)",
        "SELECT GET_LOCK('x', 1)",
        "SELECT RELEASE_LOCK('x')",
        "SELECT IS_FREE_LOCK('x')",
        "SELECT IS_USED_LOCK('x')",
        "SELECT LOAD_FILE('/tmp/x')",
        "SELECT MASTER_POS_WAIT('x', 1)",
        "SELECT SOURCE_POS_WAIT('x', 1)",
        "SELECT * FROM items LIMIT value",
        "SELECT * FROM items LIMIT 1 LIMIT 2",
        "SELECT * FROM items LIMIT 1, 2 OFFSET 3",
        "SELECT 1 LIMIT +999",
        "SELECT 1 LIMIT -999",
        "SELECT 1 LIMIT .999",
        "SELECT @x := 1",
    ],
)
def test_unsafe_or_ambiguous_queries_fail_closed_before_execution(query):
    from tools.sql_read_only import SqlAdmissionError

    with pytest.raises(SqlAdmissionError) as caught:
        admit(query)
    assert caught.value.code in {"input_invalid", "unsafe_statement"}
    if query:
        assert query not in str(caught.value)


def test_query_length_is_rejected_before_tokenization():
    from tools.sql_read_only import MAX_QUERY_CHARS, SqlAdmissionError

    with pytest.raises(SqlAdmissionError) as caught:
        admit("SELECT '" + ("x" * MAX_QUERY_CHARS) + "'")
    assert caught.value.code == "input_invalid"


@pytest.mark.parametrize("value", ["100", "5000", "30000"])
def test_timeout_bounds_are_accepted(value):
    assert admit("SELECT 1", value).timeout_ms == int(value)


@pytest.mark.parametrize("value", ["", "99", "30001", "5s", " 5000", "+5000"])
def test_timeout_invalid_format_or_range_is_rejected(value):
    from tools.sql_read_only import SqlAdmissionError

    with pytest.raises(SqlAdmissionError) as caught:
        admit("SELECT 1", value)
    assert caught.value.code == "input_invalid"


@pytest.mark.parametrize(("keyword", "spacing"), [("select", " "), ("SELECT", "\n"), ("SeLeCt", "\t")])
def test_keyword_case_and_whitespace_do_not_change_contract(keyword, spacing):
    statement = admit(f"{spacing}{keyword}{spacing}1{spacing}")
    assert statement.sql.endswith("LIMIT 101")
