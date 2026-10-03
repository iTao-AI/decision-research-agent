# Research findings delivery authority

Date: 2026-10-01. Status: accepted boundary for the approved research-findings
delivery design. Strict contracts, the pure frozen-Evidence resolver, native producer, fenced
persistence, independent API readers and the opt-in structured Live reader are
implemented. The [native proof](../evidence/research-evidence-delivery-v1.md) and
[walkthrough](../operations/research-evidence-delivery.md) record four independently
declared synthetic outcomes through installed graph/file/stream/DB/HTTP paths.
Actual desktop/narrow and keyboard observations are recorded in a separate
[browser receipt](../evidence/research-evidence-delivery-reader-v1.md).
Integrated acceptance remains a delivery-owner gate; real-provider adherence
and research quality remain unproven.

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
application candidate parser at 256 KiB, outside these field contracts. The
pure resolver, native producer and persisted-reader wiring are implemented. Canonical JSON and Markdown are each bounded to
1 MiB, matching the existing result-reader limit. Repeated frozen snippets can
expand a small candidate beyond that bound; `artifact_package_too_large`
blocks the entire package and emits only bounded closed-code diagnostics.
An explicit closed capture issue takes precedence over earlier candidate text.

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

Provider-free native regressions now exercise installed build_generic_harness,
named network_search/internet_search, native write_file, stream capture, application
execution, real server dispatch/fenced DB and independent HTTP JSON/Markdown
consumers. Failed file/source tools and missing/invalid/empty candidate controls
complete with blocked delivery. These are synthetic local structural outcomes;
paid-provider evidence and research quality require separate authorization.

Ready packages persist typed diagnostics as a third artifact in the same fenced
transaction, after canonical JSON and Markdown. Blocked packages retain only
diagnostics. Each artifact hashes its own UTF-8 bytes; status diagnostics use a
4 KiB read bound and closed fields. Invalid root VFS replacement discards prior
candidate bytes. The existing completion middleware chooses the candidate target
from server-owned runtime context with one correction; the shared graph and
legacy Markdown ReportCandidate guard remain intact.

The recovery lifecycle classifier now accepts completed/not_required/blocked
with all existing closed-owner/finalization, segment, version, dispatch and
no-failure-cause checks. This records completed execution without granting
delivery, verification or review authority. Nonterminal and failed admission
remain unchanged.

## Adjacent Talent repair

A Talent packet with neither findings nor candidate claims now produces
`empty_research_output` in the existing ReviewBundle policy. Finalization keeps
execution `completed` and sets delivery `review_required`. A human may explicitly
resolve a legitimate no-findings outcome through the existing review workflow.
Findings-only nonempty output remains eligible under existing reference and
review rules; the policy does not require every packet list to be nonempty.


The shared coordinator prompt retains the Markdown default and explicitly allows
only the server-supplied structured profile envelope to select the JSON target,
with precedence over legacy Skill output-format wording. The server constructs
that envelope from validated profile/scope and quotes query/question text as
untrusted research content. Provider-free tests prove native mechanics and
delivery authority; they do not prove real-model instruction adherence.

The producer envelope also states the existing intake boundary: Evidence capture
collapses whitespace and truncates observed snippets to 1000 code points. Exact
excerpts must occur uniquely and contiguously inside that stored normalized
snippet; later passages of a longer raw tool result cannot satisfy binding.
