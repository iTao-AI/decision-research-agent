# State Machines

Decision Research Agent uses service-owned state machines around a
DeepAgents-native execution harness. LangGraph drives runtime execution, but
application database tables are the authority for run, evidence, review,
verification, publication, and delivery state.

## Execution Path

```mermaid
stateDiagram-v2
    [*] --> pending: POST /api/runs
    pending --> leased: private dispatch claim
    leased --> pending: bounded retry
    leased --> running: atomic start fence
    leased --> failed: three attempts exhausted
    running --> completed: harness outcome accepted
    running --> failed: exception, timeout, cancellation
    completed --> [*]
    failed --> [*]
```

Execution identity:

- `thread_id` groups the caller conversation and LangGraph runtime context.
- `run_id` owns one isolated execution, workspace, telemetry, token usage,
  monitor route, cache partition, evidence ledger, and delivery result.
- `segment_id` identifies the terminal write segment used for fenced
  finalization.

Terminal writes use `state_version` and allowed previous statuses. A stale
writer, timeout callback, cancellation handler, or normal completion cannot
silently overwrite a terminal run written by another path.

The `leased` state is represented by private `run_dispatches_v1`; public
ResearchRun remains `pending` until the exact lease owner and attempt atomically
advance dispatch to `started`, run to `running`, and the initial segment to
`running`. Expired leases can be reclaimed. A stale task or timeout is a no-op
against a newer attempt. Bounded scheduler/start failures use
`run_dispatch_schedule_failed` or `run_dispatch_start_timeout`; the third
failed attempt converges dispatch, run, and segment to `failed`. An expired
third lease is terminalized with `run_dispatch_lease_expired` before scanning
the next pending row, so attempt 4 is never created. Pre-start timeout uses
atomic timeout reconciliation: the exact attempt is released while leased,
timeout-finalized if already started, or ignored if a newer attempt owns state.

## Harness Boundary

```mermaid
flowchart TD
    API["FastAPI /api/runs"] --> Service["ResearchExecutionService"]
    Service --> Harness["DeepAgents harness adapter"]
    Harness --> Framework["LangChain agent framework"]
    Framework --> Graph["LangGraph runtime"]
    Harness --> Tools["Approved tools"]
    Service --> Ledger[("Application DB")]
    Service --> Result["Canonical artifacts"]
```

DeepAgents owns agent execution, tool filtering, middleware, skills loading,
and runtime context injection. The service layer owns evidence capture,
terminal transactions, review decisions, verification snapshots, publications,
and canonical result delivery.

The main generic research state machine does not resume an interrupted tool
call after process death. Durable resume semantics apply only to the controlled
review workflow shown below.

## Generic Delivery

```mermaid
stateDiagram-v2
    completed --> ready: research-report.md persisted
    ready --> delivered: GET /api/runs/{run_id}/result
```

A completed generic run persists `research-report.md` in
`run_artifacts_v2` during the same terminal transaction. `GET
/api/runs/{run_id}/result` returns that artifact only when execution is
completed, delivery is ready, the artifact is safe, and the content hash
matches the persisted payload.

## Talent Review And Publication

```mermaid
stateDiagram-v2
    completed --> review_required: ReviewBundle requires delivery gate
    review_required --> ready: approve resolution
    review_required --> blocked: reject resolution
    ready --> stale: accepted verification change
    blocked --> stale: accepted verification change
    stale --> review_required: new snapshot finalization
```

Talent outputs must satisfy the structured contract:

- research packet schema is valid;
- findings and claims contain non-empty evidence references;
- every evidence reference resolves to the current run snapshot;
- review bundle and canonical DecisionBrief artifacts are deterministic.

Approval permits delivery. It does not verify evidence. Rejection blocks
delivery and does not start a new research run.

## Durable Review Workflow

```mermaid
stateDiagram-v2
    [*] --> checkpoint_pending
    checkpoint_pending --> waiting_decision
    waiting_decision --> resume_pending: approve/reject accepted
    resume_pending --> resuming: worker lease
    resuming --> resolution_pending
    resolution_pending --> approved
    resolution_pending --> rejected
    waiting_decision --> superseded: newer verification snapshot
    resume_pending --> manual_recovery: ambiguous or exhausted recovery
    resuming --> manual_recovery: ambiguous or exhausted recovery
```

The application DB stores decisions, workflows, leases, resume attempts, and
resolutions. The separate checkpoint DB stores only the LangGraph review-gate
checkpoint. Ambiguous state becomes `manual_recovery` instead of being guessed.

## Evidence Verification

```mermaid
stateDiagram-v2
    unverified --> human_verified: verify decision
    unverified --> human_rejected: reject decision
    human_verified --> human_rejected: newer reject revision
    human_rejected --> human_verified: newer verify revision
```

Evidence rows are immutable. Human verification is an append-only decision for
the exact persisted fingerprint. Finalization creates or reuses a deterministic
snapshot and may create a new publication revision.

## Result Endpoint States

| Run state | Result endpoint |
|---|---|
| `pending` / `running` | `409 run_not_terminal` |
| `failed` | `409 run_failed` |
| `delivery_status=review_required` | `409 run_review_required` |
| `delivery_status=blocked` | `409 run_delivery_blocked` |
| missing, empty, unsafe, too-large, or hash-mismatched artifact | `409 run_result_unavailable` |
| `completed` + `delivery_status=ready` + valid artifact | `200` canonical artifact |

## Change Log

| Date | Change |
|---|---|
| 2026-05-19 | Initial state-machine document |
| 2026-06-26 | Replaced removed coordinator/workspace model with canonical run, review, verification, and delivery state machines |
