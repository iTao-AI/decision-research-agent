# Privacy-Safe Observation Contract

This reference defines the implemented, provider-free contract for every
in-scope project-owned observation sink: the run WebSocket, the existing
LangGraph `stream_writer`, console output, and retained in-process
telemetry/API. Each logical monitor event is projected once; the WebSocket and
`stream_writer` receive independent fixed-depth built-in copies and share no
mutable envelope or `data` identity. Console receives only the fixed projected
message. Retained telemetry is separately projected through
`telemetry_fields` and reconstructed as a closed `TelemetryRecord`.

Observation is diagnostic only. `ResearchRun`, Evidence, canonical results,
artifacts, review, and delivery remain application-owned authority. Framework
runtime, checkpoints, tracing, and observation records do not become business
authority. The immutable `v0.1.6` release and
`dra.downstream-consumer.v1` run status/result/Evidence boundary are unchanged;
raw observation `args`, `result`, and `error` semantics are intentionally
hardened in place under `Unreleased`.

## Monitor envelope

Valid exact identity and timestamp values remain unchanged. Invalid values
become `null`, or the documented timestamp sentinel, without coercion or
caller magic methods. WebSocket routing uses only the projected `run_id` or
`thread_id`.

```json
{
  "type": "monitor_event",
  "schema": "dra.monitor-event.v1",
  "event": "tool_end",
  "message": "Tool execution completed",
  "data": {},
  "thread_id": "thread-a",
  "run_id": "run-a",
  "segment_id": "run-a-seg-000",
  "timestamp": "2026-07-26T00:00:00+00:00"
}
```

`thread_id` uses `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`. `run_id` uses the same
syntax and 128-character limit. `segment_id` uses the same character syntax
with a 160-character limit. Values must be exact built-in strings.
Timestamps must be exact, bounded ISO 8601 strings with an explicit timezone.

## Event data matrix

| Event | Allowed data fields | Fixed message |
| --- | --- | --- |
| session_created | workspace_created | Workspace created |
| tool_start | tool_name, args | Tool execution started |
| tool_end | tool_name, status, duration_ms, result, error, error_type | Tool execution completed |
| assistant_call | assistant_name, args | Assistant call started |
| task_result | result | Task result available |
| task_finalized | status, fallback_used, output_present, error | Task finalized |
| retry_event | service_name, attempt, max_retries, error, error_type | Retry scheduled |
| cache_hit | tool_name, cached | Tool cache hit |
| cache_miss | tool_name, cached | Tool cache miss |
| run_timeout | timeout_seconds, previous_status, finalized_by_callback | Research run timed out |
| error | error, error_type | Observation error |

Unknown events are rejected. Unknown data fields are removed. Messages are
fixed by event and never reuse a caller message.

## Descriptor matrix

Counts stop at `10_000`; a larger exact built-in value reports `10_000` and
`count_capped=true`. Projection is shallow, total, bounded, non-throwing, and
does not use recursion, `repr`, `str`, JSON serialization, custom `__len__`,
or content hashes.

| Input | Exact descriptor fields |
| --- | --- |
| None | present=False, kind=none |
| exact str | present=True, kind=string, character_count, count_capped |
| exact bytes | present=True, kind=bytes, byte_count, count_capped |
| exact dict | present=True, kind=mapping, top_level_item_count, count_capped |
| exact list or tuple | present=True, kind=sequence, top_level_item_count, count_capped |
| exact bool, int, float, or complex | present=True, kind=scalar |
| subclass or other object | present=True, kind=opaque |

## Stable error codes

| Code | Meaning |
| --- | --- |
| configuration_missing | Required local configuration is absent |
| input_invalid | Structured input validation failed |
| resource_not_found | A requested resource is absent |
| timeout | A caught timeout class ended the operation |
| service_unavailable | A caught connection class or explicit service category failed |
| execution_failed | An unclassified failure occurred |
| retryable_failure | A retry follows a caught retryable exception |

Raw errors are accepted only as ignored compatibility inputs and are discarded
immediately. Classification never parses exception text. `error_type` is an
ASCII exception class identifier of at most 128 characters and is present
only with a stable error code.

## Coherent error matrix

| Input tuple | status | error | error_type |
| --- | --- | --- | --- |
| success + no error | success | null | null |
| error + no error | error | execution_failed | null |
| allowed error | error | exact stable code | valid type or null |
| raw or unknown error | error | execution_failed | valid type or null |

## Alias matrix

Reporter labels are untrusted. Only registered aliases remain exact.

| Field | Allowed exact values | Sentinel |
| --- | --- | --- |
| agent_name | main | unknown_agent |
| assistant_name | task_subagent | unknown_assistant |
| tool_name | mysql_list_tables, mysql_table_data, mysql_query, ragflow_assistant_list, ragflow_question, tavily_search, tavily_search_dedup | unknown_tool |
| service_name | tavily | unknown_service |
| tool_status | success, error | error |
| run_status | pending, running, completed, completed_with_fallback, failed | failed |

## Telemetry API

Query process-local records through the authenticated local API:

```bash
curl -H "X-API-Key: $API_SECRET" \
  http://127.0.0.1:8000/api/telemetry/runs/<run_id>
```

Success:

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

Error:

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

Invalid direct-construction fields use closed sentinels. An invalid timestamp
uses the deterministic timezone-aware UTC value:

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

Telemetry is process-local and is lost on restart. Retention is
500 records per execution, FIFO. There is no durable replay, no replay or backfill, and no
claim that a newly started process can recover earlier records. Telemetry is
not a durable failure cause, Evidence, result, review, delivery, SLA, or
business authority.

## Field migration

| Field | Observation value | Canonical source |
| --- | --- | --- |
| args | closed descriptor | canonical tool input |
| result | closed descriptor | canonical result or artifact |
| error | stable code or null | canonical terminal result |

Consumers that previously read raw content from these observation fields must
move to the canonical source. The hardened fields do not offer an unsafe
opt-in.

## Compatibility decision

| Option | Outcome |
| --- | --- |
| Remove content-bearing observation fields | Rejected because it breaks existing field positions |
| In-place closed descriptors and codes | Selected; routes, event names, envelope, identities, and primary field positions remain |
| Versioned safe contract with explicit legacy retirement/migration | Not selected because no supported raw-observation consumer requires a migration window |

No raw endpoint, flag, environment variable, opt-in, or legacy fallback is
provided. Night Voyager does not consume this observation surface and its
unchanged pinned consumption boundary requires no upgrade.

## Failure behavior

Projection, collector, WebSocket, `stream_writer`, and console failures are
best effort. They cannot change a tool/model-visible return, canonical result,
Evidence, retry decision, or terminal outcome. Current-loop Tasks and
manager-loop Futures are retained until their exceptions are consumed.
Scheduling failure closes only the not-yet-scheduled protected coroutine.
Console output uses fixed templates and never formats a raw exception,
identity, path, argument, or result.

## Diagnosis

| Problem | Cause | Safe next step | Canonical source |
| --- | --- | --- | --- |
| `[]` | Process has no retained records for the execution | Confirm authenticated run identity and process lifetime | Application run status/result API |
| `unknown_agent` | Unregistered agent label | Register a stable alias with tests and docs | Application agent configuration |
| `unknown_assistant` | Unregistered assistant label | Register a stable alias with tests and docs | Agent harness configuration |
| `unknown_tool` | Unregistered tool label | Register a stable alias with tests and docs | Tool registry and canonical result |
| `unknown_service` | Unregistered retry service label | Register a stable alias with tests and docs | Retry call site |
| `execution_failed` | Failure had no approved stable code | Inspect the canonical terminal result; add a structured category only when justified | Application terminal result |
| Projection rejection | Unknown event or invalid envelope input | Inspect projector schema tests and caller routing | Canonical application result |
| WebSocket failure | Best-effort transport failed | Reconnect and query canonical status/result | Run status/result API |
| `stream_writer` failure | Existing local stream transport failed | Continue execution and query canonical result | Canonical result or artifact |
| Console failure | Local output failed | Continue execution and use authenticated telemetry/status | Telemetry API and canonical status |

## Contributor checklists

When adding a tool, assistant, or service alias:

- update the closed code allowlist;
- add exact alias and sentinel tests;
- update the alias table;
- review routing to the canonical input/result source.

When adding an error code:

- update the closed code table and structured call-site category;
- add exact coherent tuple and message-independent tests;
- update the stable error table;
- review the canonical terminal-result source.

When adding an event:

- update the exact event data and fixed-message tables;
- add unknown-field removal and serialization tests;
- update the event matrix;
- review canonical-source routing and stop if authority would change.

## Operator and scope boundary

See `docs/observability.md`. Raw LangSmith inputs/outputs are not a fallback
for missing closed telemetry. This capability does not implement hosted
tracing and does not claim generic log, DLP, PII, or secret-scanning safety.
Hosted tracing and process logs remain outside this contract.

This capability also makes no claim about model-context/tool-return budgeting,
global provider payload limits, durable monitoring, production deployment,
provider or research quality, business impact, inclusion in `v0.1.6`, or a
Night Voyager upgrade. It adds no provider/model call, credential access, live
data, Docker path, schema migration, dependency, release, UI/dashboard, or
consumer change.

Do not add: raw compatibility endpoint

Do not add: raw observation environment variable

Do not add: unsafe compatibility flag

Do not add: legacy raw fallback

Do not add: new UI or dashboard

Do not add: hosted tracing implementation

Do not add: framework business authority

Do not add: Night Voyager change

## 5-minute provider-free proof

After the documented Python 3.11 setup, run:

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

Expected output: `3 passed`.

| Sink | Proof |
| --- | --- |
| WebSocket | Synthetic marker absent; projected route identity preserved |
| `stream_writer` | Same safe value as WebSocket with independent object identity |
| telemetry/API | Marker absent; run isolation and closed keys preserved |
| stdout+stderr console | Marker absent from fixed console output |

The same command proves exact `str`, `dict`, and `bytes` tool-visible returns
and canonical result/Evidence behavior remain unchanged.
