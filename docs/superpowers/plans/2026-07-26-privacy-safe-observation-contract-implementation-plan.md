# Privacy-Safe Observation Contract v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan serially, task by task, with a review checkpoint after every semantic commit. Do not use subagent-driven development for this shared-contract change. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace raw data in every in-scope project-owned observation sink
(WebSocket, existing LangGraph `stream_writer`, console, and retained
telemetry/API) with a closed, bounded, provider-free metadata contract without
changing model-visible tool values or application authority.

**Architecture:** Add one stateless application-layer `ObservationProjector`
in `api/observation_contract.py`. `ToolMonitor` projects one logical event
once, then sends value-equal independent fixed-depth built-in copies to
WebSocket and LangGraph `stream_writer`, writes only fixed console messages,
and separately creates a projector-validated `TelemetryRecord`. Telemetry
construction and collection reconstruct every field so direct internal
construction or mutation cannot bypass the contract or refresh timestamps.

**Tech Stack:** Python 3.11, FastAPI WebSocket transport, LangGraph `stream_writer`, dataclasses, pytest, existing in-process telemetry, and existing repository documentation/audit tooling. No new dependency, provider/model call, credential, live data, database migration, or Docker execution is permitted.

## Global Constraints

- Authority spec: `docs/superpowers/specs/2026-07-25-privacy-safe-observation-contract-design.md`.
- Keep execution serial because the projector, monitor, telemetry, call sites, and public contract share one schema and one set of labels.
- Preserve model-visible `ToolMessage` values and tool return values byte-for-byte.
- Preserve `ResearchRun`, Evidence, canonical result, artifact, review, delivery, and application-database authority.
- Preserve `/ws/runs/{run_id}`, `/api/telemetry/runs/{run_id}`, event names, identity/routing fields, and timestamp fields.
- Preserve the immutable `dra.downstream-consumer.v1` run
  status/result/Evidence boundary, `v0.1.6`, and Night Voyager's unchanged
  pinned consumption boundary. Raw observation `args`, `result`, and `error`
  semantics are intentionally hardened in place under `Unreleased`; do not
  claim compatibility for the entire `v0.1.6` diagnostic surface or claim
  that Night Voyager consumes observations.
- Preserve the database schema, dependencies, runtime budgets, and `VERSION`.
- Keep LangGraph `stream_writer` as transport only. Do not use `wrap_tool_call`, `ToolMessage.artifact`, framework trace, or checkpoint state as observation or business authority.
- Projection must be pure, total, bounded, non-throwing, content-depth independent, and free of provider, credential, database, filesystem, or model-context access.
- Do not recurse, call `repr()`, call `str()`, JSON-serialize caller values, call a custom `__len__`, or compute content hashes.
- Cap string, bytes, mapping, and sequence counts at `10_000`; report the cap with `count_capped=true`.
- Treat reporter labels, including `assistant_name`, `tool_name`, and `service_name`, as untrusted. Only closed call-site aliases may pass.
- Accept legacy raw `error=` arguments at reporter boundaries, discard their content immediately, and map unknown non-null values to `execution_failed`. Never classify exception text.
- Collector, projector, WebSocket, `stream_writer`, and console failures must
  not change a tool return, model-visible result, retry count/timing, or
  terminal outcome. Hosted tracing and general process logs are outside this
  contract.
- Project each logical event once, then give WebSocket and `stream_writer`
  independent fixed-depth copies. The envelopes and nested `data` must be
  value-equal and non-aliased, and mutation by one sink must not contaminate
  another.
- Normalize `(status, error, error_type)` through one helper. Never retain an
  `error_type` without a stable error; an error status without a code becomes
  `execution_failed`.
- Preserve exact valid bounded identities and timezone-aware timestamps. Never
  invoke magic methods while validating hostile identity, timestamp, number,
  path, or token-usage inputs.
- `docs/observability.md` remains the separate LangSmith operator boundary.
  Raw LangSmith inputs/outputs are not a fallback for closed telemetry.
- Do not add a raw compatibility endpoint, environment variable, unsafe flag, schema migration, dependency, Release, or consumer upgrade.
- Stop and request renewed architecture approval if implementation needs an authority/DB/dependency/consumer file not listed below, changes model-visible behavior, or requires an ADR.

### Execution Environment Gate

Before the first RED, select one already-authorized exact Python 3.11
interpreter and keep its resolved absolute path for every Python command:

```bash
PYTHON_BIN="${PYTHON_BIN:-$PWD/.venv/bin/python}"
case "$PYTHON_BIN" in
  /*) ;;
  *) echo "PYTHON_3_11_AUTHORITY_REQUIRED"; exit 1 ;;
esac
test -x "$PYTHON_BIN" || {
  echo "PYTHON_3_11_AUTHORITY_REQUIRED"
  exit 1
}
test "$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" = "3.11" || {
  echo "PYTHON_3_11_AUTHORITY_REQUIRED"
  exit 1
}
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -c \
  'import fastapi, langgraph, pydantic, pytest; print("PYTHON_3_11_ENVIRONMENT_OK")'
```

If this gate fails, stop and request environment authority. Do not use bare
Python 3.13, install packages, or access a package registry. Every Python
command below uses this same `"$PYTHON_BIN"` path.

At execution start, derive the implementation boundary from the latest commit
that touches this plan, which must be the final approved plan state:

```bash
PLAN_PATH='docs/superpowers/plans/2026-07-26-privacy-safe-observation-contract-implementation-plan.md'
IMPLEMENTATION_BASE="$(git log -1 --format=%H -- "$PLAN_PATH")"
test -n "$IMPLEMENTATION_BASE"
test "$(git status --porcelain)" = ""
git show --stat --oneline "$IMPLEMENTATION_BASE" -- "$PLAN_PATH"
```

Use `"$IMPLEMENTATION_BASE"..HEAD` for the implementation-only exact
allowlist. Verify the full branch from
`2c50f233c2cc1df4fe2818551e95ab98cd61ede5` separately as approved spec +
plan + implementation. Do not use merge-base alone for the implementation
allowlist.

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
| `api/monitor.py` | Modify | Project once, distribute independent safe copies, retain scheduled sends in lock-guarded pending inventories, use fixed console messages, and keep all reporting best effort. |
| `tests/unit/test_monitor_sanitization.py` | Modify | Replace redaction/truncation expectations with closed descriptor/event expectations, pending-inventory initialization/snapshots, and failure isolation. |
| `tests/integration/test_observation_delivery.py` | Create | Prove one marker cannot cross WebSocket, `stream_writer`, telemetry, or console while identities and returns remain unchanged. |
| `agent/run_result.py` | Modify | Replace model-provided assistant labels with the stable `task_subagent` alias while preserving accumulated content/Evidence. |
| `tools/retry_utils.py` | Modify | Pass stable retry code and exception class name without stringifying the exception. |
| `tools/mysql_tools.py` | Modify | Replace display labels and raw errors with exact aliases/codes while preserving returned strings. |
| `tools/ragflow_tools.py` | Modify | Replace observed tool display labels/raw errors, keep logger-only service labels, and remove the duplicate raw answer observation while preserving returned answers. |
| `tools/tavily_tools.py` | Modify | Replace display label/raw errors with the exact alias/codes while preserving returned dicts/strings. |
| `tests/unit/test_agent_run_result.py` | Modify | Lock assistant aliasing and unchanged task-result/Evidence behavior. |
| `tests/unit/test_retry_utils.py` | Modify | Lock retry error type metadata and unchanged retry behavior. |
| `tests/unit/test_mysql_security.py` | Modify | Add monitor alias/error-code assertions without a database connection. |
| `tests/unit/test_ragflow_tools.py` | Modify | Lock aliases/codes, no raw question/answer observation, and unchanged tool returns/cleanup. |
| `tests/unit/test_tavily_tools.py` | Modify | Lock aliases/codes, closed result observation, and unchanged returned result. |
| `docs/reference/observation-contract.md` | Create | Public observation schemas, descriptors, error codes, compatibility, authority, and non-claims. |
| `docs/observability.md` | Modify | Cross-link the closed application observation contract and prohibit raw LangSmith fallback; no tracing behavior change. |
| `docs/reference/api-contract.md` | Modify | Complete the WebSocket event matrix and closed telemetry response. |
| `docs/reference/data-models.md` | Modify | Replace the raw telemetry example with `dra.telemetry-record.v1`. |
| `docs/README.md` | Modify | Index the new observation reference. |
| `CHANGELOG.md` | Modify | Add the security hardening under `Unreleased`, with compatibility and non-claims. |
| `tests/unit/test_documentation_contracts.py` | Modify | Lock the observation reference, event matrix, telemetry model, index, changelog, and non-claims. |

**Hard stop:** The implementation may not modify any other production,
authority, persistence, migration, dependency, CI, release, `VERSION`,
frontend, or consumer file. `docs/observability.md` is allowed only for the
operator-boundary cross-link above. If a test demonstrates that another file
must change, preserve the RED evidence and request a new decision instead of
expanding this list.

## Live Symbol And Signature Map

The plan is based on these current symbols and preserves their non-observation behavior:

| Live symbol | Current/planned signature contract |
| --- | --- |
| `api.monitor.sanitize_args` | Current `sanitize_args(args: dict | None) -> dict | None`; planned compatibility signature `sanitize_args(args: object) -> dict[str, object]`, returning only `projector.descriptor(args)`. |
| `api.monitor.ToolMonitor.__new__` | Preserve singleton construction; every new/reset singleton initializes `_pending_lock`, `_pending_tasks`, and `_pending_futures` before it can schedule a send. |
| `api.monitor.ToolMonitor._emit` | Keep `_emit(self, event_type: str, message: str, data: Optional[Dict[str, Any]] = None, thread_id: str | None = None, run_id: str | None = None, segment_id: str | None = None)` so live callers remain source-compatible; ignore caller `message`. |
| `api.monitor.ToolMonitor._register_pending` | Add one lock-guarded helper that atomically registers a scheduled Task/Future and installs its consuming callback. |
| `api.monitor.ToolMonitor._consume_done` | Add one callback helper that consumes `exception()` and removes the completed object under `_pending_lock`. |
| `api.monitor.ToolMonitor._pending_snapshot` | Add a lock-guarded immutable snapshot for cleanup/tests; never iterate the live sets directly. |
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
- `ObservationProjector.normalize_error(self, *, status: object, error: object, error_type: object) -> tuple[str, str | None, str | None]`
- `ObservationProjector.monitor_event(self, *, event_type: object, data: object, thread_id: object, run_id: object, segment_id: object, timestamp: object) -> dict[str, object] | None`
- `ObservationProjector.telemetry_fields(self, *, thread_id: object, run_id: object, segment_id: object, agent_name: object, tool_name: object, duration_ms: object, status: object, error: object = None, error_type: object = None, timestamp: object, token_usage: object) -> dict[str, object]`
- module singleton: `projector = ObservationProjector()`

`normalize_error()` is the only error-normalization helper used by monitor
events and telemetry. Its exact matrix is:

| Input state | Output `(status, error, error_type)` |
| --- | --- |
| success + no error | `("success", None, None)` |
| error + no error | `("error", "execution_failed", None)` |
| any status + allowed error | `("error", exact_code, valid_type_or_None)` |
| any status + raw/unknown non-null error | `("error", "execution_failed", valid_type_or_None)` |
| success + no error + supplied error type | `("success", None, None)` |

Legacy raw-error arguments are accepted only at reporter/construction
boundaries and discarded during this normalization. No code classifies
exception messages.

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

Exact envelope closure:

| Field | Exact accepted input | Invalid result |
| --- | --- | --- |
| `thread_id` | exact `str` accepted unchanged by public `validate_thread_id`: `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` | `None` |
| `run_id` | exact `str` matching `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` | `None` |
| `segment_id` | exact `str` matching `^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$` | `None` |
| monitor `timestamp` | exact timezone-aware ISO `str`: `YYYY-MM-DDTHH:MM:SS`, optional fractional second, then `Z` or `+HH:MM` / `-HH:MM` | `"1970-01-01T00:00:00+00:00"` |
| retained `timestamp` | exact timezone-aware `datetime` with built-in `datetime.timezone` | `datetime(1970, 1, 1, tzinfo=timezone.utc)` |
| retained `token_usage` | exact internally valid `TokenUsageData` or `None` | `None` |

Exact valid values are returned unchanged. Validation reads only exact
built-in types and exact dataclass fields; it never coerces or stringifies
caller objects. Numeric event metadata accepts only exact finite `int`/`float`,
clamps to `0..10_000`, and never converts a known event into `None`, including
for arbitrarily large integers.

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
| `service_name` | `tavily` | `unknown_service` |
| tool telemetry `status` | `success`, `error` | `error` |
| run `previous_status` / final status | `pending`, `running`, `completed`, `completed_with_fallback`, `failed` | `failed` |

Reporter inputs never extend these sets. Adding an alias requires an explicit call-site change and contract test.

All eleven events have exact data-key sets:

| Event | Exact `data` keys |
| --- | --- |
| `session_created` | `workspace_created` |
| `tool_start` | `tool_name`, `args` |
| `tool_end` | `tool_name`, `status`, `duration_ms`, `result`, `error`, `error_type` |
| `assistant_call` | `assistant_name`, `args` |
| `task_result` | `result` |
| `task_finalized` | `status`, `fallback_used`, `output_present`, `error` |
| `retry_event` | `service_name`, `attempt`, `max_retries`, `error`, `error_type` |
| `cache_hit` | `tool_name`, `cached` |
| `cache_miss` | `tool_name`, `cached` |
| `run_timeout` | `timeout_seconds`, `previous_status`, `finalized_by_callback` |
| `error` | `error`, `error_type` |

`workspace_created` and `output_present` are true only when the originating
path is an exact non-empty built-in `str`. All other booleans use exact
`bool` checks. Unknown input keys are never copied.

## Serial Task Interfaces

| Task | Consumes | Produces |
| --- | --- | --- |
| 1 | Approved spec only | `projector` and its exact pure contract. |
| 2 | Task 1 `projector.telemetry_fields()` | Self-projecting `TelemetryRecord`, safe collector, closed API records. |
| 3 | Tasks 1-2 projector and telemetry | One projection copied independently to WebSocket/`stream_writer`; fixed safe console, best-effort sinks. |
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
- Produces: `ObservationProjector` and singleton `projector` with the four exact method signatures above.

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
"$PYTHON_BIN" -m pytest -q \
  tests/unit/test_observation_contract.py::test_descriptors_are_exact_non_recursive_and_capped \
  tests/unit/test_observation_contract.py::test_builtin_scalars_have_no_value_field
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'api.observation_contract'`.

- [ ] **Step 3: Write event, label, error, and totality RED tests**

```python
import json
from datetime import datetime, timezone

import pytest
from api.observation_contract import projector
from api.thread_ids import validate_thread_id


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
    assert projector.normalize_error(
        status="success", error=None, error_type="IgnoredType"
    ) == ("success", None, None)
    assert projector.normalize_error(
        status="error", error=None, error_type=None
    ) == ("error", "execution_failed", None)
    assert projector.normalize_error(
        status="success", error="timeout", error_type="TimeoutError"
    ) == ("error", "timeout", "TimeoutError")
    assert projector.normalize_error(
        status="error", error="SELECT secret FROM raw", error_type="Bad.Error"
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
            "tool_name", "status", "duration_ms", "result", "error", "error_type"
        },
        "assistant_call": {"assistant_name", "args"},
        "task_result": {"result"},
        "task_finalized": {"status", "fallback_used", "output_present", "error"},
        "retry_event": {
            "service_name", "attempt", "max_retries", "error", "error_type"
        },
        "cache_hit": {"tool_name", "cached"},
        "cache_miss": {"tool_name", "cached"},
        "run_timeout": {
            "timeout_seconds", "previous_status", "finalized_by_callback"
        },
        "error": {"error", "error_type"},
    }
    for event_type, keys in expected.items():
        payload = _event(event_type, {"future": "OBS_MARKER"})
        assert set(payload) == {
            "type", "schema", "event", "message", "data",
            "thread_id", "run_id", "segment_id", "timestamp",
        }
        assert set(payload["data"]) == keys
        json.dumps(payload, allow_nan=False)


def test_hostile_envelope_and_extreme_numbers_fail_closed():
    hostile = Hostile()
    payload = projector.monitor_event(
        event_type="run_timeout",
        data={
            "timeout_seconds": 10 ** 100_000,
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


@pytest.mark.parametrize(
    ("status", "error", "error_type", "expected"),
    [
        ("success", None, "IgnoredType", ("success", None, None)),
        ("error", None, None, ("error", "execution_failed", None)),
        ("success", "timeout", "TimeoutError", ("error", "timeout", "TimeoutError")),
        (
            "error", "raw OBS_MARKER", "Bad.Error",
            ("error", "execution_failed", None),
        ),
    ],
)
def test_monitor_and_telemetry_share_exact_error_matrix(
    status, error, error_type, expected
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
```

- [ ] **Step 4: Run event tests and verify RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q tests/unit/test_observation_contract.py
```

Expected: FAIL because the projector and closed schemas do not exist.

- [ ] **Step 5: Implement the projector with exact built-in checks**

Implement the constants and descriptor core exactly as follows, then implement each event branch by selecting only the fields named in the spec:

```python
from __future__ import annotations

from datetime import datetime, timezone
import math
import re

from agent.token_tracking import TokenUsageData
from api.thread_ids import validate_thread_id


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
ISO_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$",
    re.ASCII,
)
INVALID_TIMESTAMP_TEXT = "1970-01-01T00:00:00+00:00"
INVALID_TIMESTAMP = datetime(1970, 1, 1, tzinfo=timezone.utc)
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", re.ASCII)
SEGMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$", re.ASCII)
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
        frozenset({"tavily"}),
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
        if (
            type(value) is datetime
            and type(value.tzinfo) is timezone
        ):
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
            or value.total_tokens != value.prompt_tokens + value.completion_tokens
            or type(value.model) is not str
            or not 1 <= len(value.model) <= 128
            or type(value.cost) is not float
            or not math.isfinite(value.cost)
            or value.cost < 0
        ):
            return None
        return value

    def normalize_error(
        self, *, status: object, error: object, error_type: object
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
            if type(error_type) is str and ERROR_TYPE_RE.fullmatch(error_type)
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
                    "tool_name": self._label("tool_name", source.get("tool_name")),
                    "args": self.descriptor(source.get("args")),
                }
            elif event_type == "tool_end":
                status, code, safe_type = self.normalize_error(
                    status=source.get("status"),
                    error=source.get("error"),
                    error_type=source.get("error_type"),
                )
                projected_data = {
                    "tool_name": self._label("tool_name", source.get("tool_name")),
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
                        "assistant_name", source.get("assistant_name")
                    ),
                    "args": self.descriptor(source.get("args")),
                }
            elif event_type == "task_result":
                projected_data = {
                    "result": self.descriptor(source.get("result")),
                }
            elif event_type == "task_finalized":
                output_path = source.get("output_path")
                run_status = self._label("run_status", source.get("status"))
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
                        "service_name", source.get("service_name")
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
```

The implementation audit must confirm that the concrete code above:

1. starts with `source = data if type(data) is dict else {}`;
2. uses a closed event-to-message lookup;
3. returns `None` when the event key is absent;
4. builds a new event-specific `projected_data` dict without iterating caller keys;
5. normalizes labels through the exact allowlists above;
6. clamps exact numeric metadata to `0..10_000` without overflowing;
7. reuses `validate_thread_id`, applies the explicit run/segment patterns,
   preserves exact valid identities and timestamps, and otherwise uses the
   documented `None`/UTC sentinel values;
8. preserves only an exact internally valid `TokenUsageData | None`;
9. uses the single coherent error-tuple helper for monitor and telemetry;
10. catches every exception and returns `None` or the fixed safe telemetry fallback;
11. produces JSON-serializable monitor envelopes with no NaN or Infinity.

- [ ] **Step 6: Run Task 1 GREEN**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q tests/unit/test_observation_contract.py
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


def test_record_preserves_exact_timestamp_and_valid_token_usage():
    from datetime import datetime, timezone
    from agent.telemetry import TelemetryRecord
    from agent.token_tracking import TokenUsageData

    timestamp = datetime(2026, 7, 26, 1, 2, 3, tzinfo=timezone.utc)
    usage = TokenUsageData(
        prompt_tokens=2, completion_tokens=3, model="fixture", cost=0.0
    )
    record = TelemetryRecord(
        thread_id="thread-a",
        run_id="run-a",
        segment_id="run-a-seg-000",
        agent_name="main",
        tool_name="tavily_search",
        duration_ms=1.0,
        status="success",
        token_usage=usage,
        timestamp=timestamp,
    )
    assert record.timestamp is timestamp
    assert record.token_usage is usage


def test_invalid_direct_timestamp_and_token_usage_use_sentinels():
    from datetime import datetime, timezone
    from agent.telemetry import TelemetryRecord

    record = TelemetryRecord(
        thread_id=object(),
        agent_name="main",
        tool_name="tavily_search",
        duration_ms=10 ** 100_000,
        status="error",
        error=None,
        error_type="RuntimeError",
        token_usage=object(),
        timestamp=object(),
    )
    assert record.thread_id is None
    assert record.timestamp == datetime(1970, 1, 1, tzinfo=timezone.utc)
    assert record.token_usage is None
    assert (record.status, record.error, record.error_type) == (
        "error", "execution_failed", None
    )


def test_collector_reprojects_mutation_without_refreshing_timestamp():
    from datetime import datetime, timezone
    from agent.telemetry import TelemetryCollector, TelemetryRecord

    original_timestamp = datetime(2026, 7, 26, tzinfo=timezone.utc)
    record = TelemetryRecord(
        thread_id="thread-a",
        run_id="run-a",
        agent_name="main",
        tool_name="tavily_search",
        duration_ms=1.0,
        status="success",
        timestamp=original_timestamp,
    )
    object.__setattr__(record, "error", "OBS_MARKER")
    object.__setattr__(record, "error_type", "RuntimeError")
    collector = TelemetryCollector()
    collector.record(record)
    stored = collector.get_by_run("run-a")[0]
    assert stored is not record
    assert stored.timestamp is original_timestamp
    assert (stored.status, stored.error, stored.error_type) == (
        "error", "execution_failed", "RuntimeError"
    )
    assert "OBS_MARKER" not in repr(vars(stored))
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

Add
`test_telemetry_api_serializes_success_error_and_invalid_timestamp_sentinel`
to the same authenticated integration module. Construct one success record,
one stable error record, and one record with `timestamp=object()`. Assert every
JSON object has exactly:

```python
{
    "schema", "thread_id", "run_id", "segment_id", "agent_name",
    "tool_name", "duration_ms", "status", "error", "error_type", "timestamp",
}
```

Assert the invalid timestamp serializes exactly as
`"1970-01-01T00:00:00+00:00"`, the coherent error tuples match the shared
matrix, and the endpoint remains protected by the existing `X-API-Key`
fixture.

- [ ] **Step 3: Run telemetry RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q \
  tests/unit/test_telemetry.py \
  tests/unit/test_telemetry_integration.py \
  tests/integration/test_run_auxiliary_isolation.py::test_telemetry_api_isolates_two_runs_in_same_thread \
  tests/integration/test_run_auxiliary_isolation.py::test_telemetry_api_serializes_success_error_and_invalid_timestamp_sentinel
```

Expected: FAIL because raw errors and labels are retained and the API has no schema/error type.

- [ ] **Step 4: Implement self-projecting records and safe collection**

Use a frozen dataclass and re-project during `__post_init__`:

```python
@dataclass(frozen=True)
class TelemetryRecord:
    thread_id: str | None
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
            timestamp=self.timestamp,
            token_usage=self.token_usage,
        )
        for name, value in safe.items():
            object.__setattr__(self, name, value)
```

At the start of `TelemetryCollector.record`:

```python
if type(record) is not TelemetryRecord:
    return
```

Then create one new exact `TelemetryRecord` by naming every field explicitly:

```python
safe_record = TelemetryRecord(
    thread_id=record.thread_id,
    run_id=record.run_id,
    segment_id=record.segment_id,
    agent_name=record.agent_name,
    tool_name=record.tool_name,
    duration_ms=record.duration_ms,
    status=record.status,
    error=record.error,
    error_type=record.error_type,
    token_usage=record.token_usage,
    timestamp=record.timestamp,
)
```

Never use `vars(record)`, `dataclasses.replace`, or `**record.__dict__`.
This second projection closes monkeypatched/mutated inputs while preserving the
original exact valid timestamp and token usage. If both reconstructed
`run_id` and `thread_id` are `None`, reject retention with a fixed local
diagnostic. Keep the 500-record per-execution FIFO cap, restart loss, and
run/thread isolation unchanged; there is no replay or backfill.

Update the existing 500-capacity test to use the registered
`tavily_search` alias for every record and distinct exact UTC timestamps.
Assert the first timestamp is evicted and the 500th remains; do not depend on
arbitrary dynamic tool labels that now correctly become `unknown_tool`.

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
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q \
  tests/unit/test_telemetry.py \
  tests/unit/test_telemetry_integration.py \
  tests/integration/test_run_auxiliary_isolation.py::test_telemetry_api_isolates_two_runs_in_same_thread \
  tests/integration/test_run_auxiliary_isolation.py::test_telemetry_api_serializes_success_error_and_invalid_timestamp_sentinel \
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

### Task 3: Route Every Monitor Sink Through One Projection And Independent Copies

**Files:**
- Modify: `api/monitor.py:10-258`
- Modify: `tests/unit/test_monitor_sanitization.py`
- Create: `tests/integration/test_observation_delivery.py`
- Modify: `tests/integration/test_run_auxiliary_isolation.py:134-235`

**Interfaces:**
- Consumes: `projector.monitor_event()`, `projector.descriptor()`, and safe `TelemetryRecord`.
- Produces: one logical `dra.monitor-event.v1` projection, independent
  value-equal fixed-depth copies for WebSocket and `stream_writer`, and fixed
  non-throwing console output.

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


async def _settle_monitor_pending(monitor):
    tasks, futures = monitor._pending_snapshot()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    if futures:
        await asyncio.gather(
            *(asyncio.wrap_future(future) for future in futures),
            return_exceptions=True,
        )
    assert monitor._pending_snapshot() == ((), ())


@pytest.mark.asyncio
async def test_same_marker_is_absent_from_every_observation_sink(
    monkeypatch, capsys
):
    import api.monitor as monitor_module
    from agent.telemetry import collector
    from api.context import (
        reset_execution_context,
        set_run_context,
        set_segment_context,
        set_thread_context,
    )

    marker = "OBS_MARKER_SQL_RAGFLOW_PATH_" + "x" * 4096
    websocket_snapshots = []
    websocket_ids = []
    stream_payloads = []
    stream_ids = []
    loop_errors = []
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: loop_errors.append(context))

    class FakeManager:
        def get_loop(self):
            return asyncio.get_running_loop()

        async def send_to_run(self, payload, run_id):
            websocket_ids.append((id(payload), id(payload["data"])))
            websocket_snapshots.append(
                json.loads(json.dumps(payload, allow_nan=False))
            )
            payload["data"]["tool_name"] = "mutated_by_websocket"

    class Runtime:
        def stream_writer(self, payload):
            stream_payloads.append(payload)
            stream_ids.append((id(payload), id(payload["data"])))

    monkeypatch.setattr(monitor_module.monitor, "websocket_manager", FakeManager())
    monkeypatch.setattr(builtins, "runtime", Runtime(), raising=False)
    thread_token = set_thread_context("shared-thread")
    run_token = set_run_context("run-marker")
    segment_token = set_segment_context("run-marker-seg-000")
    try:
        for _ in range(2):
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
        await _settle_monitor_pending(monitor_module.monitor)
        records = collector.get_by_run("run-marker")
        captured = capsys.readouterr()
        serialized = json.dumps(
            {
                "websocket": websocket_snapshots,
                "stream": stream_payloads,
                "telemetry": [vars(record) for record in records],
                "stdout": captured.out,
                "stderr": captured.err,
            },
            default=str,
            allow_nan=False,
        )
        assert marker not in serialized
        assert websocket_snapshots == stream_payloads
        assert websocket_ids != stream_ids
        assert all(
            web_outer != stream_outer and web_data != stream_data
            for (web_outer, web_data), (stream_outer, stream_data)
            in zip(websocket_ids, stream_ids, strict=True)
        )
        assert all(
            item["data"].get("tool_name") != "mutated_by_websocket"
            for item in stream_payloads
        )
        assert not loop_errors
    finally:
        reset_execution_context(run_token, thread_token, segment_token)
        collector.clear_run("run-marker")
        await _settle_monitor_pending(monitor_module.monitor)
        loop.set_exception_handler(previous_handler)
```

- [ ] **Step 3: Write failure-isolation RED tests**

Patch each sink independently to raise `RuntimeError("OBS_MARKER")`. Assert
`report_end()` returns normally, the other sinks still receive a safe event,
stdout and stderr do not contain the exception text, and start-time state is
cleaned. Patch `builtins.runtime` only with
`monkeypatch.setattr(builtins, "runtime", Runtime(), raising=False)` and let
pytest restore it; never manually delete it. Put
context reset, collector cleanup, pending-task settlement, and event-loop
handler restoration in `finally`.

Add `test_current_loop_websocket_failure_is_consumed`. Install a custom loop
exception handler,
pause the protected send until `_pending_snapshot()` shows exactly one Task
and no Future, release it, settle through the snapshot helper, and assert the
callback removes it. Also assert no unretrieved exception context, no marker
in stdout/stderr, no close-after-schedule behavior, no retry, and no
tool/terminal outcome change. For
manager-loop failure, add
`test_manager_loop_websocket_future_is_consumed`: run a real secondary event
loop thread, pause the send until the snapshot shows exactly one Future and no
Task, release and settle it, then assert callback removal and empty inventory.
Assert its exception is consumed with the same no-close-after-schedule and
outcome invariants. Separately make `_safe_console` raise and
add `test_console_failure_isolated_and_start_state_cleaned` to prove WebSocket,
`stream_writer`, telemetry, and start-state cleanup still complete. Pass
hostile result, identity, timestamp, path, and extreme-number
objects and assert their magic methods are never called.

Add `test_pending_inventory_initializes_and_snapshots_under_lock`. Reset the
singleton only after settling its snapshot, construct a fresh `ToolMonitor`,
assert `_pending_lock` exists and supports reentrant locked registration,
both inventories exist, and `_pending_snapshot()` returns `((), ())`. Do not
reassign either set in this or any other fixture.

Add `test_emit_never_uses_hostile_truthiness_or_raw_route_ids` with a hostile
`__bool__`, 129-character and illegal-character `thread_id` values, and
illegal `run_id` / `segment_id` values. Assert no caller magic runs and no raw
or invalid route reaches `ConnectionManager`. Add
`test_valid_generated_identities_route_exactly` using the repository's
generated identity fixtures and assert the valid values reach projection and
routing byte-for-byte unchanged.

Add `test_current_loop_scheduling_failure_closes_protected_coroutine` and
`test_manager_loop_scheduling_failure_closes_protected_coroutine`. Force
`create_task` and `run_coroutine_threadsafe` respectively to raise before
scheduling, then settle through `_pending_snapshot()` and force warning
collection. Assert both inventories remain empty, while the not-yet-scheduled
protected coroutine is closed exactly once. Also assert
stdout plus stderr contain neither the marker nor `coroutine was never
awaited`, the custom loop exception handler has no unretrieved exception, all
other sinks still run, and tool return, canonical outcome, and retry count are
unchanged.

Add
`test_observation_failures_do_not_change_exact_returns_or_canonical_result`.
Within this one test node, loop over exact `str`, `dict`, and `bytes` values,
retain the original object/value, force
projector/collector/WebSocket/`stream_writer`/console failure one at a time,
and assert the reporter returns normally and the value is byte-for-byte
unchanged. Feed the deterministic string fixture through
`process_stream_chunk`/`AgentRunAccumulator` and the existing run-result
service fixture, then assert canonical result text and Evidence references are
identical to the control. Count tool calls/retries and assert no observation
failure adds a retry or changes the terminal outcome.

- [ ] **Step 4: Run Task 3 RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q \
  tests/unit/test_monitor_sanitization.py \
  tests/integration/test_observation_delivery.py \
  tests/integration/test_run_auxiliary_isolation.py::test_monitor_isolates_same_tool_timing_and_routes_by_run \
  tests/integration/test_run_auxiliary_isolation.py::test_connection_manager_keeps_two_run_channels_for_same_thread \
  tests/integration/test_run_auxiliary_isolation.py::test_run_websocket_resolves_run_identity
```

Expected: FAIL because current payloads/messages contain raw values, share
mutable identity, interpolate sink errors, and leave asynchronous send
exceptions without the required consumption contract.

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
    target_thread_id = _explicit_or_context(thread_id, get_thread_context)
    target_run_id = _explicit_or_context(run_id, get_run_context)
    target_segment_id = _explicit_or_context(segment_id, get_segment_context)
    payload = projector.monitor_event(
        event_type=event_type,
        data=data,
        thread_id=target_thread_id,
        run_id=target_run_id,
        segment_id=target_segment_id,
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )
    if payload is None:
        _safe_console("Observation projection rejected")
        return
    route_run_id = payload["run_id"]
    route_thread_id = payload["thread_id"]
```

Select explicit identities without invoking caller truthiness and without
falling back from an invalid explicit value to context:

```python
def _explicit_or_context(explicit: object, context_getter) -> object:
    if explicit is not None:
        return explicit if type(explicit) is str else None
    try:
        return context_getter()
    except Exception:
        return None
```

Only `route_run_id` and `route_thread_id` from the projected payload may be
passed to `ConnectionManager`; test `is not None`, never truthiness. The raw
target values are projection inputs only and must never become routing keys.

Copy only the already-closed fixed-depth built-in envelope:

```python
def _copy_event_payload(payload: dict[str, object]) -> dict[str, object]:
    source_data = payload["data"]
    data_copy = {
        key: dict(value) if type(value) is dict else value
        for key, value in source_data.items()
    }
    return {
        "type": payload["type"],
        "schema": payload["schema"],
        "event": payload["event"],
        "message": payload["message"],
        "data": data_copy,
        "thread_id": payload["thread_id"],
        "run_id": payload["run_id"],
        "segment_id": payload["segment_id"],
        "timestamp": payload["timestamp"],
    }
```

Call `_copy_event_payload(payload)` separately for WebSocket and
`stream_writer`. Never pass the canonical projected dict itself to a sink.
Catch each sink independently and route fixed messages only through:

```python
def _safe_console(fixed_message: str) -> None:
    try:
        print(f"\n[Monitor] {fixed_message}")
    except Exception:
        pass
```

Console failure cannot escape, block another sink, or prevent start-state
cleanup. Failure messages are exactly:

```text
[Monitor] WebSocket delivery failed
[Monitor] stream_writer delivery failed
```

Print successful events only as:

```python
_safe_console(payload["message"])
```

Current-loop delivery schedules one protected coroutine that receives the
captured manager, copied payload, and projected route identities. It creates
and awaits `send_to_run` / `send_to_thread` inside the protected body, so no
raw send coroutine exists before scheduling:

```python
async def _protected_websocket_send(
    manager,
    payload: dict[str, object],
    run_id: str | None,
    thread_id: str | None,
) -> None:
    try:
        if run_id is not None:
            await manager.send_to_run(payload, run_id)
        elif thread_id is not None:
            await manager.send_to_thread(payload, thread_id)
    except asyncio.CancelledError:
        return
    except Exception:
        _safe_console("WebSocket delivery failed")
```

Retain the created task until its done callback calls `task.exception()` and
removes it from a private pending set. Manager-loop delivery must retain the
`run_coroutine_threadsafe` future in a private pending set and register a done
callback that calls `future.exception()` inside fixed exception handling,
removes the future, and never formats it. Capture the manager, make the
WebSocket copy, and read only the projected route IDs before constructing the
protected coroutine. If loop lookup or scheduling fails, close that one
protected coroutine explicitly and emit only the fixed fallback. Creating or
scheduling a send may fail without affecting `stream_writer`, telemetry,
console, tool retry, or outcome.

```python
from concurrent.futures import Future


# In the fresh-instance branch of ToolMonitor.__new__:
instance._pending_lock = RLock()
instance._pending_tasks: set[asyncio.Task[None]] = set()
instance._pending_futures: set[Future[None]] = set()


def _consume_done(self, pending_kind: str, completed) -> None:
    try:
        if not completed.cancelled():
            completed.exception()
    except Exception:
        pass
    finally:
        try:
            with self._pending_lock:
                pending = (
                    self._pending_tasks
                    if pending_kind == "task"
                    else self._pending_futures
                )
                pending.discard(completed)
        except Exception:
            pass


def _register_pending(self, pending_kind: str, scheduled) -> None:
    pending = (
        self._pending_tasks
        if pending_kind == "task"
        else self._pending_futures
    )
    try:
        with self._pending_lock:
            pending.add(scheduled)
            try:
                scheduled.add_done_callback(
                    lambda completed: self._consume_done(
                        pending_kind, completed
                    )
                )
            except Exception:
                pending.discard(scheduled)
                raise
    except Exception:
        # Scheduling already succeeded: never close or cancel it here.
        _safe_console("WebSocket delivery failed")


def _pending_snapshot(self) -> tuple[tuple[object, ...], tuple[object, ...]]:
    with self._pending_lock:
        return tuple(self._pending_tasks), tuple(self._pending_futures)

protected = _protected_websocket_send(
    manager,
    websocket_payload,
    route_run_id,
    route_thread_id,
)
if current_loop is manager_loop:
    try:
        task = current_loop.create_task(protected)
    except Exception:
        protected.close()
        _safe_console("WebSocket delivery failed")
        return
    self._register_pending("task", task)
else:
    try:
        future = asyncio.run_coroutine_threadsafe(protected, manager_loop)
    except Exception:
        protected.close()
        _safe_console("WebSocket delivery failed")
        return
    self._register_pending("future", future)
```

The scheduling `try` contains only `create_task(protected)` or
`run_coroutine_threadsafe(protected, manager_loop)`. Once either returns, the
event loop owns `protected`; no later bookkeeping path may call
`protected.close()` or cancel the scheduled object. `_register_pending()` is
non-throwing, rolls back a partial set insertion if callback installation
unexpectedly fails, and uses only the fixed fallback. The protected coroutine
itself consumes delivery exceptions, so even this internal bookkeeping
fallback cannot create an unretrieved send exception.

`_pending_lock` is a dedicated `RLock` because a completed manager-loop Future
may run its callback on the manager thread while the caller is registering or
snapshotting. Holding the reentrant lock across add plus callback installation
also handles an already-completed Task/Future whose callback runs immediately.
Every fresh singleton construction, including a test reset through
`ToolMonitor._instance = None` followed by `ToolMonitor()`, initializes the
lock and both sets. Tests and cleanup must settle the immutable
`_pending_snapshot()` result and assert a subsequent snapshot is `((), ())`;
they must never iterate, clear, or replace the live sets directly.
Replace every `print` in `api/monitor.py`, including
`ConnectionManager.get_loop`, connect, disconnect, and send fallbacks, with
`_safe_console()` and a fixed literal that contains no identity, loop id,
exception, path, argument, or result.

Reporter rules:

- Keep `sanitize_args` as a compatibility function whose docstring states
  that it returns a closed descriptor, not sanitized caller fields. Replace
  the current `ToolMonitor` example's nonexistent progress reporter and
  unregistered sample alias with:

```python
monitor.report_start("tavily_search", {"query": query})
try:
    result = search()
    monitor.report_end("tavily_search", result=result)
    return result
except TimeoutError as exc:
    monitor.report_end(
        "tavily_search",
        error="timeout",
        error_type=type(exc).__name__,
    )
    raise
```

  The docstrings must explain that registered stable aliases preserve public
  field positions while `args`/`result` now contain descriptors rather than
  raw values.
- `sanitize_args` remains a direct compatibility helper only. Reporters must
  not pre-project through it, which would describe the descriptor rather than
  the original argument shape.
- `report_start` / `report_tool`: keep signatures, pass raw `args` only to projector descriptor.
- `report_end(tool_name, result=None, error=None, error_type=None)`: compute duration; create `TelemetryRecord` inside `try/except`; emit safe data even if collector fails.
- `report_assistant`: retain signature, but projector closes both label and args.
- `report_task_result`: never truncate or copy content; pass value only for descriptor projection.
- `report_task_finalized`: preserve current arguments; pass `output_path` only
  to projection, where presence means exact non-empty built-in `str`; discard
  the path. Pass legacy `error_message` only into atomic error normalization,
  where its content is immediately discarded and a non-null unknown value
  becomes `execution_failed`.
- `report_session_dir`: pass `path` only to projection, where
  `workspace_created` means exact non-empty built-in `str`; never emit it.
- `report_retry(service_name, attempt, max_retries, error=None, error_type=None)`: retain legacy `error`, never inspect it, emit `retryable_failure`.
- `report_cache_hit`: projector closes `tool_name`; preserve event selection by `cached`.
- `api.server._mark_run_timeout`: keep its `_emit` routing call; projector replaces the interpolated message with the fixed timeout message.

- [ ] **Step 6: Run Task 3 GREEN**

Run the Step 4 command again.

Expected: PASS; WebSocket and `stream_writer` payloads are value-equal but
non-aliased, a mutating sink cannot contaminate the other, async failures are
consumed, and route identity is unchanged.

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
| missing RAGFlow or Tavily configuration | `configuration_missing` | `None` |
| invalid table name or SQL type | `input_invalid` | `None` |
| RAGFlow assistant not found | `resource_not_found` | `None` |
| caught `TimeoutError` / `asyncio.TimeoutError` | `timeout` | exact exception class name |
| caught `ConnectionError` / `OSError`, pool or connection unavailable | `service_unavailable` | exact caught class name when available |
| other caught exception | `execution_failed` | exact caught class name |
| retry notification after a retryable exception | `retryable_failure` | exact exception class name |

The ordered class/category decision table is:

| Order | Structured condition | Stable code |
| --- | --- | --- |
| 1 | exact local validation category | `input_invalid` |
| 2 | exact missing-configuration category | `configuration_missing` |
| 3 | `TimeoutError` / `asyncio.TimeoutError` | `timeout` |
| 4 | `ConnectionError` / `OSError` or explicit pool/whitelist unavailable category | `service_unavailable` |
| 5 | explicit not-found category | `resource_not_found` |
| 6 | any other caught exception | `execution_failed` |

No branch may inspect, search, or parse an exception/error message.

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

Add exact tests for: MySQL invalid table/SQL validation,
whitelist-unavailable and pool-unavailable categories; Tavily missing
configuration; `TimeoutError`; `ConnectionError`; `OSError`; and an unknown
exception. Assert the code and exact exception class name, and assert the
existing model-visible returned string/dict is unchanged in every case.
Name the parameterized nodes
`test_observation_error_categories_are_structured_and_message_independent`
and
`test_observation_error_mapping_uses_ordered_exception_classes`.

Add
`test_only_observed_tool_aliases_and_no_duplicate_answer_event` for RAGFlow:
assert only `ragflow_assistant_list` and `ragflow_question` reach monitor
tool events, the existing retry logger `service_name` values remain untouched,
and no raw-answer `report_tool` call remains.

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
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q \
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
- In MySQL tools, define the three module constants and replace every paired
  start/end label consistently. Change private validation/pool helpers to
  return the existing display string plus an explicit stable category; callers
  return the exact existing display string but report only the category.
  Whitelist/pool unavailability is `service_unavailable`, invalid table/SQL is
  `input_invalid`, and ordered caught classes follow the table above. Do not
  derive a category from the display string.
- In RAGFlow tools, define only the two observed tool aliases. Keep the
  existing `_retry_with_timeout` `service_name` logger labels unchanged because
  those values never reach `monitor.report_retry` or another observation
  sink. Remove the duplicate raw-answer `monitor.report_tool` block at current
  lines 174-177 because `report_end("ragflow_question", full_answer)` already
  emits the result descriptor; do not change `full_answer` or cleanup.
- In Tavily, use `tavily_search` for every start/end call and report the
  structured category before returning. Missing configuration is
  `configuration_missing`; catch timeout classes first,
  `ConnectionError`/`OSError` second, and unknown exceptions last. Keep the
  filtered result dict and every returned error string unchanged.
- In `retry_async`, replace `error=str(last_exception)` with:

```python
error="retryable_failure",
error_type=type(last_exception).__name__ if last_exception is not None else None,
```

Update the `retry`/`retry_async` `service_name` docstrings from
human-readable/display wording to "registered stable observation alias";
arbitrary values fail closed to `unknown_service`. Do not change attempts,
wait calculation, sleeps, exception propagation, or retry budgets.

- [ ] **Step 5: Run Task 4 GREEN and model/Evidence regressions**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q \
  tests/unit/test_agent_run_result.py \
  tests/unit/test_retry_utils.py \
  tests/unit/test_mysql_security.py \
  tests/unit/test_ragflow_tools.py \
  tests/unit/test_tavily_tools.py \
  tests/unit/test_cache.py \
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
- Modify: `docs/observability.md`
- Modify: `docs/reference/api-contract.md:177-195`
- Modify: `docs/reference/data-models.md:180-198`
- Modify: `docs/README.md:33-55`
- Modify: `CHANGELOG.md:5-7`
- Modify: `tests/unit/test_documentation_contracts.py`

**Interfaces:**
- Consumes: final event/data/error/descriptor tables from Tasks 1-4.
- Produces: public documentation that describes implemented behavior without claiming release, deployment, generic DLP, or consumer adoption.

- [ ] **Step 1: Write parsed documentation contract RED tests**

```python
import json
import re

import pytest


OBSERVATION_REFERENCE = (
    PROJECT_ROOT / "docs/reference/observation-contract.md"
)
EXPECTED_EVENT_KEYS = {
    "session_created": {"workspace_created"},
    "tool_start": {"tool_name", "args"},
    "tool_end": {
        "tool_name", "status", "duration_ms", "result", "error", "error_type"
    },
    "assistant_call": {"assistant_name", "args"},
    "task_result": {"result"},
    "task_finalized": {"status", "fallback_used", "output_present", "error"},
    "retry_event": {
        "service_name", "attempt", "max_retries", "error", "error_type"
    },
    "cache_hit": {"tool_name", "cached"},
    "cache_miss": {"tool_name", "cached"},
    "run_timeout": {
        "timeout_seconds", "previous_status", "finalized_by_callback"
    },
    "error": {"error", "error_type"},
}
EXPECTED_MESSAGES = {
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
EXPECTED_DESCRIPTOR_ROWS = [
    ["None", "present=False, kind=none"],
    ["exact str", "present=True, kind=string, character_count, count_capped"],
    ["exact bytes", "present=True, kind=bytes, byte_count, count_capped"],
    ["exact dict", "present=True, kind=mapping, top_level_item_count, count_capped"],
    ["exact list or tuple", "present=True, kind=sequence, top_level_item_count, count_capped"],
    ["exact bool, int, float, or complex", "present=True, kind=scalar"],
    ["subclass or other object", "present=True, kind=opaque"],
]
EXPECTED_ERROR_CODES = {
    "configuration_missing", "input_invalid", "resource_not_found", "timeout",
    "service_unavailable", "execution_failed", "retryable_failure",
}
EXPECTED_ALIASES = {
    "agent_name": ({"main"}, "unknown_agent"),
    "assistant_name": ({"task_subagent"}, "unknown_assistant"),
    "tool_name": ({
        "mysql_list_tables", "mysql_table_data", "mysql_query",
        "ragflow_assistant_list", "ragflow_question", "tavily_search",
        "tavily_search_dedup",
    }, "unknown_tool"),
    "service_name": ({"tavily"}, "unknown_service"),
    "tool_status": ({"success", "error"}, "error"),
    "run_status": ({
        "pending", "running", "completed", "completed_with_fallback", "failed",
    }, "failed"),
}
TELEMETRY_KEYS = {
    "schema", "thread_id", "run_id", "segment_id", "agent_name",
    "tool_name", "duration_ms", "status", "error", "error_type", "timestamp",
}


def _parse_table(document: str, heading: str) -> list[list[str]]:
    section = document.split(heading, 1)[1].split("\n## ", 1)[0]
    rows = [
        [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        for line in section.splitlines()
        if line.startswith("|")
    ]
    return [row for row in rows[2:]]


def _assert_observation_reference_contract(reference: str) -> None:
    json_blocks = [
        json.loads(block)
        for block in re.findall(r"```json\n(.*?)\n```", reference, re.S)
    ]
    monitor_blocks = [
        item for item in json_blocks
        if item.get("schema") == "dra.monitor-event.v1"
    ]
    assert len(monitor_blocks) == 1
    event_rows = _parse_table(reference, "## Event data matrix")
    assert len(event_rows) == len(EXPECTED_EVENT_KEYS)
    assert {
        row[0]: set(filter(None, row[1].split(", "))) for row in event_rows
    } == EXPECTED_EVENT_KEYS
    assert {row[0]: row[2] for row in event_rows} == EXPECTED_MESSAGES
    assert _parse_table(reference, "## Descriptor matrix") == (
        EXPECTED_DESCRIPTOR_ROWS
    )
    error_code_rows = _parse_table(reference, "## Stable error codes")
    assert len(error_code_rows) == len(EXPECTED_ERROR_CODES)
    assert {row[0] for row in error_code_rows} == EXPECTED_ERROR_CODES
    alias_rows = _parse_table(reference, "## Alias matrix")
    assert len(alias_rows) == len(EXPECTED_ALIASES)
    assert {
        row[0]: (set(filter(None, row[1].split(", "))), row[2])
        for row in alias_rows
    } == EXPECTED_ALIASES
    telemetry_blocks = [
        item for item in json_blocks
        if item.get("schema") == "dra.telemetry-record.v1"
    ]
    assert len(telemetry_blocks) == 3
    assert all(set(item) == TELEMETRY_KEYS for item in telemetry_blocks)
    error_rows = _parse_table(reference, "## Coherent error matrix")
    assert error_rows == [
        ["success + no error", "success", "null", "null"],
        ["error + no error", "error", "execution_failed", "null"],
        ["allowed error", "error", "exact stable code", "valid type or null"],
        ["raw or unknown error", "error", "execution_failed", "valid type or null"],
    ]
    assert _parse_table(reference, "## Field migration") == [
        ["args", "closed descriptor", "canonical tool input"],
        ["result", "closed descriptor", "canonical result or artifact"],
        ["error", "stable code or null", "canonical terminal result"],
    ]
    assert "1970-01-01T00:00:00+00:00" in reference
    assert "500 records per execution, FIFO" in reference
    assert "no replay or backfill" in reference


def test_privacy_safe_observation_contract_is_exact_and_indexed() -> None:
    reference = OBSERVATION_REFERENCE.read_text(encoding="utf-8")
    api_contract = (
        PROJECT_ROOT / "docs/reference/api-contract.md"
    ).read_text(encoding="utf-8")
    data_models = (
        PROJECT_ROOT / "docs/reference/data-models.md"
    ).read_text(encoding="utf-8")
    observability = (
        PROJECT_ROOT / "docs/observability.md"
    ).read_text(encoding="utf-8")
    _assert_observation_reference_contract(reference)
    api_rows = _parse_table(api_contract, "## Monitor event matrix")
    assert len(api_rows) == len(EXPECTED_EVENT_KEYS)
    assert {
        row[0]: set(filter(None, row[1].split(", "))) for row in api_rows
    } == EXPECTED_EVENT_KEYS
    assert {row[0]: row[2] for row in api_rows} == EXPECTED_MESSAGES
    data_model_records = [
        json.loads(block)
        for block in re.findall(r"```json\n(.*?)\n```", data_models, re.S)
        if "dra.telemetry-record.v1" in block
    ]
    assert len(data_model_records) == 3
    assert all(set(item) == TELEMETRY_KEYS for item in data_model_records)
    assert "X-API-Key" in reference
    assert "500 records per execution, FIFO" in reference
    assert "no replay or backfill" in reference
    assert "docs/observability.md" in reference
    assert "docs/reference/observation-contract.md" in observability
    assert "not a fallback" in observability
    assert "5-minute provider-free proof" in reference


@pytest.mark.parametrize(
    "old,new",
    [
        ("dra.monitor-event.v1", "dra.monitor-event.v2"),
        ("500 records per execution, FIFO", "durable retention"),
        ("args | closed descriptor", "args | raw value"),
        (
            "1970-01-01T00:00:00+00:00",
            "1970-01-01T00:00:00",
        ),
        (
            "error + no error | error | execution_failed | null",
            "error + no error | error | null | RuntimeError",
        ),
    ],
)
def test_observation_reference_rejects_contract_mutations(old, new) -> None:
    reference = OBSERVATION_REFERENCE.read_text(encoding="utf-8")
    assert old in reference
    with pytest.raises(AssertionError):
        _assert_observation_reference_contract(reference.replace(old, new))


def test_observation_reference_rejects_raw_fallback_and_scope_expansion():
    reference = OBSERVATION_REFERENCE.read_text(encoding="utf-8")
    prohibited = {
        "raw compatibility endpoint",
        "raw observation environment variable",
        "unsafe compatibility flag",
        "legacy raw fallback",
        "new UI or dashboard",
        "hosted tracing implementation",
        "framework business authority",
        "Night Voyager change",
    }
    for item in prohibited:
        assert f"Do not add: {item}" in reference
```

- [ ] **Step 2: Run docs RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 \
"$PYTHON_BIN" -m pytest -q \
  tests/unit/test_documentation_contracts.py::test_privacy_safe_observation_contract_is_exact_and_indexed \
  tests/unit/test_documentation_contracts.py::test_observation_reference_rejects_contract_mutations \
  tests/unit/test_documentation_contracts.py::test_observation_reference_rejects_raw_fallback_and_scope_expansion
```

Expected: FAIL because the observation reference and completed matrices do not exist.

- [ ] **Step 3: Write the public reference and update existing docs**

`docs/reference/observation-contract.md` must include:

1. purpose and application/framework authority boundary;
2. exact monitor envelope/key set and all eleven event/data/fixed-message
   schemas under `## Event data matrix`;
3. exact descriptor, error-code, coherent-error, identity/timestamp, numeric,
   alias, and sentinel tables, using the parsed headings
   `## Descriptor matrix`, `## Stable error codes`,
   `## Coherent error matrix`, `## Alias matrix`, and `## Field migration`;
4. complete safe telemetry JSON for success, error, and invalid-input sentinel
   records, each with the exact eleven keys;
5. authenticated local query example:
   `curl -H "X-API-Key: $API_SECRET"
   http://127.0.0.1:8000/api/telemetry/runs/<run_id>`;
6. process-local, restart-loss, `500 records per execution, FIFO`, no replay
   or backfill, and non-authority statements;
7. fail-closed and best-effort transport behavior, independent sink copies,
   and fixed console output;
8. field-level migration rows for raw `args`, `result`, and `error`, each
   naming its closed replacement and canonical source;
9. the three-option compatibility decision table and explicit prohibition of
   raw endpoint, flag, environment variable, opt-in, or legacy fallback;
10. a diagnosis table with columns `Problem`, `Cause`, `Safe next step`, and
    `Canonical source`, and exact rows for `[]`, every `unknown_*` sentinel,
    `execution_failed`, projection rejection, WebSocket failure,
    `stream_writer` failure, and console failure;
11. three contributor checklists: adding a tool/assistant/service alias, adding
    an error code, and adding an event; each requires code table, exact tests,
    docs table, and review of canonical-source routing;
12. operator cross-link to `docs/observability.md`: raw LangSmith
    inputs/outputs are not a fallback, no hosted tracing implementation, and
    no generic log/DLP claim;
13. non-claims from spec section 11 and no provider, credential, live-data,
    Docker, schema, dependency, release, UI/dashboard, consumer-upgrade, or
    Night Voyager change.
14. an exact `Do not add:` list covering raw compatibility endpoint, raw
    observation environment variable, unsafe compatibility flag, legacy raw
    fallback, new UI or dashboard, hosted tracing implementation, framework
    business authority, and Night Voyager change.

The three required telemetry examples are complete, not abbreviated:

```json
{
  "schema": "dra.telemetry-record.v1",
  "thread_id": "thread-a",
  "run_id": "run-a",
  "segment_id": "run-a-seg-000",
  "agent_name": "main",
  "tool_name": "tavily_search",
  "duration_ms": 12.4,
  "status": "success",
  "error": null,
  "error_type": null,
  "timestamp": "2026-07-26T00:00:00+00:00"
}
```

```json
{
  "schema": "dra.telemetry-record.v1",
  "thread_id": "thread-a",
  "run_id": "run-a",
  "segment_id": "run-a-seg-000",
  "agent_name": "main",
  "tool_name": "tavily_search",
  "duration_ms": 12.4,
  "status": "error",
  "error": "timeout",
  "error_type": "TimeoutError",
  "timestamp": "2026-07-26T00:00:00+00:00"
}
```

```json
{
  "schema": "dra.telemetry-record.v1",
  "thread_id": "thread-a",
  "run_id": "run-a",
  "segment_id": "run-a-seg-000",
  "agent_name": "unknown_agent",
  "tool_name": "unknown_tool",
  "duration_ms": 0.0,
  "status": "error",
  "error": "execution_failed",
  "error_type": null,
  "timestamp": "1970-01-01T00:00:00+00:00"
}
```

Add a public **5-minute provider-free proof** using only planned pytest nodes:

```bash
PYTHON_BIN="${PYTHON_BIN:-$PWD/.venv/bin/python}"
test -x "$PYTHON_BIN"
test "$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" = "3.11"
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -c 'import pytest'
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q \
  tests/integration/test_observation_delivery.py::test_same_marker_is_absent_from_every_observation_sink \
  tests/integration/test_observation_delivery.py::test_observation_failures_do_not_change_exact_returns_or_canonical_result \
  tests/integration/test_run_auxiliary_isolation.py::test_telemetry_api_isolates_two_runs_in_same_thread
```

Document expected output as `3 passed`, plus a four-sink matrix for WebSocket,
`stream_writer`, telemetry/API, and stdout+stderr console proving marker
absence. The second node must prove exact `str`/`dict`/`bytes` tool-visible
returns and canonical result/Evidence regression in the same command. Do not
add a CLI or proof script.

Update the API event list under exact heading `## Monitor event matrix` to the
exact parsed event/data/fixed-message table and include
authenticated telemetry access. Update the telemetry data model with all three
exact JSON examples and retention/sentinel rules. Add one Reference link in
`docs/README.md`. Add an `Unreleased` changelog section describing the
security hardening, unchanged application authority, and field-level changed
raw `args`/`result`/`error` semantics. In `docs/observability.md`, add only the
closed-contract cross-link and raw-LangSmith-fallback prohibition.

- [ ] **Step 4: Run docs GREEN and presentation checks**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_public_truth_documentation.py \
  tests/unit/test_final_presentation_audit.py
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" scripts/final_presentation_audit.py --root .
git diff --check
```

Expected: PASS with zero presentation violations.

- [ ] **Step 5: Commit Task 5**

```bash
git add \
  docs/reference/observation-contract.md \
  docs/observability.md \
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
EXPECTED_IMPLEMENTATION_FILES='CHANGELOG.md
agent/run_result.py
agent/telemetry.py
api/monitor.py
api/observation_contract.py
api/server.py
docs/README.md
docs/observability.md
docs/reference/api-contract.md
docs/reference/data-models.md
docs/reference/observation-contract.md
tests/integration/test_observation_delivery.py
tests/integration/test_run_auxiliary_isolation.py
tests/unit/test_agent_run_result.py
tests/unit/test_documentation_contracts.py
tests/unit/test_monitor_sanitization.py
tests/unit/test_mysql_security.py
tests/unit/test_observation_contract.py
tests/unit/test_ragflow_tools.py
tests/unit/test_retry_utils.py
tests/unit/test_tavily_tools.py
tests/unit/test_telemetry.py
tests/unit/test_telemetry_integration.py
tools/mysql_tools.py
tools/ragflow_tools.py
tools/retry_utils.py
tools/tavily_tools.py'
ACTUAL_IMPLEMENTATION_FILES="$(
  git diff --name-only "$IMPLEMENTATION_BASE"..HEAD | LC_ALL=C sort
)"
test "$ACTUAL_IMPLEMENTATION_FILES" = "$EXPECTED_IMPLEMENTATION_FILES"

BRANCH_BASE='2c50f233c2cc1df4fe2818551e95ab98cd61ede5'
EXPECTED_BRANCH_FILES="$(
  printf '%s\n%s\n%s\n' \
    "$EXPECTED_IMPLEMENTATION_FILES" \
    'docs/superpowers/plans/2026-07-26-privacy-safe-observation-contract-implementation-plan.md' \
    'docs/superpowers/specs/2026-07-25-privacy-safe-observation-contract-design.md' \
    | LC_ALL=C sort
)"
ACTUAL_BRANCH_FILES="$(
  git diff --name-only "$BRANCH_BASE"..HEAD | LC_ALL=C sort
)"
test "$ACTUAL_BRANCH_FILES" = "$EXPECTED_BRANCH_FILES"
```

Expected: the implementation-only range contains exactly the planned
implementation file map, while the full branch additionally contains only the
approved spec and plan. Any other authority/DB/dependency/consumer file is a
hard stop.

- [ ] **Step 2: Run focused observation pack**

```bash
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q \
  tests/unit/test_observation_contract.py \
  tests/unit/test_monitor_sanitization.py \
  tests/unit/test_telemetry.py \
  tests/unit/test_telemetry_integration.py \
  tests/unit/test_retry_utils.py \
  tests/unit/test_agent_run_result.py \
  tests/unit/test_mysql_security.py \
  tests/unit/test_ragflow_tools.py \
  tests/unit/test_tavily_tools.py \
  tests/unit/test_cache.py \
  tests/integration/test_observation_delivery.py \
  tests/integration/test_run_auxiliary_isolation.py \
  tests/integration/test_run_result_api.py \
  tests/unit/test_run_result_service.py
```

Expected: PASS.

- [ ] **Step 3: Run the complete Context Reliability pack**

```bash
PYTHON_DOTENV_DISABLED=1 \
"$PYTHON_BIN" -m pytest -q \
  tests/unit/test_agent_evaluation_context.py \
  tests/unit/test_deepagents_harness.py::test_locked_native_summarizer_profile_forces_coordinator_summary \
  tests/integration/test_context_reliability_regression.py
```

Expected: PASS with paired persisted application outcomes equivalent.

- [ ] **Step 4: Run documentation and presentation verification**

```bash
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_public_truth_documentation.py \
  tests/unit/test_final_presentation_audit.py
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" scripts/final_presentation_audit.py --root .
git diff --check
```

Expected: PASS and `{"status": "ok", "violations": []}`.

- [ ] **Step 5: Run non-Docker full suite and backend CI-parity commands**

```bash
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" scripts/run_dispatch_reconciliation_proof.py check
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" scripts/run_failure_cause_proof.py check
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" scripts/secure_local_runtime_proof.py check
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" scripts/bounded_live_producer_proof.py check
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q -m "not docker"
```

Expected: all commands exit zero. Do not run the local Docker lane.

- [ ] **Step 6: Record frontend as hosted-only reviewed-head evidence**

Do not run local `npm ci`, frontend tests, lint, or build. The frontend is not
an observation consumer and no frontend file is planned. Record
`Frontend Demo Console` only as a later hosted CI gate on the reviewed PR
head; do not claim it locally.

- [ ] **Step 7: Run executable content-leak and scope scans**

```bash
if rg -n -i \
  'C[a]reer|job[-_ ]?search|private[-_ ]?schedul|review[_]owner[_]key|return[_]target|source[_]thread[_]id|task[_]label|/U[s]ers/|019f[0-9a-f-]{20,}' \
  api/observation_contract.py \
  api/monitor.py \
  agent/telemetry.py \
  docs/reference/observation-contract.md \
  docs/observability.md \
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
  docs/observability.md \
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
git log --oneline "$IMPLEMENTATION_BASE"..HEAD
```

Expected: clean worktree and one semantic commit per Task 1-5. Hosted CI must later run the reviewed PR head through `Backend Tests`, `Frontend Demo Console`, `Secure Local Runtime Containers`, and `CodeQL`. Do not claim those hosted gates before they run.

## Plan Self-Review

### Spec Section To Task Mapping

| Spec section | Implementing task(s) |
| --- | --- |
| 1. Goal | Tasks 1-4; verified in Task 6 |
| 2. Architecture and authority boundary | Task 1 projector, Task 3 in-scope independent sink copies, Task 5 `docs/observability.md` boundary, Task 6 authority regressions |
| 3. WebSocket monitor-event contract | Task 1 exact envelope, live-compatible identity patterns, and eleven schemas; Task 3 projected-only routing and protected delivery/scheduling; documented in Task 5 |
| 4. Bounded argument and result descriptors | Task 1 exact shapes, hostile values, numeric bounds; Task 3 fixed-depth copies |
| 5. Stable error contract | Tasks 1, 2, and 4 |
| 6. Telemetry API contract | Task 2 explicit reconstruction, exact timestamp/token usage, sentinel, authenticated API; documented in Task 5 |
| 7. Fail-closed behavior | Task 1 closure and Task 3 hostile-truthiness, scheduling-lifetime, async/console/transport isolation |
| 8. Compatibility strategy | Tasks 3-5 field migration, three-option decision, and raw-fallback prohibition |
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
- WebSocket and `stream_writer` consume value-equal independent fixed-depth
  copies; console consumes only a fixed message through `_safe_console`.
- `ToolMonitor.__new__` initializes both pending inventories and their
  dedicated `RLock`; scheduling-only failure closes the unscheduled coroutine,
  while post-schedule retention/removal uses `_register_pending()`,
  `_consume_done()`, and immutable `_pending_snapshot()` values.
- No task changes a tool function's returned `str`, `dict`, or `bytes`, or the `process_stream_chunk` accumulation/Evidence path.
- `IMPLEMENTATION_BASE` is the latest commit touching this plan, so
  implementation allowlisting starts after the final approved plan revision.
- RAGFlow retry logger names remain unchanged because they do not reach an
  observation sink; only observed tool aliases are registered.

### Exact Review Closure Nodes

For every pytest row below, run the exact node before implementation and
expect RED for the missing contract; rerun the same node after its task and
expect GREEN. All commands use
`PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q <node>`.

| Review correction | Exact RED/GREEN node or executable gate | Task |
| --- | --- | --- |
| Implementation-only boundary | shell equality check of `"$IMPLEMENTATION_BASE"..HEAD` against `EXPECTED_IMPLEMENTATION_FILES`, plus full-branch equality check | 6 |
| `docs/observability.md` boundary | `tests/unit/test_documentation_contracts.py::test_privacy_safe_observation_contract_is_exact_and_indexed` | 5 |
| Value equality and non-aliasing | `tests/integration/test_observation_delivery.py::test_same_marker_is_absent_from_every_observation_sink` | 3 |
| Pending inventory construction/snapshot | `tests/unit/test_monitor_sanitization.py::test_pending_inventory_initializes_and_snapshots_under_lock` | 3 |
| Current-loop exception consumption and Task removal | `tests/integration/test_observation_delivery.py::test_current_loop_websocket_failure_is_consumed` | 3 |
| Manager-loop exception consumption and Future removal | `tests/integration/test_observation_delivery.py::test_manager_loop_websocket_future_is_consumed` | 3 |
| Safe console and cleanup | `tests/unit/test_monitor_sanitization.py::test_console_failure_isolated_and_start_state_cleaned` | 3 |
| Exact telemetry reconstruction | `tests/unit/test_telemetry.py::test_record_preserves_exact_timestamp_and_valid_token_usage` | 2 |
| Invalid telemetry sentinel | `tests/unit/test_telemetry.py::test_invalid_direct_timestamp_and_token_usage_use_sentinels` | 2 |
| Mutation without timestamp refresh | `tests/unit/test_telemetry.py::test_collector_reprojects_mutation_without_refreshing_timestamp` | 2 |
| Authenticated telemetry JSON | `tests/integration/test_run_auxiliary_isolation.py::test_telemetry_api_serializes_success_error_and_invalid_timestamp_sentinel` | 2 |
| Hostile identity/timestamp/numbers and JSON | `tests/unit/test_observation_contract.py::test_hostile_envelope_and_extreme_numbers_fail_closed` | 1 |
| Live-compatible identity patterns | `tests/unit/test_observation_contract.py::test_identity_patterns_match_live_application_contract` | 1 |
| Projected-only routing without hostile truthiness | `tests/integration/test_observation_delivery.py::test_emit_never_uses_hostile_truthiness_or_raw_route_ids` | 3 |
| Exact valid generated routes | `tests/integration/test_observation_delivery.py::test_valid_generated_identities_route_exactly` | 3 |
| Current-loop scheduling failure closes only unscheduled coroutine and leaves inventory empty | `tests/integration/test_observation_delivery.py::test_current_loop_scheduling_failure_closes_protected_coroutine` | 3 |
| Manager-loop scheduling failure closes only unscheduled coroutine and leaves inventory empty | `tests/integration/test_observation_delivery.py::test_manager_loop_scheduling_failure_closes_protected_coroutine` | 3 |
| One error helper, monitor + telemetry | `tests/unit/test_observation_contract.py::test_monitor_and_telemetry_share_exact_error_matrix` | 1 |
| Exact eleven event key sets | `tests/unit/test_observation_contract.py::test_all_event_schemas_have_exact_keys_and_are_json_serializable` | 1 |
| MySQL category mapping | `tests/unit/test_mysql_security.py::test_observation_error_categories_are_structured_and_message_independent` | 4 |
| Tavily ordered exception mapping | `tests/unit/test_tavily_tools.py::test_observation_error_mapping_uses_ordered_exception_classes` | 4 |
| Marker repeat, finally cleanup, stdout+stderr | `tests/integration/test_observation_delivery.py::test_same_marker_is_absent_from_every_observation_sink` | 3 |
| No unobserved RAGFlow aliases/raw answer | `tests/unit/test_ragflow_tools.py::test_only_observed_tool_aliases_and_no_duplicate_answer_event` | 4 |
| Monitor/sanitizer docstrings | `tests/unit/test_monitor_sanitization.py::test_monitor_docstrings_use_registered_aliases_and_descriptor_semantics` | 3 |
| Exact public tables/JSON/diagnosis/checklists | `tests/unit/test_documentation_contracts.py::test_privacy_safe_observation_contract_is_exact_and_indexed` | 5 |
| Five-minute provider-free proof | the exact three-node command in Task 5 | 5 |
| Documentation mutation rejection | `tests/unit/test_documentation_contracts.py::test_observation_reference_rejects_contract_mutations` | 5 |
| Python 3.11 environment | executable **Execution Environment Gate** before RED | pre-Task 1 |
| No local frontend pack | Task 6 hosted-only text plus exact implementation file allowlist | 6 |
| Out-of-scope prohibitions | `tests/unit/test_documentation_contracts.py::test_observation_reference_rejects_raw_fallback_and_scope_expansion` | 5 |
| Exact returns/canonical result | `tests/integration/test_observation_delivery.py::test_observation_failures_do_not_change_exact_returns_or_canonical_result` | 3 |

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
| Event identity or run routing changes | Context/routing | `api.thread_ids.validate_thread_id`, `api.monitor.ToolMonitor._emit`, `_schedule_websocket_send`, `ConnectionManager`, exact identity/routing tests | Do not use truthiness selection, route on raw/unprojected IDs, collapse `thread_id`/`run_id`, route through a global channel, or move identity authority to framework state. |
| Projection failure changes execution/retry | Best-effort reporter boundary | `ToolMonitor.report_*`, retry tests, observation delivery failure tests | Do not retry a tool because WebSocket/collector failed or let logging exceptions propagate. |
| Canonical result/Evidence drift | Application authority | run-result tests and Context Reliability pack | Do not make telemetry, LangGraph checkpoint, trace, or frontend state authoritative. |
| One sink mutation changes another sink payload | Fixed-depth delivery copies | `_copy_event_payload`, `test_same_marker_is_absent_from_every_observation_sink` | Do not share the projected envelope or nested `data` object between sinks. |
| Pending inventory is absent, races, or remains non-empty after settlement | WebSocket scheduling bookkeeping | `ToolMonitor.__new__`, `_pending_lock`, `_register_pending`, `_consume_done`, `_pending_snapshot`, exact Task 3 inventory/loop tests | Do not lazily create sets after scheduling, mutate them without the lock, iterate live sets in cleanup, or close a coroutine after a Task/Future owns it. |
| `coroutine was never awaited`, `Task exception was never retrieved`, or manager future warning | WebSocket scheduling | `_protected_websocket_send`, scheduling-only close path, `_register_pending`, current-loop Task callback, manager-loop Future callback, exact Task 3 loop tests | Do not create a raw send coroutine before scheduling, leak the protected coroutine on scheduling failure, include bookkeeping in the close-on-failure `try`, fire-and-forget a Task/Future, or format its exception. |
| Console failure interrupts reporting | Fixed console boundary | `_safe_console`, `test_console_failure_isolated_and_start_state_cleaned` | Do not call raw `print`, interpolate caller values, or make console success a precondition for other sinks. |
| Telemetry timestamp changes during collection | Retention reconstruction | `TelemetryRecord.__post_init__`, `TelemetryCollector.record`, timestamp mutation tests | Do not use a default factory during reconstruction or copy via `vars()`/`**__dict__`. |
| Empty telemetry response or sentinel code is unclear | Public operator contract | observation diagnosis table and authenticated telemetry tests | Do not recover by enabling raw LangSmith input/output, a raw API mode, or framework authority. |
| MySQL/Tavily code changes with error wording | Call-site structured classification | private validation category helpers and ordered exception tests | Do not parse error/exception text or guess a category from a returned display string. |

## Execution Handoff

Only after renewed authority approval of this revised plan, execute it with
`superpowers:executing-plans` in this existing isolated branch/worktree,
serially from Task 1 through Task 6. Stop at every semantic commit for review,
and stop immediately on any hard-stop or Python-environment condition. Do not
use `superpowers:subagent-driven-development` for this shared
projector/contract change.
