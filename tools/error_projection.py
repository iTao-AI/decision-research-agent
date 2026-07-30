"""Closed, model-safe projection for runtime exceptions."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal


ErrorCode = Literal[
    "configuration_missing",
    "input_invalid",
    "unsafe_statement",
    "timeout",
    "service_unavailable",
    "resource_not_found",
    "privilege_contract_invalid",
    "pool_exhausted",
    "cleanup_failed",
    "execution_failed",
]

_CODES = {
    "configuration_missing",
    "input_invalid",
    "unsafe_statement",
    "timeout",
    "service_unavailable",
    "resource_not_found",
    "privilege_contract_invalid",
    "pool_exhausted",
    "cleanup_failed",
    "execution_failed",
}
_OPERATIONS = {
    "mysql_connect": "Database connection",
    "mysql_query": "Database query",
    "mysql_cleanup": "Database cleanup",
    "ragflow_cleanup": "Document retrieval cleanup",
    "ragflow": "Document retrieval",
    "tavily": "Web search",
    "harness": "Agent execution",
    "research_execution": "Research execution",
    "task_callback": "Task callback",
}
_CODE_MESSAGES = {
    "configuration_missing": "is not configured.",
    "input_invalid": "received invalid input.",
    "unsafe_statement": "rejected an unsafe statement.",
    "timeout": "timed out.",
    "service_unavailable": "is temporarily unavailable.",
    "resource_not_found": "could not find the requested resource.",
    "privilege_contract_invalid": "failed the read-only privilege check.",
    "pool_exhausted": "has no connection available.",
    "cleanup_failed": "could not release a resource safely.",
    "execution_failed": "failed.",
}
_ERROR_TYPE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


@dataclass(frozen=True)
class ErrorProjection:
    code: ErrorCode
    message: str
    error_type: str

    def __post_init__(self) -> None:
        if self.code not in _CODES:
            raise ValueError("unsupported error code")
        if not self.message or len(self.message.encode("utf-8")) > 160:
            raise ValueError("invalid fixed error message")
        if not _ERROR_TYPE.fullmatch(self.error_type):
            raise ValueError("invalid error type")


def _exception_type(exc: BaseException) -> str:
    name = type(exc).__name__
    return name if _ERROR_TYPE.fullmatch(name) else "Exception"


def projection_for(*, operation: str, code: ErrorCode, error_type: str = "Exception") -> ErrorProjection:
    prefix = _OPERATIONS.get(operation)
    suffix = _CODE_MESSAGES.get(code)
    if prefix is None or suffix is None:
        raise ValueError("unsupported error projection")
    normalized_type = error_type if _ERROR_TYPE.fullmatch(error_type) else "Exception"
    return ErrorProjection(code=code, message=f"{prefix} {suffix}", error_type=normalized_type)


def classify_exception(exc: BaseException, *, operation: str) -> ErrorProjection:
    if operation not in _OPERATIONS:
        raise ValueError("unsupported operation")
    errno = getattr(exc, "errno", None)
    class_name = type(exc).__name__
    if errno == 3024 or isinstance(exc, TimeoutError) or "Timeout" in class_name:
        code: ErrorCode = "timeout"
    elif "PoolError" in class_name:
        code = "pool_exhausted"
    elif isinstance(exc, (ConnectionError, OSError)):
        code = "service_unavailable"
    else:
        code = "execution_failed"
    return projection_for(operation=operation, code=code, error_type=_exception_type(exc))


def safe_log(
    logger,
    level: int,
    *,
    event: str,
    projection: ErrorProjection,
    correlation: str | None = None,
    attempt: int | None = None,
) -> None:
    logger.log(
        level,
        "%s code=%s error_type=%s correlation=%s attempt=%s",
        event,
        projection.code,
        projection.error_type,
        correlation,
        attempt,
    )
