import json
from datetime import datetime, timezone

import pytest


@pytest.mark.parametrize(
    "code",
    ["unsafe_statement", "privilege_contract_invalid", "pool_exhausted", "cleanup_failed"],
)
def test_runtime_error_codes_are_preserved_by_observation_projector(code):
    from api.observation_contract import projector

    status, projected, error_type = projector.normalize_error(
        status="error", error=code, error_type="RuntimeError"
    )

    assert (status, projected, error_type) == ("error", code, "RuntimeError")

from api.observation_contract import projector
from api.thread_ids import validate_thread_id


class Hostile:
    def __len__(self):
        raise AssertionError("custom len called")

    def __repr__(self):
        raise AssertionError("repr called")

    def __str__(self):
        raise AssertionError("str called")

    def __hash__(self):
        raise AssertionError("hash called")

    def __eq__(self, other):
        raise AssertionError("equality called")

    def __float__(self):
        raise AssertionError("float called")

    def __bool__(self):
        raise AssertionError("bool called")


def test_descriptors_are_exact_non_recursive_and_capped():
    assert projector.descriptor(None) == {"present": False, "kind": "none"}
    assert projector.descriptor("x" * 10_001) == {
        "present": True,
        "kind": "string",
        "character_count": 10_000,
        "count_capped": True,
    }
    assert projector.descriptor(b"x" * 10_001) == {
        "present": True,
        "kind": "bytes",
        "byte_count": 10_000,
        "count_capped": True,
    }
    assert projector.descriptor({"nested": {"secret": "OBS_MARKER"}}) == {
        "present": True,
        "kind": "mapping",
        "top_level_item_count": 1,
        "count_capped": False,
    }
    assert projector.descriptor([Hostile()])["top_level_item_count"] == 1
    assert projector.descriptor(Hostile()) == {
        "present": True,
        "kind": "opaque",
    }
    text_subclass = type("TextSubclass", (str,), {})
    assert projector.descriptor(text_subclass("OBS_MARKER")) == {
        "present": True,
        "kind": "opaque",
    }


def test_builtin_scalars_have_no_value_field():
    for value in (True, 7, 1.5, 2 + 3j):
        assert projector.descriptor(value) == {
            "present": True,
            "kind": "scalar",
        }


def _event(event_type: str, data: object) -> dict[str, object] | None:
    return projector.monitor_event(
        event_type=event_type,
        data=data,
        thread_id="thread-a",
        run_id="run-a",
        segment_id="run-a-seg-000",
        timestamp="2026-07-26T00:00:00+00:00",
    )


def test_tool_end_has_exact_closed_shape_and_fixed_message():
    payload = _event(
        "tool_end",
        {
            "tool_name": "tavily_search",
            "result": {"nested": "OBS_MARKER"},
            "duration_ms": 12.5,
            "error": "raw SQL OBS_MARKER",
            "error_type": "RuntimeError",
            "future_field": "OBS_MARKER",
        },
    )
    assert payload == {
        "type": "monitor_event",
        "schema": "dra.monitor-event.v1",
        "event": "tool_end",
        "message": "Tool execution completed",
        "data": {
            "tool_name": "tavily_search",
            "status": "error",
            "duration_ms": 12.5,
            "result": {
                "present": True,
                "kind": "mapping",
                "top_level_item_count": 1,
                "count_capped": False,
            },
            "error": "execution_failed",
            "error_type": "RuntimeError",
        },
        "thread_id": "thread-a",
        "run_id": "run-a",
        "segment_id": "run-a-seg-000",
        "timestamp": "2026-07-26T00:00:00+00:00",
    }
    assert "OBS_MARKER" not in json.dumps(payload, ensure_ascii=False)


def test_unknown_event_and_untrusted_labels_fail_closed():
    assert _event("future_event", {"raw": "OBS_MARKER"}) is None
    payload = _event(
        "assistant_call",
        {
            "assistant_name": "OBS_MARKER",
            "args": {"description": "OBS_MARKER"},
        },
    )
    assert payload["data"]["assistant_name"] == "unknown_assistant"
    assert payload["data"]["args"]["kind"] == "mapping"
    assert "OBS_MARKER" not in json.dumps(payload)


def test_invalid_codes_and_error_types_are_closed():
    assert projector.normalize_error(
        status="success",
        error=None,
        error_type="IgnoredType",
    ) == ("success", None, None)
    assert projector.normalize_error(
        status="error",
        error=None,
        error_type=None,
    ) == ("error", "execution_failed", None)
    assert projector.normalize_error(
        status="success",
        error="timeout",
        error_type="TimeoutError",
    ) == ("error", "timeout", "TimeoutError")
    assert projector.normalize_error(
        status="error",
        error="SELECT secret FROM raw",
        error_type="Bad.Error",
    ) == ("error", "execution_failed", None)


def test_projection_is_total_for_malicious_data():
    for event_type in (
        "session_created",
        "tool_start",
        "tool_end",
        "assistant_call",
        "task_result",
        "task_finalized",
        "retry_event",
        "cache_hit",
        "cache_miss",
        "run_timeout",
        "error",
    ):
        result = _event(event_type, Hostile())
        assert result is not None
        assert "OBS_MARKER" not in json.dumps(result)


def test_all_event_schemas_have_exact_keys_and_are_json_serializable():
    expected = {
        "session_created": {"workspace_created"},
        "tool_start": {"tool_name", "args"},
        "tool_end": {
            "tool_name",
            "status",
            "duration_ms",
            "result",
            "error",
            "error_type",
        },
        "assistant_call": {"assistant_name", "args"},
        "task_result": {"result"},
        "task_finalized": {
            "status",
            "fallback_used",
            "output_present",
            "error",
        },
        "retry_event": {
            "service_name",
            "attempt",
            "max_retries",
            "error",
            "error_type",
        },
        "cache_hit": {"tool_name", "cached"},
        "cache_miss": {"tool_name", "cached"},
        "run_timeout": {
            "timeout_seconds",
            "previous_status",
            "finalized_by_callback",
        },
        "error": {"error", "error_type"},
    }
    for event_type, keys in expected.items():
        payload = _event(event_type, {"future": "OBS_MARKER"})
        assert set(payload) == {
            "type",
            "schema",
            "event",
            "message",
            "data",
            "thread_id",
            "run_id",
            "segment_id",
            "timestamp",
        }
        assert set(payload["data"]) == keys
        json.dumps(payload, allow_nan=False)


def test_hostile_envelope_and_extreme_numbers_fail_closed():
    hostile = Hostile()
    payload = projector.monitor_event(
        event_type="run_timeout",
        data={
            "timeout_seconds": 10**100_000,
            "previous_status": hostile,
            "finalized_by_callback": hostile,
        },
        thread_id="t" * 129,
        run_id="illegal/run",
        segment_id="illegal segment",
        timestamp=hostile,
    )
    assert payload["thread_id"] is None
    assert payload["run_id"] is None
    assert payload["segment_id"] is None
    assert payload["timestamp"] == "1970-01-01T00:00:00+00:00"
    assert payload["data"]["timeout_seconds"] == 10_000.0
    json.dumps(payload, allow_nan=False)


def test_identity_patterns_match_live_application_contract():
    exact = projector.monitor_event(
        event_type="error",
        data={"error": "execution_failed"},
        thread_id="t.A_1-2",
        run_id="r.A_1-2",
        segment_id="s.A_1-2",
        timestamp="2026-07-26T00:00:00+00:00",
    )
    assert exact["thread_id"] == validate_thread_id("t.A_1-2")
    assert exact["run_id"] == "r.A_1-2"
    assert exact["segment_id"] == "s.A_1-2"
    for invalid_thread in ("t" * 129, "illegal/thread"):
        payload = projector.monitor_event(
            event_type="error",
            data={"error": "execution_failed"},
            thread_id=invalid_thread,
            run_id="run-a",
            segment_id="segment-a",
            timestamp="2026-07-26T00:00:00+00:00",
        )
        assert payload["thread_id"] is None


def test_path_presence_requires_exact_nonempty_string():
    hostile = Hostile()
    session = _event("session_created", {"path": hostile})
    finalized = _event(
        "task_finalized",
        {
            "status": "completed",
            "output_path": hostile,
            "fallback_used": True,
        },
    )
    assert session["data"] == {"workspace_created": False}
    assert finalized["data"]["output_present"] is False
    assert finalized["data"]["fallback_used"] is True


@pytest.mark.parametrize(
    ("status", "error", "error_type", "expected"),
    [
        ("success", None, "IgnoredType", ("success", None, None)),
        ("error", None, None, ("error", "execution_failed", None)),
        (
            "success",
            "timeout",
            "TimeoutError",
            ("error", "timeout", "TimeoutError"),
        ),
        (
            "error",
            "raw OBS_MARKER",
            "Bad.Error",
            ("error", "execution_failed", None),
        ),
    ],
)
def test_monitor_and_telemetry_share_exact_error_matrix(
    status,
    error,
    error_type,
    expected,
):
    event = _event(
        "tool_end",
        {
            "tool_name": "tavily_search",
            "status": status,
            "error": error,
            "error_type": error_type,
        },
    )
    telemetry = projector.telemetry_fields(
        thread_id="thread-a",
        run_id="run-a",
        segment_id="run-a-seg-000",
        agent_name="main",
        tool_name="tavily_search",
        duration_ms=0.0,
        status=status,
        error=error,
        error_type=error_type,
        timestamp=datetime(2026, 7, 26, tzinfo=timezone.utc),
        token_usage=None,
    )
    assert (
        event["data"]["status"],
        event["data"]["error"],
        event["data"]["error_type"],
    ) == expected
    assert (
        telemetry["status"],
        telemetry["error"],
        telemetry["error_type"],
    ) == expected
