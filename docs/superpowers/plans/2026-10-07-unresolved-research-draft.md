# Unresolved Research Draft Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` for inline execution
> of this approved scope. Steps use checkbox syntax. Retain task-owned ignored
> evidence; do not delete prior workspaces or receipts.

**Goal:** Select unresolved questions from an accepted report, edit a separate
draft and explicitly create an independent structured research run.

**Architecture:** A context-keyed `ResearchFollowUp` owns browser-local selection,
draft and replacement confirmation. It wraps the existing reader, reuses the
scope editor/validation, and calls the existing create-intent path with an
explicit structured profile only on confirmation. Service authority and
request-version fencing remain unchanged.

**Tech Stack:** Existing React/TypeScript/Vitest and local Python public-service
test fixtures; no installation or dependency changes.

**Spec:** `docs/superpowers/specs/2026-10-07-unresolved-research-draft.md`

## Global Constraints

- Start at `fe4c9704149830d7fc1d620bf188000f65eacf00` in an owned isolated branch.
- Only accepted current `generic-evidence-report@1` unresolved questions.
- Preparation/editing/cancellation: zero POST and zero model execution.
- Existing scope: 1–5 nonblank questions, 4096 code points each; first query
  also at most 4096 UTF-8 bytes.
- New intent/key/thread/run; no old Evidence/findings/approval/lineage fields.
- No backend behavior, dependency/provider/Docker/paused-quality/release change.
- Local completion only until explicit hosted delivery authorization.

## Review Focus

- Structured attached report with ordinary generic form: the draft's explicit
  profile must not inherit generic or mutate the normal form.
- Editing then preparing again: keep edits until an explicit replace decision.
- Endpoint/profile/mode/source changes and late findings: no stale draft submit.
- Pending reconciliation/observation or known-run errors: retain existing locks
  and exact retry intent, with no extra creation.
- Successful health recheck and definite create rejection: preserve input scope,
  unlock only after health recovery, and hide prior reader until its source is
  observed again. Ambiguous recovery must remain locked to its frozen intent.
- Large/blank edits and overlapping editor IDs: clear feedback, unique labels,
  normal 1–5 creation/download and narrow keyboard use remain intact.

### Task 1: Context-bound independent draft and manual creation

**Files:**
- Create `frontend/src/presentation/researchFollowUp.tsx`.
- Modify `frontend/src/App.tsx`, `frontend/src/useLiveRun.ts`,
  `frontend/src/presentation/researchFindingsReader.tsx`,
  `frontend/src/presentation/researchScopeEditor.tsx`, `frontend/src/i18n.ts`,
  `frontend/src/styles.css`, `DESIGN.md`, `docs/demo-console.md`.
- Test `frontend/src/researchFollowUp.test.tsx` and
  `frontend/src/structuredLiveRun.test.tsx`.

**Interfaces:**
- Consumes `ResearchFindingsResponse`, current `LiveRunState`, existing
  `validateResearchQuestions`, `validateLiveDemoQuery` and `ResearchScopeEditor`.
- Produces `ResearchFollowUp({language, findings, disabled, onStart})`, where
  `onStart(questions: readonly ResearchQuestion[]): Promise<void>` is a manual
  creation callback.
- `startNewRun(query, questions?, profileId?: LiveResearchProfile)` defaults to
  the existing selected form profile; only draft confirmation supplies the
  structured override.
- Optional reader controls expose unresolved selection/prepare and a prepare
  button ref. Optional editor ID prefix/legend/question labels preserve defaults.

- [x] Write behavior tests before product code: selected unresolved text,
  independent ordinary edits, zero preparation POSTs, fresh explicit create
  scope/key/thread, duplicate clicks, explicit replacement/cancellation/focus,
  1–5/byte validation, context/stale/recovery/error gates and report download.
- [x] Verify RED: `npm run test -- src/researchFollowUp.test.tsx
  src/structuredLiveRun.test.tsx`; missing prepare/manual-draft behavior must fail.
- [x] Implement the smallest context-keyed component and optional interfaces.
  Context key includes endpoint/mode/form profile/source run/artifact identity;
  existing hook fencing rejects late responses. Keep old report until submission.
- [x] Verify GREEN with the same targeted command, then `npm run test`,
  `npm run lint`, `npm run build`, and `git diff --check`.
- [x] Update the guide/design with user actions and local/service evidence
  boundaries; commit intentional files as a semantic frontend change.

### Task 2: Actual service/persistence and browser acceptance

**Files:**
- Create `tests/integration/test_unresolved_research_draft.py` with a bounded
  deterministic service fixture reusable for the local browser session.
- Update this plan's checks and retain raw receipts/screenshots only in the
  task-owned ignored evidence directory.

**Interfaces:**
- Consumes Task 1's manual query/profile/scope request and new idempotency key.
- Uses actual public service routes and run/Evidence/artifact persistence,
  with an explicitly scripted producer and declared fixture source material.
- Produces assertions and receipts comparing original versus new run identities,
  exact accepted scope, artifact bytes/hashes, Evidence ownership and empty
  inherited approval/verification state.

- [x] Add/run public-service assertions for a mixed old report and edited new
  scope; new intent/key/run must differ, exact retry must reconcile its own new
  run, and original status/findings/result/Evidence remain byte-identical.
- [x] Run the new test plus the relevant existing create/findings contract tests
  using the already installed locked Python runtime with provider keys removed.
  Expected: all selected tests pass, without Docker or provider calls.
- [x] Run real Chinese/English browser flows at 1440px and 390px against the
  bounded local fixture. Record keyboard/focus, replacement/cancel, validation,
  actual request counts, created scope/new identity and reread old result.
- [ ] Review the whole branch in one fresh context, resolve material findings
  with targeted RED→GREEN evidence, and rerun affected checks only as needed.
- [ ] Verify exact HEAD/diff/clean state, unchanged dependency/backend inventory,
  retained evidence and primary; commit only intentional fixture/test/docs files.
- [ ] Return one local READY report with actual commands/counts, separate React,
  scripted-producer service and browser evidence, limitations and hosted candidate.
