# Run Execution Recovery Operations

This runbook covers the single-node SQLite crash-safety boundary introduced by
migration `010_run_execution_recovery`. It provides startup-only convergence,
not runtime monitoring. Release remains `hold`; implementation and proof do not
publish v0.1.7.

## Authority And Non-claims

The supported application holds one process-lifetime DB-scoped exclusive
writer gate. A private boot generation and owner fence protect each newly
running run. A later startup converts a previous boot's active owner and its
original source to immutable failed state:

- execution phase maps to `execution/execution_error`;
- finalization phase maps to `finalization/run_finalization_failed`.

Recovery is an explicit authenticated one-hop replacement. It creates a new
run, not resume, and may repeat provider or tool effects.

- No automatic retry.
- No automatic resume.
- No exactly-once execution.
- No heartbeat monitoring.
- No periodic scanner.
- No production HA.
- No distributed lock or leader election.
- No provider success.
- No business impact.
- No published v0.1.7.

The gate covers one supported local application lifespan. Repository helpers,
migrations, fixtures, and proof scripts expose direct APIs for isolated
tests/proofs only. Never run them against the live application DB; they do not
acquire application-lifespan writer authority.

## Upgrade

1. Stop all application writers.
2. Confirm the configured DB and dedicated migration backup path.
3. Start exactly one application writer.
4. Pure DB-path resolution validates lock support. On a clean checkout it may
   create only the missing canonical DB parent needed for the sibling lock.
5. The exclusive writer gate acquires immediately after parent validation and
   before DB, backup, output, probe, migration, boot, or worker mutation.
6. Migration `010_run_execution_recovery` creates its dedicated migration
   backup, applies, and verifies the schema and any exact pre-v1 running
   backfill.
7. Startup convergence activates a fresh boot before workers or requests.
8. Preserve the backup.

This is a stopped-writer upgrade. Do not start a second process while the first
still holds the gate.

## Writer Gate Diagnostics

### `run_execution_writer_already_active`

- Do not delete the empty lock file or retry in a loop.
- Identify the intended single application writer with operator tooling.
- Stop the duplicate, or finish the current writer's shutdown.
- Restart exactly one writer.

The empty sibling lock file is not a lease or PID file. Authority is the
kernel-held descriptor, and the OS releases it after process death.

### `run_execution_writer_unavailable`

- Do not bypass the gate with a PID file, timer, or environment flag.
- Verify supported Unix advisory locking and a safe private lock-file parent.
- On a clean checkout, verify the configured DB parent can be created and
  canonicalized without creating the DB or another runtime directory.
- Remediate the exact platform, file-type, or permission condition.
- Restart only after the production gate can acquire.

### Shutdown does not complete

- Do not start a successor while the old process still holds the gate.
- Inspect the blocked tracked task or finalizer without mutating DB authority.
- If deliberate termination is required, stop the process.
- The OS releases the descriptor; the next single writer performs
  startup-only convergence.

The application drains tracked tasks before writer release. Never release the
gate merely because request admission closed.

## Dedicated Backup Collision

If the fixed dedicated backup exists while the exact `010` marker is missing,
startup fails with `run_execution_recovery_backup_already_exists` without
overwriting either file:

1. Stop all writers.
2. Preserve diagnostic copies of the current DB and existing dedicated backup.
3. Verify backup schema, revision, provenance, and the current DB marker.
4. Choose one explicit operator-approved disposition.

### Verified pre-010 backup

1. Create and verify a named archival copy.
2. Restore that verified copy to the application DB, explicitly accepting
   loss of post-backup data.
3. Move the original fixed-path backup to a separate named archive.
4. Verify the fixed backup path is absent and both archive/readback are sound.
5. Retry so migration creates a fresh dedicated backup from the restored DB.

### Proven stale/wrong backup

1. Move the fixed-path file to a named archive.
2. Verify the fixed backup path is absent and the current DB is unchanged.
3. Retry, or choose a separately approved new application DB path.

Never delete, overwrite, or rename automatically. If the exact `010` marker is
already present, startup is verify-only; the retained backup is rollback
evidence, not a collision to erase.

## Explicit Replacement

An authorized caller sends exactly zero body bytes:

```text
POST /api/runs/{source_run_id}/retries
Idempotency-Key: required
```

`202 accepted` is not started, completed, or successful. The source remains
immutable failed. The response is `dra.run-recovery.v1`, and the post-commit
wake is best effort. Status/result endpoints are unchanged.

### Exact profile ID/version unavailable

- The source remains immutable failed and auditable.
- Restore the exact profile implementation and replay the same source/key; or
  inspect the source and deliberately create an unrelated ordinary keyed run
  from caller-retained input.
- Never substitute a newer profile inside recovery lineage.

### Replacement used as recovery source

- v1 is exhausted and creates no second hop.
- Inspect the source and existing replacement.
- If another attempt is deliberate, create an unrelated ordinary keyed run
  from caller-retained input.
- Never retry automatically or hide the ordinary-run boundary.

## Provider-Free Proof

Run only against isolated test-owned state:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/run_execution_recovery_proof.py check
```

The report is a provider-free real-process contract proof. It includes real
execution/finalization `SIGKILL`, stale-generation fencing, keyed replay,
migration restore, and exact old-revision verification. It is not a latency,
availability, completion, production reliability, or SLA measurement.

## Rollback

Rollback discards all post-backup data:

1. Stop all writers.
2. Preserve a diagnostic copy of the post-010 DB.
3. Obtain explicit approval for post-backup data loss.
4. Restore the complete pre-010 backup.
5. Verify exact old-revision source provenance in a fresh archive root.
6. Open and verify the restored DB only from that provider-disabled isolated
   root.
7. Only then accept writes.

Do not drop only the new tables.
Do not delete the migration marker.
Do not edit owner rows.
Do not copy replacement rows into the old schema.

The following verifier creates a fresh archived source root and checks both Git
object identity and isolated module provenance:

```bash
set -euo pipefail
: "${RESTORED_DB:?set the absolute path to the restored pre-010 database}"

ROLLBACK_REVISION="bfd744a5611c7673d9385a45bed0131d6cb47655"
ROLLBACK_EXPORT_ROOT="$(
  mktemp -d "${TMPDIR:-/tmp}/dra-rollback-source.XXXXXX"
)"

test "$(git rev-parse "${ROLLBACK_REVISION}^{commit}")" = \
  "${ROLLBACK_REVISION}"
git cat-file -e "${ROLLBACK_REVISION}^{commit}"
git archive --format=tar "${ROLLBACK_REVISION}" \
  | tar -x -C "${ROLLBACK_EXPORT_ROOT}"

(
  cd "${ROLLBACK_EXPORT_ROOT}"
  env \
    -u OPENAI_API_KEY \
    -u DEEPSEEK_API_KEY \
    -u TAVILY_API_KEY \
    PYTHON_DOTENV_DISABLED=1 \
    DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL=false \
    DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION=false \
    python3.11 -I - \
    "${ROLLBACK_EXPORT_ROOT}" \
    "${RESTORED_DB}" \
    "${ROLLBACK_REVISION}" <<'PY'
import importlib
import json
from pathlib import Path
import sys

export_root = Path(sys.argv[1]).resolve()
restored_db = Path(sys.argv[2]).expanduser().resolve()
expected_revision = sys.argv[3]

for name in tuple(sys.modules):
    if name == "api" or name.startswith("api."):
        del sys.modules[name]
sys.path.insert(0, str(export_root))

migrations = importlib.import_module("api.run_migrations")
repository = importlib.import_module("api.run_repository")
for module in (migrations, repository):
    module_path = Path(module.__file__).resolve()
    if module_path != export_root and export_root not in module_path.parents:
        raise SystemExit("rollback_source_identity_invalid")

migrations.verify_run_schema(db_path=str(restored_db))
print(
    json.dumps(
        {
            "revision": expected_revision,
            "source_identity": "verified_export_root",
            "status": "verified",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
)
PY
)
```

The verifier must print one public-neutral JSON line and no traceback. Preserve
the export root and diagnostic DB copy until the rollback decision is
accepted. Any cleanup is a separate authorized action.
