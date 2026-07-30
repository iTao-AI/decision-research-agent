from __future__ import annotations

import json
import logging

from langchain_core.messages import ToolMessage

from tools.error_projection import classify_exception, safe_log


MARKER = "DRA_ERROR_EGRESS_SENTINEL"


class HostileFailure(RuntimeError):
    def __str__(self) -> str:
        raise AssertionError("raw exception conversion attempted")

    def __repr__(self) -> str:
        raise AssertionError("raw exception representation attempted")


def test_one_projection_is_safe_for_every_serialized_runtime_sink(caplog) -> None:
    failure = HostileFailure(MARKER)
    projection = classify_exception(failure, operation="harness")
    logger = logging.getLogger("runtime-error-projection-test")

    with caplog.at_level(logging.ERROR, logger=logger.name):
        safe_log(
            logger,
            logging.ERROR,
            event="harness_failed",
            projection=projection,
            correlation="run-safe",
        )

    tool_message = ToolMessage(
        content=projection.message,
        tool_call_id="call-safe",
    )
    closed = {
        "logger": [
            {
                "message": record.getMessage(),
                "args": record.args,
                "exc_info": record.exc_info,
            }
            for record in caplog.records
        ],
        "model_context": tool_message.content,
        "monitor": {"error": projection.code, "error_type": projection.error_type},
        "telemetry": {"error": projection.code, "error_type": projection.error_type},
        "canonical_artifact": {"error": projection.message, "code": projection.code},
        "rest": {"detail": projection.message, "code": projection.code},
        "websocket": {"error": projection.code, "error_type": projection.error_type},
        "harness": {"message": projection.message, "diagnostics": {}},
        "task_callback": {
            "event": "task_callback_failed",
            "code": projection.code,
            "error_type": projection.error_type,
        },
    }
    serialized = json.dumps(closed, default=str, sort_keys=True)

    assert MARKER not in serialized
    assert "SENTINEL" not in serialized
    assert projection.code == "execution_failed"
    assert projection.message == "Agent execution failed."
    assert projection.error_type == "HostileFailure"
    assert all(record.exc_info is None for record in caplog.records)
