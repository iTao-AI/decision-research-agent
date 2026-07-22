# API Contract

This document describes the active public backend contract for Decision
Research Agent. Historical endpoints removed during v0.1.0 cleanup are not part
of this contract.

## Health

### GET /health

```json
{"status":"ok","service":"decision-research-agent"}
```

## Run Execution

### POST /api/runs

`Idempotency-Key` is an optional request header. When it is absent, every
accepted request remains an independent create and the response shape is
unchanged. A key must contain 8-128 ASCII characters matching
`[A-Za-z0-9][A-Za-z0-9._:-]{7,127}`. Its scope is service-wide for the current
single-service credential/development deployment.

The first keyed acceptance returns the existing fields plus
`idempotent_replay: false`. Reusing the same key with the same canonical
query/profile/thread/scope returns the original identities with
`idempotent_replay: true`. Both new and replay acknowledgements may trigger a
targeted private dispatch reconciliation attempt, but only one exact claim can
cross the Agent start fence. `status: started` is an acceptance acknowledgement,
not proof that Agent invocation has begun; use `GET /api/runs/{run_id}` for
current state. Successful acceptance remains HTTP 200 with the existing response shape
(plus the existing keyed-only `idempotent_replay` field).

Stable direct error envelopes are:

- `409 run_idempotency_conflict` when the key is bound to a different request;
  the response does not disclose the bound run.
- `422 run_idempotency_key_invalid` for an invalid header.
- `503 run_idempotency_unavailable` when the durable ledger cannot be used;
  keyed requests never fall back to an unkeyed create.

The raw key is not persisted, logged, or returned by the server. After commit,
dispatch is asynchronous: scheduler or wake failure does not turn an accepted
response into HTTP 500. The private worker records bounded codes such as
`run_dispatch_schedule_failed` and `run_dispatch_start_timeout`, retries up to
three attempts, and then atomically fails dispatch, run, and segment. If a
worker dies after the third claim, the next scan records
`run_dispatch_lease_expired` and performs the same terminal convergence without
creating attempt 4. Recovery stops once execution is running and does not claim
exactly-once execution.

Start a canonical run-scoped research execution.

Request:

```json
{
  "query": "Research question",
  "thread_id": "caller-session-id",
  "profile_id": "generic",
  "scope": {}
}
```

Response:

```json
{
  "status": "started",
  "thread_id": "caller-session-id",
  "run_id": "run_...",
  "segment_id": "run_..._seg_..."
}
```

### GET /api/runs/{run_id}

Return the bounded run projection: execution status, review status, delivery
status, current artifacts, current publication, review workflow, verification
summary, and state version. The projection does not expose database paths,
checkpoint payloads, lease owners, actor fingerprints, raw tracebacks, or local
artifact paths.

The status projection adds exactly one additive top-level field,
`failure_cause`, with public schema `dra.run-failure-cause.v1`. Its three exact
variants are:

Observed failure:

```json
{"failure_cause":{"schema_version":"dra.run-failure-cause.v1","observation_status":"observed","phase":"execution","code":"call_budget_exceeded","recorded_at":"2026-07-16T00:00:00+00:00"}}
```

Historical failure whose bounded cause was not recorded before migration:

```json
{"failure_cause":{"schema_version":"dra.run-failure-cause.v1","observation_status":"not_observed"}}
```

Nonfailed run:

```json
{"failure_cause":null}
```

For an observed cause, `recorded_at` is the winning application
terminal-transaction time, not the first provider, framework, or operating
system error time. The object never exposes `terminal_state_version`, raw
exception class or text, traceback, query, provider payload, retry count, lease
or checkpoint identity, database path, local path, credential, or trace ID.
Missing, duplicate, malformed, or state-inconsistent cause data fails closed as
a bounded internal error without returning the corrupt row or raw database
exception.

The extra-allow OpenAPI envelope is documentation metadata whose only declared
property is the required nullable observed/not-observed union. It is not a
response filter and does not remove existing run-status fields.

### GET /api/runs/{run_id}/result

Resolve the current canonical delivery artifact. The endpoint reads
service-owned ResearchRun, delivery/publication state, and persisted artifacts;
it does not read LangGraph checkpoint state.

Ready generic runs return `research-report.md`. Ready Talent runs return the
current publication artifact when available, otherwise the canonical
`decision-brief.md` artifact. Delivery is Markdown-only delivery in v0.1.0.

The `GET /api/runs/{run_id}/result` response, error envelope, and OpenAPI
operation remain unchanged. In particular, `409 run_failed` does not include
`failure_cause`; clients that need the bounded cause read the status endpoint
before or after the unchanged result request.

Stable errors:

| Status | Code | Meaning |
|---|---|---|
| `404` | `run_not_found` | Run does not exist |
| `409` | `run_not_terminal` | Run is still pending or running |
| `409` | `run_failed` | Run failed and has no deliverable result |
| `409` | `run_review_required` | Delivery is waiting for review |
| `409` | `run_delivery_blocked` | Delivery was blocked |
| `409` | `run_result_unavailable` | Artifact missing, empty, unsafe, too large, or hash-mismatched |

These result endpoint error codes are stable public contract values.

### GET /api/runs/{run_id}/artifacts/{artifact_id}

Return the bytes and stored media type of the current canonical deliverable
selected by the result resolver. The run terminal and delivery state, current
publication selection, and selected artifact content and metadata all come
from the same SQLite request snapshot. A state change committed after that
snapshot applies to the next request; the endpoint does not claim continuous
revocation after a response has begun.

A ready fallback artifact selected by the resolver is a legal deliverable and
retains its original bytes and media type. The endpoint does not expose historical artifact content;
it also does not expose pre-delivery content or a second storage inspection surface.

The route preserves the resolver's stable errors: `404 run_not_found`, plus
`409 run_not_terminal`, `409 run_failed`, `409 run_review_required`,
`409 run_delivery_blocked`, and `409 run_result_unavailable`. If the requested
`artifact_id` is not the resolver-selected artifact, the response is
`404 {"detail":"Artifact 不存在"}`. Path separators are not valid inside the
artifact path parameter.

### GET /api/profiles/{profile_id}

Return the server-owned profile and harness-policy manifest. It includes
schema/renderer identifiers, tool allowlists, named researchers, Skills,
backend, and filesystem permissions, but no provider credentials or
request-specific runtime state.

An unknown profile returns `404` with detail code `unknown_profile`.

## Observability

### GET /api/telemetry/runs/{run_id}

Return run-scoped telemetry records. Records carry `thread_id`, `run_id`, and
`segment_id` for correlation.

### GET /api/token-usage/runs/{run_id}

Return run-scoped token usage.

### WebSocket /ws/runs/{run_id}

Stream run-scoped monitor events. Same-thread concurrent runs use separate
channels.

Events include `session_created`, `tool_start`, `assistant_call`,
`task_result`, `run_timeout`, and `error`.

## Controlled Durable Review

The review API is feature-flagged and authenticated. It requires:

- `DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL=true`
- non-empty `API_SECRET`
- valid `X-API-Key`
- persistent application and checkpoint SQLite databases

Endpoints:

```text
GET  /api/reviews
GET  /api/reviews/health
GET  /api/runs/{run_id}/reviews/{review_id}
POST /api/runs/{run_id}/reviews/{review_id}/decisions
```

Review list responses are bounded queue projections and do not include query
text, claims, evidence bodies, decision reason, artifacts, lease data, or
checkpoint internals.

Workflow terminal and operator states include
`approved | rejected | manual_recovery | superseded`.

Decision requests support `approve` and `reject`; repeated identical
`decision_id` submissions are idempotent replays, while conflicting content is
rejected with a stable error envelope.

## Controlled Evidence Verification

The verification API is feature-flagged and authenticated. It requires durable
review readiness plus:

- `DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION=true`
- complete verification/publication schema

Endpoints:

```text
GET  /api/evidence-verifications/health
GET  /api/runs/{run_id}/evidence/verifications
GET  /api/runs/{run_id}/evidence/{evidence_id}/verification
POST /api/runs/{run_id}/evidence/{evidence_id}/verification-decisions
POST /api/runs/{run_id}/evidence/verification-snapshots
```

Verification decisions are append-only. Finalization creates or reuses a
deterministic verification snapshot and revisioned publication. Stale state
returns `409 stale_state_version` without partial writes.

## Authentication

Except `/health` and OpenAPI documentation, HTTP API paths require
`X-API-Key` when `API_SECRET` is configured. The Tool Client reads
`DECISION_RESEARCH_AGENT_API_KEY` from the environment and never accepts an API
key as a command-line argument.

When `API_SECRET` is empty, credential-free source access is allowed only when
the direct peer and literal Host must both be loopback. A configured secret
removes that exception and requires the exact `X-API-Key` on protected HTTP
and WebSocket requests. WebSocket credentials are header-only: `api_key` query
credentials are rejected before run identity lookup or connection ownership.
Public paths and CORS preflight retain their bounded bypasses. Controlled
review and Evidence verification retain independent feature-owned gates in
addition to the shared runtime access policy.

Browser CORS is deny-by-default. Operators may allow one explicit origin with
`DECISION_RESEARCH_AGENT_CORS_ALLOWED_ORIGIN`; when it is unset, the allowlist
is empty. CORS and Origin checks are not authentication. The retired
frontend-specific setting is not a compatibility alias.

The supported source entrypoint is `python api/server.py`; it passes the
already-constructed app to Uvicorn on `127.0.0.1` with reload disabled and
warning-level logging. The source and Compose launchers use Uvicorn
warning-level logging so rejected legacy query credentials are not emitted by
info-level WebSocket transport logging. Compose additionally requires explicit
API/MySQL secrets, uses loopback-only host publication, declares bounded
backend/MySQL health, drops all backend capabilities, and enables
`no-new-privileges`. These container controls do not change public paths,
authentication authority, or feature-owned review and Evidence gates.

All caller-provided `thread_id` values must be 1-128 characters of letters,
digits, dots, underscores, or hyphens. Path separators and traversal forms are
rejected.

`POST /api/runs` defaults `profile_id` to `generic`, `scope` to an empty
object, and generates `thread_id` when omitted. Unknown profiles return `400
unknown_profile`; invalid Talent scope returns `422 invalid_research_scope`
before execution is scheduled.

## Error Shape

New controlled APIs use stable bounded envelopes:

```json
{
  "code": "stable_code",
  "problem": "Human readable problem",
  "cause": "Bounded cause",
  "fix": "Actionable fix",
  "retryable": false,
  "run_id": "run_...",
  "request_id": "request_..."
}
```

Responses must not include local filesystem paths, secrets, checkpoint payloads,
actor fingerprints, lease owners, raw tracebacks, or raw model/tool payloads.
