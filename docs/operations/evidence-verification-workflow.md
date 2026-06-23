# Controlled Evidence Verification Workflow

## Supported Boundary

P2A Evidence verification is default-disabled and supports one backend replica,
one persistent application SQLite database, one separate persistent checkpoint
SQLite database, persistent output storage, one configured API credential, and
the existing durable review worker.

It adds no UI, RBAC, multi-user identity, PostgreSQL, multiple replicas,
automatic source retrieval, browser action, LLM verification, runtime Skills,
Async Subagents, or real-source proof.

## Enable

Set canonical variables only:

```dotenv
DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL=true
DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION=true
API_SECRET=<configured out of band>
TASKS_DB_PATH=/app/data/tasks.db
DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH=/app/data/review_checkpoints.db
```

The two SQLite paths must be persistent, distinct, and writable. Before the
publication migration, startup creates one transactionally consistent,
immutable application-database backup. Once the migration marker exists,
restart only verifies schema and never overwrites that backup. If the marker is
missing while the configured backup already exists, startup fails closed with
`publication_migration_backup_already_exists`; an operator must determine which
database/backup pair is authoritative instead of allowing automatic overwrite.
Keep the backup, checkpoint database, and output storage together for recovery.

Verify readiness:

```bash
python tools/decision_research_agent_tool.py doctor
```

`evidence_verification.status` is `disabled`, `ok`, or `failed`.

## Operate

List and inspect immutable Evidence:

```bash
python tools/decision_research_agent_tool.py evidence list \
  --run-id "$RUN_ID"

python tools/decision_research_agent_tool.py evidence show \
  --run-id "$RUN_ID" \
  --evidence-id "$EVIDENCE_ID"
```

Evidence list uses SQL keyset pagination. Evidence detail returns at most the
latest 100 human decisions in the compatible `decisions` field and includes
`decision_history` metadata with the fixed limit, returned count, truncation
flag, and returned revision boundary.

Verify an exact persisted fingerprint only after comparing it to the identified
source:

```bash
python tools/decision_research_agent_tool.py evidence verify \
  --run-id "$RUN_ID" \
  --evidence-id "$EVIDENCE_ID" \
  --confirm-source-match
```

`human_verified` means the authenticated operator confirmed that the persisted
snippet for that exact fingerprint matched the identified source at decision
time. It is not universal truth, claim approval, or a guarantee against later
source drift.

Reject without placing the note in shell history:

```bash
python tools/decision_research_agent_tool.py evidence reject \
  --run-id "$RUN_ID" \
  --evidence-id "$EVIDENCE_ID" \
  --reason-code content_mismatch \
  --reason-file "$REASON_FILE"
```

`--reason-stdin` is also supported. Reads are bounded to 1000 characters and
fail closed on overflow, invalid UTF-8, or I/O failure.

Finalize the changed effective state:

```bash
python tools/decision_research_agent_tool.py evidence finalize \
  --run-id "$RUN_ID"
```

Finalization creates or reuses one immutable snapshot. A changed snapshot
creates revisioned DecisionBrief artifacts and a fresh durable review. Approve
that review through the existing `review approve` command.

If persisted packet or snapshot JSON is invalid, finalization fails with a
bounded JSON error such as `publication_packet_state_invalid` or
`verification_snapshot_invalid`. The response does not expose traceback,
database paths, or raw exception text.

## States and Recovery

- A new accepted verification decision atomically changes the current
  publication to `stale`, clears its current pointer, and changes an active
  workflow to `superseded`.
- Finalization creates a new current publication in `review_required`.
- Fresh approval changes only that current publication to `ready`.
- Fresh rejection changes it to `blocked`.
- Only `is_current=1 AND status=ready` is deliverable.

`stale` publications and `superseded` workflows remain immutable audit history.
They are never resumed or selected as current delivery. A restart may recover a
`checkpoint_pending` current workflow; ambiguous checkpoint state still becomes
`manual_recovery`.

## Rollback

Set:

```dotenv
DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION=false
```

Restart the backend and verify the verification endpoints return
`evidence_verification_disabled`. Preserve all application, checkpoint, output,
decision, snapshot, artifact, review, and publication state. Do not edit the
databases or delete historical revisions.

Re-enable only after `doctor`, the 13-item durable gate, and the synthetic
verification-to-approval container canary pass.
