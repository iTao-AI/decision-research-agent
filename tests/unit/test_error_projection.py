import logging

import pytest


SENTINEL = "DRA_ERROR_EGRESS_SENTINEL"


class HostileError(Exception):
    errno = 3024
    sqlstate = "HY000"

    def __init__(self):
        self.args = (SENTINEL,)
        self.path = f"/private/{SENTINEL}"
        self.query = f"SELECT '{SENTINEL}'"
        self.string_calls = 0

    def __str__(self):
        self.string_calls += 1
        raise AssertionError("hostile __str__ must never be evaluated")


def test_classifier_uses_connector_attributes_without_exception_text():
    from tools.error_projection import classify_exception

    exc = HostileError()
    projection = classify_exception(exc, operation="mysql_query")

    assert projection.code == "timeout"
    assert projection.error_type == "HostileError"
    assert "timed out" in projection.message.lower()
    assert SENTINEL not in projection.message
    assert exc.string_calls == 0


def test_safe_log_contains_only_closed_scalars(caplog):
    from tools.error_projection import classify_exception, safe_log

    exc = HostileError()
    projection = classify_exception(exc, operation="mysql_query")
    logger = logging.getLogger("test.error_projection")
    with caplog.at_level(logging.WARNING):
        safe_log(
            logger,
            logging.WARNING,
            event="tool_failed",
            projection=projection,
            correlation="run-safe",
            attempt=2,
        )

    record = caplog.records[-1]
    assert record.exc_info is None
    assert record.args == ("tool_failed", "timeout", "HostileError", "run-safe", 2)
    assert SENTINEL not in record.getMessage()
    assert exc.string_calls == 0


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (TimeoutError(), "timeout"),
        (ConnectionError(), "service_unavailable"),
        (OSError(), "service_unavailable"),
        (RuntimeError(), "execution_failed"),
    ],
)
def test_closed_default_classification(exc, expected):
    from tools.error_projection import classify_exception

    assert classify_exception(exc, operation="ragflow").code == expected


def test_exotic_class_name_falls_back_to_exception():
    from tools.error_projection import classify_exception

    exotic = type("bad-name", (Exception,), {})()
    assert classify_exception(exotic, operation="task_callback").error_type == "Exception"


def test_unsupported_operation_and_code_fail_closed():
    from tools.error_projection import ErrorProjection, classify_exception

    with pytest.raises(ValueError):
        classify_exception(RuntimeError(), operation="unknown")
    with pytest.raises(ValueError):
        ErrorProjection(code="not_closed", message="x", error_type="Exception")
