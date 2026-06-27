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

The application database owns these identities as business facts. LangGraph
checkpoint configuration and LangSmith trace correlation do not replace the
ResearchRun ledger.
