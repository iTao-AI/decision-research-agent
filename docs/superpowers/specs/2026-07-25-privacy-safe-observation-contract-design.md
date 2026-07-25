# Privacy-Safe Observation Contract v1

## Status

Approved design for a bounded, provider-free hardening capability. This document defines implementation authority; it does not claim the capability is already released or present in `v0.1.6`.

## 1. Goal

Close raw tool result, exception, query, path, and nested-sensitive-field exposure through WebSocket monitor events, LangGraph `stream_writer`, and the telemetry API while preserving all of the following:

- model-visible `ToolMessage` values and tool return values;
- `ResearchRun`, Evidence, artifact, review, and delivery authority;
- the immutable `dra.downstream-consumer.v1` run status/result/Evidence
  boundary and Night Voyager's unchanged pinned consumption boundary;
- provider/model behavior, database schema, dependencies, and runtime budgets.

`v0.1.6` remains immutable. Raw observation `args`, `result`, and `error`
semantics are intentionally hardened in place under `Unreleased`; this does
not claim compatibility for the whole `v0.1.6` diagnostic surface or claim
that Night Voyager consumes observations.

Success is not merely truncation. Every in-scope project-owned observation
sink must receive only closed, bounded metadata.

## 2. Architecture and authority boundary

```text
Tool / Agent runtime
  ├─ model-visible return ───────────────> DeepAgents / LangChain
  ├─ application outcome ───────────────> ResearchExecutionService / DB
  └─ observation input
       └─ project-owned safe projector
            ├─ WebSocket /ws/runs/{run_id}
            ├─ LangGraph stream_writer
            ├─ fixed console output
            ├─ in-process telemetry collector
            └─ GET /api/telemetry/runs/{run_id}
```

Add one pure application-layer observation contract/projection module. It must not call a provider, read credentials, access the database, or enter model context.

Framework decisions:

- Keep LangGraph `stream_writer` as a transport, but never trust caller-provided observation data.
- Do not use LangChain `wrap_tool_call` to rewrite results because that would conflate model-visible results with operator observation.
- Do not use `ToolMessage.artifact` as the monitoring channel; artifacts belong to agent/application data flow, not the public observation contract.
- Reuse the existing provider telemetry pattern of closed allowlists, bounded counts, exception-type-only metadata, and best-effort emission.

Framework runtime, trace, and checkpoints do not become application authority.
The in-scope project-owned observation sinks are the WebSocket, the existing
LangGraph `stream_writer`, console output, and retained telemetry/API.
Hosted tracing and general process logs remain outside this contract.

## 3. WebSocket monitor-event contract

Preserve the existing envelope and route while adding an explicit schema identifier:

```json
{
  "type": "monitor_event",
  "schema": "dra.monitor-event.v1",
  "event": "tool_end",
  "message": "Tool execution completed",
  "data": {},
  "thread_id": "thread-example",
  "run_id": "run-example",
  "segment_id": "run-example-seg-000",
  "timestamp": "2026-07-26T00:00:00+00:00"
}
```

Preserve endpoint, event names, routing, identity, and timestamp.

Allowed event data:

| Event | Allowed fields |
| --- | --- |
| `session_created` | `workspace_created` |
| `tool_start` | `tool_name`, safe `args` descriptor |
| `tool_end` | `tool_name`, `status`, `duration_ms`, safe `result` descriptor, stable `error` code, `error_type` |
| `assistant_call` | `assistant_name`, safe `args` descriptor |
| `task_result` | safe `result` descriptor; consumers obtain the body from the canonical result |
| `task_finalized` | `status`, `fallback_used`, `output_present`, stable `error` code |
| `retry_event` | `service_name`, `attempt`, `max_retries`, stable `error` code, `error_type` |
| `cache_hit` / `cache_miss` | `tool_name`, `cached` |
| `run_timeout` | `timeout_seconds`, `previous_status`, `finalized_by_callback` |
| `error` | stable `error` code and optional `error_type` |

The payload and message must never contain:

- tool argument values, query, question, or description;
- tool result bodies, search results, SQL rows, or RAGFlow answers;
- raw exception strings, tracebacks, or SQL statements;
- absolute paths or output paths;
- Evidence snippets or artifact content;
- credentials, tokens, or secrets;
- unknown fields.

Envelope fields are closed as follows:

- `thread_id` is an exact built-in string matching the public
  `validate_thread_id` contract
  `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`, or `null`;
- `run_id` is an exact built-in string matching
  `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`, or `null`;
- `segment_id` is an exact built-in string matching
  `^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$`, or `null`;
- `timestamp` is an exact built-in string matching the bounded timezone-aware
  ISO form `YYYY-MM-DDTHH:MM:SS`, followed by an optional fractional second
  and then `Z` or a `+HH:MM` / `-HH:MM` offset.

Exact valid identity and timestamp values remain unchanged. Invalid values
fail closed to `null` for identities and to the deterministic
`1970-01-01T00:00:00+00:00` timestamp sentinel. Projection must validate
exact built-in values without invoking caller magic methods.
Explicit monitor identities are selected without truthiness coercion. An
invalid explicit identity does not fall back to context, and WebSocket routing
uses only the already-projected `run_id` / `thread_id` values. Raw or invalid
identities never reach `ConnectionManager`.

## 4. Bounded argument and result descriptors

Keep the `args` and `result` field positions, but replace content with metadata. Representative descriptor:

```json
{
  "present": true,
  "kind": "mapping",
  "top_level_item_count": 4,
  "count_capped": false
}
```

Allowed `kind` values:

```text
none | string | bytes | mapping | sequence | scalar | opaque
```

Rules:

- Strings expose only a capped `character_count`.
- Bytes expose only a capped `byte_count`.
- Built-in mappings and sequences expose only a top-level count.
- Opaque objects must not invoke `repr()`, `str()`, JSON serialization, or a custom `__len__`.
- Reuse the current safe telemetry count ceiling of `10_000`; values beyond the ceiling return the ceiling and set `count_capped=true`.
- Numeric observation metadata accepts only exact built-in finite `int` or
  `float` values, clamps to `0..10_000`, and never drops a known event because
  an input is extreme or hostile.
- Do not generate content hashes. No current consumer requires them, and low-entropy hashes can become new content identifiers.

Projection must be total, bounded, non-throwing, and independent of content depth.

One logical event is projected once. WebSocket and `stream_writer` receive
value-equal, independent fixed-depth copies of the closed built-in envelope
and nested `data`; no mutable object identity is shared between sinks.

## 5. Stable error contract

Keep the existing `error` field position, but allow only `null` or a closed stable code. The initial code set is:

```text
configuration_missing
input_invalid
resource_not_found
timeout
service_unavailable
execution_failed
retryable_failure
```

Rules:

- Any unclassified raw error maps to `execution_failed`.
- `error_type` is allowed only after validating the exception class name as an ASCII identifier.
- Never retain or transmit the exception message.
- Existing calls such as `report_end(error="raw text")` may remain accepted to limit call-site compatibility risk, but the raw value must be discarded immediately.
- Known call sites should progressively pass stable codes; do not classify by guessing from exception text.
- Normalize `(status, error, error_type)` atomically: `error_type` is `null`
  when `error` is `null`, and an error status without a mapped code becomes
  `execution_failed`.

## 6. Telemetry API contract

`GET /api/telemetry/runs/{run_id}` preserves its list response and existing identity fields while returning closed records:

```json
{
  "schema": "dra.telemetry-record.v1",
  "thread_id": "thread-example",
  "run_id": "run-example",
  "segment_id": "run-example-seg-000",
  "agent_name": "main",
  "tool_name": "tavily_search",
  "duration_ms": 12.4,
  "status": "error",
  "error": "timeout",
  "error_type": "TimeoutError",
  "timestamp": "2026-07-26T00:00:00+00:00"
}
```

`TelemetryRecord` must not retain raw errors. Internal callers must not be able to bypass WebSocket projection and expose content through the telemetry API.

Retention reconstructs every `TelemetryRecord` field explicitly. An exact,
valid timezone-aware `datetime` and an exact, valid
`TokenUsageData | None` are preserved without refreshing the timestamp.
Invalid direct-construction timestamps become the deterministic timezone-aware
UTC sentinel `1970-01-01T00:00:00+00:00`; invalid token usage becomes `null`.
Mutation re-projection must not create a new timestamp.

Telemetry remains process-local diagnostic state. It is not a durable failure cause, Evidence, result, review, delivery, or business authority.

## 7. Fail-closed behavior

- Unknown event types do not emit caller content; record only a fixed local projection-rejected diagnostic.
- Invalid labels, error codes, or error types are replaced with a safe sentinel or generic code.
- Projection, collector, or transport failure must not change a tool return value, agent execution, or terminal outcome.
- WebSocket send failure remains best effort and must not trigger a tool retry.
- Every console fallback uses a fixed template and never interpolates a raw error, path, argument, or result.
- Presence booleans derived from paths are true only for an exact, non-empty
  built-in string. Other values fail closed without invoking magic methods.

## 8. Compatibility strategy

The compatibility alternatives are:

| Option | Result | Decision |
| --- | --- | --- |
| Remove content-bearing observation fields | Strong closure, but breaks established field positions. | Rejected for this bounded hardening. |
| Harden in place with closed descriptors and codes | Preserves routes, event names, identity, and primary field positions while removing content. | Approved. |
| Add a versioned safe contract with explicit legacy retirement and migration | Supports a staged migration but keeps a legacy exposure path during retirement. | Rejected because no raw legacy path is authorized. |

Adopt the approved in-place fail-closed contract:

- do not add a legacy endpoint;
- do not add an environment variable that restores raw payloads;
- do not provide an unsafe compatibility flag;
- preserve routes, event names, envelopes, identity, and primary field positions;
- change `args`, `result`, and `error` semantics to closed safe metadata;
- document the security hardening in the observation reference, API contract, and `CHANGELOG.md` under `Unreleased` during implementation.

The current Console does not consume the WebSocket, and Night Voyager does not consume these observation fields. An unknown consumer that depends on raw content must move to the canonical result or artifact rather than restoring an exposure path.

`docs/observability.md` defines the separate operator boundary for LangSmith.
Raw LangSmith inputs or outputs are not a fallback for missing closed
telemetry. This capability does not implement hosted tracing and does not
claim generic process-log, DLP, or third-party logging safety.

## 9. TDD and verification contract

The first RED tests must prove that the current code exposes all of the following:

- top-level and nested secrets;
- tool results larger than 4 KiB;
- SQL statements and exception text;
- RAGFlow questions and answers;
- absolute output paths;
- retry exceptions;
- raw errors in the telemetry API;
- the same synthetic marker through WebSocket, `stream_writer`, retained
  telemetry/API, and console output.

After GREEN, verification must prove:

1. No marker appears in serialized payloads, telemetry responses, stdout, or
   stderr across two repeated executions of the main integration fixture.
2. Event identity, run isolation, and routing remain unchanged.
3. WebSocket and `stream_writer` values are equal but their envelopes and
   nested `data` objects do not alias; mutation by one sink does not affect the
   other.
4. Model-visible string, dictionary, and bytes tool results remain byte-for-byte unchanged.
5. Canonical result, Evidence, and Context Reliability comparison behavior remain unchanged.
6. Projection remains total, bounded, and non-throwing for large, nested, unserializable, and malicious objects.
7. Unknown events, invalid identities/timestamps, and invalid codes fail closed.
8. Existing focused tool, retry, telemetry, run-result, cache, and WebSocket tests pass.
9. The complete Context Reliability pack, documentation contract tests, non-Docker full suite, and presentation audit pass.
10. Hosted CI later executes the existing Backend, Frontend, Secure Local Runtime Containers, and CodeQL gates on the reviewed PR head.

Do not call providers or model endpoints, read credentials, use live data, or run local Docker for this capability pack.

## 10. Documentation impact

Implementation is expected to:

- add an observation contract/reference;
- complete the API contract event matrix;
- update the telemetry data model;
- cross-link the closed contract from `docs/observability.md` without changing
  hosted tracing behavior;
- update the documentation index;
- add an `Unreleased` changelog entry;
- add documentation contract tests.

No existing authority ADR changes because application DB authority, framework runtime, and consumer authority remain unchanged. If implementation requires changing any of those, stop and request a new architecture decision.

## 11. Non-claims

This capability does not claim:

- generic DLP, PII detection, or secret scanning;
- that every log and third-party SDK is guaranteed to contain no sensitive data;
- model-context or tool-return budgeting;
- global limits for SQL rows, RAGFlow answers, or Tavily payloads;
- durable telemetry, production monitoring, an SLA, or hosted deployment;
- provider quality, research quality, or business impact;
- inclusion in `v0.1.6`;
- that Night Voyager must upgrade.

## 12. Stop conditions and release posture

The bounded capability pack stops after:

```text
spec landed and reviewed
→ implementation plan approved
→ provider-free TDD implementation
→ independent pre-PR review
→ hosted CI
→ merge and cleanup
→ evidence closeout
```

Do not create a new Release or change `VERSION` by default. A Release requires a separate decision based on an actual observation consumer, an explicit distribution need, or a requirement for Release users to receive the security fix.

Stop immediately and request renewed architecture approval if implementation would require any of the following:

- changing model-visible results or tool execution semantics;
- changing the database schema or Evidence/result authority;
- changing the immutable `dra.downstream-consumer.v1` run
  status/result/Evidence boundary, `v0.1.6`, or Night Voyager's pinned
  consumption boundary;
- adding any legacy raw-observation mode.
