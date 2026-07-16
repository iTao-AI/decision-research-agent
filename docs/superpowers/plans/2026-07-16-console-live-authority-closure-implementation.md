# Agent Research Operations Console Live Authority Closure v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the first-party Console truthfully render live service-owned run
state and safely reconcile one ambiguous keyed create within the current page
session without changing backend authority.

**Architecture:** Preserve the existing loopback-only Fetch client and add an
immutable browser create intent, a strict run/result parser, and a pure
Static-or-Live `ConsoleProjection`. The live hook owns reconciliation, polling,
GET-only resumption, deadlines, and stale-request fencing; React screens render
only the supplied projection. Implementation runs in parallel with Durable Run
Failure Cause v1 but final landing waits for that branch to merge and then
rebases onto its additive status contract.

**Tech Stack:** React 19, TypeScript, browser Fetch, AbortController and Web
Crypto, Vitest, Testing Library, Vite, ESLint, npm audit, Python documentation
contract tests.

## Global Constraints

- Implement only
  `docs/superpowers/specs/2026-07-16-console-live-authority-closure-design.md`.
- Create one fresh isolated worktree and branch
  `codex/console-live-authority-closure` from current `origin/main`. Do not use,
  merge, or cherry-pick any stale unrelated feature worktree.
- Before editing, inspect `origin/main`, all worktrees, current failure-cause
  branch ownership, and the affected frontend files. Stop if another active
  lane modifies frontend source or the approved status addition is no longer
  additive.
- Use TDD for every behavior change: focused RED, minimal implementation,
  focused GREEN, then broader verification.
- Keep Static Demo as the default and preserve all existing deterministic
  snapshot behavior.
- Live mode must never render a run-specific value from `demoRun`.
- Every Console create uses one immutable high-entropy `RunCreateIntent`; the
  raw key appears only in `Idempotency-Key`.
- An ambiguous create may be retried only with the same intent. Once `run_id`
  is known, every recovery path is GET-only.
- Canonical artifact content comes only from
  `GET /api/runs/{run_id}/result`.
- Preserve exact loopback-only URL and health-identity validation. Do not add
  credentials, browser storage, auth changes, public hosting, LAN support, or
  arbitrary provider/query input.
- Do not add WebSocket, SSE, telemetry, token/cost, review/verification writes,
  cancellation, retry-run, upload, chat, or Markdown fact parsing.
- Do not modify `api/**`, migrations, backend integration tests, failure-cause
  proof/evidence, dependencies, frontend package metadata, version, release
  notes for historical releases, or provider configuration.
- During parallel implementation do not modify `.github/workflows/ci.yml`,
  `README.md`, `README_CN.md`, `CHANGELOG.md`, shared docs indexes, or
  `tests/unit/test_documentation_contracts.py`. Those shared files are owned by
  the failure-cause integration lane until it lands.
- Keep `VERSION` at `0.1.3`. Do not push, create a PR, merge, tag, release,
  deploy, or remove the worktree during implementation.
- Public text must remain credential-free, provider-neutral, consumer-neutral,
  and free of private paths or development-process motivation.

---

## File And Responsibility Map

| File | Responsibility |
|---|---|
| `frontend/src/apiClient.ts` | Loopback transport, immutable create intent, keyed create, structured public errors |
| `frontend/src/apiClient.test.ts` | Header/body identity, replay metadata, ambiguous/stable error behavior |
| `frontend/src/runProjection.ts` | Strict selected-field parsing for status, Evidence, review/verification presence, failure cause, and canonical result |
| `frontend/src/runProjection.test.ts` | Valid/malformed projection matrix and unknown-field isolation |
| `frontend/src/consoleProjection.ts` | Pure mutually exclusive Static/Live presentation model and observation states |
| `frontend/src/consoleProjection.test.ts` | Static/live separation and screen-level projection semantics |
| `frontend/src/useLiveRun.ts` | Create-intent lifetime, reconciliation, polling, GET-only resume, deadlines, stale-request fences |
| `frontend/src/useLiveRun.test.tsx` | Hook state-machine and request-count/order contracts |
| `frontend/src/App.tsx` | Render six screens from `ConsoleProjection` and expose bounded recovery actions |
| `frontend/src/App.test.tsx` | End-user truth, terminal dispositions, language, accessibility, and static reset |
| `frontend/src/i18n.ts` | Chinese/English labels for absence, reconciliation, resume, and terminal states |
| `frontend/src/styles.css` | Existing-design-compatible observation and recovery styling only |
| `DESIGN.md` | Console component/data authority boundary |
| `docs/demo-console.md` | Operator workflow, reconciliation, resume, failure-cause compatibility, nonclaims |
| `tests/unit/test_demo_console_contracts.py` | Dedicated parallel-safe public documentation contract |
| shared README/CHANGELOG/docs indexes | Post-failure-merge discovery only, owned by final integration task |

## Execution Ordering And Parallelism

1. Tasks 1 and 2 run serially because both define the transport/projection
   boundary used by later work.
2. After Task 2 is integrated, Tasks 3 and 4 may run in parallel from the same
   HEAD:
   - one medium worker owns only `consoleProjection.ts` and its test;
   - one medium worker owns only `useLiveRun.ts` and its test.
3. The Ultra integration owner reviews and cherry-picks those commits, runs the
   combined frontend tests, then performs Task 5.
4. Task 6 completes parallel-safe documentation and near-field verification.
5. Task 7 is a hard integration gate. If Durable Run Failure Cause v1 has not
   merged into `origin/main`, stop with a clean local branch/worktree. Do not
   edit shared discovery files or push.
6. After the failure-cause merge, rebase once, inspect the final status
   projection, complete Task 7, and hand off the clean branch for authoritative
   review.

Workers never share an index or commit concurrently in one worktree. Every
worker edits only its assigned files and returns one clean commit for ordered
integration.

---

### Task 1: Add Immutable Keyed Create Contracts

**Files:**

- Modify: `frontend/src/apiClient.ts`
- Create: `frontend/src/apiClient.test.ts`

**Interfaces:**

- Produces: `RunCreateIntent`, `createRunIntent(randomUUID?)`, keyed
  `startRun(baseUrl, intent, signal?)`, `isAmbiguousCreateError(error)`.
- Preserves: `ClientError`, `ClientRequestError`, `getHealth`, loopback URL
  validation, structured HTTP errors.

- [ ] **Step 1: Write failing create-intent and request tests**

Add deterministic tests with a fixed UUID:

```ts
const FIXED_UUID = "11111111-2222-4333-8444-555555555555";

it("creates one immutable bounded browser intent", () => {
  const intent = createRunIntent(() => FIXED_UUID);
  expect(intent).toEqual({
    idempotencyKey: `run-create-console-${FIXED_UUID}`,
    payload: {
      query: "Generate a short evidence-bound result for the Agent Research Operations Console.",
      thread_id: `demo-console-${FIXED_UUID}`,
      profile_id: "generic",
      scope: {}
    }
  });
  expect(Object.isFrozen(intent)).toBe(true);
  expect(Object.isFrozen(intent.payload)).toBe(true);
});
```

Mock fetch and require:

```ts
expect(request.headers).toContainEqual(["idempotency-key", intent.idempotencyKey]);
expect(JSON.parse(String(request.body))).toEqual(intent.payload);
expect(String(request.body)).not.toContain(intent.idempotencyKey);
```

Also require keyed responses to contain a boolean `idempotent_replay`; missing,
string, numeric, or null values fail with `invalid_response`.

- [ ] **Step 2: Run Task 1 RED**

```bash
cd frontend
npm run test -- src/apiClient.test.ts
```

Expected: collection/type failure because `RunCreateIntent` and
`createRunIntent` do not exist and `startRun` still owns request generation.

- [ ] **Step 3: Implement the immutable intent and keyed create**

Use these exact public interfaces:

```ts
export const LIVE_DEMO_QUERY =
  "Generate a short evidence-bound result for the Agent Research Operations Console.";

export type RunCreateIntent = Readonly<{
  idempotencyKey: string;
  payload: Readonly<{
    query: string;
    thread_id: string;
    profile_id: "generic";
    scope: Readonly<Record<string, never>>;
  }>;
}>;

export type RunCreationResponse = {
  run_id: string;
  segment_id: string;
  status: string;
  thread_id: string;
  idempotent_replay: boolean;
};

export function createRunIntent(
  randomUUID: () => string = () => crypto.randomUUID()
): RunCreateIntent {
  const uuid = randomUUID();
  return Object.freeze({
    idempotencyKey: `run-create-console-${uuid}`,
    payload: Object.freeze({
      query: LIVE_DEMO_QUERY,
      thread_id: `demo-console-${uuid}`,
      profile_id: "generic" as const,
      scope: Object.freeze({})
    })
  });
}
```

Change `startRun` to accept the intent and send:

```ts
headers: {
  "Content-Type": "application/json",
  "Idempotency-Key": intent.idempotencyKey
},
body: JSON.stringify(intent.payload)
```

Validate the four existing identity fields plus boolean
`idempotent_replay`. Do not return, log, or place the key in a public error.

`isAmbiguousCreateError` returns true only for a fetch-level
`connection_failed` or an `AbortError` before acknowledgement. Structured HTTP
errors, invalid responses, and idempotency conflicts return false.

- [ ] **Step 4: Run Task 1 GREEN and regression tests**

```bash
cd frontend
npm run test -- src/apiClient.test.ts src/App.test.tsx
npm run lint
```

Expected: new client tests pass. Existing App tests may require only the
mechanical test mock update for additive `idempotent_replay`; do not change UI
behavior yet.

- [ ] **Step 5: Commit Task 1**

```bash
git add frontend/src/apiClient.ts frontend/src/apiClient.test.ts \
  frontend/src/App.test.tsx
git commit -m "feat(console): add keyed live run intent"
```

---

### Task 2: Parse Strict Live Run And Result Projections

**Files:**

- Create: `frontend/src/runProjection.ts`
- Create: `frontend/src/runProjection.test.ts`
- Modify: `frontend/src/apiClient.ts`

**Interfaces:**

- Consumes: existing status and result endpoint JSON.
- Produces: `RunProjection`, `RunResultResponse`, `FailureCauseAvailability`,
  `parseRunProjection(value)`, `parseRunResult(value)`. `getRun` and
  `getResult` return only these parsed values.

- [ ] **Step 1: Write strict projection RED tests**

Define one complete current response fixture containing:

```ts
const STATUS = {
  run_id: "run_live_001",
  thread_id: "demo-console-thread",
  profile_id: "generic",
  execution_status: "completed",
  review_status: "not_required",
  delivery_status: "ready",
  state_version: 2,
  segments: [{
    segment_id: "run_live_001_seg_000",
    kind: "initial",
    sequence: 0,
    attempt: 1,
    status: "completed"
  }],
  evidence: [{
    evidence_id: "ev_001",
    source_url: "https://example.com/source",
    source_identity: "https://example.com/source",
    evidence_fingerprint: "sha256:abc",
    citation_status: "cited",
    verification_status: "unverified",
    snippet: "must not enter the selected projection"
  }],
  review_workflow: null,
  review_decision: null,
  review_resolution: null,
  failure_cause: null,
  unknown_private_field: "ignored"
};
```

Require exact selected output and assert `snippet`, query, and unknown fields
are absent. Add one mutation per required scalar, segment field, Evidence field,
counts map, canonical artifact field, and observed/not-observed failure-cause
field. Each mutation must throw a bounded `invalid_response` error.

Cover all failure-cause states:

```text
property absent -> unsupported
null -> not_applicable
not_observed object -> not_observed
observed object -> observed bounded value
malformed object -> invalid_response
```

- [ ] **Step 2: Run Task 2 RED**

```bash
cd frontend
npm run test -- src/runProjection.test.ts
```

Expected: collection fails because `runProjection.ts` does not exist.

- [ ] **Step 3: Implement selected-field types and parsers**

Use focused immutable types:

```ts
export type FailureCauseAvailability =
  | { kind: "unsupported" }
  | { kind: "not_applicable" }
  | { kind: "not_observed"; schema_version: "dra.run-failure-cause.v1" }
  | {
      kind: "observed";
      schema_version: "dra.run-failure-cause.v1";
      phase: string;
      code: string;
      recorded_at: string;
    };

export type RunProjection = Readonly<{
  run_id: string;
  thread_id: string;
  profile_id: string;
  execution_status: string;
  review_status: string;
  delivery_status: string;
  state_version: number;
  segments: readonly RunSegmentProjection[];
  evidence: readonly RunEvidenceProjection[];
  review: ReviewPresenceProjection;
  verification?: VerificationSummaryProjection;
  currentPublication?: CurrentPublicationProjection;
  currentArtifacts: readonly ArtifactMetadataProjection[];
  failureCause: FailureCauseAvailability;
}>;
```

Validate the exact v1 phase/code matrix rather than accepting arbitrary
strings:

```ts
const FAILURE_CAUSE_CODES = {
  dispatch: new Set([
    "run_dispatch_schedule_failed",
    "run_dispatch_start_failed",
    "run_dispatch_start_timeout",
    "run_dispatch_lease_expired"
  ]),
  execution: new Set([
    "call_budget_exceeded",
    "recursion_limit_exceeded",
    "invalid_research_packet",
    "missing_research_packet",
    "run_timeout",
    "cancelled",
    "execution_error"
  ]),
  finalization: new Set([
    "run_timeout",
    "cancelled",
    "run_finalization_failed"
  ])
} as const;
```

Unknown phases, unknown codes, and cross-phase code reuse fail with
`invalid_response`.

Keep helpers local and explicit: `expectRecord`, `expectString`,
`expectInteger`, `expectNullableString`, `expectArray`, and a counts-map parser
that rejects non-integer or negative counts. Freeze returned arrays/objects.
Ignore unselected upstream fields; never pass raw response objects to React.

Move `RunResultResponse` to this module and require `run_id`, execution status,
delivery status, and a selected canonical artifact object. Artifact content is
accepted only as a string and remains subject to the server's canonical result
contract.

Re-export `RunProjection` and `RunResultResponse` from `apiClient.ts` during
this task so existing imports remain source-compatible until Task 5 completes
the component refactor.

Change `getRun` and `getResult` to call the new parsers. Convert parser failures
to the existing bounded `invalid_response` client error.

- [ ] **Step 4: Run Task 2 GREEN**

```bash
cd frontend
npm run test -- src/runProjection.test.ts src/apiClient.test.ts src/App.test.tsx
npm run lint
```

Expected: all selected-field and existing live-path tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add frontend/src/runProjection.ts frontend/src/runProjection.test.ts \
  frontend/src/apiClient.ts frontend/src/apiClient.test.ts \
  frontend/src/App.test.tsx
git commit -m "feat(console): validate live run projections"
```

---

### Task 3: Build A Mutually Exclusive Console Projection

**Files:**

- Create: `frontend/src/consoleProjection.ts`
- Create: `frontend/src/consoleProjection.test.ts`

**Interfaces:**

- Consumes: `demoRun`, `HealthResponse`, `RunCreationResponse`,
  `RunProjection`, `RunResultResponse`.
- Produces: `Observation<T>`, `ConsoleProjection`,
  `buildStaticConsoleProjection()`, and
  `buildLiveConsoleProjection(input)`.

- [ ] **Step 1: Write static/live separation RED tests**

Require the exact observation union:

```ts
export type Observation<T> =
  | { kind: "observed"; value: T }
  | { kind: "not_observed" }
  | { kind: "not_applicable" }
  | { kind: "unsupported" };
```

Tests must prove:

- static projection contains the existing demo run, Evidence, review,
  verification, artifact, lifecycle, and result;
- an empty live projection contains none of those identifiers;
- a live generic run uses actual run/segment/Evidence/status values;
- an observed empty Evidence list differs from Evidence not yet observed;
- result content enters only through the supplied `RunResultResponse`;
- absence/null/not-observed/unsupported failure states stay distinct;
- JSON serialization of a live projection contains none of
  `run_demo_talent_2026_06_29`, `ev_001`,
  `decision_demo_approved_001`, or `decision-brief.md` from `demoRun`.

- [ ] **Step 2: Run Task 3 RED**

```bash
cd frontend
npm run test -- src/consoleProjection.test.ts
```

Expected: collection fails because the projection module does not exist.

- [ ] **Step 3: Implement pure screen projections**

Define a single root discriminator:

```ts
export type ConsoleProjection = Readonly<{
  source: "static" | "live";
  summary: SummaryProjection;
  command: CommandProjection;
  lifecycle: LifecycleProjection;
  evidence: Observation<readonly EvidenceView[]>;
  review: ReviewView;
  verification: Observation<VerificationView>;
  result: Observation<ResultView>;
  architecture: ArchitectureReferenceProjection;
}>;
```

`buildStaticConsoleProjection` is the only function allowed to import
`demoRun`. `buildLiveConsoleProjection` must not import it and accepts only
explicit live input. Architecture reference labels may use
`architectureNodes`, but run-specific fields may not.

Use `Object.freeze` for the returned root and nested collections. Keep the
projection presentation-only: it does not choose backend state, retry, or
canonical artifacts.

- [ ] **Step 4: Run Task 3 GREEN**

```bash
cd frontend
npm run test -- src/consoleProjection.test.ts src/runProjection.test.ts
npm run lint
```

Expected: all projection tests pass without React rendering.

- [ ] **Step 5: Commit Task 3**

```bash
git add frontend/src/consoleProjection.ts \
  frontend/src/consoleProjection.test.ts
git commit -m "feat(console): separate static and live projections"
```

---

### Task 4: Add Create Reconciliation And GET-Only Resume

**Files:**

- Modify: `frontend/src/useLiveRun.ts`
- Create: `frontend/src/useLiveRun.test.tsx`

**Interfaces:**

- Consumes: Task 1 create intent/client and Task 2 status/result client.
- Produces: `startNewRun`, `retryCreate`, `discardPendingIntent`,
  `resumeObservation`, existing health/mode/base URL actions, and expanded
  `LiveRunState`.

- [ ] **Step 1: Write hook state-machine RED tests**

Use `renderHook` with mocked fetch and deterministic UUID injection through a
new `LiveRunOptions.randomUUID` seam. Cover:

```text
ready -> startNewRun -> creating -> polling -> result
creating -> ambiguous failure -> reconciliation_required
reconciliation_required -> retryCreate -> same POST body/header -> polling
reconciliation_required -> discardPendingIntent -> ready
polling -> transport/deadline failure -> observation_interrupted
observation_interrupted -> resumeObservation -> GET status/result only
terminal non-ready -> terminal with no result GET
mode/base URL change -> abort + clear intent/run/result/projection
```

Assert request methods and URLs, not only UI state. After a known `run_id`, the
complete request log must contain exactly one POST.

- [ ] **Step 2: Run Task 4 RED**

```bash
cd frontend
npm run test -- src/useLiveRun.test.tsx
```

Expected: collection/type failure because recovery actions and states do not
exist.

- [ ] **Step 3: Implement the live state machine**

Extend statuses with exact values:

```ts
export type LiveStatus =
  | "static"
  | "idle"
  | "checking"
  | "ready"
  | "creating"
  | "reconciliation_required"
  | "polling"
  | "observation_interrupted"
  | "terminal"
  | "result"
  | "error";
```

Keep the unrendered `RunCreateIntent` in `useRef`, not in public state. Store
only whether reconciliation is required and the successful acknowledgement's
`idempotent_replay` value in render state.

Extract one `observeRun(runId, ...)` path that:

1. polls status under the existing generation/deadline fence;
2. stores every valid current projection;
3. fetches result only when `delivery_status === "ready"`;
4. returns `terminal` without a result request for other terminal delivery
   states; and
5. preserves `run_id` on interruption.

`retryCreate` must reuse the ref value. `resumeObservation` must require a known
run identity and invoke only `observeRun`. Clear the intent after a valid create
acknowledgement, an explicit discard, a stable non-ambiguous create failure, or
a mode/base URL reset.

Keep the existing request generation and AbortController fences. Stale aborts
caused by a mode/URL change do not show reconciliation UI because their
generation is no longer current.

- [ ] **Step 4: Run Task 4 GREEN and repeat ordering tests**

```bash
cd frontend
npm run test -- src/useLiveRun.test.tsx src/apiClient.test.ts \
  src/runProjection.test.ts
npm run test -- src/useLiveRun.test.tsx
npm run lint
```

Expected: both hook runs pass with the same request counts and no unhandled
promise rejection.

- [ ] **Step 5: Commit Task 4**

```bash
git add frontend/src/useLiveRun.ts frontend/src/useLiveRun.test.tsx
git commit -m "feat(console): reconcile live run observation"
```

---

### Task 5: Render All Screens From The Selected Projection

**Files:**

- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/i18n.ts`
- Modify: `frontend/src/styles.css`

**Interfaces:**

- Consumes: Tasks 3 and 4.
- Produces: truthful Static/Live rendering and explicit create retry,
  discard, observation resume, and new-run controls.

- [ ] **Step 1: Write full-screen truth RED tests**

Add one completed live fixture with unique IDs for every selected screen, then
visit all navigation buttons. Require the live values and require absence of
the static values. At minimum assert:

```ts
for (const forbidden of [
  "run_demo_talent_2026_06_29",
  "ev_001",
  "decision_demo_approved_001",
  "verification_snapshot_rev_3",
  "decision-brief.md"
]) {
  expect(screen.queryByText(forbidden)).not.toBeInTheDocument();
}
```

Add UI tests for:

- no run yet -> `not observed`, never demo identity;
- real empty Evidence -> observed empty message;
- generic review -> `not required`, verification not observed;
- ready result -> canonical result content;
- failed/cancelled/timeout/review-required/blocked -> terminal card, no result
  request;
- failure cause unsupported/null/not-observed/observed;
- reconciliation-required button reuses the same intent;
- observation-resume button issues GET only;
- Static mode restores every deterministic screen;
- Chinese/English labels and accessibility names remain stable.

- [ ] **Step 2: Run Task 5 RED**

```bash
cd frontend
npm run test -- src/App.test.tsx
```

Expected: tests fail because screen components still read `demoRun` directly
and recovery actions are not rendered.

- [ ] **Step 3: Refactor App to consume one projection**

At the App boundary select exactly one model:

```ts
const projection = useMemo(
  () =>
    liveRun.state.mode === "static"
      ? buildStaticConsoleProjection()
      : buildLiveConsoleProjection({
          health: liveRun.state.health,
          created: liveRun.state.created,
          run: liveRun.state.run,
          result: liveRun.state.result,
          status: liveRun.state.status
        }),
  [liveRun.state]
);
```

Pass the relevant projection branch into `CommandCenter`, `RunLifecycle`,
`EvidenceLedger`, `ReviewVerification`, and `CanonicalResult`. Remove every
direct `demoRun` read from those components; only the static projection builder
may read it. Keep `ArchitectureMode` explicitly reference-only.

Update Live controls so button availability derives from approved states:

```text
ready                    -> Start new run
reconciliation_required -> Retry same request / Discard
observation_interrupted  -> Resume observation
terminal or result       -> Start new run
busy                     -> disabled
```

Add concise bilingual labels for the four observation states, replay receipt,
reconciliation, GET-only resume, terminal-without-result, and failure cause.
Reuse existing visual tokens; do not redesign navigation or add a dashboard.

- [ ] **Step 4: Run Task 5 GREEN and frontend checks**

```bash
cd frontend
npm run test
npm run lint
npm run build
```

Expected: every frontend test passes, lint is clean, and production build
completes.

- [ ] **Step 5: Commit Task 5**

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx \
  frontend/src/i18n.ts frontend/src/styles.css
git commit -m "feat(console): render live service authority"
```

---

### Task 6: Document The Parallel-Safe Console Contract

**Files:**

- Modify: `DESIGN.md`
- Modify: `docs/demo-console.md`
- Create: `tests/unit/test_demo_console_contracts.py`

**Interfaces:**

- Produces: standalone Console behavior, security, retry, resume, and nonclaim
  documentation without touching failure-cause shared files.

- [ ] **Step 1: Write documentation contract RED tests**

The new Python test reads `DESIGN.md`, `docs/demo-console.md`, and selected
frontend source. Require these public facts:

```text
Static and Live run data are mutually exclusive
Idempotency-Key is header-only and browser-session scoped
ambiguous create retries the same key/request
known run observation resumes with GET only
canonical artifact comes only from /result
terminal non-ready state is not a connection failure
failure-cause unsupported/null/not_observed/observed remain distinct
loopback-only, no credentials, no review or verification authority
no durable browser intent, production, exactly-once, or live-provider claim
```

Also require that the Console implementation does not import backend modules,
LangChain, LangGraph, DeepAgents, or LangSmith.

- [ ] **Step 2: Run Task 6 RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_demo_console_contracts.py -q
```

Expected: collection fails because the test does not exist, then assertions
fail until docs are updated.

- [ ] **Step 3: Update parallel-safe documentation**

Document the approved state machines and boundaries in `DESIGN.md` and
`docs/demo-console.md`. Keep operational steps concise. Do not add private
paths, future release promises, provider credentials, or a claim that the UI
verifies Evidence.

- [ ] **Step 4: Run the near-field verification matrix**

```bash
cd frontend
npm ci
npm run test
npm run lint
npm run build
npm audit --audit-level=moderate
cd ..

PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_frontend_retirement.py \
  tests/unit/test_demo_console_contracts.py -q

git diff --check origin/main..HEAD
git diff --exit-code origin/main..HEAD -- \
  api requirements.txt constraints.txt pyproject.toml VERSION \
  frontend/package.json frontend/package-lock.json \
  .github/workflows/ci.yml
```

Expected: all checks pass and the prohibited diff is empty.

- [ ] **Step 5: Commit Task 6**

```bash
git add DESIGN.md docs/demo-console.md \
  tests/unit/test_demo_console_contracts.py
git commit -m "docs(console): define live authority closure"
```

- [ ] **Step 6: Apply the failure-cause integration gate**

Fetch current refs and inspect whether Durable Run Failure Cause v1 has merged.
If `origin/main` does not contain its final merge commit, report:

```text
parallel implementation complete
shared discovery integration waiting for failure-cause main
```

Leave the worktree clean and stop. Do not push, create a PR, modify shared
files, or poll continuously.

---

### Task 7: Rebase, Publish Discovery, And Verify The Final Branch

**Precondition:** Durable Run Failure Cause v1 is merged and its final status
projection is present on `origin/main`.

**Files:**

- Rebase: current branch onto updated `origin/main`
- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/README.md`
- Modify: `tests/unit/test_demo_console_contracts.py`
- Modify only if the final failure-cause contract requires it:
  `frontend/src/runProjection.ts`, `frontend/src/runProjection.test.ts`

**Interfaces:**

- Consumes: merged additive `failure_cause` status contract.
- Produces: complete public discovery and clean review-ready branch.

- [ ] **Step 1: Verify the integration precondition**

```bash
git fetch origin
git log --oneline --decorate -12 origin/main
git diff --name-status HEAD..origin/main
```

Read the merged failure-cause API contract and status tests. Stop for redesign
if it changes or removes existing fields, touches frontend source, or makes the
Console require a backend-specific alias.

- [ ] **Step 2: Rebase once and resolve only expected documentation drift**

```bash
git rebase origin/main
```

Expected: frontend source applies cleanly. Shared discovery files have not yet
been edited by the Console branch, so no semantic conflict is expected. Do not
silently resolve an unexpected frontend or API-contract conflict.

- [ ] **Step 3: Run the focused post-rebase contract matrix**

```bash
cd frontend
npm run test -- src/runProjection.test.ts src/consoleProjection.test.ts \
  src/useLiveRun.test.tsx src/App.test.tsx
cd ..
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_demo_console_contracts.py \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_release_metadata.py -q
```

Expected: all tests pass. If the final additive field differs from the approved
shape, stop rather than weakening the parser.

- [ ] **Step 4: Add concise shared discovery**

Update only current unreleased/discovery surfaces:

- README and README_CN: Live mode uses real service-owned state, keyed create
  reconciliation, and GET-only observation resume.
- CHANGELOG `Unreleased`: one Console reliability subsection; do not edit
  historical release sections.
- docs index: link the updated Console guide and approved spec/plan.
- dedicated Console documentation test: require discovery and preserve all
  nonclaims.

Do not add a version, release note, hosted-service claim, or future roadmap.

- [ ] **Step 5: Run final deterministic verification**

```bash
cd frontend
npm ci
npm run test
npm run lint
npm run build
npm audit --audit-level=moderate
cd ..

PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_frontend_retirement.py \
  tests/unit/test_demo_console_contracts.py \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_release_metadata.py -q

PYTHON_DOTENV_DISABLED=1 python scripts/check_canonical_identity.py --root .
PYTHON_DOTENV_DISABLED=1 python scripts/final_presentation_audit.py
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 python scripts/downstream_consumer_contract.py check \
  --input docs/evidence/downstream-consumer-contract-v1.json

git diff --check origin/main..HEAD
git diff --exit-code origin/main..HEAD -- \
  api requirements.txt constraints.txt pyproject.toml VERSION \
  frontend/package.json frontend/package-lock.json \
  .github/workflows/ci.yml docs/releases
```

Expected: frontend and public-contract checks pass; backend, dependency,
version, CI, and historical release-note diff is empty.

- [ ] **Step 6: Audit truth and private boundaries**

Use focused scans over changed public files and frontend source. Confirm:

```text
no static demo identity enters the live projection builder
no idempotency key is rendered, logged, persisted, or placed in body/URL
no POST path is reachable from resumeObservation
no backend or Agent-framework import exists in frontend
no private path, credential, provider payload, or consumer-specific field exists
```

Review matches instead of blindly asserting that generic terms never appear.

- [ ] **Step 7: Commit Task 7**

```bash
git add README.md README_CN.md CHANGELOG.md docs/README.md \
  tests/unit/test_demo_console_contracts.py
git add frontend/src/runProjection.ts frontend/src/runProjection.test.ts
git commit -m "docs(console): publish live authority closure"
```

Stage the two frontend parser files only if the final merged additive contract
required an intentional compatibility adjustment; otherwise omit them from the
command and confirm they have no diff.

- [ ] **Step 8: Final branch handoff**

Confirm a clean worktree and report:

- base and final HEAD;
- ordered commits and exact changed files;
- RED/GREEN evidence per task;
- same-key/same-body reconciliation and GET-only resume request logs;
- frontend test/lint/build/audit results;
- documentation, canonical identity, presentation, evaluation, and downstream
  contract results;
- empty backend/dependency/version/CI/release diff;
- any exact skipped check or environment limitation.

Preserve the local branch/worktree for authoritative branch-diff review. Do not
push, create a PR, merge, tag, release, deploy, or clean the worktree.
