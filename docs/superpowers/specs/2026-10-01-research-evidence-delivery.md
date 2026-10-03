# Research findings with inspectable evidence

Date: 2026-10-01. Status: approved design for local implementation by the design owner under the delegated improvement scope. Implementation and publication are separate gates.

## Goal and current behavior

A reader should move from a research question to candidate findings, inspect the exact observed source excerpt for each finding, and see which questions remain unresolved. A deliverable must distinguish execution completion, structural validity, source binding, and semantic correctness.

Current generic research already has native DeepAgents planning, named researchers, a run-scoped virtual workspace, trusted nested tool-result capture, durable finalization, and a canonical Markdown report. The live reader displays that report and run-level sources. The richer finding-to-excerpt fixture is not a live producer contract. Talent has typed packets, but an empty packet can currently pass automatic readiness checks. Do not rebuild existing orchestration, report completion, crash recovery, or run identity.

## Chosen design and alternatives

Add an opt-in generic-evidence-report@1 profile, using the existing generic harness policy, and an application-owned dra.research-findings.v1 artifact. Preserve the defaults and contracts of generic and generic-strict-citation.

The model writes a bounded JSON candidate in the virtual workspace. Application code resolves its references against Evidence already observed in the same run, constructs the canonical JSON and human-readable Markdown, and owns delivery. This reuses the native producer instead of adding a post-processing model or a second orchestrator.

Rejected alternatives: extract claims by parsing arbitrary Markdown; infer support from URL citation alone; have a model invent Evidence IDs or verification status; make fixtures the live producer; replace all legacy profiles. Automatic semantic grading is outside this change.

## Contract and data flow

1. Scope accepts 1–5 unique research questions with stable question IDs and bounded non-empty text. If no explicit questions are supplied, the existing query becomes q1. The server validates this scope before starting the run.
2. The coordinator writes /workspace/research-findings.json through the existing native file tools. The candidate includes schema version, candidate findings, per-question disposition, optional reported contradictions, and limitations. Bound the candidate to 256 KiB and at most 20 findings. The implementation plan defines strict field and string bounds within these limits.
3. Each candidate finding has a question ID, statement, and one or more references containing an exact source URL and quoted excerpt. Candidate references do not contain authoritative IDs, hashes, confidence thresholds, verification decisions, or delivery status. Each question has either candidate findings or an explicit unresolved reason. Unknown or duplicated question IDs are invalid.
4. A pure application resolver binds each reference to a unique, publishable same-run Evidence entry by the project's existing source-identity normalization and an exact contiguous excerpt in that stored snippet. It produces the persisted Evidence identity and fingerprint, plus excerpt offsets over the stored snippet. Multiple occurrences or multiple matching entries are ambiguous and rejected. Resolve against the frozen ledger, never against a fresh network request or model text.
5. Persist research-findings.json and a deterministically rendered research-report.md in the existing fenced finalization transaction. The JSON carries the run/profile/schema identity, findings, bound source references, per-question disposition, limitations, and reported contradictions. The model cannot assign authority. Hashes follow existing artifact conventions.
6. The new profile is ready only when a structurally valid package contains at least one source-bound candidate finding. Missing, invalid, ambiguous, or wholly empty output is blocked with bounded machine-readable reasons; a legacy fallback must not satisfy this profile. Honest unresolved questions are allowed alongside deliverable findings. Execution may complete while delivery is blocked. This does not change the meaning of ready for legacy profiles.
7. A new read-only GET /api/runs/{run_id}/findings resolves the current deliverable JSON through repository delivery authority and hash validation. Match existing run/result error behavior; do not expose VFS state, stale artifacts, or internal exception text. Existing result consumers still receive Markdown from the canonical result endpoint.
8. The live page offers an explicit structured research mode, preserves the existing generic mode, and displays questions, candidate findings, bound snippets and sources, unresolved questions, and limitations. Evidence inspection uses persisted projections; it must not fetch arbitrary source URLs in the server. Render strings as text and apply the existing safe-link policy.

A bound excerpt proves where the candidate came from. It does not prove that the source is true or that the excerpt entails the claim. The UI names this state as source-bound candidate material. Reported contradictions remain model-reported unless independently reviewed. Human source verification and approval keep their existing authority and are never granted automatically by this profile.

## Adjacent readiness repair

In the Talent readiness policy, a packet with no findings and no claims must enter the existing review-required path with an explicit empty-output issue instead of becoming automatically ready. Reuse the current review workflow. A human may explicitly resolve a legitimate no-findings outcome under that workflow; do not fabricate a finding or indiscriminately require every list to be non-empty. Cover the actual API finalization path as well as the policy helper.

## Native boundary and verification

Verified installed baseline: deepagents 0.6.11, langchain 1.3.10, langgraph 1.2.6, pydantic 2.13.4. Current official backend documentation was consulted on 2026-10-01: https://docs.langchain.com/oss/python/deepagents/backends . Rolling documentation can describe later features; inspect the installed source before adopting one. No framework upgrade is required by this design.

Authority graph: native graph and virtual candidate -> application resolver with observed Evidence -> fenced artifacts and run delivery -> independent API reader and UI. The VFS, trace, prompt, and browser own no business authority.

Before any paid provider proof, exercise the installed DeepAgents harness, native write_file path, actual stream adapter, finalization, and API consumer using a deterministic model and source-tool fixture. A hand-created ExecutionOutcome alone is not native success evidence. Unit tests supplement that vertical path.

Required negative controls include invented or cross-run references, ambiguous excerpts, unknown question IDs, malformed/oversized JSON, no findings, missing candidate, stale finalization, tampered artifacts, unsafe source links, and a failed native tool call. Confirm unchanged legacy fallback and strict-citation behavior. Retain the accepted causal-order evaluation regression in this branch.

Outcome evidence reports requested questions, candidate-covered questions, unresolved questions, reference-binding failures, and explicit reader observations. Do not rename these as answer accuracy or production benefit. A small declared synthetic set should include complete, partial, contradictory, and insufficient-evidence cases, with separate expected outcomes and no automatic truth score.

## Delivery slices and acceptance

1. Repair empty Talent readiness and freeze strict candidate/canonical contracts plus an ADR for the new producer-to-delivery boundary.
2. Implement the native candidate producer, resolver, persistence, Markdown rendering, and API consumer; prove one full native provider-free success and negative cases.
3. Implement the live reader mode and inspectable excerpts; verify desktop and narrow layouts, then run the relevant full suite, evaluation regression, and important-feature documentation audit on the completed candidate.

Deliver an exact HEAD, checks and observed outcomes, a short runnable walkthrough and code navigation, documentation impact, and remaining gates. Update docs discovery to mark implemented versus planned surfaces. Keep provider-free, fixture, and real-provider evidence distinct. A new paid/provider run requires a separate concrete authorization and bounded proof plan.

## Ownership, Git, and authorization

Delivery owner: the dedicated project task. It derives the implementation plan with Superpowers writing-plans and chooses direct execution or subagent-driven development. Use Sol Max for delivery ownership, Sol High for behavioral implementation/review, and Luna Max only for bounded work it can reliably complete. Do not repeat design discovery for this approved direction; material goal, contract, authority, or scope changes return to the design owner.

Public main was verified at 1be794d31d8777fe9b389e14e60d623cd0386de4. The prepared isolated branch starts at cd7e2b07e64e3496b92ab9ed3e74e64b02b411f6 and carries the latest local workflow rules plus the accepted causal-order correction. This is an explicit local stack, not a claim that those changes are hosted. Preserve the earlier branches. The task has one mutable worktree owner.

Authorized now: local implementation, tests using existing environments, documentation, review, and semantic local commits. No push, PR, merge, release, deployment, new installation, or paid-provider call is authorized by this spec. Do not touch private knowledge stores or unrelated worktrees.

## Outside this batch

Talent crawling, arbitrary URL intake, new authentication or browser approval authority, additional orchestrators, enterprise tenancy, full-page source extraction, automatic truth verification, and a cross-project product merger. Native excerpt binding remains limited to Evidence snippets actually observed by this run.
