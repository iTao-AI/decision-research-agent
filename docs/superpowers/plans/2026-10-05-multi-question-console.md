# Multi-question Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Submit 1–5 explicit stable-ID questions through the normal structured
Live Backend creation path and read their observed dispositions and sources.

**Architecture:** Reuse the current create intent, hook, REST scope and findings
reader. Copy/freeze questions at the client boundary; keep draft editing in the
console and render service-owned dispositions. No backend behavior changes.

**Tech Stack:** Existing React 19, TypeScript 7, Vite 8, Vitest 4, Testing Library
and installed native fixture/browser methods; unchanged dependency locks.

**Spec:** `docs/superpowers/specs/2026-10-05-multi-question-console.md`

## Global Constraints

- 1–5 questions; nonblank text, at most 4096 Unicode code points each.
- IDs start with an ASCII letter, then at most 63 letters/digits/underscores/hyphens.
- Exact first-question query retains the 4096 UTF-8 byte console bound.
- Default `q1`, monotonically allocated draft IDs; generic scope remains `{}`.
- Complete payload copied/deeply frozen before transport; retries reuse key/payload.
- Server owns scope normalization, delivery, Evidence and review/verification.
- Static Demo and all native browser fixtures remain explicitly synthetic.
- Local-only delivery; no new locks/dependencies/tools or provider/remote actions.

## Review Focus

- Removing the first/middle row must not renumber surviving IDs or lose text.
- Mutable caller arrays, reordered rows and late edits must not alter retry bytes.
- Unicode text may pass code-point scope limits but exceed the query byte limit.
- Pending reconciliation must lock all scope controls and preserve original intent.
- Narrow/keyboard operation and observed question status must remain readable,
  including model-reported report-level contradictions without invented mapping.

---

### Task 1: Complete immutable structured create intent

**Files:** Create `frontend/src/researchScope.ts`.
Modify `frontend/src/apiClient.ts`, `frontend/src/useLiveRun.ts`.
Test `frontend/src/apiClient.test.ts`, `frontend/src/structuredLiveRun.test.tsx`.

**Interfaces:** `validateResearchQuestions(questions: readonly ResearchQuestion[])`
returns a typed validation result. `createRunIntent(query, randomUUID, profileId,
questions?)` retains old defaults. `startNewRun(query, questions?)` passes the
complete array to the client boundary.

- [ ] Write failing create-intent tests for exact five-question payload,
  defensive deep copy, reordered stable IDs, zero/six/duplicate/blank/invalid
  IDs, Unicode limits and unchanged generic/default-one payloads.
- [ ] Run `npm run test --prefix frontend -- src/apiClient.test.ts`; verify
  explicit scopes are currently ignored and invalid scopes are accepted.
- [ ] Implement typed validation and copied/frozen arrays before UUID creation.
- [ ] Add/run a failing hook test showing a two/five-question lost response
  currently collapses to q1; mutate the caller array then retry.
- [ ] Pass the optional questions through `startNewRun`; verify original complete
  bodies and keys match, observed reader remains same-run and errors remain bounded.
- [ ] Run the two test files, inspect diff, commit `feat: preserve full structured question intent`.

### Task 2: Stable question editor and observed dispositions

**Files:** Create `frontend/src/presentation/researchScopeEditor.tsx`.
Modify `frontend/src/App.tsx`, `frontend/src/i18n.ts`, `frontend/src/styles.css`,
`frontend/src/presentation/researchFindingsReader.tsx`.
Test `frontend/src/structuredApp.test.tsx`,
`frontend/src/presentation/researchFindingsReader.test.tsx`.

**Interfaces:** App owns ordered draft questions and the monotonic next ID.
Editor receives `questions`, `language`, `disabled`, `onAdd`, `onRemove`,
`onEdit`; it renders validation and restores focus after row changes.
Submission consumes Task 1's optional complete array; the reader consumes the
existing parsed report's dispositions rather than draft state.

- [ ] Write/run failing App tests for five-question submit, blank-row blocking,
  remove/edit/re-add IDs, first-row removal/query binding and locked recovery.
- [ ] Implement compact controls with old first-question label and single default;
  prevent count overflow/empty scope, retain IDs/text on profile/language changes.
- [ ] Write/run failing keyboard focus and English editor tests; implement add
  focus and removal focus without changing lifecycle ownership.
- [ ] Write/run a failing five-question reader test for explicit observed
  candidate/unresolved labels with corresponding source and unresolved reasons.
- [ ] Render service dispositions and retain report-level contradiction caveat;
  keep existing snippet inspection and same-run parser untouched.
- [ ] Run full frontend tests, inspect diff, commit `feat: add multi-question research scope editor`.

### Task 3: Integrated local acceptance and documentation

**Files:** Modify `DESIGN.md`, `docs/demo-console.md`,
`docs/operations/research-evidence-delivery.md` and affected README copy.
Retain raw fixture/browser receipts only in ignored task output.

**Interfaces:** Reuse existing guarded native fixture API with independently
declared one/five-question cases, actual UI POST, persisted findings/result
reader and known-run GET recovery. Use the current in-app browser method.

- [ ] Run frontend test/lint/build and focused existing API/scope/idempotency
  tests; inspect actual results and unchanged server/dependency files.
- [ ] Start task-owned local Vite/native fixture processes; submit one and five
  questions from actual browser controls; verify persisted scope, same-run
  dispositions/sources, Chinese/English, desktop/narrow layout and keyboard.
- [ ] Record observed browser limits and actual results in ignored closeout;
  stop task-owned processes and release temporary UI overrides.
- [ ] Update creation/editor/query/ID/recovery documentation and links; run
  frontend documentation checks and `git diff --check`.
- [ ] Commit `docs: document multi-question structured console`.
- [ ] Dispatch one independent whole-branch review; address Important/Critical
  findings with failing regressions and appropriate suite verification.
- [ ] Return exact base/HEAD, branch/worktree, diff, actual checks and remaining
  risks to the coordinating owner once. Do not start hosted delivery or C1.
