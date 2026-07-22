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

The command accepts no query, scope, arbitrary output filename, general output
root, project name, API key, retry, fixture, or Compose override option.

## Opt-In Diagnostic Receipts

The live command accepts one optional operator-only argument,
`--diagnostic-dir <owner-only repo-external directory>`. It selects a
pre-existing directory, not a filename. The writer selects one fixed basename
from the closed table below; this exception does not permit an arbitrary
filename or general output root.

| Eligible primary | Selected receipt | Fixed basename |
|---|---|---|
| `consumer_projection_invalid / result` | Result Diagnostic Receipt v1 | `bounded-live-producer-result-diagnostic-v1.json` |
| `run_failed / observe` | Run Failure Diagnostic Receipt v1 | `bounded-live-producer-run-failure-diagnostic-v1.json` |

The command publishes at most one receipt after final cleanup. The preflight rejects
the directory if either fixed filename already exists. Both formats are
canonical UTF-8 JSON bounded to 4 KiB, and the resulting regular file is mode
`0600`. The directory must be absolute, owner-only, repo-external, owned by the
current user, free of symlink traversal, and identity-stable for the command
lifetime. Publication is non-overwriting and uses the selected fixed basename
only. The invoking UID may modify the operator-owned file during or after
publication, so this sink does not claim same-UID pathname immutability. Every
consumer must strictly validate the receipt before use; each receipt remains a
non-authoritative operator diagnostic.

### Result Diagnostic Receipt v1

The receipt uses schema `dra.bounded-live-producer-result-diagnostic.v1`. It is
eligible only for a final `consumer_projection_invalid` failure in phase
`result`; the existing public error envelope remains unchanged. Result
Diagnostic Receipt v1 remains byte- and behavior-compatible. Its bounded
classification records one of these stages without retaining the response or
exception text:

| Stage | Exact reasons |
|---|---|
| `connection` | `connection_failed` |
| `response_status` | `response_status_invalid` |
| `response_body` | `response_read_failed`, `response_size_exceeded` |
| `response_json` | `response_utf8_invalid`, `response_json_invalid`, `response_not_object` |
| `response_identity` | `run_identity_mismatch` |
| `consumer_contract` | `contract_result_invalid`, `contract_schema_invalid` |
| `projection_disposition` | `projection_disposition_invalid` |

### Run Failure Diagnostic Receipt v1

Terminal observation is status-before-result: requested run, thread, and profile
identity is validated before terminal classification. No failed, fallback,
delivery-blocked, or malformed terminal state requests `/result`. Only an exact
`completed / ready` status continues to one result request.

The sibling receipt uses schema
`dra.bounded-live-producer-run-failure-diagnostic.v1`. It is eligible only for
`run_failed / observe`, and `cleanup_status` is exactly `succeeded` or `failed`.
It validates the observed `dra.run-failure-cause.v1` projection against the
application-owned `RUN_FAILURE_CAUSE_CODES` matrix:

| Application phase | Exact application codes |
|---|---|
| `dispatch` | `run_dispatch_lease_expired`, `run_dispatch_schedule_failed`, `run_dispatch_start_failed`, `run_dispatch_start_timeout` |
| `execution` | `call_budget_exceeded`, `cancelled`, `execution_error`, `invalid_research_packet`, `missing_research_packet`, `recursion_limit_exceeded`, `run_timeout` |
| `finalization` | `cancelled`, `run_finalization_failed`, `run_timeout` |

The run-failure receipt contains no raw body or content, run, thread, or segment
identity, timestamp, HTTP status or byte count, provider or model identity, or
path, log, trace, or credential material. Result diagnostics continue to omit
raw response bodies, artifact and Evidence content, URLs, credentials, provider
payloads, and exception text.

A successful observation, a more precise stable failure, an omitted diagnostic
option, or the provider-free `check` command creates no receipt. Neither receipt
is application authority. Each receipt is not live evidence, canonical result
authority, Evidence authority, or downstream business authority. A receipt does
not authorize a retry. Each eligible receipt is written after cleanup so its
cleanup status is final. A best-effort publication failure never replaces the
primary public failure. This targeted addition makes no API, database, Agent
runtime, canonical result, Evidence, dependency, VERSION, or release change.
Any later provider-backed use requires a separately authorized one-shot live
observation.

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
The existing secure-local-runtime proof runs inside the exact locked backend
image after build and before any service or provider activity. The provider-free
fixture and separately authorized live paths use this same precheck authority,
with no network, all capabilities dropped, `no-new-privileges`, a read-only
`/proof` source mount, and bounded `data` / `output` tmpfs mounts. The invoking
host's production dependency graph is not archive-validation authority.
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
| Result | `run_fallback_rejected`, `consumer_projection_invalid`, `artifact_invalid`, `artifact_hash_mismatch` |
| Evidence | `evidence_missing`, `evidence_invalid`, `evidence_domain_rejected`, `required_cited_domain_missing` |
| Usage | `usage_invalid` |
| Restart | `backend_restart_failed`, `restart_identity_drift`, `restart_evidence_drift`, `restart_artifact_drift` |
| Replay | `idempotent_replay_invalid`, `duplicate_run_observed` |
| Output | `report_invalid`, `output_exists`, `output_write_failed` |
| Cleanup | `cleanup_failed` |
| Internal | `evaluation_internal_error` |

A structurally valid fallback result maps to `run_fallback_rejected` in the
`result` phase. Malformed result or consumer projection data remains
`consumer_projection_invalid`; terminal-state fallback remains
`run_fallback_rejected` in the `observe` phase. Only an exact canonical `409`
`run_result_unavailable` envelope with bounded keys and types,
`retryable=true`, and the requested `run_id` maps to `artifact_invalid`.
Other transport, HTTP, JSON, envelope, and result-contract failures remain
`consumer_projection_invalid`. `contract_artifact_invalid` maps to
`artifact_invalid` in the `result` phase, while defensive
`contract_state_invalid` maps to `run_state_invalid` in the `observe` phase.

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

## Opt-In Limiter Diagnostic Sidecar

The bounded producer alone may enable
`DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_LIMITER_DIAGNOSTICS=true`. The mode is
default-disabled; absence writes nothing, and any present value other than exact lowercase
`true` fails during configuration validation. It does not change base Compose or ordinary runtime
configuration.

When native framework call-limit exceptions reach the existing outer harness boundary, the
application may project only these seven closed limiter fields: `limiter_kind`, `tool_scope`,
`run_count`, `run_limit`, `thread_count`, `thread_limit`, and `agent_role`. Model limits use
`tool_scope=not_applicable`; tool limits use only `all_tools` or `task`. Unknown tool names produce
no diagnostic. `agent_role` remains `not_observed`; there is no role inference.

The internal `dra.call-budget-origin-sidecar.v1` object is written only to:

```text
/app/output/operator-diagnostics/<run_id>/call-budget-v1.json
```

It is canonical JSON, at most 4096 bytes, in a mode-`0600` owner-owned regular file. It contains no
prompt, query, scope, provider/model identity, arbitrary tool name, tool input/output, Evidence,
artifact content, credential, URL, exception text, traceback, or caller-selected path. Writer
failure never replaces the application terminal cause.

After exact application cause `execution/call_budget_exceeded`, the evaluator proves the one full
backend container ID and its task-owned `<project>_backend_output` named volume before and after
the fixed direct invocation:

```text
python /app/scripts/bounded_live_producer_runtime_diagnostics.py read --run-id <run_id>
```

The reader uses descriptor-relative `O_NOFOLLOW`, verifies owner, mode, link count, size and open
file identity, and emits only strict canonical bytes. The host validates those bytes again and
keeps only the typed value in memory. Missing, invalid, ambiguous, or drifted state means
`not_observed`; it does not change the primary failure. No shell, `docker compose cp`, arbitrary
path, host copy, retained failed container, or retained output volume is permitted.

A valid value selects `dra.bounded-live-producer-call-budget-diagnostic.v1` at the fixed operator
filename `bounded-live-producer-call-budget-diagnostic-v1.json`. It contains the existing
`run_failed/observe` primary, exact application run-failure cause, and the seven limiter fields.
Exactly one of result-boundary, generic run-failure, or call-budget receipt can be published, and
publication occurs after final cleanup. The owner-only sink remains non-overwriting, inode-bound,
bounded and best effort.

This is operator-only diagnostic transport: there is no API, database, or public failure contract change;
no model or budget change; no role inference; no LangSmith authority; and no successful live-provider evidence claim.
The receipt is not Evidence, application authority, billing data, or
proof of research quality. It does not authorize an automatic retry or any budget/model adjustment.
