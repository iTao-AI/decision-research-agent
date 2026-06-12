# Evidence-Governed Research Foundation Execution

## Completion status

- [x] P0A safety preflight: verified constraints, backend named volumes, task DB backup,
  and same-thread active guard.
- [x] P0A evidence lifecycle: execution-boundary snapshot, content fingerprint merge,
  immutable outcome publication, timeout closure recovery, and finalizer runtime-read removal.
- [x] P0B1 foundation: independent `run_id`, segment/attempt separation, state-version
  fencing, atomic terminal/evidence persistence, `/api/runs`, and run-scoped runtime keys.
- [x] P1A deterministic contracts: bounded ResearchScope, ResearchPacket/Finding/Claim,
  ReviewBundle, canonical DecisionBrief hash/renderer, ProfileSpec, and AgentHarnessPolicy.
- [x] Backend-only DX foundation: profile manifest, `doctor`, `run --wait`, and `result`.
- [x] Presentation-layer product branding: `Decision Research Agent`, while preserving
  `deep-search-agent` compatibility identifiers.
- [ ] Not completed: Talent value gate. No real declared benchmark sample was available,
  so no improvement claim is recorded.
- [ ] Not completed: P0B2 same-thread concurrency, durable HITL, Skills, Async Subagent,
  and UI expansion. Their gates remain closed.

## TDD evidence

Key RED failures included missing `OutcomeBox`, missing execution snapshot APIs, missing
run repository, missing `/api/runs`, missing Talent contracts, and missing CLI doctor.
Each capability was implemented only after its scoped test failed for the expected reason.

## Verification

- Baseline before implementation: `python -m pytest -q` -> `325 passed in 38.78s`.
- P0A focused suite: `66 passed in 3.96s`.
- P0B1 run identity and runtime isolation focused suites: `37 passed in 17.46s`.
- Final full backend suite after branding: `python -m pytest -q` -> `363 passed in 41.52s`.
- `python -m compileall -q agent api tools` passed.
- `docker compose config --quiet` passed with a temporary empty `.env`.
- CLI help smoke tests passed for `doctor`, `run`, and `result`.
- Frontend build was not run because this isolated worktree has no installed
  `frontend/node_modules`; no dependencies were installed.

## Safety boundary

LangGraph `thread_id` remains the checkpoint/session cursor. Application `run_id` owns
execution-scoped state. LangSmith remains correlation-only. Durable HITL is not enabled.
