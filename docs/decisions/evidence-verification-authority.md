# Evidence Verification Authority

## Decision

Decision Research Agent keeps collected Evidence immutable and stores human
verification as append-only decisions bound to one exact
`run_id + evidence_id + evidence_fingerprint` tuple.

Deterministic preflight establishes whether a persisted Evidence snapshot is
eligible for a human `verify` decision. Preflight does not fetch a URL, resolve
DNS, call an LLM, or judge truth. A human decision may append `verify` or
`reject`; corrections append a new revision and never update prior rows.

## Authority Boundary

- `evidence_entries_v2` owns what the run collected.
- `baseline_verification_origin=declared_fixture` records only the controlled
  server-bundled benchmark contract.
- `evidence_verification_preflights_v2` owns deterministic eligibility checks.
- `evidence_verification_decisions_v2` owns human decision history.
- `evidence_verification_snapshots_v2` owns one deterministic effective-state
  input for later artifact rebuilding.
- Review approval owns delivery permission and never grants Evidence
  verification.
- LangSmith remains diagnostic correlation and is not a business ledger.

`human_verified` means an authenticated reviewer confirmed that the persisted
snippet for the exact fingerprint was consistent with the identified source at
the recorded decision time. It is not a universal truth, claim approval, market
accuracy score, or guarantee that the source remains unchanged.

## Compatibility

Existing Talent benchmark fixtures remain effectively `verified` with origin
`declared_fixture`. They are not labeled `human`. Ordinary legacy
`verification_status=verified` rows do not gain fixture or human authority
unless the migration also proves the persisted Talent scope declared a
`provided_aggregate`.

PR1 adds no API, CLI, publication pointer, artifact revision, or new review
workflow. Those changes require the separately approved P2A PR2.

## Rejected Alternatives

- Mutating `evidence_entries_v2.verification_status`: rejected because it erases
  decision history and stale fingerprint boundaries.
- Automatic LLM verification: rejected because a model is not the human
  authority for this milestone.
- Server-side URL retrieval: deferred because it adds SSRF, redirect, DNS,
  payload, content-type, and source-drift risks not required for PR1.
