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
unless the migration also proves an aggregate-only Talent scope and the row has
legacy `verification_status=verified`.

P2A PR2 exposes the authority through strictly authenticated API and canonical
Tool Client operations. It adds an explicit revisioned publication head:

- a new accepted human decision atomically stales the current publication;
- the changed effective snapshot deterministically rebuilds immutable artifacts;
- every changed snapshot requires a fresh durable review;
- an earlier review decision cannot approve a later publication;
- only `is_current=1 AND status=ready` is deliverable.

Collected Evidence and ResearchPackets remain immutable. A correction that only
changes verification authority and derived delivery does not require a new
`run_id`. Review approval remains delivery permission and never grants Evidence
verification.

The controlled boundary remains default-disabled, single-node SQLite, and one
backend replica. PR2 adds no source retrieval, LLM verification, UI, RBAC,
Skills, Async Subagents, multi-instance behavior, or real-source proof.

## Rejected Alternatives

- Mutating `evidence_entries_v2.verification_status`: rejected because it erases
  decision history and stale fingerprint boundaries.
- Automatic LLM verification: rejected because a model is not the human
  authority for this milestone.
- Server-side URL retrieval: deferred because it adds SSRF, redirect, DNS,
  payload, content-type, and source-drift risks not required for PR1.
