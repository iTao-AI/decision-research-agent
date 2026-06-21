# Controlled Review Workflow

## Supported Boundary

The controlled review workflow supports one backend replica, one persistent
application SQLite database, one separate persistent checkpoint SQLite
database, persistent output storage, an explicit feature flag, and one
configured API credential.

This is not a multi-user or multi-instance deployment contract. The application
database remains the business ledger; the checkpoint database stores only the
LangGraph review-gate execution position. The existing Vue frontend does not
provide review controls.

## Configure

Set all four variables through the deployment environment:

- `DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL`
- `API_SECRET`
- `TASKS_DB_PATH`
- `DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH`

The feature flag must be explicitly `true`. Both database paths must be
persistent files, must be different, and must not be `:memory:`. Their parent
directories and the output directory must be writable. Keep `API_SECRET` out of
source control and provide the corresponding Tool Client credential through
`DECISION_RESEARCH_AGENT_API_KEY`.

## Verify

Run the checks serially:

```bash
python tools/decision_research_agent_tool.py doctor

python scripts/durable_hitl_gate_runner.py \
  --output docs/evidence/durable-hitl-gate-report.json

DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
  python -m pytest \
  tests/integration/test_durable_review_container.py::test_controlled_review_cli_approve_and_reject_canary \
  -q
```

`doctor` must report the server, Talent profile, and durable review checks as
`ok`. The gate report must contain `status=PASS`, `expected=13`, `passed=13`,
and an empty `failed` list. The Docker CLI canary must pass without a skip:
approval reaches `workflow.status=approved` with `delivery_status=ready`;
rejection reaches `workflow.status=rejected` with `delivery_status=blocked`
and no reviewed artifact.

Before allowing an external caller, create controlled synthetic reviews and
complete one approve and one reject lifecycle with the first-party Tool Client.
Confirm approval produces a reviewed artifact and rejection leaves delivery
blocked without a reviewed artifact.

## Operate

Discover and inspect pending work:

```bash
python tools/decision_research_agent_tool.py review list \
  --status waiting_decision

python tools/decision_research_agent_tool.py review show \
  --run-id "$RUN_ID"
```

Approve and wait for durable resolution:

```bash
python tools/decision_research_agent_tool.py review approve \
  --run-id "$RUN_ID" \
  --wait
```

Reject without placing the reason in shell history:

```bash
python tools/decision_research_agent_tool.py review reject \
  --run-id "$RUN_ID" \
  --reason-file "$REJECTION_REASON_FILE" \
  --wait
```

Standard input is also supported:

```bash
python tools/decision_research_agent_tool.py review reject \
  --run-id "$RUN_ID" \
  --reason-stdin \
  --wait
```

Wait separately when a decision was submitted without `--wait`:

```bash
python tools/decision_research_agent_tool.py review wait \
  --run-id "$RUN_ID"
```

Retrieve the terminal run and reviewed artifact metadata:

```bash
python tools/decision_research_agent_tool.py result \
  --run-id "$RUN_ID"
```

Approval permits delivery but does not verify Evidence. Rejection blocks
delivery, creates no reviewed deliverable, and does not start new research.
Corrected research requires a new `run_id`.

## Manual Recovery

If `review show` or `review wait` reports `manual_recovery`:

1. Set `DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL=false` and restart the
   backend.
2. Preserve and back up the application database, checkpoint database, and
   output storage.
3. Capture redacted `doctor`, review detail, and service log output.
4. Classify the stable `last_error_code` against a reviewed recovery procedure.
5. Escalate when the state is ambiguous or no documented repair applies.

Do not edit either database, delete the checkpoint, force-resume the graph, or
change the accepted decision.

## Rollback

Set `DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL=false` and restart the backend.
Verify review endpoints return `durable_hitl_disabled`. Preserve all
application, checkpoint, output, decision, and unresolved workflow state.

Re-enable only after `doctor` passes and startup reconciliation succeeds with a
compatible version. Do not roll code across schema or checkpoint compatibility
boundaries without the existing backup and restore procedure.

## Non-Goals

P1C does not add a UI or React migration, RBAC or multi-user identity,
PostgreSQL, multiple replicas, claim editing, decision amendment, automatic
rerun, runtime Skills, or Async Subagents.
