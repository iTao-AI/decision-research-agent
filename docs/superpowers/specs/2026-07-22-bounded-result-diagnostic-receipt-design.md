# Bounded Result Diagnostic Receipt v1 Design

## Status

Approved on 2026-07-22 for public-neutral specification, mechanical landing, and implementation
planning. This document does not authorize implementation, provider credentials, a live provider
run, network cost, push, pull request creation, merge, tag, release, deployment, or publication of
live evidence.

Planning baseline: Decision Research Agent `main` at
`f0d7e440438d18bb2941f01ec8b7b11625a6ef1b`, with `VERSION=0.1.5`.

## Summary

The bounded live producer evaluation has repeatedly reached the terminal result boundary and then
failed with the stable public error `consumer_projection_invalid`. Deterministic persisted
API-to-consumer projection tests pass, and earlier repairs already distinguish canonical artifact,
state, Evidence, fallback, and hash failures. The remaining public code still intentionally
collapses several materially different result-boundary failures:

```text
result connection or response read
  -> HTTP status acceptance
  -> bounded UTF-8 and JSON object decoding
  -> requested run identity
  -> downstream consumer contract
  -> accepted projection disposition
  -> consumer_projection_invalid
```

Another provider-backed attempt without better observability would test no new hypothesis. This
design adds one opt-in, versioned, bounded, public-safe diagnostic receipt that identifies which
result-boundary stage rejected the observation without retaining the response body, artifact
content, Evidence, credentials, URLs, headers, logs, exceptions, tracebacks, local paths, ports, or
database state.

The existing public error envelope remains byte-compatible. The diagnostic receipt is an
operator-owned troubleshooting artifact, not live evidence, a canonical result, a consumer
contract, or application business authority.

## Inspected Baseline

The design was finalized against a clean primary checkout with:

- `main == origin/main == f0d7e440438d18bb2941f01ec8b7b11625a6ef1b`;
- `VERSION=0.1.5`;
- no open pull requests;
- the bounded live producer evaluation and its provider-free deterministic gate on `main`;
- the canonical report completion guard using the locked LangChain/DeepAgents middleware order;
- stable taxonomy mappings for exact `run_result_unavailable`, artifact, state, Evidence,
  fallback, and hash failures;
- a public error envelope containing exactly schema version, code, phase, retryability, and
  cleanup status;
- `ProofHttpClient._request_json` collapsing transport, bounded-read, unexpected status, and JSON
  failures into the caller-supplied stable code;
- `ProofHttpClient.result` collapsing response identity mismatch into
  `consumer_projection_invalid`;
- `project_live_observation` mapping unclassified downstream `contract_result_invalid` and
  `contract_schema_invalid` failures to `consumer_projection_invalid`; and
- cleanup that deliberately removes task-owned runtime state and does not preserve raw provider or
  result payloads.

The design relies on these current implementation facts, not on historical live payloads. Previous
failed observations were correctly cleaned up, so their specific internal cause is not recoverable
and must not be inferred.

## Problem

`consumer_projection_invalid` is a correct fail-closed public disposition, but it no longer gives
the operator enough information to choose a deterministic repair. A failure can still mean any of
the following:

- the result connection could not produce a complete response;
- the response body could not be read within the existing bound;
- the HTTP status was outside the accepted `200` or retained canonical `409` paths;
- the response was not bounded UTF-8 JSON or was not a JSON object;
- the response identified a different run;
- the strict downstream consumer rejected the result contract or schema; or
- the consumer projection returned an unexpected disposition.

Changing one or two public error codes would only replace one broad bucket with several broad
buckets. Retaining the container, database, raw response, or logs would improve diagnosis at the
cost of the privacy, cleanup, and authority boundaries the proof is intended to demonstrate.

The required capability is therefore a narrow observation layer that records safe structural
facts before raw state is discarded and publishes them only through an explicitly requested,
operator-owned diagnostic sink.

## Product Decision

Add `dra.bounded-live-producer-result-diagnostic.v1` as an opt-in JSON-only receipt for an eligible
`consumer_projection_invalid` failure in the `result` phase.

The receipt must:

1. use a closed schema and closed stage/reason registries;
2. contain only structural metadata already observed by the proof;
3. be constructed before cleanup but written only after cleanup status is known;
4. use a caller-provided, repo-external, preflighted output directory and one fixed basename;
5. use atomic create-without-overwrite semantics and a strict byte limit;
6. never replace or weaken the existing primary error;
7. remain absent from required CI outputs and committed live evidence; and
8. leave default `check` and `observe-live` behavior byte-compatible when no diagnostic sink is
   supplied.

The implementation may add proof-owned internal types and exception metadata. It must not change
the REST API, OpenAPI schema, application database, Agent runtime, canonical result, Evidence,
downstream consumer acceptance contract, or framework authority.

## Goals

1. Distinguish every current generic result-boundary rejection stage without exposing raw data.
2. Preserve the current stable public error envelope and provider-free deterministic output.
3. Allow one future live observation to identify a deterministic next action rather than another
   broad failure bucket.
4. Prove with mutation tests that each diagnostic reason is produced only by its intended boundary.
5. Preserve bounded memory, total deadline, cleanup ordering, non-overwrite, and public-safety
   guarantees.
6. Keep the implementation independently reviewable and releasable as one focused pull request.

## Non-Goals

This change does not add or claim:

- a successful live provider observation or committed live evidence;
- a retry, an additional run intent, or automatic provider execution;
- raw response capture, artifact excerpts, Evidence excerpts, logs, tracebacks, exception text,
  headers, URLs, query strings, ports, container identifiers, database paths, or credential data;
- a general logging, tracing, audit, or observability platform;
- a new REST or Tool Client error contract;
- a new public downstream consumer schema or a second result validator;
- artifact repair, response coercion, schema relaxation, or acceptance of malformed output;
- changes to DeepAgents, LangChain, LangGraph, LangSmith, middleware ordering, model/tool budgets,
  provider selection, or Agent execution;
- database persistence, migration, hosted diagnostics, telemetry upload, or LangSmith authority;
- durable usage or cost accounting, provider billing, or source-truth verification;
- a version bump, release preparation, deployment, or downstream product acceptance; or
- preservation of failed task containers, volumes, databases, images, or temporary credential
  snapshots.

## Authority And Compatibility Boundaries

| Surface | Existing authority | Diagnostic responsibility |
|---|---|---|
| HTTP result | DRA REST API and proof-owned exact loopback transport | Classify the observation stage; do not reinterpret response content |
| Consumer acceptance | `project_consumer_case` | Record its closed error code or accepted disposition; do not change acceptance |
| Public failure | existing evaluation error envelope v1 | Remain the canonical CLI failure and byte-compatible default output |
| Cleanup | managed lifecycle ownership receipt | Complete cleanup before diagnostic publication and report actual cleanup status |
| Diagnostic file | operator-owned safe directory | Store one non-authoritative structural receipt with atomic non-overwrite |
| Application state | DRA database and canonical result service | No diagnostic persistence or mutation |
| Framework runtime | existing DeepAgents/LangChain/LangGraph integration | No new diagnostic or business authority |

The diagnostic receipt cannot make a failed observation valid. Its existence does not prove that a
provider returned a correct answer, that a canonical artifact is acceptable, or that a downstream
consumer accepted the result.

## Receipt Contract

The JSON receipt contains exactly:

```json
{
  "schema_version": "dra.bounded-live-producer-result-diagnostic.v1",
  "primary": {
    "code": "consumer_projection_invalid",
    "phase": "result",
    "retryable": false,
    "cleanup_status": "succeeded"
  },
  "result_boundary": {
    "stage": "consumer_contract",
    "reason": "contract_result_invalid",
    "http_status": 200,
    "response_bytes": 1234
  }
}
```

All models are strict, frozen, and `extra="forbid"`. The top-level keys are exactly
`schema_version`, `primary`, and `result_boundary`.

### Primary

`primary` is the exact public failure projection after cleanup. It contains only:

- `code`, fixed to `consumer_projection_invalid`;
- `phase`, fixed to `result`;
- `retryable`, fixed to `false`; and
- `cleanup_status`, one of the existing `not_started`, `succeeded`, or `failed` values.

### Result boundary

`result_boundary.stage` is exactly one of:

- `connection`;
- `response_status`;
- `response_body`;
- `response_json`;
- `response_identity`;
- `consumer_contract`; or
- `projection_disposition`.

`result_boundary.reason` is exactly one of:

- `connection_failed`;
- `response_status_invalid`;
- `response_read_failed`;
- `response_size_exceeded`;
- `response_utf8_invalid`;
- `response_json_invalid`;
- `response_not_object`;
- `run_identity_mismatch`;
- `contract_result_invalid`;
- `contract_schema_invalid`; or
- `projection_disposition_invalid`.

Only valid stage/reason pairs are accepted:

| Stage | Reasons |
|---|---|
| `connection` | `connection_failed` |
| `response_status` | `response_status_invalid` |
| `response_body` | `response_read_failed`, `response_size_exceeded` |
| `response_json` | `response_utf8_invalid`, `response_json_invalid`, `response_not_object` |
| `response_identity` | `run_identity_mismatch` |
| `consumer_contract` | `contract_result_invalid`, `contract_schema_invalid` |
| `projection_disposition` | `projection_disposition_invalid` |

`http_status` is either `null` when no valid response status was observed or the exact integer in
the inclusive range 100 through 599. `response_bytes` is either `null` when a complete body was not
retained or an integer from 0 through the existing `MAX_HTTP_RESPONSE_BYTES` bound.

No key names from the response, strings from the response, hashes derived from the response,
provider identifiers, model identifiers, request identifiers, or secret-derived values are
allowed in the receipt.

## Diagnostic Capture Flow

The result observation follows this order:

1. Validate the requested run identifier using the existing public error behavior.
2. Open the exact no-proxy, no-redirect loopback connection under the existing deadline.
3. Record only whether a valid response status was observed.
4. Read the body under the existing byte bound while retaining only the completed byte count as
   diagnostic metadata.
5. Decode bounded UTF-8 JSON and require a JSON object.
6. Apply the existing accepted status rules.
7. Require the requested `run_id` identity.
8. Call the existing downstream consumer projection unchanged.
9. Require the existing accepted projection disposition.
10. On an eligible generic failure, attach one internal strict diagnostic object to the existing
    evaluation error without serializing raw state.
11. Execute the existing cleanup path.
12. If and only if an explicit diagnostic sink was preflighted, serialize one diagnostic receipt
    with the final cleanup status.
13. Emit the unchanged one-line public error envelope on stderr and exit 1.

The proof must discard the raw body and parsed response as soon as they are no longer needed. The
diagnostic object contains only the closed structural fields above.

Failures already classified as `artifact_invalid`, `artifact_hash_mismatch`, `evidence_invalid`,
`run_state_invalid`, or `run_fallback_rejected` do not emit this receipt because they already have
an actionable stable classification.

## Diagnostic Output Boundary

The existing CLI may add one optional `observe-live` argument named `--diagnostic-dir`.

The directory must be:

- absolute and outside the repository worktree;
- pre-existing and opened without following symlinks;
- a directory owned by the current effective user;
- mode `0700` or stricter;
- not group- or world-writable;
- represented by one filesystem object during preflight and publication; and
- free of the fixed output basename
  `bounded-live-producer-result-diagnostic-v1.json`.

Invalid output ownership fails in the input phase before Docker, credentials, or provider activity.
The implementation must use descriptor-relative operations, `O_NOFOLLOW` where supported,
exclusive creation, mode `0600`, a bounded temporary file, `fsync`, atomic link or rename without
overwrite, and directory `fsync`. It must not accept an arbitrary output filename.

The receipt is bounded to 4 KiB of canonical UTF-8 JSON. It is JSON-only and has no Markdown
projection. A pre-existing final or temporary path is never overwritten or removed.

The operator is responsible for reading and deleting the receipt after diagnosis. The managed
Compose cleanup must not delete arbitrary operator directories. The receipt is not a task runtime
residue and is never committed as live evidence.

## Failure And Dual-Failure Semantics

The existing evaluation error remains primary. Diagnostic capture or publication must never:

- change `consumer_projection_invalid` into success;
- change retryability;
- replace a cleanup failure;
- hide a primary result failure; or
- authorize a provider retry.

If cleanup also fails, the receipt records `cleanup_status=failed` while preserving the result
stage/reason. If diagnostic publication fails, the CLI still emits the original public evaluation
error. The failure must not overwrite or delete a pre-existing operator path. Provider-free tests
must make diagnostic publication failures observable to the test harness without adding raw detail
to the public error envelope.

Unknown internal exceptions do not receive a guessed result diagnostic. They keep the existing
`evaluation_internal_error` behavior.

## Deterministic Test Matrix

Required provider-free tests must prove:

### Contract and serializer

- exact schema, key set, enums, valid stage/reason pairs, integer bounds, strict types, frozen
  models, canonical serialization, import silence, and a 4 KiB maximum;
- rejection of unknown fields, booleans as integers, NaN/Infinity, raw strings, response key names,
  URLs, paths, ports, headers, credentials, provider/model identifiers, tracebacks, and secret-like
  markers;
- public error serialization remains byte-identical without a diagnostic sink.

### HTTP stage classification

- connection failure before a status;
- invalid status object or out-of-range status;
- malformed, negative, or oversized declared length;
- bounded-read exception;
- body exceeding the existing maximum;
- invalid UTF-8;
- invalid JSON;
- valid JSON that is not an object;
- unexpected complete HTTP status;
- requested run identity mismatch; and
- successful exact result response with no diagnostic object.

### Consumer and projection classification

- `contract_result_invalid` and `contract_schema_invalid` map only to their exact diagnostic
  reasons while the public code remains `consumer_projection_invalid`;
- existing artifact, Evidence, state, fallback, and hash mappings remain unchanged and do not
  create the generic receipt;
- unexpected accepted-projection disposition maps only to
  `projection_disposition_invalid`;
- a valid supported projection produces no receipt.

### Output and cleanup

- valid repo-external owner-only directory;
- relative, repository-contained, symlinked, replaced, group/world-writable, wrong-owner, missing,
  or pre-populated directory rejection before mutation;
- atomic create, non-overwrite, bounded temporary files, final and directory `fsync`, and no
  unrelated cleanup;
- primary-only, primary-plus-cleanup, and diagnostic-write-failure paths;
- final cleanup status is reflected without changing the primary error;
- no diagnostic output on success, provider-free `check`, or non-eligible failures; and
- no provider, network, Docker service, or live evidence requirement in the deterministic gate.

Mutation tests must fail if adjacent result stages collapse into one reason, raw response material
enters the receipt, the default error envelope changes, cleanup is skipped, or a pre-existing path
can be overwritten.

## Documentation Impact

The implementation PR updates only documentation needed to describe:

- the opt-in operator diagnostic contract;
- the unchanged public failure envelope;
- the privacy and authority boundary;
- the fixed output ownership rules;
- the provider-free verification commands; and
- the live retry stop condition.

It may amend the existing bounded live producer reference, design, and implementation plan where
required for consistency. It must not add a live evidence file, release note, version bump, or
downstream product claim.

## Delivery And Live Stop Sequence

Delivery remains deliberately staged:

1. Land this approved design mechanically.
2. Write and review a TDD implementation plan.
3. Implement and merge the provider-free diagnostic capability as one focused pull request.
4. Obtain separate authorization for exactly one diagnostic live observation.
5. If the receipt identifies a reproducible deterministic defect, implement and merge one targeted
   fix without provider activity.
6. Obtain separate authorization for exactly one post-fix validation observation.
7. If the diagnostic observation remains inconclusive, or the post-fix validation still fails
   without a new evidence-backed hypothesis, record the result as a known limitation and stop.

No step authorizes an automatic retry. A failed attempt cannot reuse an earlier live authorization.

## Compatibility And Migration

- The existing public error schema version and bytes remain unchanged by default.
- `bounded_live_producer_proof.py check` remains byte-identical.
- `observe-live` without `--diagnostic-dir` remains behaviorally and byte compatible.
- The optional diagnostic file is additive, repo-external, and non-authoritative.
- The REST API, OpenAPI, Tool Client, database, canonical result, Evidence, and downstream consumer
  contracts do not migrate.
- No dependency or framework version changes are required.
- Rollback is a source revert of the diagnostic code, tests, and documentation; it does not require
  data migration or evidence deletion.

## Risks And Mitigations

| Risk | Mitigation |
|---|---|
| Diagnostic receipt becomes a second error authority | Keep the existing error envelope primary and fix the receipt to one eligible failure class |
| Structural metadata leaks sensitive content | Closed enums and bounded integers only; forbid response-derived strings and hashes |
| Output path creates overwrite or symlink risk | Owner-only pre-existing directory, fixed basename, descriptor-relative exclusive atomic publication |
| Additional instrumentation changes acceptance | Diagnostic data is attached only after existing failure decisions; consumer contract remains unchanged |
| Cleanup loses the diagnostic | Build the strict object before cleanup and publish after final cleanup status is known |
| Diagnostic write masks the real failure | Preserve the original evaluation error and test dual-failure behavior |
| One more live run becomes another blind retry | Require the merged receipt capability and one-shot stop sequence before provider authorization |
| Schema grows into general observability | Keep v1 result-only, JSON-only, opt-in, non-persistent, and provider-free in CI |

## Rejected Alternatives

### Add two more broad public failure codes

This still leaves multiple unrelated causes in each bucket and can consume another provider run
without a deterministic next action.

### Expose raw exception text or response body

Raw material may contain report content, source details, paths, provider data, or secrets and would
violate the proof's public-safety boundary.

### Preserve the failed container or application database

This weakens cleanup, privacy, and task ownership and turns one bounded proof into an operational
forensics system.

### Change the downstream consumer validator first

The deterministic consumer path passes. There is no evidence that acceptance semantics need to
change; only the failure stage is currently unobservable.

### Change the REST API or canonical result contract

The current evidence does not establish a runtime contract defect. Public runtime changes require
a separately proven consumer or operator blocker.

### Add framework tracing or LangSmith authority

The gap is in a proof-owned post-run HTTP/result boundary. Framework tracing does not own the REST
response, consumer projection, cleanup, or diagnostic file and is unnecessary for this contract.

## Acceptance Criteria

The implementation is acceptable only when:

1. all receipt fields, stage/reason pairs, output rules, and byte bounds are strict and tested;
2. every current generic result-boundary branch has one deterministic diagnostic classification;
3. the existing public error envelope and provider-free check remain byte-identical by default;
4. raw response, artifact, Evidence, credential, URL, header, log, exception, path, port, Docker,
   and database material cannot enter the receipt;
5. the downstream consumer acceptance contract is reused unchanged;
6. cleanup completes before publication and dual failures preserve the primary result cause;
7. output preflight and publication cannot overwrite or follow an untrusted path;
8. required CI remains credential-free, provider-free, network-free except for the existing Docker
   build requirements, and deterministic;
9. API, DB, Agent/framework authority, dependencies, CI provider policy, VERSION, release metadata,
   and live evidence remain unchanged unless the reviewed implementation plan explicitly proves a
   documentation-only consistency update is necessary; and
10. no live observation occurs in the implementation PR.

## Final Decision

Proceed with one focused Bounded Result Diagnostic Receipt v1 change. Expand observability only far
enough to make the next result-boundary failure actionable, while preserving the existing public
error, cleanup, privacy, consumer, and business-authority boundaries. Do not broaden into raw
forensics, runtime contract changes, or repeated provider experimentation.
