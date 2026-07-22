# Bounded Run Failure Diagnostic Receipt Design

**Status:** Approved direction; public-neutral design source for mechanical landing.

## Context

The bounded live producer harness already has a provider-free contract, a separately authorized
one-run live lifecycle, stable public failure envelopes, and the opt-in
`dra.bounded-live-producer-result-diagnostic.v1` receipt for a narrow class of result-boundary
failures.

A diagnostic live observation reached the protected status/result surface and produced:

```text
code           = consumer_projection_invalid
phase          = result
http_status    = 409
response_bytes = 226
diagnostic     = response_status / response_status_invalid
```

The repository-owned request path explains the loss of information. `observe_terminal()` polls
status until `execution_status` is no longer `pending` or `running`, but then requests `/result`
before it classifies the terminal status. A failed run therefore returns the canonical
`409 run_failed` result envelope and is collapsed into the generic result-status diagnostic before
the existing `_terminal_error(status)` logic can emit `run_failed / observe`.

The result diagnostic did its job: it located the failing boundary without retaining response
content. The next change must correct the observation order and make a future failed run actionable
without saving raw provider output, application databases, HTTP bodies, logs, traces, or secrets.

## Decision

Implement two tightly coupled provider-free changes:

1. classify a terminal status before requesting `/result`; and
2. add one sibling, opt-in Run Failure Diagnostic Receipt v1 that projects only the existing
   application-owned failure-cause observation status and exact phase/code pair.

The existing Result Diagnostic Receipt v1 remains byte- and behavior-compatible. A sibling schema
is preferable to mutating or replacing v1 because it preserves its fixed result-only meaning,
filename, strict consumers, and rollback boundary.

## Alternatives Considered

### Only reorder terminal classification

This would correctly emit `run_failed / observe`, but a subsequent live attempt would still omit
the application-owned cause that already exists in the status response. It would turn one generic
failure into another and would not justify another provider call.

### Reorder plus a sibling run-failure receipt — selected

This retains the stable public error while exposing only the closed failure-cause vocabulary already
owned by the application. It is sufficient to distinguish dispatch, execution, finalization,
timeout, cancellation, budget, recursion, packet, and generic execution/finalization failures.

### Preserve a raw response, task database, provider payload, or container

This would provide more detail but would expand secret handling, content retention, cleanup,
operator access, and authority boundaries. It is rejected.

## Goals

- Ensure terminal `failed`, `completed_with_fallback`, and completed-but-not-ready states are
  classified before any `/result` request.
- Preserve the existing successful `completed / not_required / ready` path and make exactly one
  `/result` request only for that path.
- Strictly validate the status response's existing `dra.run-failure-cause.v1` projection.
- Publish one bounded, owner-only, non-overwriting run-failure receipt after cleanup when and only
  when the primary error is `run_failed / observe`.
- Keep the existing public error envelope unchanged.
- Keep Result Diagnostic Receipt v1 unchanged for eligible
  `consumer_projection_invalid / result` failures.
- Make one later, separately authorized live attempt capable of identifying an actionable
  application failure cause without retaining raw content.

## Non-Goals

- No provider, model, search, Docker live observation, or credential access in this change.
- No retry, fallback retry, or automatic post-merge live execution.
- No REST/OpenAPI, database, migration, Agent runtime, canonical result, Evidence, review,
  verification, publication, or delivery-authority change.
- No new application failure-cause phase or code.
- No raw HTTP body, result payload, artifact content, Evidence content, query, scope, URL, header,
  port, path, log, exception, traceback, provider response, token, credential, or secret-derived
  value in a receipt.
- No persisted task database, failed container, LangSmith trace, or hosted diagnostic service.
- No VERSION, dependency, CI, release metadata, or live-evidence change.

## Observation Order

`observe_terminal()` keeps its single research deadline and status polling loop. After a status is
not `pending` or `running`, it must apply the following order:

```text
validate requested run/thread/profile identity
  -> classify terminal execution and delivery state
       failed                   -> run_failed / observe (+ optional safe diagnostic)
       completed_with_fallback  -> run_fallback_rejected / observe
       completed but not ready  -> run_delivery_not_ready / observe
       any other terminal tuple -> run_state_invalid / observe
  -> only completed + ready continues
  -> request /result exactly once
  -> validate result, artifact, Evidence, and downstream projection
```

No failed, fallback, delivery-blocked, or malformed terminal state may call `/result`. The existing
`project_live_observation()` checks remain as defense in depth for direct callers and tests; they do
not own the polling order.

## Existing Failure-Cause Authority

The application status response already owns `failure_cause` through
`dra.run-failure-cause.v1`. The diagnostic harness must validate that projection with the existing
application contract rather than create a second phase/code registry.

For a newly created failed run:

- an exact `observed` projection with an allowed phase/code pair produces `run_failed / observe`
  with an in-memory run-failure diagnostic;
- `not_observed`, missing, malformed, cross-phase, or extra-field cause data fails closed as
  `run_state_invalid / observe` and produces no run-failure receipt; and
- completed, fallback, or non-ready states must not carry a run-failure diagnostic.

This does not make the diagnostic receipt authoritative. The application status response and its
database ledger remain authoritative for the run failure.

## Run Failure Diagnostic Receipt v1

Add a sibling schema:

```json
{
  "schema_version": "dra.bounded-live-producer-run-failure-diagnostic.v1",
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
    "code": "execution_error"
  }
}
```

The strict receipt contract is:

- `schema_version` is exactly
  `dra.bounded-live-producer-run-failure-diagnostic.v1`;
- `primary.code` is exactly `run_failed`;
- `primary.phase` is exactly `observe`;
- `primary.retryable` is exactly `false`;
- `primary.cleanup_status` is exactly `succeeded` or `failed` and reflects the final cleanup
  result; `not_started` is invalid because this receipt is published only after an owned live
  lifecycle reaches terminal observation and attempts cleanup;
- `run_failure.cause_schema_version` is exactly `dra.run-failure-cause.v1`;
- `run_failure.observation_status` is exactly `observed`;
- `run_failure.phase` is one existing application phase;
- `run_failure.code` is valid for that exact phase in the existing application-owned matrix;
- extra fields are forbidden and strict validation rejects coercion; and
- canonical UTF-8 JSON remains at most 4 KiB.

The receipt deliberately omits run identity, state version, timestamp, HTTP status/bytes, provider
identity, model identity, duration, and content. Those fields are unnecessary to identify the
bounded application failure class.

## Diagnostic Selection And Compatibility

The existing `--diagnostic-dir` remains the only diagnostic CLI option. It may publish at most one
of two fixed files after cleanup:

```text
bounded-live-producer-result-diagnostic-v1.json
bounded-live-producer-run-failure-diagnostic-v1.json
```

Selection is exact:

| Primary failure | Eligible output |
|---|---|
| `consumer_projection_invalid / result` with a typed result diagnostic | Result Diagnostic Receipt v1 |
| `run_failed / observe` with a validated observed application cause | Run Failure Diagnostic Receipt v1 |
| success or any other failure | no diagnostic file |

Result Diagnostic Receipt v1 keeps its existing schema, filename, fields, byte serialization,
eligibility, and public-error behavior. The new receipt does not replace it and is not a migration
target for existing v1 consumers.

The diagnostic directory preflight must reject the invocation if either fixed final filename
already exists. Publication remains non-overwriting and writes only the selected fixed basename.
One invocation can never publish both files.

## Sink And Cleanup Safety

Reuse the existing descriptor-relative, owner-only diagnostic sink and its identity, symlink,
permission, non-overwrite, bounded-write, `fsync`, link, quarantine, and cleanup protections.
Refactor only enough to parameterize the approved fixed basename and strict serializer.

The directory remains:

- absolute and repo-external;
- pre-existing, owned by the invoking UID, and mode-restricted;
- free of symlink traversal;
- identity-stable for the command lifetime; and
- non-authoritative and writable by the invoking UID.

The in-memory diagnostic is created before cleanup, and the selected receipt is published after
cleanup so `cleanup_status` is final. A diagnostic publication failure never replaces the primary
evaluation error. A same-UID directory owner may mutate the file during or after publication, so
every consumer must strict-validate it.

## Error Handling

- Public stdout/stderr and exit-code behavior remain unchanged.
- `run_failed / observe` is the primary public error for an exact failed terminal status.
- A missing or invalid failure-cause projection is `run_state_invalid / observe`, not a guessed
  `run_failed` diagnostic.
- Result HTTP failures remain governed by Result Diagnostic Receipt v1.
- Cleanup failure is grouped with the primary error and reflected in the selected receipt.
- Unknown internal exceptions receive no guessed diagnostic.

## Testing

The implementation must add deterministic RED-to-GREEN coverage for:

1. failed status classification before `/result`, with a client that fails the test if
   `result_observation()` is called;
2. fallback and delivery-not-ready states also avoiding `/result`;
3. completed/ready invoking `/result` exactly once and preserving the accepted projection;
4. every existing application-owned failure-cause phase/code pair;
5. missing, `not_observed`, malformed, cross-phase, coerced, and extra-field causes failing closed;
6. strict run-failure receipt schema, canonical bytes, 4 KiB bound, and public-safety scan;
7. exact diagnostic selection and proof that one invocation cannot publish both files;
8. preflight rejection when either fixed filename exists;
9. descriptor-relative non-overwrite, symlink, replacement, permission, `fsync`, cleanup, and
   primary-plus-cleanup behavior for the new basename;
10. unchanged Result Diagnostic Receipt v1 bytes and eligibility;
11. unchanged public error envelope without `--diagnostic-dir`;
12. no diagnostic on success or ineligible failures; and
13. documentation contracts that lock both receipt registries and non-claims.

Run the complete bounded-producer provider-free matrix, affected application failure-cause tests,
documentation/release contracts, deterministic `check` twice for byte equality, canonical identity,
presentation audit, `git diff --check`, and public/private/credential scans. Run the existing
required Docker authority lane because the proof lifecycle and diagnostic sink are shared, but do
not run `observe-live`.

## Delivery Sequence

1. Land and review this public-neutral design.
2. Land and review a TDD implementation plan.
3. Implement the provider-free ordering and sibling receipt in one focused PR.
4. Merge only after authoritative branch-diff review and exact-head hosted CI.
5. Obtain a separate authorization for at most one final live observation.
6. If that observation succeeds, review an evidence-only change.
7. If it produces an actionable application cause, decide whether one targeted fix is justified.
8. If it remains inconclusive or exposes no new evidence-backed hypothesis, record the known
   limitation and stop; do not retry.

## Migration And Rollback

There is no application data migration. Existing Result Diagnostic Receipt v1 consumers remain
compatible. Consumers that want the new run-failure receipt opt into the sibling fixed filename and
strict schema.

Rollback is a source revert of the terminal ordering, sibling contract, sink parameterization,
tests, and documentation. It does not require deleting application data, Evidence, release assets,
or a committed live report.

## Public Claims

This change may claim only that the provider-free harness classifies terminal state before result
fetch and can emit one bounded, non-authoritative application failure-cause receipt after cleanup.
It must not claim a successful live observation, provider quality, source truth, downstream
acceptance, production deployment, SLA, or business outcome.
