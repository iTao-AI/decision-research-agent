# Run Identity Boundaries

`thread_id`, `run_id`, and `segment_id` represent different scopes. They must
not be mechanically renamed or collapsed.

## Keep as `thread_id`

- LangGraph `configurable.thread_id` for framework execution context.
- Caller conversation/session grouping.

## Use `run_id`

- Runtime context and canonical `/api/runs` execution identity.
- Search de-duplication cache key.
- Token collection key.
- ResearchRun, Evidence, artifact, review, verification, publication, and
  result lookup ownership.

## Use `segment_id`

- Identify one terminal write segment for fenced finalization.
- Prevent timeout, cancellation, normal completion, or stale callbacks from
  overwriting a terminal result written by another path.

## Carry both

- Privacy-bounded LangSmith metadata and monitor/telemetry events.
- Logs and diagnostics needed to correlate caller sessions with executions.
- Operational diagnostics that do not expose private payloads.

`POST /api/runs` permits same-thread concurrency. Workspace, runtime context,
telemetry, WebSocket routing, token collection, monitor routing, search cache,
Evidence, and delivery remain isolated by `run_id`.

Optional `Idempotency-Key` reconciliation does not change same-thread independent runs:
unkeyed requests remain independent. Only callers that reuse
the same key and canonical request recover the original identity. The
application database owns this immutable binding; checkpoint and trace state
do not.

The application database owns these identities as business facts. LangGraph
checkpoint configuration and LangSmith trace correlation do not replace the
ResearchRun ledger.

## Interruption And Replacement Identity

A boot generation is private process-generation authority. Each newly running
`run_id` receives one exact owner fence bound to its initial `segment_id`.
Startup-only convergence never revives that identity: the original source
becomes immutable failed with either `execution/execution_error` or
`finalization/run_finalization_failed`.

`POST /api/runs/{source_run_id}/retries` creates a new run identity and one-hop
lineage. The source and replacement keep the exact immutable thread, query,
profile/version, and canonical scope, but they remain distinct executions.
Recovery acceptance is not execution success, and existing status/result
schemas expose neither boot/owner identity nor lineage.
