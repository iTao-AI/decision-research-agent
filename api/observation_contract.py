"""Closed, bounded projection for project-owned observation sinks."""

from __future__ import annotations

from datetime import datetime, timezone
import math
import re

from agent.token_tracking import TokenUsageData
from api.thread_ids import validate_thread_id
from tools.error_projection import RUNTIME_ERROR_CODES


MAX_OBSERVATION_COUNT = 10_000
MONITOR_SCHEMA = "dra.monitor-event.v1"
TELEMETRY_SCHEMA = "dra.telemetry-record.v1"
ERROR_CODES = RUNTIME_ERROR_CODES
ERROR_TYPE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$", re.ASCII)
ISO_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$",
    re.ASCII,
)
INVALID_TIMESTAMP_TEXT = "1970-01-01T00:00:00+00:00"
INVALID_TIMESTAMP = datetime(1970, 1, 1, tzinfo=timezone.utc)
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", re.ASCII)
SEGMENT_ID_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$",
    re.ASCII,
)
BUILTIN_SCALARS = frozenset({bool, int, float, complex})
FIXED_MESSAGES = {
    "session_created": "Workspace created",
    "tool_start": "Tool execution started",
    "tool_end": "Tool execution completed",
    "assistant_call": "Assistant call started",
    "task_result": "Task result available",
    "task_finalized": "Task finalized",
    "retry_event": "Retry scheduled",
    "cache_hit": "Tool cache hit",
    "cache_miss": "Tool cache miss",
    "run_timeout": "Research run timed out",
    "error": "Observation error",
}
LABELS = {
    "agent_name": (frozenset({"main"}), "unknown_agent"),
    "assistant_name": (frozenset({"task_subagent"}), "unknown_assistant"),
    "tool_name": (
        frozenset(
            {
                "mysql_list_tables",
                "mysql_table_data",
                "mysql_query",
                "ragflow_assistant_list",
                "ragflow_question",
                "tavily_search",
                "tavily_search_dedup",
            }
        ),
        "unknown_tool",
    ),
    "service_name": (frozenset({"tavily"}), "unknown_service"),
    "tool_status": (frozenset({"success", "error"}), "error"),
    "run_status": (
        frozenset(
            {
                "pending",
                "running",
                "completed",
                "completed_with_fallback",
                "failed",
            }
        ),
        "failed",
    ),
}


def _count(length: int) -> tuple[int, bool]:
    return min(length, MAX_OBSERVATION_COUNT), length > MAX_OBSERVATION_COUNT


class ObservationProjector:
    """Project untrusted observation inputs into closed metadata."""

    @staticmethod
    def _label(kind: str, value: object) -> str:
        allowed, sentinel = LABELS[kind]
        return (
            value
            if type(value) is str and len(value) <= 128 and value in allowed
            else sentinel
        )

    @staticmethod
    def _nonnegative_number(value: object) -> float:
        if type(value) is int:
            if value <= 0:
                return 0.0
            if value >= MAX_OBSERVATION_COUNT:
                return float(MAX_OBSERVATION_COUNT)
            return float(value)
        if type(value) is float:
            if not math.isfinite(value) or value <= 0:
                return 0.0
            return min(value, float(MAX_OBSERVATION_COUNT))
        return 0.0

    @staticmethod
    def _bounded_nonnegative_int(value: object) -> int:
        if type(value) is not int or value < 0:
            return 0
        return min(value, MAX_OBSERVATION_COUNT)

    def descriptor(self, value: object) -> dict[str, object]:
        try:
            value_type = type(value)
            if value is None:
                return {"present": False, "kind": "none"}
            if value_type is str:
                count, capped = _count(len(value))
                return {
                    "present": True,
                    "kind": "string",
                    "character_count": count,
                    "count_capped": capped,
                }
            if value_type is bytes:
                count, capped = _count(len(value))
                return {
                    "present": True,
                    "kind": "bytes",
                    "byte_count": count,
                    "count_capped": capped,
                }
            if value_type is dict:
                count, capped = _count(len(value))
                return {
                    "present": True,
                    "kind": "mapping",
                    "top_level_item_count": count,
                    "count_capped": capped,
                }
            if value_type is list or value_type is tuple:
                count, capped = _count(len(value))
                return {
                    "present": True,
                    "kind": "sequence",
                    "top_level_item_count": count,
                    "count_capped": capped,
                }
            if value_type in BUILTIN_SCALARS:
                return {"present": True, "kind": "scalar"}
        except Exception:
            pass
        return {"present": True, "kind": "opaque"}

    @staticmethod
    def _thread_id(value: object) -> str | None:
        if type(value) is not str:
            return None
        try:
            return validate_thread_id(value)
        except ValueError:
            return None

    @staticmethod
    def _run_id(value: object) -> str | None:
        return (
            value
            if type(value) is str and RUN_ID_RE.fullmatch(value)
            else None
        )

    @staticmethod
    def _segment_id(value: object) -> str | None:
        return (
            value
            if type(value) is str and SEGMENT_ID_RE.fullmatch(value)
            else None
        )

    @staticmethod
    def _timestamp_text(value: object) -> str:
        if (
            type(value) is not str
            or len(value) > 32
            or not ISO_TIMESTAMP_RE.fullmatch(value)
        ):
            return INVALID_TIMESTAMP_TEXT
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return INVALID_TIMESTAMP_TEXT
        return value if parsed.tzinfo is not None else INVALID_TIMESTAMP_TEXT

    @staticmethod
    def _timestamp_value(value: object) -> datetime:
        if type(value) is datetime and type(value.tzinfo) is timezone:
            return value
        return INVALID_TIMESTAMP

    @staticmethod
    def _token_usage(value: object) -> TokenUsageData | None:
        if value is None:
            return None
        if type(value) is not TokenUsageData:
            return None
        if (
            type(value.prompt_tokens) is not int
            or value.prompt_tokens < 0
            or type(value.completion_tokens) is not int
            or value.completion_tokens < 0
            or type(value.total_tokens) is not int
            or value.total_tokens
            != value.prompt_tokens + value.completion_tokens
            or type(value.model) is not str
            or not 1 <= len(value.model) <= 128
            or type(value.cost) is not float
            or not math.isfinite(value.cost)
            or value.cost < 0
        ):
            return None
        return value

    def normalize_error(
        self,
        *,
        status: object,
        error: object,
        error_type: object,
    ) -> tuple[str, str | None, str | None]:
        if error is None or (type(error) is str and error == ""):
            if type(status) is str and status == "error":
                return "error", "execution_failed", None
            return "success", None, None
        code = (
            error
            if type(error) is str
            and len(error) <= 32
            and error in ERROR_CODES
            else "execution_failed"
        )
        safe_type = (
            error_type
            if type(error_type) is str
            and ERROR_TYPE_RE.fullmatch(error_type)
            else None
        )
        return "error", code, safe_type

    def monitor_event(
        self,
        *,
        event_type: object,
        data: object,
        thread_id: object,
        run_id: object,
        segment_id: object,
        timestamp: object,
    ) -> dict[str, object] | None:
        try:
            if type(event_type) is not str or len(event_type) > 32:
                return None
            message = FIXED_MESSAGES.get(event_type)
            if message is None:
                return None
            source = data if type(data) is dict else {}
            if event_type == "session_created":
                path = source.get("path")
                projected_data = {
                    "workspace_created": type(path) is str and bool(path),
                }
            elif event_type == "tool_start":
                projected_data = {
                    "tool_name": self._label(
                        "tool_name",
                        source.get("tool_name"),
                    ),
                    "args": self.descriptor(source.get("args")),
                }
            elif event_type == "tool_end":
                status, code, safe_type = self.normalize_error(
                    status=source.get("status"),
                    error=source.get("error"),
                    error_type=source.get("error_type"),
                )
                projected_data = {
                    "tool_name": self._label(
                        "tool_name",
                        source.get("tool_name"),
                    ),
                    "status": status,
                    "duration_ms": self._nonnegative_number(
                        source.get("duration_ms")
                    ),
                    "result": self.descriptor(source.get("result")),
                    "error": code,
                    "error_type": safe_type,
                }
            elif event_type == "assistant_call":
                projected_data = {
                    "assistant_name": self._label(
                        "assistant_name",
                        source.get("assistant_name"),
                    ),
                    "args": self.descriptor(source.get("args")),
                }
            elif event_type == "task_result":
                projected_data = {
                    "result": self.descriptor(source.get("result")),
                }
            elif event_type == "task_finalized":
                output_path = source.get("output_path")
                run_status = self._label(
                    "run_status",
                    source.get("status"),
                )
                _, code, _ = self.normalize_error(
                    status="error" if run_status == "failed" else "success",
                    error=source.get("error"),
                    error_type=None,
                )
                projected_data = {
                    "status": run_status,
                    "fallback_used": source.get("fallback_used") is True,
                    "output_present": (
                        type(output_path) is str and bool(output_path)
                    ),
                    "error": code,
                }
            elif event_type == "retry_event":
                _, code, safe_type = self.normalize_error(
                    status="error",
                    error=source.get("error"),
                    error_type=source.get("error_type"),
                )
                projected_data = {
                    "service_name": self._label(
                        "service_name",
                        source.get("service_name"),
                    ),
                    "attempt": self._bounded_nonnegative_int(
                        source.get("attempt")
                    ),
                    "max_retries": self._bounded_nonnegative_int(
                        source.get("max_retries")
                    ),
                    "error": code,
                    "error_type": safe_type,
                }
            elif event_type in {"cache_hit", "cache_miss"}:
                projected_data = {
                    "tool_name": self._label(
                        "tool_name",
                        source.get("tool_name"),
                    ),
                    "cached": event_type == "cache_hit",
                }
            elif event_type == "run_timeout":
                projected_data = {
                    "timeout_seconds": self._nonnegative_number(
                        source.get("timeout_seconds")
                    ),
                    "previous_status": self._label(
                        "run_status",
                        source.get("previous_status"),
                    ),
                    "finalized_by_callback": (
                        source.get("finalized_by_callback") is True
                    ),
                }
            else:
                _, code, safe_type = self.normalize_error(
                    status="error",
                    error=source.get("error"),
                    error_type=source.get("error_type"),
                )
                projected_data = {
                    "error": code,
                    "error_type": safe_type,
                }
            return {
                "type": "monitor_event",
                "schema": MONITOR_SCHEMA,
                "event": event_type,
                "message": message,
                "data": projected_data,
                "thread_id": self._thread_id(thread_id),
                "run_id": self._run_id(run_id),
                "segment_id": self._segment_id(segment_id),
                "timestamp": self._timestamp_text(timestamp),
            }
        except Exception:
            return None

    def telemetry_fields(
        self,
        *,
        thread_id: object,
        run_id: object,
        segment_id: object,
        agent_name: object,
        tool_name: object,
        duration_ms: object,
        status: object,
        error: object = None,
        error_type: object = None,
        timestamp: object,
        token_usage: object,
    ) -> dict[str, object]:
        try:
            safe_status, code, safe_type = self.normalize_error(
                status=self._label("tool_status", status),
                error=error,
                error_type=error_type,
            )
            return {
                "thread_id": self._thread_id(thread_id),
                "run_id": self._run_id(run_id),
                "segment_id": self._segment_id(segment_id),
                "agent_name": self._label("agent_name", agent_name),
                "tool_name": self._label("tool_name", tool_name),
                "duration_ms": self._nonnegative_number(duration_ms),
                "status": safe_status,
                "error": code,
                "error_type": safe_type,
                "timestamp": self._timestamp_value(timestamp),
                "token_usage": self._token_usage(token_usage),
            }
        except Exception:
            return {
                "thread_id": None,
                "run_id": None,
                "segment_id": None,
                "agent_name": "unknown_agent",
                "tool_name": "unknown_tool",
                "duration_ms": 0.0,
                "status": "error",
                "error": "execution_failed",
                "error_type": None,
                "timestamp": INVALID_TIMESTAMP,
                "token_usage": None,
            }


projector = ObservationProjector()
