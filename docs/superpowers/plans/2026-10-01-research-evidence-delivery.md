# Research Evidence Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver source-bound candidate findings and explicit unresolved questions through the native research runtime, persisted artifacts, API, and live reader; prevent empty Talent packets from becoming automatically ready.

**Architecture:** The existing DeepAgents generic graph writes a strict JSON candidate in its run-scoped VFS. A pure application resolver binds excerpts to frozen Evidence, then the existing fenced transaction persists canonical JSON, deterministic Markdown, and bounded diagnostics. Repository-backed readers and the console consume those artifacts without owning delivery or verification authority.

**Tech Stack:** Existing Python 3.11 environment, DeepAgents 0.6.11, LangChain 1.3.10, LangGraph 1.2.6, Pydantic 2.13.4, SQLite/FastAPI, React/TypeScript/Vite.

**Spec:** `docs/superpowers/specs/2026-10-01-research-evidence-delivery.md`

## Global Constraints

- Opt-in profile `generic-evidence-report@1`; preserve `generic` and `generic-strict-citation` contracts and defaults.
- Candidate path `/workspace/research-findings.json`; candidate maximum 256 KiB UTF-8 and 20 findings.
- Canonical artifact schema `dra.research-findings.v1`; persist `research-findings.json` and `research-report.md` only through the existing fenced finalization transaction.
- Frozen same-run Evidence is the only reference authority. Source binding is not source truth, entailment, semantic correctness, human verification, or approval.
- Reuse the generic harness policy, named synchronous researchers, native file tools, and stream adapter. Add no model post-processing, crawler, runtime Skill, Async Subagent, framework upgrade, dependency, or second orchestrator.
- Local implementation, verification, documentation, review, and semantic commits are authorized. No push, PR, merge, release, deployment, installation, or paid provider call is authorized.
- Preserve the local rules and accepted causal-order correction already present at starting HEAD `1716d3aff4b3602aacab0a1ef5a418d463f2e64a`.
- One mutable worktree owner; implementation tasks are serial. Only the assigned isolated checkout may be changed. Keep documentation public-neutral.

## Review Focus

- A Unicode excerpt, including repeated or overlapping occurrences, must produce exact code-point offsets or a bounded ambiguity failure (Task 2).
- A valid early candidate followed by a malformed/oversized replacement must block rather than retain stale successful output (Task 3).
- A rehashed canonical artifact with foreign Evidence IDs or altered snippet offsets must fail independent reading (Task 3).
- A changed question/mode during lost-response reconciliation must preserve the original keyed request and never attach old findings to a new run (Task 4).
- Long source excerpts and hostile text must stay readable at narrow width and render as text with existing safe-link rules (Task 4).

## File Responsibilities

- `agent/research_findings_contracts.py`: strict scope, candidate, canonical, and diagnostic contracts; no runtime imports.
- `api/research_findings.py`: pure parsing, binding, canonicalization, and deterministic artifact construction.
- `api/research_findings_service.py`: independent repository-backed read and bounded diagnostic projection.
- Existing `agent/deepagents_harness.py`, `agent/run_result.py`, and `api/research_execution_service.py`: native prompt envelope and VFS candidate capture only.
- Existing `agent/profile_registry.py`, `api/server.py`, `api/run_repository.py`, and `api/run_result_service.py`: opt-in selection, validation, fenced delivery, and snapshot/read integration.
- `frontend/src/researchFindings.ts` and `frontend/src/presentation/researchFindingsReader.tsx`: strict selected-field consumer and readable source-bound findings.
- Existing frontend client, live hook, app, copy, and styles: explicit mode selection, keyed create/observe flow, and live rendering.
- `scripts/research_evidence_delivery_proof.py` plus synthetic fixtures: provider-free native walkthrough and declared outcomes, without truth scores.

### Task 1: Repair empty Talent readiness and freeze strict contracts

**Files:**
- Modify: `api/review_service.py`, `tests/unit/test_talent_artifacts.py`, `tests/integration/test_run_api.py` (or the existing finalization-focused integration module).
- Create: `agent/research_findings_contracts.py`, `tests/unit/test_research_findings_contracts.py`, `docs/decisions/research-findings-delivery-authority.md`.
- Modify: the Talent readiness explanation in `docs/reference/state-machines.md`.

**Interfaces:**
- `ResearchQuestion`: `question_id` ASCII identifier `[A-Za-z][A-Za-z0-9_-]{0,63}`, `text` 1–4096 characters after trimming.
- `ResearchFindingsScope`: exactly `questions`, 1–5 unique `ResearchQuestion` items.
- `validate_research_findings_scope(scope: dict, *, query: str) -> ResearchFindingsScope`: omitted `questions` uses query as `q1`; an explicitly empty list is invalid; forbid unknown fields.
- `CandidateReference`: exactly `source_url` (1–2048 characters) and `excerpt` (1–1000 characters, preserved verbatim, nonblank).
- `CandidateFinding`: exactly `question_id`, `statement` (1–2000 characters), and `references` (1–10 items).
- `QuestionDisposition`: exactly `question_id`, `status` (`candidate_findings` or `unresolved`), and optional `reason` (1–2000 characters); unresolved requires a nonblank reason and candidate_findings omits reason.
- `ResearchFindingsCandidate`: `schema_version=dra.research-findings-candidate.v1`, 0–20 findings, 1–5 unique dispositions, `reported_contradictions` and `limitations` (each 0–20 strings of 1–2000 characters). No unknown fields or authoritative model-supplied values.
- `BoundSourceReference`: application-owned Evidence ID/fingerprint, publishable source URL/identity, frozen snippet, exact excerpt, code-point `excerpt_start`/`excerpt_end`.
- `BoundFinding`: application-generated stable `finding_id` (`f1`, `f2`, …), question ID, statement, references.
- `ResearchFindingsReport`: `schema_version=dra.research-findings.v1`, run/profile/version identity, accepted questions, bound findings, dispositions, reported contradictions, limitations. No automatic verification/approval or confidence claims.
- `ResearchFindingsDiagnostics`: `schema_version=dra.research-findings-diagnostics.v1`, run ID, at most 20 closed issue codes, and requested/covered/unresolved question counts plus reference-binding failure count. Use fixed diagnostic codes; no raw exception/model text.

- [ ] **Step 1:** Add policy and actual API finalization regressions asserting an empty packet becomes `completed/review_required` with trigger `empty_research_output`; assert findings-only nonempty output remains eligible under existing rules.
- [ ] **Step 2:** Run those tests and record the expected pre-fix failure; implement the smallest `build_review_bundle` repair without requiring all packet lists to be nonempty.
- [ ] **Step 3:** Add strict-contract tests for field bounds, unknown fields, type coercion, duplicate/unknown scope IDs, explicit empty questions, verbatim excerpts, and model-invented authority fields. Run RED before implementing the models/helper.
- [ ] **Step 4:** Implement frozen strict Pydantic contracts. Candidate disposition/finding consistency against accepted scope is validated by Task 2; contract-level validators enforce local uniqueness and shape.
- [ ] **Step 5:** Write the ADR with application DB authority, frozen-ledger resolution, code-point offsets, existing transaction fencing, source-binding non-claims, native framework reuse rationale, and no paid proof claim. Update Talent readiness documentation.
- [ ] **Step 6:** Run focused contract/Talent/finalization tests and `git diff --check`; make semantic commit(s). Report exact commands and RED/GREEN evidence.

### Task 2: Resolve frozen excerpts and render deterministic artifacts

**Files:**
- Create: `api/research_findings.py`, `tests/unit/test_research_findings.py`.
- Consume: `agent/research_findings_contracts.py`, `agent/research.py`, `agent/source_url_policy.py`.

**Interfaces:**
- `ResearchFindingsBuildResult`: delivery status (`ready` or `blocked`), canonical report or `None`, artifacts, updated Evidence entries, and typed diagnostics.
- `build_research_findings_artifacts(*, run_id: str, scope: ResearchFindingsScope, candidate_content: str | None, evidence_entries: list[EvidenceEntry]) -> ResearchFindingsBuildResult`.
- `render_research_findings_markdown(report: ResearchFindingsReport) -> str`.
- `validate_research_findings_report(report: ResearchFindingsReport, *, run_id: str, scope: ResearchFindingsScope, evidence_rows: list[dict]) -> bool`: independent same-run identity/excerpt checks, used by Task 3.
- Canonical JSON uses UTF-8, sorted keys, compact separators, no volatile timestamps; each artifact hash is SHA-256 of its actual bytes, as generic artifacts do.
- Artifact IDs/kinds: `research-findings.json` / `research_findings_json`, `research-report.md` / `research_findings_markdown`, `research-findings-diagnostics.json` / `research_findings_diagnostics_json`.
- Ready requires at least one finding and every reference uniquely resolved. Any malformed, missing, unmatched, ambiguous, or wholly empty candidate blocks the entire package; persist only bounded diagnostics for blocked output.
- Codes include `candidate_missing`, `candidate_too_large`, `candidate_invalid`, `question_disposition_invalid`, `reference_not_found`, `reference_ambiguous`, `source_url_unsafe`, and `empty_research_output`; application may add a closed code for an actually distinct in-scope failure and document it.

- [ ] **Step 1:** Write RED tests for complete, partial, contradictory, and all-unresolved candidates, deterministic bytes/hashes/Markdown, Unicode exact offsets, repeated/overlapping excerpts, multiple matching entries, unknown/missing/duplicate question dispositions, invented URLs, unsafe URLs, authority injection, malformed/duplicate-key/oversized JSON, and wrong scope/foreign Evidence IDs on independent validation.
- [ ] **Step 2:** Implement strict JSON parsing with a 256 KiB byte check before parsing; reject duplicate keys and non-JSON numeric constants. Validate every accepted question is represented exactly once and covered/unresolved status matches findings.
- [ ] **Step 3:** Resolve source identities with existing `source_identity_for`, require publishability for both candidate and stored URL, count every contiguous excerpt occurrence (including overlaps), and reject more than one matching ledger entry. Bind only the provided frozen ledger; no network or model calls.
- [ ] **Step 4:** Generate stable finding IDs, canonical JSON and readable Markdown naming candidate status, quoted observed snippets, unresolved reasons, limitations, and model-reported contradictions. Retain human verification authority; mark bound entries cited without modifying their verification status.
- [ ] **Step 5:** Implement independent validation against persisted Evidence rows, expected scope, profile/version/run identity, exact snippet/offset/fingerprint, and uniqueness. Reject unknown or foreign rows and malformed bounds.
- [ ] **Step 6:** Run focused contract/resolver/source-policy checks, `git diff --check`, and semantic commit(s).

### Task 3: Connect native VFS producer to fenced persistence and API readers

**Files:**
- Modify: `agent/profile_registry.py`, `agent/deepagents_harness.py`, `agent/run_result.py`, `api/research_execution_service.py`, `api/server.py`, `api/run_repository.py`, `api/run_result_service.py`.
- Create: `api/research_findings_service.py`, `tests/integration/test_research_findings_api.py`, `tests/integration/test_research_findings_native.py`.
- Modify: focused profile/harness/stream/lifecycle tests and `docs/reference/api-contract.md`, `docs/reference/data-models.md`, `docs/reference/state-machines.md`, `docs/AGENT_INTEGRATION.md`.

**Interfaces:**
- Register `generic-evidence-report` version `1`, classified as generic family with the unchanged generic policy. Compile/reuse the same generic graph; only the new profile's request envelope adds accepted questions and strict candidate instructions.
- Add `findings_candidate: ReportCandidate | None` to accumulator/outcome. Capture only `/workspace/research-findings.json` from root native VFS file updates. A later invalid replacement clears/invalidates the earlier candidate rather than retaining stale bytes; apply byte bounds before conversion/parsing.
- New profile scope is validated/normalized before `create_run` and keyed creation. Use bounded `invalid_research_scope` without raw validator input/exception text.
- Finalization calls Task 2 once with frozen outcome Evidence, persists all returned artifacts/status through the existing owner/state/segment fence, and never builds a generic Markdown fallback for this profile.
- Delivery snapshot includes scope and same-run Evidence rows needed for independent binding validation in one read transaction.
- `resolve_run_findings(*, run_id: str, db_path: str | None = None)`: use existing result errors and repository authority; response `{run_id, execution_status, delivery_status, artifact, report}` with JSON artifact metadata/content/hash and typed canonical report.
- Result reader validates matching canonical JSON and deterministic Markdown for the new profile. GET `/api/runs/{run_id}/findings` requires terminal ready delivery and correct profile/version, hashes, schema, Evidence bindings, and current artifact identity.
- Expose optional bounded `findings_issues` and `findings_outcome` only for the new profile in GET run projection, derived from the committed diagnostic artifact after strict identity/hash validation. Keep legacy projections unchanged. Corrupt diagnostics fail closed without exposing internal text.

- [ ] **Step 1:** Add RED tests for profile manifest/harness selection, pre-dispatch scope validation and keyed replay, native VFS candidate capture/replacement, completed-ready success, completed-blocked missing/invalid/empty candidate, and legacy generic fallback/strict-citation behavior.
- [ ] **Step 2:** Implement opt-in registry, request envelope, and bounded candidate capture with existing native file tools/stream adapter. Do not parse findings out of arbitrary model Markdown or nested source text.
- [ ] **Step 3:** Wire Task 2 into application finalization, retain timeout/cancellation Evidence behavior, and add persisted bounded reason projection. Update snapshot readers and independent JSON/Markdown resolution.
- [ ] **Step 4:** Add endpoint negatives: missing/nonterminal/failed/review-required/blocked/wrong-profile run, missing JSON, mismatched hash, recomputed hash with foreign references/offsets, stale finalization, unsafe links, and mismatched Markdown. Use the current repository fence and real finalization path.
- [ ] **Step 5:** Prove a vertical provider-free success with the installed `build_generic_harness`, deterministic tool-calling `BaseChatModel`, native named `network_search` and fixture `internet_search`, native `write_file`, actual stream adapter, `ResearchExecutionService`, API dispatch/finalization, and independent GET findings/result. Include a native file-tool failure and no-candidate control; no hand-created outcome can be the sole proof.
- [ ] **Step 6:** Update public API/data/state/integration contracts with bounds, errors, diagnostics, hashes/offset units, profile compatibility, and non-claims. Run focused native/API/lifecycle/profile/strict-citation tests, `git diff --check`, and semantic commit(s).

### Task 4: Add explicit live structured research and inspectable snippets

**Files:**
- Create: `frontend/src/researchFindings.ts`, `frontend/src/researchFindings.test.ts`, `frontend/src/presentation/researchFindingsReader.tsx`, reader tests.
- Modify: `frontend/src/apiClient.ts`, `frontend/src/apiClient.test.ts`, `frontend/src/useLiveRun.ts`, `frontend/src/useLiveRun.test.tsx`, `frontend/src/runProjection.ts`, `frontend/src/App.tsx`, `frontend/src/App.test.tsx`, `frontend/src/styles.css` (or actual stylesheet), `frontend/src/copy.ts` (or actual copy module), `DESIGN.md`, `docs/demo-console.md`.

**Interfaces:**
- Extend the existing immutable keyed create intent with an explicit profile/scope selection; generic remains the default. Structured mode submits one question (`q1`, current query); API retains support for 1–5 questions. Do not invent client questions for attached runs.
- `getFindings(baseUrl: string, runId: string, signal?: AbortSignal)` parses selected canonical fields and requires response/run/profile identity, safe field bounds, and coherent excerpt offsets.
- Fetch findings only after the observed new-profile run is ready; old profiles continue to use canonical Markdown. Any findings read failure clears findings/result presentation and surfaces a bounded client error.
- Live reader renders accepted questions, source-bound candidate findings, exact excerpt and stored snippet inspection, source links, unresolved questions, reported contradictions, and limitations as text; apply existing safe-link policy.
- Keyed retry preserves the original query/profile/scope; switching mode/base URL invalidates all run/findings state; stale responses never win.

- [ ] **Step 1:** Add RED consumer/hook/app tests for explicit mode selection, immutable intent/retry, observed-profile fetch gating, attached-run identity, request cancellation/stale findings, malformed/unavailable findings, blocked reason display, and unchanged generic/static paths.
- [ ] **Step 2:** Implement strict selected-field parsing, client read, keyed intent extension, and hook findings state. Keep backend state authoritative; the frontend never infers readiness from findings presence.
- [ ] **Step 3:** Add structured live reader and clear Chinese/English candidate/source-binding wording. Render malicious HTML/Markdown as text; unsafe links have no actionable href. Retain the canonical Markdown reader/download for ready delivery.
- [ ] **Step 4:** Test long Unicode snippets and mobile/keyboard source inspection in component tests. Update design/operator docs for implemented live surfaces and boundaries.
- [ ] **Step 5:** Reuse existing frontend dependencies without installation. Run `npm run test`, `npm run lint`, `npm run build`, and `git diff --check`; make semantic commit(s). Parent will inspect actual desktop/narrow rendered pages after Task 5's proof server is available.

### Task 5: Publish local proof assets and close documentation discovery

**Files:**
- Create: `scripts/research_evidence_delivery_proof.py`, declared synthetic fixture/expected-outcome files under `tests/fixtures/research-evidence-delivery/`, proof tests, `docs/evidence/research-evidence-delivery-v1.json`, `docs/evidence/research-evidence-delivery-v1.md`, `docs/operations/research-evidence-delivery.md`.
- Modify: `README.md`, `docs/README.md` (or actual discovery index), relevant important-feature/navigation documentation tests.
- Reuse: Task 3's deterministic native fixture/model helper; extract it to a focused test/proof helper only if necessary, without duplicating the vertical implementation.

**Interfaces:**
- Runnable provider-free `python scripts/research_evidence_delivery_proof.py check`; optional `serve` supports a bounded localhost temporary API with native deterministic producer for parent browser acceptance. Disable tracing/dotenv/providers and remove task-owned runtime resources on exit.
- Evidence contains declared complete/partial/contradictory/insufficient-evidence cases, separate expected outcomes, requested/covered/unresolved counts, binding failures, runtime/consumer checkpoints, and explicit reader observations. Keep fixtures, native provider-free proof, and paid/real-provider proof distinct.
- Walkthrough names commands and code navigation, actual implemented/planned surfaces, limitations, and a separate concrete paid-proof gate (target profile/question set, provider/model, call/token/time/spend bound, source tools/domains, authorization, retained receipts). It performs no paid calls.

- [ ] **Step 1:** Write proof contract tests and native fixture cases with independently declared expected outcomes. Run RED before script/fixtures implementation.
- [ ] **Step 2:** Implement the runnable native provider-free proof and localhost serving path using the real API producer/consumer, not manually fabricated completed runs. Emit public-neutral bounded evidence without host paths/secrets/raw exceptions.
- [ ] **Step 3:** Generate committed JSON/Markdown proof evidence from the actual check and update docs discovery, walkthrough, source-snippet limits, reader labels, and paid-proof gates. Historical evidence keeps its original scope.
- [ ] **Step 4:** Run proof/documentation-focused checks and `git diff --check`; make semantic commit(s). Parent performs full relevant suite, evaluation gates, final review, and browser acceptance on the integrated HEAD.

## Integrated Acceptance (delivery owner)

- [ ] Read task review reports and resolve all blocking findings before dependent tasks.
- [ ] Run backend non-Docker suite, dependency/import compatibility, deterministic evaluation v1/v2 (including causal-order regression), evidence-loop, run creation/dispatch/failure/recovery/security/bounded-producer checks named in current CI.
- [ ] Run frontend test/lint/build once on the integrated candidate; inspect desktop and narrow live structured pages with native provider-free API and actual browser tools.
- [ ] Run Docker gates only when applicable to the changed contract and resources are available; identify any skipped required hosted gate precisely. Do not claim unrun Docker/HITL/paid/hosted checks.
- [ ] Audit important-feature docs against implemented producer, delivery, API, reader, compatibility, and evidence limits; reconcile evidence with observations.
- [ ] Obtain whole-branch Sol review, fix verified issues, rerun affected checks, verify `git diff --check`, clean Git state, exact HEAD, and unchanged protected checkouts.
- [ ] Return `READY` for local acceptance or exact missing gate(s), branch/worktree/HEAD, diff, actual checks/outcomes, walkthrough, documentation impact, and remaining remote/paid gates. Preserve the clean worktree; no remote action.
