# Research findings delivery authority

Date: 2026-10-01. Status: accepted boundary for the approved research-findings
delivery design. Strict contracts are implemented; producer, resolver,
persistence integration and API/UI consumer wiring are subsequent slices.

## Decision

The application database remains authoritative for ResearchRun, EvidenceLedger,
artifact metadata and delivery state. Native DeepAgents planning, researchers,
virtual file tools and stream capture produce candidate material. Virtual files,
model output, LangGraph checkpoints, LangSmith traces and the browser do not
assign business authority.

`agent/research_findings_contracts.py` separates the bounded
`dra.research-findings-candidate.v1` producer contract from the application-owned
`dra.research-findings.v1` report and closed-code
`dra.research-findings-diagnostics.v1` diagnostics. All models use strict
Pydantic validation, forbidden extra fields and frozen attributes. Lists remain
ordinary lists under Pydantic's shallow `frozen` semantics; accepted snapshots
must be serialized and persisted through the application boundary rather than
treated as mutable business ledgers. Model candidates cannot supply Evidence
IDs/fingerprints, finding IDs, approval, verification, confidence or delivery
claims. Contract validation enforces local shape and uniqueness; accepted-scope
membership, complete dispositions and finding/disposition consistency belong
to the application resolver.

Scope contains exactly `questions`: 1–5 unique ASCII question IDs and trimmed
question text of 1–4096 characters. Omitted questions default to query as `q1`;
an explicitly empty list fails validation. Candidates contain at most 20
findings, each with 1–10 source URL/excerpt references, 1–5 unique dispositions,
and bounded model-reported contradictions and limitations. Empty findings are
structurally representable for honest unresolved research; this alone grants
no delivery readiness. The candidate byte-size limit is enforced by the
future producer reader, outside these field contracts.

## Evidence resolution and non-claims

The application resolver must use the frozen, same-run observed Evidence
snapshot and existing source-identity normalization. It must require a
publishable source URL, exactly one matching Evidence entry and exactly one
contiguous excerpt occurrence in the stored snippet. Missing, cross-run,
invented or ambiguous references fail closed. It must not re-fetch a source
to bind a reference or accept model-invented authority.

Bound references carry the application-owned Evidence ID/fingerprint, source
URL/identity, unchanged frozen snippet, verbatim excerpt and zero-based,
half-open Python Unicode code-point offsets. Offsets count neither UTF-8 bytes
nor UTF-16 code units. Local validation checks that
`snippet[excerpt_start:excerpt_end] == excerpt`; the resolver must additionally
prove unique binding to observed Evidence. Application code assigns stable
`f1`, `f2`, … finding IDs in accepted order.

Source binding proves where candidate material came from. It does not verify
source truth, entailment, answer accuracy or human value. Reported
contradictions remain model-reported. Human verification and approval retain
their existing authority: approval permits delivery and does not verify
Evidence. Diagnostics expose fixed issue codes and counts, never raw model
text, exceptions or private paths.

## Finalization and framework reuse

The new opt-in profile must integrate JSON and deterministic Markdown artifacts
into the existing `finalize_run_transaction` boundary. Run/segment/state-version
and execution-owner fencing prevent stale writers; the accepted terminal state,
frozen Evidence and artifact metadata must commit atomically. Execution can
complete while delivery is blocked. Legacy generic and strict-citation behavior
retains its current contracts; no legacy fallback may satisfy the new profile.

Pydantic 2.13.4's installed `StringConstraints`, `ConfigDict` and validators were
checked alongside current [official strict-mode documentation](https://docs.pydantic.dev/latest/concepts/strict_mode/)
and [model immutability documentation](https://docs.pydantic.dev/latest/concepts/models/#faux-immutability)
through Context7. Native validation supplies strict types, bounds, extra-field
rejection and frozen attributes. Small application validators enforce the
domain's uniqueness, disposition-reason and exact-offset rules. Checkpoints
and tracing cannot replace the application ledger; no framework upgrade or
additional orchestrator is required.

Provider-free contract and Talent finalization regressions validate this first
slice. They do not prove native research-findings production or a paid-provider
run. Native producer-through-reader proof remains a subsequent delivery gate;
paid-provider evidence requires separate authorization.

## Adjacent Talent repair

A Talent packet with neither findings nor candidate claims now produces
`empty_research_output` in the existing ReviewBundle policy. Finalization keeps
execution `completed` and sets delivery `review_required`. A human may explicitly
resolve a legitimate no-findings outcome through the existing review workflow.
Findings-only nonempty output remains eligible under existing reference and
review rules; the policy does not require every packet list to be nonempty.
