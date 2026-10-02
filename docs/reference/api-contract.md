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

The failure-cause status extension adds one additive top-level field,
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
`decision-brief.md` artifact. The result endpoint continues to return Markdown.
For `generic-evidence-report@1`, it independently validates the paired canonical
JSON against frozen same-run Evidence and requires exact deterministic Markdown
equality; rehashed arbitrary text or foreign references remain unavailable.

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

### Structured research: generic-evidence-report@1

The opt-in profile reuses the generic harness and server-owned policy. Its scope
is `{"questions":[{"question_id":"q1","text":"Research question"}]}`:
1–5 unique question IDs and nonempty text up to 4096 code points per question.
An omitted `questions` field defaults to the query as `q1`; an explicit empty
list is invalid. IDs start with an ASCII letter followed by up to 63 letters,
digits, underscores or hyphens. Extra scope fields are rejected. The server
normalizes scope before unkeyed or idempotent creation and dispatch. Invalid
scope returns `422 invalid_research_scope` without raw validator input.

Native tools write `/workspace/research-findings.json`, at most 256 KiB UTF-8,
with `dra.research-findings-candidate.v1`: up to 20 findings, at most 10 exact
source URL/excerpt references per finding, and one disposition per question.
The model supplies candidate statements and exact observed excerpts; it does
not supply authoritative Evidence IDs, hashes, verification or delivery state.
Only root VFS updates are captured. Invalid, null or oversized replacements
invalidate prior candidate bytes; failed source ToolMessages grant no Evidence
authority. The existing completion guard makes at most one correction to write
the new JSON target, selected from server-owned runtime context.

Completed runs can be `ready` or `blocked` with `review_status=not_required`.
Ready requires at least one source-bound finding and valid question coverage;
explicit unresolved questions can accompany findings. Missing, malformed,
empty, ambiguous or unobserved references block the entire package. This profile
never uses the legacy Markdown fallback. Legacy generic and strict citation
behavior is unchanged. A bound excerpt does not prove truth or entailment, and
reported contradictions remain model-reported.

### GET /api/runs/{run_id}/findings

Read-only structured delivery for `generic-evidence-report@1`. Response:

```json
{
  "run_id": "run_...",
  "execution_status": "completed",
  "delivery_status": "ready",
  "artifact": {
    "artifact_id": "research-findings.json",
    "kind": "research_findings_json",
    "media_type": "application/json",
    "content": "<canonical JSON string>",
    "content_hash": "<SHA-256 of this artifact's actual UTF-8 bytes>"
  },
  "report": {
    "schema_version": "dra.research-findings.v1",
    "run_id": "run_...",
    "profile_id": "generic-evidence-report",
    "profile_version": "1",
    "questions": [{"question_id": "q1", "text": "Research question"}],
    "findings": [{
      "finding_id": "f1", "question_id": "q1", "statement": "Candidate finding",
      "references": [{
        "evidence_id": "ev_run_..._<fingerprint>",
        "evidence_fingerprint": "<64 lowercase hex characters>",
        "source_url": "https://example.com/source",
        "source_identity": "https://example.com/source",
        "snippet": "Observed excerpt", "excerpt": "Observed excerpt",
        "excerpt_start": 0, "excerpt_end": 16
      }]
    }],
    "dispositions": [{"question_id": "q1", "status": "candidate_findings"}],
    "limitations": [], "reported_contradictions": []
  }
}
```

`report` is an object containing run/profile/schema identity, accepted questions,
`findings`, `dispositions`, limitations and reported contradictions. Each finding
has a stable `f1`, `f2`, … ID and bound references with same-run `evidence_id`,
`evidence_fingerprint`, source URL/identity, unchanged frozen `snippet`, exact
`excerpt`, and zero-based half-open **Unicode code-point** offsets
`excerpt_start`/`excerpt_end`. Offsets are neither UTF-8 bytes nor UTF-16 units.

The reader uses one repository snapshot of run delivery authority, scope,
artifacts and same-run Evidence rows. It rejects duplicate JSON keys, nonfinite
numbers, malformed UTF-8, unknown fields, wrong profile/version, invalid own-byte
hashes, noncanonical Markdown and changed or foreign Evidence references even
when hashes are recomputed. Both JSON and Markdown independently fit 1 MiB
UTF-8, inclusive. JSON and Markdown must belong to current artifact selection
where publication selection exists. No checkpoint, VFS, source refetch or model
call occurs. Errors match `/result`: `run_not_found`, `run_not_terminal`,
`run_failed`, `run_review_required`, `run_delivery_blocked` and
`run_result_unavailable`; ready runs with another profile use the last error.

GET run status adds optional `findings_issues` (closed issue codes, at most 20)
and `findings_outcome` only for this profile after strict identity/hash validation
of the persisted diagnostic artifact (at most 4 KiB). Its four bounded counts
are `requested_question_count` (1–5), `covered_question_count` (0–5),
`unresolved_question_count` (0–5), and `reference_binding_failure_count` (0–200).
Corrupt diagnostics omit these fields. Counts describe candidate coverage and
binding failures; they are not semantic accuracy metrics. Diagnostics contain
no candidate bytes or raw exception text. Ready packages persist diagnostics
alongside JSON/Markdown; blocked packages persist diagnostics only.

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

`generic-strict-citation` is selected through the existing `profile_id` field.
Its manifest reports version `"1"` through this single-profile endpoint; there
is no profile-list endpoint and the documented proof schema is not a manifest
or result field. Ready strict delivery requires an exact current-run admitted
source URL in the canonical non-fallback artifact after application
recomputation. Strict finalization failure reuses
`finalization/run_finalization_failed`, retains Evidence, and exposes no
artifact. The literal `generic` profile is unchanged: zero exact citations
remain warning-only. In other words, zero exact citations remain warning-only
for literal `generic`. See
[Strict Citation Profile](strict-citation-profile.md) for the correction,
privacy, producer-pin, and non-claim boundaries.

## Observability

### GET /api/telemetry/runs/{run_id}

Return closed run-scoped telemetry records. The protected local route uses the
same `X-API-Key` authentication contract as other protected HTTP endpoints.
Records carry `thread_id`, `run_id`, and `segment_id` for correlation; see the
[Observation Contract](observation-contract.md).

### GET /api/token-usage/runs/{run_id}

Return run-scoped token usage.

### WebSocket /ws/runs/{run_id}

Stream run-scoped monitor events. Same-thread concurrent runs use separate
channels.

## Monitor event matrix

Every event uses `schema=dra.monitor-event.v1`, a fixed message, closed event
data, and the existing run WebSocket route.

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
unknown_profile`; invalid Talent or research-findings scope returns `422 invalid_research_scope`
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

## Explicit Run Replacement

```text
POST /api/runs/{source_run_id}/retries
X-API-Key: required by the configured local runtime
Idempotency-Key: required
body: exactly zero body bytes
```

Whitespace, JSON, form data, and any other byte are rejected with
`422 run_recovery_body_not_allowed`. Authentication denial occurs before body
observation or repository access. Success is asynchronous HTTP `202` with the
closed ten-field `dra.run-recovery.v1` response:

```json
{
  "schema_version": "dra.run-recovery.v1",
  "status": "accepted",
  "reason": "previous_boot_interrupted",
  "interrupted_phase": "execution",
  "source_run_id": "source",
  "run_id": "replacement",
  "thread_id": "caller-thread",
  "segment_id": "replacement_seg_000",
  "recovery_attempt": 1,
  "idempotent_replay": false
}
```

This is a new run, not resume. `accepted is not started, completed, or
successful`; post-commit wake is best effort. Replaying the same source/key
returns the same replacement with only `idempotent_replay=true`. Existing
create/status/result and `dra.run-failure-cause.v1` schemas do not change.

| Status | Code | Meaning |
|---|---|---|
| 404 | `run_recovery_source_not_found` | Source identity is absent |
| 409 | `run_recovery_not_eligible` | Exact profile or source contract unavailable |
| 409 | `run_recovery_exhausted` | Replacement cannot create a second hop |
| 409 | `run_recovery_conflict` | Key or source already has different binding |
| 422 | `run_recovery_key_invalid` | Key fails the bounded contract |
| 422 | `run_recovery_body_not_allowed` | One or more body bytes were observed |
| 503 | `run_recovery_unavailable` | Durable recovery authority is unavailable |

Raw zero-body request example (headers are supplied through stdin rather than
API-key command arguments):

```bash
curl --config - <<EOF
url = "http://127.0.0.1:8000/api/runs/${SOURCE_RUN_ID}/retries"
request = "POST"
header = "X-API-Key: ${DECISION_RESEARCH_AGENT_API_KEY}"
header = "Idempotency-Key: ${RECOVERY_KEY}"
fail-with-body
silent
show-error
EOF
```

The example intentionally supplies no body or content-type option. The
recovery key deduplicates replacement creation only, not provider/tool effects.


The shared coordinator prompt retains the Markdown default and explicitly allows
only the server-supplied structured profile envelope to select the JSON target,
with precedence over legacy Skill output-format wording. The server constructs
that envelope from validated profile/scope and quotes query/question text as
untrusted research content. Provider-free tests prove native mechanics and
delivery authority; they do not prove real-model instruction adherence.

The producer envelope also states the existing intake boundary: Evidence capture
collapses whitespace and truncates observed snippets to 1000 code points. Exact
excerpts must occur uniquely and contiguously inside that stored normalized
snippet; later passages of a longer raw tool result cannot satisfy binding.
