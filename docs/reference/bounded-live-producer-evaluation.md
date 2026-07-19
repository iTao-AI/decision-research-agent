# Bounded Live Producer Evaluation

The bounded live producer evaluation is an application-owned proof harness for
one fixed `generic` research scenario. It binds a clean tracked source archive,
an isolated loopback Compose project, the protected DRA create/status/result
surface, application-owned persistence, canonical downstream projection,
backend restart, same-key replay, and exact task-owned cleanup.

Implementation availability proves deterministic contracts and a provider-free
Docker lifecycle only. No provider-backed observation claim is valid until an
operator separately authorizes one `observe-live` run and a later review accepts
the generated evidence.

## Provider-Free Contract Check

The required CI entrypoint is:

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/bounded_live_producer_proof.py check
```

`check` is credential-free, provider-free, Docker-free, external-network-free,
and import-silent for the Agent runtime. It validates the checked-in manifest,
report/error schemas, canonical serialization, output policy, failure registry,
and fixed boundaries. Success prints exactly one canonical JSON line with mode
`provider_free`, schema `dra.bounded-live-producer-manifest.v1`, and status
`valid`.

## Separately Authorized Live Command

`observe-live` is never a CI command. Before running it, the operator must
approve the source commit and manifest, provider and model declarations, the
fixed request, one DRA run intent, estimate-only cost treatment, and the total
wall-clock limit of 3,450 seconds.

The credential file must be external to the repository, owned by the current
user, a regular single-link non-symlink file, readable only by that user, no
larger than 64 KiB, and owner-only mode `0400` or `0600`. Files inside the source
checkout, hard links to another path, or files in another worktree of the same
Git repository are rejected. The validated bytes become one private in-memory
snapshot. Each Compose command receives a new owner-read-only, single-link
ephemeral file in a private random directory outside the repository and task
tree. The harness revalidates its inode and exact bytes after the command and
verifies the original pathname's directory identity before and after the
command, then removes the file before the next command. Cleanup retains
descriptor-based directory identity across path rename or symlink replacement
and keeps failed removal authority for a close retry. Replacing or editing the
original path cannot change later commands, while observed command-local
replacement or mutation fails closed. These checks bind accepted harness
results; they do not claim kernel-level pathname immutability against the
invoking user. The snapshot is never added to the tracked archive or task tree,
and no credential value or secret-derived digest is printed or published. The
file's allowed keys are closed. Required non-empty entries cover provider,
model, process API, search, and MySQL configuration; benchmark, durable review,
Evidence verification, and LangSmith tracing must be `false`; LangSmith
input/output hiding must be `true`; LangSmith and RAGFlow credential values must
be empty. The process `DECISION_RESEARCH_AGENT_API_KEY` must exactly match the
file's `API_SECRET` without either value being printed.

The command shape is:

```bash
chmod 600 "$DRA_BOUNDED_ENV_FILE"
PYTHON_DOTENV_DISABLED=1 \
DECISION_RESEARCH_AGENT_API_KEY="$DRA_PROCESS_API_KEY" \
python scripts/bounded_live_producer_proof.py observe-live \
  --env-file "$DRA_BOUNDED_ENV_FILE" \
  --provider-id "$DRA_PROVIDER_ID" \
  --provider-base-url "$DRA_PROVIDER_BASE_URL" \
  --primary-model-id "$DRA_PRIMARY_MODEL_ID" \
  --fallback-model-id "$DRA_FALLBACK_MODEL_ID"
```

The provider base URL must be public HTTPS with no credentials, query, fragment,
or unapproved path. Its host must be canonical ASCII public DNS or a canonical
public IP address; loopback/private addresses and numeric or Unicode address
aliases fail closed without DNS lookup. The declarations must match the
external file. Optional `--pricing-basis` and `--currency` must be supplied
together and match a canonical, runtime-compatible per-model pricing map plus
the public basis/currency declaration in that file. These fields validate input
compatibility; they do not by themselves authorize observed cost.
`--retain-task-images` is an operator-local cleanup choice and never enters the
public report.

The command accepts no query, scope, output path, project name, API key, retry,
fixture, or Compose override option.

## Source, Lifecycle, And Deadlines

The harness refuses a dirty source tree. One captured commit SHA drives the
tree, tracked-file list, archived `VERSION`, and `git archive`; mutable `HEAD`
and source status are revalidated before mutation and after archive validation.
It records the exact commit, tree, `VERSION`, tracked archive and manifest
hashes, sanitized Compose hash, built image identity, and bounded
Docker/Compose versions. The build context is the extracted tracked archive,
not the mutable checkout.

The managed lifecycle is:

```text
probe -> validate -> archive -> build/start -> health -> protected create
-> terminal projection -> usage -> backend restart -> health -> persistence
-> exact same-key replay -> cleanup -> paired publication
```

Docker receives unique project ownership and engine-assigned loopback ports.
The harness inspects the current backend binding again after restart before it
rebuilds the HTTP client. It never publishes local ports or Docker resource
names and never performs a global prune or prefix-based delete.

One monotonic 3,450-second outer deadline starts before input and credential
validation. Non-cleanup work is limited to the first 3,330 seconds: the Docker
probe has a 30-second child bound, the active lifecycle has a 3,300-second child
bound, and its build, research, and restart/replay children retain their
1,200/1,800/300-second caps. Cleanup has an independent 120-second child reserve
that remains inside the outer wall time. Report serialization and publication
use only time left after cleanup; expiration blocks output before mutation. No
retry or child phase receives a fresh budget. Subprocess termination,
process-group wait, descendant termination, stream draining, and pipe closure
all consume the same remaining authority.

The validated credential snapshot is closed on every path after successful validation.
Before project cleanup takes ownership, the harness records the exact random task-temp path; a
probe, snapshot, project-construction, ownership-transition, or deadline failure removes only that
path through a cleanup child contained in the outer 120-second reserve. Once project cleanup takes
ownership, the normal exact project receipt remains authoritative.

## Accepted Public Contract

The accepted terminal tuple is exact:

```text
execution_status = completed
review_status    = not_required
delivery_status  = ready
failure_cause    = null
profile_id       = generic
```

The canonical result must keep the original run/thread/segment identities and
the `research-report.md` Markdown artifact with an exact persisted SHA-256. The
existing downstream projection must return consumer support `supported` and
disposition `accept_draft`.

At least one and at most 100 run-level Evidence rows are accepted. Every raw
Evidence row must match the accepted `run_id` and `segment_id` before consumer
projection; foreign or missing ownership fails closed. Evidence IDs must be
unique, source identities non-empty, and source URLs public HTTPS. At least one
cited row must match every manifest-required domain. Ordered Evidence must
remain byte-identical across restart. The report includes only the current
consumer allowlist; it omits query text, snippets, tool/provider payloads,
artifact content, private paths, credentials, logs, raw errors, and traces.
Recorded or cited Evidence is candidate research Evidence, not independently
verified truth and not authorization for a downstream business decision.

Usage is either `observed` or `not_observed`, and token totals may be observed.
In Change 1, `cost_estimate` remains `not_observed` because the aggregate usage
endpoint cannot bind tokens and cost to the exact per-call model and rate. A
declaration or runtime-compatible pricing map alone is insufficient; missing or
unknown response models and default-fallback attribution also fail closed.
Search-provider cost remains `not_observed`; the report is not a billing record
or a hard currency cap.

After restart, the harness requires identical identities, terminal state,
ordered Evidence, artifact metadata/hash, and `supported` / `accept_draft`
disposition. The exact original request and idempotency key must then return
`idempotent_replay=true` without state or artifact mutation.

## Outputs And Evidence Status

Successful live observation may publish only these two previously absent paths:

```text
docs/evidence/bounded-live-producer-v1.json
docs/evidence/bounded-live-producer-v1.md
```

Markdown is linked first as a deterministic projection; JSON machine authority
is linked last. JSON is acceptable only when the matching Markdown path exists,
the final directory `fsync` succeeds, the command reports success, and the pair
is later accepted through a reviewed evidence-only change. A JSON path alone is
never authority, and a failure before its final link cannot leave machine
authority even if rollback operations fail. Rollback removes run-created links
when the filesystem permits it without touching pre-existing paths. An
unremovable Markdown-only residue is non-authoritative and blocks a later
overwrite; rollback failure never replaces the stable primary output error. No
live report is committed by this implementation change.

## Stable Failure Taxonomy

Failures use one single-line JSON object on stderr, empty stdout, exit code 1,
and only stable schema, code, phase, retryability, and cleanup status fields.

| Phase | Stable codes |
|---|---|
| Input | `manifest_invalid`, `source_dirty`, `source_identity_invalid`, `credential_source_invalid`, `output_invalid` |
| Docker | `docker_unavailable`, `compose_config_invalid`, `source_archive_invalid`, `image_build_failed`, `service_start_failed`, `service_identity_invalid` |
| Create | `create_rejected`, `create_response_invalid`, `create_identity_mismatch`, `create_reconciliation_unresolved` |
| Observe | `run_observation_deadline`, `run_state_invalid`, `run_failed`, `run_fallback_rejected`, `run_delivery_not_ready` |
| Result | `consumer_projection_invalid`, `artifact_invalid`, `artifact_hash_mismatch` |
| Evidence | `evidence_missing`, `evidence_invalid`, `evidence_domain_rejected`, `required_cited_domain_missing` |
| Usage | `usage_invalid` |
| Restart | `backend_restart_failed`, `restart_identity_drift`, `restart_evidence_drift`, `restart_artifact_drift` |
| Replay | `idempotent_replay_invalid`, `duplicate_run_observed` |
| Output | `report_invalid`, `output_exists`, `output_write_failed` |
| Cleanup | `cleanup_failed` |
| Internal | `evaluation_internal_error` |

Unknown exceptions map to `evaluation_internal_error`; raw exceptions and
tracebacks never enter public output. A primary plus cleanup failure preserves
both causes locally while projecting the stable primary code with failed
cleanup status. Malformed provider, model, pricing, or credential declarations
fail as `credential_source_invalid` in the `input` phase before Docker or
provider mutation. Unknown and interruption paths use the same single-line
envelope and report the cleanup status actually reached.

## Rollback And Non-Claims

Rollback is a source revert of this harness and its documentation. An in-flight
failure still uses the bounded ownership receipt to remove only task-owned
containers, volumes, networks, temporary paths, and image tags. Each temporary
root, image tag, and standalone container name is recorded before the mutation
that can leave it behind. A cleanup inventory refresh failure does not skip
already-recorded `down` or exact-removal attempts, and an unclaimed namespace
never triggers project-wide cleanup. Successful exact resource inventories,
not a failed inspection exit status, prove that recorded resources are absent.
Existing evidence paths are never overwritten or deleted by the harness.

This contract is producer-only. It is not accepted source truth, a business
decision, provider-side exactly-once behavior, externally exactly-once
execution, general durability, a billing record, provider-quality proof,
research-quality proof, a hosted deployment, multi-tenant readiness, an SLA, or
a release/deployment certification. In particular, it is not exactly-once
execution and does not make Tool Client, REST/OpenAPI, database schema, Agent
runtime, LangGraph, LangSmith, or the frontend a new business authority.
It is not a hosted deployment and provides no multi-tenant or SLA guarantee.
