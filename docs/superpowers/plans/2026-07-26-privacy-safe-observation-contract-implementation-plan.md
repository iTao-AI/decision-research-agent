# Privacy-Safe Observation Contract v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan serially, task by task, with a review checkpoint after every semantic commit. Do not use subagent-driven development for this shared-contract change. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace raw monitor, `stream_writer`, console, and telemetry observations with a closed, bounded, provider-free metadata contract without changing model-visible tool values or application authority.

**Architecture:** Add one stateless application-layer `ObservationProjector` in `api/observation_contract.py`. `ToolMonitor` projects an event once and sends that same closed payload to WebSocket and LangGraph `stream_writer`, prints only its fixed message, and separately creates a projector-validated `TelemetryRecord`; telemetry construction and collection re-project inputs so direct internal construction cannot bypass the contract.

**Tech Stack:** Python 3.11, FastAPI WebSocket transport, LangGraph `stream_writer`, dataclasses, pytest, existing in-process telemetry, and existing repository documentation/audit tooling. No new dependency, provider/model call, credential, live data, database migration, or Docker execution is permitted.

## Global Constraints

- Authority spec: `docs/superpowers/specs/2026-07-25-privacy-safe-observation-contract-design.md`.
- Keep execution serial because the projector, monitor, telemetry, call sites, and public contract share one schema and one set of labels.
- Preserve model-visible `ToolMessage` values and tool return values byte-for-byte.
- Preserve `ResearchRun`, Evidence, canonical result, artifact, review, delivery, and application-database authority.
- Preserve `/ws/runs/{run_id}`, `/api/telemetry/runs/{run_id}`, event names, identity/routing fields, and timestamp fields.
- Preserve the database schema, dependencies, runtime budgets, `VERSION`, immutable `v0.1.6`, and the Night Voyager consumer pin.
- Keep LangGraph `stream_writer` as transport only. Do not use `wrap_tool_call`, `ToolMessage.artifact`, framework trace, or checkpoint state as observation or business authority.
- Projection must be pure, total, bounded, non-throwing, content-depth independent, and free of provider, credential, database, filesystem, or model-context access.
- Do not recurse, call `repr()`, call `str()`, JSON-serialize caller values, call a custom `__len__`, or compute content hashes.
- Cap string, bytes, mapping, and sequence counts at `10_000`; report the cap with `count_capped=true`.
- Treat reporter labels, including `assistant_name`, `tool_name`, and `service_name`, as untrusted. Only closed call-site aliases may pass.
- Accept legacy raw `error=` arguments at reporter boundaries, discard their content immediately, and map unknown non-null values to `execution_failed`. Never classify exception text.
- Collector, projector, WebSocket, `stream_writer`, and console failures must not change a tool return, model-visible result, retry count/timing, or terminal outcome.
- Do not add a raw compatibility endpoint, environment variable, unsafe flag, schema migration, dependency, Release, or consumer upgrade.
- Stop and request renewed architecture approval if implementation needs an authority/DB/dependency/consumer file not listed below, changes model-visible behavior, or requires an ADR.

---

## Exact Planned File Map

| Path | Action | Responsibility |
| --- | --- | --- |
| `api/observation_contract.py` | Create | Single pure projector, descriptor shapes, closed labels/codes, event schemas, fixed messages, and telemetry projection. |
| `tests/unit/test_observation_contract.py` | Create | Exhaustive descriptor, malicious-object, event-schema, label, error, and totality tests. |
| `agent/telemetry.py` | Modify | Make `TelemetryRecord` self-projecting and make `TelemetryCollector.record` reject/re-project bypass attempts. |
| `api/server.py` | Modify | Serialize the closed telemetry schema and keep timeout observation data on the projector path. |
| `tests/unit/test_telemetry.py` | Modify | Lock direct-construction safety, error discard, type validation, and capacity behavior. |
| `tests/unit/test_telemetry_integration.py` | Modify | Lock monitor-to-collector safe records. |
| `tests/integration/test_run_auxiliary_isolation.py` | Modify | Lock safe telemetry API output plus unchanged run isolation and WebSocket routing. |
| `api/monitor.py` | Modify | Project once, distribute one safe payload, use fixed console messages, and keep all reporting best effort. |
| `tests/unit/test_monitor_sanitization.py` | Modify | Replace redaction/truncation expectations with closed descriptor/event expectations and failure isolation. |
| `tests/integration/test_observation_delivery.py` | Create | Prove one marker cannot cross WebSocket, `stream_writer`, telemetry, or console while identities and returns remain unchanged. |
| `agent/run_result.py` | Modify | Replace model-provided assistant labels with the stable `task_subagent` alias while preserving accumulated content/Evidence. |
| `tools/retry_utils.py` | Modify | Pass stable retry code and exception class name without stringifying the exception. |
| `tools/mysql_tools.py` | Modify | Replace display labels and raw errors with exact aliases/codes while preserving returned strings. |
| `tools/ragflow_tools.py` | Modify | Replace display labels/service labels/raw errors, and remove the duplicate raw answer observation while preserving returned answers. |
| `tools/tavily_tools.py` | Modify | Replace display label/raw errors with the exact alias/codes while preserving returned dicts/strings. |
| `tests/unit/test_agent_run_result.py` | Modify | Lock assistant aliasing and unchanged task-result/Evidence behavior. |
| `tests/unit/test_retry_utils.py` | Modify | Lock retry error type metadata and unchanged retry behavior. |
| `tests/unit/test_mysql_security.py` | Modify | Add monitor alias/error-code assertions without a database connection. |
| `tests/unit/test_ragflow_tools.py` | Modify | Lock aliases/codes, no raw question/answer observation, and unchanged tool returns/cleanup. |
| `tests/unit/test_tavily_tools.py` | Modify | Lock aliases/codes, closed result observation, and unchanged returned result. |
| `docs/reference/observation-contract.md` | Create | Public observation schemas, descriptors, error codes, compatibility, authority, and non-claims. |
| `docs/reference/api-contract.md` | Modify | Complete the WebSocket event matrix and closed telemetry response. |
| `docs/reference/data-models.md` | Modify | Replace the raw telemetry example with `dra.telemetry-record.v1`. |
| `docs/README.md` | Modify | Index the new observation reference. |
| `CHANGELOG.md` | Modify | Add the security hardening under `Unreleased`, with compatibility and non-claims. |
| `tests/unit/test_documentation_contracts.py` | Modify | Lock the observation reference, event matrix, telemetry model, index, changelog, and non-claims. |

**Hard stop:** The implementation may not modify any other production, authority, persistence, migration, dependency, CI, release, `VERSION`, frontend, or consumer file. If a test demonstrates that an unlisted authority file must change, preserve the RED evidence and request a new decision instead of expanding this list.

## Live Symbol And Signature Map

The plan is based on these current symbols and preserves their non-observation behavior:

| Live symbol | Current/planned signature contract |
| --- | --- |
| `api.monitor.sanitize_args` | Current `sanitize_args(args: dict | None) -> dict | None`; planned compatibility signature `sanitize_args(args: object) -> dict[str, object]`, returning only `projector.descriptor(args)`. |
| `api.monitor.ToolMonitor._emit` | Keep `_emit(self, event_type: str, message: str, data: Optional[Dict[str, Any]] = None, thread_id: str | None = None, run_id: str | None = None, segment_id: str | None = None)` so live callers remain source-compatible; ignore caller `message`. |
| `api.monitor.ToolMonitor.report_start` | Keep `report_start(self, tool_name: str, args: Dict[str, Any] = None)`. |
| `api.monitor.ToolMonitor.report_tool` | Keep `report_tool(self, tool_name: str, args: Dict[str, Any] = None)` as the alias of `report_start`. |
| `api.monitor.ToolMonitor.report_end` | Extend to `report_end(self, tool_name: str, result: Any = None, error: object = None, error_type: object = None)`; legacy raw `error` input remains accepted but is never retained. |
| `api.monitor.ToolMonitor.report_assistant` | Keep `report_assistant(self, assistant_name: str, args: Dict[str, Any] = None)`; projector closes both inputs. |
| `api.monitor.ToolMonitor.report_task_result` | Broaden annotation to `report_task_result(self, result: object)`; never mutate or copy content into output. |
| `api.monitor.ToolMonitor.report_task_finalized` | Keep existing `thread_id`, `status`, `fallback_used`, `output_path`, and `error_message` arguments; project only status, booleans, and stable error metadata. |
| `api.monitor.ToolMonitor.report_session_dir` | Keep `report_session_dir(self, path: str)`; project only `workspace_created`. |
| `api.monitor.ToolMonitor.report_retry` | Extend to `report_retry(self, service_name: str, attempt: int, max_retries: int, error: object = None, error_type: object = None)`. |
| `api.monitor.ToolMonitor.report_cache_hit` | Keep `report_cache_hit(self, tool_name: str, cached: bool = True)`. |
| `agent.telemetry.TelemetryRecord` | Preserve identity, duration, status, token usage, and timestamp fields; add `schema` and `error_type`, and project all observation fields in `__post_init__`. |
| `agent.telemetry.TelemetryCollector.record` | Keep `record(self, record: TelemetryRecord) -> None`; exact-type check and reconstruction close bypasses. |
| `api.server._serialize_telemetry` | Keep `_serialize_telemetry(records)` and its list return; add only closed `schema` and `error_type` positions. |
| `api.server.get_run_telemetry` | Keep `async get_run_telemetry(run_id: str)` and route `GET /api/telemetry/runs/{run_id}`. |
| `api.server.run_websocket_endpoint` | Keep `async run_websocket_endpoint(websocket: WebSocket, run_id: str)` and route `/ws/runs/{run_id}`. |
| `agent.run_result.process_stream_chunk` | Keep `process_stream_chunk(chunk: dict[str, Any], accumulator: AgentRunAccumulator, monitor) -> None`; change only the observation alias. |
| `tools.retry_utils.retry_async` | Keep current callable, retry budget, backoff, and exception semantics; change only `monitor.report_retry` metadata arguments. |
| `tools.mysql_tools.list_sql_tables` | Keep `list_sql_tables() -> str`. |
| `tools.mysql_tools.get_table_data` | Keep `get_table_data(table_name: str) -> str`. |
| `tools.mysql_tools.execute_sql_query` | Keep `execute_sql_query(query: str) -> str`. |
| `tools.ragflow_tools.get_assistant_list` | Keep `get_assistant_list(dummy_arg: str = "") -> str`. |
| `tools.ragflow_tools.create_ask_delete` | Keep `create_ask_delete(assistant_name: str, question: str) -> str`. |
| `tools.tavily_tools._internet_search_impl` | Keep query/result behavior and all current parameters: `query`, `max_results`, `topic`, `include_raw_content`, and `include_domains`. |
| `api.monitor.ConnectionManager.send_to_run` | Keep `async send_to_run(self, message: dict, run_id: str)` and run-scoped routing. |

## Shared Interfaces And Closed Values

All tasks use these exact public implementation signatures:

- `ObservationProjector.descriptor(self, value: object) -> dict[str, object]`
- `ObservationProjector.error_code(self, value: object) -> str | None`
- `ObservationProjector.error_type(self, value: object) -> str | None`
- `ObservationProjector.monitor_event(self, *, event_type: str, data: object, thread_id: str | None, run_id: str | None, segment_id: str | None, timestamp: str) -> dict[str, object] | None`
- `ObservationProjector.telemetry_fields(self, *, thread_id: str, run_id: str | None, segment_id: str | None, agent_name: object, tool_name: object, duration_ms: object, status: object, error: object = None, error_type: object = None) -> dict[str, object]`
- module singleton: `projector = ObservationProjector()`

`monitor_event()` returns `None` for an unknown event. It never returns caller `message`; messages are selected only from this fixed table:

| Event | Fixed message |
| --- | --- |
| `session_created` | `Workspace created` |
| `tool_start` | `Tool execution started` |
| `tool_end` | `Tool execution completed` |
| `assistant_call` | `Assistant call started` |
| `task_result` | `Task result available` |
| `task_finalized` | `Task finalized` |
| `retry_event` | `Retry scheduled` |
| `cache_hit` | `Tool cache hit` |
| `cache_miss` | `Tool cache miss` |
| `run_timeout` | `Research run timed out` |
| `error` | `Observation error` |

Exact descriptor shapes:

| Exact input type | Descriptor |
| --- | --- |
| `None` | `{"present": False, "kind": "none"}` |
| exact `str` | `{"present": True, "kind": "string", "character_count": N, "count_capped": B}` |
| exact `bytes` | `{"present": True, "kind": "bytes", "byte_count": N, "count_capped": B}` |
| exact `dict` | `{"present": True, "kind": "mapping", "top_level_item_count": N, "count_capped": B}` |
| exact `list` or `tuple` | `{"present": True, "kind": "sequence", "top_level_item_count": N, "count_capped": B}` |
| exact `bool`, `int`, `float`, or `complex` | `{"present": True, "kind": "scalar"}` |
| every subclass or other object | `{"present": True, "kind": "opaque"}` |

`N` is `min(exact_builtin_length, 10_000)` and `B` is whether the exact built-in length exceeded `10_000`. Subclasses are always `opaque`, so custom `__len__`, `__str__`, `__repr__`, iterators, properties, or encoders are never invoked.

Closed stable error codes:

```text
configuration_missing
input_invalid
resource_not_found
timeout
service_unavailable
execution_failed
retryable_failure
```

Any non-null value outside this set becomes `execution_failed`. `error_type` is retained only when it is an exact `str` matching ASCII `^[A-Za-z_][A-Za-z0-9_]{0,127}$`; otherwise it becomes `None`.

Closed aliases:

| Label class | Accepted aliases | Sentinel |
| --- | --- | --- |
| `agent_name` | `main` | `unknown_agent` |
| `assistant_name` | `task_subagent` | `unknown_assistant` |
| `tool_name` | `mysql_list_tables`, `mysql_table_data`, `mysql_query`, `ragflow_assistant_list`, `ragflow_question`, `tavily_search`, `tavily_search_dedup` | `unknown_tool` |
| `service_name` | `tavily`, `ragflow_list`, `ragflow_find_chat`, `ragflow_create_session`, `ragflow_ask` | `unknown_service` |
| tool telemetry `status` | `success`, `error` | `error` |
| run `previous_status` / final status | `pending`, `running`, `completed`, `completed_with_fallback`, `failed` | `failed` |

Reporter inputs never extend these sets. Adding an alias requires an explicit call-site change and contract test.

## Serial Task Interfaces

| Task | Consumes | Produces |
| --- | --- | --- |
| 1 | Approved spec only | `projector` and its exact pure contract. |
| 2 | Task 1 `projector.telemetry_fields()` | Self-projecting `TelemetryRecord`, safe collector, closed API records. |
| 3 | Tasks 1-2 projector and telemetry | One projected event shared by WebSocket/`stream_writer`/console, best-effort sinks. |
| 4 | Task 3 reporter signatures | Stable aliases/codes at every live call site; unchanged tool/model values. |
| 5 | Final Tasks 1-4 behavior | Public reference, API/data-model/index/changelog contract tests. |
| 6 | All prior tasks | Fresh focused/full/CI-parity evidence and execution handoff. |

---

### Task 1: Add The Pure Observation Projector

**Files:**
- Create: `api/observation_contract.py`
- Create: `tests/unit/test_observation_contract.py`

**Interfaces:**
- Consumes: exact values and tables in **Shared Interfaces And Closed Values**.
- Produces: `ObservationProjector` and singleton `projector` with the five exact method signatures above.

- [ ] **Step 1: Write descriptor and malicious-object RED tests**

```python
from api.observation_contract import projector


class Hostile:
    def __len__(self):
        raise AssertionError("custom len called")

    def __repr__(self):
        raise AssertionError("repr called")

    def __str__(self):
        raise AssertionError("str called")


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
    assert projector.descriptor(Hostile()) == {"present": True, "kind": "opaque"}
    assert projector.descriptor(type("TextSubclass", (str,), {})("OBS_MARKER")) == {
        "present": True,
        "kind": "opaque",
    }


def test_builtin_scalars_have_no_value_field():
    for value in (True, 7, 1.5, 2 + 3j):
        assert projector.descriptor(value) == {"present": True, "kind": "scalar"}
```

- [ ] **Step 2: Run descriptor tests and verify RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q \
  tests/unit/test_observation_contract.py::test_descriptors_are_exact_non_recursive_and_capped \
  tests/unit/test_observation_contract.py::test_builtin_scalars_have_no_value_field
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'api.observation_contract'`.

- [ ] **Step 3: Write event, label, error, and totality RED tests**

```python
import json

from api.observation_contract import projector


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
        {"assistant_name": "OBS_MARKER", "args": {"description": "OBS_MARKER"}},
    )
    assert payload["data"]["assistant_name"] == "unknown_assistant"
    assert payload["data"]["args"]["kind"] == "mapping"
    assert "OBS_MARKER" not in json.dumps(payload)


def test_invalid_codes_and_error_types_are_closed():
    assert projector.error_code(None) is None
    assert projector.error_code("timeout") == "timeout"
    assert projector.error_code("SELECT secret FROM raw") == "execution_failed"
    assert projector.error_type("TimeoutError") == "TimeoutError"
    assert projector.error_type("Bad.Error") is None


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
```

- [ ] **Step 4: Run event tests and verify RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q tests/unit/test_observation_contract.py
```

Expected: FAIL because the projector and closed schemas do not exist.

- [ ] **Step 5: Implement the projector with exact built-in checks**

Implement the constants and descriptor core exactly as follows, then implement each event branch by selecting only the fields named in the spec:

```python
from __future__ import annotations

from datetime import datetime
import math
import re


MAX_OBSERVATION_COUNT = 10_000
MONITOR_SCHEMA = "dra.monitor-event.v1"
TELEMETRY_SCHEMA = "dra.telemetry-record.v1"
ERROR_CODES = frozenset({
    "configuration_missing",
    "input_invalid",
    "resource_not_found",
    "timeout",
    "service_unavailable",
    "execution_failed",
    "retryable_failure",
})
ERROR_TYPE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$", re.ASCII)
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
        frozenset({
            "mysql_list_tables",
            "mysql_table_data",
            "mysql_query",
            "ragflow_assistant_list",
            "ragflow_question",
            "tavily_search",
            "tavily_search_dedup",
        }),
        "unknown_tool",
    ),
    "service_name": (
        frozenset({
            "tavily",
            "ragflow_list",
            "ragflow_find_chat",
            "ragflow_create_session",
            "ragflow_ask",
        }),
        "unknown_service",
    ),
    "tool_status": (frozenset({"success", "error"}), "error"),
    "run_status": (
        frozenset({
            "pending",
            "running",
            "completed",
            "completed_with_fallback",
            "failed",
        }),
        "failed",
    ),
}


def _count(length: int) -> tuple[int, bool]:
    return min(length, MAX_OBSERVATION_COUNT), length > MAX_OBSERVATION_COUNT


class ObservationProjector:
    @staticmethod
    def _label(kind: str, value: object) -> str:
        allowed, sentinel = LABELS[kind]
        return value if type(value) is str and value in allowed else sentinel

    @staticmethod
    def _nonnegative_number(value: object) -> float:
        if type(value) not in {int, float}:
            return 0.0
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else 0.0

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

    def error_code(self, value: object) -> str | None:
        if value is None or (type(value) is str and value == ""):
            return None
        if type(value) is str and value in ERROR_CODES:
            return value
        return "execution_failed"

    def error_type(self, value: object) -> str | None:
        if type(value) is str and ERROR_TYPE_RE.fullmatch(value):
            return value
        return None

    def monitor_event(
        self,
        *,
        event_type: str,
        data: object,
        thread_id: str | None,
        run_id: str | None,
        segment_id: str | None,
        timestamp: str,
    ) -> dict[str, object] | None:
        try:
            message = FIXED_MESSAGES.get(event_type)
            if message is None:
                return None
            source = data if type(data) is dict else {}
            if event_type == "session_created":
                projected_data = {
                    "workspace_created": source.get("workspace_created") is True,
                }
            elif event_type == "tool_start":
                projected_data = {
                    "tool_name": self._label("tool_name", source.get("tool_name")),
                    "args": self.descriptor(source.get("args")),
                }
            elif event_type == "tool_end":
                code = self.error_code(source.get("error"))
                projected_data = {
                    "tool_name": self._label("tool_name", source.get("tool_name")),
                    "status": "error" if code is not None else "success",
                    "duration_ms": self._nonnegative_number(
                        source.get("duration_ms")
                    ),
                    "result": self.descriptor(source.get("result")),
                    "error": code,
                    "error_type": self.error_type(source.get("error_type")),
                }
            elif event_type == "assistant_call":
                projected_data = {
                    "assistant_name": self._label(
                        "assistant_name", source.get("assistant_name")
                    ),
                    "args": self.descriptor(source.get("args")),
                }
            elif event_type == "task_result":
                projected_data = {
                    "result": self.descriptor(source.get("result")),
                }
            elif event_type == "task_finalized":
                projected_data = {
                    "status": self._label("run_status", source.get("status")),
                    "fallback_used": source.get("fallback_used") is True,
                    "output_present": source.get("output_present") is True,
                    "error": self.error_code(source.get("error")),
                }
            elif event_type == "retry_event":
                projected_data = {
                    "service_name": self._label(
                        "service_name", source.get("service_name")
                    ),
                    "attempt": self._bounded_nonnegative_int(
                        source.get("attempt")
                    ),
                    "max_retries": self._bounded_nonnegative_int(
                        source.get("max_retries")
                    ),
                    "error": self.error_code(source.get("error")),
                    "error_type": self.error_type(source.get("error_type")),
                }
            elif event_type in {"cache_hit", "cache_miss"}:
                projected_data = {
                    "tool_name": self._label("tool_name", source.get("tool_name")),
                    "cached": event_type == "cache_hit",
                }
            elif event_type == "run_timeout":
                projected_data = {
                    "timeout_seconds": self._nonnegative_number(
                        source.get("timeout_seconds")
                    ),
                    "previous_status": self._label(
                        "run_status", source.get("previous_status")
                    ),
                    "finalized_by_callback": (
                        source.get("finalized_by_callback") is True
                    ),
                }
            else:
                projected_data = {
                    "error": self.error_code(source.get("error")),
                    "error_type": self.error_type(source.get("error_type")),
                }
            return {
                "type": "monitor_event",
                "schema": MONITOR_SCHEMA,
                "event": event_type,
                "message": message,
                "data": projected_data,
                "thread_id": thread_id,
                "run_id": run_id,
                "segment_id": segment_id,
                "timestamp": timestamp,
            }
        except Exception:
            return None

    def telemetry_fields(
        self,
        *,
        thread_id: str,
        run_id: str | None,
        segment_id: str | None,
        agent_name: object,
        tool_name: object,
        duration_ms: object,
        status: object,
        error: object = None,
        error_type: object = None,
    ) -> dict[str, object]:
        try:
            code = self.error_code(error)
            safe_status = self._label("tool_status", status)
            if safe_status == "error" and code is None:
                code = "execution_failed"
            return {
                "thread_id": (
                    thread_id if type(thread_id) is str else "unknown"
                ),
                "run_id": run_id if type(run_id) is str else None,
                "segment_id": (
                    segment_id if type(segment_id) is str else None
                ),
                "agent_name": self._label("agent_name", agent_name),
                "tool_name": self._label("tool_name", tool_name),
                "duration_ms": self._nonnegative_number(duration_ms),
                "status": "error" if code is not None else "success",
                "error": code,
                "error_type": self.error_type(error_type),
            }
        except Exception:
            return {
                "thread_id": "unknown",
                "run_id": None,
                "segment_id": None,
                "agent_name": "unknown_agent",
                "tool_name": "unknown_tool",
                "duration_ms": 0.0,
                "status": "error",
                "error": "execution_failed",
                "error_type": None,
            }


projector = ObservationProjector()
```

The implementation audit must confirm that the concrete code above:

1. starts with `source = data if type(data) is dict else {}`;
2. uses a closed event-to-message lookup;
3. returns `None` when the event key is absent;
4. builds a new event-specific `projected_data` dict without iterating caller keys;
5. normalizes labels through the exact allowlists above;
6. normalizes non-finite or negative duration to `0.0`;
7. preserves `thread_id`, `run_id`, `segment_id`, and the generated timestamp exactly;
8. catches every exception and returns `None` or the fixed safe telemetry fallback.

- [ ] **Step 6: Run Task 1 GREEN**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q tests/unit/test_observation_contract.py
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

```bash
git add api/observation_contract.py tests/unit/test_observation_contract.py
git diff --cached --check
git commit -m "feat(observation): add closed projection contract"
```

---

### Task 2: Make Telemetry Retention And API Non-Bypassable

**Files:**
- Modify: `agent/telemetry.py:10-67`
- Modify: `api/server.py:1124-1145`
- Modify: `tests/unit/test_telemetry.py`
- Modify: `tests/unit/test_telemetry_integration.py`
- Modify: `tests/integration/test_run_auxiliary_isolation.py:76-182`

**Interfaces:**
- Consumes: `projector.telemetry_fields() -> dict[str, object]` with the exact keyword-only signature defined above.
- Produces: `TelemetryRecord.error` as stable code only, optional `error_type`, fixed `schema`, and API records matching `dra.telemetry-record.v1`.

- [ ] **Step 1: Write direct-construction and collector-bypass RED tests**

```python
def test_record_discards_raw_error_at_construction():
    from agent.telemetry import TelemetryRecord

    record = TelemetryRecord(
        thread_id="thread-a",
        run_id="run-a",
        segment_id="run-a-seg-000",
        agent_name="raw agent OBS_MARKER",
        tool_name="raw tool OBS_MARKER",
        duration_ms=1.0,
        status="error",
        error="SELECT secret FROM private_table OBS_MARKER",
        error_type="RuntimeError",
    )
    assert record.schema == "dra.telemetry-record.v1"
    assert record.agent_name == "unknown_agent"
    assert record.tool_name == "unknown_tool"
    assert record.error == "execution_failed"
    assert record.error_type == "RuntimeError"
    assert "OBS_MARKER" not in vars(record).values()


def test_collector_rejects_telemetry_record_subclass():
    from agent.telemetry import TelemetryCollector, TelemetryRecord

    class BypassRecord(TelemetryRecord):
        pass

    collector = TelemetryCollector()
    collector.record(BypassRecord(
        thread_id="thread-a",
        agent_name="main",
        tool_name="tavily_search",
        duration_ms=1.0,
        status="success",
    ))
    assert collector.get_by_thread("thread-a") == []
```

- [ ] **Step 2: Write telemetry API RED assertion**

Extend `test_telemetry_api_isolates_two_runs_in_same_thread` so one direct record supplies a raw marker error and assert:

```python
assert run_a.json()[0] == {
    "schema": "dra.telemetry-record.v1",
    "thread_id": "shared-thread",
    "run_id": "run-a",
    "segment_id": "run-a-seg-000",
    "agent_name": "main",
    "tool_name": "tavily_search",
    "duration_ms": 1.0,
    "status": "error",
    "error": "execution_failed",
    "error_type": "RuntimeError",
    "timestamp": run_a.json()[0]["timestamp"],
}
assert "OBS_MARKER" not in run_a.text
```

- [ ] **Step 3: Run telemetry RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_telemetry.py \
  tests/unit/test_telemetry_integration.py \
  tests/integration/test_run_auxiliary_isolation.py::test_telemetry_api_isolates_two_runs_in_same_thread
```

Expected: FAIL because raw errors and labels are retained and the API has no schema/error type.

- [ ] **Step 4: Implement self-projecting records and safe collection**

Use a frozen dataclass and re-project during `__post_init__`:

```python
@dataclass(frozen=True)
class TelemetryRecord:
    thread_id: str
    agent_name: str
    tool_name: str
    duration_ms: float
    status: str
    run_id: str | None = None
    segment_id: str | None = None
    error: str | None = None
    error_type: str | None = None
    token_usage: "TokenUsageData | None" = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    schema: str = field(init=False, default="dra.telemetry-record.v1")

    def __post_init__(self) -> None:
        safe = projector.telemetry_fields(
            thread_id=self.thread_id,
            run_id=self.run_id,
            segment_id=self.segment_id,
            agent_name=self.agent_name,
            tool_name=self.tool_name,
            duration_ms=self.duration_ms,
            status=self.status,
            error=self.error,
            error_type=self.error_type,
        )
        for name, value in safe.items():
            object.__setattr__(self, name, value)
```

At the start of `TelemetryCollector.record`:

```python
if type(record) is not TelemetryRecord:
    return
```

Then create one new exact `TelemetryRecord` from the already-safe primitive fields before retention. This second projection prevents monkeypatched or mutated inputs from bypassing the collector. Keep the 500-record cap and run/thread isolation unchanged.

Update `_serialize_telemetry()` to emit only:

```python
{
    "schema": r.schema,
    "thread_id": r.thread_id,
    "run_id": r.run_id,
    "segment_id": r.segment_id,
    "agent_name": r.agent_name,
    "tool_name": r.tool_name,
    "duration_ms": r.duration_ms,
    "status": r.status,
    "error": r.error,
    "error_type": r.error_type,
    "timestamp": r.timestamp.isoformat(),
}
```

- [ ] **Step 5: Run Task 2 GREEN and isolation regression**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_telemetry.py \
  tests/unit/test_telemetry_integration.py \
  tests/integration/test_run_auxiliary_isolation.py::test_telemetry_api_isolates_two_runs_in_same_thread \
  tests/integration/test_run_auxiliary_isolation.py::test_monitor_isolates_same_tool_timing_and_routes_by_run
```

Expected: PASS; run A and run B remain isolated.

- [ ] **Step 6: Commit Task 2**

```bash
git add \
  agent/telemetry.py \
  api/server.py \
  tests/unit/test_telemetry.py \
  tests/unit/test_telemetry_integration.py \
  tests/integration/test_run_auxiliary_isolation.py
git diff --cached --check
git commit -m "feat(telemetry): enforce closed observation records"
```

---

### Task 3: Route Every Monitor Sink Through One Projected Payload

**Files:**
- Modify: `api/monitor.py:10-258`
- Modify: `tests/unit/test_monitor_sanitization.py`
- Create: `tests/integration/test_observation_delivery.py`
- Modify: `tests/integration/test_run_auxiliary_isolation.py:134-235`

**Interfaces:**
- Consumes: `projector.monitor_event()`, `projector.descriptor()`, and safe `TelemetryRecord`.
- Produces: one `dra.monitor-event.v1` payload shared by WebSocket and `stream_writer`; console emits only fixed messages.

- [ ] **Step 1: Replace old sanitization expectations with closed-descriptor RED tests**

Retain the compatibility name but lock its new semantics:

```python
from api.monitor import sanitize_args


def test_sanitize_args_is_closed_descriptor_compatibility_alias():
    marker = {"query": "OBS_MARKER", "nested": {"secret": "OBS_MARKER"}}
    assert sanitize_args(marker) == {
        "present": True,
        "kind": "mapping",
        "top_level_item_count": 2,
        "count_capped": False,
    }
```

Update the capturing monitor override to accept the live `_emit` signature including `run_id` and `segment_id`. Assert reporter outputs contain descriptors, fixed fields, stable codes, and no `path`, `output_path`, `error_message`, raw result, query, or unknown key.

- [ ] **Step 2: Write identical-marker cross-sink RED integration test**

```python
import asyncio
import builtins
import json

import pytest


@pytest.mark.asyncio
async def test_same_marker_is_absent_from_every_observation_sink(monkeypatch, capsys):
    import api.monitor as monitor_module
    from agent.telemetry import collector
    from api.context import (
        reset_execution_context,
        set_run_context,
        set_segment_context,
        set_thread_context,
    )

    marker = "OBS_MARKER_SQL_RAGFLOW_PATH_" + "x" * 4096
    websocket_payloads = []
    stream_payloads = []

    class FakeManager:
        def get_loop(self):
            return asyncio.get_running_loop()

        async def send_to_run(self, payload, run_id):
            websocket_payloads.append(payload)

    class Runtime:
        def stream_writer(self, payload):
            stream_payloads.append(payload)

    monkeypatch.setattr(monitor_module.monitor, "websocket_manager", FakeManager())
    monkeypatch.setattr(builtins, "runtime", Runtime(), raising=False)
    thread_token = set_thread_context("shared-thread")
    run_token = set_run_context("run-marker")
    segment_token = set_segment_context("run-marker-seg-000")
    try:
        value = {
            "query": marker,
            "nested": {"secret": marker},
            "rows": [marker],
            "answer": marker,
            "output_path": "/private/" + marker,
        }
        monitor_module.monitor.report_start("tavily_search", value)
        monitor_module.monitor.report_end(
            "tavily_search",
            result=value,
            error=marker,
            error_type="RuntimeError",
        )
        assert value["query"] == marker
    finally:
        reset_execution_context(run_token, thread_token, segment_token)
        del builtins.runtime

    await asyncio.sleep(0)
    records = collector.get_by_run("run-marker")
    serialized = json.dumps(
        {
            "websocket": websocket_payloads,
            "stream": stream_payloads,
            "telemetry": [vars(record) for record in records],
            "console": capsys.readouterr().out,
        },
        default=str,
    )
    assert marker not in serialized
    assert websocket_payloads == stream_payloads
    assert all(item["run_id"] == "run-marker" for item in websocket_payloads)
    collector.clear_run("run-marker")
```

- [ ] **Step 3: Write failure-isolation RED tests**

Patch each sink independently to raise `RuntimeError("OBS_MARKER")`. Assert `report_end()` returns normally, the other sinks still receive a safe event, the console does not contain the exception text, and start-time state is cleaned. Separately pass hostile result objects and assert their magic methods are not called.

- [ ] **Step 4: Run Task 3 RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_monitor_sanitization.py \
  tests/integration/test_observation_delivery.py \
  tests/integration/test_run_auxiliary_isolation.py::test_monitor_isolates_same_tool_timing_and_routes_by_run \
  tests/integration/test_run_auxiliary_isolation.py::test_connection_manager_keeps_two_run_channels_for_same_thread \
  tests/integration/test_run_auxiliary_isolation.py::test_run_websocket_resolves_run_identity
```

Expected: FAIL because current payloads/messages contain raw values and sink errors are interpolated.

- [ ] **Step 5: Implement project-once delivery and fixed fallbacks**

Keep `_emit` call compatibility but ignore its `message`:

```python
def _emit(
    self,
    event_type: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    thread_id: str | None = None,
    run_id: str | None = None,
    segment_id: str | None = None,
):
    target_thread_id = thread_id or get_thread_context()
    target_run_id = run_id or get_run_context()
    target_segment_id = segment_id or get_segment_context()
    payload = projector.monitor_event(
        event_type=event_type,
        data=data,
        thread_id=target_thread_id,
        run_id=target_run_id,
        segment_id=target_segment_id,
        timestamp=datetime.datetime.now().isoformat(),
    )
    if payload is None:
        print("\n[Monitor] Observation projection rejected")
        return
```

Send the same `payload` object to `_schedule_websocket_send` and `builtins.runtime.stream_writer`. Catch each sink separately and print only:

```text
[Monitor] WebSocket delivery failed
[Monitor] stream_writer delivery failed
```

Print successful events as:

```python
print(f"\n[Monitor] {payload['message']}")
```

Reporter rules:

- `report_start` / `report_tool`: keep signatures, pass raw `args` only to projector descriptor.
- `report_end(tool_name, result=None, error=None, error_type=None)`: compute duration; create `TelemetryRecord` inside `try/except`; emit safe data even if collector fails.
- `report_assistant`: retain signature, but projector closes both label and args.
- `report_task_result`: never truncate or copy content; pass value only for descriptor projection.
- `report_task_finalized`: preserve current arguments; emit `output_present=output_path is not None`; discard `output_path` and raw `error_message`.
- `report_session_dir`: emit `workspace_created=path is not None`; never emit the path.
- `report_retry(service_name, attempt, max_retries, error=None, error_type=None)`: retain legacy `error`, never inspect it, emit `retryable_failure`.
- `report_cache_hit`: projector closes `tool_name`; preserve event selection by `cached`.
- `api.server._mark_run_timeout`: keep its `_emit` routing call; projector replaces the interpolated message with the fixed timeout message.

- [ ] **Step 6: Run Task 3 GREEN**

Run the Step 4 command again.

Expected: PASS; WebSocket and `stream_writer` payloads are identical and route identity is unchanged.

- [ ] **Step 7: Commit Task 3**

```bash
git add \
  api/monitor.py \
  tests/unit/test_monitor_sanitization.py \
  tests/integration/test_observation_delivery.py \
  tests/integration/test_run_auxiliary_isolation.py
git diff --cached --check
git commit -m "feat(monitor): project privacy-safe observation events"
```

---

### Task 4: Convert Live Call Sites To Closed Aliases And Stable Codes

**Files:**
- Modify: `agent/run_result.py:338-355`
- Modify: `tools/retry_utils.py:62-91`
- Modify: `tools/mysql_tools.py:101-220`
- Modify: `tools/ragflow_tools.py:50-200`
- Modify: `tools/tavily_tools.py:102-128`
- Modify: `tests/unit/test_agent_run_result.py`
- Modify: `tests/unit/test_retry_utils.py`
- Modify: `tests/unit/test_mysql_security.py`
- Modify: `tests/unit/test_ragflow_tools.py`
- Modify: `tests/unit/test_tavily_tools.py`

**Interfaces:**
- Consumes: Task 3 reporter signatures and closed aliases/codes.
- Produces: no raw caller label/error at a known call site and byte-for-byte unchanged model/tool returns.

Exact call-site aliases:

| File and symbol | Current display/model-derived label | Required alias |
| --- | --- | --- |
| `agent.run_result.process_stream_chunk` task call | `args["subagent_type"]` | `task_subagent` |
| `tools.mysql_tools.list_sql_tables` | `数据库获取表名工具！` | `mysql_list_tables` |
| `tools.mysql_tools.get_table_data` | `数据库内容浏览工具` | `mysql_table_data` |
| `tools.mysql_tools.execute_sql_query` | `数据库查询工具` | `mysql_query` |
| `tools.ragflow_tools.get_assistant_list` | `RAGFlow助手列表查询` | `ragflow_assistant_list` |
| `tools.ragflow_tools.create_ask_delete` | `RAGFlow助手提问工具` | `ragflow_question` |
| `tools.tavily_tools._internet_search_impl` | `网络搜索工具` | `tavily_search` |
| `tools.tavily_tools.search_with_dedup` | existing `tavily_search_dedup` | unchanged |

Exact error mapping:

| Condition | Code | `error_type` |
| --- | --- | --- |
| missing RAGFlow configuration | `configuration_missing` | `None` |
| invalid table name or SQL type | `input_invalid` | `None` |
| RAGFlow assistant not found | `resource_not_found` | `None` |
| caught `TimeoutError` / `asyncio.TimeoutError` | `timeout` | exact exception class name |
| caught `ConnectionError` / `OSError`, pool or connection unavailable | `service_unavailable` | exact caught class name when available |
| other caught exception | `execution_failed` | exact caught class name |
| retry notification after a retryable exception | `retryable_failure` | exact exception class name |

- [ ] **Step 1: Write call-site RED assertions**

Add tests that patch reporter methods and assert exact calls, for example:

```python
report_end.assert_called_once_with("tavily_search", expected)
```

For timeout:

```python
report_end.assert_called_once_with(
    "tavily_search",
    error="timeout",
    error_type="TimeoutError",
)
```

For `process_stream_chunk`, retain the model-supplied marker in the source message but assert:

```python
assert monitor.assistant_calls == [
    ("task_subagent", {"desc": "private model description OBS_MARKER"})
]
assert accumulator.assistant_calls == 1
```

The reporter/projector integration test proves the description becomes a descriptor, while this test proves the accumulator behavior is unchanged.

- [ ] **Step 2: Add unchanged-return tests**

For every tool family, capture the exact return before asserting monitor calls:

```python
result = tavily_tools.internet_search.invoke({"query": "OBS_MARKER"})
assert result == expected
```

Use analogous existing deterministic fixtures for MySQL validation and RAGFlow answers. Add a parameterized monitor test for exact `str`, `dict`, and `bytes` values:

```python
@pytest.mark.parametrize("value", ["text", {"key": "value"}, b"raw-bytes"])
def test_reporting_does_not_mutate_model_visible_value(value):
    original = value.copy() if type(value) is dict else value
    monitor.report_end("tavily_search", result=value)
    assert value == original
```

- [ ] **Step 3: Run call-site RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_agent_run_result.py \
  tests/unit/test_retry_utils.py \
  tests/unit/test_mysql_security.py \
  tests/unit/test_ragflow_tools.py \
  tests/unit/test_tavily_tools.py
```

Expected: FAIL because current call sites pass display/model labels and raw error strings.

- [ ] **Step 4: Apply exact aliases and errors**

Implementation details:

- In `process_stream_chunk`, call `monitor.report_assistant("task_subagent", {"desc": args.get("description")})`; do not change `last_agent_text`, task results, packet parsing, Evidence extraction, or diagnostics.
- In MySQL tools, define the three module constants and replace every paired start/end label consistently. Return all existing error/result strings unchanged. Map validation failures to `input_invalid`, pool/string connection failures to `service_unavailable`, and caught exceptions to `execution_failed` with `type(exc).__name__`.
- In RAGFlow tools, define the two tool aliases. Change service names from hyphenated display values to `ragflow_list`, `ragflow_find_chat`, `ragflow_create_session`, and `ragflow_ask`. Remove the duplicate raw-answer `monitor.report_tool` block at current lines 174-177 because `report_end("ragflow_question", full_answer)` already emits the result descriptor; do not change `full_answer` or cleanup.
- In Tavily, use `tavily_search` for every start/end call. Keep the filtered result dict and returned error strings unchanged.
- In `retry_async`, replace `error=str(last_exception)` with:

```python
error="retryable_failure",
error_type=type(last_exception).__name__ if last_exception is not None else None,
```

Do not change attempts, wait calculation, sleeps, exception propagation, or retry budgets.

- [ ] **Step 5: Run Task 4 GREEN and model/Evidence regressions**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_agent_run_result.py \
  tests/unit/test_retry_utils.py \
  tests/unit/test_mysql_security.py \
  tests/unit/test_ragflow_tools.py \
  tests/unit/test_tavily_tools.py \
  tests/integration/test_run_result_api.py \
  tests/unit/test_run_result_service.py
```

Expected: PASS with existing tool values, canonical result behavior, and Evidence behavior unchanged.

- [ ] **Step 6: Commit Task 4**

```bash
git add \
  agent/run_result.py \
  tools/retry_utils.py \
  tools/mysql_tools.py \
  tools/ragflow_tools.py \
  tools/tavily_tools.py \
  tests/unit/test_agent_run_result.py \
  tests/unit/test_retry_utils.py \
  tests/unit/test_mysql_security.py \
  tests/unit/test_ragflow_tools.py \
  tests/unit/test_tavily_tools.py
git diff --cached --check
git commit -m "fix(observation): close tool and retry call sites"
```

---

### Task 5: Publish The Observation Reference And Documentation Contract

**Files:**
- Create: `docs/reference/observation-contract.md`
- Modify: `docs/reference/api-contract.md:177-195`
- Modify: `docs/reference/data-models.md:180-198`
- Modify: `docs/README.md:33-55`
- Modify: `CHANGELOG.md:5-7`
- Modify: `tests/unit/test_documentation_contracts.py`

**Interfaces:**
- Consumes: final event/data/error/descriptor tables from Tasks 1-4.
- Produces: public documentation that describes implemented behavior without claiming release, deployment, generic DLP, or consumer adoption.

- [ ] **Step 1: Write documentation contract RED test**

```python
def test_privacy_safe_observation_contract_is_documented_and_indexed() -> None:
    reference = (
        PROJECT_ROOT / "docs/reference/observation-contract.md"
    ).read_text(encoding="utf-8")
    api_contract = (
        PROJECT_ROOT / "docs/reference/api-contract.md"
    ).read_text(encoding="utf-8")
    data_models = (
        PROJECT_ROOT / "docs/reference/data-models.md"
    ).read_text(encoding="utf-8")
    docs_index = (PROJECT_ROOT / "docs/README.md").read_text(encoding="utf-8")
    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for phrase in (
        "dra.monitor-event.v1",
        "dra.telemetry-record.v1",
        "configuration_missing",
        "retryable_failure",
        "10_000",
        "unknown fields fail closed",
        "Telemetry remains process-local diagnostic state",
        "does not claim generic DLP",
    ):
        assert phrase in reference
    for event in (
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
        assert f"`{event}`" in api_contract
    assert '"schema": "dra.telemetry-record.v1"' in data_models
    assert "Observation Contract" in docs_index
    assert "privacy-safe observation" in changelog.lower()
```

- [ ] **Step 2: Run docs RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q \
  tests/unit/test_documentation_contracts.py::test_privacy_safe_observation_contract_is_documented_and_indexed
```

Expected: FAIL because the observation reference and completed matrices do not exist.

- [ ] **Step 3: Write the public reference and update existing docs**

`docs/reference/observation-contract.md` must include:

1. purpose and application/framework authority boundary;
2. exact monitor envelope and all eleven event data schemas;
3. exact descriptor table and `10_000` cap;
4. exact error code list and ASCII `error_type`;
5. fixed messages and closed label/sentinel behavior;
6. telemetry record schema and process-local/non-authoritative status;
7. fail-closed and best-effort transport behavior;
8. in-place compatibility and canonical-result migration for raw consumers;
9. non-claims from spec section 11;
10. no provider, credential, live-data, Docker, schema, dependency, release, or consumer-upgrade claim.

Update the API event list to a complete event/data table. Update the telemetry data model example with `schema` and `error_type`. Add one Reference link in `docs/README.md`. Add an `Unreleased` changelog section describing the security hardening, unchanged application authority, and changed raw `args`/`result`/`error` semantics.

- [ ] **Step 4: Run docs GREEN and presentation checks**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_public_truth_documentation.py \
  tests/unit/test_final_presentation_audit.py
python scripts/final_presentation_audit.py --root .
git diff --check
```

Expected: PASS with zero presentation violations.

- [ ] **Step 5: Commit Task 5**

```bash
git add \
  docs/reference/observation-contract.md \
  docs/reference/api-contract.md \
  docs/reference/data-models.md \
  docs/README.md \
  CHANGELOG.md \
  tests/unit/test_documentation_contracts.py
git diff --cached --check
git commit -m "docs(observation): document privacy-safe contracts"
```

---

### Task 6: Run Final Provider-Free Verification And Hand Off Serial Execution

**Files:**
- Verify only; no planned file modification.

**Interfaces:**
- Consumes: Tasks 1-5 committed state.
- Produces: one reviewed branch state ready for independent pre-PR review.

- [ ] **Step 1: Verify exact planned file scope**

Run:

```bash
git diff --name-only "$(git merge-base HEAD main)"..HEAD
```

Expected: only the files in **Exact Planned File Map**. Any unplanned authority/DB/dependency/consumer file is a hard stop.

- [ ] **Step 2: Run focused observation pack**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_observation_contract.py \
  tests/unit/test_monitor_sanitization.py \
  tests/unit/test_telemetry.py \
  tests/unit/test_telemetry_integration.py \
  tests/unit/test_retry_utils.py \
  tests/unit/test_agent_run_result.py \
  tests/unit/test_mysql_security.py \
  tests/unit/test_ragflow_tools.py \
  tests/unit/test_tavily_tools.py \
  tests/integration/test_observation_delivery.py \
  tests/integration/test_run_auxiliary_isolation.py \
  tests/integration/test_run_result_api.py \
  tests/unit/test_run_result_service.py
```

Expected: PASS.

- [ ] **Step 3: Run the complete Context Reliability pack**

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q \
  tests/unit/test_agent_evaluation_context.py \
  tests/unit/test_deepagents_harness.py::test_locked_native_summarizer_profile_forces_coordinator_summary \
  tests/integration/test_context_reliability_regression.py
```

Expected: PASS with paired persisted application outcomes equivalent.

- [ ] **Step 4: Run documentation and presentation verification**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_public_truth_documentation.py \
  tests/unit/test_final_presentation_audit.py
python scripts/final_presentation_audit.py --root .
git diff --check
```

Expected: PASS and `{"status": "ok", "violations": []}`.

- [ ] **Step 5: Run non-Docker full suite and backend CI-parity commands**

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_dispatch_reconciliation_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_failure_cause_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/secure_local_runtime_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/bounded_live_producer_proof.py check
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m "not docker"
```

Expected: all commands exit zero. Do not run the local Docker lane.

- [ ] **Step 6: Run frontend CI parity without changing frontend files**

```bash
cd frontend
npm ci
npm run test
npm run lint
npm run build
cd ..
```

Expected: PASS with no tracked frontend diff. If dependency installation requires unauthorized network/tool changes, record the exact skipped gate instead of changing dependencies.

- [ ] **Step 7: Run executable content-leak and scope scans**

```bash
if rg -n -i \
  'C[a]reer|job[-_ ]?search|private[-_ ]?schedul|review[_]owner[_]key|return[_]target|source[_]thread[_]id|task[_]label|/U[s]ers/|019f[0-9a-f-]{20,}' \
  api/observation_contract.py \
  api/monitor.py \
  agent/telemetry.py \
  docs/reference/observation-contract.md \
  docs/reference/api-contract.md \
  docs/reference/data-models.md \
  docs/README.md \
  CHANGELOG.md; then
  echo "PUBLIC_NEUTRAL_SCAN_FAILED"
  exit 1
else
  echo "PUBLIC_NEUTRAL_SCAN_OK"
fi

if rg -n \
  'OBS_MARKER|SELECT secret FROM private_table|/private/OBS_MARKER' \
  docs/reference/observation-contract.md \
  docs/reference/api-contract.md \
  docs/reference/data-models.md \
  CHANGELOG.md; then
  echo "SYNTHETIC_MARKER_DOC_SCAN_FAILED"
  exit 1
else
  echo "SYNTHETIC_MARKER_DOC_SCAN_OK"
fi
```

Expected: both scans print `OK`.

- [ ] **Step 8: Confirm clean state and hosted-only gates**

```bash
git status --short --branch
git log --oneline "$(git merge-base HEAD main)"..HEAD
```

Expected: clean worktree and one semantic commit per Task 1-5. Hosted CI must later run the reviewed PR head through `Backend Tests`, `Frontend Demo Console`, `Secure Local Runtime Containers`, and `CodeQL`. Do not claim those hosted gates before they run.

## Plan Self-Review

### Spec Section To Task Mapping

| Spec section | Implementing task(s) |
| --- | --- |
| 1. Goal | Tasks 1-4; verified in Task 6 |
| 2. Architecture and authority boundary | Task 1 projector, Task 3 sink integration, Task 6 authority regressions |
| 3. WebSocket monitor-event contract | Tasks 1 and 3; documented in Task 5 |
| 4. Bounded argument and result descriptors | Task 1 |
| 5. Stable error contract | Tasks 1, 2, and 4 |
| 6. Telemetry API contract | Task 2; documented in Task 5 |
| 7. Fail-closed behavior | Tasks 1 and 3 |
| 8. Compatibility strategy | Tasks 3-5 |
| 9. TDD and verification contract | RED/GREEN in Tasks 1-5; full evidence in Task 6 |
| 10. Documentation impact | Task 5 |
| 11. Non-claims | Global constraints and Task 5 |
| 12. Stop conditions and release posture | Global hard stop and Task 6 hosted-only handoff |

### Type And Symbol Consistency Findings

- `ObservationProjector.descriptor()` is the only value-shape function used by event fields.
- `ObservationProjector.monitor_event()` is the only monitor envelope constructor.
- `ObservationProjector.telemetry_fields()` is used by both `TelemetryRecord` and `TelemetryCollector`.
- `ToolMonitor.report_end(error_type=None)` and `ToolMonitor.report_retry(error_type=None)` use the same error-type validation.
- Aliases in Task 4 exactly match the projector allowlists and documentation tables.
- `TelemetryRecord.schema` and `_serialize_telemetry()` both use `dra.telemetry-record.v1`.
- WebSocket and `stream_writer` consume the same projected dict; console consumes only its fixed `message`.
- No task changes a tool function's returned `str`, `dict`, or `bytes`, or the `process_stream_chunk` accumulation/Evidence path.

### Completeness Scan

Before implementation approval, run:

```bash
plan='docs/superpowers/plans/2026-07-26-privacy-safe-observation-contract-implementation-plan.md'
if rg -n -i \
  'T[B]D|T[O]DO|implement[ ]later|fill[ ]in[ ]details|add[ ]appropriate[ ]error[ ]handling|write[ ]tests[ ]for[ ]the[ ]above|similar[ ]to[ ]Task[ ][0-9]+' \
  "$plan"; then
  echo "PLAN_COMPLETENESS_SCAN_FAILED"
  exit 1
else
  echo "PLAN_COMPLETENESS_SCAN_OK"
fi
```

Expected: `PLAN_COMPLETENESS_SCAN_OK`.

### Diagnosis And Navigation

| Observed symptom | Owning layer | First exact symbols/tests to inspect | Prohibited false fix |
| --- | --- | --- | --- |
| Marker appears in WebSocket or `stream_writer` | Observation projection/delivery | `api.observation_contract.ObservationProjector.monitor_event`, `api.monitor.ToolMonitor._emit`, `tests/integration/test_observation_delivery.py` | Do not rewrite `ToolMessage`, add raw compatibility mode, or filter only known secret names. |
| Marker appears in telemetry API | Telemetry retention/projection | `agent.telemetry.TelemetryRecord.__post_init__`, `TelemetryCollector.record`, `api.server._serialize_telemetry`, telemetry tests | Do not hide only the API field while retaining raw error internally. |
| Arbitrary tool/assistant/service label appears | Closed label mapping | projector allowlists, `agent.run_result.process_stream_chunk`, exact Task 4 call sites | Do not accept arbitrary strings because they are short or ASCII. |
| Wrong error code | Call-site classification | Task 4 error table and caught exception class at the exact tool/retry site | Do not guess from exception text or preserve the message for later classification. |
| Tool/model-visible result changes | Tool or Agent call site | exact failing tool test, `agent.run_result.process_stream_chunk`, run-result/Evidence tests | Do not use `wrap_tool_call`, `ToolMessage.artifact`, or observation descriptors as model results. |
| Event identity or run routing changes | Context/routing | `api.monitor.ToolMonitor._emit`, `_schedule_websocket_send`, `ConnectionManager`, run auxiliary isolation tests | Do not collapse `thread_id`/`run_id`, route through a global channel, or move identity authority to framework state. |
| Projection failure changes execution/retry | Best-effort reporter boundary | `ToolMonitor.report_*`, retry tests, observation delivery failure tests | Do not retry a tool because WebSocket/collector failed or let logging exceptions propagate. |
| Canonical result/Evidence drift | Application authority | run-result tests and Context Reliability pack | Do not make telemetry, LangGraph checkpoint, trace, or frontend state authoritative. |

## Execution Handoff

After this plan is approved, execute it only with `superpowers:executing-plans` in this existing isolated branch/worktree, serially from Task 1 through Task 6. Stop at every semantic commit for review, and stop immediately on any hard-stop condition. Do not use `superpowers:subagent-driven-development` for this shared projector/contract change.
