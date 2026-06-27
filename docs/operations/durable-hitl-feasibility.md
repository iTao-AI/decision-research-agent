# Durable HITL Feasibility

## Status

The endpoint is experimental and disabled by default. A successful gate report
proves the bounded P1B durability contract only; it does not enable the feature
automatically or establish general production readiness.

## Enable in a controlled environment

```dotenv
DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL=true
API_SECRET=<configured out of band>
DECISION_RESEARCH_AGENT_DB_PATH=/app/data/decision_research_agent.db
DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH=/app/data/review_checkpoints.db
```

Both SQLite files must use persistent storage. Keep `API_SECRET` outside source
control and send it through the `X-API-Key` header.

## Decision semantics

- `approve` permits delivery and creates the reviewed DecisionBrief artifact.
  It does not verify evidence or convert candidate claims into verified facts.
- `reject` sets delivery to `blocked`, records the resolution, and does not
  start new research or create a reviewed DecisionBrief artifact.
- A repeated byte-equivalent decision request is an idempotent replay.
  Conflicting decisions fail closed.

## Recovery boundary

The application database is authoritative for the immutable decision, workflow
status, leases, resolution, and artifact metadata. The separate LangGraph
checkpoint database is authoritative only for the pure review-gate execution
checkpoint. Startup reconciliation repairs known crash windows; ambiguous or
poisoned state becomes `manual_recovery` rather than being guessed.

## Gate command

Docker must be running because a skipped container test is a gate failure.

```bash
python scripts/durable_hitl_gate_runner.py \
  --output docs/evidence/durable-hitl-gate-report.json
```

`PASS` requires thirteen passes. Any failure or Docker skip is `NO_GO`. On
`NO_GO`, keep the feature flag false and do not begin P1C.

The container gate uses an isolated, test-only bootstrap readiness report to
break the startup prerequisite cycle. The authoritative report is still built
only from all 13 actual gate results, and production images do not use the test
override.
