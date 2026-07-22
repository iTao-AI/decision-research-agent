# Bounded Live Producer Evaluation v1 Design

## Status

Approved on 2026-07-18 for mechanical public landing and implementation planning.
This document does not authorize implementation, provider credentials, a live provider run,
network cost, push, pull request creation, merge, release, tag, deployment, or publication of
evidence.

Planning baseline: Decision Research Agent `v0.1.5` at
`9791f649b3a0f3f26f7e7ff949c3ae3a86530d97`.

Candidate release: `v0.1.6` only after the harness has merged, one separately authorized live
observation has succeeded, its sanitized evidence has been reviewed and merged, and release
preparation has passed its own gate.

## Summary

Decision Research Agent already has the individual production-path capabilities needed by an
external Agent consumer: secure loopback Compose, idempotent run creation, durable pre-start
dispatch, bounded terminal failure causes, run-level Evidence, canonical generic Markdown,
restart-safe application persistence, a strict downstream consumer projection, and deterministic
regression gates. The missing evidence is not another runtime contract. It is one bounded proof
that these capabilities work together during a real provider-backed run from an exact source
identity.

This design adds a public-safe evaluation harness with two deliberately separate modes:

```text
provider-free check
  -> strict contracts, manifest, serializers, lifecycle fakes, and Docker lifecycle tests

separately authorized observe-live
  -> exact tracked source archive
  -> isolated loopback Compose
  -> one generic run intent with one idempotency key
  -> current status + canonical result + run-level Evidence
  -> existing downstream consumer projection
  -> backend restart and persistence comparison
  -> exact same-key create replay
  -> sanitized bounded evidence report
  -> bounded cleanup
```

The implementation does not change the REST API, database, canonical result, Evidence schema,
LangGraph or DeepAgents authority, public Tool Client contract, or product-specific business
authority. It proves the DRA producer boundary only. A separate consumer repository may later use
the resulting released producer contract in its own governed proof.

## Inspected Baseline

The design was finalized against a clean repository with:

- `main == origin/main == 9791f649b3a0f3f26f7e7ff949c3ae3a86530d97`;
- annotated `v0.1.5` peeled to the same commit and a public non-prerelease GitHub Release;
- no open pull requests and only the primary worktree;
- `VERSION=0.1.5`;
- exact `/health` identity
  `{"status":"ok","service":"decision-research-agent"}`;
- loopback-only dynamic Compose host ports, required API and MySQL secrets, declared backend and
  MySQL health checks, dropped backend capabilities, and `no-new-privileges`;
- keyed `POST /api/runs` acceptance and same-request replay with durable reconciliation;
- durable pre-start dispatch intent, lease fencing, three-attempt convergence, and stable terminal
  failure causes;
- `GET /api/runs/{run_id}` as the bounded run, Evidence, review, delivery, and failure-cause
  projection;
- `GET /api/runs/{run_id}/result` as the canonical application-owned artifact authority;
- `GET /api/token-usage/runs/{run_id}` as a process-local summary whose cost is a static pricing
  estimate rather than a provider invoice;
- `scripts/downstream_consumer_contract.py::project_consumer_case` as the current strict generic
  consumer projection with a 1 MiB artifact bound and public-HTTPS Evidence rules;
- server-owned generic DeepAgents/LangChain middleware budgets; and
- existing deterministic evaluation, consumer, run-creation, dispatch, failure-cause, secure
  runtime, and release proof patterns.

The public Tool Client preserves the correct create request and exposes create, status, result,
and polling operations, but its current standard-library transport is not the authority for this
proof because the proof additionally requires explicit no-redirect and no-proxy behavior. The
design reuses its request semantics and stable API contracts without changing its public surface.

## Problem

Current evidence proves important slices independently, but it does not prove the integrated
claim an operator or downstream Agent cares about:

> An exact DRA source revision can run one bounded real research execution through the supported
> local service, persist a canonical result and public Evidence, survive a backend restart, and
> reconcile the original create intent back to the same run identity.

The existing deterministic fixtures cannot establish provider-backed execution. A manual demo
cannot establish exact source identity, restart behavior, idempotent reconciliation, public-safe
serialization, or repeatable acceptance criteria. A live script that prints a report or Docker
logs would also create privacy and credential risks without producing a durable contract.

This proof must therefore join five already-owned authorities without creating a sixth:

1. Git owns the exact tracked source identity.
2. Docker Compose owns the isolated local process lifecycle.
3. The DRA application database owns run, dispatch, Evidence, and artifact state.
4. The DRA REST contract owns the consumer-visible projection.
5. The proof owns only bounded observation, validation, sanitization, and cleanup.

## Product Decision

Implement one managed-Compose, bounded live producer evaluation harness with schema
`dra.bounded-live-producer-evaluation.v1`.

The harness must be useful in three states:

- required CI can validate every deterministic contract without credentials or a provider;
- an operator can separately authorize exactly one managed live run intent from a clean commit;
- a reviewed successful live report can later be committed as evidence without raw research
  content, credentials, logs, tracebacks, local paths, or private source data.

The proof accepts only the existing `generic` profile and the existing canonical
`research_report_markdown` result. It requires at least one cited public HTTPS Evidence entry. A
completed run without that Evidence is a valid DRA execution but an unsuccessful evaluation
observation because it cannot support the intended downstream Evidence boundary.

## Goals

1. Bind one live observation to an exact clean Git commit, tree, tracked source archive, VERSION,
   sanitized Compose configuration, and built backend image.
2. Start the exact source through the supported secure local Compose topology using unique project
   ownership and engine-assigned loopback ports.
3. Submit one public-safe generic research request with one high-entropy idempotency key.
4. Preserve the exact request and key across at most one ambiguous-create reconciliation.
5. Observe terminal status, canonical result, run-level Evidence, and process-local usage through
   the existing protected REST API.
6. Validate the result with the existing downstream consumer projection rather than a second
   canonical contract.
7. Require one non-fallback deliverable artifact and at least one cited public HTTPS Evidence row.
8. Restart the backend and prove that application-owned status, Evidence order, and artifact
   identity remain stable.
9. Replay the exact create request and require the original run identity without authorizing a
   second run intent.
10. Emit only a strict, bounded, public-safe JSON report and deterministic Markdown projection.
11. Preserve primary and cleanup failure causes without leaking raw exceptions or Docker output.
12. Keep live execution explicit, separately authorized, cost-bounded by one run intent and the
   existing server call limits, and absent from required CI.

## Non-Goals

For Change 1, this stage does not add or claim:

- a downstream product decision, domain-specific consumer, human verification, business approval,
  or product adoption;
- a new REST path, response field, schema version, database table, migration, profile, or result
  kind;
- typed generic findings, a second canonical outcome, Markdown claim extraction, or Evidence
  reinterpretation;
- exactly-once Agent execution, provider/tool side-effect exactly-once, running-execution recovery,
  or multi-instance high availability;
- server-side cancellation when the client observation deadline expires;
- durable token usage, durable cost, a provider invoice, a hard dollar budget, billing
  reconciliation, or LangSmith billing authority;
- source truth, factual correctness, complete web coverage, independent source verification, or
  domain acceptance merely because DRA recorded `citation_status` or `verification_status`;
- hosted deployment, TLS, identity, RBAC, multi-tenancy, anonymous public research, or an SLA;
- a new Codex Skill, MCP adapter, Tool Client API, Agent middleware, subagent topology, memory,
  checkpoint authority, or framework migration;
- arbitrary provider URLs, arbitrary credential sources, arbitrary Compose files, arbitrary Docker
  projects, arbitrary filesystem roots, or arbitrary output paths;
- live-provider execution in required CI or automatic provider retry; or
- a new release before successful reviewed live evidence exists.

## Existing Authorities And Reuse

| Surface | Reused authority | Evaluation responsibility |
|---|---|---|
| Source | Git commit, tree, tracked files, VERSION | Create and hash an exact tracked archive; reject dirty or ambiguous source |
| Local runtime | checked-in Compose, Dockerfile, secure runtime contracts | Start only the approved services with unique ownership and loopback ports |
| Credentials | operator-owned environment and Compose env file | Check presence and safe file properties; never publish values or derived secret digests |
| Run creation | current keyed `POST /api/runs` contract | Preserve exact key and canonical request; reconcile only an ambiguous acknowledgement |
| Dispatch | application ledger, worker, lease, and start fence | Observe only public state; do not inspect or replace private dispatch authority |
| Result | `GET /api/runs/{run_id}/result` | Require the existing generic canonical artifact and exact content hash |
| Evidence | run-status Evidence projection | Apply current downstream public-HTTPS and field validation; do not promote verification |
| Consumer | `project_consumer_case` | Reuse its state/result/Evidence projection and disposition |
| Usage | process-local token collector | Record observed totals or `not_observed`; label cost as estimate |
| Restart | Compose backend service lifecycle and application volume | Compare public state before and after restart |
| Proof | strict Pydantic contracts and serializers | Own observation acceptance and public-safe output only |
| LangGraph / DeepAgents / LangChain | existing research runtime and server-owned call limits | No new lifecycle, business, or proof authority |
| LangSmith | optional diagnostics | Not an acceptance, persistence, factual, or billing source |

The harness is application-owned Python code because its lifecycle begins before Agent invocation
and ends after container cleanup. LangChain, DeepAgents, and LangGraph do not provide the Git,
Docker, credential, idempotency-reconciliation, restart, or public-artifact authority required
here. Pydantic strict models, the current runtime, and the current consumer projection are reused
where their semantics match.

## Components

The implementation plan should refine exact filenames, but the feature is expected to add these
bounded surfaces:

1. `benchmarks/bounded-live-producer-v1/manifest.json`
   - checked-in public-safe research scenario and exact acceptance policy;
   - generic profile only;
   - exact required cited source domains;
   - fixed request, response, Evidence, deadline, and report bounds;
   - no credential, provider URL, local path, or live observation.
2. `scripts/bounded_live_producer_contracts.py`
   - strict Pydantic manifest and report models;
   - exact discriminated observation variants;
   - public-safety validation;
   - deterministic JSON and Markdown serialization.
3. `scripts/bounded_live_producer_proof.py`
   - `check`: provider-free deterministic contract gate;
   - `observe-live`: separately authorized managed-Compose observation;
   - stable one-line JSON CLI failures, bounded reads, import silence, and atomic non-overwrite
     output.
4. Focused unit and integration tests
   - deterministic transport, lifecycle, mutation, serialization, and cleanup matrix;
   - required Docker lifecycle with no provider research.
5. Public reference and evidence documentation
   - the harness PR documents the contract and non-claims;
   - a later evidence-only change may add the successful live JSON and Markdown report.

No committed file may be named or described as live evidence until it was produced by a successful
`observe-live` execution and independently reviewed. Deterministic CI fixtures must use names and
wording that identify them as contract fixtures, not provider observations.

## Manifest Contract

The checked-in manifest is public and immutable for v1. It contains exactly:

- schema version and scenario ID;
- profile ID `generic`;
- a bounded public research question;
- a bounded canonical JSON scope;
- an ordered set of required cited public source domains;
- required terminal state and canonical artifact kind/media type;
- minimum and maximum Evidence counts;
- exact request, response, artifact, report, and lifecycle bounds;
- usage observation policy;
- output policy and non-claims.

The v1 research question is:

> Using official Python documentation and Python Enhancement Proposals, compare the principal
> deployment benefits, compatibility limits, and operational caveats of the optional
> free-threaded CPython 3.13 build. Produce a concise decision brief for a backend team evaluating
> a bounded pilot, cite factual claims, and state unresolved limitations.

The v1 canonical scope is the empty JSON object. The two required cited source domains are
`docs.python.org` and `peps.python.org`. This is an evaluation acceptance rule, not a claim that the
generic runtime enforces a search-domain allowlist. Additional Evidence is accepted only when it
passes the existing public-HTTPS consumer contract. The manifest contains no private project,
user, customer, or business data.

V1 manifest bounds are:

| Item | Bound |
|---|---|
| Query | 1 through 4,096 UTF-8 bytes after exact newline normalization |
| Canonical scope JSON | at most 16 KiB, maximum depth 8, maximum 256 aggregate nodes |
| Required cited source domains | 1 through 8 exact lowercase DNS names; no wildcard or IP literal |
| Idempotency key | current 8-128 ASCII contract; generated with at least 128 bits of entropy |
| Tracked source archive | at most 64 MiB, at most 4,096 members, no member larger than 16 MiB |
| One subprocess stdout or stderr stream | at most 1 MiB retained; excess fails closed or is discarded by an approved quiet mode |
| One HTTP response | at most 2 MiB before JSON parsing |
| Canonical artifact | 1 through 1 MiB UTF-8 bytes, matching the existing consumer contract |
| Evidence | 1 through 100 ordered rows |
| Public JSON report | at most 1 MiB |
| Public Markdown report | at most 1 MiB |

The proof computes and publishes the canonical request SHA-256 and manifest SHA-256. It does not
repeat the research question or scope in the report. The manifest remains the reviewable public
input authority.

## Credential And Operator Boundary

`observe-live` requires two separate operator-owned inputs:

1. a Compose env file outside the repository containing the service, database, and provider
   configuration required by the checked-in Compose contract; and
2. `DECISION_RESEARCH_AGENT_API_KEY` in the proof process environment for protected API calls.

The env file must be a regular non-symlink file, owned by the current user, with no group or other
permission bits. Its path is accepted only through the dedicated live command and is never stored
in the report. Credential values are never accepted as CLI arguments. The harness may validate
that required names are present, but it must not print values, copy the env file into the source
archive, persist it in a task directory, include it in diagnostics, or publish a digest derived
from a credential value.

The live preflight parses only an exact allowlist of configuration names. It requires non-empty API,
database, model-provider, and search-provider credentials; an explicitly authorized public HTTPS
model-provider base URL; the approved primary and fallback model identifiers; disabled benchmark
fixtures, durable review, and Evidence verification; `LANGSMITH_TRACING=false`; and empty unrelated
LangSmith and RAGFlow credentials. The provider URL must match the separately approved value and
must not contain userinfo, query, fragment, private or loopback address, or an unapproved path.
This validation constrains the proof execution only and does not change ordinary DRA configuration.

The subprocess environment is constructed from an allowlist of operating-system and Docker client
variables plus the explicit env-file reference. Ambient provider credentials, proxy settings, and
unrelated environment variables are not silently inherited. The container obtains provider
configuration only through the operator-owned Compose env file.

Provider and model identity in the public report is `operator_declared`. It may include bounded
public provider, primary-model, and fallback-model identifiers supplied through non-secret
manifest-compatible metadata and matched to the approved env-file entries. The proof does not
claim that DRA or the provider independently attested which configured model handled each call.

## Exact Source And Container Identity

The live command must run from a clean DRA checkout and fail before Docker mutation unless all of
these facts are established:

- current branch HEAD is an exact 40-character commit;
- `git status --porcelain=v1 --untracked-files=all` is empty;
- `VERSION` is a strict supported version string;
- the checked-in Compose, Dockerfile, constraints, requirements, manifest, proof, and contract
  files are tracked by that commit;
- no local path or credential-bearing file is part of the archive input.

The harness then creates a task-owned uncompressed `git archive` of `HEAD`, validates safe archive
members, hashes the exact archive bytes, and extracts it into a bounded temporary directory. All
Compose config, build, and service operations run from that extracted tracked snapshot rather than
the mutable working directory.

The public source receipt records:

- repository and service canonical names;
- VERSION;
- source commit and source tree;
- tracked archive SHA-256;
- manifest SHA-256;
- sanitized effective Compose configuration SHA-256;
- backend image ID;
- Docker and Compose version identifiers; and
- `source_clean=true` and `build_context=tracked_archive`.

Resolved Compose configuration may contain secrets. The harness must parse it, reject unknown
secret-bearing shapes, replace every approved credential value with a constant type marker, and
hash only the canonical sanitized projection. It must not publish or retain the raw resolved
configuration. The receipt proves which source and local build output were observed; it is not a
software-supply-chain attestation, reproducible-build claim, base-image immutability claim, or
signature.

## Managed Compose Lifecycle

The harness owns one unique Compose project name derived from a random proof execution ID. It may
operate only the checked-in backend and MySQL services from the extracted tracked snapshot.

The ordered lifecycle is:

1. probe the Docker daemon and Compose version without mutation;
2. validate source, manifest, credentials, output destinations, and existing task ownership;
3. create and validate the tracked source archive and extracted snapshot;
4. resolve and sanitize the effective Compose configuration;
5. request engine-assigned host ports while preserving exact `127.0.0.1` HostIp;
6. build the backend image from the tracked snapshot;
7. execute `scripts/secure_local_runtime_proof.py check` inside the exact locked backend image and
   require it to pass before any MySQL, backend, or provider activity;
8. start MySQL and backend under the unique project;
9. inspect both containers, networks, volumes, image identity, health state, and port bindings;
10. poll exact `/health` until the supported identity is observed;
11. execute the one bounded run workflow;
12. restart only the backend service and repeat readiness plus persistence checks;
13. replay the exact original keyed create request;
14. validate the complete captured observation while retaining it only in bounded process memory;
15. attempt bounded cleanup of all task-owned containers, volumes, networks, temporary files, and
    task-built image tags; and
16. after successful cleanup, add the cleanup observation, serialize the final report, and
    atomically publish the two exact non-existing evidence files.

The harness must refuse an existing Compose project with the same name and must never issue a
global Docker cleanup, prune, broad label delete, or deletion based only on a name prefix. Every
cleanup target is recorded from the task's own creation receipt before mutation.

Task-built image tags are removed after their immutable image IDs have been recorded unless an
explicit proof command option requests retention. Retention is an operator-local choice and is not
included in public evidence. Pre-existing images and build cache are never deleted.

## Proof-Owned HTTP Transport

The live harness uses a small proof-owned transport with these invariants:

- the base URL is constructed from the inspected dynamic backend binding and is exactly
  `http://127.0.0.1:<port>`;
- no userinfo, non-root path, query, fragment, hostname alias, IPv6 rewrite, or remote address is
  accepted;
- system and environment proxies are disabled;
- redirects are rejected for health, create, status, usage, and result requests;
- request headers are an exact allowlist and credentials are header-only;
- response bodies are streamed or bounded before parsing;
- JSON uses strict expected top-level identities before projection;
- errors expose stable proof codes only, never raw body, response headers, exception text, or URL
  query; and
- each request consumes the remaining lifecycle deadline rather than receiving a fresh full
  timeout.

The transport reuses current REST request semantics but does not modify or pretend to validate the
public Tool Client transport. A later Tool Client hardening remains a separate decision if a real
consumer demonstrates that need.

## Run Intent And Ambiguous Create Reconciliation

The harness creates one canonical request from the checked-in manifest, generates one contract-safe
thread ID with at least 128 bits of entropy, and generates one high-entropy idempotency key in
memory. The thread ID is included in the first request so acknowledgement identity is exact. The
canonical request bytes, thread ID, and key remain immutable for the lifecycle. The key is never
returned, logged, persisted by the harness, or included in the public report.

Supported create outcomes are:

| Observation | Action |
|---|---|
| First HTTP 200 keyed acknowledgement | require `idempotent_replay=false`, retain identities, poll |
| Ambiguous transport or bounded body-read failure before a valid acknowledgement | perform at most one replay with the exact key and request |
| Replay HTTP 200 | require `idempotent_replay=true` and the original identities |
| Key conflict, invalid key, idempotency unavailable, redirect, identity mismatch, or malformed body | fail closed |
| Second ambiguous outcome | stop with `create_reconciliation_unresolved` |

An HTTP error with a complete bounded response is not ambiguous and is never retried automatically.
Terminal provider, tool, Agent, dispatch, or finalization failure is not retried by the proof. The
existing server-owned DeepAgents/LangChain call limits remain the only per-run model and tool call
limits.

The proof's “one run intent” means one DRA run creation identity. It does not mean one provider
request, one model call, one tool call, or exactly-once external side effects.

## Terminal State And Canonical Consumer Projection

The harness polls only `GET /api/runs/{run_id}` using one monotonic deadline. Client deadline expiry
ends observation and does not call a cancellation endpoint or claim server cancellation.

V1 accepts only this exact delivery state:

```text
execution_status = completed
review_status    = not_required
delivery_status  = ready
failure_cause    = null
profile_id       = generic
```

`completed_with_fallback`, `failed`, review-required, blocked, unknown, inconsistent, or malformed
state fails the live evaluation. The harness then reads the canonical result and calls the existing
`project_consumer_case` with the observed status and result. Acceptance requires:

- `expected.support=supported`;
- `expected.disposition=accept_draft`;
- exact requested run identity throughout;
- artifact ID `research-report.md`;
- kind `research_report_markdown`;
- media type `text/markdown`;
- non-empty bounded UTF-8 content; and
- exact persisted content SHA-256.

The artifact content is held only in bounded process memory long enough to validate and hash it.
It is never written to a raw temporary file, included in the public report, copied into diagnostics,
or retained after cleanup.

## Evidence Acceptance

The same downstream projection validates the run-level Evidence allowlist. The live evaluation
adds only scenario acceptance rules:

- at least one and at most 100 Evidence rows;
- unique evidence IDs according to the current consumer contract and non-empty source identities;
- exact source URL scheme `https`;
- public DNS host, no localhost, IP literal, userinfo, query, fragment, or non-default port;
- `citation_status=cited` for at least one accepted row whose host belongs to the manifest's exact
  required cited source domains;
- supported bounded verification status as compatibility metadata; and
- stable order before and after restart.

Every published Evidence string is independently bounded: evidence IDs use the current 1-128 ASCII
identifier contract, timestamps are at most 64 UTF-8 bytes, and source URL/source identity are at
most 4,096 UTF-8 bytes. These are proof-output limits and do not change the upstream API contract.

Other Evidence rows may use different public HTTPS hosts. They remain candidate research Evidence,
not accepted source truth. The public report includes only the current consumer allowlist:

- `evidence_id`;
- `source_url`;
- `source_identity`;
- `retrieved_at`;
- `citation_status`; and
- `verification_status`.

It excludes snippet, query text, tool payload, provider response, local cache, fingerprint source
content, and any unapproved additive upstream field. Evidence recorded or cited by DRA is not
independently verified and does not authorize a downstream decision.

## Usage And Cost Observation

Before backend restart, the harness reads `GET /api/token-usage/runs/{run_id}` exactly once. The
report uses a discriminated union:

- `observed`: positive call count and internally consistent non-negative prompt, completion, and
  total token counts; or
- `not_observed`: zero/missing provider usage metadata or an unavailable bounded endpoint.

An observed usage object always contains `cost_estimate.status=not_observed` in Change 1. The
aggregate token endpoint does not expose exact per-call model identity or rate selection, so its
`total_cost` cannot be bound to the operator declaration, runtime pricing entry, unknown response
model, or default-price fallback. A declaration, currency, or runtime-compatible pricing map does
not upgrade that aggregate amount to observed cost. The strict manifest and report schemas reject
an observed cost variant even when its decimal and currency fields are well formed.

The endpoint also does not report search-provider usage, so search cost remains `not_observed`.
No aggregate amount is presented as total run cost. A later change may introduce an observed cost
variant only after a separately approved per-call model/rate identity contract exists.

The process-local usage endpoint is expected to reset after backend restart. The proof records only
the pre-restart observation and does not treat post-restart absence as run corruption. This stage
does not add persistence. If the live observation shows that durable usage is necessary for an
operator or consumer, it becomes evidence for a later independent contract change.

## Restart And Idempotent Replay

After successful pre-restart projection, the harness stores only bounded comparison facts:

- run, thread, and segment IDs;
- execution, review, delivery, state version, and failure-cause projection;
- ordered Evidence projection rows;
- canonical artifact ID, kind, media type, byte length, and SHA-256; and
- public consumer disposition.

The backend is then restarted through the same Compose project. The harness waits for exact health
and re-reads status and result. It requires:

- identical run, thread, and segment identity;
- the same accepted terminal state;
- no state-version regression;
- byte-identical ordered Evidence projection;
- identical artifact metadata, length, and SHA-256; and
- the same `supported` / `accept_draft` consumer disposition.

The harness finally replays the exact original create request with the exact original idempotency
key. The acknowledgement must return `idempotent_replay=true` and the original identities. A new
run, conflicting identity, missing replay flag, or non-identical request is a blocking failure.

Because the run is already terminal, replay must not change the accepted public state, return a
second run identity, or return a second terminal artifact. The proof does not inspect private
dispatch state or provider call counters and therefore does not independently claim that no
internal reconciliation work occurred or that provider-side execution was exactly once.

## Deadlines And Resource Budgets

`observe-live` creates one monotonic 3,450-second outer deadline before input validation. Its first
3,330 seconds are the maximum non-cleanup window, covering input and credential validation, the
Docker probe, source preparation, and the active lifecycle. Every subprocess, Docker operation,
HTTP request, readiness loop, sleep, restart, phase transition, report build, and publication
consumes that same outer authority.

| Phase | Maximum |
|---|---|
| Input/credential validation, probe and active lifecycle | 3,330-second non-cleanup window |
| Docker daemon and Compose probe | 30-second child bound |
| Active lifecycle from source validation through replay | 3,300-second child bound |
| Build/start/initial health sub-bound | 1,200 seconds within the active lifecycle |
| Research terminal observation sub-bound | 1,800 seconds within the active lifecycle |
| Restart, persistence comparison, and replay sub-bound | 300 seconds within the active lifecycle |
| Cleanup reserve | 120-second child bound independent of active work but contained in outer wall time |
| Total wall-clock bound | 3,450 seconds |

The outer deadline reserves the final 120 seconds from non-cleanup work. Cleanup may consume at
most that reserve and never extends the total wall deadline. Report serialization and paired
publication use only outer time remaining after cleanup; expiration prevents publication rather
than being detected only after output. No retry receives a fresh phase budget. A fake monotonic
clock must prove phase-transition and post-cleanup publication exhaustion before any mutation,
negative sleep, or fresh timeout allocation.

After credential validation succeeds, its in-memory snapshot is closed on every exit path. The
exact random task-temp path is owned before snapshot preparation can create it. Failures before the
managed project cleanup guard starts remove only that path using a cleanup child inside the outer
reserve; cleanup failure remains paired with the stable primary cause. After the guard starts, the
managed project receipt owns the existing cleanup sequence.

The cost boundary is one operator-authorized DRA run intent, at most one ambiguous create replay,
and the current server-owned call-limit middleware. It is not a hard currency cap. The operator
must approve provider credentials, provider/model declaration, the manifest request, and this
maximum duration before `observe-live` is run.

## Public Report Contract

The live report schema is `dra.bounded-live-producer-evaluation.v1` and uses exact top-level keys:

```text
schema_version
status
source
scenario
lifecycle
run
result
evidence
usage
restart
replay
cleanup
boundaries
limits
```

`status` may be `valid` only when every required observation is present and accepted. A successful
report contains:

- exact source and sanitized runtime identity;
- scenario ID, manifest hash, request hash, profile, and required-cited-domain policy;
- bounded lifecycle timing in integer milliseconds;
- run identities and pre/post-restart public states;
- artifact ID, kind, media type, byte length, and SHA-256;
- the ordered Evidence projection;
- observed/not-observed usage and estimate metadata;
- restart, replay, and cleanup observations; and
- fixed boundaries and non-claims.

Live timestamps, run IDs, Evidence IDs, URLs, and artifact hashes make separate provider runs
non-identical. “Deterministic report” means strict ordering and byte-identical serialization of the
same validated captured observation, not repeatable model output or identical future research.

The Markdown report is a deterministic projection of the validated JSON object. Markdown is never
parsed back into authority. JSON remains the machine contract.

## Public-Safety Policy

The public report and all stable CLI failures must reject or omit:

- credentials, secrets, tokens, cookies, authorization headers, env values, and secret-derived
  hashes;
- query and scope text outside the checked-in manifest reference;
- canonical Markdown content, Evidence snippets, tool output, raw provider response, and raw model
  messages;
- Docker logs, container environment, resolved secret-bearing Compose config, raw HTTP body on
  error, response headers, traceback, exception type or text, and LangSmith trace payload;
- absolute POSIX, Windows, UNC, home-relative, temporary, repository, archive, env-file, database,
  or artifact paths;
- private, loopback, link-local, multicast, reserved, `.local`, `.internal`, or credential-bearing
  source URLs;
- host usernames, machine names, process IDs, local port numbers, container names, network names,
  volume names, and random project suffixes;
- unbounded strings, unordered mappings, NaN, Infinity, negative counters, or unknown schema
  fields; and
- product-specific consumer names, private workflows, sensitive user context, or unsupported
  production claims.

Dynamic host ports are validated internally but the public report records only
`loopback_binding_observed=true`; it does not expose the port numbers. Container and project names
are replaced with stable role labels.

## Stable Failure Taxonomy

Stable CLI failures are single-line JSON on stderr with empty stdout and exit code 1. Help returns
exit code 0. The public error object contains only schema version, stable code, phase, retryable,
and cleanup status.

Required failure codes include:

| Phase | Stable codes |
|---|---|
| Input | `manifest_invalid`, `source_dirty`, `source_identity_invalid`, `credential_source_invalid`, `output_invalid` |
| Docker | `docker_unavailable`, `compose_config_invalid`, `source_archive_invalid`, `image_build_failed`, `service_start_failed`, `service_identity_invalid` |
| Create | `create_rejected`, `create_response_invalid`, `create_identity_mismatch`, `create_reconciliation_unresolved` |
| Observe | `run_observation_deadline`, `run_state_invalid`, `run_failed`, `run_fallback_rejected`, `run_delivery_not_ready` |
| Result | `run_fallback_rejected`, `consumer_projection_invalid`, `artifact_invalid`, `artifact_hash_mismatch` |
| Evidence | `evidence_missing`, `evidence_invalid`, `evidence_domain_rejected`, `required_cited_domain_missing` |
| Usage | `usage_invalid` for malformed or inconsistent data; valid absence maps to `not_observed` |
| Restart | `backend_restart_failed`, `restart_identity_drift`, `restart_evidence_drift`, `restart_artifact_drift` |
| Replay | `idempotent_replay_invalid`, `duplicate_run_observed` |
| Output | `report_invalid`, `output_exists`, `output_write_failed` |
| Cleanup | `cleanup_failed` |
| Internal | `evaluation_internal_error` |

Unknown exceptions map to `evaluation_internal_error` after bounded local diagnostics are captured.
Raw exception data is never serialized into public output.

## Cleanup And Dual-Failure Semantics

Cleanup runs after any mutation regardless of success, timeout, cancellation, serialization
failure, or primary exception. It has its own 120-second reserve and attempts every recorded
task-owned target in deterministic order.

If only cleanup fails, the command fails with `cleanup_failed`. If a primary failure and cleanup
failure both occur, the local implementation preserves both causes using Python 3.11 grouped
exception semantics or an equivalent typed aggregate. The public CLI projects only the stable
primary code plus `cleanup_status=failed`; local debug output remains bounded and secret-safe.

A report may be written only after successful lifecycle observations and successful cleanup. The
only v1 public destinations are the exact absent repository paths
`docs/evidence/bounded-live-producer-v1.json` and
`docs/evidence/bounded-live-producer-v1.md`. Both parents and destinations must pass
symlink/no-follow validation before Docker mutation. Writes use temporary sibling files, file
synchronization, and atomic non-overwrite links. Markdown is linked first and JSON machine
authority last. JSON is acceptable only with the matching Markdown projection and a successful,
separately reviewed evidence publication; a JSON path alone is never authority. A failure before
the JSON link cannot leave machine authority. Rollback removes run-created links when the
filesystem permits it; an unremovable Markdown-only residue remains non-authoritative and blocks a
later overwrite. The harness never touches a path that predated the run and must not accept
arbitrary output paths.

## Deterministic Required CI

Required CI remains provider-free, credential-free, and independent of provider, search, or
research-service network access.
It must cover:

### Contracts and serialization

- strict Python-object validation with no coercion;
- exact manifest and report keys, schema versions, enum values, and discriminated variants;
- bounded UTF-8 reads, JSON depth/node bounds, output sizes, and safe integer/decimal handling;
- deterministic JSON key ordering and Markdown projection;
- public-safety scans over every string field and rendered output;
- atomic paired output, no overwrite, symlink rejection, write/replace failure, and temp cleanup;
- stable CLI errors, empty stdout on failure, help behavior, and import silence.

### HTTP and run semantics

- no proxy, no redirect, exact loopback base URL, header allowlist, and bounded body reads;
- first acceptance, same-key replay, key conflict, invalid/unavailable ledger, malformed JSON,
  identity mismatch, ambiguous body read, second ambiguity, and deadline exhaustion;
- all supported and rejected run/review/delivery/failure-cause tuples;
- exact result identity, fallback rejection, artifact kind/media/size/hash mutations;
- missing, duplicate, private-host, wrong-domain, malformed, uncited, reordered, and additive
  Evidence mutations;
- usage observed/not-observed, inconsistent totals, non-finite cost, missing pricing basis, and
  estimate labeling;
- restart identity/state/Evidence/artifact drift and replay-created duplicate run mutations.

### Lifecycle and cleanup

- fake-clock global and phase deadlines, including no negative sleep and no fresh retry budget;
- exact tracked archive membership, unsafe member rejection, bounded extraction, and source dirty
  failure before Docker mutation;
- sanitized Compose config with secret-field mutation tests;
- primary-only, cleanup-only, and dual-failure preservation;
- exact task ownership and refusal to touch pre-existing Docker resources.

### Required Docker lane

The existing required Docker lane should exercise the new harness lifecycle with a deterministic
provider-free test double or existing local runtime seam. It must prove:

- exact tracked snapshot build;
- unique Compose ownership;
- two engine-assigned, distinct, positive loopback host ports;
- exact MySQL and backend health;
- protected API access without publishing the key;
- backend restart with persisted deterministic run fixture state;
- same-key reconciliation against a deterministic fixture path;
- privilege and credential-isolation inspection; and
- zero task-owned container, volume, network, temp, and tag residue.

It must not call a live model, search provider, arbitrary URL, or real research runtime, and must
not describe its fixture as live evidence.

## Live Observation Gate

`observe-live` is never run automatically. It requires one explicit authorization that identifies:

- the exact merged DRA commit;
- the checked-in manifest revision and public research request;
- the operator-declared provider and model identifiers;
- the external credential source;
- the one-run-intent boundary;
- the 3,450-second maximum wall-clock duration;
- the accepted estimate-only cost boundary; and
- the two exact absent repository evidence destinations.

The command performs one execution. It does not automatically retry after a provider, tool,
terminal, Evidence, artifact, restart, replay, output, or cleanup failure. An ambiguous create may
use the one exact same-key reconciliation defined above because it does not authorize a second run
intent.

Failed live attempts may produce a local sanitized diagnostic, but no failed or partial artifact is
committed under the live evidence name. A successful report still requires independent branch-diff
review before it becomes repository evidence.

## Delivery Sequence

### Change 1: harness and deterministic contract

One implementation pull request should add the manifest, strict contracts, managed lifecycle,
provider-free CI matrix, required Docker lifecycle, public reference documentation, and
`Unreleased` entry. It must not change VERSION, dependencies unless an implementation blocker is
separately approved, or any public runtime contract.

### Change 2: live evidence

After Change 1 merges, a separate authorization may run `observe-live` from the exact clean merged
commit. A successful sanitized JSON/Markdown report and its documentation/index updates form a
small evidence-only pull request. If the live run exposes a contract or runtime defect, stop and
design a separate targeted fix rather than hiding it in the evidence change.

### Post-Observation Targeted Runtime Repair Amendment

This targeted repair was separately authorized after a bounded observation exposed a runtime
closure defect. Its exact scope is the generic coordinator canonical completion middleware and
precise fallback failure classification.

The correction uses the native LangChain `after_model` hook with `jump_to="model"` and the
DeepAgents `write_file` tool. The completion middleware is registered before the existing
call-limit middleware so reverse `after_model` execution records the completed call before any
conditional model re-entry. The correction remains within the existing model, tool, and recursion
budgets.

This amendment does not change REST/OpenAPI, database, canonical result or Evidence authority, the
provider contract, VERSION, dependencies, CI, or release metadata. No live-success claim is made
and no live evidence is published.

### Change 3: release preparation

Only after the live evidence change merges should release preparation evaluate `v0.1.6`. Release
metadata must distinguish deterministic contract coverage from the one real provider-backed
observation and preserve all non-claims. Tag, GitHub Release, archive validation, and runtime smoke
remain separately authorized closeout actions.

### Later stage: Real Agent Evaluation v2

Real Agent Evaluation v2 is a separate design. It may compare a small frozen set of real or
sanitized captured observations against the deterministic evaluator registry. It must not be
folded into this harness pull request and must not turn one live report into a quality benchmark.

## Documentation Impact

The harness implementation should update only documentation required to discover and operate the
new evaluation boundary:

- a dedicated reference document;
- evidence and documentation indexes;
- Agent integration or getting-started material only if a public command is added;
- architecture/framework-boundary wording for proof ownership;
- README and CHANGELOG discovery after the capability is real; and
- release notes only during separate release preparation.

The public documentation must distinguish:

- deterministic contract coverage;
- required local Docker lifecycle coverage;
- one separately authorized live provider observation;
- producer compatibility from downstream business acceptance; and
- token/cost estimate from durable usage or provider billing.

## Compatibility And Migration

The Change 1 feature is additive and proof-owned:

- no migration or backfill;
- no API or OpenAPI change;
- no canonical result or Evidence change;
- no Tool Client CLI or environment-variable change;
- in Change 1, no profile or middleware change;
- no Compose product-default change unless a separately reviewed harness blocker requires one;
- no required credential in ordinary deterministic tests; and
- no change to existing evidence baselines.

Deleting the new harness files restores the previous product behavior. A live evidence file is a
historical observation and does not become runtime input.

## Risks And Mitigations

| Risk | Mitigation |
|---|---|
| A live report is mistaken for a quality benchmark | Name it a producer evaluation, publish one exact scenario, and retain explicit non-claims |
| The proof leaks query or provider content | Keep input in the public manifest; output only hashes and allowlisted Evidence fields |
| Credentials leak through Compose config or diagnostics | External env file, scrubbed subprocess environment, typed redaction, mutation tests, and no raw logs |
| Dirty files change the built service | Build from a hashed tracked `git archive`, not the working directory |
| Redirect or proxy reaches an unintended service | Exact dynamic loopback origin, disabled proxies, and redirect rejection |
| Lost create acknowledgement creates duplicate research | One immutable request/key and at most one exact idempotent reconciliation |
| Client timeout is mistaken for server cancellation | Stop polling and state the non-claim explicitly |
| Restart loses process-local usage | Observe once before restart and label usage non-durable |
| Default pricing is mistaken for billing | Publish cost only with approved pricing basis and `estimate=true` |
| Cleanup hides the real failure | Preserve primary and cleanup failures separately |
| Docker cleanup touches unrelated work | Unique receipts, exact task ownership, and no prefix/global deletion |
| The harness duplicates runtime authority | Reuse status/result/Evidence consumer projection and keep proof-owned code observational |
| Consumer integration is inferred | State producer-only scope; require consumer-owned governance in a later repository proof |

## Acceptance Criteria

The design is implemented only when all of these are true:

1. Required CI passes without provider credentials, provider/search network access, or live
   research.
2. The new Docker lane passes as a required hosted check and leaves zero task-owned runtime
   residue.
3. The live command cannot run from dirty or ambiguous source and builds from the tracked archive.
4. Credential values, raw content, logs, tracebacks, and absolute paths cannot enter stable output.
5. One accepted live run projects as `supported` / `accept_draft` through the existing consumer
   validator.
6. At least one cited public HTTPS Evidence row from an allowed domain is present.
7. Artifact bytes are bounded, non-empty, and hash-valid without being written to raw disk.
8. Backend restart preserves the accepted public state, Evidence order, and artifact identity.
9. Exact same-key replay returns the original identities and does not return a second run identity.
10. Usage is truthfully `observed` or `not_observed`; any cost is an estimate with explicit basis.
11. Primary and cleanup failures remain distinguishable and public-safe.
12. JSON and Markdown serialization are stable for the same captured observation.
13. The Change 1 harness PR changes no runtime/API/DB/framework authority and makes no live claim.
14. The live evidence PR contains only a successful reviewed sanitized observation and discovery
    updates.
15. Release preparation remains separate and does not begin before the live evidence is merged.

## Rejected Alternatives

### Change the runtime contract first

Rejected because current status, result, Evidence, idempotency, restart, and failure contracts are
sufficient for the bounded proof. A new outcome schema without consumer evidence would add
authority and migration cost before demonstrating a gap.

### Run against a manually started service

Rejected because it cannot bind source, build, Compose configuration, lifecycle, restart, and
cleanup into one reviewable observation.

### Use the public Tool Client unchanged

Rejected for this proof because its current transport does not provide the explicit no-proxy and
no-redirect guarantees required by the live security boundary. This is not evidence that the Tool
Client contract must change.

### Commit the raw Markdown result

Rejected because the proof needs artifact identity and Evidence metadata, not redistribution of
provider-generated prose. Raw content increases privacy, copyright, prompt-injection, and review
cost without strengthening the producer contract.

### Add durable usage or billing in the same change

Rejected because usage persistence is a separate application contract. The live observation first
determines whether process-local usage is an actual consumer or operator blocker.

### Add LangChain or DeepAgents middleware to the Change 1 proof

Rejected for Change 1 because the missing proof lifecycle is outside Agent invocation. This does
not prohibit the separately authorized post-observation runtime repair. The project uses
framework-native middleware only where it matches runtime semantics.

### Combine live producer proof and downstream product closure

Rejected because the producer and consumer have separate release, credential, governance, and
business authorities. Combining them would weaken source identity and blur approval boundaries.

## Final Decision

Proceed with Bounded Live Producer Evaluation v1 as the next DRA stage. Land this design
mechanically, review its actual public diff, then write the implementation plan. Do not start Real
Agent Evaluation v2, durable usage, structured outcome, multi-instance work, or a consumer-specific
integration until this producer proof either succeeds or exposes a concrete contract blocker.

### Post-Observation Result Diagnostic Amendment

A later bounded observation showed that `consumer_projection_invalid` still collapsed multiple
result-boundary stages after existing artifact, state, Evidence, fallback, and hash
classifications. The separately approved Bounded Result Diagnostic Receipt v1 adds one optional
`--diagnostic-dir` with a fixed basename and owner-only repo-external directory. This is the only
exception to Change 1's prohibition on output-path options; it does not permit an arbitrary
filename or general output root.

The existing public error envelope remains unchanged. The JSON-only receipt is written after
cleanup, is not live evidence or application authority, contains no raw response or provider
material, and does not authorize a retry. REST, OpenAPI, database, Agent/framework authority,
canonical result, Evidence, downstream consumer acceptance, dependencies, CI provider policy,
VERSION, and release metadata remain unchanged.
