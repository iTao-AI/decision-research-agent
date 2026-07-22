# Artifact Delivery And Limiter Diagnostics Closure Design

**Status:** Approved direction; public-neutral design source for mechanical landing and
implementation planning.

## Summary

Decision Research Agent has a stable canonical result resolver, application-owned delivery state,
and a bounded live producer evaluation with opt-in structural diagnostics. A focused read-only
audit identified three remaining closure gaps:

1. `GET /api/runs/{run_id}/artifacts/{artifact_id}` can return persisted artifact content without
   applying the canonical result resolver's terminal, review, delivery, and integrity gates.
2. LangChain's native model/tool call-limit exceptions are collapsed into the public application
   cause `execution / call_budget_exceeded` before a separately authorized live evaluator can
   distinguish which limiter fired.
3. Public discovery surfaces mix release evidence, optional operator proofs, historical records,
   and one benchmark value claim that conflicts with the current deterministic runner.

The selected closure is three independently reviewable pull requests:

- **PR A — Artifact delivery gate:** make the existing artifact-content route a view of the current
  canonical deliverable rather than a raw persisted-artifact reader.
- **PR B — Operator-only limiter diagnostics:** preserve a closed projection of native limiter
  attributes through an explicitly enabled, task-owned sidecar and publish a non-authoritative
  call-budget diagnostic receipt from the bounded evaluator.
- **PR C — Public truth and proof taxonomy:** correct the benchmark claim and classify proof
  artifacts by what actually gates CI, release, optional operations, or historical evidence.

PR A, PR B, and PR C may be developed concurrently in isolated worktrees with non-overlapping file
ownership. PR A lands first. PR B must synchronize with the post-PR-A `main` before merge. PR C is
independent and may land whenever its exact-head checks and review are complete. No provider-backed
observation is authorized by this design. A later observation requires PR A and PR B to be merged,
fresh provider-free verification, and separate one-shot authorization.

## Inspected Baseline

This design was finalized against:

- `main == origin/main == b73d3fc6e4f0f76cbe27d988307bdfce3a61d55d`;
- a clean primary checkout and no open pull requests;
- `VERSION=0.1.5` and the public, non-draft, non-prerelease `v0.1.5` release;
- LangChain `1.3.10`, DeepAgents `0.6.11`, LangGraph `1.2.6`, LangSmith `0.8.18`, and
  Pydantic `2.13.4` in `constraints.txt`;
- the provider-free bounded producer gate on required CI;
- no committed `bounded-live-producer-v1.json` or Markdown live evidence; and
- no known repository consumer of the raw `/artifacts/{artifact_id}` content route.

Current implementation facts:

- `api/run_result_service.py::resolve_run_result` already owns terminal-state, delivery-state,
  canonical-artifact selection, bounded-content, unsafe-content, and content-hash validation.
- `api/server.py::get_run_artifact` bypasses that resolver and calls `get_artifact` directly.
- `agent/deepagents_harness.py::DeepAgentsHarness.execute` catches
  `ModelCallLimitExceededError` and `ToolCallLimitExceededError`, then raises only
  `HarnessExecutionError(failure_kind="call_budget_exceeded")`.
- `api/research_execution_service.py::ResearchExecutionService.execute` persists the stable public
  failure kind but no native limiter attributes.
- the bounded evaluator already has strict Result Diagnostic Receipt v1 and Run Failure Diagnostic
  Receipt v1 sinks; both are opt-in, post-cleanup, bounded, non-overwriting, and explicitly
  non-authoritative.
- `AGENTS.md` says the fixed-sample Talent value gate passed, while the current deterministic runner
  deliberately returns `passed=false` and leaves the human value decision outside deterministic
  readiness.
- `docs/evidence/README.md` says it retains only current release-gate evidence while indexing a
  broader mixture of deterministic baselines, optional workflow proofs, and historical reviewed
  artifacts.

## Product And Engineering Decisions

### Artifact content is delivery, not storage inspection

The public artifact route remains in place for compatibility, but it becomes a byte-oriented view
of the same current artifact selected and validated by `resolve_run_result`. The repository does not
add a second privileged audit endpoint. There is no approved identity or RBAC model that could make
such an endpoint meaningfully privileged, and no known consumer requires pre-delivery content.

Artifact metadata may remain visible in the existing run-status projection. This change only gates
artifact content.

### Limiter origin remains operator-only

The public application cause remains exactly `execution / call_budget_exceeded`. The database,
`dra.run-failure-cause.v1`, REST API, canonical result, Evidence, review, publication, and delivery
contracts do not gain limiter fields.

LangChain remains the source of model/tool limiter enforcement and native exception attributes.
DRA projects only a strict closed subset of those attributes. It does not parse exception text,
infer a coordinator or researcher identity, increase a budget, retry a provider call, or turn
LangSmith into application authority.

### Documentation reflects current executable truth

Public claims are corrected to match current code and checked-in evidence. The change does not
erase historical design decisions; it makes current discovery surfaces explicit about deterministic
readiness, human decisions, release gates, optional proofs, and absent live evidence.

## Alternatives Considered

### Add a privileged raw-artifact endpoint

Rejected. Without an identity and authorization model, a differently named endpoint would not be
privileged. It would preserve the same delivery bypass under a new path and expand public surface.

### Remove the artifact route

Rejected. The route is documented and useful as a content-only compatibility surface. Tightening
it to canonical delivery semantics removes the authority gap with less migration cost.

### Put limiter origin in `dra.run-failure-cause.v1`

Rejected. The current application cause intentionally describes a stable business-facing class,
not framework implementation details. A schema expansion would create API/DB migration cost before
any real consumer has requested it.

### Use LangSmith traces as the diagnostic authority

Rejected. LangSmith remains privacy-first, optional diagnostics. Trace availability, retention, or
hosted access cannot determine application state or make a one-shot evaluation reproducible.

### Increase call budgets or change models first

Rejected. Existing evidence identifies `call_budget_exceeded` but does not identify the exact
limiter. Raising budgets or switching models would change cost and behavior without testing a
specific hypothesis.

### Rewrite the bounded producer harness or repository state machine

Rejected. The audited runtime authority flow is internally coherent, and the evaluator is isolated
from production imports. A whole-harness or repository rewrite would add risk without closing the
two demonstrated gaps.

## Authority Map

| Surface | Authority after this change | Explicit non-authority |
|---|---|---|
| Run and delivery state | Application database and `resolve_run_result` | Artifact route, Agent runtime, diagnostic receipt |
| Current artifact bytes | Canonical result resolver after integrity validation | Raw persisted row, status metadata |
| Call-limit enforcement | Locked LangChain middleware | DRA receipt, LangSmith |
| Public terminal cause | `dra.run-failure-cause.v1` in the application database | Native exception class and operator sidecar |
| Internal limiter sidecar | Task-owned runtime diagnostic file | API, DB, Evidence, live proof |
| Outer call-budget receipt | Operator-owned, strict, non-authoritative evaluation artifact | Canonical result, provider quality, business acceptance |
| Proof classification | CI workflow, release documents, and each artifact's stated boundary | Directory placement alone |

## PR A — Artifact Delivery Gate

### Route semantics

`GET /api/runs/{run_id}/artifacts/{artifact_id}` must call
`resolve_run_result(run_id=run_id)` exactly once and must not call `get_artifact` directly.

The resolver path used by this route must obtain the run terminal/delivery facts, current artifact
selection, and selected artifact content/metadata from one explicit SQLite read transaction. The
transaction defines a request snapshot: all authorization and integrity decisions for one request
come from the same database snapshot. A commit that changes delivery state or current artifact
after that snapshot affects the next request; this design does not claim continuous revocation
during an already-open response. The generic `get_run` implementation must not be rewritten merely
to provide this snapshot; a small read-only repository projection may serve this route and the
canonical result resolver.

The route behavior is:

| Condition | Response |
|---|---|
| Run does not exist | Preserve the resolver's `404 run_not_found` envelope |
| Run is pending or running | Preserve `409 run_not_terminal` |
| Run failed | Preserve `409 run_failed` |
| Review is required | Preserve `409 run_review_required` |
| Delivery is blocked | Preserve `409 run_delivery_blocked` |
| No ready deliverable exists | Preserve `409 run_result_unavailable` |
| Current artifact is missing, unsafe, oversized, or hash-invalid | Preserve `409 run_result_unavailable` |
| Requested `artifact_id` is not the resolver-selected current artifact | Preserve the route's existing `404 {"detail":"Artifact 不存在"}` shape |
| Requested ID equals the valid current artifact | Return the resolver-validated bytes and media type |

The success response must use the artifact object already returned by `resolve_run_result`; it must
not re-read the row after validation. The selected bytes, stored hash, media type, safety state, and
the run/delivery facts that authorize them therefore come from the same request snapshot, avoiding
mixed-state authorization and a second selection rule.

### Compatibility

The path, method, success media type, and success bytes remain unchanged for a current ready
artifact. An integrity-valid fallback artifact that the canonical resolver has selected as the
current `research-report.md` and whose run has reached `delivery_status=ready` is a legal ready
deliverable and must return its original bytes and media type. The intentional behavior change is
that historical, non-ready fallback, review-blocked, failed, pending, stale, or integrity-invalid
artifact content is no longer retrievable through the public route.

No known consumer depends on the old raw-read behavior. If a future audited storage-inspection use
case appears, it requires a separately approved identity/authorization design rather than a bypass
in this route.

### Tests

PR A must add RED-to-GREEN coverage for:

1. every resolver 404/409 disposition listed above;
2. a ready current artifact returning exact bytes and media type;
3. a non-current requested ID returning the existing artifact 404 shape;
4. hash-tampered, unsafe, missing, empty, and oversized current artifacts failing closed;
5. review approval permitting content and rejection blocking content;
6. generic and Talent/current-artifact selection behavior;
7. a ready resolver-selected fallback report returning its original bytes and media type;
8. a controlled interleaving in which delivery/current-artifact state changes during the request,
   proving that one response never mixes run facts from one SQLite snapshot with artifact bytes or
   metadata from another;
9. proof that the route uses one resolved artifact and performs no direct raw repository read; and
10. API/reference documentation describing content delivery rather than storage inspection.

### Expected file ownership

PR A owns only the artifact delivery surface and its tests/docs, principally:

- `api/server.py`;
- `api/run_repository.py` only for a minimal read-only result snapshot projection;
- `api/run_result_service.py` only if a small reusable resolver helper is justified;
- existing run-result and API integration tests; and
- `docs/reference/api-contract.md` and directly related contract tests.

It must not modify Agent middleware, bounded producer scripts, evidence indexes, benchmark claims,
database schema, migrations, dependencies, CI, or VERSION.

## PR B — Operator-Only Limiter Diagnostic Sidecar

### Framework-native source

The implementation must preserve native structured attributes only from the locked exception
types:

- `ModelCallLimitExceededError`; and
- `ToolCallLimitExceededError`.

The official LangChain middleware remains responsible for enforcement. DRA must not replace the
middleware or parse `str(exc)`. The adapter maps attributes by name and fails closed when a value is
missing, coerced, Boolean-as-integer, negative, outside DRA's explicit diagnostic bound, or
semantically inconsistent.

### Application-owned in-memory projection

Add one frozen strict application type, conceptually:

```text
CallBudgetDiagnostic
  limiter_kind: model | tool
  tool_scope: not_applicable | all_tools | task
  run_count: bounded integer
  run_limit: bounded positive integer
  thread_count: bounded integer
  thread_limit: bounded positive integer | null
  agent_role: not_observed
```

DRA defines `MAX_CALL_BUDGET_DIAGNOSTIC_COUNT = 1_000_000` for this projection. Every counter and
limit must satisfy `type(value) is int`; `bool` and coercible strings are rejected. `run_count` and
`thread_count` are in `0..MAX_CALL_BUDGET_DIAGNOSTIC_COUNT`; `run_limit` is in
`1..MAX_CALL_BUDGET_DIAGNOSTIC_COUNT`; and `thread_limit` is either `null` or in that same positive
range. The projection must not invent a relation such as `count <= limit`, because a native tool
limit exception may report the attempted call above its configured limit.

Rules:

- model exceptions map to `limiter_kind=model` and `tool_scope=not_applicable`;
- tool exceptions with `tool_name is None` map to `tool_scope=all_tools`;
- tool exceptions with exact `tool_name == "task"` map to `tool_scope=task`;
- every other tool name produces no limiter diagnostic rather than leaking or expanding a tool
  registry;
- `agent_role` is always `not_observed` because the locked framework exception does not provide a
  stable coordinator/researcher identity at the outer catch; and
- the public `failure_kind` remains exactly `call_budget_exceeded`.

`HarnessExecutionError` may carry this optional typed diagnostic in memory. Existing callers that
inspect only `failure_kind` remain compatible.

### Runtime sidecar

The runtime sidecar is explicitly opt-in and disabled by default. Enabling it is restricted to the
bounded live producer lifecycle through the closed environment entry
`DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_LIMITER_DIAGNOSTICS=true`. The key is accepted only by the
controlled `observe-live` `LiveConfiguration` allowlist: absence disables the sidecar, while any
present value other than exact lowercase `true` fails before provider activity. It is not added to
`.env.example`, base Compose, or a public report. It does not add a general logging configuration or
an arbitrary output path.

When enabled and when a valid `CallBudgetDiagnostic` exists, the application writes one strict,
canonical JSON sidecar beneath the existing task-owned output root:

```text
/app/output/operator-diagnostics/<validated-run-id>/call-budget-v1.json
```

The internal sidecar schema is exactly:

```json
{
  "schema_version": "dra.call-budget-origin-sidecar.v1",
  "limiter": {
    "limiter_kind": "model",
    "tool_scope": "not_applicable",
    "run_count": 40,
    "run_limit": 40,
    "thread_count": 40,
    "thread_limit": null,
    "agent_role": "not_observed"
  }
}
```

The writer must:

- derive the path only from the application-owned output root and a validated run ID;
- create owner-only directories and a mode-`0600` regular file;
- reject symlinks, pre-existing files, replacement races, extra fields, coercion, and oversized
  canonical bytes;
- use create-without-overwrite, flush, and `fsync` semantics;
- never write exception text, traceback, prompt, provider/model identity, tool arguments/results,
  query, scope, Evidence, artifact content, credential material, URLs, paths supplied by a caller,
  or secret-derived values; and
- never replace, delay, or change the application terminal cause if diagnostic publication fails.

The sidecar is not added to artifact metadata, the database, status, result, Evidence, or public
output. Ordinary runtime and Compose behavior remain unchanged when the exact proof-owned mode is
absent.

### Task-owned extraction

After the bounded evaluator observes an exact `execution / call_budget_exceeded` application cause
and before Compose cleanup, it may read only the fixed sidecar for the exact created run from the
task-owned backend container. The evaluator must first resolve one unique full backend container ID
from the current Compose project, prove that ID belongs to the current task ownership receipt, and
prove that the sidecar root is the mount backed by this task's newly owned `backend_output` volume.

Extraction uses direct `docker exec <exact-full-container-id>` with an argument-vector command to a
fixed, stage-owned reader module. It must not use a shell, arbitrary path, `docker compose cp`, or a
host diagnostic file. The reader opens the fixed run-scoped sidecar descriptor-relative with
`O_NOFOLLOW`, requires a regular mode-`0600` file at most 4 KiB, records inode/size/mode from the open
descriptor, strictly validates the schema, emits only canonical closed-field JSON bytes to captured
stdout, and verifies the same open-file identity after reading. The host validates those canonical
bytes again and keeps the typed value in memory only. No captured sidecar bytes may enter public
stdout, stderr, cleanup diagnostics, or provider logs.

Extraction must:

- consume the existing outer deadline and bounded subprocess budget without extending either;
- re-resolve and prove the same full backend container ID and task ownership after the read;
- reject missing or ambiguous containers, ownership drift, mount drift, symlinks, directories,
  replacement races, malformed JSON, schema drift, and oversized bytes;
- retain no host copy or raw container output after the typed in-memory projection is built;
- use existing exact Compose cleanup so `down -v` removes the task-owned `backend_output` volume;
  and
- treat absence or invalidity as `not_observed`, not as a new application failure or a guessed
  limiter.

No failed container, task database, raw response, trace, or output volume is retained.

### Call Budget Diagnostic Receipt v1

When the application cause is exactly `execution / call_budget_exceeded` and a valid internal
sidecar was extracted, the evaluator selects a third outer receipt:

```json
{
  "schema_version": "dra.bounded-live-producer-call-budget-diagnostic.v1",
  "primary": {
    "code": "run_failed",
    "phase": "observe",
    "retryable": false,
    "cleanup_status": "succeeded"
  },
  "run_failure": {
    "cause_schema_version": "dra.run-failure-cause.v1",
    "observation_status": "observed",
    "phase": "execution",
    "code": "call_budget_exceeded"
  },
  "limiter": {
    "limiter_kind": "model",
    "tool_scope": "not_applicable",
    "run_count": 40,
    "run_limit": 40,
    "thread_count": 40,
    "thread_limit": null,
    "agent_role": "not_observed"
  }
}
```

The fixed filename is:

```text
bounded-live-producer-call-budget-diagnostic-v1.json
```

The receipt is strict, extra-forbidden, canonical UTF-8 JSON, and at most 4 KiB. It is constructed
before cleanup from validated closed fields and published only after cleanup so
`cleanup_status` is final.

Diagnostic selection becomes:

| Primary condition | Selected outer receipt |
|---|---|
| Eligible result-boundary projection failure | Result Diagnostic Receipt v1 |
| Non-budget `run_failed / observe` with valid application cause | Run Failure Diagnostic Receipt v1 |
| `execution / call_budget_exceeded` with valid limiter sidecar | Call Budget Diagnostic Receipt v1 |
| `execution / call_budget_exceeded` without a valid sidecar | Existing Run Failure Diagnostic Receipt v1 |
| Success or any other failure | No diagnostic receipt |

One invocation may publish at most one outer receipt. Diagnostic-directory preflight rejects the
invocation if any of the three fixed final filenames already exists. Result Diagnostic Receipt v1
and Run Failure Diagnostic Receipt v1 retain their exact schema, bytes, filenames, and eligibility.

The call-budget receipt is a non-authoritative operator diagnostic. It proves only which locked
framework limiter exception was structurally observed and its counters. It does not prove that the
budget is correct, the model is inadequate, the run should be retried, or a downstream consumer
would accept the result.

### Tests

PR B must add deterministic RED-to-GREEN coverage for:

1. model, global-tool, and `task`-tool limiter extraction from the locked framework exceptions;
2. all reachable generic coordinator/subagent propagation paths preserving
   `agent_role=not_observed`, without testing or documenting inferred role identity;
3. missing, Boolean, negative, above-`1_000_000`, unknown-tool, and malformed native attributes
   producing no guessed limiter diagnostic, including a legitimate exceeded count greater than its
   limit;
4. unchanged `failure_kind=call_budget_exceeded` and unchanged durable public failure cause;
5. runtime sidecar disabled by default, enabled only by exact
   `DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_LIMITER_DIAGNOSTICS=true`, and invalid present values
   rejected before provider activity;
6. fixed run-scoped path, owner-only permissions, non-overwrite, symlink/replacement, bounded bytes,
   `fsync`, and publication-failure isolation;
7. exact full-container and newly owned `backend_output` volume binding, descriptor-safe in-container
   extraction before cleanup, container/mount drift rejection, no host file, and task-volume deletion
   during cleanup;
8. missing/invalid sidecar falling back to Run Failure Diagnostic Receipt v1;
9. strict Call Budget Diagnostic Receipt v1 schema, canonical bytes, public-safety scan, and 4 KiB
   bound;
10. exact selection among all three receipt types and proof that one invocation cannot publish two;
11. primary-plus-cleanup failure preservation and final cleanup status;
12. byte compatibility for both existing v1 receipts and default provider-free output;
13. locked LangChain/DeepAgents integration tests that use real exception classes; and
14. documentation contracts that lock schema, selection, authority, and non-claims.

### Expected file ownership

PR B principally owns:

- `agent/harness_contracts.py`;
- `agent/deepagents_harness.py`;
- `api/research_execution_service.py` and the minimal injection seam in `agent/main_agent.py`;
- one small application-owned writer, expected as `api/operator_diagnostics.py`;
- one fixed in-container reader, expected as
  `scripts/bounded_live_producer_runtime_diagnostics.py`;
- bounded producer contracts, lifecycle, proof, diagnostic sink, and their focused tests;
- `docs/reference/bounded-live-producer-evaluation.md`; and
- a minimal amendment to the existing approved bounded-producer spec/plan when required for current
  implementation truth.

It must not modify artifact-route semantics, database schema, migrations, public failure-cause
schema, API/OpenAPI, Evidence, review, publication, delivery authority, budgets, model selection,
dependencies, CI, release metadata, or VERSION.

### Framework decision

This PR reuses LangChain's installed model/tool call-limit middleware and native exception types.
It does not add custom limiter middleware because the framework already satisfies enforcement and
budget contracts. Project-owned code is limited to safe projection and operator receipt transport,
which LangChain, DeepAgents, LangGraph, and LangSmith do not own.

## PR C — Public Truth And Proof Taxonomy

PR C is documentation-only except for deterministic documentation-contract tests.

### Talent benchmark claim

Replace the current `AGENTS.md` statement that the fixed-sample Talent value gate passed with a
claim matching executable truth. The new statement must say that the repository contains a
fixed-sample Talent benchmark contract and that deterministic readiness remains separate from a
human value decision. It must not claim market validity, hiring impact, live accuracy, or a passed
human gate without a repository-visible decision artifact.

Historical ADRs may continue to describe the decision made at that time, but current discovery
surfaces must not treat the historical wording as stronger than the current runner and checked-in
evidence.

### Evidence taxonomy

`docs/evidence/README.md` must stop describing every indexed artifact as a current release gate. It
must group each existing artifact into exactly one discovery class:

1. **Required deterministic CI/release baseline** — byte-checked or contract-tested in required
   gates.
2. **Optional operator/workflow proof** — runnable and reviewed, but not required for every CI or
   release.
3. **Historical reviewed record** — retained for a bounded past decision or release claim.
4. **Absent future evidence** — documented expected paths that do not yet exist and make no claim.

Each artifact keeps its own authority and non-claims. Directory placement alone does not promote a
record into a release gate.

### Useful checks

The English and Chinese READMEs must either:

- list every deterministic proof command currently run by required CI; or
- explicitly label the displayed commands as a selected subset and link to `.github/workflows/ci.yml`
  as the current required-gate authority.

The chosen wording must classify the downstream consumer contract accurately: its committed
fixture and CLI build/check behavior are exercised by the full test suite even though CI does not
run a separate top-level downstream CLI command. PR C must not add a redundant CI step solely to
make the README list symmetrical.

### Tests and ownership

PR C creates or uses a dedicated public-truth documentation contract so it does not share
implementation files with PR A or PR B. Tests must reject:

1. a restored Talent “value gate passed” claim without a repository-visible authority artifact;
2. wording that calls every evidence record a current release gate;
3. missing or duplicate evidence classification;
4. a claim that absent bounded live paths are completed evidence;
5. a claim that the downstream CLI is a separate required CI command; and
6. English/Chinese discovery drift for useful checks and proof boundaries.

PR C owns only:

- `AGENTS.md`;
- `README.md`;
- `README_CN.md`;
- `docs/evidence/README.md`;
- directly necessary documentation indexes; and
- a dedicated public-truth documentation test file.

It must not modify runtime, API, DB, Agent, bounded producer implementation, existing evidence
payloads, release notes, dependencies, CI, or VERSION.

## Parallel Delivery Topology

The implementation parent owns the shared contract, branch topology, cross-lane integration, and
final verification. After this design and its implementation plan are landed and reviewed, the
work may fan out once:

```text
Ultra parent
  ├─ medium lane A: artifact delivery gate
  ├─ medium lane B: limiter sidecar and operator receipt
  └─ medium lane C: public truth and proof taxonomy

landing order:
  A merge
    -> B sync/rebase against updated main
    -> B targeted integration review and merge

  C may merge independently when exact-head review and CI are green
```

Lane rules:

- each lane uses an isolated worktree and branch;
- children do not delegate again;
- no shared writable worktree or shared uncommitted files;
- the parent owns spec/plan amendments, file-ownership changes, cross-lane conflict resolution, and
  the consolidated final report;
- any unexpected shared-file requirement returns to the parent before editing;
- child summaries do not replace parent inspection of actual diffs and tests; and
- no lane may push, create a PR, merge, release, run a provider, or clean another lane without the
  corresponding authorization.

PR A lands first because it closes a current public authority bypass. PR B then validates its
task-owned diagnostic transport against the tightened artifact surface even though it does not
consume that route directly. PR C is independent because it owns discovery truth rather than
runtime behavior.

## Integrated Verification

Before PR A:

- focused run-result service and artifact-route unit/integration tests;
- review/delivery/integrity state matrix;
- API documentation contracts;
- broader backend tests matching the route's blast radius;
- canonical identity, presentation audit, and `git diff --check`.

Before PR B:

- locked LangChain/DeepAgents exception and harness matrix;
- complete bounded producer provider-free matrix;
- both existing diagnostic receipt compatibility suites;
- new sidecar/receipt safety and mutation matrix;
- required Docker authority lane with exact task cleanup;
- provider-free `check` twice with byte-identical output;
- run failure-cause proof, downstream contract, Agent evaluation, canonical identity,
  presentation audit, and `git diff --check`.

Before PR C:

- dedicated public-truth documentation tests;
- existing documentation/release/presentation contracts;
- English/Chinese discovery consistency;
- public/private/credential/unfinished-marker scans; and
- `git diff --check`.

After PR A and PR B are both on the same integrated HEAD, rerun the full relevant non-Docker
backend suite, required Docker lane, all deterministic proof checks, downstream consumer contract,
canonical identity, presentation audit, dependency/version diff, public/private scans, and exact
task-resource cleanup. No live provider is part of this integration gate.

## Compatibility And Migration

- PR A is a deliberate fail-closed behavior tightening on an existing route. Current ready artifact
  success remains compatible; pre-delivery raw content access is removed.
- PR B is opt-in and additive. Default runtime, public errors, existing diagnostic v1 files, and
  provider-free output remain byte-compatible.
- PR C is claim/discovery correction only.
- No database migration, dependency change, CI expansion, version bump, release preparation, or
  consumer schema migration is required by these PRs.
- A patch release may be evaluated after the three changes and the subsequent bounded live
  decision are complete. This design does not pre-commit a version or publication result.

## Rollback

- PR A rolls back by reverting its route/docs/tests commit; no data migration exists. Reverting
  reopens the documented delivery bypass and therefore requires an explicit risk decision.
- PR B rolls back by reverting the opt-in sidecar/receipt change. Existing Result and Run Failure
  Diagnostic Receipt v1 behavior remains the fallback and no persisted application state requires
  repair.
- PR C rolls back as documentation/tests only, but must not restore claims contradicted by current
  executable evidence.

## Deferred Whole-Repository Audit Items

The following are intentionally not part of PR A, PR B, or PR C:

- removal or privatization mechanics for fixture-only `transition_run`;
- deduplication of state checks across create, dispatch, Agent, finalize, review, publication, and
  delivery paths unless a concrete duplicate-authority bug is found;
- retirement or archival of live-specific bounded producer lifecycle/fixture scripts;
- a rewrite of `run_repository.py`, the test architecture, or the failure taxonomy;
- generic structured outcomes, public limiter diagnostics, RBAC, hosted deployment, multi-instance
  runtime, or a general observability platform; and
- release/version work.

These items belong to the separately planned final bounded repository audit after the current live
proof effort reaches a terminal conclusion. Provider-free `check` remains a required CI gate until
that audit proves a safe replacement or retirement path.

## Acceptance Criteria

1. The artifact-content route can return bytes only for the resolver-selected, integrity-valid,
   current ready deliverable, with authorization facts and selected content drawn from one explicit
   SQLite request snapshot.
2. No second raw or privileged artifact-content surface is added.
3. Public failure cause remains `execution / call_budget_exceeded` with no API/DB/schema expansion.
4. Native limiter diagnostics use structured locked-framework attributes and never exception text.
5. Runtime sidecar creation is exact-mode opt-in, run-scoped, owner-only, non-overwriting, bounded,
   and unable to change terminal application behavior.
6. Sidecar extraction is bound to the exact task-owned backend container and output volume, uses a
   fixed descriptor-safe reader, and retains no host copy.
7. The bounded evaluator publishes at most one strict operator receipt after cleanup; existing v1
   receipts remain byte-compatible.
8. Missing or invalid limiter sidecars produce no inference and fall back to the existing run-failure
   receipt.
9. Current public benchmark and evidence claims match executable repository truth.
10. A/B/C stay within their file-ownership and non-goal boundaries and can be independently
   reviewed and reverted.
11. All required focused, broader, deterministic, Docker, documentation, identity, presentation,
    safety, and cleanup checks pass on the exact reviewed heads.
12. No provider/model/search call, live evidence publication, version bump, release, deployment, or
    downstream business acceptance occurs without a later explicit authorization.

## Completion Boundary

Completion of PR A, PR B, and PR C proves only:

- public artifact bytes obey existing canonical delivery authority;
- a future bounded live failure caused by a locked model/tool call limiter can expose safe structural
  origin to an operator without changing business authority; and
- repository discovery surfaces describe current proof boundaries honestly.

It does not prove a successful provider run, research quality, acceptable cost, downstream consumer
acceptance, production operation, or the correctness of any future budget change. Those claims
require separate evidence and authorization.
