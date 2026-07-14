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

### GET /api/runs/{run_id}/result

Resolve the current canonical delivery artifact. The endpoint reads
service-owned ResearchRun, delivery/publication state, and persisted artifacts;
it does not read LangGraph checkpoint state.

Ready generic runs return `research-report.md`. Ready Talent runs return the
current publication artifact when available, otherwise the canonical
`decision-brief.md` artifact. Delivery is Markdown-only delivery in v0.1.0.

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

Return one persisted artifact by the exact run and artifact IDs. A successful
response uses the stored media type and returns the content as the response
body. This endpoint does not select the current deliverable; use the result
endpoint for delivery policy.

An unknown run/artifact pair returns `404` with
`{"detail":"Artifact 不存在"}`. Path separators are not valid inside the
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

Browser CORS is deny-by-default. Operators may allow one explicit origin with
`DECISION_RESEARCH_AGENT_CORS_ALLOWED_ORIGIN`; when it is unset, the allowlist
is empty. The retired frontend-specific setting is not a compatibility alias.

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
