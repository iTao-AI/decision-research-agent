"""Bounded lexical admission for the deliberately narrow MySQL SELECT surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping


MAX_QUERY_CHARS = 16_384
DEFAULT_TIMEOUT_MS = 5_000
MIN_TIMEOUT_MS = 100
MAX_TIMEOUT_MS = 30_000


class SqlAdmissionError(ValueError):
    code: Literal["input_invalid", "unsafe_statement"]

    def __init__(self, code: Literal["input_invalid", "unsafe_statement"]):
        self.code = code
        message = "The SQL query is invalid." if code == "input_invalid" else "The SQL query is not permitted."
        super().__init__(message)


@dataclass(frozen=True)
class ReadOnlyStatement:
    sql: str
    timeout_ms: int
    max_rows: int = 100
    fetch_batch_rows: int = 25
    max_serialized_bytes: int = 65_536


@dataclass(frozen=True)
class _Token:
    value: str
    start: int
    end: int
    depth: int


_BANNED_TOKENS = {
    "ALTER",
    "BENCHMARK",
    "CALL",
    "CREATE",
    "DEALLOCATE",
    "DELETE",
    "DELIMITER",
    "DO",
    "DROP",
    "DUMPFILE",
    "EXECUTE",
    "GET_LOCK",
    "GRANT",
    "HANDLER",
    "INSERT",
    "INTO",
    "IS_FREE_LOCK",
    "IS_USED_LOCK",
    "LOAD",
    "LOAD_FILE",
    "MASTER_POS_WAIT",
    "OUTFILE",
    "PREPARE",
    "RELEASE_LOCK",
    "RENAME",
    "REVOKE",
    "SET",
    "SLEEP",
    "SOURCE_POS_WAIT",
    "TRUNCATE",
    "UPDATE",
    "USE",
}
_BANNED_PHRASES = {
    ("FOR", "UPDATE"),
    ("FOR", "SHARE"),
    ("LOCK", "IN", "SHARE", "MODE"),
}


def _timeout(environ: Mapping[str, str]) -> int:
    raw = environ.get("MYSQL_QUERY_TIMEOUT_MS")
    if raw is None:
        return DEFAULT_TIMEOUT_MS
    if not raw.isascii() or not raw.isdigit():
        raise SqlAdmissionError("input_invalid")
    value = int(raw)
    if not MIN_TIMEOUT_MS <= value <= MAX_TIMEOUT_MS:
        raise SqlAdmissionError("input_invalid")
    return value


def _scan(sql: str) -> list[_Token]:
    tokens: list[_Token] = []
    depth = 0
    quote: str | None = None
    i = 0
    while i < len(sql):
        char = sql[i]
        if quote is not None:
            if char == "\\":
                i += 2
                continue
            if char == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if char in "'\"`":
            quote = char
            i += 1
            continue
        if char == "\x00":
            raise SqlAdmissionError("input_invalid")
        if char == "#" or sql.startswith("/*", i) or (
            sql.startswith("--", i)
            and (i + 2 == len(sql) or sql[i + 2].isspace() or ord(sql[i + 2]) < 32)
        ):
            raise SqlAdmissionError("unsafe_statement")
        if char == ";":
            raise SqlAdmissionError("unsafe_statement")
        if char == "(":
            tokens.append(_Token(char, i, i + 1, depth))
            depth += 1
            i += 1
            continue
        if char == ")":
            depth -= 1
            if depth < 0:
                raise SqlAdmissionError("input_invalid")
            tokens.append(_Token(char, i, i + 1, depth))
            i += 1
            continue
        if char.isalnum() or char in "_$":
            start = i
            i += 1
            while i < len(sql) and (sql[i].isalnum() or sql[i] in "_$"):
                i += 1
            tokens.append(_Token(sql[start:i].upper(), start, i, depth))
            continue
        if char == ",":
            tokens.append(_Token(char, i, i + 1, depth))
        i += 1
    if quote is not None or depth != 0:
        raise SqlAdmissionError("input_invalid")
    return tokens


def _reject_dangerous(tokens: list[_Token]) -> None:
    words = [token.value for token in tokens if token.value not in {"(", ")", ","}]
    if any(word in _BANNED_TOKENS for word in words):
        raise SqlAdmissionError("unsafe_statement")
    for phrase in _BANNED_PHRASES:
        width = len(phrase)
        if any(tuple(words[index : index + width]) == phrase for index in range(len(words) - width + 1)):
            raise SqlAdmissionError("unsafe_statement")


def _governing_select(tokens: list[_Token]) -> _Token:
    top = [token for token in tokens if token.depth == 0 and token.value not in {"(", ")", ","}]
    if not top or top[0].value not in {"SELECT", "WITH"}:
        raise SqlAdmissionError("unsafe_statement")
    if top[0].value == "SELECT":
        return top[0]
    for token in top[1:]:
        if token.value == "RECURSIVE":
            continue
        if token.value == "SELECT":
            return token
    raise SqlAdmissionError("unsafe_statement")


def _bounded_limit(sql: str, tokens: list[_Token]) -> str:
    top = [token for token in tokens if token.depth == 0]
    limits = [index for index, token in enumerate(top) if token.value == "LIMIT"]
    if not limits:
        return sql + " LIMIT 101"
    if len(limits) != 1:
        raise SqlAdmissionError("unsafe_statement")
    index = limits[0]
    tail = top[index + 1 :]
    if not tail or not tail[0].value.isascii() or not tail[0].value.isdigit():
        raise SqlAdmissionError("unsafe_statement")
    count_token = tail[0]
    if len(tail) == 1:
        pass
    elif len(tail) == 3 and tail[1].value == "," and tail[2].value.isdigit():
        count_token = tail[2]
    elif len(tail) == 3 and tail[1].value == "OFFSET" and tail[2].value.isdigit():
        pass
    else:
        raise SqlAdmissionError("unsafe_statement")
    count = int(count_token.value)
    if count <= 101:
        return sql
    return sql[: count_token.start] + "101" + sql[count_token.end :]


def admit_read_only_query(query: str, *, environ: Mapping[str, str]) -> ReadOnlyStatement:
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARS:
        raise SqlAdmissionError("input_invalid")
    timeout_ms = _timeout(environ)
    sql = query.strip()
    if sql.endswith(";"):
        sql = sql[:-1].rstrip()
    tokens = _scan(sql)
    _reject_dangerous(tokens)
    governing = _governing_select(tokens)
    sql = _bounded_limit(sql, tokens)
    hint = f" /*+ MAX_EXECUTION_TIME({timeout_ms}) */"
    sql = sql[: governing.end] + hint + sql[governing.end :]
    return ReadOnlyStatement(sql=sql, timeout_ms=timeout_ms)
