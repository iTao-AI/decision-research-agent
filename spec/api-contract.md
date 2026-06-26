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
`decision-brief.md` artifact.

Stable errors:

| Status | Code | Meaning |
|---|---|---|
| `404` | `run_not_found` | Run does not exist |
| `409` | `run_not_terminal` | Run is still pending or running |
| `409` | `run_failed` | Run failed and has no deliverable result |
| `409` | `run_review_required` | Delivery is waiting for review |
| `409` | `run_delivery_blocked` | Delivery was blocked |
| `409` | `run_result_unavailable` | Artifact missing, empty, unsafe, too large, or hash-mismatched |

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

All caller-provided `thread_id` values must be 1-128 characters of letters,
digits, dots, underscores, or hyphens. Path separators and traversal forms are
rejected.

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
